from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

from . import pipeline, report, site

ROOT = Path(__file__).resolve().parent.parent


def cmd_run(args) -> int:
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    only = set(args.sources.split(",")) if args.sources else None
    try:
        payload = pipeline.run(cfg, Path(args.out), only=only, ledger_path=Path(args.ledger))
    except RuntimeError as e:
        print(e, file=sys.stderr)  # nothing is overwritten when every source is down
        return 1
    docs = Path(args.out).parent
    d = Path(args.digest)
    d.parent.mkdir(parents=True, exist_ok=True)
    d.write_text(report.digest(payload, args.dashboard_url or site.site_url(cfg, docs), cfg), encoding="utf-8")
    pages = site.build(cfg, docs, payload)
    print(f"site: {len(pages)} pages written")

    f = payload["funnel"]
    print(f"collected {f['collected']:,} -> {f['excluded']} excluded, {f['duplicates']} duplicates, "
          f"{f['below_score']:,} below the score cut, {f['capped']:,} over a cap -> {f['shown']:,} shown "
          f"(new this week {payload['new_this_week']}, closing soon {payload['closing_soon']})")
    for s in payload["sources"]:
        print(f"  {s['name']:12} {'ok ' if s['ok'] else 'ERR'} fetched {s['fetched']:>5,} shown {s['shown']:>5,} "
              f"requests {s['requests']:>3}  {s['error'] or s['detail']}")
    for i, o in enumerate(payload["offers"][:10], 1):
        print(f"  {i:>2}. {o['score']:>5.1f}  [{o['source']}] {o['title'][:80]}")
    gh = os.environ.get("GITHUB_OUTPUT")
    if gh:
        with open(gh, "a", encoding="utf-8") as fh:
            fh.write(f"shown={f['shown']}\nnew_this_week={payload['new_this_week']}\n"
                     f"closing_soon={payload['closing_soon']}\n")
    return 0


def cmd_site(args) -> int:
    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    pages = site.build(cfg, Path(args.docs))
    print("\n".join(pages))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="learnradar",
                                 description="Find courses, training and degrees in Finland, Sweden, Norway and online.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="collect, classify, score -> docs/courses.json + digests/latest.md")
    r.add_argument("--config", default=str(ROOT / "config.yaml"))
    r.add_argument("--out", default=str(ROOT / "docs" / "courses.json"))
    r.add_argument("--ledger", default=str(ROOT / "data" / "seen.json"))
    r.add_argument("--digest", default=str(ROOT / "digests" / "latest.md"))
    r.add_argument("--sources", help="comma-separated subset: " + ",".join(pipeline.SOURCES))
    r.add_argument("--dashboard-url", default=os.environ.get("DASHBOARD_URL", ""))
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("site", help="rebuild the static pages from the current docs/courses.json, without fetching")
    s.add_argument("--config", default=str(ROOT / "config.yaml"))
    s.add_argument("--docs", default=str(ROOT / "docs"))
    s.set_defaults(fn=cmd_site)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
