import json

from web import build


def test_builds_every_page(fixture_data, tmp_path):
    count = build.build(str(tmp_path))
    # Home, About, and each council's pages: 4 London boroughs (all England,
    # London, and similar councils for Lewisham only), Wigan and Hartlepool
    # (all England, region, type)
    assert count == 5 + (4 * 2 + 1) + 2 * 3  # with privacy and the two postcode search pages
    lewisham = (tmp_path / "lewisham" / "index.html").read_text()
    assert "<h1 class=\"govuk-heading-xl govuk-!-margin-bottom-4\">Lewisham</h1>" in lewisham
    assert "<title>How Lewisham Council compares – Councils compared</title>" in lewisham
    assert '"@type": "BreadcrumbList"' in lewisham
    assert "Ryan O'Callaghan" in lewisham
    assert "This is not a government service" in lewisham
    assert "Compares worst on" in lewisham
    # Measures with no figure are left out, and counted instead
    assert "Fly-tipping incidents" not in lewisham and "more measures have no figure" in lewisham
    assert "&lt;" not in lewisham  # no HTML shown as text
    assert (tmp_path / "privacy" / "index.html").exists()
    similar = (tmp_path / "lewisham" / "similar" / "index.html").read_text()
    assert 'href="/greenwich/similar/"' in similar
    assert (tmp_path / "404.html").exists()
    assert "Where your council tax goes" in lewisham and "Council tax is only part of the money" in lewisham
    assert "Where your council tax goes" in similar  # on every comparison page
    assert json.loads((tmp_path / "data" / "councils-by-code.json").read_text())["E09000023"] == "lewisham"
    assert (tmp_path / "_headers").exists()
    assert "https://councilscompared.com/lewisham/similar/" in (tmp_path / "sitemap.xml").read_text()
    assert json.loads((tmp_path / "data" / "councils.json").read_text())["councils"]
    assert (tmp_path / "data" / "councils.csv").read_text().startswith("ons_code,council,")


def test_analytics_can_be_turned_off(fixture_data, tmp_path, monkeypatch):
    monkeypatch.setattr(build, "UMAMI_WEBSITE_ID", "")
    build.build(str(tmp_path))
    assert "stats.mybin.day" not in (tmp_path / "index.html").read_text()
    monkeypatch.setattr(build, "UMAMI_WEBSITE_ID", "abc")
    build.build(str(tmp_path))
    assert 'data-website-id="abc"' in (tmp_path / "index.html").read_text()
