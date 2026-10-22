"""Complaints about Scottish councils, from the Scottish Public Services Ombudsman.

The Ombudsman publishes a year's statistics on a page per year, with a
spreadsheet of the complaints it received about each organisation. It names
councils ("The Highland Council"), so names are matched (see pipeline.names).

Few complaints are investigated in full in Scotland (most are settled at an
earlier stage), so upheld complaints are too few to compare councils on;
complaints received are compared instead.
"""

import re

from pipeline import sheets
from pipeline.http import get, get_text
from pipeline.sources import Result

ID = "spso"
WEB = "https://www.spso.org.uk"
PAGE = f"{WEB}/statistics"


def fetch(context):
    years = re.findall(r'href="/statistics-(\d{4}-\d\d)"', get_text(PAGE))
    period = max(years)
    page = f"{WEB}/statistics-{period}"
    match = re.search(r'href="(/sites/spso/files/statistics/ComplaintsReceivedBySubjectAndAuthority[^"]*\.xlsx)"',
                      get_text(page))
    if not match:
        raise RuntimeError(f"No complaints received spreadsheet on {page}")
    url = WEB + match.group(1)
    result = Result(id=ID, title=f"Scottish Public Services Ombudsman: statistics, {period}", url=page,
                    period=period, files=[url])

    rows = sheets.sheet(sheets.workbook(get(url)), r"Local Authority")
    head = sheets.header_row(rows, r"^Aberdeen City Council$")
    header = rows[head]
    total = next(row for row in reversed(rows) if sheets.text(row[0]) == "Total")
    matcher, population = context["matcher"], context["population"]
    for i, name in enumerate(header):
        code = matcher.code(name)
        if code in population and code.startswith("S") and sheets.num(total[i]) is not None:
            result.set(code, "om_received", sheets.num(total[i]) / population[code] * 100_000)
    if len(result.values) != 32:
        result.notes.append(f"Ombudsman figures for {len(result.values)} councils, not 32")
    return result
