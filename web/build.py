"""Build the static site into dist/.

    npm run build:css && python -m web.build

Pages: the home page, one page per council (compared with all of England)
with a page under it for each other comparison group, and About. The data
is also published as JSON and CSV for anyone to reuse.
"""

import csv
import hashlib
import io
import json
import os
import re
import shutil
import sys
from datetime import date

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, PackageLoader, PrefixLoader, select_autoescape
from markupsafe import Markup, escape

from web import model

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(model.ROOT, "dist")
SITE_URL = "https://councilscompared.com"
REPO_URL = "https://github.com/ryanocallaghan/CouncilsCompared"
ISSUES_URL = REPO_URL + "/issues"
AUTHOR_URL = "https://ryanocallaghan.com"
AUTHOR = {"@type": "Person", "name": "Ryan O'Callaghan", "url": AUTHOR_URL,
          "sameAs": [AUTHOR_URL, "https://github.com/ryanocallaghan"]}
# Published at /<key>.txt so IndexNow knows submissions come from us (web/indexnow.py)
INDEXNOW_KEY = "b49469e07ca9739c5c5e4e3bfaa95e14"
OGL_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
CONTACT_URL = "https://www.ryanocallaghan.com/800"  # the contact form on Ryan's website

# Cookie-free analytics on the self-hosted Umami that mybin.day uses. Set
# UMAMI_WEBSITE_ID to "" to turn it off (e.g. for a local build).
UMAMI_SCRIPT = os.environ.get("UMAMI_SCRIPT", "https://stats.mybin.day/script.js")
UMAMI_WEBSITE_ID = os.environ.get("UMAMI_WEBSITE_ID", "c45c09b5-2816-4025-835f-402e19d80c18")


def possessive(name):
    return f"{name}’" if name.endswith("s") else f"{name}’s"


def sentence_join(items):
    items = list(items)
    if len(items) <= 1:
        return Markup("").join(items)
    return Markup(", ").join(items[:-1]) + Markup(" and ") + items[-1]


def council_links(councils, group="nation"):
    return sentence_join(Markup('<a class="govuk-link" href="{}">{}</a>').format(model.path(c, group), c["name"])
                         for c in councils)


def long_date(iso):
    if not iso:
        return ""
    day = date.fromisoformat(iso[:10])
    return f"{day.day} {day:%B %Y}"


def environment():
    env = Environment(
        loader=ChoiceLoader([
            FileSystemLoader(os.path.join(HERE, "templates")),
            PrefixLoader({"govuk_frontend_jinja": PackageLoader("govuk_frontend_jinja")}),
        ]),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(possessive=possessive, sentence_join=sentence_join, council_links=council_links,
                       long_date=long_date)
    return env


def asset_version():
    """Changes when the CSS or JS does, so browsers fetch the new one."""
    digest = hashlib.sha1()
    for name in ("main.css", "app.js"):
        path = os.path.join(DIST, "assets", name)
        if os.path.exists(path):
            digest.update(open(path, "rb").read())
    return digest.hexdigest()[:10]


def image_version():
    """Changes when the share image does: assets are cached for a year, and
    link previews keep an image for as long as its address stays the same."""
    with open(os.path.join(HERE, "static", "og.png"), "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()[:10]


def write(out, path, text):
    target = os.path.join(out, path.strip("/"), "index.html") if path.endswith("/") else os.path.join(out, path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w") as f:
        f.write(text)


def csv_text(councils):
    measures = [m.id for m in model.MEASURES]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ons_code", "council", "type", "region", "population", "band_d"] + measures
                    + [f"spend_per_resident: {s}" for s in model.SPENDING] + ["ofsted_grade", "ofsted_inspected"])
    for c in councils:
        ofsted = c.get("ofsted") or {}
        writer.writerow([c["code"], c["name"], c["type"], c["region"], c["population"], c["band_d"]]
                        + [c["values"].get(m) for m in measures]
                        + [c["spend"].get(s) for s in model.SPENDING]
                        + [ofsted.get("grade"), ofsted.get("inspected")])
    return out.getvalue()


def write_lookups(out, councils):
    """For the postcode search (functions/go.js): ONS code -> page, and the
    most common council tax band in each neighbourhood, split into small
    files by the start of the neighbourhood code."""
    from pipeline.sheets import SAME_COUNCIL
    pages = {c["code"]: c["slug"] for c in councils}
    for old, new in SAME_COUNCIL:
        for a, b in ((old, new), (new, old)):
            if a in pages:
                pages.setdefault(b, pages[a])
    with open(os.path.join(out, "data", "councils-by-code.json"), "w") as f:
        json.dump(pages, f, separators=(",", ":"))
    path = os.path.join(model.ROOT, "data", "sources", "area_bands.json")
    if not os.path.exists(path):
        return
    with open(path) as f:
        bands = json.load(f)["extra"]
    shards = {}
    for area, band in bands.items():
        shards.setdefault(area[:6], {})[area] = band
    os.makedirs(os.path.join(out, "data", "bands"), exist_ok=True)
    for prefix, shard in shards.items():
        with open(os.path.join(out, "data", "bands", f"{prefix}.json"), "w") as f:
            json.dump(shard, f, separators=(",", ":"))


def structured_data(council, group, updated):
    """Breadcrumbs for search results (Councils compared > Lewisham), and
    the page as one about the council, so search engines and AI answers
    know which council the figures are for."""
    crumbs = [("Councils compared", "/"), (council["name"], model.path(council))]
    if group != "nation":
        crumbs.append((model.group_tab(council, group), model.path(council, group)))
    page = {
        "@type": "WebPage",
        "url": SITE_URL + model.path(council, group),
        "about": {
            "@type": "GovernmentOrganization",
            "name": f"{council['name']} Council",
            "areaServed": {"@type": "AdministrativeArea", "name": council["name"], "identifier": council["code"]},
        },
        "author": AUTHOR,
    }
    if updated:
        page["dateModified"] = updated
    return {
        "@context": "https://schema.org",
        "@graph": [page, {
            "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i, "name": name, "item": SITE_URL + path}
                                for i, (name, path) in enumerate(crumbs, 1)],
        }],
    }


def temporal_coverage(period):
    """ "2024-25" -> "2024/2025", "2025" -> "2025"; None for anything else
    ("January to March 2026"), which schema.org can't express simply."""
    if re.fullmatch(r"\d{4}", period):
        return period
    match = re.fullmatch(r"(\d{4})-(\d{2})", period)
    if match:
        start = int(match[1])
        return f"{start}/{start + 1}"
    return None


def every_council(nation):
    """Which councils a ranking covers, in words."""
    if nation == "England":
        return ("every council in England that runs all local services (unitary authorities, metropolitan "
                "districts and London boroughs)")
    return f"every council in {nation}"


def dataset(name, description, path, period, source, updated, ogl=True, nation="England"):
    """A ranking page as a dataset, for Google Dataset Search."""
    data = {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": f"{name}: every council in {nation}",
        "description": f"{name}, for {every_council(nation)}, ranked, from official statistics. {description}",
        "url": SITE_URL + path,
        "creator": AUTHOR,
        "spatialCoverage": {"@type": "Place", "name": nation},
        "distribution": [
            {"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": SITE_URL + "/data/councils.csv"},
            {"@type": "DataDownload", "encodingFormat": "application/json",
             "contentUrl": SITE_URL + "/data/councils.json"},
        ],
    }
    if source.get("url"):
        data["isBasedOn"] = source["url"]
    if ogl:
        data["license"] = OGL_URL
    if temporal_coverage(period):
        data["temporalCoverage"] = temporal_coverage(period)
    if updated:
        data["dateModified"] = updated
    return data


def llms_txt(councils):
    """A plain summary for AI tools: what the site is and where the figures are."""
    measures = "\n".join(f"- [{m.label}]({SITE_URL}/measures/{m.id.replace('_', '-')}/)"
                         for m in model.MEASURES if model.available(m))
    return f"""# Councils compared

> How each of the {len(councils)} single-tier councils in England (unitary authorities, metropolitan districts and London boroughs) compares with the rest of England, its region, councils of the same type and similar councils, using official published statistics. An independent website by Ryan O'Callaghan, not affiliated with any government department or council.

Each council has a page at {SITE_URL}/<council>/ (for example {SITE_URL}/lewisham/), with pages under it comparing it with its region (/region/), councils of the same type (/type/) and similar councils (/similar/). A position of 1st is the best in the group. Figures are updated weekly as new editions are published.

## About

- [About the figures]({SITE_URL}/about/): which councils are included, how they are compared, what to bear in mind, and every source
- [All measures]({SITE_URL}/measures/)

## Measures

{measures}

## Data

- [Every figure for every council (CSV)]({SITE_URL}/data/councils.csv)
- [Every figure for every council (JSON)]({SITE_URL}/data/councils.json)

Contains public sector information licensed under the Open Government Licence v3.0, and data from the Silktide Index.
"""


def build(out=DIST):
    data = model.load()
    councils = sorted(data["councils"].values(), key=lambda c: c["name"])
    sources = data["sources"]
    env = environment()
    common = {
        "site_url": SITE_URL, "repo_url": REPO_URL, "issues_url": ISSUES_URL, "model": model,
        "sources": sources, "all_councils": councils, "asset_version": asset_version(),
        "image_version": image_version(),
        "author_url": AUTHOR_URL, "contact_url": CONTACT_URL,
        "umami": {"script": UMAMI_SCRIPT, "website_id": UMAMI_WEBSITE_ID} if UMAMI_WEBSITE_ID else None,
    }
    pages = []  # [(path, last modified)]
    updated = model.updated()

    def page(path, template, nav=None, lastmod=None, **context):
        write(out, path, env.get_template(template).render(page_path=path, nav=nav, **common, **context))
        if path.endswith("/"):
            pages.append((path, lastmod))

    regions = {}
    for c in councils:
        if c["nation"] == "England":
            regions.setdefault(c["region"], []).append(c)
    other_nations = [(n, [c for c in councils if c["nation"] == n]) for n in model.nations() if n != "England"]
    page("/", "index.html", nav="/", lastmod=updated, regions=sorted(regions.items()), other_nations=other_nations,
         structured_data={
        "@context": "https://schema.org", "@type": "WebSite", "name": "Councils compared", "url": SITE_URL + "/",
        "description": f"How {model.coverage()} compares, from official statistics.",
        "author": AUTHOR, "publisher": AUTHOR,
    })
    for council in councils:
        groups = model.groups_for(council)
        for group in groups:
            comparison = model.compare(council, group)
            council_updated = model.updated(model.nation_sources(council["nation"]))
            page(model.path(council, group), "council.html", nav="/", lastmod=council_updated, groups=groups,
                 comparison=comparison, key_figures=model.key_figures(comparison), updated=council_updated,
                 council_tax=model.council_tax(council),
                 structured_data=structured_data(council, group, council_updated))
    order = ["ehcp", "lgo", "lgo_decisions", "tsm", "ctax", "band_d", "fly", "waste", "homelessness",
             "silktide", "spending", "ofsted", "neighbours", "lgbf", "spso", "scot_homelessness", "scot_band_d",
             "scot_spending", "population"]
    # A nation's sources only once the nation is on the site
    used = set().union(*(model.nation_sources(n) for n in model.nations()))
    source_list = [sources[s] for s in order if s in sources and s in used]
    page("/measures/", "measures.html", nav="/measures/")
    regions_list = sorted({c["region"] for c in councils if c["nation"] == "England"})
    types = sorted({c["type"] for c in councils if c["nation"] == "England"})
    areas = {a: (name, note) for a, name, note in model.AREAS}
    for nation in model.nations():
        for m in (m for m in model.MEASURES if model.available(m, nation)):
            rows = model.ranking(m, nation)
            ranked = {c["code"] for _, c, _, _ in rows}
            path = model.measure_path(m, nation)
            source_id = m.source_for(nation)
            source = sources.get(source_id, {})
            measure_updated = model.updated({source_id})
            page(path, "measure.html", nav="/measures/", lastmod=measure_updated or None, measure=m, rows=rows,
                 nation=nation, summary=model.measure_summary(m, rows, nation), updated=measure_updated,
                 structured_data=dataset(m.label, f"{'Higher' if m.better == 'higher' else 'Lower'} is better.",
                                         path, model.period(m, nation), source, measure_updated, nation=nation,
                                         ogl=source_id != "silktide"),  # the Silktide Index is not under the OGL
                 map=model.hexmap(m, nation), period=model.period(m, nation), source=source,
                 area_name=areas[m.area][0], note=model.area_note(m.area, nation), regions=regions_list,
                 types=types,
                 missing=[c for c in model.in_nation(nation) if c["code"] not in ranked])
    for nation in model.nations():
        band_d_id = model.nation_source("band_d", nation)
        band_d_source = sources.get(band_d_id, {})
        band_d_updated = model.updated({band_d_id})
        band_d_rows = model.band_d_ranking(nation)
        if not band_d_rows:
            continue
        band_d_path = model.band_d_path(nation)
        page(band_d_path, "band_d.html", nav="/measures/", lastmod=band_d_updated or None, rows=band_d_rows,
             nation=nation, summary=model.band_d_summary(band_d_rows, nation), source=band_d_source,
             updated=band_d_updated, regions=regions_list, types=types,
             structured_data=dataset(f"Council tax Band D {band_d_source.get('period', '')}".strip(),
                                     "The yearly bill for a Band D home, including police, fire and parish "
                                     "charges." if nation == "England" else "The yearly bill for a Band D "
                                     "home, not including water and sewerage charges.", band_d_path,
                                     band_d_source.get("period", ""), band_d_source, band_d_updated,
                                     nation=nation))
    for group, value in model.hubs():
        hub = model.hub(group, value)
        hub_path = model.hub_path(group, value)
        hub_updated = model.updated(model.nation_sources(hub["nation"]))
        page(hub_path, "hub.html", nav="/", lastmod=hub_updated, hub=hub, updated=hub_updated, structured_data={
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i, "name": name, "item": SITE_URL + p}
                                for i, (name, p) in enumerate([("Councils compared", "/"),
                                                               (f"{hub['title']} compared", hub_path)], 1)],
        })
    page("/about/", "about.html", nav="/about/", councils=councils, source_list=source_list)
    page("/privacy/", "privacy.html", today="19 October 2026")
    page("404.html", "404.html")
    page("/postcode-not-found/", "postcode_not_found.html")
    page("/not-covered/", "not_covered.html")

    os.makedirs(os.path.join(out, "data"), exist_ok=True)
    shutil.copy(model.DATA_FILE, os.path.join(out, "data", "councils.json"))
    with open(os.path.join(out, "data", "councils.csv"), "w", newline="") as f:
        f.write(csv_text(councils))
    write_lookups(out, councils)
    with open(os.path.join(out, "data", "site.json"), "w") as f:
        json.dump(model.site_data(), f, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    with open(os.path.join(out, "sitemap.xml"), "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for path, lastmod in pages:
            when = f"<lastmod>{lastmod}</lastmod>" if lastmod else ""
            f.write(f"  <url><loc>{escape(SITE_URL + path)}</loc>{when}</url>\n")
        f.write("</urlset>\n")
    with open(os.path.join(out, "robots.txt"), "w") as f:
        # Content-Signal: search engines and AI answers may use the pages (contentsignals.org)
        f.write(f"User-agent: *\nContent-Signal: search=yes, ai-input=yes\nAllow: /\n"
                f"Sitemap: {SITE_URL}/sitemap.xml\n")
    with open(os.path.join(out, "llms.txt"), "w") as f:
        f.write(llms_txt(councils))
    with open(os.path.join(out, f"{INDEXNOW_KEY}.txt"), "w") as f:
        f.write(INDEXNOW_KEY)
    for name in os.listdir(os.path.join(HERE, "static")):
        target = os.path.join(out, name if name.startswith("_") else os.path.join("assets", name))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy(os.path.join(HERE, "static", name), target)
    return len(pages)


if __name__ == "__main__":
    count = build(sys.argv[1] if len(sys.argv) > 1 else DIST)
    print(f"Built {count} pages")
