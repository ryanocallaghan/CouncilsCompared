"""ONS mid-year population estimates, which also say what kind of council each is.

The councils compared are every single-tier council in England: unitary
authorities, metropolitan districts and London boroughs. The City of London
and the Isles of Scilly are left out: with a few thousand residents each, and
services shared with neighbours, they are not comparable.
"""

import re

from pipeline import sheets
from pipeline.http import get, get_json, get_text
from pipeline.sources import Result

ID = "population"
PAGE = ("https://www.ons.gov.uk/peoplepopulationandcommunity/populationandmigration/populationestimates/"
        "datasets/estimatesofthepopulationforenglandandwales")
TYPES = {"Unitary Authority": "Unitary authority", "Metropolitan District": "Metropolitan district",
         "London Borough": "London borough"}
LEFT_OUT = {"E09000001", "E06000053"}  # City of London, Isles of Scilly

# ONS's lookups of local authority districts to regions, as an ArcGIS API
GEOPORTAL = "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services"


def display_name(name):
    """ "Bristol, City of" -> "Bristol"."""
    return re.sub(r",\s*(City|County) of$", "", name).strip()


def latest_file():
    page = get_text(PAGE)
    links = re.findall(r'href="(/file\?uri=[^"]+/mye(\d\d)tablesew\.xlsx)"', page)
    if not links:
        raise RuntimeError("No mid-year estimates file on the ONS page")
    path, year = max(links, key=lambda link: int(link[1]))
    return "https://www.ons.gov.uk" + path, 2000 + int(year)


def regions():
    """{lad code: region name} from the newest LAD-to-region lookup."""
    services = get_json(GEOPORTAL + "?f=json")["services"]
    names = [s["name"] for s in services if re.fullmatch(r"LAD(\d\d)_RGN\1_EN_LU(_v\d+)?", s["name"])]
    name = max(names, key=lambda n: (n[3:5], n))
    query = (f"{GEOPORTAL}/{name}/FeatureServer/0/query?where=1%3D1&outFields=*&f=json"
             "&resultRecordCount=2000")
    lookup = {}
    for feature in get_json(query)["features"]:
        attributes = feature["attributes"]
        code = next(v for k, v in attributes.items() if re.fullmatch(r"LAD\d\dCD", k))
        region = next(v for k, v in attributes.items() if re.fullmatch(r"RGN\d\dNM", k))
        lookup[code] = region
    return lookup, f"{GEOPORTAL}/{name}"


def fetch(context=None):
    url, year = latest_file()
    rows = sheets.sheet(sheets.workbook(get(url)), r"^MYE2 - Persons")
    head = sheets.header_row(rows, r"^Code$")
    header = rows[head]
    col_type = sheets.column(header, r"^Geography$")
    col_name = sheets.column(header, r"^Name$")
    col_all = sheets.column(header, r"^All ages$")
    region_of, region_source = regions()
    result = Result(id=ID, title=f"ONS: Population estimates, mid-{year}", url=PAGE, period=f"mid-{year}",
                    files=[url, region_source])
    for row in rows[head + 1:]:
        code = sheets.code(row[0])
        kind = TYPES.get(sheets.text(row[col_type]))
        if not code or not kind or code in LEFT_OUT:
            continue
        name = sheets.text(row[col_name])
        result.values[code] = {"population": int(sheets.num(row[col_all]))}
        result.extra[code] = {"name": display_name(name), "ons_name": name, "type": kind,
                              "region": region_of.get(code)}
        if not region_of.get(code):
            result.notes.append(f"No region for {name} ({code})")
    if not 120 <= len(result.values) <= 140:
        raise RuntimeError(f"Expected about 130 single-tier councils, found {len(result.values)}")
    return result
