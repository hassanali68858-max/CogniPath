import logging
from datetime import datetime
from functools import partial
from time import sleep

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import create_engine, select
from sqlalchemy.exc import SQLAlchemyError

from .assessment import collect_knowledge
from .db import Settings, events, preferences
from .models import EventCandidate
from .recommendations import HELSINKI, publish, refresh
from .service import queue_nightly, run_next

logger = logging.getLogger(__name__)


def enrich_events(client, conn, event_ids):
    rows = conn.execute(select(events.c.id, events.c.details, events.c.knowledge).where(
        events.c.id.in_(event_ids)
    ).order_by(events.c.id))
    candidates = [(event_id, EventCandidate.model_validate(details), knowledge or {})
                  for event_id, details, knowledge in rows]
    collect_knowledge(conn, client, Settings(), candidates)


def match_nightly(engine, planner, model_client):
    settings = Settings()
    summary = {"users": 0, "matched": 0, "published": 0, "withdrawn": 0, "failed": 0}
    with engine.connect() as conn:
        users = conn.scalars(select(preferences.c.user_id).where(
            preferences.c.preferences["nightly_matching"].as_boolean().is_(True)
        )).all()
    for user_id in users:
        summary["users"] += 1
        try:
            with engine.begin() as conn:
                auto_publish = refresh(conn, user_id, model_client, settings)
            summary["matched"] += 1
            if auto_publish:
                with engine.begin() as conn:
                    delivery = publish(conn, planner, user_id)
                summary["published"] += len(delivery["published"])
                summary["withdrawn"] += len(delivery["withdrawn"])
                summary["failed"] += bool(delivery["failed"])
        except (LookupError, ValueError, SQLAlchemyError):
            summary["failed"] += 1
            logger.exception("Nightly recommendations failed for user %s", user_id)
    return summary


def main():
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    engine = create_engine(settings.event_database_url, pool_pre_ping=True)
    scheduler = BackgroundScheduler(timezone=HELSINKI)

    def enqueue():
        queue_nightly(engine, datetime.now(HELSINKI).date())

    hour, minute = settings.event_nightly_hour, settings.event_nightly_minute
    scheduler.add_job(enqueue, "cron", hour=hour, minute=minute, misfire_grace_time=3600, coalesce=True)
    scheduler.start()
    try:
        now = datetime.now(HELSINKI)
        if (now.hour, now.minute) >= (hour, minute):
            enqueue()
        with (
            httpx.Client(timeout=20, follow_redirects=True) as client,
            httpx.Client(timeout=10, base_url=settings.event_planner_url) as planner,
            httpx.Client(timeout=45) as model_client,
        ):
            match = partial(match_nightly, engine, planner, model_client)
            while True:
                try:
                    if not run_next(engine, client, match, partial(enrich_events, model_client)):
                        sleep(2)
                except SQLAlchemyError:
                    logger.exception("Worker database operation failed")
                    sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        scheduler.shutdown()
        engine.dispose()


if __name__ == "__main__":
    main()
