# Plan: council websites, digital services and compliance

Status: proposal, not started. Written November 2026.

## Why

The "Website" area of a council page has one measure: the Silktide accessibility
score. Residents judge a council by how easy it is to do things online, and
much of what a council is legally obliged to publish lives on its website. This
plan adds measures for three questions:

1. **Can I do it online?** Whether a council's core services have a working
   online page, and how many of its service links are broken.
2. **Does it follow the rules?** Accessibility statement, transparency data,
   planning data, contract notices, cookies.
3. **Is it run safely?** Email and web security basics.

## Principles

- **Published sources first.** The site uses official published statistics.
  Phases 1 and 2 use only data someone else publishes. Phase 3 adds checks we
  run ourselves, and those are labelled as such everywhere they appear.
- **Same shape as every other source.** One module per source in
  `pipeline/sources/`, returning a `Result`, saved to `data/sources/<id>.json`,
  run by the Monday workflow, with checks in `tests/test_data.py`.
- **Explainable in one sentence.** Each measure gets a label anyone could
  understand and a line on the methodology page saying exactly how it is
  worked out. Anything that can't be explained like that is left out.
- **Fair to councils.** Check the same pages in the same way for every
  council, record when, and keep the evidence (URL, status, the text matched)
  so any council that disputes a result can see why.
- **Polite.** One request a second for each site, our existing user agent, and
  never anything that needs a login or submits a form.

## Measures

`better` is the direction used for ranking. "Check" means a pass/fail result
rather than a number to rank. Checks are shown differently (see Presentation).

### Phase 1: published sources

| id | Label | Kind | Source |
|---|---|---|---|
| `online_services` | Core services with a page on the council's website | %, higher | Local Links Manager |
| `broken_links` | Council service links GOV.UK found broken | %, lower | Local Links Manager |
| `planning_data` | Required planning datasets the council provides | %, higher | Planning Data platform |
| `foi_late` | Freedom of information requests answered late | %, lower | WhatDoTheyKnow |

**Local Links Manager** (GOV.UK). GOV.UK's "find your local council" service
pages link to each council's page for each standard service (LGSL code, with
interaction type: apply, pay, report, find out). Local Links Manager holds
these links and regularly checks them. From it:

- `online_services`: of a fixed list of about 20 core services that every
  single-tier council provides (pay council tax, bin collection day, report a
  missed bin, report fly-tipping, apply for a parking permit, apply for a
  school place, report a pothole, apply for housing, register a birth, and so
  on), the share with a link that works.
- `broken_links`: of all the council's links in Local Links Manager, the
  share GOV.UK's checker marks as broken.
- `extra.homepage`: the council's homepage. Phase 3 needs it, and nothing
  else gives us an official list.
- `extra.links`: the service URLs, for the task checks in phase 3.

The fixed service list goes in the module with the LGSL codes, so it is easy
to review. Only services every single-tier council in England provides are
included, so councils aren't penalised for services they don't run.

**Planning Data platform** (planning.data.gov.uk, MHCLG). Tracks which
planning authorities provide the datasets they are required to (brownfield
land, conservation areas, Article 4 directions, tree preservation orders,
listed building outlines and others) and how good that data is.
`planning_data` is the share of the required datasets the council provides.
The list of datasets comes from the platform rather than being typed out, so
it follows any change in the requirements. Check how the platform deals with
national parks and development corporations, which take planning powers in
part of some councils.

**WhatDoTheyKnow** (mySociety). Holds the public FOI requests sent through it
to each council, with their status. `foi_late` is the share answered after the
legal 20 working days, over the last two full years, for councils with at
least 50 requests in that time. It isn't official and only covers requests
made through WhatDoTheyKnow, which the label and methodology must say. It is
included because it is the only consistent, public view of FOI performance
across every council. If mySociety's terms or rate limits rule out a weekly
fetch, fetch it monthly (`MAX_AGE_DAYS = 30`, as `lgo_decisions` does).

### Phase 2: more published sources

| id | Label | Kind | Source |
|---|---|---|---|
| `contracts_published` | Contracts awarded with a published notice within 30 days | %, higher | Find a Tender (OCDS) |
| `accounts_audited` | Latest accounts audited by the deadline | check | MHCLG / PSAA |
| `ico_action` | ICO enforcement or reprimand in the last three years | check | ICO |
| `local_digital` | Has signed the Local Digital Declaration | check | MHCLG Local Digital |

These need more care in matching and explaining, so they come after phase 1
has shipped. `contracts_published` needs a careful definition: Find a Tender
replaced Contracts Finder under the Procurement Act 2023 (from February 2025),
so the measure should only start from then. `ico_action` and the accounts
deadline are rare events, so they are shown as a flag on the council's page
rather than ranked.

### Phase 3: our own checks

One new source, `website`, which visits each council's site. These are labelled
"Our checks" on the site, not published statistics.

| id | Label | Kind | How |
|---|---|---|---|
| `a11y_statement` | Has an accessibility statement reviewed in the last year | check | Find the statement (footer link, then `/accessibility`), read its status and "last reviewed" date |
| `a11y_status` | What the accessibility statement says | text | "fully", "partially" or "not compliant", from the GDS template wording |
| `spend_data_age` | Months since the newest published spending over £500 | number, lower | Find the transparency page, find the newest spending file by its name and date |
| `trackers_before_consent` | Tracking cookies set before you agree to them | check | Load the homepage in Playwright with no interaction, and list the third-party cookies and requests to known trackers |
| `reject_cookies` | Can reject cookies as easily as accept them | check | A reject button on the first layer of the banner |
| `dmarc` | Email protected against spoofing (DMARC set to quarantine or reject) | check | DNS TXT lookup of `_dmarc.<domain>` |
| `https` | Website uses HTTPS everywhere (HSTS) | check | `Strict-Transport-Security` header on the homepage |
| `security_txt` | Says how to report a security problem | check | `/.well-known/security.txt` |
| `online_tasks` | Top tasks you can complete online | %, higher | For the 10 top tasks, whether the page from Local Links Manager leads to an online form or payment rather than only a phone number or PDF |

What we also record, but don't rank: the CMS, the forms platform and the
payments provider, detected from the HTML, shown as background on the council's
page ("This council's website runs on…").

`online_tasks` is the hardest to make fair, so it goes last within phase 3.
Before it ships, check a sample of 20 councils by hand and agree the rules.

## Pipeline changes

- `pipeline/sources/local_links.py`, `planning_data.py`, `foi.py`
  (phase 1); `contracts.py`, `accounts.py`, `ico.py`, `local_digital.py`
  (phase 2); `website.py` (phase 3). Each added to `STEPS`, and those with
  measures to `VALUE_SOURCES`, in `pipeline/update.py`.
- `website.py` needs the homepage from `local_links`, so it runs after it and
  reads `context["results"]["local_links"]`.
- Checks are stored as `True`/`False` in `values`, with the evidence in
  `extra[code][measure]` (URL checked, date, what was found), so a council's
  page can show why and the data stays auditable.
- New dependencies: `dnspython` for DMARC lookups. Playwright is only needed by
  `website.py`; install it in the workflow with
  `pip install playwright && playwright install chromium`.
- `website.py` takes about 130 councils × ~15 requests at one a second, which
  is roughly 35 minutes. Give it `MAX_AGE_DAYS = 28` so it runs monthly rather
  than every week, and raise the workflow's `timeout-minutes` to 90.
- Councils named rather than coded (WhatDoTheyKnow, Local Digital) are matched
  through `pipeline/names.py`; add aliases there as needed.

## Site changes

- `web/model.py`: new `Measure`s in the `digital` area. Rename the area from
  "Website" to "Online services and openness" (wording to decide), and rewrite
  its description to cover the new measures.
- Measures support a `kind` of `"check"`. Checks aren't ranked: the council's
  page shows a tick or cross with a short reason, and the measure page shows
  how many councils pass, with a list of those that don't.
- A small "Our checks" tag on every measure from `website.py`, linking to the
  methodology section.
- `web/templates/about.html`: a methodology section for each new source, and
  credits (WhatDoTheyKnow, Find a Tender, ICO) in the footer next to Silktide.
- Scotland: Local Links Manager and Planning Data cover England only. Phase 3
  checks work for Scottish councils too, so give those measures
  `nations=("England", "Scotland")`.

## Tests

- `tests/test_pipeline.py`: a parser test for each new source against a small
  saved response in `tests/fixtures/`, as for the existing sources.
- `tests/test_data.py`: each new measure covers most councils
  (the existing `test_each_measure_covers_most_councils`); percentages are
  0–100; checks are booleans; every check has its evidence; `spend_data_age`
  is between 0 and 120.
- `tests/test_model.py`: check measures are never ranked, and render on the
  council page and the measure page.

## Order of work

Each step is one pull request that can be merged on its own.

1. `local_links` source and the two measures. Methodology text.
2. Support for check measures in `web/model.py` and the templates (no new
   data yet; tested with the fixture).
3. `planning_data` source.
4. `foi` source.
5. `website` source, part one: DMARC, HTTPS, security.txt, accessibility
   statement. No browser needed.
6. `website` source, part two: Playwright cookie checks and the transparency
   spending check.
7. Phase 2 sources, one pull request each.
8. `online_tasks`, after the hand check of 20 councils.

## Risks

- **Endpoints and terms not yet checked.** This plan was written in an
  environment without access to the sources, so the exact API routes, fields
  and terms of use for Local Links Manager, Planning Data, WhatDoTheyKnow and
  Find a Tender need confirming before each step starts. If one can't be used,
  drop its measure rather than scraping around a restriction.
- **Bot protection.** Some council sites sit behind Cloudflare or similar and
  may block the checker. Record "couldn't check" rather than a fail, and list
  those councils in the update summary.
- **False fails.** Statements and spending files live in different places on
  each site. Each fail keeps its evidence and URL, and the first full run is
  reviewed by hand before it is published.
- **Councils disputing results.** Add a "Think this is wrong?" link on check
  measures, pointing to an email address or a GitHub issue template.
- **Measures that reward box-ticking.** Prefer measures residents would notice
  (services online, links that work, FOI answered on time) over ones that only
  test paperwork, and keep check measures out of any overall ranking.

## Decisions needed

1. Are you happy to publish our own checks (phase 3) alongside official
   statistics, labelled "Our checks"? If not, stop after phase 2.
2. Is WhatDoTheyKnow acceptable as a source, given it isn't official?
3. What should the area be called once it covers more than the website?
4. Should check measures appear in the "how this council compares" summary
   at the top of the council page, or only in the area itself?
