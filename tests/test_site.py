import copy
import re
import shutil
from pathlib import Path

import yaml

from learnradar import site

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def o(i, **kw):
    base = {"id": f"opintopolku:{i}", "source": "opintopolku", "title": f"Kurssi {i}", "url": f"https://example.org/{i}",
            "provider": "Opisto", "country": "Finland", "kind": "training", "cost": "funded", "languages": ["fi"],
            "tags": ["jotpa"], "goals": ["upskill"], "score": 50 + i}
    base.update(kw)
    return base


def data(offers):
    return {"generated_at": "2026-11-24T09:00:00+00:00", "date": "2026-11-24", "offers": offers}


def docs_dir(tmp_path):
    d = tmp_path / "docs"
    d.mkdir()
    shutil.copy(ROOT / "docs" / "index.html", d / "index.html")
    return d


def test_filters_match_the_dashboard():
    xs = [o(1), o(2, country="Sweden"), o(3, online=True, country=""), o(4, cost="audit", tags=[]),
          o(5, languages=["fi", "en"], kind="degree", goals=["degree"])]
    assert [x["id"] for x in site.select(xs, {"show": "jotpa", "where": "fi"})] == \
        ["opintopolku:5", "opintopolku:1"]                      # best score first
    assert len(site.select(xs, {"cost": "free"})) == 4          # audit is not free...
    assert len(site.select(xs, {"cost": "learnfree"})) == 5     # ...but it is free to learn
    assert len(site.select(xs, {"where": "nordic"})) == 4
    assert len(site.select(xs, {"where": "online"})) == 1
    assert len(site.select(xs, {"lang": "en", "kind": "degree"})) == 1
    assert site.to_hash({"where": "fi", "lang": "en"}) == "where=fi&lang=en"


def test_build_writes_pages_sitemap_and_stamps_index(tmp_path):
    docs = docs_dir(tmp_path)
    evil = o(0, title='<script>alert(1)</script> & co', url="javascript:alert(1)")
    written = site.build(CFG, docs, data([o(i) for i in range(1, 30)] + [evil]))
    assert "fi/jotpa-koulutukset/index.html" in written
    assert "en/english-taught-degrees-sweden/index.html" not in written       # under MIN_OFFERS
    page = (docs / "fi/jotpa-koulutukset/index.html").read_text(encoding="utf-8")
    assert '<html lang="fi">' in page and "30 vaihtoehtoa" in page
    assert 'href="../../#show=jotpa"' in page
    ranked = re.search(r'<ol class="list">(.*?)</ol>', page, re.S).group(1)
    assert ranked.count("<li>") == site.TOP
    assert "<script>alert" not in page and "javascript:" not in page          # escaped, unsafe link dropped
    sm = (docs / "sitemap.xml").read_text(encoding="utf-8")
    assert "https://girimohan.github.io/learning-radar/fi/jotpa-koulutukset/" in sm
    assert "english-taught-degrees-sweden" not in sm
    idx = (docs / "index.html").read_text(encoding="utf-8")
    assert '<link rel="canonical" href="https://girimohan.github.io/learning-radar/">' in idx
    assert 'href="fi/jotpa-koulutukset/"' in idx
    # running again changes nothing
    site.build(CFG, docs, data([o(i) for i in range(1, 30)] + [evil]))
    assert (docs / "index.html").read_text(encoding="utf-8") == idx


def test_custom_domain_and_analytics(tmp_path):
    docs = docs_dir(tmp_path)
    (docs / "CNAME").write_text("learn.barmo.fi\n", encoding="utf-8")
    cfg = copy.deepcopy(CFG)
    cfg["site"]["analytics"] = {"provider": "plausible", "id": "learn.barmo.fi"}
    site.build(cfg, docs, data([o(i) for i in range(1, 10)]))
    idx = (docs / "index.html").read_text(encoding="utf-8")
    assert 'href="https://learn.barmo.fi/"' in idx and 'data-domain="learn.barmo.fi"' in idx
    assert "Sitemap: https://learn.barmo.fi/sitemap.xml" in (docs / "robots.txt").read_text(encoding="utf-8")
    assert "Plausible" in (docs / "privacy/index.html").read_text(encoding="utf-8")


def test_privacy_without_analytics_says_so(tmp_path):
    docs = docs_dir(tmp_path)
    cfg = copy.deepcopy(CFG)
    cfg["site"]["analytics"] = {"provider": "plausible", "id": ""}
    site.build(cfg, docs, data([o(1)]))
    assert "do not use any analytics" in (docs / "privacy/index.html").read_text(encoding="utf-8")
    assert "plausible.io/js" not in (docs / "index.html").read_text(encoding="utf-8")


def test_page_filters_are_valid_dashboard_filters():
    # Every landing page filter must use keys and values the dashboard understands.
    js = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    for lang, slug, flt, *_ in site.PAGES:
        assert re.fullmatch(r"[a-z0-9-]+", slug) and lang in site.T
        for k, v in flt.items():
            assert re.search(rf"\b{k}: \(o, v\)", js), k
            if k == "show":
                assert re.search(rf"\b{v}:\[", js), v
