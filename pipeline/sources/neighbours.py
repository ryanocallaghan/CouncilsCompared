"""The Department for Education's statistical neighbours.

For each children's services authority, the ten authorities most like it on
the things that drive demand for services (deprivation, population, and so
on). County councils are left out of each list, as they are not compared
here, so a council can have fewer than ten.
"""

from pipeline import govuk, sheets
from pipeline.http import get
from pipeline.sources import Result

ID = "neighbours"
PAGE = "/government/publications/local-authority-interactive-tool-lait"


def fetch(context):
    item = govuk.content(PAGE)
    attachment = govuk.find_attachment(item, r"statistical neighbour")
    rows = sheets.sheet(sheets.workbook(get(attachment["url"])), r"^ModelWide$")
    head = sheets.header_row(rows, r"^la_code$")
    header = rows[head]
    cols = [sheets.column(header, rf"^SN_{n}$") for n in range(1, 11)]
    councils = context["councils"]
    result = Result(id=ID, title="Department for Education: Children's services statistical neighbours",
                    url=item["web_url"], period=item.get("public_updated_at", "")[:4],
                    published=govuk.published(item), files=[attachment["url"]])
    for row in rows[head + 1:]:
        code = sheets.code(row[0])
        if code in councils:
            result.extra[code] = [n for n in (sheets.code(row[c]) for c in cols) if n in councils]
    return result
