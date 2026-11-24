"""Collect -> drop noise and duplicates -> fields and goals -> new / closing soon -> score -> cap -> write."""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
from pathlib import Path

from . import classify, scoring
from .models import COSTS, GOALS, KINDS, Offer
from .sources import SourceResult, coursera, daad, futurelearn, moocfi, mslearn, norway, opintopolku, sweden
from .text import has_keyword, norm_title

SOURCES = {
    "opintopolku": opintopolku.fetch, "sweden": sweden.fetch, "norway": norway.fetch, "daad": daad.fetch,
    "futurelearn": futurelearn.fetch,
    "coursera": coursera.fetch, "mslearn": mslearn.fetch, "moocfi": moocfi.fetch,
}


def collect(cfg: dict, only: set[str] | None = None) -> list[SourceResult]:
    """Runs the enabled sources side by side (Opintopolku is slow on purpose; the others need not wait)."""
    src = cfg.get("sources", {})
    names = [n for n in SOURCES if src.get(n, {}).get("enabled", True) and (only is None or n in only)]

    def run(name: str) -> SourceResult:
        try:
            return SOURCES[name](src.get(name, {}))
        except Exception as e:  # one broken source must not stop the others
            return SourceResult(name, ok=False, error=f"{type(e).__name__}: {e}"[:200])

    with cf.ThreadPoolExecutor(len(names) or 1) as ex:
        return list(ex.map(run, names))


def prefilter(offers: list[Offer], cfg: dict, funnel: dict) -> list[Offer]:
    excl = [k.lower() for k in cfg.get("exclude_title", [])]
    out, ids, titles = [], set(), set()
    for o in offers:
        t = o.title.lower()
        if any((k in t) if not k[-1].isalnum() else has_keyword(t, k) for k in excl):
            funnel["excluded"] += 1
            continue
        key = (norm_title(o.title), norm_title(o.provider), o.source)
        if o.uid in ids or key in titles:
            funnel["duplicates"] += 1
            continue
        ids.add(o.uid)
        titles.add(key)
        out.append(o)
    return out


def mark_history(offers: list[Offer], ledger: dict, today: dt.date, first_run: bool, cfg: dict) -> int:
    """first_seen from the ledger; 'new' = first seen within new_days.

    Nothing is 'new' on the very first run, nor the first time a source appears (a source added later, or one
    that was down until now), since everything it lists would otherwise look new. Ledger entries are
    [first_seen, last_seen, baseline] where baseline=1 means 'was already there when we started looking'.
    """
    day = today.isoformat()
    new_cut = (today - dt.timedelta(days=cfg.get("new_days", 7))).isoformat()
    close_cut = (today + dt.timedelta(days=cfg.get("closing_days", 21))).isoformat()
    known_sources = {k.split(":", 1)[0] for k in ledger}
    new = 0
    for o in offers:
        e = ledger.get(o.uid)
        if e is None:
            baseline = first_run or o.source not in known_sources
            e = ledger[o.uid] = [day, day, 1 if baseline else 0]
        e[1] = day
        o.first_seen = e[0]
        o.is_new = not e[2] and e[0] >= new_cut
        new += o.is_new
        o.closing_soon = bool(o.deadline) and day <= o.deadline <= close_cut
    return new


def prune_ledger(ledger: dict, today: dt.date, keep_days: int = 90) -> None:
    cutoff = (today - dt.timedelta(days=keep_days)).isoformat()
    for k in [k for k, e in ledger.items() if e[1] < cutoff]:
        del ledger[k]


def process(offers: list[Offer], cfg: dict, today: dt.date, ledger: dict, first_run: bool) -> tuple[list[Offer], dict]:
    funnel = {"collected": len(offers), "excluded": 0, "duplicates": 0}
    xs = prefilter(offers, cfg, funnel)
    topics = cfg.get("topics", [])
    for o in xs:
        classify.match_topics(o, topics, cfg.get("untopical_weight", 0.5))
        o.goals = classify.goals(o)
    mark_history(xs, ledger, today, first_run, cfg)
    for o in xs:
        scoring.score(o, cfg, today)
    min_score = cfg.get("min_score", 0)
    kept = [o for o in xs if o.score >= min_score]
    funnel["below_score"] = len(xs) - len(kept)
    kept.sort(key=lambda o: (-o.score, o.title.lower()))
    caps = {n: c.get("max_items") for n, c in cfg.get("sources", {}).items()}
    group_caps = {(n, g): v for n, c in cfg.get("sources", {}).items() for g, v in (c.get("max_per_group") or {}).items()}
    per, capped = {}, []
    for o in kept:
        gk = (o.source, o.group)
        if group_caps.get(gk) and per.get(gk, 0) >= group_caps[gk]:
            continue
        if caps.get(o.source) and per.get(o.source, 0) >= caps[o.source]:
            continue
        per[o.source] = per.get(o.source, 0) + 1
        per[gk] = per.get(gk, 0) + 1
        capped.append(o)
    capped = capped[: cfg.get("max_items", 7000)]
    funnel["capped"] = len(kept) - len(capped)
    funnel["shown"] = len(capped)
    return capped, funnel


def run(cfg: dict, out_path: Path, today: dt.date | None = None, only: set[str] | None = None,
        ledger_path: Path | None = None, results: list[SourceResult] | None = None,
        now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    today = today or now.date()
    ledger_path = ledger_path or out_path.parent.parent / "data" / "seen.json"
    results = results if results is not None else collect(cfg, only)
    if results and not any(r.ok and r.offers for r in results):
        raise RuntimeError("no source returned anything: " + "; ".join(f"{r.name}: {r.error or r.detail}" for r in results))
    ledger: dict = {}
    if ledger_path.exists():
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except ValueError:
            ledger = {}
    first_run = not ledger
    offers, funnel = process([o for r in results for o in r.offers], cfg, today, ledger, first_run)
    # A source that failed today keeps its ledger entries (they are only pruned after 90 days unseen).
    prune_ledger(ledger, today)

    shown_by = {}
    for o in offers:
        shown_by[o.source] = shown_by.get(o.source, 0) + 1
    payload = {
        "generated_at": now.isoformat(timespec="seconds"),
        "date": today.isoformat(),
        "first_run": first_run,
        "new_this_week": sum(o.is_new for o in offers),
        "closing_soon": sum(o.closing_soon for o in offers),
        "funnel": funnel,
        "sources": [{"name": r.name, "ok": r.ok, "fetched": len(r.offers), "shown": shown_by.get(r.name, 0),
                     "requests": r.requests, "detail": r.detail, "error": r.error} for r in results],
        "topics": [t["name"] for t in cfg.get("topics", [])] + ["Other"],
        "kinds": KINDS, "costs": COSTS, "goals": GOALS,
        "offers": [o.to_public() for o in offers],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    return payload
