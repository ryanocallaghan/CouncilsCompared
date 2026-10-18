"""Tenant Satisfaction Measures, from the Regulator of Social Housing.

Every council that owns homes reports these each year: a tenant survey and
some performance figures. Councils that transferred their homes to a
housing association have none.
"""

from pipeline import govuk, names, sheets
from pipeline.http import get
from pipeline.sources import Result

ID = "tsm"
COLLECTION = "/government/collections/tenant-satisfaction-measures"

PERCEPTION = {
    "tsm_overall": r"\(TP01\)$",
    "tsm_maintained": r"\(TP04\)$",
    "tsm_safe": r"\(TP05\)$",
    "tsm_listens": r"\(TP06\)$",
}
MANAGEMENT = {
    "tsm_decent": r"^Proportion of homes that do not meet.*\(RP01\)",
    "tsm_repairs": r"^Proportion of non-emergency.*\(RP02 1\)",
    "tsm_complaints": r"^LCRA - Proportion of stage one complaints.*\(CH02 1\)",
}


def read(rows, measures, result, matcher, councils):
    head = sheets.header_row(rows, r"^Landlord name$")
    header = rows[head]
    kind = sheets.column(header, r"^Landlord type$")
    cols = {m: sheets.column(header, pattern, exclude=r"survey method") for m, pattern in measures.items()}
    for row in rows[head + 1:]:
        if sheets.text(row[kind]) != "LA":
            continue
        code = matcher.code(row[0])
        if code not in councils:
            continue
        for measure, col in cols.items():
            result.set(code, measure, sheets.num(row[col]))


def fetch(context):
    item, attachment = govuk.latest(COLLECTION, r"^Tenant Satisfaction Measures \d{4}", r"full data")
    year = govuk.years_in(item["title"])
    result = Result(id=ID, title=f"Regulator of Social Housing: {item['title']}", url=item["web_url"],
                    period=f"{year - 1}-{str(year)[2:]}", published=govuk.published(item),
                    files=[attachment["url"]])
    book = sheets.workbook(get(attachment["url"]))
    read(sheets.sheet(book, r"LCRA_Perception$"), PERCEPTION, result, context["matcher"], context["population"])
    read(sheets.sheet(book, r"Management_Info$"), MANAGEMENT, result, context["matcher"], context["population"])
    return result
