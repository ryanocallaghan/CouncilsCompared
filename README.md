# Councils compared

[councilscompared.com](https://councilscompared.com) shows how each of the 130 single-tier councils in England (unitary authorities, metropolitan districts and London boroughs) compares with the rest of England, its region, councils of the same type, and its statistical neighbours, using official published statistics.

It is an independent website, not affiliated with GOV.UK, any government department or any council. It uses the [GOV.UK Design System](https://design-system.service.gov.uk/) with its own header, colours and Arial, as non-government services must.

## How it works

```
pipeline/   fetches each publication and turns it into figures by ONS code
data/       the figures: data/sources/<source>.json, assembled into data/councils.json
web/        builds the static site from data/councils.json into dist/
functions/  a Cloudflare Pages Function for the council chooser without JavaScript
tests/      unit tests, and checks on the data itself
```

Every Monday the [Update data](.github/workflows/update-data.yml) workflow runs `python -m pipeline.update`. If any figures changed, it opens a pull request (or updates the open one) describing what changed, with the result of the data checks. Cloudflare Pages builds a preview of the pull request; merging it publishes the new figures.

When new figures or pages reach `main`, the [Tell search engines](.github/workflows/indexnow.yml) workflow sends every page in the sitemap to [IndexNow](https://www.indexnow.org/) (Bing, Yandex and others), so they fetch the pages again soon.

If a source fails (a site is down, or a spreadsheet changes shape), its previous figures are kept and the pull request says which one failed, so the others still update.

### Sources

| Source | How it's found | Measures |
|---|---|---|
| ONS mid-year population estimates | the newest file linked from the ONS dataset page; regions from the ONS Open Geography API | population, council type, region |
| DfE children's services statistical neighbours | GOV.UK Content API | similar councils |
| DfE education, health and care plans | Explore Education Statistics public API | EHC plans within 20 weeks |
| LGSCO annual review data | files linked from the Ombudsman's page | complaints received and upheld, remedies |
| LGSCO decision search | the Ombudsman's search, monthly, a second between requests | upheld decisions by service area |
| RSH Tenant Satisfaction Measures | GOV.UK Content API (collection) | tenant satisfaction, repairs, decent homes, complaints |
| MHCLG council tax collection rates and levels | GOV.UK Content API (collection) | collection rate, Band D |
| Defra fly-tipping (ENV24) and waste (ENV18) | GOV.UK Content API | fly-tipping, enforcement, recycling |
| MHCLG statutory homelessness | GOV.UK Content API | temporary accommodation, prevention and relief |
| MHCLG revenue outturn (RSX) | GOV.UK Content API (collection) | spending per resident |
| Ofsted local authority inspection outcomes | GOV.UK Content API (collection) | children's services grade |
| Silktide Index | the index's pages | website accessibility score |

Columns are found by their headings and rows by ONS code, so new editions usually work without changes. Councils named rather than coded (the Ombudsman, the regulator, Silktide) are matched by name in `pipeline/names.py`.

## Running it

```sh
pip install -r requirements-dev.txt
npm install

python -m pipeline.update            # fetch everything (the Ombudsman search takes about 15 minutes)
python -m pipeline.update --only ctax,tsm
CC_CACHE=cache python -m pipeline.update   # keep downloads in cache/ while working on a parser

npm run build                        # CSS, then the site, into dist/
python -m http.server -d dist 8000
python -m pytest
```

Analytics: the cookie-free [Umami](https://umami.is) script from stats.mybin.day. Set `UMAMI_WEBSITE_ID=""` to build without it.

## Hosting

Cloudflare Pages, connected to this repository:

- Build command: `pip install -r requirements.txt && npm run build`
- Build output directory: `dist`
- Environment variable: `PYTHON_VERSION` = `3.12`

## Licence

Code: MIT. Data: contains public sector information licensed under the [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/), and data from the [Silktide Index](https://index.silktide.com/).
