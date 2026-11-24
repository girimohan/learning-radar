"""Sweden: Skolverket's Susa-navet open API, the national register of education offers.

Three resources are joined: events (one run of a course: dates, place, deadline, language, pace), infos (what
the course is: title, credits, description) and providers (school names).

* Higher vocational education (YH), labour market training (AUB) and folk high schools (FHS) are read in full;
  each is a page or two of 2,000.
* University courses and programmes (HS) number about 64,000 events, so only those added or updated in the last
  `hs_days` days are read (most of next term's courses are), and only runs whose application is still open or
  that have not started are kept.
"""
from __future__ import annotations

import datetime as dt

from ..http import FetchError, get
from ..models import Offer
from ..text import clip, strip_html
from . import SourceResult

API = "https://api.skolverket.se/susa-navet/emil3"
FULL_TYPES = ("YH", "AUB", "FHS")
LANG = {"swe": "sv", "eng": "en", "fin": "fi", "nor": "no", "deu": "de", "ger": "de"}
KIND = {"YH": "vocational", "AUB": "training", "FHS": "course"}


def _s(obj: dict | None, *prefer: str) -> str:
    """Text of a {"strings": [{"lang": "swe", "value": ...}]} or {"urls": [...]} object, preferring English."""
    items = (obj or {}).get("strings") or (obj or {}).get("urls") or []
    for lang in prefer or ("eng", "swe"):
        for x in items:
            if x.get("lang") == lang and (x.get("value") or "").strip():
                return x["value"].strip()
    return next(((x.get("value") or "").strip() for x in items if (x.get("value") or "").strip()), "")


def _all(path: str, params: dict, res: SourceResult, key: str, max_pages: int = 40) -> list[dict]:
    out, page = [], 0
    while page < max_pages:
        d = get(f"{API}/{path}", params={**params, "page": page, "size": 2000}) or {}
        res.requests += 1
        out.extend(d.get(key) or [])
        info = d.get("page") or {}
        page += 1
        if page >= int(info.get("totalPages") or 0):
            break
    return out


def to_offer(ev: dict, info: dict, providers: dict[str, str], school_type: str, today: dt.date) -> Offer | None:
    e, i = ev.get("content") or {}, info.get("content") or {}
    if ev.get("status") != "ACTIVE" or not e or not i or e.get("isCancelled"):
        return None
    title = strip_html(_s(i.get("title")) or _s(e.get("title")))
    if not title:
        return None
    iso = today.isoformat()
    ext = next((x for x in e.get("extensions") or [] if x.get("type") == "UHEventExtension"), {})
    app = e.get("application") or {}
    deadline = (ext.get("applicationDetails") or {}).get("closeDate") or app.get("last") or ""
    start = (e.get("execution") or {}).get("start") or ""
    if deadline and deadline < iso and not (start and start > iso and school_type != "HS"):
        return None                                   # applications closed
    if not deadline and start and start < iso and school_type != "AUB":
        return None                                   # already started
    deadline = deadline if deadline >= iso else ""
    credits_obj = i.get("credits") or {}
    system = ((credits_obj.get("system") or {}).get("code") or "").lower()
    credits = credits_obj.get("credits") if system == "hp" else None    # högskolepoäng = ECTS
    duration = f"{credits_obj['credits']:g} YH credits" if system == "yh" and credits_obj.get("credits") else ""
    level, kind = "", KIND.get(school_type, "course")
    tags = []
    if school_type == "HS":
        lv = {x.get("code") for x in i.get("educationLevels") or []}
        degrees = " ".join(_s(d) for d in i.get("degrees") or []).lower()
        if (i.get("configuration") or {}).get("code") == "program" and (credits or 0) >= 60:
            kind = "degree"
            level = ("master" if "avancerad" in lv or "master" in degrees or "magister" in degrees else "bachelor")
        else:
            kind = "course"
        fee = ext.get("tuitionFee") or {}
        cost, note = (("free_eu", f"Tuition for students from outside the EU/EEA (about {fee['total']:,} SEK)")
                      if fee.get("value") and fee.get("total") else
                      ("free_eu", "Tuition for students from outside the EU/EEA") if fee.get("value") else ("free", ""))
        online = bool(ext.get("itdistance"))
    elif school_type == "YH":
        cost, note = "free", "No tuition; Swedish student aid (CSN) may apply"
        online = "distance" in e
        tags.append("higher_vocational")
    elif school_type == "AUB":
        cost, note = "funded", "Labour market training: free for jobseekers, places are given by Arbetsförmedlingen"
        online = "distance" in e
        tags.append("unemployed")
    else:
        cost, note = "free", "Folk high school: no tuition, costs for materials or board may apply"
        online = "distance" in e
        tags.append("folk_high_school")
    pace = (e.get("paceOfStudy") or {}).get("percentage")
    if pace and pace < 100:
        tags.append("part_time")
        duration = (duration + ", " if duration else "") + f"{pace}% pace"
    if ((e.get("timeOfStudy") or {}).get("code") or "") in ("kvall", "kväll", "helg"):
        tags.append("evening")
    town = next((loc.get("town") or _s(loc.get("studyLocation")) for loc in e.get("locations") or []
                 if loc.get("town") or loc.get("studyLocation")), "")
    if town.lower() in ("ortsoberoende", "distans"):     # "location-independent": a distance course
        town, online = "", True
    town = town.title() if town.isupper() else town
    prov = [providers.get(p, "") for p in e.get("providers") or []]
    url = _s(e.get("url"), "eng", "swe") or _s(i.get("url"), "eng", "swe") or _s(app.get("url"))
    if not url:
        return None
    status = "open" if school_type == "AUB" else "scheduled"   # AUB: continuous admission via Arbetsförmedlingen
    return Offer(
        source="sweden", source_id=ev.get("id") or e.get("identifier", ""), title=title, url=url,
        provider=next((p for p in prov if p), ""), country="Sweden", city=town, kind=kind, level=level,
        cost=cost, cost_note=note, languages=[LANG.get(x, x[:2]) for x in e.get("languageOfInstructions") or []] or ["sv"],
        online=online, credits=credits, duration=duration, starts=start if start >= iso else "", deadline=deadline,
        status=status, tags=tags, summary=clip(strip_html(_s(i.get("description"))), 260), group=school_type,
    )


def fetch(cfg: dict, today: dt.date | None = None) -> SourceResult:
    res = SourceResult("sweden")
    today = today or dt.date.today()
    types = [t for t in cfg.get("school_types", ["HS", "YH", "AUB", "FHS"])]
    since = (today - dt.timedelta(days=int(cfg.get("hs_days", 60)))).isoformat() + "T00:00:00"
    counts = {}
    try:
        providers = {p["id"]: _s((p.get("content") or {}).get("name"))
                     for p in _all("educationProviders", {}, res, "educationProviders") if p.get("content")}
        for st in types:
            params = {"schoolType": st}
            if st not in FULL_TYPES:
                params["updatedSince"] = since
            events = _all("educationEvents", params, res, "educationEvents")
            infos = {x["id"]: x for x in _all("educationInfos", params, res, "educationInfos")}
            n = 0
            for ev in events:
                info = infos.get((ev.get("content") or {}).get("education") or "")
                o = to_offer(ev, info or {}, providers, st, today) if info else None
                if o:
                    res.offers.append(o)
                    n += 1
            counts[st] = f"{n} of {len(events)}"
    except FetchError as e:
        if not res.offers:
            res.ok, res.error = False, str(e)[:200]
            return res
        res.detail = f"stopped early: {e}; "
    names = {"HS": "university", "YH": "higher vocational", "AUB": "labour market training", "FHS": "folk high school"}
    res.detail += "; ".join(f"{names.get(k, k)} {v} runs still open" for k, v in counts.items())
    return res
