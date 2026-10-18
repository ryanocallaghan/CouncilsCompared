"""Upheld Ombudsman decisions by service area, counted from published decisions.

The annual review data only splits complaints received by service, so the
Ombudsman's decision search is used to count upheld decisions about
children's services, special educational needs and homelessness. Two
financial years are counted together, to smooth out small numbers.

The search is paged ten at a time, so this makes several hundred requests:
it waits a second between each, and only runs again once a month.
"""

import re
import time
import urllib.parse
from collections import Counter

from pipeline.http import get_text
from pipeline.sources import Result

ID = "lgo_decisions"
MAX_AGE_DAYS = 28  # how often to search again (see pipeline.update)
SEARCH = "https://www.lgo.org.uk/Decisions/SearchResults"
PAGE = "https://www.lgo.org.uk/decisions"
ITEM = re.compile(r'class="mainItemLabel"><a href="/decisions/([^/"]+)/([^/"]+)/[^"]+">([^<]+?)\s*\(')
COUNT = re.compile(r"Your search has (\d+) results?")

MEASURES = {
    "om_children": lambda category, sub: category.startswith("children"),
    "om_sen": lambda category, sub: sub == "special-educational-needs",
    "om_homeless": lambda category, sub: sub == "homelessness",
}


def search(name, start, end, page):
    query = urllib.parse.urlencode({"fd": start, "td": end, "dc": "u+", "aname": name, "page": page})
    return get_text(f"{SEARCH}?{query}", pause=1)


def decisions(name, start, end):
    """Counter of (category, subcategory) for one council's upheld decisions."""
    counts = Counter()
    first = search(name, start, end, 1)
    match = COUNT.search(first)
    total = int(match.group(1)) if match else 0
    pages = -(-total // 10)
    for page in range(1, pages + 1):
        html = first if page == 1 else search(name, start, end, page)
        for category, sub, label in ITEM.findall(html):
            # The search matches names containing the text; keep exact ones
            if label.strip() == name:
                counts[(category, sub)] += 1
    return counts


def fetch(context):
    latest = context["results"]["lgo"].extra["latest"]  # the last financial year in the annual review data
    start, end = f"{latest - 1}-04-01", f"{latest + 1}-03-31"
    period = f"{latest - 1}-{str(latest)[2:]} and {latest}-{str(latest + 1)[2:]}"
    population = context["population"]
    result = Result(id=ID, title="Local Government and Social Care Ombudsman: published decisions",
                    url=PAGE, period=period, extra={"checked": time.strftime("%Y-%m-%d"), "counts": {}})
    for code, name in sorted(context["results"]["lgo"].extra["names"].items()):
        counts = decisions(name, start, end)
        result.extra["counts"][code] = {f"{c}/{s}": n for (c, s), n in sorted(counts.items())}
        for measure, matches in MEASURES.items():
            n = sum(v for (c, s), v in counts.items() if matches(c, s))
            result.set(code, measure, n / population[code] * 100_000)
    return result
