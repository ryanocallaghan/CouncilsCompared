"""Council tax: how much of the year's bills councils collected, and what Band D costs."""

import re

from pipeline import govuk, sheets
from pipeline.http import get
from pipeline.sources import Result

COLLECTION = "/government/collections/council-tax-statistics"


def collection_rates(context):
    item, attachment = govuk.latest(COLLECTION, r"^Collection rates for Council Tax", r"^Table 6\b")
    rows = sheets.sheet(sheets.workbook(get(attachment["url"])), r"^Table_6a")
    head = sheets.header_row(rows, r"^ONS Code$")
    header = rows[head]
    ons = sheets.column(header, r"^ONS Code$")
    rate = sheets.column(header, r"as a percentage", last=True)
    match = re.search(r"(\d{4}-\d\d)", sheets.text(header[rate]))
    result = Result(id="ctax", title=f"MHCLG: {item['title']}", url=item["web_url"],
                    period=match.group(1) if match else str(govuk.years_in(item["title"])),
                    published=govuk.published(item), files=[attachment["url"]])
    for row in rows[head + 1:]:
        code = sheets.code(row[ons])
        if code in context["population"]:
            result.set(code, "ctax_collect", sheets.num(row[rate]))
    return result


def band_d(context):
    item, attachment = govuk.latest(COLLECTION, r"^Council Tax levels set by local authorities", r"Table 10\b")
    rows = sheets.sheet(sheets.workbook(get(attachment["url"])), r"^Data_Billing$")
    head = sheets.header_row(rows, r"^ONS Code$")
    header = rows[head]
    ons = sheets.column(header, r"^ONS Code$")
    area = sheets.column(header, r"council tax for area of the billing authority including both local and major")
    # Who the Band D bill goes to: the council (with and without parish and
    # other local precepts), and the major preceptors
    parts = {
        "with_local": sheets.column(header, r"^8\. Average .*including Adult Social Care precept and local precepts.*current year"),
        "council": sheets.column(header, r"^9\. Average .*excluding local precepts.*current year"),
        "gla_or_county": sheets.column(header, r"major precepting authorities.*\(county or GLA\)"),
        "police": sheets.column(header, r"major precepting authorities.*\(police\)"),
        "fire": sheets.column(header, r"major precepting authorities.*\(fire\)"),
        "combined": sheets.column(header, r"major precepting authorities.*\(combined authority\)"),
    }
    year = govuk.years_in(item["title"])
    result = Result(id="band_d", title=f"MHCLG: {item['title']}", url=item["web_url"],
                    period=f"{year - 1}-{str(year)[2:]}", published=govuk.published(item),
                    files=[attachment["url"]])
    for row in rows[head + 1:]:
        code = sheets.code(row[ons])
        if code in context["population"]:
            result.set(code, "band_d", sheets.num(row[area]), places=2)
            values = {name: sheets.num(row[col]) or 0.0 for name, col in parts.items()}
            result.extra[code] = {
                "council": round(values["council"], 2),
                "parish": round(values["with_local"] - values["council"], 2),
                "gla_or_county": round(values["gla_or_county"], 2),
                "police": round(values["police"], 2),
                "fire": round(values["fire"], 2),
                "combined": round(values["combined"], 2),
            }
    return result
