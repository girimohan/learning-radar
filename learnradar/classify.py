"""Which fields an offer belongs to, and which learner goals it serves."""
from __future__ import annotations

from .models import Offer
from .text import has_keyword


def match_topics(o: Offer, topics: list[dict], untopical_weight: float = 0.5) -> None:
    """Sets o.topics (best first), o.topic and o.topic_weight.

    A keyword in the title or the provider's subject labels is enough. The description alone needs two
    different keywords of the same field, so one passing mention ("...used in healthcare") does not count.
    """
    title, subj, summ = o.title.lower(), " ".join(o.subjects).lower(), o.summary.lower()
    found = []
    for i, t in enumerate(topics):
        place, hits = None, set()
        for k in t.get("any", []):
            if has_keyword(title, k):
                place = 0
                break
            if place is None and has_keyword(subj, k):
                place = 1
            if has_keyword(summ, k):
                hits.add(k.rstrip("*"))
        if place is None and len(hits) >= 2:
            place = 2
        if place is not None:
            w = float(t.get("weight", 1.0)) * (0.9 if place == 2 else 1.0)
            found.append((place, -w, i, t["name"], w))
    found.sort()
    o.topics = [f[3] for f in found]
    if found:
        o.topic, o.topic_weight = found[0][3], found[0][4]
    else:
        o.topic, o.topic_weight = "Other", float(untopical_weight)


def goals(o: Offer) -> list[str]:
    tags = set(o.tags)
    g = []
    if o.kind == "degree":
        g.append("degree")
    if (o.kind in ("degree", "vocational") or "unemployed" in tags or "professional_certificate" in tags
            or (o.kind == "training" and (o.credits or 0) >= 30)
            or (o.kind == "certification" and o.level in ("beginner", ""))):
        g.append("change")
    if o.kind != "degree" and (o.kind in ("course", "training", "certification")
                               or tags & {"continuing", "jotpa", "micro", "evening"}
                               or (o.kind == "online" and "certificate" in tags)):
        g.append("upskill")
    if ((o.kind in ("online", "course", "prep") and o.cost in ("free", "funded", "audit", "free_eu"))
            or tags & {"open_university", "folk_high_school"}):
        g.append("learn")
    return g or ["learn"]
