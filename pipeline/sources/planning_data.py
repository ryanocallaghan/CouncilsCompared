"""Which planning datasets each council publishes, from MHCLG's Planning Data platform.

Planning authorities are asked to publish their planning data (conservation
areas, tree preservation orders and so on) in a standard form, which the
platform collects. Its performance database says, for each authority and
dataset, how many working endpoints (places the platform collects it from)
there are.

A council's figure is the share of eight datasets it publishes through at
least one working endpoint. The eight are the ones the platform expects from
most councils; every council is measured on all eight, whether or not the
platform lists them as expected from it yet.

The brownfield land register, which councils have had to publish since 2017,
is a check: a yes or no.

Councils created since 2019 can still have data collected under the district
councils they replaced. A dataset counts for the new council if it publishes
it itself, or if every one of the old councils does, so that it covers the
whole area.
"""

import csv
import datetime
import io

from pipeline.http import get_json, get_text
from pipeline.sources import Result

ID = "planning_data"
PAGE = "https://www.planning.data.gov.uk/"
PROVISION = "https://datasette.planning.data.gov.uk/performance/provision_summary.csv?_stream=on&_size=max"
ORGANISATIONS = "https://www.planning.data.gov.uk/organisation.json"

DATASETS = {
    "conservation-area": "Conservation areas",
    "conservation-area-document": "Conservation area documents",
    "article-4-direction": "Article 4 directions",
    "article-4-direction-area": "Article 4 direction areas",
    "listed-building-outline": "Listed building outlines",
    "tree-preservation-order": "Tree preservation orders",
    "tree-preservation-zone": "Tree preservation zones",
    "tree": "Protected trees",
}
BROWNFIELD = "brownfield-land"
COLUMNS = {"organisation", "dataset", "active_endpoint_count"}

# The district councils each new council replaced: (year, platform organisation ids)
REPLACED = {
    "E06000058": (2019, ["BMH", "CHC", "POL"]),  # Bournemouth, Christchurch and Poole
    "E06000059": (2019, ["EDO", "NDO", "PUR", "WDO", "WEY"]),  # Dorset
    "E06000060": (2020, ["AYL", "CHN", "SBU", "WYO"]),  # Buckinghamshire
    "E06000061": (2021, ["COR", "ENO", "KET", "WEL"]),  # North Northamptonshire
    "E06000062": (2021, ["DAV", "NOR", "SNR"]),  # West Northamptonshire
    "E06000063": (2023, ["ALL", "CAR", "COP"]),  # Cumberland
    "E06000064": (2023, ["BAR", "EDN", "SLA"]),  # Westmorland and Furness
    "E06000065": (2023, ["CRA", "HAE", "HAG", "RIH", "RYE", "SCE", "SEL"]),  # North Yorkshire
    "E06000066": (2023, ["MEN", "SEG", "SSO", "SWT"]),  # Somerset
}


def codes(organisations):
    """{ONS code: organisation id}, for the councils there are now."""
    return {o["statistical-geography"]: o["organisation"]
            for group in organisations["organisations"].values() for o in group
            if o.get("statistical-geography") and not o.get("end-date")}


def provided(rows):
    """{organisation id: set of datasets with a working endpoint}, and every organisation seen."""
    found, seen = {}, set()
    for row in rows:
        seen.add(row["organisation"])
        if int(row["active_endpoint_count"] or 0) > 0:
            found.setdefault(row["organisation"], set()).add(row["dataset"])
    return found, seen


def old_councils(code, found):
    """The datasets each council that code replaced has, [] if it replaced none."""
    _, ids = REPLACED.get(code, (None, []))
    return [found.get(f"local-authority:{i}", set()) for i in ids]


def datasets_for(code, organisation, found):
    """What a council publishes itself, and what every council it replaced does."""
    old = old_councils(code, found)
    return found.get(organisation, set()) | (set.intersection(*old) if old else set())


def brownfield_reason(code, found):
    """Why a council has no brownfield land register on the platform, in a sentence."""
    old = old_councils(code, found)
    have = sum(1 for datasets in old if BROWNFIELD in datasets)
    if have:
        return (f"The Planning Data platform collects registers for only part of the area, from {have} of the "
                f"{len(old)} councils it replaced in {REPLACED[code][0]}, and none from the council itself.")
    return ("The Planning Data platform doesn't collect one from the council. If the council publishes one on its "
            "own website, it isn't in a form the platform can use.")


def fetch(context):
    rows = list(csv.DictReader(io.StringIO(get_text(PROVISION))))
    missing = COLUMNS - set(rows[0] if rows else [])
    if missing:
        raise KeyError(f"The provision summary has no {sorted(missing)} columns")
    found, seen = provided(rows)
    organisation_for = codes(get_json(ORGANISATIONS))
    today = datetime.date.today()
    result = Result(id=ID, title="Planning Data: data provided by each planning authority", url=PAGE,
                    period=today.strftime("%B %Y"), published=today.isoformat(), files=[PROVISION, ORGANISATIONS])
    for code in sorted(context["population"]):
        if not code.startswith("E"):
            continue  # the platform covers England only
        organisation = organisation_for.get(code)
        if organisation not in seen:
            result.notes.append(f"{code} isn't on the Planning Data platform")
            continue
        datasets = datasets_for(code, organisation, found)
        result.set(code, "planning_data", 100 * len(datasets & set(DATASETS)) / len(DATASETS))
        result.extra[code] = {"missing": [name for key, name in DATASETS.items() if key not in datasets]}
        has_register = BROWNFIELD in datasets
        result.check(code, "brownfield", has_register, "" if has_register else brownfield_reason(code, found))
    return result
