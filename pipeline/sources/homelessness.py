"""Temporary accommodation and homelessness case outcomes, from MHCLG's quarterly tables."""

import re

from pipeline import govuk, sheets
from pipeline.http import get
from pipeline.sources import Result

ID = "homelessness"
PAGE = "/government/statistical-data-sets/live-tables-on-homelessness"
QUARTERS = {"January to March": 1, "April to June": 2, "July to September": 3, "October to December": 4}
TITLE = re.compile(r"^Detailed local authority level tables: (" + "|".join(QUARTERS) + r") (\d{4})", re.I)


def latest_attachment(item):
    candidates = []
    for attachment in govuk.attachments(item):
        match = TITLE.match(attachment.get("title", ""))
        if match and "accessible" not in attachment["title"].lower():
            quarter = {k.lower(): v for k, v in QUARTERS.items()}[match.group(1).lower()]
            candidates.append(((int(match.group(2)), quarter), attachment, f"{match.group(1)} {match.group(2)}"))
    return max(candidates, key=lambda c: c[0])


def table(book, name):
    rows = sheets.sheet(book, rf"^{name}$")
    head = sheets.header_row(rows, r"^Organisation Identification Code$")
    return rows[head], [r for r in rows[head + 1:] if sheets.code(r[0])]


def share(part, whole, minimum=10):
    if part is None or not whole or whole < minimum:
        return None
    return part / whole * 100


def fetch(context):
    item = govuk.content(PAGE)
    _, attachment, period = latest_attachment(item)
    book = sheets.workbook(get(attachment["url"]))
    population = context["population"]
    result = Result(id=ID, title=f"MHCLG: Statutory homelessness, {period}", url=item["web_url"],
                    period=period, published=govuk.published(item), files=[attachment["url"]])

    header, rows = table(book, "TA1")
    rate = sheets.column(header, r"^Households in TA Total \(per thousand\)")
    households = sheets.column(header, r"^Households in area")
    for row in rows:
        code = sheets.code(row[0])
        if code in population:
            result.set(code, "ta_rate", sheets.num(row[rate]))
            if sheets.num(row[households]):
                result.extra.setdefault("households", {})[code] = round(sheets.num(row[households]) * 1000)

    header, rows = table(book, "TA4c")
    total = sheets.column(header, r"^Households in TA Total")
    long_cols = [i for i, h in enumerate(header) if re.search(r"(2 to 5 years|5 or more years)$", sheets.text(h))]
    for row in rows:
        code = sheets.code(row[0])
        if code in population:
            # Small numbers are suppressed ([c]): almost always families in
            # B&Bs, which are few, so they are counted as none
            parts = [0.0 if sheets.text(row[i]) == "[c]" else sheets.num(row[i]) for i in long_cols]
            if None not in parts:
                result.set(code, "ta_long", share(sum(parts), sheets.num(row[total])))

    for name, measure, ended, secured in [
        ("P1", "prevention", r"^Households whose prevention duty ended", r"^Households who secured accommodation"),
        ("R1", "relief", r"^Households whose relief duty ended", r"^Secured accommodation for 6 or more months"),
    ]:
        header, rows = table(book, name)
        ended_col, secured_col = sheets.column(header, ended), sheets.column(header, secured)
        for row in rows:
            code = sheets.code(row[0])
            if code in population:
                result.set(code, measure, share(sheets.num(row[secured_col]), sheets.num(row[ended_col])))
    return result
