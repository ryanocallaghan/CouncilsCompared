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


def test_changes_list_checks_that_flipped():
    def data(passed):
        return {"sources": {}, "councils": [{"code": "A", "name": "Aville", "values": {},
                                             "checks": {"brownfield": {"pass": passed, "reason": ""}}}]}
    assert "| `brownfield` | 1 | Aville (fails) |" in changes(data(True), data(False))
    assert changes(data(True), data(True)) == "No figures changed."


def test_most_common_band_in_each_neighbourhood(monkeypatch):
    import io
    import zipfile
    from pipeline.sources import area_bands
    rows = ['"geography","ba_code","ecode","area_name","band_a","band_b","band_c","band_d","band_e","band_f","band_g","band_h","band_i","all_properties"',
            '"LAUA","5690","E09000023","Lewisham","9210","36740","48390","27920","8130","2820","1370","190","[z]","134760"']
    rows += [f'"LSOA","N/A","E01{n:06d}","x","30","370","210","150","40","20","20","[c]","[z]","840"' for n in range(30_000)]
    rows.append('"LSOA","N/A","E01999999","tie","100","100","0","0","0","0","0","0","[z]","200"')
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        z.writestr("CTSOP1_1/CTSOP1_1.csv", "\n".join(rows))
    item = {"title": "Council Tax: stock of properties, 2026", "web_url": "https://www.gov.uk/x"}
    monkeypatch.setattr(area_bands.govuk, "latest", lambda *a: (item, {"url": "u"}))
    monkeypatch.setattr(area_bands, "get", lambda url: data.getvalue())
    result = area_bands.fetch()
    assert result.extra["E01000001"] == "B"
    assert result.extra["E01999999"] == "A"  # a tie goes to the lower band
    assert "E09000023" not in result.extra and result.period == "2026"


def test_planning_data_counts_datasets_with_a_working_endpoint(monkeypatch):
    from pipeline.sources import planning_data

    rows = ["organisation,dataset,provision_reason,active_endpoint_count,error_endpoint_count",
            "local-authority:LEW,conservation-area,expected,1,0",
            "local-authority:LEW,tree,expected,2,1",  # one of two endpoints erroring still counts
            "local-authority:LEW,article-4-direction,encouraged,0,1",  # only an erroring endpoint
            "local-authority:LEW,brownfield-land,statutory,1,0",
            "local-authority:LEW,local-plan,statutory,1,0",  # not one of the eight
            "local-authority:HRY,tree,expected,0,0",
            "national-park-authority:X,conservation-area,expected,1,0"]
    organisations = {"organisations": {
        "local-authority": [{"organisation": "local-authority:LEW", "statistical-geography": "E09000023"},
                            {"organisation": "local-authority:HRY", "statistical-geography": "E09000014"}],
        "national-park-authority": [{"organisation": "national-park-authority:X", "statistical-geography": ""}]}}
    monkeypatch.setattr(planning_data, "get_text", lambda url: "\n".join(rows))
    monkeypatch.setattr(planning_data, "get_json", lambda url: organisations)
    result = planning_data.fetch({"population": {"E09000023": 1, "E09000014": 1, "E08000032": 1, "S12000033": 1}})
    assert result.values == {"E09000023": {"planning_data": 25.0}, "E09000014": {"planning_data": 0.0}}
    assert result.checks["E09000023"]["brownfield"] == {"pass": True, "reason": ""}
    assert result.checks["E09000014"]["brownfield"]["pass"] is False
    assert "doesn't collect one" in result.checks["E09000014"]["brownfield"]["reason"]
    assert "Conservation areas" not in result.extra["E09000023"]["missing"]
    assert len(result.extra["E09000014"]["missing"]) == 8
    assert any("E08000032" in note for note in result.notes)  # not on the platform; Scotland isn't asked


def test_planning_data_counts_the_councils_a_new_one_replaced_only_if_all_have_it(monkeypatch):
    from pipeline.sources import planning_data

    rows = ["organisation,dataset,active_endpoint_count",
            "local-authority:CUA,tree,0",
            # Cumberland replaced Allerdale, Carlisle and Copeland in 2023
            "local-authority:ALL,conservation-area,1", "local-authority:CAR,conservation-area,1",
            "local-authority:COP,conservation-area,1",
            "local-authority:CAR,brownfield-land,1", "local-authority:COP,brownfield-land,1"]
    organisations = {"organisations": {"local-authority": [
        {"organisation": "local-authority:CUA", "statistical-geography": "E06000063"},
        {"organisation": "local-authority:CAR", "statistical-geography": "E07000028", "end-date": "2023-03-31"}]}}
    monkeypatch.setattr(planning_data, "get_text", lambda url: "\n".join(rows))
    monkeypatch.setattr(planning_data, "get_json", lambda url: organisations)
    result = planning_data.fetch({"population": {"E06000063": 1}})
    assert result.values["E06000063"]["planning_data"] == 12.5  # conservation areas, from all three
    check = result.checks["E06000063"]["brownfield"]
    assert check["pass"] is False
    assert "from 2 of the 3 councils it replaced in 2023" in check["reason"]


def test_planning_data_fails_when_its_columns_change(monkeypatch):
    from pipeline.sources import planning_data
    monkeypatch.setattr(planning_data, "get_text", lambda url: "organisation,dataset,endpoints\nx,y,1\n")
    with pytest.raises(KeyError, match="active_endpoint_count"):
        planning_data.fetch({"population": {}})


@pytest.mark.parametrize("name, slug", [
    ("London Borough of Lewisham", "lewisham"),
    ("Leeds City Council", "leeds"),
    ("Royal Borough of Kensington and Chelsea", "kensington-and-chelsea"),
    ("St. Helens Metropolitan Borough Council", "st-helens"),
    ("Westmorland and Furness Council", "westmorland-and-furness"),
    ("Brighton & Hove City Council", "brighton-and-hove"),
])
def test_local_links_slugs_from_gov_uk_names(name, slug):
    from pipeline.sources import local_links
    assert local_links.slug(name) == slug


def test_local_links_counts_working_links(monkeypatch):
    from pipeline.sources import local_links

    csv_text = ("Authority Name,GSS,Description,LGSL,LGIL,URL,Title,Supported by GOV.UK\n"
                "London Borough of Lewisham,E09000023,x,57,8,https://lewisham.gov.uk/tax,,true\n"
                "Fife Council,S12000015,x,57,8,https://fife.gov.uk/tax,,true\n")
    authorities = {"lewisham": "E09000023", "fife": "S12000015"}  # Fife by its old code
    statuses = {57: "ok", 524: "broken", 36: "caution", 13: None}  # 13: not checked yet; others: no link

    def get_json(url, pause=0):
        query = dict(p.split("=") for p in url.split("?")[1].split("&"))
        lgsl = int(query["lgsl"])
        response = {"local_authority": {"gss": authorities[query["authority_slug"]], "homepage_url": "https://x"}}
        if lgsl in statuses:
            response["local_interaction"] = {"lgsl_code": lgsl, "status": statuses[lgsl], "url": f"https://x/{lgsl}"}
        return response

    monkeypatch.setattr(local_links, "get_text", lambda url: csv_text)
    monkeypatch.setattr(local_links, "get_json", get_json)
    monkeypatch.setattr(local_links, "loads", lambda url: False)  # the broken link really is
    monkeypatch.setattr(local_links.time, "sleep", lambda seconds: None)
    result = local_links.fetch({"population": {"E09000023": 1, "S12000047": 1, "W06000001": 1}})
    # England: 19 checked (13 isn't yet), of which ok and caution work
    assert result.values["E09000023"]["links_working"] == round(100 * 2 / 19, 1)
    lewisham = result.extra["E09000023"]
    assert lewisham["services"] == 19 and lewisham["broken"] == ["Bin collections"]
    assert len(lewisham["missing"]) == 16 and "Paying council tax" not in lewisham["missing"]
    # Scotland is compared on fewer services, and Fife is found by its old code
    assert result.extra["S12000047"]["services"] == len(local_links.SERVICES) - 4 - 1
    assert "W06000001" not in result.values


def test_local_links_refuses_a_slug_for_the_wrong_council(monkeypatch):
    from pipeline.sources import local_links
    monkeypatch.setattr(local_links, "get_text", lambda url: "Authority Name,GSS\nLewisham,E09000023\n")
    monkeypatch.setattr(local_links, "get_json", lambda url, pause=0: {"local_authority": {"gss": "E09000014"}})
    with pytest.raises(ValueError, match="E09000014"):
        local_links.fetch({"population": {"E09000023": 1}})


def test_local_links_rechecks_links_gov_uk_marks_broken(monkeypatch):
    from pipeline.sources import local_links
    monkeypatch.setattr(local_links.time, "sleep", lambda seconds: None)
    pages = {"https://x/works": True, "https://x/gone": False, "https://x/blocked": None}
    monkeypatch.setattr(local_links, "loads", pages.get)
    links = {"57": {"status": "broken", "url": "https://x/works"},  # keys as saved: strings
             "59": {"status": "broken", "url": "https://x/gone"},
             "63": {"status": "broken", "url": "https://x/blocked"},
             "69": {"status": "ok", "url": "https://x/ok"},
             "524": {"status": "missing", "url": None}}
    local_links.recheck(links)
    assert [v["status"] for v in links.values()] == ["rechecked", "broken", "broken", "ok", "missing"]
    figures = local_links.summary(links)
    assert figures["working"] == 40.0
    assert figures["broken"] == ["Council tax discounts", "Council tax support"]
    assert figures["missing"] == ["Bin collections"]


def test_silktide_keeps_two_places_and_its_own_rank_for_this_month(monkeypatch):
    from pipeline.sources import silktide

    def snapshot(timeframe, score):
        return {"timeframeId": timeframe, "metricSnapshots": [
            {"metricType": {"name": "wcag-22-aa.score"}, "numericValue": 1.0},
            {"metricType": {"name": "wcag-22.score"}, "numericValue": score}]}

    pages = {
        silktide.CATEGORY: {
            "latestTimeframeSlug": "october-2026",
            "timeframes": [{"id": 83, "slug": "october-2026", "name": "October 2026"},
                           {"id": 82, "slug": "september-2026", "name": "September 2026"}],
            "websites": [{"name": "London Borough of Lewisham Council", "slug": "lewisham"},
                         {"name": "Haringey London Borough Council", "slug": "haringey"},
                         {"name": "Kent County Council", "slug": "kent"}]},
        f"{silktide.BASE}/website/lewisham": {
            "timeframe": "october-2026", "categoryRanks": [{"rank": 192, "categoryName": "UK Councils"}],
            "website": {"websiteSnapshots": [snapshot(82, 50.0), snapshot(83, 92.682724)]}},
        # Only last month's snapshot: no figure, and so no rank
        f"{silktide.BASE}/website/haringey": {
            "timeframe": "october-2026", "categoryRanks": [{"rank": 5, "categoryName": "UK Councils"}],
            "website": {"websiteSnapshots": [snapshot(82, 99.0)]}},
    }
    monkeypatch.setattr(silktide, "page_data", lambda url: pages[url])
    population = {code: 1 for code in COUNCILS}
    result = silktide.fetch({"matcher": names.Matcher(COUNCILS), "population": population})
    assert result.period == "October 2026"
    assert result.values == {"E09000023": {"web_access": 92.68}}
    assert result.extra == {"E09000023": {"rank": 192, "of": 3, "url": f"{silktide.BASE}/website/lewisham"}}


@pytest.mark.parametrize("homepage, expected", [
    ("https://www.lewisham.gov.uk/", "lewisham.gov.uk"),
    ("http://lewisham.gov.uk", "lewisham.gov.uk"),
    ("https://new.enfield.gov.uk/", "enfield.gov.uk"),  # the council's own domain, not the website's part of it
    ("https://m.luton.gov.uk/Page/Show", "luton.gov.uk"),
])
def test_our_checks_use_the_councils_own_domain_for_email(homepage, expected):
    from pipeline.sources import website
    assert website.domain(homepage) == expected


@pytest.mark.parametrize("records, passed, says", [
    (["v=DMARC1; p=reject; rua=mailto:x@example.gov.uk"], True, ""),
    (["v=DMARC1;p=quarantine;pct=100"], True, ""),
    (["v=DMARC1; p=none; rua=mailto:x@example.gov.uk"], False, "“none”"),
    (["v=DMARC1; p=quarantine; pct=75"], False, "75%"),
    ([], False, "no DMARC record"),
    (["v=DMARC1; p=reject", "v=DMARC1; p=none"], False, "more than one"),
    (None, None, "couldn't"),  # DNS failed: not held against the council
])
def test_dmarc_needs_quarantine_or_reject_for_all_email(records, passed, says):
    from pipeline.sources import website
    result, reason, _ = website.dmarc(records)
    assert result is passed and says in reason


@pytest.mark.parametrize("status, final, header, passed, says", [
    (200, "https://x.gov.uk/", "max-age=31536000; includeSubDomains", True, ""),
    (200, "https://x.gov.uk/", "max-age=2592000", False, "only 30 days"),
    (200, "https://x.gov.uk/", "max-age=0", False, "turns the protection off"),
    (200, "https://x.gov.uk/", None, False, "doesn't send"),
    (200, "http://x.gov.uk/", None, False, "insecure"),
    (403, "https://x.gov.uk/", None, None, "403"),  # blocked: couldn't check
    (None, "https://x.gov.uk/", None, None, "couldn't load"),
])
def test_hsts_needs_to_last_a_year(status, final, header, passed, says):
    from pipeline.sources import website
    headers = {"strict-transport-security": header} if header else {}
    result, reason, _ = website.hsts(status, final, headers)
    assert result is passed and says in reason


@pytest.mark.parametrize("status, kind, text, passed, says", [
    (200, "text/plain; charset=utf-8", "Contact: mailto:security@x.gov.uk\nExpires: 2027-01-01T00:00:00Z\n", True, ""),
    (200, "text/plain", "contact: https://x.gov.uk/report\n", True, ""),
    (200, "text/plain", "Contact: mailto:a@x.gov.uk\nExpires: 2025-01-01T00:00:00Z\n", False, "expired on 2025-01-01"),
    (200, "text/plain", "Contact: mailto:a@x.gov.uk\nExpires: 2027-02-30T00:00:00Z\n", True, ""),  # not a real date
    (200, "text/html", "<html>Page not found</html>", False, "web page instead"),
    (404, "text/html", "", False, "no security.txt"),
    (403, "text/html", "", None, "didn't let us look"),
])
def test_security_txt_needs_a_contact_and_not_to_have_expired(status, kind, text, passed, says):
    import datetime
    from pipeline.sources import website
    result, reason, _ = website.security_txt(status, "https://x.gov.uk/.well-known/security.txt",
                                             {"content-type": kind}, text, datetime.date(2026, 11, 3))
    assert result is passed and says in reason


def test_our_checks_record_answers_reasons_and_evidence(monkeypatch):
    from pipeline.sources import Result, website
    pages = {
        "https://www.lewisham.gov.uk/": (200, "https://lewisham.gov.uk/",
                                         {"strict-transport-security": "max-age=31536000"}, ""),
        "https://lewisham.gov.uk/.well-known/security.txt": (404, "https://lewisham.gov.uk/.well-known/security.txt",
                                                             {}, ""),
        "https://www.haringey.gov.uk/": (403, "https://www.haringey.gov.uk/", {}, ""),
        "https://www.haringey.gov.uk/.well-known/security.txt": (403, "https://www.haringey.gov.uk/x", {}, ""),
    }
    monkeypatch.setattr(website, "get_page", pages.get)
    monkeypatch.setattr(website, "dmarc_records", lambda name: {"lewisham.gov.uk": ["v=DMARC1; p=reject"]}.get(name, []))
    monkeypatch.setattr(website.time, "sleep", lambda seconds: None)
    links = Result(id="local_links", title="", url="", period="", extra={
        "E09000023": {"homepage": "http://www.lewisham.gov.uk"}, "E09000014": {"homepage": "https://www.haringey.gov.uk/"}})
    result = website.fetch({"results": {"local_links": links}, "population": {"E09000023": 1, "E09000014": 1, "E09000001": 1}})
    lewisham = result.checks["E09000023"]
    assert lewisham["dmarc"] == {"pass": True, "reason": "", "evidence": "v=DMARC1; p=reject"}
    assert lewisham["https"]["pass"] is True and lewisham["security_txt"]["pass"] is False
    haringey = result.checks["E09000014"]
    assert haringey["dmarc"]["pass"] is False  # DNS still answers when the website blocks us
    assert haringey["https"]["pass"] is None and haringey["security_txt"]["pass"] is None
    assert any("E09000014: couldn't check https, security_txt" == note for note in result.notes)
    assert any("E09000001" in note for note in result.notes)  # no homepage


@pytest.mark.parametrize("name, domain, expected", [
    ("_ga", ".lewisham.gov.uk", "Google Analytics"),
    ("_ga_2YXLBKBVBX", ".hartlepool.gov.uk", "Google Analytics"),
    ("_hjSession_2972342", ".camden.gov.uk", "Hotjar"),
    ("nmstat", ".cumberland.gov.uk", "Siteimprove Analytics"),
    ("YSC", ".youtube.com", "YouTube"),
    ("anything", ".doubleclick.net", "Google advertising"),  # by the site that set it
    ("CookieControl", "www.leeds.gov.uk", None),  # the banner remembering a choice
    ("__cf_bm", ".lewisham.gov.uk", None),  # bot protection
    ("__cf_bm", ".twitter.com", None),  # bot protection, even on a site whose other cookies track
    ("ASP.NET_SessionId", "www.york.gov.uk", None),
])
def test_tracking_cookies_are_from_known_analytics_and_advertising_services(name, domain, expected):
    from pipeline.sources import cookies
    assert cookies.service(name, domain) == expected


@pytest.mark.parametrize("texts, accept, reject", [
    (["OK to use analytics cookies", "Don't use analytics cookies"], 1, 1),
    (["I Accept Cookies", "I Do Not Accept Cookies"], 1, 1),
    (["Allow all", "Deny"], 1, 1),
    (["MORE OPTIONS", "DISAGREE", "AGREE"], 1, 1),
    (["Accept all cookies", "Use necessary cookies only"], 1, 1),
    (["Accept all cookies", "Accept only essential cookies"], 1, 1),
    (["Accept all cookies", "Cookie settings"], 1, 0),
    (["Yes", "No", "Search", "Menu"], 0, 0),  # "Is this page useful?" isn't a cookie banner
])
def test_cookie_banner_buttons(texts, accept, reject):
    from pipeline.sources import cookies
    found = cookies.buttons(texts)
    assert (len(found[0]), len(found[1])) == (accept, reject)


def test_cookie_checks_judge_what_a_visit_found():
    from pipeline.sources import cookies
    ga = [{"name": "_ga", "domain": ".x.gov.uk"}, {"name": "YSC", "domain": ".youtube.com"},
          {"name": "CookieControl", "domain": "x.gov.uk"}]
    judged = cookies.judge(200, "Home", ga, ["Accept all cookies", "Reject all cookies"])
    assert judged["trackers"][0] is False
    assert judged["trackers"][1] == "Before we chose anything, the homepage set cookies from Google Analytics and YouTube."
    assert judged["trackers"][2] == "_ga on x.gov.uk, YSC on youtube.com"  # by service
    assert judged["reject_cookies"][0] is True
    # Accept but no reject; no banner but tracking; no banner and nothing to ask
    assert cookies.judge(200, "Home", [], ["Accept all cookies", "Manage cookies"])["reject_cookies"][0] is False
    assert "without showing a banner" in cookies.judge(200, "Home", ga, [])["reject_cookies"][1]
    assert cookies.judge(200, "Home", [], ["Search"]) == {
        "trackers": (True, "", ""), "reject_cookies": (True, "", "No analytics or advertising cookies, so nothing to ask")}
    # Blocked, a bot check or unreachable: couldn't check, never a fail
    for status, title in [(403, ""), (429, ""), (200, "Just a moment..."), (None, "")]:
        judged = cookies.judge(status, title, ga, [])
        assert judged["trackers"][0] is None and judged["reject_cookies"][0] is None


def test_cookie_checks_run_in_a_browser_for_each_homepage(monkeypatch):
    import sys
    import types
    from pipeline.sources import Result, cookies

    class Playwright:
        chromium = types.SimpleNamespace(launch=lambda: types.SimpleNamespace(close=lambda: None))
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", types.SimpleNamespace(sync_playwright=Playwright))
    visits = {"https://lewisham.gov.uk/": (200, "Lewisham", [{"name": "_ga", "domain": ".lewisham.gov.uk"}],
                                           ["Allow all", "Deny"]),
              "https://www.manchester.gov.uk/": (403, "", [], [])}
    monkeypatch.setattr(cookies, "visit", lambda browser, url: visits[url])
    monkeypatch.setattr(cookies.time, "sleep", lambda seconds: None)
    links = Result(id="local_links", title="", url="", period="", extra={
        "E09000023": {"homepage": "https://lewisham.gov.uk/"}, "E08000003": {"homepage": "https://www.manchester.gov.uk/"}})
    result = cookies.fetch({"results": {"local_links": links}, "population": {"E09000023": 1, "E08000003": 1}})
    assert result.checks["E09000023"]["trackers"]["pass"] is False
    assert result.checks["E09000023"]["trackers"]["evidence"] == "_ga on lewisham.gov.uk"
    assert result.checks["E09000023"]["reject_cookies"]["pass"] is True
    assert result.checks["E08000003"]["trackers"]["pass"] is None
    assert any(note.startswith("E08000003: couldn't check cookies") for note in result.notes)


def test_psaa_finds_the_newest_month_and_each_years_deadline():
    import datetime
    from pipeline.sources import psaa
    listing = ('<a href="https://www.psaa.co.uk/managing-audit-quality/monthly-audit-opinion-data/august-2026-audit-opinion-data/">'
               '<a href="https://www.psaa.co.uk/managing-audit-quality/monthly-audit-opinion-data/september-2026-audit-opinion-data/">'
               '<a href="https://www.psaa.co.uk/managing-audit-quality/monthly-audit-opinion-data/december-2025-audit-opinion-data/">')
    assert psaa.latest_month(listing)[:2] == (2026, 9)
    page = ("<td>2025/26</td><td>31 January 2027</td><td>460 (534)</td>"
            "<td>2024/25</td><td>27 Feb 2026</td><td>457 (531)</td><td>2023/24</td><td>28 Feb 2025</td>")
    assert psaa.backstops(page) == {"2025-2026": datetime.date(2027, 1, 31), "2024-2025": datetime.date(2026, 2, 27),
                                    "2023-2024": datetime.date(2025, 2, 28)}


@pytest.mark.parametrize("status, when, passed, says", [
    ("Delivered by backstop", "2026-02-20", True, "on 20 February 2026, by the deadline"),
    ("Post backstop opinion delivered", "2026-04-15", False, "on 15 April 2026, after the deadline"),
    ("Unsigned", "-", False, "still hadn't signed off its 2024-25 accounts"),
])
def test_psaa_accounts_audited_by_the_deadline(status, when, passed, says):
    import datetime
    from pipeline.sources import psaa
    result, reason = psaa.judge(status, psaa.signed(when), "2024-2025", datetime.date(2026, 2, 27))
    assert result is passed and says in reason


def test_ico_action_in_the_last_three_years(monkeypatch):
    import datetime
    from pipeline.sources import ico

    def item(when, kind, title, url):
        return {"filterItemMetaData": f"{when}, {kind}, Local government", "title": title, "url": url}
    pages = {"local-government": [
        item("16 May 2025", "Reprimands", "London Borough of Hammersmith and Fulham", "/e/2025/05/hf/"),
        item("16 August 2023", "Reprimands", "London Borough of Lewisham", "/e/2023/08/lewisham/"),  # too long ago
        item("29 November 2025", "Reprimands", "Charnwood Borough Council", "/e/2025/11/charnwood/"),  # not on the site
    ], "social-care": [item("27 August 2025", "Enforcement notices", "Bristol City Council", "/e/2025/08/bristol/")]}

    def search(sector, page=1):
        return {"results": pages.get(sector, []), "pagination": {"hasMore": False}}
    monkeypatch.setattr(ico, "search", search)
    monkeypatch.setattr(ico.time, "sleep", lambda seconds: None)

    class Today(datetime.date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 4)
    monkeypatch.setattr(ico.datetime, "date", Today)
    councils = {"E09000013": "Hammersmith and Fulham", "E09000023": "Lewisham", "E06000023": "Bristol, City of"}
    from pipeline.names import Matcher
    result = ico.fetch({"matcher": Matcher(councils), "population": {code: 1 for code in councils}})
    assert result.checks["E09000013"]["ico_action"] == {
        "pass": False, "reason": "The ICO took action against the council: a reprimand on 16 May 2025.",
        "evidence": "https://ico.org.uk/e/2025/05/hf/"}
    assert result.checks["E09000023"]["ico_action"]["pass"] is True
    assert "an enforcement notice on 27 August 2025" in result.checks["E06000023"]["ico_action"]["reason"]
    assert result.period == "November 2023 to November 2026"
