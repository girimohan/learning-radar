"""Microsoft Learn: certifications, Applied Skills credentials and learning paths, from the public Catalog API."""
from __future__ import annotations

from ..http import FetchError, get
from ..models import Offer
from ..text import clean_url, clip, strip_html
from . import SourceResult

URL = "https://learn.microsoft.com/api/learn/catalog/"


def _level(levels: list[str] | None) -> str:
    levels = levels or []
    return levels[0] if len(levels) == 1 else ""


def _subjects(x: dict) -> list[str]:
    vals = (x.get("subjects") or []) + (x.get("roles") or []) + (x.get("products") or [])
    return [v.replace("-", " ") for v in vals][:10]


def cert_offer(c: dict) -> Offer | None:
    if not c.get("uid") or not c.get("title") or not c.get("url"):
        return None
    return Offer(
        source="mslearn", source_id=c["uid"], title=strip_html(c["title"]), url=clean_url(c["url"]),
        provider="Microsoft", kind="certification", level=_level(c.get("levels")), cost="paid",
        cost_note="Learning material is free; the exam has a fee", languages=["en"], online=True, self_paced=True,
        status="anytime", tags=["certificate"], subjects=_subjects(c),
        summary=clip(strip_html(c.get("summary") or c.get("subtitle") or ""), 260),
    )


def skill_offer(a: dict) -> Offer | None:
    if not a.get("uid") or not a.get("title") or not a.get("url"):
        return None
    return Offer(
        source="mslearn", source_id=a["uid"], title=strip_html(a["title"]), url=clean_url(a["url"]),
        provider="Microsoft", kind="certification", level=_level(a.get("levels")), cost="free",
        cost_note="Free online assessment", languages=["en"], online=True, self_paced=True, status="anytime",
        tags=["certificate", "micro"], subjects=_subjects(a),
        summary=clip(strip_html(a.get("summary") or ""), 260),
    )


def path_offer(p: dict) -> Offer | None:
    if not p.get("uid") or not p.get("title") or not p.get("url"):
        return None
    mins = p.get("duration_in_minutes") or 0
    duration = f"{mins / 60:.0f} hours" if mins >= 90 else f"{mins} minutes" if mins else ""
    return Offer(
        source="mslearn", source_id=p["uid"], title=strip_html(p["title"]), url=clean_url(p["url"]),
        provider="Microsoft", kind="online", level=_level(p.get("levels")), cost="free", languages=["en"],
        online=True, self_paced=True, duration=duration, status="anytime", subjects=_subjects(p),
        summary=clip(strip_html(p.get("summary") or ""), 260),
    )


def fetch(cfg: dict) -> SourceResult:
    res = SourceResult("mslearn")
    try:
        d = get(URL, params={"locale": "en-us"}) or {}
        res.requests = 1
    except FetchError as e:
        res.ok, res.error = False, str(e)[:200]
        return res
    certs = [o for o in map(cert_offer, d.get("certifications") or []) if o]
    skills = [o for o in map(skill_offer, d.get("appliedSkills") or []) if o]
    paths = sorted(d.get("learningPaths") or [], key=lambda p: -(p.get("popularity") or 0))
    paths = [o for o in map(path_offer, paths[: int(cfg.get("learning_paths", 250))]) if o]
    res.offers = certs + skills + paths
    res.detail = (f"{len(certs)} certifications, {len(skills)} Applied Skills, {len(paths)} most popular of "
                  f"{len(d.get('learningPaths') or [])} learning paths")
    return res
