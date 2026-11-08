import json
import ssl
import urllib.parse
import urllib.request
import hashlib
import certifi
import re
from db import cache_get, cache_set
from llm import ask_llm

ESCO_API = "https://ec.europa.eu/esco/api"
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

# Small in-memory copy so the same run does not ask the database twice
_memory = {}


def _cached(key):
    """Look up a key in memory first, then in the database."""
    if key not in _memory:
        _memory[key] = cache_get(key)
    return _memory[key]


def _store(key, data):
    """Save a value in memory and in the database."""
    _memory[key] = data
    cache_set(key, data)


def _get(path, params):
    """GET an ESCO endpoint, using the database cache when possible."""
    query = urllib.parse.urlencode({**params, "language": "en"})
    url = f"{ESCO_API}/{path}?{query}"
    data = _cached(url)
    if data is None:
        with urllib.request.urlopen(url, timeout=30, context=SSL_CONTEXT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        _store(url, data)
    return data


def search_esco(text, kind="skill", limit=5):
    """Search ESCO for a skill or occupation and return (title, uri) pairs."""
    data = _get("search", {"text": text, "type": kind, "limit": limit})
    results = data.get("_embedded", {}).get("results", [])
    return [(r["title"], r["uri"]) for r in results]


def get_skill(uri):
    """Fetch full details of one ESCO skill (or skill group) by its URI."""
    return _get("resource/skill", {"uri": uri})


def get_occupation(uri):
    """Fetch full details of one ESCO occupation by its URI."""
    return _get("resource/occupation", {"uri": uri})


def get_ancestors(uri, max_steps=6):
    """Walk up the ESCO hierarchy and return the chain of (title, uri)."""
    chain = []
    current = uri
    for _ in range(max_steps):
        links = get_skill(current)["_links"]
        # Skills use broaderHierarchyConcept; higher groups use broaderConcept
        parents = links.get("broaderHierarchyConcept") or links.get("broaderConcept") or []
        if not parents:
            break
        parent = parents[0]
        chain.append((parent["title"], parent["uri"]))
        current = parent["uri"]
    return chain


def specific_groups(uri):
    """Return the specific ancestor groups of a skill (codes with a dot, like S5.1)."""
    groups = set()
    for _, parent_uri in get_ancestors(uri):
        if "." in parent_uri.rsplit("/", 1)[-1]:
            groups.add(parent_uri)
    return groups


def occupation_groups(occ):
    """All specific groups of the occupation's essential and optional skills."""
    groups = set()
    links = occ["_links"]
    for s in links.get("hasEssentialSkill", []) + links.get("hasOptionalSkill", []):
        groups |= specific_groups(s["uri"])
    return groups


def esco_relevance(skill_uri, occ):
    """1.0 essential, 0.6 optional, 0.3 same specific group, else 0."""
    links = occ["_links"]
    essential = {s["uri"] for s in links.get("hasEssentialSkill", [])}
    optional = {s["uri"] for s in links.get("hasOptionalSkill", [])}
    if skill_uri in essential:
        return 1.0
    if skill_uri in optional:
        return 0.6
    if specific_groups(skill_uri) & occupation_groups(occ):
        return 0.3
    return 0.0


def map_to_esco(name, kind="skill"):
    """Map free text to the best matching ESCO skill or occupation (title, uri), or None."""
    key = f"map:{kind}:{name.lower()}"
    cached = _cached(key)
    if cached is not None:
        # Stored as {"result": [title, uri]} or {"result": None}
        return tuple(cached["result"]) if cached["result"] else None

    candidates = search_esco(name, kind=kind)
    if not candidates:
        # Abbreviations like "SEO" or "AI" may find nothing: ask for the full name and retry
        full = ask_llm(f"Write the full name of the {kind} '{name}'. Answer with the name only.").strip()
        candidates = search_esco(full, kind=kind)
        if not candidates:
            _store(key, {"result": None})
            return None

    # Exact title match: no need to ask the LLM
    for title, uri in candidates:
        if title.lower() == name.lower():
            _store(key, {"result": [title, uri]})
            return (title, uri)

    options = "\n".join(f"{i}. {title}" for i, (title, _) in enumerate(candidates))
    prompt = f"""Which ESCO {kind} best matches "{name}"?
{options}
Answer with the number only."""
    answer = ask_llm(prompt)
    digits = "".join(ch for ch in answer if ch.isdigit())
    index = int(digits[0]) if digits else 0
    if index >= len(candidates):
        index = 0  # fall back to the first result

    # Save the choice so the same text always maps to the same ESCO concept
    _store(key, {"result": list(candidates[index])})
    return candidates[index]

def shares_word(a, b):
    """True if two texts are the same or share a meaningful word (or word stem)."""
    squash = lambda s: re.sub(r"[^a-z0-9#+]", "", s.lower())
    if squash(a) == squash(b):
        return True  # exact match, e.g. "C#", "R", "No SQL" vs "NoSQL"
    stop = {"and", "with", "for", "the", "use", "using"}
    words = lambda s: {w[:5] for w in re.findall(r"[a-z]+", s.lower()) if len(w) >= 3 and w not in stop}
    return bool(words(a) & words(b))

def is_good_match(name, title):
    """Ask the LLM if an ESCO skill title really describes the skill name (cached)."""
    squash = lambda s: re.sub(r"[^a-z0-9#+]", "", s.lower())
    if squash(name) == squash(title):
        return True  # exact match, no need to ask
        # One name contains the other (e.g. "Microsoft Office" in "use microsoft office").
    # Only when the longer one is short, so "React" vs "react calmly in stressful situations" is not accepted.
    a, b = squash(name), squash(title)
    short, long_ = sorted([a, b], key=len)
    long_words = max(name, title, key=len).split()
    if len(short) >= 3 and short in long_ and len(long_words) <= 3:
        return True
    
    prompt = f"""A CV lists the skill "{name}". Is it the same skill or the same specific area as "{title}"?
                    Examples:
                    Git -> tools for software configuration management: yes
                    Python -> use scripting programming: yes
                    Teaching Methods -> advise on teaching methods: yes
                    Artificial Intelligence -> principles of artificial intelligence: yes
                    Flash -> install roof flashing: no
                    React -> react calmly in stressful situations: no
                    Docker -> learning management systems: no
                    Answer only yes or no."""
    key = "verify:" + hashlib.md5(prompt.encode()).hexdigest()
    cached = _cached(key)
    if cached is not None:
        return cached["ok"]
    
    answer = ask_llm(prompt).strip().lower()
    ok = "yes" in answer[:20]
    _store(key, {"ok": ok})
    return ok

def skills_to_uris(names):
    """Map a list of skill names to a set of ESCO skill URIs."""
    uris = set()
    for name in names:
        split = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
        text = split if all(len(w) >= 3 for w in split.split()) else name
        candidates = search_esco(text, "skill", limit=5)
        if not candidates:
            # Abbreviations may find nothing: fall back to the old mapper (it retries with the full name)
            result = map_to_esco(text, "skill")
            candidates = [result] if result else []
        # Try the top results in order and keep the first one the LLM accepts
        for title, uri in candidates:
            if is_good_match(text, title):
                uris.add(uri)
                break
        else:
           pass  # No ESCO equivalent: the skill is still compared by name
    return uris

if __name__ == "__main__":
    for goal in ["AI", "data scientist", "nurse", "marketing manager"]:
        print(goal, "->", map_to_esco(goal, kind="occupation"))