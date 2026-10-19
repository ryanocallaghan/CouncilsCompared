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
CONTACT_EMAIL = "hello@councilscompared.com"

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


def council_links(councils, group="england"):
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


def structured_data(council, group):
    """Breadcrumbs for search results: Councils compared > Lewisham."""
    crumbs = [("Councils compared", "/"), (council["name"], model.path(council))]
    if group != "england":
        crumbs.append((model.group_tab(council, group), model.path(council, group)))
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [{"@type": "ListItem", "position": i, "name": name, "item": SITE_URL + path}
                            for i, (name, path) in enumerate(crumbs, 1)],
    }


def build(out=DIST):
    data = model.load()
    councils = sorted(data["councils"].values(), key=lambda c: c["name"])
    sources = data["sources"]
    env = environment()
    common = {
        "site_url": SITE_URL, "repo_url": REPO_URL, "issues_url": ISSUES_URL, "model": model,
        "sources": sources, "all_councils": councils, "asset_version": asset_version(),
        "author_url": AUTHOR_URL, "contact_email": CONTACT_EMAIL,
        "umami": {"script": UMAMI_SCRIPT, "website_id": UMAMI_WEBSITE_ID} if UMAMI_WEBSITE_ID else None,
    }
    pages = []

    def page(path, template, nav=None, **context):
        write(out, path, env.get_template(template).render(page_path=path, nav=nav, **common, **context))
        if path.endswith("/"):
            pages.append(path)

    regions = {}
    for c in councils:
        regions.setdefault(c["region"], []).append(c)
    page("/", "index.html", nav="/", regions=sorted(regions.items()), structured_data={
        "@context": "https://schema.org", "@type": "WebSite", "name": "Councils compared", "url": SITE_URL + "/",
        "description": "How every single-tier council in England compares, from official statistics.",
        "author": {"@type": "Person", "name": "Ryan O'Callaghan", "url": AUTHOR_URL},
    })
    for council in councils:
        groups = model.groups_for(council)
        for group in groups:
            page(model.path(council, group), "council.html", nav="/", groups=groups,
                 comparison=model.compare(council, group), council_tax=model.council_tax(council),
                 structured_data=structured_data(council, group))
    order = ["ehcp", "lgo", "lgo_decisions", "tsm", "ctax", "band_d", "fly", "waste", "homelessness",
             "silktide", "spending", "ofsted", "neighbours", "population"]
    source_list = [sources[s] for s in order if s in sources]
    page("/measures/", "measures.html", nav="/measures/")
    regions_list = sorted({c["region"] for c in councils})
    types = sorted({c["type"] for c in councils})
    areas = {a: (name, note) for a, name, note in model.AREAS}
    for m in model.MEASURES:
        rows = model.ranking(m)
        ranked = {c["code"] for _, c, _, _ in rows}
        page(f"/measures/{m.id.replace('_', '-')}/", "measure.html", nav="/measures/", measure=m, rows=rows,
             map=model.hexmap(m), period=model.period(m), source=sources.get(m.source, {}),
             area_name=areas[m.area][0], note=areas[m.area][1], regions=regions_list, types=types,
             missing=[c for c in councils if c["code"] not in ranked])
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
        for path in pages:
            f.write(f"  <url><loc>{escape(SITE_URL + path)}</loc></url>\n")
        f.write("</urlset>\n")
    with open(os.path.join(out, "robots.txt"), "w") as f:
        f.write(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")
    for name in os.listdir(os.path.join(HERE, "static")):
        target = os.path.join(out, name if name.startswith("_") else os.path.join("assets", name))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy(os.path.join(HERE, "static", name), target)
    return len(pages)


if __name__ == "__main__":
    count = build(sys.argv[1] if len(sys.argv) > 1 else DIST)
    print(f"Built {count} pages")
