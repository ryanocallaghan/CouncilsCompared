import json

from web import build


def test_builds_every_page(fixture_data, tmp_path):
    count = build.build(str(tmp_path))
    # Home, About, and each council's pages: 4 London boroughs (all England,
    # London, and similar councils for Lewisham only), Wigan and Hartlepool
    # (all England, region, type)
    from web import model
    # Home, about, privacy, two postcode pages, measures index and one page per measure, then the councils,
    # then the council tax page and the hubs: 3 regions, and metropolitan districts and unitary authorities
    assert count == 6 + len([m for m in model.MEASURES if model.available(m)]) + (4 * 2 + 1) + 2 * 3 + 1 + 3 + 2
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
    fly = (tmp_path / "measures" / "om-upheld" / "index.html").read_text()
    assert "Complaints the Ombudsman upheld" in fly and 'class="app-hex app-q1"' in fly
    assert json.loads((tmp_path / "data" / "site.json").read_text())["councils"]
    similar = (tmp_path / "lewisham" / "similar" / "index.html").read_text()
    assert 'href="/greenwich/similar/"' in similar
    assert (tmp_path / "404.html").exists()
    assert "Where your council tax goes" in lewisham and "Council tax is only part of the money" in lewisham
    assert "Where your council tax goes" in similar  # on every comparison page
    assert json.loads((tmp_path / "data" / "councils-by-code.json").read_text())["E09000023"] == "lewisham"
    assert (tmp_path / "_headers").exists()
    assert "https://councilscompared.com/lewisham/similar/" in (tmp_path / "sitemap.xml").read_text()
    assert json.loads((tmp_path / "data" / "councils.json").read_text())["councils"]
    # For search engines and AI answers
    assert "Key figures" in lewisham and "Last updated 17 September 2026" in lewisham
    assert '"@type": "GovernmentOrganization"' in lewisham
    assert '"@type": "Dataset"' in fly and "<title>Complaints the Ombudsman upheld, per 100,000 residents: every council in England ranked (2025-26)" in fly
    assert "<lastmod>2026-09-17</lastmod>" in (tmp_path / "sitemap.xml").read_text()
    assert "Content-Signal: search=yes, ai-input=yes" in (tmp_path / "robots.txt").read_text()
    assert "/data/councils.csv" in (tmp_path / "llms.txt").read_text()
    assert (tmp_path / f"{build.INDEXNOW_KEY}.txt").read_text() == build.INDEXNOW_KEY
    london = (tmp_path / "regions" / "london" / "index.html").read_text()
    assert "<title>London boroughs compared" in london and 'href="/lewisham/region/"' in london
    assert 'href="/regions/london/"' in lewisham and 'href="/types/metropolitan-districts/"' in (
        tmp_path / "wigan" / "index.html").read_text()
    council_tax = (tmp_path / "council-tax" / "index.html").read_text()
    assert "<title>Council tax Band D" in council_tax and '"@type": "Dataset"' in council_tax
    assert (tmp_path / "data" / "councils.csv").read_text().startswith("ons_code,council,")


def test_analytics_can_be_turned_off(fixture_data, tmp_path, monkeypatch):
    monkeypatch.setattr(build, "UMAMI_WEBSITE_ID", "")
    build.build(str(tmp_path))
    assert "stats.mybin.day" not in (tmp_path / "index.html").read_text()
    monkeypatch.setattr(build, "UMAMI_WEBSITE_ID", "abc")
    build.build(str(tmp_path))
    assert 'data-website-id="abc"' in (tmp_path / "index.html").read_text()


def test_indexnow_sends_every_page_in_the_sitemap(fixture_data, tmp_path):
    from web import indexnow
    build.build(str(tmp_path))
    pages = indexnow.urls(tmp_path / "sitemap.xml")
    assert "https://councilscompared.com/" in pages and "https://councilscompared.com/lewisham/similar/" in pages
