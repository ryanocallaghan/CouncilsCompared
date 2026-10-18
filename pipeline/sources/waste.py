"""Household waste recycling rates, from Defra's ENV18 tables."""

import re

from pipeline import govuk, sheets
from pipeline.http import get
from pipeline.sources import Result

ID = "waste"
PAGE = "/government/statistical-data-sets/env18-local-authority-collected-waste-annual-results-tables"


def latest_attachment(item):
    candidates = [a for a in govuk.attachments(item)
                  if re.search(r"local authority collected waste generation", a.get("title", ""), re.I)
                  and a.get("url", "").lower().endswith((".ods", ".xlsx"))]
    # Prefer .ods when both formats are published for a year
    return max(candidates, key=lambda a: (govuk.years_in(a["title"]), a["url"].endswith(".ods")))


def fetch(context):
    item = govuk.content(PAGE)
    attachment = latest_attachment(item)
    rows = sheets.sheet(sheets.workbook(get(attachment["url"])), r"^Table_3$")
    head = sheets.header_row(rows, r"^ONS code$")
    header = rows[head]
    year_col = sheets.column(header, r"^(Financial )?Year$")
    ons = sheets.column(header, r"^ONS code$")
    rate = sheets.column(header, r"^Percentage of household waste sent for reuse, recycling or composting")
    result = Result(id=ID, title="Defra: Local authority collected waste (ENV18)", url=item["web_url"],
                    period="", published=item.get("public_updated_at", "")[:10], files=[attachment["url"]])
    for row in rows[head + 1:]:
        code = sheets.code(row[ons])
        year = sheets.text(row[year_col]).replace("/", "-")
        value = sheets.num(row[rate])
        if code in context["population"] and value is not None and re.fullmatch(r"\d{4}-\d\d", year):
            # Some editions give a share (0.268), others a percentage (26.8)
            result.trend(code, "recycling", year, value * 100 if value <= 1 else value)
    latest = max(p for t in result.trends.values() for p in t["recycling"])
    result.period = latest
    for code, trends in result.trends.items():
        result.set(code, "recycling", trends["recycling"].get(latest))
    return result
