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
    assert model.groups_for(model.councils()["lewisham"]) == ["nation", "region", "similar"]


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
    assert model.group_option(lewisham, "nation") == "All councils in England (6)"
    assert model.group_option(lewisham, "region") == "London boroughs (4)"
    assert model.group_option(wigan, "region") == "Councils in North West (1)"


def test_key_figures_stand_on_their_own(fixture_data):
    # Each sentence names the council, year, position and which end is best,
    # so it still makes sense quoted alone
    figures = model.key_figures(model.compare(model.councils()["lambeth"]))
    assert figures[1] == ("In 2025-26, Lambeth was 6th of 6 among all councils in England for complaints the "
                          "Ombudsman upheld, per 100,000 residents (1st is lowest), at 20 against a median of 7.")


def test_measure_summary(fixture_data):
    m = model.measure_by_id("om_upheld")
    assert model.measure_summary(m, model.ranking(m)) == (
        "In 2025-26, the highest figure was Lambeth’s (20) and the lowest Wigan’s (3). "
        "The median across 6 councils in England was 7.")


def test_updated_is_the_newest_publication(fixture_data):
    assert model.updated() == "2026-09-17"
    assert model.updated({"ctax"}) == "2026-07-31"


def test_band_d_lowest_first(fixture_data):
    rows = model.band_d_ranking()
    assert rows[0][0] == 1 and rows[-1][:1] == (6,) and rows[-1][1]["name"] == "Lewisham"


def test_hubs(fixture_data):
    # London boroughs are the same as London, so have no separate type hub
    assert model.hubs() == [("region", "London"), ("region", "North East"), ("region", "North West"),
                            ("type", "Metropolitan district"), ("type", "Unitary authority")]
    assert model.hub_path("type", "Unitary authority") == "/types/unitary-authorities/"
    assert model.hub_for(model.councils()["lewisham"], "type") == "/regions/london/"
    london = model.hub("region", "London")
    assert london["title"] == "London boroughs"
    assert [r["path"] for r in london["rows"]][0] == "/greenwich/region/"


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


def test_councils_are_compared_within_their_nation(fixture_data):
    lewisham = model.councils()["lewisham"]
    assert lewisham["nation"] == "England"  # from the ONS code, when the data has no nation
    assert model.nations() == ["England"]
    assert model.group_tab(lewisham, "nation") == "All England"
    glasgow = {"code": "S12000049", "name": "Glasgow City", "slug": "glasgow-city", "nation": "Scotland",
               "region": "Scotland", "type": "Council area", "neighbours": []}
    # No regions or types in Scotland, and no similar councils without a list of them
    assert model.groups_for(glasgow) == ["nation"]
    assert model.group_phrase(glasgow, "nation") == "all councils in Scotland"
    assert model.path(glasgow) == "/glasgow-city/"
    upheld = model.measure_by_id("om_upheld")
    assert not model.available(upheld, "Scotland")  # an English measure
    assert model.measure_path(upheld) == "/measures/om-upheld/"
    assert model.measure_path(upheld, "Scotland") == "/measures/om-upheld/scotland/"


def test_scotland_is_hidden_until_published(fixture_data):
    assert "glasgow-city" not in model.councils()
    assert model.nations() == ["England"]


def test_scottish_councils_are_compared_with_each_other(fixture_data, monkeypatch):
    monkeypatch.setattr(model, "PUBLISHED", ["England", "Scotland"])
    assert model.nations() == ["England", "Scotland"]
    glasgow = model.councils()["glasgow-city"]
    assert model.groups_for(glasgow) == ["nation", "similar"]
    result = model.compare(glasgow)
    assert len(result.members) == 4 and result.phrase == "all councils in Scotland"
    rows = {r.measure.id: r for area in result.areas for r in area.rows}
    # Each measure's own period, from the LGBF, and ranked only among Scottish councils
    assert (rows["literacy"].position, rows["literacy"].count, rows["literacy"].period) == (4, 4, "2024-25")
    assert rows["ctax_collect"].count == 4
    # England's areas without Scottish measures are left out, and Scotland's added
    areas = [a.id for a in result.areas]
    assert "send" not in areas and "schools" in areas
    assert "glasgow-city" not in [c["slug"] for c in model.group_members(model.councils()["lewisham"], "nation")]
    assert model.period(model.measure_by_id("ctax_collect"), "Scotland") == "2025-26"
    assert model.measure_by_id("ctax_collect").source_for("Scotland") == "lgbf"


def test_scottish_council_tax(fixture_data, monkeypatch):
    monkeypatch.setattr(model, "PUBLISHED", ["England", "Scotland"])
    ct = model.council_tax(model.councils()["glasgow-city"])
    ratios = {b["band"]: b["ratio"] for b in ct["bands"]}
    # Scotland's bands E to H are higher than England's
    assert ratios["A"] == pytest.approx(240 / 360) and ratios["H"] == pytest.approx(882 / 360)
    # All of it goes to the council: no police, fire or parish charges
    assert [p["label"] for p in ct["who"]] == ["Glasgow City council"]
    assert (ct["period"], ct["spend_period"]) == ("2026-27", "2024-25")
    assert ct["check"][0] == "https://www.saa.gov.uk/" and "Scottish Water" in ct["note"]
    assert [s["label"] for s in ct["services"]] == ["Social work and social care", "Housing and homelessness"]


def test_band_d_ranking_is_within_a_nation(fixture_data, monkeypatch):
    monkeypatch.setattr(model, "PUBLISHED", ["England", "Scotland"])
    rows = model.band_d_ranking("Scotland")
    assert [(pos, c["name"]) for pos, c, _, _ in rows] == [(1, "City of Edinburgh"), (2, "Glasgow City")]
    assert model.band_d_path("Scotland") == "/council-tax/scotland/"
    assert model.band_d_summary(rows, "Scotland").endswith("The median across 2 councils in Scotland was £1,666.")
    assert "Glasgow City" not in [c["name"] for _, c, _, _ in model.band_d_ranking()]


def test_coverage(fixture_data, monkeypatch):
    assert model.coverage() == "every single-tier council in England"
    monkeypatch.setattr(model, "PUBLISHED", ["England", "Scotland"])
    assert model.coverage() == "every single-tier council in England and every council in Scotland"
