"""Net spending per resident in Scotland, from Scottish Local Government
Finance Statistics (the councils' audited Local Financial Returns).

Services are put under the same headings as England's where they match.
Social work is one figure: councils pay for much of it through their area's
Integration Joint Board, which in some areas covers children's services too,
so adults' and children's care can't be told apart fairly. Public health is
run by the NHS in Scotland, so there is no figure for it.
"""

from pipeline import govscot, sheets
from pipeline.http import get
from pipeline.sources import Result

ID = "scot_spending"
COLLECTION = "/collections/local-government-finance-statistics/"

SERVICES = {
    "Social work and social care": ["Total Social Work"],
    "Housing (general fund)": ["Total Non-HRA Housing"],
    "Environmental and regulatory": ["Total Environmental Services"],
    "Highways and transport": ["Total Roads and Transport"],
    "Culture and leisure": ["Total Culture and Related Services"],
    "Planning and development": ["Total Building, Planning & Development"],
    "Central services": ["Total Central Services"],
}
TOTAL = "All services excluding schools"


def fetch(context):
    page, period = govscot.latest(COLLECTION, r"/scottish-local-government-finance-statistics-(\d{4}-\d\d)/$")
    url = govscot.find(govscot.files(page + "documents/"), r"LA Level - Net Revenue Expenditure by Subservice")
    book = sheets.workbook(get(url))
    matcher, population = context["matcher"], context["population"]
    result = Result(id=ID, title=f"Scottish Government: Scottish Local Government Finance Statistics, {period}",
                    url=page, period=period, published=govscot.published(page), files=[url])
    for name in book.sheet_names:
        code = matcher.code(name)
        if code not in population or not code.startswith("S"):
            continue  # Scotland as a whole, joint boards and transport partnerships
        rows = book.get_sheet_by_name(name).to_python()
        head = sheets.header_row(rows, r"^Subservice$")
        net = sheets.column(rows[head], r"^Net Revenue Expenditure")
        lines = {sheets.text(row[0]): sheets.num(row[net]) for row in rows[head + 1:] if sheets.text(row[0])}
        per_head = 1000 / population[code]  # figures are in £ thousands
        for label, services in SERVICES.items():
            values = [lines.get(s) for s in services]
            if None not in values:
                result.set(code, label, sum(values) * per_head)
        general, education = lines.get("Total General Fund (GF)"), lines.get("Total Education")
        if general is not None and education is not None:
            result.set(code, TOTAL, (general - education) * per_head)
    if len(result.values) != 32:
        result.notes.append(f"Spending figures for {len(result.values)} councils, not 32")
    return result
