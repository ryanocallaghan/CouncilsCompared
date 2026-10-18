import json

from web import build


def test_builds_every_page(fixture_data, tmp_path):
    count = build.build(str(tmp_path))
    # Home, About, and each council's pages: 4 London boroughs (all England,
    # London, and similar councils for Lewisham only), Wigan and Hartlepool
    # (all England, region, type)
    assert count == 2 + (4 * 2 + 1) + 2 * 3
    lewisham = (tmp_path / "lewisham" / "index.html").read_text()
    assert "Lewisham compared with all councils in England" in lewisham
    assert "This is not a government service" in lewisham
    assert "compares worst with all councils in England on:" in lewisham
    assert "&lt;p" not in lewisham  # the summary is HTML, not escaped
    similar = (tmp_path / "lewisham" / "similar" / "index.html").read_text()
    assert 'href="/greenwich/similar/"' in similar
    assert (tmp_path / "404.html").exists()
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
