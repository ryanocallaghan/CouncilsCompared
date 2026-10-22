"""Scottish councils, from the Local Government Benchmarking Framework (LGBF).

Every Scottish council reports the same indicators to the Improvement
Service, which publishes them on the Spatial Hub under the Open Government
Licence. Each indicator has its own latest year, kept in extra["periods"].

The LGBF also puts councils in "family groups" of eight similar councils.
The groups for people's services (education, social work, housing) are by
deprivation, like England's statistical neighbours, so they are used for the
"similar councils" comparison.
"""

import csv
import io

from pipeline.http import get_json, get_text
from pipeline.sources import Result

ID = "lgbf"
API = "https://data.spatialhub.scot/api/3/action/package_show?id=local_government_benchmarking_framework-is"
PAGE = "https://data.spatialhub.scot/dataset/local_government_benchmarking_framework-is"

# LGBF indicator -> the measure it gives (see web/model.py MEASURES)
INDICATORS = {
    "CORP07": "ctax_collect",
    "ENV06": "recycling",
    "ENV03c": "street_clean",
    "ENV07a": "bins_satisfied",
    "ENV07b": "streets_satisfied",
    "HSN03": "housing_quality",
    "HSN04b": "repair_days",
    "CHN13a": "literacy",
    "CHN13b": "numeracy",
    "CHN11": "destinations",
    "CHN19a": "attendance",
    "SW04b": "care_impact",
    "SW07": "care_graded",
    "SW08": "delayed_discharge",
}
TRENDS = {"ENV06": "recycling"}  # also drawn over time, as for England
FAMILY = "CHN04"  # an indicator grouped by deprivation, for the family groups


def resource(package, name):
    return next(r["url"] for r in package["resources"] if r["name"] == name)


def fetch(context):
    package = get_json(API)["result"]
    data_url = resource(package, "LGBF Data Table Cash")
    info_url = resource(package, "LGBF Indicators Information")
    info = {r["Code"]: r for r in csv.DictReader(io.StringIO(get_text(info_url).lstrip("﻿")))}
    rows = list(csv.DictReader(io.StringIO(get_text(data_url).lstrip("﻿"))))
    matcher, population = context["matcher"], context["population"]
    result = Result(id=ID, title="Improvement Service: Local Government Benchmarking Framework", url=PAGE,
                    period="", published=package["metadata_modified"][:10], files=[data_url, info_url])

    series = {}  # {(code, indicator): {year: value}}
    families = {}  # {family group: [code]}
    unmatched = set()
    for row in rows:
        indicator = row["Indicators_Information_Code"]
        if indicator not in INDICATORS and indicator != FAMILY:
            continue
        code = matcher.code(row["LA_Information_LocalAuthority"])
        if code not in population or not code.startswith("S"):
            unmatched.add(row["LA_Information_LocalAuthority"])
            continue
        year = row["LA_Data_LGBF_Year"]
        if indicator == FAMILY:
            if year == max(r["LA_Data_LGBF_Year"] for r in rows if r["Indicators_Information_Code"] == FAMILY):
                families.setdefault(row["LA_Data_FamilyGroup"], []).append(code)
            continue
        try:
            value = float(row["LA_Data_LA_IndicatorCash"])
        except ValueError:
            continue  # "NA", or blank
        if "%" in info[indicator]["NumberFormat"]:
            value *= 100  # given as a share
        series.setdefault((code, indicator), {})[year] = value

    if unmatched:
        raise RuntimeError(f"Councils not matched to an ONS code: {sorted(unmatched)}")
    periods = {}
    for indicator, measure in INDICATORS.items():
        years = [y for (_, i), values in series.items() if i == indicator for y in values]
        if not years:
            result.notes.append(f"No figures for {indicator}")
            continue
        latest = max(years)
        periods[measure] = latest
        for (code, i), values in series.items():
            if i == indicator:
                result.set(code, measure, values.get(latest))
                if indicator in TRENDS:
                    for year, value in values.items():
                        result.trend(code, TRENDS[indicator], year, value)
    result.period = max(periods.values())
    result.extra = {
        "periods": periods,
        # The other councils in each council's family group
        "neighbours": {code: sorted(c for c in group if c != code)
                       for group in families.values() for code in group},
    }
    if len(result.values) != 32:
        result.notes.append(f"Figures for {len(result.values)} councils, not 32")
    return result
