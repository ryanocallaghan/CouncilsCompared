"""Whether GOV.UK's links to each council's core services work.

GOV.UK sends people to the right page on their council's website (to pay
council tax, report a missed bin, apply for a school place) using Local Links
Manager, which holds the link for every council and service and checks them
regularly. Its CSV of every link has no check results, so each core
service's link is asked for through its API, which says how the last check
went:

- ok: works
- caution: works, with a warning (it redirects, say)
- broken: doesn't work
- no link at all: GOV.UK can only send people to the council's homepage

Some council websites block GOV.UK's checker, so every link looks broken.
So each link GOV.UK marks broken is tried once here: if the page loads, it
counts as working ("rechecked"); if it's gone (404 or 410), it stays broken;
anything else (blocked, timed out) keeps GOV.UK's verdict.

A council's figure is the share of its core services with a link that works
(ok, caution or rechecked). Links not checked yet are left out.

About 20 requests a council, so it runs monthly.
"""

import csv
import datetime
import io
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from pipeline.http import USER_AGENT, get_json, get_text
from pipeline.sources import Result

ID = "local_links"
BASE = "https://local-links-manager.publishing.service.gov.uk"
CSV = f"{BASE}/data/links_to_services_provided_by_local_authorities.csv"
PAGE = "https://www.gov.uk/find-local-council"
MAX_AGE_DAYS = 28
PAUSE = 0.5

# What a resident most often goes to their council's website for, by LGSL
# code. Each is a service almost every council in the nation has a link for,
# so no council is marked down for a service it doesn't run.
SERVICES = {
    57: "Paying council tax",
    59: "Council tax discounts",
    63: "Council tax support",
    69: "Housing benefit",
    524: "Bin collections",
    528: "Bulky waste collections",
    587: "Reporting fly-tipping",
    557: "Reporting a road problem",
    474: "Parking permits",
    279: "Blue badges",
    273: "Older people's bus passes",
    13: "Primary school places",
    14: "Secondary school places",
    4: "Free school meals",
    36: "School term dates",
    92: "Applying for council housing",
    112: "Help if you're homeless",
    437: "Libraries",
    364: "Registering to vote",
    353: "Making a complaint",
}
# Scottish councils mostly have no link for these, so Scotland is compared on the rest
NOT_IN = {"S": {528, 474, 4, 273}}
WORKING = {"ok", "caution", "rechecked"}

# GOV.UK's slug where it isn't the council's name without "Council" and so on
SLUGS = {
    "E06000010": "kingston-upon-hull",
    "E06000015": "derby",
    "E06000047": "county-durham",
    "E06000058": "bournemouth-christchurch-poole",
    "E06000065": "north-yorkshire",
    "E06000066": "somerset",
    "E08000021": "newcastle-upon-tyne",
    "S12000013": "eilean-siar",
    "S12000017": "highland",
    "S12000020": "moray",
    "S12000047": "fife",
    "S12000048": "perth-and-kinross",
    "S12000049": "glasgow",
    "S12000050": "north-lanarkshire",
}
# Councils GOV.UK still knows by an older code
OLD_CODES = {
    "E10000023": "E06000065",  # North Yorkshire, unitary since 2023
    "E10000027": "E06000066",  # Somerset, unitary since 2023
    "S12000015": "S12000047",  # Fife
    "S12000024": "S12000048",  # Perth and Kinross
    "S12000046": "S12000049",  # Glasgow
    "S12000044": "S12000050",  # North Lanarkshire
}


def services_for(code):
    return [lgsl for lgsl in SERVICES if lgsl not in NOT_IN.get(code[0], set())]


def slug(name):
    """GOV.UK's slug from the name in its CSV: "London Borough of Lewisham" -> "lewisham"."""
    for prefix in ["London Borough of ", "Royal Borough of ", "City of ", "Borough of ", "Council of the "]:
        name = name.removeprefix(prefix)
    name = re.sub(r"\s+(Metropolitan Borough|Metropolitan District|City|Borough|County|District)?\s*Council$", "",
                  name)
    name = re.sub(r"\s+Council$", "", name)
    name = name.lower().replace("&", "and").replace("'", "").replace(".", "")
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")


def names_from_csv(text):
    """{ons code: GOV.UK's name for the council}."""
    return {OLD_CODES.get(row["GSS"], row["GSS"]): row["Authority Name"]
            for row in csv.DictReader(io.StringIO(text)) if row.get("GSS")}


def link(slug_, lgsl):
    query = urllib.parse.urlencode({"authority_slug": slug_, "lgsl": lgsl})
    return get_json(f"{BASE}/api/link?{query}", pause=PAUSE)


def status(response):
    """ok, caution or broken; "missing" when GOV.UK has no link; None when not checked yet."""
    interaction = response.get("local_interaction")
    if not interaction or not interaction.get("url"):
        return "missing"
    return interaction.get("status")


def loads(url):
    """Whether a page loads, from one request: True, False if it's gone, None if we can't tell."""
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            return 200 <= response.status < 400
    except urllib.error.HTTPError as e:
        return False if e.code in (404, 410) else None
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return None


def recheck(links, pause=PAUSE):
    """Try each link GOV.UK marks broken; those that load count as working."""
    for link_ in links.values():
        if link_["status"] == "broken" and link_.get("url"):
            if loads(link_["url"]):
                link_["status"] = "rechecked"
            time.sleep(pause)


def summary(links):
    """The figure and the detail for a council's page, from {lgsl: {status, url}}."""
    checked = [v["status"] for v in links.values() if v["status"]]
    return {
        "working": 100 * sum(s in WORKING for s in checked) / len(checked) if checked else None,
        "services": len(checked),
        # In the order of SERVICES, whatever order the links were saved in
        "broken": [name for k, name in SERVICES.items() if links.get(str(k), {}).get("status") == "broken"],
        "missing": [name for k, name in SERVICES.items() if links.get(str(k), {}).get("status") == "missing"],
    }


def fetch(context):
    today = datetime.date.today()
    result = Result(id=ID, title="GOV.UK Local Links Manager", url=PAGE, period=today.strftime("%B %Y"),
                    published=today.isoformat(), files=[CSV])
    result.extra["checked"] = today.isoformat()
    names = names_from_csv(get_text(CSV))
    unchecked = 0
    for code in sorted(context["population"]):
        if code[0] not in "ES":
            continue
        if code not in names and code not in SLUGS:
            result.notes.append(f"{code} isn't in Local Links Manager")
            continue
        slug_ = SLUGS.get(code) or slug(names[code])
        links, homepage = {}, None
        for lgsl in services_for(code):
            response = link(slug_, lgsl)
            authority = response.get("local_authority") or {}
            found = OLD_CODES.get(authority.get("gss"), authority.get("gss"))
            if found != code:
                raise ValueError(f"GOV.UK's {slug_!r} is {found}, not {code}")
            homepage = authority.get("homepage_url")
            interaction = response.get("local_interaction") or {}
            links[str(lgsl)] = {"status": status(response), "url": interaction.get("url")}
        recheck(links)
        figures = summary(links)
        unchecked += len(links) - figures["services"]
        if figures["services"] < len(links) / 2:
            result.notes.append(f"{code}: only {figures['services']} of {len(links)} links checked by GOV.UK")
            continue
        result.set(code, "links_working", figures.pop("working"))
        result.extra[code] = {"slug": slug_, "homepage": homepage, "links": links,
                              **figures}
    if unchecked:
        result.notes.append(f"{unchecked} links not checked by GOV.UK yet, left out")
    return result
