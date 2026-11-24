import datetime as dt
import json
from pathlib import Path

import yaml

from learnradar import classify, pipeline, report
from learnradar.models import Offer
from learnradar.sources import SourceResult
from learnradar.text import has_keyword, parse_text_date

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
TODAY = dt.date(2026, 11, 24)


def offer(i, **kw):
    base = dict(source="opintopolku", source_id=str(i), title=f"Course {i}", url=f"https://example.org/{i}",
                provider="Uni", country="Finland", kind="course", cost="free", status="open", languages=["fi"])
    base.update(kw)
    return Offer(**base)


def test_keywords():
    assert has_keyword("intro to ai and ethics", "ai")
    assert not has_keyword("maintain your car", "ai")
    assert has_keyword("ohjelmoinnin perusteet", "ohjelmoi*")
    assert not has_keyword("perusohjelmointi", "ohjelmoi*")     # prefix must start the word
    assert has_keyword("c# for beginners", "c#")
    assert parse_text_date("Register by 31 October 2026 + 1 more") == "2026-10-31"
    assert parse_text_date("This programme has no deadline.") == ""


def test_topics_and_goals():
    o = offer(1, title="Data-analytiikan perusteet", summary="")
    classify.match_topics(o, CFG["topics"])
    assert o.topic == "Data & AI"
    # one passing mention in the description is not enough
    o2 = offer(2, title="Leadership skills", summary="Useful in healthcare and elsewhere.")
    classify.match_topics(o2, CFG["topics"])
    assert o2.topic == "Business & management" and "Health & social care" not in o2.topics
    o3 = offer(3, title="Basket weaving", summary="")
    classify.match_topics(o3, CFG["topics"], 0.5)
    assert o3.topic == "Other" and o3.topic_weight == 0.5
    assert "degree" in classify.goals(offer(4, kind="degree", level="master"))
    assert "change" in classify.goals(offer(5, kind="vocational"))
    assert "change" in classify.goals(offer(6, tags=["unemployed"]))
    assert "upskill" in classify.goals(offer(7, tags=["jotpa"]))
    assert "learn" in classify.goals(offer(8, kind="online", cost="free"))


def test_new_and_closing(tmp_path):
    ledger = {}
    a = [offer(1), offer(2, deadline="2026-12-01")]
    xs, _ = pipeline.process(a, CFG, TODAY, ledger, first_run=True)
    assert not any(o.is_new for o in xs)                         # nothing is new on the first run
    assert next(o for o in xs if o.source_id == "2").closing_soon
    later = TODAY + dt.timedelta(days=2)
    b = [offer(1), offer(2), offer(3), offer(9, source="norway", country="Norway")]
    xs, _ = pipeline.process(b, CFG, later, ledger, first_run=False)
    new = {o.source_id for o in xs if o.is_new}
    assert new == {"3"}                     # norway was never seen before: its first listing is a baseline
    assert next(o for o in xs if o.source_id == "1").first_seen == TODAY.isoformat()
    much_later = TODAY + dt.timedelta(days=20)
    xs, _ = pipeline.process(b, CFG, much_later, ledger, first_run=False)
    assert not any(o.is_new for o in xs)


def test_scores_rank_sensibly():
    ledger = {}
    xs, _ = pipeline.process([
        offer(1, title="Python programming", cost="free", credits=5.0, online=True, self_paced=True, status="anytime"),
        offer(2, title="Python programming advanced", cost="paid", credits=5.0),
        offer(3, title="Master's in data science", kind="degree", level="master", cost="free_eu"),
    ], CFG, TODAY, ledger, True)
    s = {o.source_id: o for o in xs}
    assert s["1"].score > s["2"].score
    assert s["3"].score > s["2"].score
    assert all(0 <= o.score <= 100 for o in xs)
    assert "Free" in s["1"].reasons and any(r.startswith("Field:") for r in s["1"].reasons)


def test_dedupe_and_exclude():
    funnel = {"collected": 3, "excluded": 0, "duplicates": 0}
    xs = pipeline.prefilter([offer(1), offer(2, title="Course 1"), offer(3, title="Demo course")], CFG, funnel)
    assert [o.source_id for o in xs] == ["1"] and funnel == {"collected": 3, "excluded": 1, "duplicates": 1}


def test_run_writes_files_and_digest(tmp_path):
    res = [SourceResult("opintopolku", offers=[offer(1, tags=["jotpa"], cost="funded"),
                                                offer(2, kind="degree", level="master", cost="free_eu", languages=["en"])]),
           SourceResult("norway", ok=False, error="HTTP 503")]
    out = tmp_path / "docs" / "courses.json"
    payload = pipeline.run(CFG, out, today=TODAY, ledger_path=tmp_path / "seen.json", results=res)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["funnel"]["shown"] == 2 and data["sources"][1]["ok"] is False
    assert (tmp_path / "seen.json").exists()
    md = report.digest(payload, "https://example.github.io/learning-radar/", CFG)
    assert "Free training and courses in Finland" in md and "Course 1" in md and "Source problems" in md and "HTTP 503" in md


def test_run_refuses_when_everything_failed(tmp_path):
    import pytest
    with pytest.raises(RuntimeError):
        pipeline.run(CFG, tmp_path / "c.json", today=TODAY, ledger_path=tmp_path / "s.json",
                     results=[SourceResult("norway", ok=False, error="down")])
    assert not (tmp_path / "c.json").exists()


def test_group_caps():
    cfg = dict(CFG, sources={"sweden": {"max_items": 3, "max_per_group": {"HS": 1}}})
    xs = [offer(i, source="sweden", group="HS", title=f"Uni {i}", kind="degree", level="master") for i in range(3)]
    xs += [offer(10 + i, source="sweden", group="FHS", title=f"Folk {i}") for i in range(3)]
    kept, funnel = pipeline.process(xs, cfg, TODAY, {}, True)
    groups = [o.group for o in kept]
    assert groups.count("HS") == 1 and groups.count("FHS") == 2 and funnel["capped"] == 3
