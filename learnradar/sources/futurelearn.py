"""FutureLearn: online courses from (mostly UK and European) universities, from its public courses feed."""
from __future__ import annotations

import datetime as dt

from ..http import FetchError, get
from ..models import Offer
from ..text import clean_url, clip, strip_html
from . import SourceResult

URL = "https://www.futurelearn.com/feeds/courses"
LEVELS = {"introductory": "beginner", "open": "beginner", "intermediate": "intermediate", "advanced": "advanced"}


def to_offer(c: dict, today: dt.date) -> Offer | None:
    if not c.get("uuid") or not c.get("name") or c.get("open_for_enrolment") is False:
        return None
    access = (c.get("access_model") or "").lower()
    runs = sorted(c.get("runs") or [], key=lambda r: r.get("start_date") or "")
    iso = today.isoformat()
    upcoming = [r for r in runs if (r.get("start_date") or "") >= iso]
    nxt = upcoming[0] if upcoming else (runs[-1] if runs else {})
    sponsored = (nxt.get("business_model") == "sponsored_access")
    if sponsored or access == "free":
        cost, note = ("funded", "Sponsored: free full access") if sponsored else ("free", "")
    elif access == "unlimited":
        cost, note = "audit", "Free limited access; pay to upgrade for full access and a certificate"
    elif access in ("experttrack", "professionalcertificate"):
        cost, note = "paid", "Subscription programme (free trial available)"
    elif access == "premium":
        cost, note = "paid", "Paid course"
    else:
        cost, note = "unknown", ""
    kind = "training" if access in ("experttrack", "professionalcertificate") else "online"
    weeks, hours = nxt.get("duration_in_weeks"), c.get("hours_per_week")
    duration = ", ".join(x for x in [f"{weeks} weeks" if weeks else "", f"{hours} h/week" if hours else ""] if x)
    if upcoming:
        status, starts = "scheduled", nxt.get("start_date") or ""
    else:
        status, starts = "anytime", ""
    rev = c.get("reviews") or {}
    tags = ["certificate"] if c.get("has_certificates") else []
    if (rev.get("total_count") or 0) >= 10 and rev.get("average_score"):
        tags.append(f"rated {rev['average_score']:.1f}/5 ({rev['total_count']})")
    summary = strip_html(c.get("introduction") or "") or strip_html(c.get("description") or "")
    return Offer(
        source="futurelearn", source_id=c["uuid"], title=strip_html(c["name"]), url=clean_url(c.get("url") or ""),
        provider=(c.get("organisation") or {}).get("name", ""), kind=kind,
        level=LEVELS.get((c.get("course_level") or "").lower(), ""), cost=cost, cost_note=note,
        languages=[c.get("language") or "en"], online=True, self_paced=status == "anytime", duration=duration,
        starts=starts, status=status, tags=tags,
        subjects=list(dict.fromkeys((c.get("categories") or []) + (c.get("topics") or [])))[:10],
        summary=clip(summary, 260),
    )


def fetch(cfg: dict, today: dt.date | None = None) -> SourceResult:
    res = SourceResult("futurelearn")
    today = today or dt.date.today()
    try:
        data = get(URL) or []
        res.requests = 1
    except FetchError as e:
        res.ok, res.error = False, str(e)[:200]
        return res
    for c in data:
        o = to_offer(c, today)
        if o:
            res.offers.append(o)
    res.detail = f"{len(res.offers)} of {len(data)} courses open for enrolment"
    return res
