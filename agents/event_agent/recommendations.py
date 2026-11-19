import re
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert

from shared.contracts import ActivityProposal, ProposalBatch

from .assessment import assess, eligible_for_catalog_analysis
from .db import events, get_preferences, recommendations as saved
from .models import EventCandidate, Preferences
from .service import CATALOG_LOCK, store_candidate

HELSINKI = ZoneInfo("Europe/Helsinki")
HORIZON_DAYS = 28
SHORTLIST_SIZE = 20


def normalized(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold()))


def lock_user(conn, user_id: str) -> None:
    conn.execute(text("SELECT pg_advisory_xact_lock(67140202, hashtext(:user_id))"), {"user_id": user_id})


def list_recommendations(conn, user_id: str) -> list[dict]:
    rows = conn.execute(select(saved).where(saved.c.user_id == user_id, saved.c.current)).mappings()
    results = [
        {"id": row["id"], "event_id": row["event_id"], **row["result"],
         "scored_at": row["scored_at"], "delivery_status": row["delivery_status"]}
        for row in rows
    ]
    return sorted(results, key=lambda row: (
        row.get("decision") == "consider", -row["score"], row["event"]["start"] is None,
        EventCandidate.model_validate(row["event"]).start or datetime.max.replace(tzinfo=timezone.utc), row["id"],
    ))


def save_match(conn, user_id, key, event_id, result, now, current=True):
    statement = insert(saved).values(
        user_id=user_id, id=key, event_id=event_id, result=result, current=current, scored_at=now,
    )
    conn.execute(statement.on_conflict_do_update(
        index_elements=[saved.c.user_id, saved.c.id],
        set_={"result": result, "current": current, "scored_at": now},
    ))


def refresh(conn, user_id: str, client, settings) -> bool:
    lock_user(conn, user_id)
    prefs = get_preferences(conn, user_id)
    if prefs is None:
        raise LookupError("Event preferences not found")
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=HORIZON_DAYS)
    candidates = []
    for event_id, details, knowledge in conn.execute(
        select(events.c.id, events.c.details, events.c.knowledge).order_by(events.c.id)
    ):
        event = EventCandidate.model_validate(details)
        if not eligible_for_catalog_analysis(event, now) or event.start >= horizon:
            continue
        candidates.append((event_id, event, knowledge or {}))
    decisions = assess(conn, client, settings, prefs, candidates)
    matches = [(key, event.start, decisions[key]) for key, event, _ in candidates if decisions[key]["decision"] != "skip"]
    matches.sort(key=lambda entry: (entry[2]["decision"] != "recommend", -entry[2]["score"], entry[1], entry[0]))
    shortlist = {key for key, _, _ in matches[:SHORTLIST_SIZE]}
    conn.execute(update(saved).where(
        saved.c.user_id == user_id, saved.c.event_id.is_not(None), saved.c.current
    ).values(current=False))
    for event_id, result in decisions.items():
        save_match(conn, user_id, event_id, event_id, result, now, current=event_id in shortlist)
    return prefs.auto_publish


def match_posters(conn, user_id, candidates, share_events, client, settings):
    lock_user(conn, user_id)
    prefs = get_preferences(conn, user_id)
    if prefs is None:
        raise LookupError("Event preferences not found")
    if share_events:
        conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": CATALOG_LOCK})
    now = datetime.now(timezone.utc)
    matched = set()
    shared = set()
    seen = set()
    inputs = {}
    for event in candidates:
        start = event.start.astimezone(timezone.utc).isoformat() if event.start else normalized(event.time_note or "")
        identity = "\x1f".join((normalized(event.title), normalized(event.organizer or ""),
                                normalized(event.venue or event.city or ""), start))
        digest = sha256(identity.encode()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        event_id = None
        if share_events:
            _, event_id = store_candidate(conn, event.model_copy(update={"external_id": digest}))
            shared.add(event_id)
        if event.start is not None and event.start < now:
            continue
        key = event_id or f"poster-{digest}"
        inputs[key] = (event, event_id)
    assessments = assess(conn, client, settings, prefs, [
        (key, event, conn.scalar(select(events.c.knowledge).where(events.c.id == event_id)) or {}
         if event_id else None)
        for key, (event, event_id) in sorted(inputs.items())
    ])
    for key, result in assessments.items():
        _, event_id = inputs[key]
        if result["decision"] == "recommend" or (event_id and result["decision"] == "consider"):
            matched.add(key)
        if event_id or key in matched:
            save_match(conn, user_id, key, event_id, result, now, current=key in matched)
    return matched, len(shared), prefs.auto_publish


def to_proposal(user_id, row, event, now):
    if row["result"].get("decision", "recommend") != "recommend":
        return None
    if event.cancelled or event.start is None or event.end is None or event.start < now:
        return None
    start = event.start.astimezone(HELSINKI).replace(tzinfo=None)
    end = event.end.astimezone(HELSINKI).replace(tzinfo=None)
    if end <= start:
        return None
    return ActivityProposal(
        proposal_id=f"event-{row['id']}", source_agent="event", user_id=user_id,
        type="event", title=event.title, fixed_time={"start": start, "end": end},
        opportunity_ref=row["event_id"] or row["id"], resource_url=event.url, location=event.venue,
        value={"study": 0.0, "career": 0.0, "social": min(row["result"]["score"], 0.9)},
        reason=row["result"]["reason"],
    )


def publish(conn, client: httpx.Client, user_id: str, ids: list[str] | None = None) -> dict:
    lock_user(conn, user_id)
    rows = conn.execute(
        select(saved, events.c.details.label("catalog_event"))
        .outerjoin(events, events.c.id == saved.c.event_id)
        .where(saved.c.user_id == user_id)
    ).mappings().all()
    chosen = {row["id"] for row in rows if row["current"]} if ids is None else set(ids)
    if chosen - {row["id"] for row in rows if row["current"]}:
        raise LookupError("Recommendation not found")
    now = datetime.now(timezone.utc)
    result = {"published": [], "unchanged": [], "skipped": [], "failed": [], "withdrawn": []}
    pending = {}

    def record(key, status, **values):
        conn.execute(update(saved).where(saved.c.user_id == user_id, saved.c.id == key).values(
            delivery_status=status, **values,
        ))
        result[status].append(key)

    for row in rows:
        key = row["id"]
        event = EventCandidate.model_validate(row["catalog_event"] or row["result"]["event"])
        if event.cancelled and row["last_published"]:
            path = f"/proposals/{quote(user_id, safe='')}/event-{quote(key, safe='')}/withdraw"
            try:
                response = client.post(path)
                if response.status_code != 404:
                    response.raise_for_status()
            except httpx.HTTPError:
                record(key, "failed")
            else:
                record(key, "withdrawn", last_published=None, current=False)
            continue
        if key not in chosen and (ids is not None or not row["last_published"]):
            continue
        proposal = to_proposal(user_id, row, event, now)
        if proposal is None:
            if key in chosen:
                record(key, "skipped")
        elif proposal.model_dump(mode="json") == row["last_published"]:
            if row["delivery_status"] != "published":
                conn.execute(update(saved).where(saved.c.user_id == user_id, saved.c.id == key).values(
                    delivery_status="published",
                ))
            result["unchanged"].append(key)
        else:
            pending[key] = proposal

    if pending:
        batch = ProposalBatch(source_agent="event", user_id=user_id, generated_at=now,
                              proposals=list(pending.values()))
        try:
            client.post("/proposals/batch", json=batch.model_dump(mode="json")).raise_for_status()
        except httpx.HTTPError:
            for key in pending:
                record(key, "failed")
        else:
            for key, proposal in pending.items():
                record(key, "published", last_published=proposal.model_dump(mode="json"))
    return result
