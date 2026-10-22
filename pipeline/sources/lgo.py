"""The Local Government and Social Care Ombudsman's annual review data.

Three spreadsheets a year: complaints received, decisions made, and remedy
and compliance outcomes. The Ombudsman names councils rather than giving
ONS codes, so names are matched (see pipeline.names).
"""

import re

from pipeline import sheets
from pipeline.http import get, get_text
from pipeline.sources import Result

ID = "lgo"
PAGE = "https://www.lgo.org.uk/information-centre/reports/annual-review-reports/local-government-complaint-reviews"
FILE = re.compile(r'href="(https://www\.lgo\.org\.uk/assets/attach/\d+/(\d)-[A-Za-z-]+?-(\d\d)-(\d\d)\.xlsx)"')
TREND_YEARS = 4


def files():
    """{(kind, start year): url}, kind 1 = received, 2 = decided, 3 = remedies."""
    found = {}
    for url, kind, start, _ in FILE.findall(get_text(PAGE)):
        found[(int(kind), 2000 + int(start))] = url
    return found


def table(url):
    rows = sheets.sheet(sheets.workbook(get(url)), r"^Data$")
    head = sheets.header_row(rows, r"^Authority Name$")
    return rows[head], rows[head + 1:]


def per_100k(count, population):
    return count / population * 100_000


def fetch(context):
    found = files()
    latest = max(year for kind, year in found if kind == 3)
    period = f"{latest}-{str(latest + 1)[2:]}"
    matcher, population = context["matcher"], context["population"]
    result = Result(id=ID, title=f"Local Government and Social Care Ombudsman: annual review data, {period}",
                    url=PAGE, period=period)
    names = {}

    header, rows = table(found[(1, latest)])
    result.files.append(found[(1, latest)])
    total = sheets.column(header, r"^Total$")
    for row in rows:
        code = matcher.code(row[0])
        if code in population and sheets.num(row[total]) is not None:
            names[code] = sheets.text(row[0])
            result.set(code, "om_received", per_100k(sheets.num(row[total]), population[code]))

    # Upheld decisions, this year and the years before for the trend
    for year in range(latest - TREND_YEARS + 1, latest + 1):
        url = found.get((2, year))
        if not url:
            continue
        result.files.append(url)
        header, rows = table(url)
        upheld = sheets.column(header, r"^Upheld$")
        label = f"{year}-{str(year + 1)[2:]}"
        for row in rows:
            code = matcher.code(row[0])
            if code in population and sheets.num(row[upheld]) is not None:
                value = per_100k(sheets.num(row[upheld]), population[code])
                result.trend(code, "om_upheld", label, value)
                if year == latest:
                    result.set(code, "om_upheld", value)

    header, rows = table(found[(3, latest)])
    result.files.append(found[(3, latest)])
    before = sheets.column(header, r"^Upheld cases where the authority provided a satisfactory remedy before")
    timely = sheets.column(header, r"^Percentage of compliance outcomes recorded as delivered on time")
    cases = sheets.column(header, r"^Number of cases with a compliance outcome")
    upheld_count = sheets.column(header, r"^Number of upheld complaints")
    for row in rows:
        code = matcher.code(row[0])
        if code not in population:
            continue
        # A percentage of a handful of cases says little, so leave those out
        if (sheets.num(row[upheld_count]) or 0) >= 5 and sheets.num(row[before]) is not None:
            result.set(code, "om_remedy_before", sheets.num(row[before]) * 100)
        if (sheets.num(row[cases]) or 0) >= 5 and sheets.num(row[timely]) is not None:
            result.set(code, "om_timely", sheets.num(row[timely]) * 100)

    missing = {code for code in population if code.startswith("E")} - set(names)  # England only
    if missing:
        result.notes.append(f"No Ombudsman figures for {len(missing)} councils: {sorted(missing)}")
    result.extra = {"names": names, "latest": latest}
    return result
