"""Website accessibility scores from the Silktide Index.

The index tests every UK council website each month against WCAG 2.2 AA.
Its pages carry their data as JSON (Next.js), which is read here.
"""

import json
import re

from pipeline.http import get_text
from pipeline.sources import Result

ID = "silktide"
BASE = "https://index.silktide.com"
CATEGORY = f"{BASE}/category/council-uk"
METRIC = "wcag-22.score"


def page_data(url):
    html = get_text(url, pause=1)
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(match.group(1))["props"]["pageProps"]


def fetch(context):
    category = page_data(CATEGORY)
    timeframe = next(t for t in category["timeframes"] if t["slug"] == category["latestTimeframeSlug"])
    result = Result(id=ID, title="Silktide Index: UK councils", url=CATEGORY, period=timeframe["name"])
    matcher, population = context["matcher"], context["population"]
    for website in category["websites"]:
        code = matcher.code(website["name"])
        if code not in population or code in result.values:
            continue
        props = page_data(f"{BASE}/website/{website['slug']}")
        for snapshot in props["website"].get("websiteSnapshots", []):
            for metric in snapshot.get("metricSnapshots", []):
                if metric.get("metricType", {}).get("name") == METRIC:
                    result.set(code, "web_access", metric["numericValue"])
    missing = set(population) - set(result.values)
    if missing:
        result.notes.append(f"No Silktide score for {len(missing)} councils: {sorted(missing)}")
    return result
