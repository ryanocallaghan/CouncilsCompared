"""Fly-tipping incidents and enforcement actions, from Defra (formerly ENV24).

The spreadsheet has a row per council and year, with incidents by where they
were found, what was dumped and how big they were, and every kind of action
the council took. Defra doesn't collect the weight of fly-tipped waste, and
stopped estimating clearance costs in 2017-18, so neither is used.
"""

import re

from pipeline import govuk, sheets
from pipeline.http import get
from pipeline.sources import Result

ID = "fly"
PAGE = "/government/statistical-data-sets/env24-fly-tipping-incidents-and-actions-taken-in-england"  # redirects

# Where fly-tips were found and what was dumped, for the council page:
# {label: heading in the spreadsheet}
LAND = {
    "Roads": "Highway Incidents",
    "Footpaths and bridleways": "Footpath / Bridleway Incidents",
    "Back alleys": "Back Alleyway Incidents",
    "Council land": "Council Land Incidents",
    "Private and residential land": "Private / Residential Incidents",
    "Commercial and industrial land": "Commercial / Industrial Incidents",
    "Farmland": "Agricultural Incidents",
    "Railways": "Railway Incidents",
    "Rivers and banks": "Watercourse / Bank Incidents",
}
WASTE = {
    "Household black bags": "Black Bags - Household Incidents",
    "Other household waste": "Other Household Waste Incidents",
    "Commercial black bags": "Black Bags - Commercial Incidents",
    "Other commercial waste": "Other Commercial Waste Incidents",
    "Building and demolition waste": "Constr / Demol / Excav Incidents",
    "Garden waste": "Green Incidents",
    "White goods": "White Goods Incidents",
    "Other electrical items": "Other Electrical Incidents",
    "Vehicle parts": "Vehicle Parts Incidents",
    "Tyres": "Tyres Incidents",
    "Asbestos": "Asbestos Incidents",
    "Clinical waste": "Clinical Incidents",
    "Chemicals, oil and fuel": "Chemical Drums, Oil, Fuel Incidents",
    "Animal carcasses": "Animal Carcass Incidents",
}
LARGE = ["Small Van Load Incidents", "Transit Van Load Incidents", "Tipper Lorry Load Incidents",
         "Significant / Multi Loads Incidents"]
FPN = ["Fixed Penalty Notices issued specifically for fly-tipping",
       "Fixed Penalty Notices issued for Household Duty of Care"]
# What the council did, for the council page, in the order of a case
ACTIONS = {
    "Investigations": "Investigation Actions",
    "Warning letters": "Warning Letter Actions",
    "Statutory notices": "Statutory Notice Actions",
    "Duty of care inspections": "Duty of Care Inspection Actions",
    "Fixed penalty notices": "Total Fixed Penalty Notice Actions",
    "Vehicles seized": "Vehicles seized",
    "Prosecutions": "Prosecution Actions",
    "Fines issued by courts": "Fine Outcomes (issued by courts)",
    "Prison sentences": "Custodial Sentence Outcomes",
}
MIN_INCIDENTS = 50  # fewer than this, and shares of incidents aren't compared


def data_attachment(item):
    candidates = [a for a in govuk.attachments(item)
                  if a.get("url", "").lower().endswith((".ods", ".xlsx"))
                  and re.search(r"reported by LAs|by local authority", a.get("title", ""), re.I)]
    return max(candidates, key=lambda a: (govuk.years_in(a["title"] + " " + a["url"]), a["url"].endswith(".ods")))


def by_code(rows):
    """{code: {year: {heading: cell}}} from a sheet with a row per council and year."""
    head = sheets.header_row(rows, r"^ONS code$|^LA code$|^Local authority code$")
    header = [sheets.text(h) for h in rows[head]]
    year_col = sheets.column(header, r"year")
    out = {}
    for row in rows[head + 1:]:
        code = sheets.code_in(row)
        year = sheets.text(row[year_col]).replace("/", "-")
        if code and re.fullmatch(r"\d{4}-\d\d", year):
            out.setdefault(code, {})[year] = dict(zip(header, row))
    return out


def total(row, headings):
    """The sum of some columns, or None if any is missing."""
    values = [sheets.num(row.get(h)) for h in headings]
    return None if None in values else sum(values)


def counts(row, labels):
    """[(label, count)] for the columns with any, largest first."""
    found = [(label, int(sheets.num(row.get(h)))) for label, h in labels.items() if sheets.num(row.get(h))]
    return sorted(found, key=lambda item: -item[1])


def fetch(context):
    item = govuk.content(PAGE)
    attachment = data_attachment(item)
    book = sheets.workbook(get(attachment["url"]))
    incidents = by_code(sheets.sheet(book, r"incidents"))
    actions = by_code(sheets.sheet(book, r"actions"))
    population = context["population"]
    latest = max(y for years in incidents.values() for y in years)
    result = Result(id=ID, title=f"Defra: {item['title']}", url=item["web_url"], period=latest,
                    published=govuk.published(item), files=[attachment["url"]])
    detail = result.extra.setdefault("detail", {})
    for code in population:
        years = incidents.get(code, {})
        row = years.get(latest)
        n = sheets.num(row.get("Total Incidents")) if row else None
        if n is None:
            continue
        acted = actions.get(code, {}).get(latest, {})
        a = sheets.num(acted.get("Total Actions"))
        result.set(code, "fly_rate", n / population[code] * 1000)
        if n >= MIN_INCIDENTS:
            if a is not None:
                result.set(code, "fly_enforce", a / n * 100)
            if total(acted, FPN) is not None:
                result.set(code, "fly_fpn", total(acted, FPN) / n * 100)
        for year, past in years.items():
            count = sheets.num(past.get("Total Incidents"))
            if count is not None:
                result.trend(code, "fly_rate", year, count / population[code] * 1000)
            fpn = total(actions.get(code, {}).get(year, {}), FPN)
            if count and count >= MIN_INCIDENTS and fpn is not None:
                result.trend(code, "fly_fpn", year, fpn / count * 100, places=2)
        detail[code] = {
            # Some councils count only fly-tips the public report, not those their own staff find
            "basis": "public" if re.search(r"public", sheets.text(row.get("Reporting basis")), re.I) else "all",
            "incidents": int(n),
            # Not compared: how big a fly-tip is depends on who dumped it, and councils record sizes differently
            "large": round(total(row, LARGE) / n * 100) if n >= MIN_INCIDENTS and total(row, LARGE) is not None
            else None,
            "land": counts(row, LAND)[:5],
            "waste": counts(row, WASTE)[:5],
            "actions": [(label, int(sheets.num(acted.get(h)) or 0)) for label, h in ACTIONS.items()
                        if sheets.num(acted.get(h)) is not None],
            "court_fines": sheets.num(acted.get("Total fines (£)")),
            "fpn_amount": sheets.num(acted.get("Fixed Penalty Amount")),
            "fpn_early": sheets.num(acted.get("Fixed Penalty Notice early payment amount")),
        }
    public = sum(1 for d in detail.values() if d["basis"] == "public")
    if public:
        result.notes.append(f"{public} councils count only fly-tips reported by the public")
    return result
