import pytest

from pipeline import govuk, names, sheets
from pipeline.sources import homelessness
from pipeline.update import changes

COUNCILS = {
    "E09000023": "Lewisham", "E06000023": "Bristol, City of", "E06000019": "Herefordshire, County of",
    "E09000014": "Haringey", "E08000032": "Bradford", "E08000036": "Wakefield", "E06000047": "County Durham",
    "E06000010": "Kingston upon Hull, City of", "E08000013": "St. Helens", "E09000020": "Kensington and Chelsea",
}


@pytest.mark.parametrize("name, code", [
    ("London Borough of Lewisham", "E09000023"),
    ("Bristol City Council", "E06000023"),
    ("Herefordshire Council", "E06000019"),
    ("Haringey London Borough Council", "E09000014"),
    ("Bradford Metropolitan Council", "E08000032"),
    ("City of Bradford Metropolitan District Council", "E08000032"),
    ("Wakefield City Metropolitan District Council", "E08000036"),
    ("Durham County Council", "E06000047"),
    ("Hull City Council", "E06000010"),
    ("St Helens Metropolitan Borough Council", "E08000013"),
    ("Royal Borough of Kensington & Chelsea", "E09000020"),
    ("Kent County Council", None),
])
def test_names_from_other_publications_match_ons_codes(name, code):
    assert names.Matcher(COUNCILS).code(name) == code


@pytest.mark.parametrize("value, expected", [(12.5, 12.5), ("1,234", 1234.0), ("[c]", None), ("[x]", None),
                                             ("", None), ("x", None), ("45%", 45.0)])
def test_num(value, expected):
    assert sheets.num(value) == expected


def test_codes_changed_by_boundary_changes_are_the_same_council(monkeypatch):
    monkeypatch.setattr(sheets, "KNOWN", {"E08000016"})
    assert sheets.code("E08000038") == "E08000016"  # Barnsley's 2025 code
    assert sheets.code(" E08000016\n") == "E08000016"
    assert sheets.code("E07000223") == "E07000223"
    assert sheets.code("Adur") is None


@pytest.mark.parametrize("title, year", [
    ("Collection rates for Council Tax and non-domestic rates in England, 2025 to 2026", 2026),
    ("Tenant Satisfaction Measures 2024/25", 2025),
    ("Local authority inspection outcomes as at 31 March 2026", 2026),
    ("Live tables", 0),
])
def test_years_in(title, year):
    assert govuk.years_in(title) == year


def test_finds_the_latest_quarter_of_homelessness_figures():
    item = {"details": {"attachments": [
        {"title": "Detailed local authority level tables: October to December 2025 (revised)", "url": "a.ods"},
        {"title": "Detailed local authority level tables: January to March 2026", "url": "b.ods"},
        {"title": "Detailed local authority level tables: January to March 2026 - Accessible", "url": "c.ods"},
        {"title": "Detailed local authority level tables: financial year 2025-26", "url": "d.ods"},
        {"title": "Detailed local authority level tables: April to June 2025", "url": "e.ods"},
    ]}}
    _, attachment, period = homelessness.latest_attachment(item)
    assert attachment["url"] == "b.ods" and period == "January to March 2026"


def test_changes_describe_new_editions_and_revised_figures():
    before = {"sources": {"ctax": {"title": "Council tax", "period": "2024-25"}},
              "councils": [{"code": "A", "name": "Aville", "values": {"ctax_collect": 95.0}}]}
    after = {"sources": {"ctax": {"title": "Council tax", "period": "2025-26"}},
             "councils": [{"code": "A", "name": "Aville", "values": {"ctax_collect": 96.5}}]}
    text = changes(before, after)
    assert "| Council tax | 2024-25 → **2025-26** | New edition |" in text
    assert "| `ctax_collect` | 1 | Aville: 95.0 → 96.5 |" in text
    assert changes(after, after) == "No figures changed."
