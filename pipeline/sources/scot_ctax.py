"""Band D council tax in Scotland, from the Scottish Government's council tax datasets.

Scottish councils set one charge each: there are no police, fire or parish
precepts. Scottish Water's water and sewerage charges are collected with
council tax, but are not in these figures.
"""

import re

from pipeline import govscot, sheets
from pipeline.http import get, get_text
from pipeline.sources import Result

ID = "scot_band_d"
PAGE = f"{govscot.WEB}/publications/council-tax-datasets/"
FILE = re.compile(r'href="(/binaries/[^"]*Council%2BTax%2Bby%2BBand%2B-%2B(\d{4}-\d\d)[^"]*\.xlsx)"')


def fetch(context):
    found = {year: govscot.WEB + path for path, year in FILE.findall(get_text(PAGE))}
    if not found:
        raise RuntimeError(f"No council tax by band spreadsheet on {PAGE}")
    period = max(found)
    url = found[period]
    rows = sheets.sheet(sheets.workbook(get(url)), r"CT by Band")
    head = sheets.header_row(rows, r"^Band D$")
    band_d = sheets.column(rows[head], r"^Band D$")
    matcher, population = context["matcher"], context["population"]
    result = Result(id=ID, title=f"Scottish Government: Council Tax by band, {period}", url=PAGE,
                    period=period, published=govscot.published(PAGE), files=[url])
    for row in rows[head + 1:]:
        code = matcher.code(row[0])
        if code in population and code.startswith("S"):
            result.set(code, "band_d", sheets.num(row[band_d]), places=2)
            if sheets.num(row[band_d]):
                result.extra[code] = {"council": round(sheets.num(row[band_d]), 2)}  # all of it goes to the council
    if len(result.values) != 32:
        result.notes.append(f"Band D figures for {len(result.values)} councils, not 32")
    return result
