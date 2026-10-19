"""The most common council tax band in each neighbourhood, from the VOA.

The Valuation Office Agency publishes how many homes are in each band for
every lower layer super output area (about 1,500 people). There is no open
way to look up one home's band, so the calculator starts on the most common
band near the visitor's postcode and links to the VOA to check their own.
"""

import csv
import io
import zipfile

from pipeline import govuk
from pipeline.http import get
from pipeline.sources import Result

ID = "area_bands"
COLLECTION = "/government/collections/valuation-office-council-tax-statistics"
BANDS = "ABCDEFGH"


def fetch(context=None):
    item, attachment = govuk.latest(COLLECTION, r"^Council Tax: stock of properties", r"^CTSOP\s*1\.1")
    archive = zipfile.ZipFile(io.BytesIO(get(attachment["url"])))
    name = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
    rows = csv.DictReader(io.StringIO(archive.read(name).decode("utf-8-sig")))
    result = Result(id=ID, title=f"Valuation Office Agency: {item['title']}", url=item["web_url"],
                    period=str(govuk.years_in(item["title"])), published=govuk.published(item),
                    files=[attachment["url"]])
    for row in rows:
        if row["geography"] != "LSOA":
            continue
        counts = []
        for band in BANDS:
            value = row.get(f"band_{band.lower()}", "")
            counts.append(int(value) if value.isdigit() else 0)  # [c]: too few to show
        if sum(counts):
            # The most common band; on a tie, the lower one
            result.extra[row["ecode"]] = BANDS[counts.index(max(counts))]
    if len(result.extra) < 30_000:
        raise RuntimeError(f"Only {len(result.extra)} neighbourhoods: has the file changed?")
    return result
