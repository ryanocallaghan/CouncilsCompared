"""EHC plans issued within 20 weeks, from the Explore Education Statistics API."""

import csv
import io
import re

from pipeline.http import get_json, get_text
from pipeline.sources import Result

ID = "ehcp"
API = "https://api.education.gov.uk/statistics/v1"
SLUG = "education-health-and-care-plans"
PAGE = f"https://explore-education-statistics.service.gov.uk/find-statistics/{SLUG}"


def data_set():
    publications = get_json(f"{API}/publications?search=education%20health%20and%20care%20plans&pageSize=40")
    publication = next(p for p in publications["results"] if p["slug"] == SLUG)
    sets = get_json(f"{API}/publications/{publication['id']}/data-sets")["results"]
    return next(s for s in sets if re.search(r"timeliness.*20 weeks", s["title"], re.I))


def fetch(context):
    found = data_set()
    url = f"{API}/data-sets/{found['id']}/csv"
    rows = csv.DictReader(io.StringIO(get_text(url)))
    councils = context["councils"]
    result = Result(id=ID, title="Department for Education: Education, health and care plans", url=PAGE,
                    period="", published=found["latestVersion"]["published"][:10], files=[url])
    for row in rows:
        code = row.get("new_la_code")
        if (code in councils and row["geographic_level"] == "Local authority"
                and row["breakdown_topic"] in ("All EHC plans issued", "All EHC plans")
                and row["exemptions_flag"] == "Excluding exemptions"
                and row["timeliness"] == "Plans issued within 20 weeks"):
            try:
                value = float(row["ehc_plan_percent"])
            except ValueError:
                continue
            result.trend(code, "ehcp_20wk", row["time_period"], value)
    latest = max(p for t in result.trends.values() for p in t["ehcp_20wk"])
    result.period = latest
    for code, trends in result.trends.items():
        result.set(code, "ehcp_20wk", trends["ehcp_20wk"].get(latest))
    return result
