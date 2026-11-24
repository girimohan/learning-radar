"""Coursera: Specialisations and Professional Certificates (and optionally single courses), public catalog API."""
from __future__ import annotations

from ..http import FetchError, get
from ..models import Offer
from ..text import clip, strip_html
from . import SourceResult

API = "https://api.coursera.org/api"
LEVELS = {"BEGINNER": "beginner", "INTERMEDIATE": "intermediate", "ADVANCED": "advanced", "MIXED": ""}
COST_NOTE = "Certificate needs a Coursera subscription (free trial); some courses can be audited free"


def _all(path: str, fields: str, res: SourceResult, page: int = 1000, max_pages: int = 40) -> list[dict]:
    out, start = [], 0
    for _ in range(max_pages):
        d = get(f"{API}/{path}", params={"limit": page, "start": start, "fields": fields})
        res.requests += 1
        els = (d or {}).get("elements") or []
        out.extend(els)
        nxt = ((d or {}).get("paging") or {}).get("next")
        if not els or not nxt:
            break
        start = int(nxt)
    return out


def _partners(ids: list[str], partners: dict[str, str]) -> str:
    names = [partners[i] for i in ids if i in partners]
    return names[0] + (f" + {len(names) - 1} more" if len(names) > 1 else "") if names else ""


def spec_offer(s: dict, partners: dict[str, str], languages: set[str]) -> Offer | None:
    langs = s.get("primaryLanguages") or ["en"]
    if languages and not set(langs) & languages:
        return None
    if not s.get("slug") or not s.get("name"):
        return None
    pro = "ProfessionalCertificate" in (s.get("productVariant") or "")
    md = s.get("metadata") or {}
    months = md.get("monthsToCompleteOverride")
    n = len(s.get("courseIds") or [])
    duration = ", ".join(x for x in [f"{n} courses" if n else "", f"about {months} months" if months else ""] if x)
    path = "professional-certificates" if pro else "specializations"
    return Offer(
        source="coursera", source_id=s.get("id") or s["slug"], title=strip_html(s["name"]),
        url=f"https://www.coursera.org/{path}/{s['slug']}", provider=_partners(s.get("partnerIds") or [], partners),
        kind="training" if pro else "online", level=LEVELS.get(md.get("level") or "", ""), cost="varies",
        cost_note=COST_NOTE, languages=list(langs), online=True, self_paced=True, duration=duration,
        status="anytime", tags=["certificate"] + (["professional_certificate"] if pro else []),
        summary=clip(strip_html(s.get("tagline") or s.get("description") or ""), 260),
    )


def course_offer(c: dict, partners: dict[str, str], languages: set[str]) -> Offer | None:
    langs = c.get("primaryLanguages") or ["en"]
    if languages and not set(langs) & languages:
        return None
    if not c.get("slug") or not c.get("name"):
        return None
    subj = [d.get("subdomainId", "").replace("-", " ") for d in (c.get("domainTypes") or [])]
    return Offer(
        source="coursera", source_id=c.get("id") or c["slug"], title=strip_html(c["name"]),
        url=f"https://www.coursera.org/learn/{c['slug']}", provider=_partners(c.get("partnerIds") or [], partners),
        kind="online", cost="audit" if c.get("certificates") else "free",
        cost_note="Free to audit; the certificate is paid" if c.get("certificates") else "",
        languages=list(langs), online=True, self_paced=True, duration=c.get("workload") or "", status="anytime",
        tags=["certificate"] if c.get("certificates") else [], subjects=[s for s in subj if s],
        summary=clip(strip_html(c.get("description") or ""), 260),
    )


def fetch(cfg: dict) -> SourceResult:
    res = SourceResult("coursera")
    languages = set(cfg.get("languages", ["en", "fi", "sv", "de"]))
    try:
        partners = {p["id"]: p.get("name", "") for p in _all("partners.v1", "name", res)}
        specs = _all("onDemandSpecializations.v1", "partnerIds,tagline,description,productVariant,metadata,"
                     "courseIds,primaryLanguages", res)
        courses = _all("courses.v1", "description,workload,primaryLanguages,partnerIds,domainTypes,certificates",
                       res) if cfg.get("include_courses") else []
        # The partner listing leaves some out; look the rest up by id, 100 at a time.
        missing = sorted({p for x in specs + courses for p in (x.get("partnerIds") or []) if p not in partners})
        for i in range(0, len(missing), 100):
            d = get(f"{API}/partners.v1", params={"ids": ",".join(missing[i:i + 100]), "fields": "name"}) or {}
            res.requests += 1
            partners.update({p["id"]: p.get("name", "") for p in d.get("elements") or []})
    except FetchError as e:
        res.ok, res.error = False, str(e)[:200]
        return res
    for s in specs:
        o = spec_offer(s, partners, languages)
        if o:
            res.offers.append(o)
    n_spec = len(res.offers)
    for c in courses:
        o = course_offer(c, partners, languages)
        if o:
            res.offers.append(o)
    res.detail = (f"{n_spec} of {len(specs)} specialisations and professional certificates in "
                  f"{', '.join(sorted(languages))}" + (f", {len(res.offers) - n_spec} courses" if courses else ""))
    return res
