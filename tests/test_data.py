"""Checks on data/councils.json itself, run on every data update before it
is proposed, so a source that changed shape can't quietly empty a column."""

import json
import os

import pytest

from web import model

with open(os.path.join(model.ROOT, "data", "councils.json")) as f:
    DATA = json.load(f)
COUNCILS = DATA["councils"]

COUNT = {"England": (125, 140), "Scotland": (32, 32)}  # councils in each nation

# The least each measure should cover in each nation: housing only counts
# councils that own homes, and small numbers are left out of some shares
MINIMUM = {(m.id, "England"): 120 for m in model.MEASURES}
MINIMUM.update({(m.id, "England"): 75 for m in model.MEASURES if m.area == "housing"})
# Counted from the Ombudsman's search, which is slow and sometimes refuses:
# not required, so the rest of an update can still be published
MINIMUM.update({(m, "England"): 0 for m in ("om_children", "om_sen", "om_homeless")})
MINIMUM.update({(m, "England"): n for m, n in
                dict(om_remedy_before=100, om_timely=90, ta_long=100, fly_enforce=100).items()})
MINIMUM.update({(m.id, "Scotland"): 30 for m in model.MEASURES})
MINIMUM.update({(m.id, "Scotland"): 24 for m in model.MEASURES if m.area == "housing"})  # 26 own homes


def nation_of(council):
    return council.get("nation") or model.NATIONS[council["code"][0]]


def test_every_council_is_there():
    assert len({c["slug"] for c in COUNCILS}) == len(COUNCILS)
    for nation, (low, high) in COUNT.items():
        assert low <= sum(1 for c in COUNCILS if nation_of(c) == nation) <= high, nation
    for c in COUNCILS:
        assert c["region"] and c["type"] in model.TYPE_PLURAL and c["population"] > 20_000, c["name"]


@pytest.mark.parametrize("measure,nation", [(m.id, n) for m in model.MEASURES for n in m.nations])
def test_each_measure_covers_most_councils(measure, nation):
    covered = sum(1 for c in COUNCILS if nation_of(c) == nation and measure in c["values"])
    assert covered >= MINIMUM[measure, nation], f"{measure} in {nation}: only {covered} councils"


def test_measures_only_appear_in_their_nations():
    nations = {m.id: m.nations for m in model.MEASURES}
    for c in COUNCILS:
        for measure in c["values"]:
            assert nation_of(c) in nations[measure], (c["name"], measure)


@pytest.mark.parametrize("measure", [m.id for m in model.MEASURES if m.unit == "%"])
def test_percentages_are_percentages(measure):
    for c in COUNCILS:
        if measure in c["values"]:
            assert 0 <= c["values"][measure] <= 100, (c["name"], measure, c["values"][measure])


def test_every_source_says_what_period_it_covers():
    for source_id, source in DATA["sources"].items():
        assert source["period"] and source["url"].startswith("https://"), source_id


def test_spending_and_ofsted():
    assert sum(1 for c in COUNCILS if c["spend"]) >= 120
    assert sum(1 for c in COUNCILS if c["ofsted"]) >= 120
    assert all(c["ofsted"]["grade"] in model.GRADES for c in COUNCILS if c["ofsted"])
