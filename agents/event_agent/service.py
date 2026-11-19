import logging
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert

from .assessment import eligible_for_catalog_analysis
from .db import events, runs, source_events, sources
from .llm import ModelUnavailable
from .sources import collect

logger = logging.getLogger(__name__)
CATALOG_LOCK = 67140201
WORKER_LOCK = 67140203


def reset_event_data(conn) -> bool:
    for key in (WORKER_LOCK, CATALOG_LOCK):
        if not conn.scalar(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}):
            return False
    conn.execute(text(
        "TRUNCATE event.recommendations, event.source_events, event.events, "
        "event.ingestion_runs, event.poster_uploads, event.user_preferences, event.sources"
    ))
    conn.execute(sources.insert(), [
        {
            "key": "keski-suomi",
            "name": "Keski-Suomi Events",
            "url": (
                "https://keskisuomievents.fi/api/v1/event?include=location%2Carea"
                "&page=1&page_size=500&super_event_type=none%2Cumbrella"
            ),
            "adapter": "linked_events",
            "enabled": True,
        },
        {"key": "poster", "name": "Shared board uploads", "url": "", "adapter": "poster", "enabled": False},
    ])
    return True


def queue_nightly(engine, local_date):
    with engine.begin() as conn:
        keys = list(conn.scalars(select(sources.c.key).where(sources.c.enabled).order_by(sources.c.key)))
        conn.execute(insert(runs).values(
            id=uuid4().hex, nightly_date=local_date, source_keys=keys, status="queued", results={},
        ).on_conflict_do_nothing(index_elements=[runs.c.nightly_date]))


def fingerprint(candidate):
    fields = (candidate.title, candidate.organizer, candidate.venue)
    if candidate.start is None or not all(value and value.strip() for value in fields):
        return None
    parts = [" ".join(value.casefold().split()) for value in fields]
    parts.append(candidate.start.astimezone(timezone.utc).isoformat())
    return repr(parts)


def store_candidate(conn, candidate, *, existing_only=False):
    external_key = candidate.external_id or (str(candidate.url) if candidate.url else None)
    if not external_key:
        raise ValueError("Event needs a stable ID or URL")
    key = (source_events.c.source_key == candidate.source_key, source_events.c.external_key == external_key)
    data = candidate.model_dump(mode="json")
    existing = conn.execute(select(source_events).where(*key)).mappings().one_or_none()
    if existing_only and existing is None:
        return "skipped", None
    if existing and existing["details"] == data:
        return "unchanged", existing["event_id"]

    signature = fingerprint(candidate)
    if existing:
        conn.execute(update(source_events).where(*key).values(details=data))
        changes = {"fingerprint": signature, "details": data}
        if not candidate.cancelled:
            changes["knowledge"] = None
        conn.execute(update(events).where(events.c.id == existing["event_id"]).values(**changes))
        return "updated", existing["event_id"]

    matches = []
    if signature is not None:
        matches = conn.scalars(select(events.c.id).where(events.c.fingerprint == signature).limit(2)).all()
    if len(matches) == 1:
        event_id = matches[0]
    else:
        event_id = uuid4().hex
        conn.execute(events.insert().values(id=event_id, fingerprint=signature, details=data))
    conn.execute(source_events.insert().values(
        source_key=candidate.source_key, external_key=external_key, event_id=event_id, details=data,
    ))
    return "inserted", event_id


def ingest_run(conn, client, run, enrich):
    results = {}
    failed = 0
    remaining = run["limit"]
    for key in run["source_keys"]:
        if remaining == 0:
            break
        counts = dict.fromkeys(("inserted", "updated", "unchanged", "failed"), 0)
        try:
            with conn.begin():
                source = conn.execute(select(sources).where(
                    sources.c.key == key, sources.c.enabled.is_(True)
                )).mappings().one()
            candidates = collect(client, source, limit=remaining)
            event_ids = set()
            now = datetime.now(timezone.utc)
            with conn.begin():
                conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CATALOG_LOCK})
                for candidate in candidates:
                    if candidate is None:
                        counts["failed"] += 1
                        continue
                    if not candidate.cancelled and not eligible_for_catalog_analysis(candidate, now):
                        continue
                    status, event_id = store_candidate(conn, candidate, existing_only=candidate.cancelled)
                    if status == "skipped":
                        continue
                    if not candidate.cancelled:
                        event_ids.add(event_id)
                    counts[status] += 1
                if event_ids:
                    enrich(conn, event_ids)
            if remaining is not None:
                remaining -= counts["inserted"] + counts["updated"] + counts["unchanged"]
        except (ValueError, TypeError, httpx.HTTPError, LookupError) as error:
            logger.warning("Source %s failed (%s)", key, error)
            counts = {"inserted": 0, "updated": 0, "unchanged": 0, "failed": 1}
            if isinstance(error, ModelUnavailable):
                counts["error"] = str(error)
            failed += 1
        results[key] = counts
    status = "succeeded"
    if not results:
        status = "skipped"
    elif failed == len(results):
        status = "failed"
    elif any(result["failed"] for result in results.values()):
        status = "partial"
    with conn.begin():
        conn.execute(update(runs).where(runs.c.id == run["id"]).values(
            status="matching" if run["nightly_date"] else status, source_status=status, results=results,
        ))


def run_next(engine, client, match_nightly, enrich) -> bool:
    with engine.connect() as conn:
        with conn.begin():
            locked = conn.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": WORKER_LOCK})
        if not locked:
            return False
        try:
            with conn.begin():
                pending = select(runs).where(
                    runs.c.status.in_(("queued", "running", "matching"))
                ).order_by(
                    (runs.c.status != "queued").desc(), runs.c.created_at, runs.c.id
                ).limit(1)
                run = conn.execute(pending).mappings().first()
                if run is None:
                    return False
                if run["status"] != "matching":
                    conn.execute(update(runs).where(runs.c.id == run["id"]).values(status="running"))
            if run["status"] != "matching":
                ingest_run(conn, client, run, enrich)
            if run["nightly_date"]:
                summary = match_nightly()
                with conn.begin():
                    source_status = conn.scalar(select(runs.c.source_status).where(runs.c.id == run["id"]))
                    status = "partial" if summary["failed"] or source_status in ("partial", "failed") else "succeeded"
                    conn.execute(update(runs).where(runs.c.id == run["id"]).values(status=status, matching=summary))
            return True
        finally:
            with conn.begin():
                conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": WORKER_LOCK})
