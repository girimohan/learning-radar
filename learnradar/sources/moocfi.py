"""MOOC.fi: free online courses run by the University of Helsinki and partners (GraphQL API)."""
from __future__ import annotations

import re

from ..http import FetchError, get
from ..models import Offer
from ..text import clip, strip_html
from . import SourceResult

URL = "https://www.mooc.fi/api/graphql"
QUERY = "{ courses(language: \"en\") { id name slug ects status hidden language start_date end_date link description } }"
LANG = {"se": "sv", "fi": "fi", "en": "en", "de": "de", "de-at": "de", "sv": "sv"}


def to_offer(c: dict, languages: set[str]) -> Offer | None:
    if c.get("hidden") or c.get("status") not in ("Active", "Upcoming") or not c.get("name"):
        return None
    lang = LANG.get((c.get("language") or "").lower(), (c.get("language") or "")[:2].lower())
    if languages and lang and lang not in languages:
        return None
    m = re.search(r"\d+(?:[.,]\d+)?", c.get("ects") or "")
    credits = float(m.group(0).replace(",", ".")) if m else None
    upcoming = c.get("status") == "Upcoming"
    slug = c.get("slug") or ""
    return Offer(
        source="moocfi", source_id=c.get("id") or slug, title=strip_html(c["name"]),
        url=c.get("link") or f"https://www.mooc.fi/en/", provider="MOOC.fi (University of Helsinki)",
        kind="online", cost="free", languages=[lang] if lang else [], online=True, self_paced=not upcoming,
        credits=credits, duration=f"{c['ects']} ECTS" if c.get("ects") else "",
        starts=(c.get("start_date") or "")[:10] if upcoming else "", status="upcoming" if upcoming else "anytime",
        tags=["certificate"], summary=clip(strip_html(c.get("description") or ""), 260),
    )


def fetch(cfg: dict) -> SourceResult:
    res = SourceResult("moocfi")
    languages = set(cfg.get("languages", ["en", "fi", "sv", "de"]))
    try:
        d = get(URL, json_body={"query": QUERY}) or {}
        res.requests = 1
    except FetchError as e:
        res.ok, res.error = False, str(e)[:200]
        return res
    courses = (d.get("data") or {}).get("courses") or []
    if d.get("errors") and not courses:
        res.ok, res.error = False, str(d["errors"])[:200]
        return res
    seen = set()
    for c in courses:
        o = to_offer(c, languages)
        if o and o.title.lower() not in seen:
            seen.add(o.title.lower())
            res.offers.append(o)
    res.detail = f"{len(res.offers)} active or upcoming of {len(courses)} courses"
    return res
