# Learning Radar

Finds courses, professional training, vocational qualifications and degrees that can lift a career, in
Finland, Sweden, Norway, Germany and online, and ranks them so the free, recognised and open-now options come first. Built on
the same pattern as [remote-job-radar](https://github.com/girimohan/remote-job-radar) and
[viral-news-radar](https://github.com/girimohan/viral-news-radar).

It is for anyone who wants to **upskill in their job**, **change career**, **get a degree**, or simply
**learn something new**, whether they can pay or need it free.

## What you get

| | |
|---|---|
| **Dashboard** | `docs/index.html`, served by GitHub Pages. Pick a goal, then filter by place (all Nordic countries, Finland, Sweden, Norway, Germany, online), cost (free or funded, free to learn, paid), type, field, language and level, or show only Jotpa-funded training, training for jobseekers, higher vocational education (YH, fagskole), folk high schools, part-time study, open university, micro-credentials, evening courses, new offers or close deadlines. Every card says why it ranked where it did and links to the provider's own page. **My plan** keeps a shortlist in the browser, soonest deadline first. Filtered views are in the URL, so you can share them. |
| **Weekly digest** | Every Monday a GitHub issue (which GitHub emails to you) lists what is new this week, deadlines in the next three weeks, free training in Finland with applications open now, free vocational training in Sweden and Norway, and degrees taught in English with no tuition. Also saved in `digests/latest.md`. |
| **Data** | `docs/courses.json` holds the current offers. `data/seen.json` remembers when each offer was first seen, so the radar can say what is new. |

## Where the data comes from

| Source | What | How |
|---|---|---|
| **Opintopolku** (Studyinfo.fi) | Every Finnish education offer with an application open now or opening within 30 days: university and UAS degrees, open university courses, continuing education, specialisation training, vocational qualifications, Jotpa-funded training, labour market training, folk high schools. | Public konfo-backend API, about 75 requests per run with a 3-second pause between each (about five minutes). |
| **Skolverket Susa-navet** (Sweden) | Swedish university courses and programmes still open for application (with deadlines and non-EU tuition), higher vocational education (YH, free), labour market training from Arbetsförmedlingen, and folk high schools. | Skolverket's open API, about 25 requests. University runs are read when added or updated in the last 60 days (`hs_days`). |
| **Utdanning.no** (Norway) | About 1,400 bachelor's, master's and one-year programmes in the national admission (Samordna opptak), and about 700 vocational college (fagskole) programmes. | Public api.utdanning.no, about 15 requests. |
| **DAAD** | About 2,500 international programmes in Germany: bachelor's, master's, doctoral, language courses and summer schools, with tuition and deadlines. | The JSON search behind daad.de's programme finder, 6 requests. |
| **FutureLearn** | About 1,800 online courses from UK and European universities, with access model and ratings. | Its public courses feed, 1 request. |
| **Coursera** | Specialisations and Professional Certificates (multi-course programmes aimed at a job role). | Public catalog API, about 10 requests. |
| **Microsoft Learn** | Certifications, free Applied Skills credentials and the most popular free learning paths. | Documented Catalog API, 1 request. |
| **MOOC.fi** | The University of Helsinki's free online courses (Elements of AI, programming, cyber security...). | Its GraphQL API, 1 request. |

## How it works

```
collect  ->  drop noise and duplicates  ->  match fields  ->  work out goals  ->  new / deadline soon  ->  score  ->  dashboard + digest
```

1. **Collect** (`learnradar/sources/`). The eight sources run side by side. Opintopolku needs two kinds of
   request: a listing of offers, and one filtered query per tag (free, paid, tuition fee, Jotpa, labour market
   training, continuing education, micro-credential, open university, teaching language, online,
   evening or weekend). The listing endpoint silently ignores some filters (fees, teaching time, "opens within
   30 days"), so tags use the search endpoint, the listing is only used when its count agrees with the
   search endpoint's, and a tag whose filter comes back unapplied is dropped and reported rather than stuck
   on every offer.
2. **Fields** (`learnradar/classify.py`). Each offer is matched to the fields in `config.yaml` (Software & IT,
   Data & AI, Health & social care, Green transition...). A keyword in the title or the provider's own
   subject labels is enough; the description alone needs two different keywords of the same field. Finnish
   keywords end in `*` to catch inflections (`ohjelmoi*` matches *ohjelmointi*, *ohjelmoinnin*).
3. **Goals.** Degrees serve *get a degree*; qualifications, labour market training, long training
   programmes and professional certificates serve *change career*; courses, certifications, continuing
   education and micro-credentials serve *upskill*; free online and open university courses serve *learn*.
4. **Score, 0-100** (`learnradar/scoring.py`). A weighted sum of what you walk away with (degree,
   qualification, certification, credits), what it costs, the field's weight, whether you can apply or start
   now (or how close the deadline is), and whether it fits around a job (online, self-paced, evenings). New
   offers and deadlines within three weeks get a few extra points. The reasons are shown on every card.
5. **Cap.** The best offers of each source are kept, up to the caps in `config.yaml` (13,000 in all), so the
   page stays quick.

## Set up (once)

1. **Create the repository** `learning-radar` on GitHub and push this folder to it (commands below).
2. **Run it:** Actions tab -> *Learning radar* -> *Run workflow*. It takes about five to eight minutes. After that it
   runs by itself on Monday, Wednesday and Friday mornings and sends the digest on Mondays.
3. **Turn on the dashboard:** Settings -> Pages -> *Deploy from a branch* -> branch `main`, folder `/docs`.
   It appears at `https://<your-user>.github.io/learning-radar/`.
4. **Get the digest by email:** Watch -> All activity on the repository.

```bash
cd learning-radar
git init && git add . && git commit -m "Learning radar"
git branch -M main
git remote add origin https://github.com/<your-user>/learning-radar.git
git push -u origin main
```

The repository already contains a first run's data, so the dashboard works as soon as Pages is on.
No secrets or API keys are needed.

## Change what it looks for

Everything is in `config.yaml`:

- `topics`: fields, their keywords and a weight. Raise the weight of fields you want to promote (for example
  ones with many open jobs in your region).
- `scoring`: how much credential, cost, field, timing and flexibility count, and the bonuses.
- `min_score`, `max_items` and each source's `max_items`: how long the list is.
- `sources`: turn sources on or off. `opintopolku.skip_types` leaves out school-age offers (general upper
  secondary, basic art education). `coursera.include_courses` adds Coursera's ~26,000 single courses (a much
  bigger page). `mslearn.learning_paths` sets how many learning paths to keep.
- `exclude_title`: title words that drop an offer.

## Run locally

```bash
pip install -r requirements-dev.txt
python -m pytest -q
python -m learnradar run                          # full run, about five minutes
python -m learnradar run --sources sweden,norway  # quick partial run
python -m http.server -d docs                     # dashboard at http://localhost:8000
```

## Limits

- Opintopolku lists offers whose application is open or opens within 30 days, not those that closed
  yesterday or open in six months. Its listing has no deadline dates, so Finnish offers are not in "closing
  soon"; DAAD and FutureLearn give dates.
- Opintopolku lists a programme once even when many schools run it (a Bachelor of Engineering in IT can have
  19 versions). Tags such as Jotpa-funded, labour market training, taught in English or online then mean "at
  least one version is", and the card says "19 versions; some are Jotpa-funded" rather than calling the whole
  programme funded. Open the course page to see each school's version.
- Finnish degrees with no fee information are shown as free (free by law when taught in Finnish or Swedish;
  English-taught ones charge non-EU/EEA students). Costs elsewhere are what the provider's listing says.
  "Free" degrees in Germany still have a semester contribution; Jotpa training can have a small fee. Always
  check the course page.
- Countries with a national database read here: Finland, Sweden, Norway and Germany. **Denmark and Iceland
  are not included yet**: no open API for their national course catalogues was found (Danish and Icelandic
  universities do appear among the online courses). The rest of Europe is covered through online courses. Adding a country means
  adding one file in `learnradar/sources/`.
- Sweden: only university runs added or updated in the last 60 days are read (there are about 64,000 in
  all), so a course published earlier and never updated can be missing. Raise `sweden.hs_days` to read more.
- Norway: Utdanning.no gives no deadlines (most programmes close in Samordna opptak in the spring). State
  institutions are marked free for EU/EEA citizens; private ones and vocational colleges are "cost not stated".
  Programmes are assumed to be taught in Norwegian.
- Studyportals, edX and Class Central are not used: none has an open public API to read from.

## Good citizenship

Only public, documented or openly served data. The collector identifies itself, runs three times a week,
waits between requests to Opintopolku and backs off when rate-limited. Every offer links to the provider's own
page; the dashboard shows titles and short descriptions only.
