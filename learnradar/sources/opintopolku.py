"""Opintopolku / Studyinfo.fi: every Finnish education offer, from the public konfo-backend API.

Two kinds of request:

* the listing (external/search/toteutukset-koulutuksittain) gives each offer's name, description, type,
  credits, providers and towns, for offers whose application is open now. It ignores the "opens within 30
  days" filter (and returns every programme), so for any window where its count disagrees with the search
  endpoint's, the search endpoint's hits are used instead (no towns, one provider name and a count);
* tag queries (search/koulutukset with one filter each) give the offer ids that are, for example, free,
  Jotpa-funded, labour market training, taught in English or online. The listing endpoint ignores some of
  these filters, so tags always use the search endpoint, and a tag whose filter comes back unapplied (as many
  results as the unfiltered listing) is dropped and reported rather than applied to everything.

About 75 requests a run (pages of 200), with a pause between each (delay_seconds in config.yaml).
"""
from __future__ import annotations

import re
import time

from ..http import FetchError, get
from ..models import Offer
from ..text import clip, pick_lang, strip_html
from . import SourceResult

BASE = "https://opintopolku.fi/konfo-backend"
LISTING = BASE + "/external/search/toteutukset-koulutuksittain"
SEARCH = BASE + "/search/koulutukset"

WINDOWS = {
    "open": {"hakukaynnissa": "true"},           # application open now
    "upcoming": {"hakualkaapaivissa": "30"},     # application opens within 30 days
}

TAGS = {
    "jotpa": {"jotpa": "true"},                                   # free or low-cost, funded by Jotpa
    "unemployed": {"tyovoimakoulutus": "true"},                   # labour market training for jobseekers
    "continuing": {"taydennyskoulutus": "true"},                  # continuing education for professionals
    "micro": {"pieniosaamiskokonaisuus": "true"},                 # micro-credential
    "open_university": {"koulutustyyppi": "yo-opintojakso-avoin,yo-opintokokonaisuus-avoin,"
                                          "amk-opintojakso-avoin,amk-opintokokonaisuus-avoin"},
    "fee_free": {"maksullisuustyyppi": "maksuton"},
    "fee_paid": {"maksullisuustyyppi": "maksullinen"},
    "fee_tuition": {"maksullisuustyyppi": "lukuvuosimaksu"},      # tuition fee (non-EU/EEA degree students)
    "lang_fi": {"opetuskieli": "oppilaitoksenopetuskieli_1,oppilaitoksenopetuskieli_3"},
    "lang_en": {"opetuskieli": "oppilaitoksenopetuskieli_4"},
    "lang_sv": {"opetuskieli": "oppilaitoksenopetuskieli_2,oppilaitoksenopetuskieli_3"},
    "online": {"opetustapa": "opetuspaikkakk_3,opetuspaikkakk_2"},  # online or distance teaching
    "evening": {"opetusaika": "opetusaikakk_2,opetusaikakk_3"},     # evening or weekend teaching
}

KIND_BY_TYPE = {
    "amk": "degree", "yo": "degree",
    "kk-opintojakso": "course", "kk-opintokokonaisuus": "course",
    "erikoistumiskoulutus": "training", "amk-erikoistumiskoulutus": "training", "yo-erikoistumiskoulutus": "training",
    "amm": "vocational", "muu-amm-tutkinto": "vocational", "amm-osaamisala": "vocational",
    "amm-tutkinnon-osa": "training", "amm-muu": "training", "muu": "training",
    "ope-pedag-opinnot": "training", "amm-ope-erityisope-ja-opo": "training",
    "vapaa-sivistystyo-muu": "course", "vapaa-sivistystyo-opistovuosi": "course",
    "vapaa-sivistystyo-osaamismerkki": "course",
    "aikuisten-perusopetus": "prep", "tuva": "prep", "tuva-normal": "prep", "telma": "prep",
}

_MASTER = re.compile(r"\b(master|maisteri|ylempi|ylemp|magister|mba|msc|m\.sc)", re.I)
_BACHELOR = re.compile(r"\b(bachelor|kandidaat|\(amk\)|\(yh\)|bsc|b\.sc|insinööri \(amk\)|tradenom)", re.I)
_DOCTOR = re.compile(r"\b(doctor|tohtori|phd|lisensiaat)", re.I)


def _pages(url: str, params: dict, size: int, delay: float, res: SourceResult, max_pages: int = 40):
    """All hits of one query. Returns (total, hits).

    The API caps a page at 200 hits without saying so, so paging goes by what actually came back.
    """
    hits, total, page = [], 0, 1
    while page <= max_pages:
        if res.requests:
            time.sleep(delay)
        d = get(url, params={**params, "lng": "en", "page": page, "size": min(size, 200)})
        res.requests += 1
        batch = (d or {}).get("hits") or []
        total = int((d or {}).get("total") or 0)
        hits.extend(batch)
        if not batch or len(hits) >= total:
            break
        page += 1
    return total, hits


def _level(hit: dict, title: str) -> str:
    names = " ".join(pick_lang(t.get("nimi"), "en", "fi") for t in (hit.get("tutkintonimikkeet") or []))
    names += " " + " ".join(pick_lang(k.get("nimi"), "en", "fi") for k in (hit.get("koulutukset") or []))
    names += " " + title
    if _DOCTOR.search(names):
        return "doctorate"
    has_m, has_b = bool(_MASTER.search(names)), bool(_BACHELOR.search(names))
    if has_m and has_b:
        return "bachelor+master"
    return "master" if has_m else "bachelor" if has_b else ""


def _credits(hit: dict) -> tuple[float | None, str]:
    unit = hit.get("opintojenLaajuusyksikko") or {}
    n = hit.get("opintojenLaajuusNumero")
    lo, hi = hit.get("opintojenLaajuusNumeroMin"), hit.get("opintojenLaajuusNumeroMax")
    if n is None:
        n = hi if hi is not None else lo
    if n is None:
        return None, ""
    uname = pick_lang(unit.get("nimi"), "en", "fi")
    span = f"{lo:g}-{hi:g}" if lo is not None and hi is not None and lo != hi else f"{n:g}"
    if str(unit.get("koodiUri", "")).startswith("opintojenlaajuusyksikko_2"):
        return float(n), f"{span} ECTS"
    return None, f"{span} {uname}".strip()


def _cost(tags: set[str], options: int = 1, degree: bool = False, langs: list[str] | None = None) -> tuple[str, str]:
    """Cost from the fee and funding tags.

    Opintopolku lists one entry per programme, which several schools may run (`options`). The tags say that
    at least one of those versions matched the filter, so with several versions "Jotpa-funded" means "one of
    the versions is", and the note says so instead of claiming it for all.
    """
    free, paid, tuition = "fee_free" in tags, "fee_paid" in tags, "fee_tuition" in tags
    some = options > 1
    if "unemployed" in tags and not some:
        return "funded", "Labour market training: free for jobseekers, apply through employment services"
    if "jotpa" in tags and not some:
        return "funded", "Funded by Jotpa for working-age adults (free or low cost)"
    if free and not (paid or tuition):
        return "free", ""
    if free:
        return "varies", "Free and paid options"
    if tuition and not paid:
        return "free_eu", "Tuition fee for students from outside the EU/EEA"
    if paid:
        return ("varies", "Some versions charge a fee") if some else ("paid", "Fee charged (see the course page)")
    if degree:
        # Finnish degree education is free by law, except English-taught programmes for non-EU/EEA students.
        langs = langs or []
        if langs == ["en"]:
            return "free_eu", "Tuition fee for students from outside the EU/EEA"
        return "free", "English-taught versions charge tuition to non-EU/EEA students" if "en" in langs else ""
    return "unknown", ""


OPTION_LABEL = {"jotpa": "Jotpa-funded", "unemployed": "labour market training for jobseekers",
                "lang_en": "taught in English", "online": "online", "evening": "evening or weekend"}


def to_offer(hit: dict, window: str, tags: set[str]) -> Offer | None:
    oid = hit.get("oid")
    names = hit.get("nimi") or {}
    title = strip_html(pick_lang(names, "en", "fi", "sv"))
    if not oid or not title:
        return None
    has_en = bool((names.get("en") or "").strip())
    typ = hit.get("koulutustyyppi") or ""
    kind = KIND_BY_TYPE.get(typ, "course")
    tot = hit.get("toteutukset") or []
    providers, towns = [], {}
    tarj = hit.get("toteutustenTarjoajat") or {}      # search-endpoint hits: a count and one name
    if not tot and tarj.get("count"):
        tot = [{"oppilaitosNimi": tarj.get("nimi")}] + [{} for _ in range(int(tarj["count"]) - 1)]
    for t in tot:
        p = pick_lang(t.get("oppilaitosNimi"), "en", "fi")
        if p and p not in providers:
            providers.append(p)
        for k in t.get("kunnat") or []:
            n = pick_lang(k.get("nimi"), "fi", "sv", "en")
            if n:
                towns[n] = towns.get(n, 0) + 1
    town_list = sorted(towns, key=lambda x: -towns[x])
    city = ", ".join(town_list[:3]) + (f" +{len(town_list) - 3}" if len(town_list) > 3 else "")
    n_prov = max(len(providers), int(tarj.get("count") or 0))
    provider = providers[0] + (f" + {n_prov - 1} more" if n_prov > 1 else "") if providers else ""
    level = _level(hit, title) if kind == "degree" else ""
    if kind == "degree" and not level and not hit.get("tutkintonimikkeet"):
        kind = "training"
    credits, duration = _credits(hit)
    langs = [code for code in ("fi", "en", "sv") if f"lang_{code}" in tags] or ["fi"]
    options = max(len(tot), 1)
    cost, note = _cost(tags, options, kind == "degree", langs)
    if options > 1:
        some = [OPTION_LABEL[t] for t in OPTION_LABEL if t in tags and not (t == "lang_en" and langs == ["en"])]
        if some:
            note = (note + ". " if note else "") + f"{options} versions; some are " + ", ".join(some)
    out_tags = sorted(t for t in tags if not t.startswith(("fee_", "lang_")) and t != "online")
    if typ.startswith("vapaa-sivistystyo"):
        out_tags.append("folk_high_school")
    if options > 1:
        out_tags.append("several_versions")
    summary = clip(strip_html(pick_lang(hit.get("kuvaus"), "en", "fi", "sv")), 260)
    return Offer(
        source="opintopolku", source_id=oid, title=title,
        url=f"https://opintopolku.fi/konfo/{'en' if has_en else 'fi'}/koulutus/{oid}",
        provider=provider, country="Finland", city=city, kind=kind, level=level, cost=cost, cost_note=note,
        languages=langs, online="online" in tags, credits=credits, duration=duration, status=window,
        tags=out_tags, subjects=[s for s in (hit.get("luokittelutermit") or [])][:10], summary=summary,
    )


def fetch(cfg: dict) -> SourceResult:
    res = SourceResult("opintopolku")
    size = int(cfg.get("page_size", 200))
    delay = float(cfg.get("delay_seconds", 3))
    skip = set(cfg.get("skip_types", []))
    base: dict[str, tuple[dict, str]] = {}
    tags: dict[str, set[str]] = {}
    dropped, counts, notes = [], {}, []
    try:
        for window in cfg.get("windows", ["open", "upcoming"]):
            wparams = WINDOWS[window]
            # The search endpoint applies every filter; the listing ignores some (it returns all ~7,500
            # programmes for "opens within 30 days"). Compare their counts and use the richer listing only
            # when it agrees.
            total = _total(SEARCH, wparams, res, delay)
            l_total = _total(LISTING, wparams, res, delay)
            endpoint = LISTING if abs(l_total - total) <= max(5, total // 50) else SEARCH
            if endpoint is SEARCH:
                notes.append(f"'{window}' read from the search endpoint")
            _, hits = _pages(endpoint, wparams, size, delay, res)
            for h in hits:
                if h.get("oid") and h["oid"] not in base:
                    base[h["oid"]] = (h, window)
            for tag, tparams in TAGS.items():
                t_total, t_hits = _pages(SEARCH, {**wparams, **tparams}, size, delay, res)
                if total > 50 and t_total >= total:
                    dropped.append(f"{tag} ({window})")    # the filter was not applied
                    continue
                counts[tag] = counts.get(tag, 0) + t_total
                for h in t_hits:
                    if h.get("oid"):
                        tags.setdefault(h["oid"], set()).add(tag)
    except FetchError as e:
        if not base:
            res.ok, res.error = False, str(e)[:200]
            return res
        res.detail = f"stopped early: {e}; "
    skipped = 0
    for oid, (h, window) in base.items():
        if (h.get("koulutustyyppi") or "") in skip:
            skipped += 1
            continue
        o = to_offer(h, window, tags.get(oid, set()))
        if o:
            res.offers.append(o)
    res.detail += (f"{len(base)} offers with application open or opening soon, {skipped} school-age offers "
                   f"skipped, {res.requests} requests; tagged: "
                   + ", ".join(f"{k} {v}" for k, v in counts.items()))
    if notes:
        res.detail += "; " + ", ".join(notes)
    if dropped:
        res.detail += "; filters ignored by the API, tag not used: " + ", ".join(dropped)
    return res


def _total(url: str, params: dict, res: SourceResult, delay: float) -> int:
    if res.requests:
        time.sleep(delay)
    d = get(url, params={**params, "lng": "en", "page": 1, "size": 1})
    res.requests += 1
    return int((d or {}).get("total") or 0)
