import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import httpx
from pydantic import ValidationError

from ..models import EventCandidate

logger = logging.getLogger(__name__)
HELSINKI = ZoneInfo("Europe/Helsinki")


def localized(value):
    if isinstance(value, dict):
        return next((value[key] for key in ("fi", "en", "sv") if value.get(key)), None)
    return value if isinstance(value, str) and value else None


def scrape(client: httpx.Client, source, limit: int | None = None):
    cutoff = datetime.now(timezone.utc) + timedelta(hours=48)
    start_date = cutoff.astimezone(HELSINKI).date().isoformat()
    url = httpx.URL(source["url"]).copy_set_param("start", start_date)
    if limit is not None:
        page_size = min(limit, int(url.params.get("page_size", "100")))
        url = url.copy_set_param("page_size", str(page_size))
    origin = (url.scheme, url.host, url.port)
    visited = set()
    while url:
        if url in visited or (url.scheme, url.host, url.port) != origin:
            raise ValueError("Invalid pagination URL")
        visited.add(url)
        response = client.get(url)
        response.raise_for_status()
        page = response.json()
        for item in page["data"]:
            location = item.get("location") or {}
            try:
                candidate = EventCandidate(
                    source_key=source["key"],
                    external_id=item.get("id"),
                    title=localized(item.get("name")),
                    organizer=localized(item.get("provider_name")),
                    topics=[
                        name for keyword in item.get("keywords") or []
                        if (name := localized(keyword.get("name")))
                    ],
                    languages=[
                        language["id"].lower() for language in item.get("in_language") or []
                        if isinstance(language, dict) and isinstance(language.get("id"), str)
                    ],
                    online=item.get("is_virtualevent"),
                    description=localized(item.get("short_description")),
                    url=localized(item.get("info_url")) or item.get("@id"),
                    venue=localized(location.get("name")),
                    city=localized(location.get("address_locality")),
                    start=item.get("start_time"),
                    end=item.get("end_time"),
                    cancelled=bool(item.get("deleted")) or item.get("event_status") == "EventCancelled",
                )
            except ValidationError as error:
                fields = ", ".join(".".join(map(str, issue["loc"])) or "event" for issue in error.errors())
                logger.warning("Skipping %s event %s with invalid fields: %s", source["key"], item.get("id"), fields)
                yield None
            else:
                if candidate.start is not None and candidate.start >= cutoff:
                    yield candidate
        next_page = page["meta"].get("next")
        url = httpx.URL(urljoin(str(response.url), next_page)) if next_page else None
