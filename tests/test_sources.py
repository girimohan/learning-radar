"""Each source's parser, on records shaped like the real API responses (trimmed)."""
import datetime as dt

from learnradar.sources import coursera, futurelearn, moocfi, mslearn, opintopolku

TODAY = dt.date(2026, 11, 24)

OP_HIT = {
    "oid": "1.2.246.562.13.00000000000000013081",
    "nimi": {"en": "An introduction to battery technology and industry", "fi": "Johdanto akkuteknologiaan"},
    "kuvaus": {"en": "<p>This course gives you an understanding of rechargeable <b>batteries</b>.</p>"},
    "koulutustyyppi": "kk-opintojakso",
    "opintojenLaajuusyksikko": {"koodiUri": "opintojenlaajuusyksikko_2#1", "nimi": {"en": "ECTS credits"}},
    "opintojenLaajuusNumero": None, "opintojenLaajuusNumeroMin": 1.0, "opintojenLaajuusNumeroMax": 1.0,
    "toteutukset": [{"oppilaitosNimi": {"fi": "Itä-Suomen yliopisto", "en": "University of Eastern Finland"},
                     "kunnat": [{"nimi": {"fi": "Kuopio"}}]}],
    "luokittelutermit": ["akkuala", "batteries"], "tutkintonimikkeet": [], "koulutukset": [],
}


def test_opintopolku_jotpa_course():
    o = opintopolku.to_offer(OP_HIT, "open", {"jotpa", "fee_free", "lang_en", "online", "open_university"})
    assert o.title == "An introduction to battery technology and industry"
    assert o.url.endswith("/konfo/en/koulutus/1.2.246.562.13.00000000000000013081")
    assert o.provider == "University of Eastern Finland" and o.city == "Kuopio" and o.country == "Finland"
    assert o.kind == "course" and o.credits == 1.0 and o.duration == "1 ECTS"
    assert o.cost == "funded" and "Jotpa" in o.cost_note
    assert o.languages == ["en"] and o.online and o.status == "open"
    assert set(o.tags) == {"jotpa", "open_university"}          # fee_/lang_/online are folded into fields
    assert "<" not in o.summary


def test_opintopolku_costs():
    assert opintopolku._cost({"fee_free"})[0] == "free"
    assert opintopolku._cost({"fee_free", "fee_paid"})[0] == "varies"
    assert opintopolku._cost({"fee_tuition"})[0] == "free_eu"
    assert opintopolku._cost({"fee_paid"})[0] == "paid"
    assert opintopolku._cost({"unemployed", "fee_paid"})[0] == "funded"
    assert opintopolku._cost(set())[0] == "unknown"


def test_opintopolku_several_versions_are_not_all_funded():
    """A programme run by 19 schools, one of them Jotpa-funded, must not be labelled 'funded' as a whole."""
    hit = dict(OP_HIT, koulutustyyppi="amk", nimi={"en": "Bachelor of Engineering, Information Technology"},
               tutkintonimikkeet=[{"nimi": {"en": "Bachelor of Engineering"}}],
               toteutukset=[{"oppilaitosNimi": {"en": f"UAS {i}"}, "kunnat": []} for i in range(19)])
    o = opintopolku.to_offer(hit, "open", {"jotpa", "lang_fi", "lang_en", "online"})
    assert o.cost == "free"                     # Finnish degree, no fee tags: free by law
    assert "19 versions; some are Jotpa-funded, taught in English, online" in o.cost_note
    assert o.languages == ["fi", "en"] and "several_versions" in o.tags
    assert o.provider == "UAS 0 + 18 more"
    en_only = opintopolku.to_offer(hit, "open", {"lang_en"})
    assert en_only.cost == "free_eu"


def test_opintopolku_search_shaped_hit():
    hit = {k: v for k, v in OP_HIT.items() if k != "toteutukset"}
    hit["toteutustenTarjoajat"] = {"count": 3, "nimi": {"en": "Metropolia University of Applied Sciences"}}
    o = opintopolku.to_offer(hit, "upcoming", {"jotpa"})
    assert o.provider == "Metropolia University of Applied Sciences + 2 more" and o.city == ""
    assert o.cost != "funded" and "3 versions; some are Jotpa-funded" in o.cost_note


def test_opintopolku_falls_back_when_listing_ignores_the_window(monkeypatch):
    """The listing endpoint returns all ~7,500 programmes for 'opens within 30 days'; use search then."""
    calls = []

    def fake_get(url, params=None, **kw):
        calls.append((url, dict(params)))
        listing = url == opintopolku.LISTING
        if "hakualkaapaivissa" in params:
            total = 7477 if listing else 2
        else:
            total = 1
        if params["size"] == 1:
            return {"total": total, "hits": []}
        if listing:
            return {"total": total, "hits": [dict(OP_HIT, oid="L1")]}
        tag_only = set(params) - {"lng", "page", "size", "hakukaynnissa", "hakualkaapaivissa"}
        if tag_only:
            return {"total": 0, "hits": []}
        return {"total": total, "hits": [dict(OP_HIT, oid="S1"), dict(OP_HIT, oid="S2")]}

    monkeypatch.setattr(opintopolku, "get", fake_get)
    res = opintopolku.fetch({"delay_seconds": 0})
    by_id = {o.source_id: o.status for o in res.offers}
    assert by_id == {"L1": "open", "S1": "upcoming", "S2": "upcoming"}
    assert "'upcoming' read from the search endpoint" in res.detail and "ignored" not in res.detail


def test_opintopolku_degree_level_and_finnish_fallback():
    hit = dict(OP_HIT, koulutustyyppi="amk", nimi={"fi": "Sairaanhoitaja (AMK)"}, opintojenLaajuusNumero=210.0,
               tutkintonimikkeet=[{"nimi": {"fi": "Sairaanhoitaja (AMK)", "en": "Bachelor of Health Care"}}])
    o = opintopolku.to_offer(hit, "upcoming", set())
    assert o.kind == "degree" and o.level == "bachelor" and o.credits == 210
    assert o.title == "Sairaanhoitaja (AMK)" and "/konfo/fi/" in o.url
    assert o.languages == ["fi"] and o.status == "upcoming"


FL = {
    "uuid": "u1", "url": "https://www.futurelearn.com/courses/x?utm_campaign=Courses+feed&utm_source=courses-feed",
    "name": "Agentic AI Fundamentals", "introduction": "Build autonomous AI systems.", "course_level": "Introductory",
    "language": "en", "hours_per_week": 2, "has_certificates": True, "categories": ["IT & Computer Science"],
    "topics": ["AI"], "organisation": {"name": "Edureka"}, "open_for_enrolment": True, "access_model": "Unlimited",
    "runs": [{"start_date": "2025-01-06", "duration_in_weeks": 2, "business_model": "upgraded_access"}],
    "reviews": {"average_score": 4.61, "total_count": 59},
}


def test_futurelearn():
    o = futurelearn.to_offer(FL, TODAY)
    assert o.url == "https://www.futurelearn.com/courses/x"
    assert o.cost == "audit" and o.status == "anytime" and o.self_paced and o.level == "beginner"
    assert "rated 4.6/5 (59)" in o.tags
    sponsored = dict(FL, runs=[{"start_date": "2027-01-11", "duration_in_weeks": 3, "business_model": "sponsored_access"}],
                     reviews={"average_score": None, "total_count": None})
    s = futurelearn.to_offer(sponsored, TODAY)
    assert s.cost == "funded" and s.status == "scheduled" and s.starts == "2027-01-11"
    assert futurelearn.to_offer(dict(FL, open_for_enrolment=False), TODAY) is None


def test_coursera_professional_certificate():
    s = {"id": "abc", "slug": "google-data-analytics", "name": "Google Data Analytics", "partnerIds": ["1"],
         "productVariant": "ProfessionalCertificateS12n", "metadata": {"level": "BEGINNER", "monthsToCompleteOverride": 6},
         "courseIds": ["a", "b"], "tagline": "Get on the fast track to a career in data analytics."}
    o = coursera.spec_offer(s, {"1": "Google"}, {"en"})
    assert o.url == "https://www.coursera.org/professional-certificates/google-data-analytics"
    assert o.kind == "training" and o.provider == "Google" and "professional_certificate" in o.tags
    assert o.duration == "2 courses, about 6 months" and o.cost == "varies"
    assert coursera.spec_offer(dict(s, primaryLanguages=["es"]), {}, {"en"}) is None


def test_mslearn_and_moocfi():
    c = mslearn.cert_offer({"uid": "certification.x", "title": "Microsoft Certified: Azure Fundamentals",
                            "url": "https://learn.microsoft.com/en-us/credentials/x/?WT.mc_id=api_CatalogApi",
                            "levels": ["beginner"], "subjects": ["cloud-computing"]})
    assert c.cost == "paid" and c.kind == "certification" and "WT.mc_id" not in c.url
    m = moocfi.to_offer({"id": "1", "name": "Elements of AI", "slug": "elements-of-ai", "ects": "2", "status": "Active",
                         "hidden": False, "language": "en", "link": "https://www.elementsofai.com/"}, {"en", "fi"})
    assert m.cost == "free" and m.credits == 2 and m.status == "anytime"
    assert moocfi.to_offer({"name": "X", "status": "Ended", "language": "en"}, {"en"}) is None
    assert moocfi.to_offer({"name": "X", "status": "Active", "language": "el"}, {"en"}) is None


def test_sweden_university_course_and_yh():
    from learnradar.sources import sweden
    ev = {"id": "e.1", "status": "ACTIVE", "content": {
        "education": "i.1", "providers": ["p.gu"], "languageOfInstructions": ["eng"],
        "url": {"urls": [{"lang": "eng", "value": "https://www.gu.se/en/x"}]},
        "execution": {"start": "2027-01-18"}, "locations": [{"town": "Ortsoberoende"}], "paceOfStudy": {"percentage": 50},
        "extensions": [{"type": "UHEventExtension", "itdistance": False, "tuitionFee": {"value": True, "total": 40500},
                        "applicationDetails": {"closeDate": "2026-12-01"}}]}}
    info = {"id": "i.1", "content": {"title": {"strings": [{"lang": "swe", "value": "Dentala material"},
                                                         {"lang": "eng", "value": "Advanced dental materials"}]},
                                     "credits": {"system": {"code": "hp"}, "credits": 15}, "configuration": {"code": "kurs"}}}
    o = sweden.to_offer(ev, info, {"p.gu": "University of Gothenburg"}, "HS", TODAY)
    assert o.title == "Advanced dental materials" and o.provider == "University of Gothenburg"
    assert o.kind == "course" and o.credits == 15 and o.cost == "free_eu" and "40,500" in o.cost_note
    assert o.online and o.city == "" and o.deadline == "2026-12-01" and o.languages == ["en"] and "part_time" in o.tags
    closed = dict(ev, content=dict(ev["content"], extensions=[dict(ev["content"]["extensions"][0],
                                                                    applicationDetails={"closeDate": "2026-10-15"})]))
    assert sweden.to_offer(closed, info, {}, "HS", TODAY) is None
    assert sweden.to_offer(dict(ev, status="DELETED", content=None), info, {}, "HS", TODAY) is None
    yh = {"id": "e.2", "status": "ACTIVE", "content": {"education": "i.2", "providers": [], "distance": {},
          "url": {"urls": [{"lang": "swe", "value": "https://example.se"}]}, "execution": {"start": "2027-08-16"},
          "application": {"last": "2027-04-15"}, "languageOfInstructions": ["swe"]}}
    yinfo = {"id": "i.2", "content": {"title": {"strings": [{"lang": "swe", "value": "Front End Developer"}]},
                                      "credits": {"system": {"code": "yh"}, "credits": 400}}}
    y = sweden.to_offer(yh, yinfo, {}, "YH", TODAY)
    assert y.kind == "vocational" and y.cost == "free" and y.online and y.duration == "400 YH credits"
    assert y.deadline == "2027-04-15" and y.country == "Sweden" and y.languages == ["sv"]


def test_norway_programmes_and_fagskole():
    from learnradar.sources import norway
    x = {"title": "Bioingeniørfag", "uh_tilbud_id": ["uit.no___BIOING"], "uh_tilbud_title": ["Bioingeniørfag - bachelor"],
         "uh_tilbud_url": ["/utdanning/uit.no/bioingeniorfag_-_bachelor"], "sted": ["Troms"],
         "organisasjon": "UiT Norges arktiske universitet", "studieniva": "Bachelor", "studieplasser": 24,
         "deltid": "", "nettbasert": "", "interesse": ["Helse/Helse og medisin"]}
    o = norway.programme_offer(x)
    assert o.url == "https://utdanning.no/utdanning/uit.no/bioingeniorfag_-_bachelor"
    assert o.kind == "degree" and o.level == "bachelor" and o.cost == "free_eu" and o.city == "Troms"
    private = norway.programme_offer(dict(x, organisasjon="Høyskolen Kristiania", studieniva="Årsstudium", sted=["Ukjent"]))
    assert private.cost == "unknown" and private.kind == "training" and private.credits == 60 and private.city == ""
    f = norway.fagskole_offer({"navn": "Visuelle kunstfag", "lenke": "/uno-sync-redirect/fagskole_tilbud/396254",
                               "fagskole": "Einar Granum Kunstfagskole", "studieform": ["Deltid", "Nettbasert"],
                               "studietype": "Fagskolegrad", "sted": ["Oslo"], "fagfelt": ["Kunstfag"]})
    assert f.kind == "vocational" and f.online and "part_time" in f.tags and f.source_id == "fagskole:396254"


def test_norway_english_titles():
    from learnradar.sources import norway
    assert norway._languages("Master's Programme in Energy and Environment") == ["en"]
    assert norway._languages("Bachelor of Science in Marine Engineering") == ["en"]
    assert norway._languages("Sykepleie – Fleksibel deltidsutdanning") == ["no"]
    assert norway._languages("Økonomi og administrasjon") == ["no"]
    assert norway._languages("Master i ledelse") == ["no"]
