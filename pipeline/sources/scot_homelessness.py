"""Homelessness in Scotland, from the Scottish Government's annual tables.

Scotland has no prevention and relief duties like England's, so its
measures are its own: temporary accommodation at 31 March, how long
households spent in it, and how many homeless households found a settled
home (a council or housing association tenancy, or a private let).
"""

import re

from pipeline import govscot, sheets
from pipeline.http import get
from pipeline.sources import Result

ID = "scot_homelessness"
COLLECTION = "/collections/homelessness-statistics/"


def table(book, name):
    """The header and rows of the first table on a worksheet, up to the
    blank row after it."""
    rows = sheets.sheet(book, rf"^{name}$")
    head = sheets.header_row(rows, r"^Local Authority$")
    body = []
    for row in rows[head + 1:]:
        if not sheets.text(row[0]):
            break
        body.append(row)
    return rows[head], body


def fetch(context):
    page, period = govscot.latest(COLLECTION, r"/homelessness-in-scotland-(\d{4}-\d\d)/$")
    url = govscot.find(govscot.files(page + "documents/"), r"^Main tables")
    book = sheets.workbook(get(url))
    matcher, population = context["matcher"], context["population"]
    result = Result(id=ID, title=f"Scottish Government: Homelessness in Scotland, {period}", url=page,
                    period=period, published=govscot.published(page), files=[url])

    def councils(rows):
        for row in rows:
            code = matcher.code(row[0])
            if code in population and code.startswith("S"):
                yield code, row

    # Households in temporary accommodation at 31 March, and all households
    header, rows = table(book, "T33")
    rate = sheets.column(header, r"temporary accommodation.*Rate per 10,000")
    households = sheets.column(header, r"^All households - Number")
    for code, row in councils(rows):
        if sheets.num(row[rate]) is not None:
            result.set(code, "ta_rate", sheets.num(row[rate]) / 10)  # per 1,000, as for England
        if sheets.num(row[households]):
            result.extra.setdefault("households", {})[code] = round(sheets.num(row[households]))

    # Average days in temporary accommodation, for cases that closed in each year
    header, rows = table(book, "T38")
    years = [(i, sheets.text(h)) for i, h in enumerate(header) if re.fullmatch(r"\d{4}-\d\d", sheets.text(h))]
    for code, row in councils(rows):
        for i, year in years:
            result.trend(code, "ta_days", year, sheets.num(row[i]), places=0)
        latest = years[-1][0]
        result.set(code, "ta_days", sheets.num(row[latest]), places=0)

    # Unintentionally homeless households (where contact was kept) who found a settled home
    header, rows = table(book, "T55")
    settled = sheets.column(header, r"^Proportion securing settled accommodation")
    for code, row in councils(rows):
        if sheets.num(row[settled]) is not None:
            result.set(code, "settled", sheets.num(row[settled]) * 100)

    if len(result.values) != 32:
        result.notes.append(f"Homelessness figures for {len(result.values)} councils, not 32")
    return result
