"""Ofsted's latest judgement of each council's children's services."""

import datetime
import re

from pipeline import govuk, sheets
from pipeline.http import get
from pipeline.sources import Result

ID = "ofsted"
COLLECTION = "/government/collections/childrens-social-care-statistics"
GRADES = ["Outstanding", "Good", "Requires improvement to be good", "Inadequate"]


def iso_date(value):
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.strftime("%Y-%m-%d")
    match = re.fullmatch(r"(\d\d?)/(\d\d?)/(\d{4})", sheets.text(value))
    if match:
        day, month, year = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return sheets.text(value)[:10]


def grade(text):
    text = sheets.text(text)
    if text.lower().startswith("requires improvement"):
        return "Requires improvement"
    return text.capitalize()


def fetch(context):
    item, attachment = govuk.latest(COLLECTION, r"^Local authority inspection outcomes as at", r"^Underlying data")
    rows = sheets.sheet(sheets.workbook(get(attachment["url"])), r"^Inspections_as_at")
    head = sheets.header_row(rows, r"^Local authority area code$")
    header = rows[head]
    ons = sheets.column(header, r"^Local authority area code$")
    overall = sheets.column(header, r"^Overall effectiveness$")
    inspected = sheets.column(header, r"^Inspection date$")
    link = sheets.column(header, r"^Web link$")
    period = re.sub(r"^.*as at ", "", item["title"])
    result = Result(id=ID, title=f"Ofsted: {item['title']}", url=item["web_url"], period=period,
                    published=govuk.published(item), files=[attachment["url"]])
    for row in rows[head + 1:]:
        code = sheets.code(row[ons])
        if code in context["population"] and sheets.text(row[overall]):
            result.extra[code] = {"grade": grade(row[overall]), "inspected": iso_date(row[inspected]),
                                  "report": sheets.text(row[link])}
    return result
