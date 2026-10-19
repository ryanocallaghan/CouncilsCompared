import pytest

from web import model


@pytest.mark.parametrize(
    "value, better, expected",
    [(90, "higher", 1), (50, "higher", 3), (10, "lower", 1), (90, "lower", 3), (70, "higher", 2)],
)
def test_position_counts_from_the_best(value, better, expected):
    values = [90, 70, 50, 10] if better == "higher" else [10, 50, 90, 95]
    assert model.position(value, values, better) == expected


def test_ties_share_a_position():
    assert model.position(50, [50, 50, 40], "higher") == 1


@pytest.mark.parametrize("position, count, expected", [(1, 32, "top"), (16, 32, "top"), (17, 32, "middle"),
                                                       (24, 32, "middle"), (25, 32, "bottom"), (6, 6, "bottom"),
                                                       (5, 6, "bottom"), (4, 6, "middle"), (3, 6, "top")])
def test_bands(position, count, expected):
    assert model.band(position, count) == expected


@pytest.mark.parametrize("value, unit, expected", [(22.9, "%", "22.9%"), (7.0, "", "7"), (111.25, "", "111.2"),
                                                   (1387.3, "£", "£1,387"), (-312.3, "£", "−£312"),
                                                   (None, "%", "No figure")])
def test_fmt(value, unit, expected):
    assert model.fmt(value, unit) == expected


@pytest.mark.parametrize("n, expected", [(1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"), (11, "11th"),
                                         (12, "12th"), (13, "13th"), (21, "21st"), (22, "22nd"), (130, "130th")])
def test_ordinal(n, expected):
    assert model.ordinal(n) == expected


def test_strip_puts_better_on_the_right():
    values = {"A": 10, "B": 50, "C": 90}
    higher = model.strip(values, "C", {"A", "B", "C"}, "higher", 50)
    lower = model.strip(values, "C", {"A", "B", "C"}, "lower", 50)
    assert higher.me > 90 and lower.me < 10
    assert higher.median == lower.median == 50
    assert higher.path(True).startswith("M20 ")  # A, at 2% across


def test_compared_with_all_england(fixture_data):
    lewisham = model.councils()["lewisham"]
    result = model.compare(lewisham)
    rows = {r.measure.id: r for area in result.areas for r in area.rows}
    assert (rows["ehcp_20wk"].position, rows["ehcp_20wk"].count, rows["ehcp_20wk"].band) == (6, 6, "bottom")
    assert rows["ehcp_20wk"].value == "22.9%" and rows["ehcp_20wk"].period == "2025-26"
    assert "fly_rate" not in rows  # no figure, so not shown
    streets = next(a for a in result.areas if a.id == "streets")
    assert streets.rows == []  # no council in the fixture has these figures, so they aren't shown at all
    send = next(a for a in result.areas if a.id == "send")
    assert send.headline == "Bottom quarter"
    assert result.ranked == 4
    assert result.phrase == "all councils in England"
    assert len(result.members) == 6


def test_the_summary_says_which_end_is_best(fixture_data):
    # "Furthest behind on upheld complaints" was once read as good news:
    # for measures where lower is better, say so
    lambeth = model.compare(model.councils()["lambeth"])
    assert lambeth.compares_worst[0] == "complaints the Ombudsman upheld, per 100,000 residents (6th of 6; 1st is lowest)"
    lewisham = model.compare(model.councils()["lewisham"])
    assert lewisham.compares_worst[0] == "special educational needs plans issued on time (6th of 6; 1st is highest)"


def test_region_and_type_groups(fixture_data):
    lewisham, wigan = model.councils()["lewisham"], model.councils()["wigan"]
    assert {c["name"] for c in model.group_members(lewisham, "region")} == {
        "Lewisham", "Greenwich", "Lambeth", "Southwark"}
    assert model.group_phrase(lewisham, "region") == "London boroughs"
    assert model.group_tab(wigan, "type") == "Metropolitan districts"
    assert model.group_phrase(wigan, "region") == "councils in North West"


def test_london_boroughs_have_no_separate_type_page(fixture_data):
    # For a London borough its region and its type are the same group
    assert model.groups_for(model.councils()["lewisham"]) == ["england", "region", "similar"]


def test_similar_councils_need_enough_neighbours(fixture_data):
    assert "similar" not in model.groups_for(model.councils()["greenwich"])  # only 1
    similar = model.group_members(model.councils()["lewisham"], "similar")
    assert [c["name"] for c in similar] == ["Lewisham", "Greenwich", "Lambeth", "Southwark"]


def test_paths(fixture_data):
    lewisham = model.councils()["lewisham"]
    assert model.path(lewisham) == "/lewisham/"
    assert model.path(lewisham, "similar") == "/lewisham/similar/"


def test_trend_charts(fixture_data):
    result = model.compare(model.councils()["lewisham"])
    assert [t["title"] for t in result.trends] == ["EHC plans issued within 20 weeks"]
    lines = result.trends[0]["chart"]["lines"]
    assert lines[0]["last"] == "22.9%" and lines[1]["last"] == "41.5%"  # median of 22.9 and 60


def test_line_chart_scales_percentages_to_100():
    chart = model.line_chart(["2024", "2025"], [("A", {"2024": 60, "2025": 80}, "x")], "%")
    assert chart["ticks"][-1]["label"] == "100%"
    assert chart["lines"][0]["last"] == "80.0%"


def test_ofsted_grades_are_counted(fixture_data):
    result = model.compare(model.councils()["lewisham"])
    assert dict(result.grades) == {"Outstanding": 1, "Good": 4, "Requires improvement": 1, "Inadequate": 0}


def test_council_tax_split(fixture_data):
    ct = model.council_tax(model.councils()["lewisham"])
    assert [p["label"] for p in ct["who"]] == ["Lewisham council", "Mayor of London (GLA), including police and fire"]
    assert sum(p["band_d"] for p in ct["who"]) == pytest.approx(ct["band_d"])
    # The council's part, split by its spending; roads brought in money, so are left out
    assert [s["label"] for s in ct["services"]] == ["Children's social care", "Adult social care"]
    assert sum(s["band_d"] for s in ct["services"]) == pytest.approx(1726.82)
    assert ct["left_out"] == ["Roads and transport"]
    assert dict((b["band"], b["ratio"]) for b in ct["bands"])["H"] == 2


def test_no_council_tax_split_without_figures(fixture_data):
    assert model.council_tax(model.councils()["greenwich"]) is None


def test_council_tax_split(fixture_data):
    ct = model.council_tax(model.councils()["lewisham"])
    assert [p["label"] for p in ct["who"]] == ["Lewisham council", "Mayor of London (GLA), including police and fire"]
    assert sum(p["band_d"] for p in ct["who"]) == pytest.approx(ct["band_d"])
    # The council's part, split by its spending; roads brought in money, so are left out
    assert [s["label"] for s in ct["services"]] == ["Children's social care", "Adult social care"]
    assert sum(s["band_d"] for s in ct["services"]) == pytest.approx(1726.82)
    assert ct["left_out"] == ["Roads and transport"]
    assert dict((b["band"], b["ratio"]) for b in ct["bands"])["H"] == 2


def test_no_council_tax_split_without_figures(fixture_data):
    assert model.council_tax(model.councils()["greenwich"]) is None


def test_group_menu(fixture_data):
    lewisham, wigan = model.councils()["lewisham"], model.councils()["wigan"]
    assert model.group_option(lewisham, "england") == "All councils in England (6)"
    assert model.group_option(lewisham, "region") == "London boroughs (4)"
    assert model.group_option(wigan, "region") == "Councils in North West (1)"


def test_ranking_for_a_measure_page(fixture_data):
    rows = model.ranking(model.measure_by_id("om_upheld"))
    assert [(pos, c["name"]) for pos, c, _, _ in rows][:2] == [(1, "Wigan"), (2, "Hartlepool")]
    assert rows[-1][1]["name"] == "Lambeth" and rows[-1][3] == 3  # bottom quarter


def test_hexmap_colours_our_councils_and_greys_the_rest(fixture_data):
    cells = model.hexmap(model.measure_by_id("ehcp_20wk"))["cells"]
    ours = [c for c in cells if c["council"]]
    assert {c["council"]["name"] for c in ours} == {"Lewisham", "Greenwich", "Lambeth", "Southwark", "Wigan",
                                                    "Hartlepool"}
    assert all(c["class"].startswith("app-q") for c in ours)
    assert sum(1 for c in cells if c["class"] == "app-hex--other") > 250  # county and district areas


def test_site_data_for_the_charts(fixture_data):
    data = model.site_data()
    assert data["councils"][0]["name"] == "Greenwich"
    assert data["measures"]["om_upheld"] == {"label": "Complaints the Ombudsman upheld, per 100,000 residents",
                                             "unit": "", "better": "lower"}


def test_measures_covering_too_few_councils_are_hidden(fixture_data):
    # 5 of the 6 councils have the Ombudsman figure; only 4 have tenant satisfaction,
    # but council housing is shown anyway, as only councils with homes report it
    assert model.available(model.measure_by_id("om_upheld"))
    assert not model.available(model.measure_by_id("fly_rate"))
    assert model.available(model.measure_by_id("tsm_overall"))
