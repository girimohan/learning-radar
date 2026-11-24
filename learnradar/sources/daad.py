"""DAAD International Programmes: degree programmes, language courses and summer schools in Germany.

Reads the JSON search behind daad.de's public programme finder, a few pages of 500.
"""
from __future__ import annotations

import datetime as dt
import re

from ..http import FetchError, get
from ..models import Offer
from ..text import parse_text_date, strip_html
from . import SourceResult

URL = "https://www2.daad.de/deutschland/studienangebote/international-programmes/api/solr/en/search.json"
SITE = "https://www2.daad.de"
LEVELS = {1: "bachelor", 2: "master", 3: "doctorate"}
LANGS = {"english": "en", "german": "de", "french": "fr", "spanish": "es", "finnish": "fi", "swedish": "sv"}
_NUM = re.compile(r"\d[\d,.]*")


def _amount(s: str) -> int | None:
    m = _NUM.search(s or "")
    if not m:
        return None
    try:
        return int(float(m.group(0).replace(",", "")))
    except ValueError:
        return None


def to_offer(c: dict, today: dt.date) -> Offer | None:
    title = strip_html(c.get("courseName") or c.get("courseNameShort") or "")
    if not c.get("id") or not title:
        return None
    ctype = c.get("courseType")
    level = LEVELS.get(ctype, "")
    name_l = (title + " " + (c.get("subject") or "")).lower()
    if level:
        kind = "degree"
    elif "german" in name_l or "language" in name_l or "sprach" in name_l:
        kind = "prep"
    else:
        kind = "course"
    dates = c.get("date") or []
    iso = today.isoformat()
    future = [d for d in dates if (d.get("start") or "") >= iso[:7]]
    nxt = future[0] if future else (dates[0] if dates else {})
    deadlines = [parse_text_date(c.get("applicationDeadline"))] + [d.get("registrationDeadline") or "" for d in dates]
    deadlines = sorted(d for d in deadlines if d and d >= iso)
    deadline = deadlines[0] if deadlines else ""
    fees = (c.get("tuitionFees") or "").strip()
    course_cost = nxt.get("costs") if isinstance(nxt.get("costs"), (int, float)) else None
    if course_cost:
        cost, note = "paid", f"Course fee €{course_cost:,.0f}"
    elif fees.lower().startswith("no tuition"):
        cost, note = "free", "No tuition fees; a semester contribution (usually a few hundred euros) is common"
    elif "varies" in fees.lower():
        cost, note = "varies", "Tuition depends on the student (see the programme page)"
    elif _amount(fees):
        cost, note = "paid", f"Tuition €{_amount(fees):,} (see the programme page for the period)"
    else:
        cost, note = "unknown", ""
    if dates and nxt.get("start"):
        starts = nxt["start"]
        duration = f"{nxt.get('start')} to {nxt.get('end')}" if nxt.get("end") else ""
    else:
        starts = c.get("beginning") or ""
        duration = c.get("programmeDuration") or ""
    adl = (c.get("applicationDeadline") or "").lower()
    # A future deadline does not mean applications are open yet, so only "no deadline" counts as open;
    # scoring ranks the others by how close the deadline is.
    status = "open" if "no deadline" in adl or "any time" in adl else "scheduled"
    langs = sorted({LANGS.get(x.lower(), x.lower()[:2]) for x in (c.get("languages") or [])})
    subj = strip_html(c.get("subject") or "")
    bits = [f"Subject: {subj}"] if subj and subj.lower() not in title.lower() else []   # the rest is in tags
    # isCompleteOnlinePossible is also true for "Partly online" and "Hybrid"; the badge says which.
    badge = (c.get("badgeLabel") or "").lower()
    tags = ["scholarship_info"] if c.get("financialSupport") else []
    if badge in ("partly online", "hybrid"):
        tags.append("partly_online")
    return Offer(
        source="daad", source_id=str(c["id"]), title=title, url=SITE + (c.get("link") or ""),
        provider=strip_html(c.get("academy") or ""), country="Germany", city=c.get("city") or "", kind=kind,
        level=level, cost=cost, cost_note=note, languages=langs, online=badge == "fully online",
        duration=duration, starts=starts, deadline=deadline, status=status, tags=tags,
        subjects=[subj] if subj else [], summary=". ".join(bits),
    )


def fetch(cfg: dict, today: dt.date | None = None) -> SourceResult:
    res = SourceResult("daad")
    today = today or dt.date.today()
    size = int(cfg.get("page_size", 500))
    seen = set()
    offset, total = 0, None
    try:
        while total is None or offset < total:
            d = get(URL, params={"q": "", "limit": size, "offset": offset, "sort": 4})
            res.requests += 1
            if not d:
                break
            total = int(d.get("numResults") or 0)
            batch = d.get("courses") or []
            if not batch:
                break
            for c in batch:
                o = to_offer(c, today)
                if o and o.source_id not in seen:
                    seen.add(o.source_id)
                    res.offers.append(o)
            offset += size
            if offset > 20000:
                break
    except FetchError as e:
        if not res.offers:
            res.ok, res.error = False, str(e)[:200]
            return res
        res.detail = f"stopped early: {e}; "
    res.detail += f"{len(res.offers)} of {total or 0} programmes"
    return res
