"""A 0-100 score for how good an opportunity an offer is for someone building a career, with the reasons."""
from __future__ import annotations

import datetime as dt

from .models import COSTS, Offer

COST_VALUE = {"free": 1.0, "funded": 1.0, "free_eu": 0.85, "audit": 0.75, "varies": 0.6, "unknown": 0.45, "paid": 0.3}
TAG_REASON = {
    "jotpa": "Jotpa-funded", "unemployed": "Labour market training", "continuing": "Continuing education",
    "micro": "Micro-credential", "open_university": "Open university (no entry requirements)",
    "evening": "Evening or weekend teaching", "professional_certificate": "Professional certificate",
    "folk_high_school": "Folk high school / adult education centre",
    "higher_vocational": "Higher vocational education", "part_time": "Part-time",
}


def credential(o: Offer) -> tuple[float, str]:
    if o.kind == "degree":
        return 1.0, f"{o.level.replace('+', ' and ').capitalize() or 'Degree'} degree" if o.level else "Degree"
    if o.kind == "vocational":
        return 0.9, "Vocational qualification"
    if o.kind == "certification":
        return 0.75, "Certification"
    if o.kind == "training":
        big = (o.credits or 0) >= 30
        return (0.8 if big else 0.7), (f"{o.credits:g} ECTS programme" if o.credits else "Professional training")
    if o.credits:
        return 0.45 + min(o.credits, 30) / 30 * 0.3, f"{o.credits:g} ECTS credits"
    if "certificate" in o.tags:
        return 0.45, "Certificate on completion"
    if o.kind == "prep":
        return 0.45, ""
    return (0.4 if o.kind == "course" else 0.35), ""


def timing(o: Offer, today: dt.date) -> tuple[float, str]:
    if o.deadline:
        try:
            d = dt.date.fromisoformat(o.deadline)
            days, when = (d - today).days, f"Apply by {d.day} {d.strftime('%b %Y')}"
            return (1.0 if days <= 90 else 0.8 if days <= 180 else 0.6), when
        except ValueError:
            pass
    if o.status == "open":
        return 1.0, "Application open now"
    if o.status == "anytime":
        return 0.9, "Start any time"
    if o.status == "upcoming":
        return 0.75, "Application opens within 30 days"
    if o.starts and len(o.starts) >= 7:
        try:
            start = dt.date.fromisoformat(o.starts if len(o.starts) == 10 else o.starts + "-01")
            days = (start - today).days
            if 0 <= days <= 120:
                return 0.75, f"Starts {start.day} {start.strftime('%b %Y')}"
        except ValueError:
            pass
    return 0.5, ""


def flexibility(o: Offer) -> tuple[float, str]:
    if o.online and o.self_paced:
        return 1.0, "Online, at your own pace"
    if o.online:
        return 0.95, "Online"
    if "evening" in o.tags:
        return 0.85, ""
    if "part_time" in o.tags:
        return 0.8, ""
    if "partly_online" in o.tags:
        return 0.7, "Partly online"
    return 0.4, ""


def score(o: Offer, cfg: dict, today: dt.date) -> None:
    sc = cfg.get("scoring", {})
    c, c_why = credential(o)
    k = COST_VALUE.get(o.cost, 0.45)
    t, t_why = timing(o, today)
    f, f_why = flexibility(o)
    s = 100 * (sc.get("credential", 0.28) * c + sc.get("cost", 0.30) * k + sc.get("field", 0.22) * o.topic_weight
               + sc.get("timing", 0.12) * t + sc.get("flexibility", 0.08) * f)
    reasons = []
    if o.cost in ("free", "funded", "free_eu", "audit"):
        reasons.append(COSTS[o.cost])
    several = "several_versions" in o.tags      # an Opintopolku programme run by several schools
    reasons += [TAG_REASON[x] + (" (some versions)" if several and x in ("jotpa", "unemployed", "evening") else "")
                for x in o.tags if x in TAG_REASON]
    reasons += [x for x in (c_why, t_why, f_why) if x]
    if o.topic != "Other":
        reasons.append(f"Field: {o.topic}")
    if o.closing_soon and o.deadline:
        days = (dt.date.fromisoformat(o.deadline) - today).days
        reasons.insert(0, "Deadline today" if days == 0 else f"Deadline in {days} day{'s' if days != 1 else ''}")
        s += sc.get("closing_bonus", 4)
    if o.is_new:
        reasons.append("New this week")
        s += sc.get("new_bonus", 4)
    o.score = max(0.0, min(100.0, s))
    o.reasons = list(dict.fromkeys(reasons))
