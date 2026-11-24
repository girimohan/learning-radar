"""Norway: Utdanning.no's public API (api.utdanning.no).

* studievelgeren: about 1,400 bachelor's, master's and one-year programmes in the national admission
  (Samordna opptak), 100 per page.
* fagskolevelgeren: about 700 higher vocational college (fagskole) programmes, one request.

Neither lists deadlines. Most of these programmes are applied for through Samordna opptak in the spring.
"""
from __future__ import annotations

import re

from ..http import FetchError, get
from ..models import Offer
from ..text import strip_html
from . import SourceResult

API = "https://api.utdanning.no"
SITE = "https://utdanning.no"
# State universities and university colleges: no tuition for EU/EEA/Swiss citizens (a semester fee applies);
# since 2023 students from elsewhere pay tuition. Private institutions set their own fees.
PUBLIC = re.compile(r"^(universitetet|uit |nord universitet|nmbu|ntnu|norges |oslomet|høgskulen i volda|"
                    r"høgskolen i (østfold|molde|innlandet)|høgskulen på vestlandet|politihøgskolen|"
                    r"arkitektur- og designhøgskolen|kunsthøgskolen i oslo|samisk høgskole|sámi allaskuvla|"
                    r"forsvarets høgskole|norwegian)", re.I)
LEVEL = {"bachelor": "bachelor", "master": "master", "integrert master": "master", "ph.d.": "doctorate"}


def _places(x: dict) -> str:
    return ", ".join([s for s in x.get("sted") or [] if s and s.lower() != "ukjent"][:2])


def _cost(org: str) -> tuple[str, str]:
    if PUBLIC.search(org or ""):
        return "free_eu", "No tuition for EU/EEA/Swiss citizens (semester fee applies); others pay tuition"
    return "unknown", "Private institution: check for tuition fees"


def programme_offer(x: dict) -> Offer | None:
    title = strip_html((x.get("uh_tilbud_title") or [x.get("title")])[0] or "")
    if not title:
        return None
    rel = (x.get("uh_tilbud_url") or [""])[0]
    url = SITE + rel if rel else (x.get("hjemmeside") or "")
    if not url:
        return None
    niva = (x.get("studieniva") or "").lower()
    level = LEVEL.get(niva, "")
    kind = "degree" if level else "training"
    credits = 60.0 if niva.startswith("årsstudium") else None
    cost, note = _cost(x.get("organisasjon", ""))
    tags = ["part_time"] if x.get("deltid") else []
    if x.get("samlingsbasert"):
        tags.append("evening")               # gathered sessions: designed to fit around a job
    subjects = [s.split("/")[-1] for s in x.get("interesse") or []]
    sid = (x.get("uh_tilbud_id") or [x.get("so_kode") or title])[0]
    return Offer(
        source="norway", source_id=str(sid), title=title, url=url, provider=x.get("organisasjon", ""),
        country="Norway", city=_places(x), kind=kind, level=level, cost=cost,
        cost_note=note, languages=["no"], online=bool(x.get("nettbasert")), credits=credits,
        duration="One-year programme (60 ECTS)" if credits else "", status="scheduled", tags=tags,
        subjects=subjects[:10],
        summary=f"{x.get('studieniva', '')} programme. Apply through Samordna opptak "
                f"({x.get('studieplasser') or '?'} places).".strip(),
    )


def fagskole_offer(x: dict) -> Offer | None:
    title = strip_html(x.get("navn") or "")
    if not title or not x.get("lenke"):
        return None
    form = " ".join((x.get("studieform") or []) + (x.get("undervisningsform") or []) + (x.get("studietempo") or [])).lower()
    tags = ["higher_vocational"]
    if "deltid" in form:
        tags.append("part_time")
    if "samling" in form:
        tags.append("evening")
    return Offer(
        source="norway", source_id="fagskole:" + x["lenke"].rstrip("/").split("/")[-1], title=title,
        url=SITE + x["lenke"], provider=x.get("fagskole", ""), country="Norway",
        city=_places(x), kind="vocational", cost="unknown",
        cost_note="Public vocational colleges are usually free; private ones charge fees", languages=["no"],
        online="nett" in form, duration=x.get("studietype", ""), status="scheduled", tags=tags,
        subjects=(x.get("fagfelt") or []) + (x.get("interesse_level_2") or [])[:6],
        summary=f"{x.get('studietype', 'Fagskole')} in {', '.join(x.get('fagfelt') or []) or 'a vocational field'}.",
    )


def fetch(cfg: dict) -> SourceResult:
    res = SourceResult("norway")
    progs, fag = [], []
    try:
        page, last = 1, 1
        while page <= last and page <= 40:
            d = get(f"{API}/studievelgeren/result", params={"per_page": 100, "page": page}) or {}
            res.requests += 1
            progs.extend(d.get("items") or [])
            last = -(-int(d.get("total_items") or 0) // 100)
            page += 1
        if cfg.get("fagskole", True):
            fag = get(f"{API}/fagskolevelgeren/fagskole") or []
            res.requests += 1
    except FetchError as e:
        if not progs:
            res.ok, res.error = False, str(e)[:200]
            return res
        res.detail = f"stopped early: {e}; "
    seen = set()
    for o in [programme_offer(x) for x in progs] + [fagskole_offer(x) for x in fag]:
        if o and o.source_id not in seen:
            seen.add(o.source_id)
            res.offers.append(o)
    res.detail += f"{len(progs)} higher education programmes, {len(fag)} vocational college programmes"
    return res
