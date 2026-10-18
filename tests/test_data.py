"""Checks on data/councils.json itself, run on every data update before it
is proposed, so a source that changed shape can't quietly empty a column."""

import json
import os

import pytest

from web import model

with open(os.path.join(model.ROOT, "data", "councils.json")) as f:
    DATA = json.load(f)
COUNCILS = DATA["councils"]

# The least each measure should cover: housing only counts councils that own
# homes, and small numbers are left out of some shares
MINIMUM = {m.id: 120 for m in model.MEASURES}
MINIMUM.update({m.id: 75 for m in model.MEASURES if m.area == "housing"})
MINIMUM.update(om_remedy_before=100, om_timely=90, ta_long=100, fly_enforce=100)


def test_every_single_tier_council_is_there():
    assert 125 <= len(COUNCILS) <= 140
    assert len({c["slug"] for c in COUNCILS}) == len(COUNCILS)
    for c in COUNCILS:
        assert c["region"] and c["type"] in model.TYPE_PLURAL and c["population"] > 20_000, c["name"]


@pytest.mark.parametrize("measure", [m.id for m in model.MEASURES])
def test_each_measure_covers_most_councils(measure):
    covered = sum(1 for c in COUNCILS if measure in c["values"])
    assert covered >= MINIMUM[measure], f"{measure}: only {covered} councils"


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
