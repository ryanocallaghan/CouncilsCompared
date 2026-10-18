"""Fly-tipping incidents and enforcement actions, from Defra (formerly ENV24)."""

import re

from pipeline import govuk, sheets
from pipeline.http import get
from pipeline.sources import Result

ID = "fly"
PAGE = "/government/statistical-data-sets/env24-fly-tipping-incidents-and-actions-taken-in-england"  # redirects


def data_attachment(item):
    candidates = [a for a in govuk.attachments(item)
                  if a.get("url", "").lower().endswith((".ods", ".xlsx"))
                  and re.search(r"local authority|LA |incidents and actions", a.get("title", ""), re.I)]
    if not candidates:
        candidates = [a for a in govuk.attachments(item) if a.get("url", "").lower().endswith((".ods", ".xlsx"))]
    return max(candidates, key=lambda a: (govuk.years_in(a["title"] + " " + a["url"]), a["url"].endswith(".ods")))


def latest_by_code(rows, value_pattern):
    """{code: {year: value}} from a sheet with a row per council and year."""
    head = sheets.header_row(rows, r"^ONS code$|^LA code$|^Local authority code$")
    header = rows[head]
    year_col = sheets.column(header, r"year")
    value_col = sheets.column(header, value_pattern)
    out = {}
    for row in rows[head + 1:]:
        code = sheets.code_in(row)
        year = sheets.text(row[year_col]).replace("/", "-")
        if code and re.fullmatch(r"\d{4}-\d\d", year):
            out.setdefault(code, {})[year] = sheets.num(row[value_col])
    return out


def fetch(context):
    item = govuk.content(PAGE)
    attachment = data_attachment(item)
    book = sheets.workbook(get(attachment["url"]))
    incidents = latest_by_code(sheets.sheet(book, r"incidents"), r"^Total incidents")
    actions = latest_by_code(sheets.sheet(book, r"actions"), r"^Total actions")
    population = context["population"]
    latest = max(y for years in incidents.values() for y in years)
    result = Result(id=ID, title=f"Defra: {item['title']}", url=item["web_url"], period=latest,
                    published=govuk.published(item), files=[attachment["url"]])
    for code in population:
        n = incidents.get(code, {}).get(latest)
        a = actions.get(code, {}).get(latest)
        if n is None:
            continue
        result.set(code, "fly_rate", n / population[code] * 1000)
        if a is not None and n >= 50:
            result.set(code, "fly_enforce", a / n * 100)
        for year, count in incidents[code].items():
            if count is not None:
                result.trend(code, "fly_rate", year, count / population[code] * 1000)
    return result
