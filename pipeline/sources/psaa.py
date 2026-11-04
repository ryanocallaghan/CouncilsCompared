"""Whether each council's latest accounts were audited by the legal deadline, from PSAA.

After years of delayed audits, the government set a deadline (a "backstop
date") for each year's audit of English councils' accounts: 28 February 2025
for 2023-24, 27 February 2026 for 2024-25, and so on. Public Sector Audit
Appointments, which appoints most councils' auditors, publishes each month
which audits have been signed off, and when.

The check is for the latest year whose deadline has passed: did the
auditor sign their opinion by then? An opinion signed by the deadline
counts even if it was "disclaimed" (the auditor couldn't give assurance,
often because of the backlog from earlier years).
"""

import datetime
import html
import re

from pipeline import sheets
from pipeline.http import get, get_text
from pipeline.sources import Result

ID = "psaa"
LISTING = "https://www.psaa.co.uk/managing-audit-quality/monthly-audit-opinion-data/"
SINGLE_TIER = r"^(Unitary Authority|Metropolitan District Council|London Borough Council)$"
ON_TIME = r"^Delivered by backstop"


def latest_month(listing):
    """The address of the newest month's page, from the list of monthly pages."""
    pages = re.findall(r'href="(https://www\.psaa\.co\.uk/managing-audit-quality/monthly-audit-opinion-data/'
                       r'([a-z]+)-(\d{4})-audit-opinion-data/)"', listing)
    months = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
              "november", "december"]
    dated = [(int(year), months.index(month) + 1, url) for url, month, year in pages if month in months]
    if not dated:
        raise ValueError("No monthly audit opinion pages on PSAA's list")
    return max(dated)


def backstops(page):
    """{"2024-2025": date} for each audit year in the month's table of deadlines."""
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
    found = {}
    for start, end, day, month, year in re.findall(r"\b(\d{4})/(\d{2}) (\d{1,2}) ([A-Z][a-z]{2})[a-z]* (\d{4})", text):
        date = datetime.datetime.strptime(f"{day} {month} {year}", "%d %b %Y").date()
        found.setdefault(f"{start}-{int(start[:2] + end)}", date)
    return found


def signed(value):
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime) else value.date()
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2}).*", sheets.text(value))
    return datetime.date(*map(int, match.groups())) if match else None


def judge(status, when, year, deadline):
    """(pass, reason) for one council's audit."""
    status = sheets.text(status)
    years = year.replace("-20", "-")  # "2024-2025" -> "2024-25"
    if re.match(ON_TIME, status, re.I):
        return True, f"Its auditor signed off its {years} accounts on {when:%-d %B %Y}, by the deadline of {deadline:%-d %B %Y}." \
            if when else f"Its auditor signed off its {years} accounts by the deadline of {deadline:%-d %B %Y}."
    if when:
        return False, (f"Its auditor signed off its {years} accounts on {when:%-d %B %Y}, after the deadline of "
                       f"{deadline:%-d %B %Y}.")
    return False, f"Its auditor still hadn't signed off its {years} accounts, due by {deadline:%-d %B %Y}."


def fetch(context):
    year_number, month_number, month_page = latest_month(get_text(LISTING))
    page = get_text(month_page)
    deadlines = backstops(page)
    today = datetime.date.today()
    passed = {year: date for year, date in deadlines.items() if date < today}
    if not passed:
        raise ValueError(f"No audit year with a deadline that has passed on {month_page}")
    year = max(passed)
    deadline = passed[year]
    files = re.findall(r'href="([^"]+\.xlsx)"', page)
    if not files:
        raise ValueError(f"No spreadsheet on {month_page}")
    rows = sheets.sheet(sheets.workbook(get(files[0])), rf"^{year}$")
    header = rows[sheets.header_row(rows, r"^Organisation Name$")]
    name, kind = sheets.column(header, r"^Organisation Name$"), sheets.column(header, r"^Sector Type$")
    status, when = sheets.column(header, r"^Audit Status$"), sheets.column(header, r"^Audit Signed Date$")
    month = datetime.date(year_number, month_number, 1).strftime("%B %Y")
    result = Result(id=ID, title="PSAA: monthly audit opinion data", url=month_page,
                    period=f"{year.replace('-20', '-')} accounts, as at {month}", files=[month_page, files[0]])
    for row in rows[rows.index(header) + 1:]:
        if not re.match(SINGLE_TIER, sheets.text(row[kind])):
            continue
        code = context["matcher"].code(sheets.text(row[name]))
        if not code or code not in context["population"]:
            result.notes.append(f"No council for {sheets.text(row[name])!r}")
            continue
        passed_, reason = judge(row[status], signed(row[when]), year, deadline)
        result.check(code, "accounts_audited", passed_, reason)
    missing = [c for c in context["population"] if c.startswith("E") and c not in result.checks]
    if missing:
        result.notes.append(f"Not in PSAA's data (they may appoint their own auditor): {', '.join(sorted(missing))}")
    return result
