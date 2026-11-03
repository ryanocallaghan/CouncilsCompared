# Plan: council websites, digital services and compliance

Status: proposal, not started. Written 2 November 2026; sources checked 3
November 2026 (see "What the sources hold").

## Why

The "Website" area of a council page has one measure: the Silktide accessibility
score. Residents judge a council by how easy it is to do things online, and
much of what a council is legally obliged to publish lives on its website. This
plan adds measures for three questions:

1. **Can I do it online?** Whether the links GOV.UK gives to a council's core
   services work.
2. **Does it follow the rules?** Planning data, the brownfield land register,
   contract notices, the accessibility statement, transparency data, cookies.
3. **Is it run safely?** Email and web security basics.

## Principles

- **Published sources first.** The site uses official published statistics.
  Phases 1 and 2 use only data someone else publishes. Phase 3 adds checks we
  run ourselves (agreed 3 November 2026), and those are labelled as such
  everywhere they appear.
- **Same shape as every other source.** One module per source in
  `pipeline/sources/`, returning a `Result`, saved to `data/sources/<id>.json`,
  run by the Monday workflow, with checks in `tests/test_data.py`.
- **Explainable in one sentence.** Each measure gets a label anyone could
  understand and a line on the methodology page saying exactly how it is
  worked out. Anything that can't be explained like that is left out.
- **Fair to councils.** Check the same things in the same way for every
  council, record when, and keep the evidence (URL, status, the text matched)
  so any council that disputes a result can see why.
- **Polite.** Our existing user agent, a pause between requests, and never
  anything that needs a login, submits a form or gets past a bot challenge.

## What the sources hold

Checked by hand on 3 November 2026.

**Local Links Manager (GOV.UK)** works, with no key.

- `https://local-links-manager.publishing.service.gov.uk/data/links_to_services_provided_by_local_authorities.csv`
  (7.6 MB): one row per council and service, with columns `Authority Name`,
  `GSS`, `Description`, `LGSL`, `LGIL`, `URL`, `Title`, `Supported by GOV.UK`.
  It covers 385 councils in England, Scotland and Wales. Rows have the **GSS
  code**, so no name matching is needed. A single-tier council has about 176
  links (median). It does **not** include the link checker's result.
- `/api/link?authority_slug=<slug>&lgsl=<code>` gives one link with its
  `status` (`ok`, `caution` or `broken`, as seen so far). For example, Leeds's
  "check your bin day" link is `broken` and Croydon's missed-bin link is
  `caution`. Services the council has no link for come back empty.
- `/api/local-authority?authority_slug=<slug>` gives `homepage_url`, `gss`,
  `tier` and `country_name`. It needs the slug, not the GSS code.
- There is no bulk export of link statuses: guessed paths for one return 403.

**Planning Data (MHCLG)** works, with no key. The performance database on
`datasette.planning.data.gov.uk` has a `provision_summary` table, one row per
organisation and dataset, with `provision_reason` (statutory, expected,
encouraged and so on), `active_endpoint_count` and `error_endpoint_count`.
`/performance/provision_summary.csv?_stream=on&_size=max` downloads all 8,185
rows. Organisations map to GSS codes through `www.planning.data.gov.uk/organisation.json`
(`statistical-geography`).

- Eight datasets are "expected" from 102 single-tier councils: trees, tree
  preservation orders and zones, Article 4 directions and their areas,
  conservation areas and their documents, and listed building outlines. The
  share of them each council provides ranges widely, from 0% at the 20th
  percentile to 100% at the 80th, so it is a good measure.
- The brownfield land register is statutory for 134 councils, and 118 provide
  it. The newer plan datasets (local plan, timetable and others) are
  statutory, but few councils provide them yet, so they are left out for now.

**Find a Tender** and **Contracts Finder** both answer their OCDS APIs with no
key (`/api/1.0/ocdsReleasePackages`, `/Published/Notices/OCDS/Search`).

**WhatDoTheyKnow** returns a Cloudflare "Just a moment..." challenge to
scripts, for its pages and its JSON. That rules out fetching it. If FOI
timeliness is wanted, ask mySociety for a data extract or permission. It is
taken out of phase 1.

**DMARC** records vary as hoped. In a sample of five councils, Hackney is
`p=reject`; Leeds `p=quarantine; sp=reject`; Cornwall `p=quarantine; pct=75`;
Croydon's is a CNAME to a DMARC provider. Most councils send reports to NCSC's
Mail Check service (`dmarc-rua@dmarc.service.gov.uk`).

## Measures

`better` is the direction used for ranking. "Check" means a pass/fail result
rather than a number to rank. Checks are shown differently (see Site changes).

### Phase 1: published sources

| id | Label | Kind | Source | Nations |
|---|---|---|---|---|
| `links_working` | Links to the council's core services that work | %, higher | Local Links Manager | England, Scotland (Wales when it launches) |
| `planning_data` | Planning datasets the council provides | %, higher | Planning Data | England |
| `brownfield` | Publishes its brownfield land register as data | check | Planning Data | England |

**`links_working`.** A fixed list of about 20 services that almost every
single-tier council has a link for. From the CSV, the most common ones are
school term dates, fostering, applying for council housing, free school meals,
primary and secondary school places, council tax (paying, discounts, the annual
bill), business rate relief, housing benefit, mutual exchange, and bins.
Coverage alone doesn't separate councils: nearly all have a link for each. What
does is whether the link **works**. So the measure is the share of those links
whose status is `ok`. `caution` is counted as not working; to be confirmed once
we know what the checker means by it.

- The CSV gives the URL and LGSL code for each council's links. The `/api/link`
  call gives the status: about 20 calls per council, about 2,600 in all. At one
  a second that takes 45 minutes, so this source runs monthly
  (`MAX_AGE_DAYS = 28`, as `lgo_decisions` does).
- The slug for each council comes from the GOV.UK API, once, and is kept in
  `extra.slugs`, along with each council's homepage (`extra.homepage`, used
  by phase 3) and the service URLs (`extra.links`).
- Choose the service list from the CSV by coverage, and check it by hand
  against the services a resident would actually look for. It lives in the
  module with the LGSL codes, so it is easy to review. Leave out any service a
  council doesn't run (for example where waste goes to a joint authority).

**`planning_data`.** The share of the eight datasets listed above that the
council provides through at least one working endpoint. Count all eight for
every single-tier council, whatever the `provision_reason`, so 29 councils
aren't left out because they aren't in the "expected" cohort. Say so on the
methodology page. Where a national park or development corporation is the
planning authority for part of a council's area, the council is still
measured on its own data.

**`brownfield`.** Whether the council provides the `brownfield-land` dataset
through a working endpoint. It has been a legal requirement since 2017.

### Phase 2: more published sources

| id | Label | Kind | Source |
|---|---|---|---|
| `contracts_published` | Contracts awarded with a notice published within 30 days | %, higher | Find a Tender (OCDS) |
| `accounts_audited` | Latest accounts audited by the deadline | check | MHCLG / PSAA |
| `ico_action` | ICO enforcement or reprimand in the last three years | check | ICO |

These need more care in matching and explaining, so they come after phase 1
has shipped. `contracts_published` needs a careful definition: Find a Tender
replaced Contracts Finder for new procurements under the Procurement Act 2023
(from 24 February 2025), so the measure should only start from then. Buyers in
OCDS are named, not coded, so they need matching through `pipeline/names.py`.
`ico_action` and the accounts deadline are rare events, so they are shown as a
flag on the council's page rather than ranked. The sources for
`accounts_audited` and `ico_action` haven't been checked yet.

FOI timeliness (from WhatDoTheyKnow) goes here only if mySociety provides the
data (see "What the sources hold").

### Phase 3: our own checks

One new source, `website`, which visits each council's site from the homepage
in Local Links Manager. These are labelled "Our checks" on the site, not
published statistics.

| id | Label | Kind | How |
|---|---|---|---|
| `dmarc` | Email protected against spoofing (DMARC set to quarantine or reject, for all mail) | check | DNS TXT lookup of `_dmarc.<domain>`, following CNAMEs; `pct` below 100 doesn't pass |
| `https` | Website uses HTTPS everywhere (HSTS) | check | `Strict-Transport-Security` header on the homepage |
| `security_txt` | Says how to report a security problem | check | `/.well-known/security.txt` |
| `a11y_statement` | Has an accessibility statement reviewed in the last year | check | Find the statement (footer link, then `/accessibility`), read its "last reviewed" date |
| `a11y_status` | What the accessibility statement says | text | "fully", "partially" or "not compliant", from the GDS template wording |
| `spend_data_age` | Months since the newest published spending over £500 | number, lower | Find the transparency page, find the newest spending file by its name and date |
| `trackers_before_consent` | Tracking cookies set before you agree to them | check | Load the homepage in Playwright with no interaction, and list the third-party cookies and requests to known trackers |
| `reject_cookies` | Can reject cookies as easily as accept them | check | A reject button on the first layer of the banner |
| `online_tasks` | Top tasks you can complete online | %, higher | For the 10 top tasks, whether the page from Local Links Manager leads to an online form or payment rather than only a phone number or PDF |

What we also record, but don't rank: the CMS, the forms platform and the
payments provider, detected from the HTML, shown as background on the council's
page ("This council's website runs on…").

`online_tasks` is the hardest to make fair, so it goes last within phase 3.
Before it ships, check a sample of 20 councils by hand and agree the rules.

### The existing Silktide measure

Silktide's site gives each council a rank among all 391 UK councils (county,
district and the other nations included), while we rank it among the
councils in its comparison group. Lewisham, for example, is 192nd on
Silktide and 63rd of 130 on our site, from the same October 2026 score
(92.68). Both put it near the middle, but a reader who checks will think one
of us is wrong. So:

- Under the measure, say that our position is among the group shown, and that
  Silktide ranks every UK council together.
- Keep Silktide's own rank (`categoryRanks` on the website page we already
  fetch, so no extra requests) in `extra`, and show it with a link: "Silktide
  ranks it 192nd of 391 UK councils".
- Keep two decimal places rather than one (`places=2` in
  `pipeline/sources/silktide.py`). Rounding to 92.7 creates ties Silktide
  doesn't have: Lewisham shares its position with another council.

This can be done on its own, before phase 1.

## Pipeline changes

- `pipeline/sources/local_links.py` and `planning_data.py` (phase 1);
  `contracts.py`, `accounts.py`, `ico.py` (phase 2);
  `website.py` (phase 3). Each added to `STEPS`, and those with measures to
  `VALUE_SOURCES`, in `pipeline/update.py`.
- `website.py` needs the homepages from `local_links`, so it runs after it and
  reads `context["results"]["local_links"]`.
- Checks are stored as `True`/`False` in `values`, with the evidence in
  `extra[code][measure]` (URL checked, date, what was found), so a council's
  page can show why and the data stays auditable.
- New dependencies: `dnspython` for DMARC lookups. Playwright is only needed by
  `website.py`; install it in the workflow with
  `pip install playwright && playwright install chromium`.
- `website.py` takes about 130 councils × ~15 requests at one a second, which
  is roughly 35 minutes. Give it `MAX_AGE_DAYS = 28`, and stagger it from
  `local_links` (also monthly, 45 minutes) so they don't both run in the same
  week. Raise the workflow's `timeout-minutes` to 90 if they ever do.
- Local Links Manager and Planning Data give GSS codes, so they need no name
  matching. OCDS buyers and ICO notices do; add aliases to
  `pipeline/names.py` as needed.

## Site changes

- `web/model.py`: split the measures over three areas, by the question a
  resident would ask (proposed; names to agree):

  | Area | Question | Measures |
  |---|---|---|
  | Online services (the existing `digital` area, renamed) | Can I get things done online? | `links_working`, `online_tasks`, `web_access`, `a11y_statement` (with `a11y_status` shown in its reason) |
  | Privacy and security | Is my data safe with them? | `trackers_before_consent`, `reject_cookies`, `dmarc`, `https`, `security_txt`, `ico_action` |
  | Openness | Do they publish what they should? | `spend_data_age`, `contracts_published`, `accounts_audited`, `brownfield`, `planning_data`, FOI if it comes |

  Accessibility goes with online services because an inaccessible site is a
  service some residents can't use. `planning_data` and `brownfield` could
  later move to a Planning area with MHCLG's planning application statistics.
  Most of Privacy and security is our own checks, so the area as a whole
  carries the "Our checks" label. `local_digital` is left out: signing a
  declaration says little a resident would notice.
- Measures support a `kind` of `"check"`. Checks aren't ranked: the council's
  page shows a tick or cross with a short reason, and the measure page shows
  how many councils pass, with a list of those that don't.
- A small "Our checks" tag on every measure from `website.py`, linking to the
  methodology section.
- `web/templates/about.html`: a methodology section for each new source, and
  credits in the footer next to Silktide. Local Links Manager and Planning
  Data are both under the Open Government Licence.

## Other nations and two-tier England

- Local Links Manager covers England, Scotland and Wales, so `links_working`
  is ready for Wales when it launches, and for two-tier England (the CSV and
  API give each council's `tier`; county and district councils provide
  different services, so each tier needs its own service list).
- Planning Data is England only. Scottish and Welsh councils get no planning
  measures.
- Phase 3 checks work for every council, so give those measures every nation
  that's live.

## Tests

- `tests/test_pipeline.py`: a parser test for each new source against a small
  saved response in `tests/fixtures/` (a few rows of the links CSV, a few
  `/api/link` responses including `broken` and `caution`, a few rows of
  `provision_summary`).
- `tests/test_data.py`: each new measure covers most councils
  (the existing `test_each_measure_covers_most_councils`); percentages are
  0–100; checks are booleans; every check has its evidence; `spend_data_age`
  is between 0 and 120.
- `tests/test_model.py`: check measures are never ranked, and render on the
  council page and the measure page.

## Order of work

Each step is one pull request, opened against `main` and mergeable on its
own. Where one needs another merged first, its description says so.

1. `local_links` source and `links_working`. Methodology text.
2. `planning_data` source and `planning_data`.
3. Support for check measures in `web/model.py` and the templates, then the
   `brownfield` check.
4. `website` source, part one: DMARC, HTTPS, security.txt, accessibility
   statement. No browser needed.
5. `website` source, part two: Playwright cookie checks and the transparency
   spending check.
6. Phase 2 sources, one pull request each.
7. `online_tasks`, after the hand check of 20 councils.

## Risks

- **What `caution` means.** Local Links Manager's checker marks some links
  `caution` (Croydon's missed-bin link, which redirects). Find out what it
  covers before counting it as not working; otherwise count only `broken`.
- **The link checker is GOV.UK's, not ours.** If GOV.UK stops checking, or
  checks less often, the measure goes stale. Record the date of each run and
  warn in the update summary if statuses stop changing.
- **Planning Data is still being built.** Datasets move between "expected" and
  "statutory", and the performance database's tables may change. Find
  columns by name, and fail the source (keeping the previous figures) if one
  goes missing.
- **Bot protection.** Some council sites sit behind Cloudflare or similar and
  may block the phase 3 checker. Record "couldn't check" rather than a fail,
  and list those councils in the update summary.
- **False fails.** Statements and spending files live in different places on
  each site. Each fail keeps its evidence and URL, and the first full run is
  reviewed by hand before it is published.
- **Councils disputing results.** Add a "Think this is wrong?" link on check
  measures, pointing to an email address or a GitHub issue template.
- **Measures that reward box-ticking.** Prefer measures residents would notice
  (links that work, services online) over ones that only test paperwork, and
  keep check measures out of any overall ranking.

## Decisions

Made on 3 November 2026:

- **Our own checks are published**, labelled "Our checks". Phase 3 goes ahead.
- **This plan stays on its branch**, not merged to `main`.

- **Ask mySociety for FOI data**: either a periodic extract of requests by
  authority (on time, late, overdue) or permission to read the authority JSON
  pages at a low rate. FOI joins Openness only if they agree.
- **Areas**: Online services, Privacy and security, Openness.

Proposed, to confirm:

- **Checks in the council page summary.** Keep checks out of the quarter
  counts ("5 of 12 measures in the top quarter"), since a yes/no can't be
  ranked. Add one line under the summary when a council fails any: "Fails 2
  of 9 checks: DMARC, accessibility statement". Say nothing when it passes
  them all.
