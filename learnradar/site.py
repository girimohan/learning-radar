"""Static pages around the dashboard, rebuilt from docs/courses.json on every run.

* Landing pages for common searches (docs/<lang>/<slug>/index.html), one plain HTML list each, so search
  engines and people without JavaScript see real content. Each page is a saved dashboard filter: its count and
  its "open all" link give the same result as the dashboard.
* docs/about/ (disclaimer, how the score works, sources and licences, accessibility) and docs/privacy/.
* docs/sitemap.xml and docs/robots.txt.
* The shared <head> block of docs/index.html (canonical URL, Open Graph tags, analytics) and its list of
  landing pages, between <!-- site:... --> markers.

The site address comes from docs/CNAME when a custom domain is set, otherwise from `site.url` in config.yaml.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from html import escape
from pathlib import Path

FREE = {"free", "funded", "free_eu"}
LEARN_FREE = FREE | {"audit"}
NORDIC = {"Finland", "Sweden", "Norway", "Denmark", "Iceland"}
COUNTRY = {"fi": "Finland", "se": "Sweden", "no": "Norway"}
SHOW_TAG = {"jotpa": "jotpa", "unemployed": "unemployed", "higher_vocational": "higher_vocational",
            "folk": "folk_high_school", "part_time": "part_time", "open_university": "open_university",
            "micro": "micro", "evening": "evening"}
TOP = 20
REPO = "https://github.com/girimohan/learning-radar"


# ---- the dashboard's filters, in Python (must match TESTS in docs/index.html) ----

def _test(o: dict, key: str, v: str) -> bool:
    if key == "goal":
        return v in (o.get("goals") or [])
    if key == "where":
        if v == "online":
            return bool(o.get("online"))
        if v == "nordic":
            return o.get("country") in NORDIC
        return o.get("country") == COUNTRY.get(v)
    if key == "cost":
        c = o.get("cost")
        return c in FREE if v == "free" else c in LEARN_FREE if v == "learnfree" else c in ("paid", "varies", "unknown")
    if key == "kind":
        return o.get("kind") == v
    if key == "topic":
        return o.get("topic") == v or v in (o.get("topics") or [])
    if key == "lang":
        return v in (o.get("languages") or [])
    if key == "level":
        return o.get("level") == v
    if key == "show":
        if v == "new":
            return bool(o.get("is_new"))
        if v == "soon":
            return bool(o.get("closing_soon"))
        if v == "apply":
            return o.get("status") in ("open", "anytime")
        return SHOW_TAG.get(v, v) in (o.get("tags") or [])
    raise KeyError(key)


def select(offers: list[dict], flt: dict) -> list[dict]:
    """Offers matching a dashboard filter, best first (the dashboard's default order)."""
    xs = [o for o in offers if all(_test(o, k, v) for k, v in flt.items())]
    return sorted(xs, key=lambda o: -o.get("score", 0))


def to_hash(flt: dict) -> str:
    return "&".join(f"{k}={v}" for k, v in flt.items())


# ---- landing pages ----

PAGES = [
    # (lang, slug, filter, title, description, intro)
    ("fi", "ilmaiset-koulutukset", {"where": "fi", "cost": "free", "goal": "upskill"},
     "Ilmaiset koulutukset ja kurssit Suomessa",
     "Maksuttomat ja julkisesti rahoitetut koulutukset ja kurssit Suomessa yhdellä listalla, parhaat ensin. "
     "Päivittyy kolmesti viikossa.",
     "Maksuttomat tai julkisesti rahoitetut koulutukset ja kurssit, joilla voit kehittää osaamistasi työn ohessa. "
     "Mukana on muun muassa Jotpan rahoittamia koulutuksia, täydennyskoulutuksia ja ammatillisia kursseja. "
     "Tutkinnot ovat omalla listallaan Learning Radarissa."),
    ("fi", "jotpa-koulutukset", {"show": "jotpa"},
     "Jotpan rahoittamat koulutukset",
     "Haettavana olevat Jatkuvan oppimisen ja työllisyyden palvelukeskuksen (Jotpa) rahoittamat koulutukset "
     "työikäisille yhdellä listalla. Maksuttomia tai edullisia, usein verkossa.",
     "Jatkuvan oppimisen ja työllisyyden palvelukeskus Jotpa rahoittaa työikäisille suunnattuja koulutuksia "
     "aloille, joilla on osaajapulaa. Koulutukset ovat osallistujille maksuttomia tai edullisia, ja moni "
     "järjestetään verkossa tai iltaisin."),
    ("fi", "avoin-yliopisto", {"show": "open_university"},
     "Avoimen yliopiston ja avoimen AMK:n kurssit",
     "Avoimen yliopiston ja avoimen ammattikorkeakoulun kurssit, joihin voi ilmoittautua nyt. "
     "Ei pohjakoulutusvaatimuksia, ja opintopisteet voi hyödyntää myöhemmin tutkinnossa.",
     "Yliopistot ja ammattikorkeakoulut tarjoavat avoimena opetuksena yksittäisiä kursseja, joihin ei tarvita "
     "pohjakoulutusta. Kurssit maksavat yleensä pienen opintopistekohtaisen maksun, ja suoritetut opinnot voi "
     "myöhemmin sisällyttää tutkintoon."),
    ("fi", "koulutukset-tyonhakijoille", {"where": "fi", "show": "unemployed"},
     "Koulutukset työnhakijoille",
     "Työnhakijoille suunnatut koulutukset Suomessa, kuten työvoimakoulutukset. Maksuttomia, ja "
     "työttömyysetuuden voi yleensä säilyttää opiskelun aikana.",
     "Jos olet ilmoittautunut työnhakijaksi, työvoimakoulutus on sinulle maksuton ja voit yleensä saada "
     "työttömyysetuutta opiskelun ajalta. Keskustele aina ensin oman työllisyyspalvelusi kanssa ennen kuin haet."),
    ("en", "english-taught-degrees-finland", {"where": "fi", "kind": "degree", "lang": "en"},
     "English-taught degrees in Finland",
     "Bachelor's and master's degrees taught in English at Finnish universities and universities of applied "
     "sciences, free for EU/EEA citizens. Updated three times a week.",
     "Bachelor's and master's programmes in Finland where English is a teaching language. They are free for "
     "EU/EEA citizens; students from elsewhere usually pay tuition and can often apply for a scholarship from "
     "the university. Most open for application in the joint application periods in January and March."),
    ("en", "free-courses-in-english-finland", {"where": "fi", "lang": "en", "cost": "free"},
     "Free courses and degrees in English in Finland",
     "Courses, training and degrees in Finland that are taught in English and free or publicly funded, "
     "best first. Updated three times a week.",
     "Courses, training and degrees in Finland that are taught in English and are free or publicly funded. "
     "Degrees on this list are free for EU/EEA citizens; students from elsewhere usually pay tuition."),
    ("en", "english-taught-degrees-sweden", {"where": "se", "kind": "degree", "lang": "en"},
     "English-taught degrees in Sweden",
     "Bachelor's and master's programmes taught in English at Swedish universities, free for EU/EEA and "
     "Swiss citizens. Updated three times a week.",
     "Bachelor's and master's programmes at Swedish universities where English is a teaching language. "
     "Tuition is free for EU/EEA and Swiss citizens; others pay tuition. You apply at universityadmissions.se."),
    ("en", "free-online-courses", {"where": "online", "cost": "free"},
     "Free online courses for your career",
     "Free online courses and training from universities and online platforms, ranked by what they can do "
     "for your career. Updated three times a week.",
     "Free online courses and training from universities and online platforms, ranked by what they can do "
     "for your career: credits and certificates first, then fields with good job prospects. Courses where "
     "only the certificate costs money are in the radar too, under \"Free to learn\"."),
    ("sv", "yrkeshogskola", {"where": "se", "show": "higher_vocational"},
     "Yrkeshögskoleutbildningar (YH)",
     "Yrkeshögskoleutbildningar i hela Sverige på en lista: avgiftsfria, framtagna tillsammans med "
     "arbetslivet och berättigade till studiemedel från CSN. Många går på distans.",
     "Yrkeshögskolan erbjuder yrkesinriktade utbildningar på sex månader till två år som tas fram tillsammans "
     "med arbetsgivare. Utbildningarna är avgiftsfria och berättigar till studiemedel från CSN, och många kan "
     "läsas på distans."),
    ("sv", "folkhogskola", {"where": "se", "show": "folk"},
     "Folkhögskolekurser",
     "Kurser och utbildningar på folkhögskolor i Sverige på en lista. Ingen kursavgift, korta och långa "
     "kurser, många på distans.",
     "Folkhögskolor tar inte ut någon kursavgift, men du kan behöva betala för material, mat eller boende. "
     "Här finns både korta kurser och längre utbildningar."),
    ("sv", "arbetsmarknadsutbildning", {"where": "se", "show": "unemployed"},
     "Arbetsmarknadsutbildningar",
     "Arbetsmarknadsutbildningar i Sverige på en lista: avgiftsfria yrkesutbildningar för arbetssökande.",
     "Arbetsförmedlingen köper yrkesutbildningar för arbetssökande som är inskrivna hos dem. Utbildningarna är "
     "avgiftsfria, och det är Arbetsförmedlingen som beviljar platserna."),
    ("no", "fagskole", {"where": "no", "kind": "vocational"},
     "Fagskoleutdanninger",
     "Fagskoleutdanninger i hele Norge på én liste: praktiske, yrkesrettede utdanninger på seks måneder til "
     "to år, mange på deltid eller nett.",
     "Fagskolene tilbyr praktiske, yrkesrettede høyere utdanninger på seks måneder til to år, og mange kan tas "
     "på deltid eller nett. Offentlige fagskoler er som regel gratis, mens private kan ta skolepenger."),
    ("no", "bachelor-og-master", {"where": "no", "kind": "degree"},
     "Bachelor- og masterprogrammer i Norge",
     "Bachelor- og masterprogrammer ved norske universiteter og høgskoler på én liste. Statlige institusjoner "
     "tar ikke skolepenger fra EU/EØS-borgere.",
     "Bachelor- og masterprogrammer ved norske universiteter og høgskoler. Statlige institusjoner tar ikke "
     "skolepenger fra EU/EØS-borgere, bare en semesteravgift; siden 2023 betaler studenter fra andre land "
     "skolepenger. De fleste programmene søkes gjennom Samordna opptak om våren."),
]
MIN_OFFERS = 5          # a page with fewer offers is left out (and removed if it was built before)

T = {
    "en": dict(open="Open all {n} in Learning Radar", top="The {k} best, by score", updated="Updated {d}",
               deadline="Deadline {d}", online="Online", other="More lists", about="About and sources",
               privacy="Privacy", report="Report an error", credit="A free tool by Barmo",
               count="{n} options right now", home="All courses",
               disclaimer="Learning Radar is an independent service and is not affiliated with the Finnish National "
                          "Agency for Education, Skolverket or Utdanning.no. Details come from each provider's "
                          "listing and can change: always check the course page before you apply.",
               costs=dict(free="Free", funded="Free (publicly funded)", free_eu="Free for EU/EEA citizens",
                          audit="Free to learn, certificate paid", varies="Free or paid, depends on the option",
                          paid="Paid", unknown="Cost not stated"),
               kinds=dict(degree="Degree", vocational="Vocational qualification", training="Professional training",
                          course="Course", online="Online course", certification="Certification",
                          prep="Language & preparatory"),
               countries={}),
    "fi": dict(open="Avaa kaikki {n} Learning Radarissa", top="{k} parasta pisteiden mukaan",
               updated="Päivitetty {d}", deadline="Haku päättyy {d}", online="Verkossa", other="Muut listat",
               about="Tietoa ja lähteet", privacy="Tietosuoja", report="Ilmoita virheestä",
               credit="Barmon ilmainen työkalu", count="{n} vaihtoehtoa juuri nyt", home="Kaikki koulutukset",
               disclaimer="Learning Radar on riippumaton palvelu, eikä se liity Opetushallitukseen, Skolverketiin "
                          "tai Utdanning.no:hon. Tiedot tulevat järjestäjien omista ilmoituksista ja voivat muuttua: "
                          "tarkista aina koulutuksen oma sivu ennen kuin haet.",
               costs=dict(free="Maksuton", funded="Maksuton (julkisesti rahoitettu)",
                          free_eu="Maksuton EU/ETA-kansalaisille", audit="Opiskelu maksuton, todistus maksullinen",
                          varies="Maksuton tai maksullinen, vaihtelee", paid="Maksullinen",
                          unknown="Hinta ei tiedossa"),
               kinds=dict(degree="Tutkinto", vocational="Ammatillinen tutkinto", training="Täydennyskoulutus",
                          course="Kurssi", online="Verkkokurssi", certification="Sertifikaatti",
                          prep="Kieli- ja valmentava koulutus"),
               countries={"Finland": "Suomi", "Sweden": "Ruotsi", "Norway": "Norja"}),
    "sv": dict(open="Visa alla {n} i Learning Radar", top="De {k} bästa enligt poäng", updated="Uppdaterad {d}",
               deadline="Sista ansökningsdag {d}", online="Distans", other="Fler listor",
               about="Om tjänsten och källor", privacy="Integritet", report="Rapportera ett fel",
               credit="Ett gratis verktyg från Barmo", count="{n} alternativ just nu", home="Alla utbildningar",
               disclaimer="Learning Radar är en fristående tjänst och har ingen koppling till Skolverket, "
                          "Utbildningsstyrelsen i Finland eller Utdanning.no. Uppgifterna kommer från anordnarnas "
                          "egna annonser och kan ändras: kontrollera alltid utbildningens egen sida innan du söker.",
               costs=dict(free="Avgiftsfri", funded="Avgiftsfri (offentligt finansierad)",
                          free_eu="Avgiftsfri för EU/EES-medborgare", audit="Gratis att läsa, intyg kostar",
                          varies="Gratis eller avgift, beror på alternativ", paid="Avgift",
                          unknown="Kostnad ej angiven"),
               kinds=dict(degree="Program", vocational="Yrkesutbildning", training="Utbildning", course="Kurs",
                          online="Onlinekurs", certification="Certifiering", prep="Språk och förberedande"),
               countries={"Finland": "Finland", "Sweden": "Sverige", "Norway": "Norge"}),
    "no": dict(open="Se alle {n} i Learning Radar", top="De {k} beste etter poeng", updated="Oppdatert {d}",
               deadline="Søknadsfrist {d}", online="Nett", other="Flere lister", about="Om tjenesten og kilder",
               privacy="Personvern", report="Meld fra om feil", credit="Et gratis verktøy fra Barmo",
               count="{n} tilbud akkurat nå", home="Alle studier",
               disclaimer="Learning Radar er en uavhengig tjeneste og har ingen tilknytning til Utdanning.no, "
                          "Skolverket eller Utdanningsstyrelsen i Finland. Opplysningene kommer fra tilbydernes egne "
                          "oppføringer og kan endres: sjekk alltid studiets egen side før du søker.",
               costs=dict(free="Gratis", funded="Gratis (offentlig finansiert)", free_eu="Gratis for EU/EØS-borgere",
                          audit="Gratis å lære, sertifikat koster", varies="Gratis eller betalt, avhenger av tilbudet",
                          paid="Betalt", unknown="Pris ikke oppgitt"),
               kinds=dict(degree="Studieprogram", vocational="Fagskoleutdanning", training="Videreutdanning",
                          course="Kurs", online="Nettkurs", certification="Sertifisering",
                          prep="Språk og forberedende"),
               countries={"Finland": "Finland", "Sweden": "Sverige", "Norway": "Norge"}),
}
MONTHS_EN = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def fmt_date(iso: str, lang: str) -> str:
    try:
        d = dt.date.fromisoformat(iso[:10])
    except ValueError:
        return iso
    if lang == "en":
        return f"{d.day} {MONTHS_EN[d.month - 1]} {d.year}"
    if lang == "sv":
        return d.isoformat()
    return f"{d.day}.{d.month}.{d.year}"


# ---- shared pieces ----

def site_url(cfg: dict, docs: Path) -> str:
    cname = docs / "CNAME"
    if cname.exists() and cname.read_text(encoding="utf-8").strip():
        return f"https://{cname.read_text(encoding='utf-8').strip()}/"
    url = ((cfg.get("site") or {}).get("url") or "").strip()
    return url if url.endswith("/") else url + "/"


def analytics_tag(cfg: dict) -> str:
    a = (cfg.get("site") or {}).get("analytics") or {}
    provider, ident = (a.get("provider") or "").lower(), escape(str(a.get("id") or ""), quote=True)
    if not ident:
        return ""
    if provider == "plausible":
        return f'<script defer data-domain="{ident}" src="https://plausible.io/js/script.outbound-links.js"></script>'
    if provider == "goatcounter":
        return (f'<script data-goatcounter="https://{ident}.goatcounter.com/count" async '
                f'src="https://gc.zgo.at/count.js"></script>')
    return ""


FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Ccircle cx='16' "
           "cy='16' r='14' fill='%230F766E'/%3E%3Ccircle cx='16' cy='16' r='8' fill='none' stroke='%23fff' "
           "stroke-width='2.5'/%3E%3Ccircle cx='16' cy='16' r='2.5' fill='%23fff'/%3E%3C/svg%3E")
OG_LOCALE = {"en": "en_GB", "fi": "fi_FI", "sv": "sv_SE", "no": "nb_NO"}


def head_tags(cfg: dict, base: str, path: str, title: str, desc: str, lang: str = "en") -> str:
    url = base + path
    e = lambda s: escape(s, quote=True)
    return "\n".join([
        f'<link rel="canonical" href="{e(url)}">',
        f'<link rel="icon" href="{FAVICON}">',
        f'<meta property="og:type" content="website">',
        f'<meta property="og:site_name" content="Learning Radar">',
        f'<meta property="og:title" content="{e(title)}">',
        f'<meta property="og:description" content="{e(desc)}">',
        f'<meta property="og:url" content="{e(url)}">',
        f'<meta property="og:image" content="{e(base)}assets/og.png">',
        f'<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">',
        f'<meta property="og:locale" content="{OG_LOCALE.get(lang, "en_GB")}">',
        f'<meta name="twitter:card" content="summary_large_image">',
        analytics_tag(cfg),
    ]).strip()


def page_shell(cfg, base, path, lang, title, desc, body, up) -> str:
    t = T[lang]
    e = escape
    return f"""<!doctype html>
<html lang="{"nb" if lang == "no" else lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)} | Learning Radar</title>
<meta name="description" content="{e(desc, quote=True)}">
{head_tags(cfg, base, path, title, desc, lang)}
<link rel="stylesheet" href="{up}assets/page.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site"><div class="wrap">
  <a class="brand" href="{up}">Learning Radar</a>
  <nav aria-label="Site"><a href="{up}">{e(t["home"])}</a><a href="{up}about/">{e(t["about"])}</a></nav>
</div></header>
<main id="main" class="wrap">
{body}
</main>
<footer class="site"><div class="wrap">
  <p>{e(t["disclaimer"])}</p>
  <p><a href="{up}about/">{e(t["about"])}</a> · <a href="{up}privacy/">{e(t["privacy"])}</a> ·
     <a href="{REPO}/issues/new?template=wrong-info.yml">{e(t["report"])}</a> ·
     <a href="https://barmo.fi/?utm_source=learning-radar&amp;utm_medium=footer">{e(t["credit"])}</a></p>
</div></footer>
</body>
</html>
"""


def item(o: dict, lang: str) -> str:
    t, e = T[lang], escape
    place = [o.get("city", ""), t["countries"].get(o.get("country", ""), o.get("country", ""))]
    place = ", ".join(p for p in place if p)
    if o.get("online"):
        place = f'{t["online"]}{" / " + place if place else ""}'
    bits = [t["costs"].get(o.get("cost", ""), ""), t["kinds"].get(o.get("kind", ""), ""),
            f'{o["credits"]:g} ECTS' if o.get("credits") else "",
            t["deadline"].format(d=fmt_date(o["deadline"], lang)) if o.get("deadline") else ""]
    url = o.get("url", "")
    url = url if re.match(r"^https?://", url) else "#"
    who = " · ".join(x for x in (o.get("provider", ""), place) if x)
    return (f'<li><a href="{e(url, quote=True)}" rel="noopener">{e(o["title"])}</a>'
            f'<span class="who">{e(who)}</span>'
            f'<span class="meta">{e(" · ".join(b for b in bits if b))}</span></li>')


def landing(cfg, base, data, page, others) -> str:
    lang, slug, flt, title, desc, intro = page
    t, e = T[lang], escape
    xs = select(data["offers"], flt)
    updated = fmt_date(data.get("date") or data["generated_at"][:10], lang)
    links = "".join(f'<li><a href="../../{p[0]}/{p[1]}/">{e(p[3])}</a></li>' for p in others if p[1] != slug)
    body = f"""<h1>{e(title)}</h1>
<p class="lede">{e(intro)}</p>
<p class="count"><b>{e(t["count"].format(n=f"{len(xs):,}".replace(",", " ")))}</b> · {e(t["updated"].format(d=updated))}</p>
<p><a class="cta" href="../../#{e(to_hash(flt), quote=True)}">{e(t["open"].format(n=f"{len(xs):,}".replace(",", " ")))} →</a></p>
<h2>{e(t["top"].format(k=min(TOP, len(xs))))}</h2>
<ol class="list">{"".join(item(o, lang) for o in xs[:TOP])}</ol>
<h2>{e(t["other"])}</h2>
<ul class="others">{links}</ul>"""
    return page_shell(cfg, base, f"{lang}/{slug}/", lang, title, desc, body, "../../")


def about(cfg, base, data) -> str:
    sc = cfg.get("scoring") or {}
    pct = lambda k: f"{round(float(sc.get(k, 0)) * 100)}%"
    site = cfg.get("site") or {}
    mail = escape(site.get("contact_email", ""), quote=True)
    sources = "".join(f"<li>{s}</li>" for s in [
        '<b>Opintopolku (Studyinfo.fi)</b>, the Finnish National Agency for Education\'s national study portal: '
        'degrees, vocational qualifications, continuing education, open university and Jotpa-funded training in '
        'Finland. <a href="https://opintopolku.fi/">opintopolku.fi</a>',
        '<b>Skolverket, Susa-navet</b>, the Swedish national register of education: university courses and '
        'programmes, higher vocational education, labour market training and folk high schools. '
        '<a href="https://www.skolverket.se/om-oss/var-verksamhet/skolverkets-e-tjanster/susa-navet">skolverket.se</a>',
        '<b>Utdanning.no</b>: higher education programmes in Norway\'s national admission and vocational college '
        '(fagskole) programmes. Contains data under the Norwegian licence for Open Government data (NLOD) made '
        'available by Utdanning.no. <a href="https://data.norge.no/nlod/en/2.0">NLOD 2.0</a>',
        '<b>MOOC.fi</b> (University of Helsinki), <b>FutureLearn</b>, <b>Coursera</b> and <b>Microsoft Learn</b>: '
        'course titles, descriptions and links from their public catalogues.',
    ])
    body = f"""<h1>About Learning Radar</h1>
<p class="lede">Learning Radar collects courses, training, vocational qualifications and degrees in Finland, Sweden,
Norway and online from public sources, three times a week, and ranks them by what they can do for your career.
It is free, has no ads and needs no account. It is built and run by <a href="https://barmo.fi/?utm_source=learning-radar&amp;utm_medium=about">Barmo</a>,
a small software studio in Vantaa, Finland.</p>

<h2 id="disclaimer">Check before you apply</h2>
<p>Learning Radar is an independent service. It is not affiliated with, or endorsed by, the Finnish National Agency
for Education (Opetushallitus), Skolverket, Utdanning.no or any course provider. Costs, dates, languages and
eligibility come from each provider's own listing and are read automatically, so they can be out of date or
wrong. Always check the course page, and for benefits your employment office, Kela, CSN or Lånekassen, before you
apply. Nothing here is advice about your own situation.</p>

<h2 id="score">How the score works</h2>
<p>Each offer gets a score from 0 to 100. It is a ranking aid, not a judgement of quality.</p>
<ul>
<li><b>What you walk away with ({pct("credential")})</b>: a degree or qualification counts most, then a certification, then university credits.</li>
<li><b>What it costs ({pct("cost")})</b>: free and publicly funded first, then free to learn with a paid certificate, then paid.</li>
<li><b>Field ({pct("field")})</b>: fields where employers are looking for people, such as software, data, cybersecurity, health care, energy and engineering, score higher.</li>
<li><b>Timing ({pct("timing")})</b>: an application deadline in the next three months, or a course you can start any time.</li>
<li><b>Fits around a job ({pct("flexibility")})</b>: online, self-paced, part-time, evenings or weekends.</li>
</ul>
<p>Offers first seen in the last {int(cfg.get("new_days", 7))} days and offers whose deadline is in the next
{int(cfg.get("closing_days", 21))} days get a few extra points ({sc.get("new_bonus", 4):g} and
{sc.get("closing_bonus", 4):g}). Offers under {cfg.get("min_score", 30):g} are not shown. The reasons under each course show what counted.</p>

<h2 id="sources">Sources and licences</h2>
<ul>{sources}</ul>
<p>Course names, descriptions and trademarks belong to their owners. Every course links to the provider's own page.
If you run one of these services or offer a course and want something changed or removed, please
<a href="mailto:{mail}">email us</a>.</p>

<h2 id="report">Report an error</h2>
<p>Found a wrong price, date or language? <a href="{REPO}/issues/new?template=wrong-info.yml">Report it on GitHub</a>
(needs a free GitHub account) or <a href="mailto:{mail}?subject=Learning%20Radar%3A%20wrong%20information">email us</a>.
Each course also has its own report link in the radar.</p>

<h2 id="accessibility">Accessibility</h2>
<p>We aim to meet WCAG 2.1 level AA. The radar works with a keyboard and screen readers, follows your system's
light or dark setting, and the lists on this site work without JavaScript. Known limits: course descriptions
come from providers and may be in Finnish, Swedish or Norwegian only. If something does not work for you,
please <a href="mailto:{mail}?subject=Learning%20Radar%3A%20accessibility">tell us</a> and we will fix it.</p>

<h2 id="code">Open source</h2>
<p>The code is open source under the MIT licence: <a href="{REPO}">github.com/girimohan/learning-radar</a>.</p>

<h2 id="organisations">For schools and organisations</h2>
<p>Want a course finder like this for your own courses, students or clients, in your own colours and languages?
<a href="https://barmo.fi/?utm_source=learning-radar&amp;utm_medium=about-org">Barmo builds them</a>.</p>"""
    return page_shell(cfg, base, "about/", "en", "About, sources and how the score works",
                      "What Learning Radar is, where its data comes from, how the score works, and how to report "
                      "an error.", body, "../")


def privacy(cfg, base) -> str:
    site = cfg.get("site") or {}
    mail = escape(site.get("contact_email", ""), quote=True)
    a = site.get("analytics") or {}
    provider = (a.get("provider") or "").lower() if a.get("id") else ""
    stats = {
        "plausible": 'We count visits with <a href="https://plausible.io/data-policy">Plausible Analytics</a>, an EU-hosted '
                     'service that uses no cookies and stores no personal data or IP addresses. We see only totals, '
                     'such as how many people visited a page and which course pages they opened.',
        "goatcounter": 'We count visits with <a href="https://www.goatcounter.com/help/privacy">GoatCounter</a>, which '
                       'uses no cookies and stores no personal data or IP addresses. We see only totals, such as how '
                       'many people visited a page.',
    }.get(provider, "We do not use any analytics or visitor tracking.")
    body = f"""<h1>Privacy</h1>
<p class="lede">Learning Radar has no accounts, no ads and no cookies. This notice explains the little that is processed.</p>
<h2>Who is responsible</h2>
<p>Barmo (Business ID {escape(site.get("business_id", ""))}), Vantaa, Finland. Contact: <a href="mailto:{mail}">{mail}</a>.</p>
<h2>Your study plan</h2>
<p>Courses you add to "My plan" are saved in your own browser (local storage). They never leave your device and we
cannot see them. Clearing your browser data, or "Clear all" in the plan, deletes them.</p>
<h2>Visitor statistics</h2>
<p>{stats}</p>
<h2>Hosting</h2>
<p>The site is hosted on GitHub Pages. GitHub receives your IP address and browser details when you load a page,
to deliver it and keep the service secure; see <a href="https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement">GitHub's privacy statement</a>.
The site loads no fonts, scripts or images from other services{", apart from the statistics script above" if provider else ""}.</p>
<h2>When you contact us</h2>
<p>If you email us or report an error, we use your message and address only to answer and fix the problem, and
delete them when they are no longer needed. Reports on GitHub are public and covered by GitHub's terms.</p>
<h2>Your rights</h2>
<p>You can ask what data we hold about you, and have it corrected or deleted, by emailing us. You can also
complain to the Data Protection Ombudsman in Finland: <a href="https://tietosuoja.fi/en">tietosuoja.fi</a>.</p>"""
    return page_shell(cfg, base, "privacy/", "en", "Privacy", "How Learning Radar handles your data: no accounts, "
                      "no cookies, and your study plan stays in your browser.", body, "../")


# ---- the dashboard's own page ----

def stamp(html: str, name: str, content: str) -> str:
    """Replace what is between <!-- site:name --> and <!-- /site:name --> (markers kept, so it can run again)."""
    pat = re.compile(rf"(<!-- site:{name} -->)(.*?)(<!-- /site:{name} -->)", re.S)
    if not pat.search(html):
        raise ValueError(f"marker site:{name} missing")
    return pat.sub(lambda m: f"{m.group(1)}\n{content}\n{m.group(3)}", html, count=1)


def build(cfg: dict, docs: Path, data: dict | None = None) -> list[str]:
    """Write every static page. Returns the paths written, relative to docs/."""
    data = data or json.loads((docs / "courses.json").read_text(encoding="utf-8"))
    base = site_url(cfg, docs)
    written = []

    def write(rel: str, text: str):
        p = docs / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        written.append(rel)

    live = [p for p in PAGES if len(select(data["offers"], p[2])) >= MIN_OFFERS]
    for p in PAGES:
        rel = f"{p[0]}/{p[1]}/index.html"
        if p in live:
            write(rel, landing(cfg, base, data, p, live))
        elif (docs / rel).exists():
            (docs / rel).unlink()
    write("about/index.html", about(cfg, base, data))
    write("privacy/index.html", privacy(cfg, base))

    idx = docs / "index.html"
    html = idx.read_text(encoding="utf-8")
    title = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
    desc = re.search(r'<meta name="description" content="([^"]*)"', html).group(1)
    from html import unescape
    html = stamp(html, "head", head_tags(cfg, base, "", unescape(title), unescape(desc)))
    groups = {"fi": "Suomeksi", "en": "In English", "sv": "På svenska", "no": "På norsk"}
    lists = "\n".join(
        f'<p lang="{"nb" if g == "no" else g}"><b>{groups[g]}:</b> ' + " · ".join(f'<a href="{p[0]}/{p[1]}/">{escape(p[3])}</a>' for p in live if p[0] == g) + "</p>"
        for g in groups if any(p[0] == g for p in live))
    html = stamp(html, "links", lists)
    idx.write_text(html, encoding="utf-8", newline="\n")
    written.append("index.html")

    day = (data.get("date") or data["generated_at"][:10])
    urls = [""] + [f"{p[0]}/{p[1]}/" for p in live] + ["about/", "privacy/"]
    sm = "".join(f"<url><loc>{escape(base + u)}</loc><lastmod>{day}</lastmod></url>\n" for u in urls)
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n'
                         f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{sm}</urlset>\n')
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {base}sitemap.xml\n")
    return written
