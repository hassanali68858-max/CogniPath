import httpx

from .collectors import scrape_keski_suomi
from .models import EventCandidate

ADAPTERS = {"linked_events": scrape_keski_suomi.scrape}


def collect(client: httpx.Client, source, limit: int | None = None) -> list[EventCandidate | None]:
    candidates = []
    collected = 0
    for candidate in ADAPTERS[source["adapter"]](client, source, limit=limit):
        if candidate is None or not (candidate.external_id or candidate.url):
            candidates.append(None)
            continue
        candidates.append(candidate)
        collected += 1
        if collected == limit:
            break
    return candidates
