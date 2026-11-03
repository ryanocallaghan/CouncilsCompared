"""Which planning datasets each council publishes, from MHCLG's Planning Data platform.

Planning authorities are asked to publish their planning data (conservation
areas, tree preservation orders and so on) in a standard form, which the
platform collects. Its performance database says, for each authority and
dataset, how many working endpoints (places the platform collects it from)
there are.

A council's figure is the share of eight datasets it publishes through at
least one working endpoint. The eight are the ones the platform expects from
most councils; every council is measured on all eight, whether or not the
platform lists them as expected from it yet. The brownfield land register,
which councils have had to publish since 2017, is kept as a yes or no in
extra.
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


def codes(organisations):
    """{organisation id: ONS code}, from the platform's list of organisations."""
    return {o["organisation"]: o["statistical-geography"]
            for group in organisations["organisations"].values() for o in group
            if o.get("statistical-geography")}


def provided(rows, code_for):
    """{ons code: set of datasets with a working endpoint}, and every code seen."""
    found, seen = {}, set()
    for row in rows:
        code = code_for.get(row["organisation"])
        if not code:
            continue
        seen.add(code)
        if int(row["active_endpoint_count"] or 0) > 0:
            found.setdefault(code, set()).add(row["dataset"])
    return found, seen


def fetch(context):
    rows = list(csv.DictReader(io.StringIO(get_text(PROVISION))))
    missing = COLUMNS - set(rows[0] if rows else [])
    if missing:
        raise KeyError(f"The provision summary has no {sorted(missing)} columns")
    found, seen = provided(rows, codes(get_json(ORGANISATIONS)))
    today = datetime.date.today()
    result = Result(id=ID, title="Planning Data: data provided by each planning authority", url=PAGE,
                    period=today.strftime("%B %Y"), published=today.isoformat(), files=[PROVISION, ORGANISATIONS])
    for code in sorted(context["population"]):
        if not code.startswith("E"):
            continue  # the platform covers England only
        if code not in seen:
            result.notes.append(f"{code} isn't on the Planning Data platform")
            continue
        datasets = found.get(code, set())
        result.set(code, "planning_data", 100 * len(datasets & set(DATASETS)) / len(DATASETS))
        result.extra[code] = {
            "missing": [name for key, name in DATASETS.items() if key not in datasets],
            "brownfield": BROWNFIELD in datasets,
        }
    return result
