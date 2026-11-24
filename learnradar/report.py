"""The weekly digest: a Markdown page that becomes a GitHub issue (GitHub emails it to you)."""
from __future__ import annotations

FLAG = {"Finland": "🇫🇮", "Sweden": "🇸🇪", "Norway": "🇳🇴", "Germany": "🇩🇪"}


def _line(o: dict, costs: dict, kinds: dict) -> str:
    where = FLAG.get(o.get("country", ""), "")
    place = ", ".join(x for x in [o.get("city", "").split(",")[0], o.get("country", "")] if x)
    if o.get("online"):
        place = "Online" + (f" ({place})" if place else "")
    bits = [kinds.get(o["kind"], o["kind"]), costs.get(o["cost"], o["cost"]), place]
    if o.get("deadline"):
        bits.append(f"deadline {o['deadline']}")
    head = f"- {where + ' ' if where else ''}**[{o['title']}]({o['url']})**"
    prov = f", {o['provider']}" if o.get("provider") else ""
    return f"{head}{prov} · {' · '.join(b for b in bits if b)} · **{o['score']:.0f}**"


def _section(title: str, xs: list[dict], payload: dict, note: str = "") -> list[str]:
    if not xs:
        return []
    out = [f"## {title}", ""]
    if note:
        out += [note, ""]
    out += [_line(o, payload["costs"], payload["kinds"]) for o in xs] + [""]
    return out


def digest(payload: dict, dashboard_url: str = "", cfg: dict | None = None) -> str:
    d = (cfg or {}).get("digest", {})
    xs = payload["offers"]
    f = payload["funnel"]
    out = [f"# Learning radar, {payload['date']}", ""]
    out.append(f"{len(xs):,} courses, training programmes and degrees worth a look, out of {f['collected']:,} "
               f"collected. {payload['new_this_week']:,} are new this week and {payload['closing_soon']:,} have a "
               f"deadline in the next three weeks.")
    if dashboard_url:
        out += ["", f"**[Open the dashboard]({dashboard_url})** to filter by goal, field, cost, place and language."]
    out.append("")
    new = [o for o in xs if o.get("is_new")]
    out += _section("New this week", new[: d.get("top_new", 15)], payload)
    closing = sorted((o for o in xs if o.get("closing_soon")), key=lambda o: o["deadline"])
    out += _section("Deadlines coming up", closing[: d.get("top_closing", 12)], payload)
    free_fi = [o for o in xs if o.get("country") == "Finland" and o["cost"] in ("free", "funded")
               and o.get("status") == "open" and o["kind"] != "degree"]
    funded = [o for o in free_fi if o["cost"] == "funded"]           # Jotpa / labour market training first
    free_fi = funded + [o for o in free_fi if o not in funded]
    out += _section("Free training and courses in Finland, application open now",
                    free_fi[: d.get("top_free_finland", 12)], payload,
                    "Jotpa-funded training for working-age adults and labour market training for jobseekers first.")
    nordic = [o for o in xs if o.get("country") in ("Sweden", "Norway") and o["cost"] in ("free", "funded")
              and o["kind"] in ("vocational", "training", "course")]
    out += _section("Free vocational training in Sweden and Norway", nordic[: d.get("top_nordic", 10)], payload,
                    "Swedish higher vocational education (YH) and labour market training, folk high schools, "
                    "and Norwegian vocational colleges.")
    degrees = [o for o in xs if o["kind"] == "degree" and o["cost"] in ("free", "free_eu")
               and o.get("status") == "open" and "en" in o.get("languages", [])]
    out += _section("Degrees taught in English with no tuition (for EU/EEA citizens at least)",
                    degrees[: d.get("top_degrees", 8)], payload)
    bad = [s for s in payload["sources"] if not s["ok"] or "ignored" in (s.get("detail") or "")
           or "stopped early" in (s.get("detail") or "")]
    if bad:
        out += ["## Source problems", ""] + [f"- **{s['name']}**: {s['error'] or s['detail']}" for s in bad] + [""]
    out += ["---", "Costs, dates and eligibility come from each provider's listing and can change. "
            "Check the course page before you apply."]
    return "\n".join(out) + "\n"
