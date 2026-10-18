"""Net spending per resident, from MHCLG's revenue outturn (RSX)."""

from pipeline import govuk, sheets
from pipeline.http import get
from pipeline.sources import Result

ID = "spending"
COLLECTION = "/government/collections/local-authority-revenue-expenditure-and-financing"

# What the site shows: the RSX service, or a calculation from them
SERVICES = {
    "Children's social care": ["Children Social Care"],
    "Adult social care": ["Adult Social Care"],
    "Public health": ["Public Health"],
    "Housing (general fund)": ["Housing services (GFRA only)"],
    "Environmental and regulatory": ["Environmental and regulatory services"],
    "Highways and transport": ["Highways and transport services"],
    "Culture and leisure": ["Cultural and related services"],
    "Planning and development": ["Planning and development services"],
    "Central services": ["Central services"],
}
TOTAL = "All services excluding schools"


def fetch(context):
    item, attachment = govuk.latest(COLLECTION, r"individual local authority data\s*-\s*outturn", r"\(RSX\)")
    rows = sheets.sheet(sheets.workbook(get(attachment["url"])), r"^RSX_LA_Data")
    head = sheets.header_row(rows, r"^ONS Code$")
    header = rows[head]
    ons = sheets.column(header, r"^ONS Code$")

    def net(service):
        return sheets.column(header, rf"^{service} - Net Current Expenditure")

    cols = {label: [net(s) for s in services] for label, services in SERVICES.items()}
    total, education = net("Total Service Expenditure"), net("Education services")
    year = govuk.years_in(item["title"])
    period = f"{year - 1}-{str(year)[2:]}"
    population = context["population"]
    result = Result(id=ID, title=f"MHCLG: Revenue outturn, {period}", url=item["web_url"], period=period,
                    published=govuk.published(item), files=[attachment["url"]])
    for row in rows[head + 1:]:
        code = sheets.code(row[ons])
        if code not in population:
            continue
        per_head = 1000 / population[code]  # figures are in £ thousands
        for label, services in cols.items():
            values = [sheets.num(row[c]) for c in services]
            if None not in values:
                result.set(code, label, sum(values) * per_head)
        if sheets.num(row[total]) is not None and sheets.num(row[education]) is not None:
            result.set(code, TOTAL, (sheets.num(row[total]) - sheets.num(row[education])) * per_head)
    return result
