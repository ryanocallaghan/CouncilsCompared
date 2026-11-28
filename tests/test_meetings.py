import datetime
import hashlib
import json
import os
from types import SimpleNamespace

import pytest

from pipeline import meetings, moderngov

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
SITE = {"name": "Testham", "list": "https://democracy.example.gov.uk", "docs": "https://docs.example.gov.uk"}
MEETING = {"id": "9000", "committee_id": "115", "committee": "Cabinet", "date": "2026-11-18T19:00",
           "cancelled": False}


@pytest.fixture
def page():
    with open(os.path.join(FIXTURES, "moderngov_meeting.html")) as f:
        html = f.read()
    return {"items": moderngov.agenda(SITE["list"], html), "packs": moderngov.packs(SITE["list"], html)}


def test_calendar_reads_meetings_cancellations_and_moves(monkeypatch):
    html = (
        '<a href="ieListDocuments.aspx?CId=183&amp;MId=4508"  title="Meeting&#32;of&#32;Cabinet,&#32;18&#47;11&#47;'
        '2026&#32;6.30&#32;pm&#32;">Cabinet</a>'
        '<a href="ieListDocuments.aspx?CId=162&amp;MId=4695"  title="Meeting&#32;of&#32;CANCELLED&#32;-&#32;Licensing'
        '&#32;Sub-Committee,&#32;04&#47;11&#47;2026&#32;10.00&#32;am&#32;">x</a>'
        '<a href="ieListDocuments.aspx?CId=136&amp;MId=4532"  title="Meeting&#32;of&#32;MOVED&#32;-&#32;Moved&#32;from'
        '&#32;5&#32;Nov,&#32;Planning&#32;Committee,&#32;29&#47;10&#47;2026&#32;6.30&#32;pm&#32;">x</a>'
        '<a href="ieListDocuments.aspx?CId=1046&amp;MId=12251"  title="Planning&#32;Committee,&#32;28&#47;10&#47;2026'
        '&#32;7.00&#32;pm&#32;">x</a>'
        '<a href="ieListDocuments.aspx?CId=1013&amp;MId=11503&amp;Info=1" title="Link to Constitution">x</a>'
        '<a href="mgCalendarMonthView.aspx?M=12" title="Next month">Next</a>'
    )
    monkeypatch.setattr(moderngov, "get", lambda url: html.encode())
    found = {m["id"]: m for m in moderngov.calendar(SITE["list"], 2026, 11)}
    assert found["4508"] == {"id": "4508", "committee_id": "183", "committee": "Cabinet", "date": "2026-11-18T18:30",
                             "cancelled": False}
    assert found["4695"]["cancelled"] and found["4695"]["committee"] == "Licensing Sub-Committee"
    assert found["4532"]["committee"] == "Planning Committee" and not found["4532"]["cancelled"]
    assert found["12251"]["committee"] == "Planning Committee"  # a site that leaves out "Meeting of"
    assert len(found) == 4


def test_agenda_items_have_reports_appendices_and_decisions(page):
    items = {i["number"]: i for i in page["items"]}
    assert items["1"]["title"] == "Apologies for Absence" and items["1"]["report"] is None
    budget = items["3"]
    assert budget["title"] == "Draft Budget 2027-28"
    assert budget["report"] == {"name": "Draft Budget 2027-28", "path": "/documents/s102/Budget 2027-28 Cover Report.pdf"}
    assert [a["name"] for a in budget["appendices"]] == ["Appendix 1 - Savings proposals", "Appendix 2 - Equalities"]
    # Line breaks in the page's source are joined up; paragraphs stay apart
    assert budget["sections"]["Decision"] == "Resolved-\n1) That the Cabinet agree the draft budget for consultation."
    assert meetings.routine(items["1"]) and meetings.routine(items["2"]) and not meetings.routine(budget)
    assert meetings.exempt(items["4"]) and not meetings.exempt(budget)
    # Brent's "Supported Accommodation" item mentions "supported exempt accommodation", a kind of housing
    housing = {"title": "Supported Accommodation", "sections": {"About": "Including non-commissioned supported exempt accommodation."}}
    assert not meetings.exempt(housing)
    assert meetings.exempt({"title": "Exempt minutes", "sections": {}})
    assert [p["name"] for p in page["packs"]] == ["Agenda frontsheet", "Agenda reports pack"]


def fake_pdfs(monkeypatch, pages):
    """Downloads that return the URL itself, and PDFs of pages[name] pages of text each."""
    monkeypatch.setattr(meetings, "pdf_pages", lambda data: [f"text of {data.decode()} p{n}"
                                                             for n in range(1, pages(data.decode()) + 1)])
    return lambda url: url.encode()


def test_routine_confidential_and_repeated_papers_are_not_read(monkeypatch, page):
    get = fake_pdfs(monkeypatch, lambda url: 60 if "Budget" in url else 9)
    appendix_2 = SITE["docs"] + "/documents/s104/Appendix%202%20-%20Equalities.pdf"
    seen = {hashlib.sha256(appendix_2.encode()).hexdigest(): "Scrutiny Committee, 10 November 2026"}
    items, papers = meetings.gather(SITE, MEETING, page, seen, get=get)
    assert "Housing Contract (Exempt Category 3)" not in [i["title"] for i in items]
    records = {r["name"]: r for r in (p.record() for p in papers)}
    assert set(records) == {"Draft Budget 2027-28", "Appendix 1 - Savings proposals", "Appendix 2 - Equalities"}
    assert records["Draft Budget 2027-28"]["read"] == f"first {meetings.MAX_PAGES} of 60 pages"
    assert records["Appendix 1 - Savings proposals"]["read"] == f"first {meetings.APPENDIX_PAGES} of 9 pages"
    assert records["Appendix 2 - Equalities"]["read"] == "same as the papers for Scrutiny Committee, 10 November 2026"
    # Papers only count as seen once their summary is saved (by run)
    assert len(seen) == 1


def test_the_whole_pack_is_read_only_when_no_item_has_papers(monkeypatch, page):
    get = fake_pdfs(monkeypatch, lambda url: 3)
    routine_only = {**page, "items": [i for i in page["items"] if meetings.routine(i)]}
    _, papers = meetings.gather(SITE, MEETING, routine_only, {}, get=get)
    assert papers == []  # the minutes are routine, so nothing is read, not even the pack
    no_papers = {**page, "items": [{**i, "report": None, "appendices": []} for i in page["items"]]}
    _, papers = meetings.gather(SITE, MEETING, no_papers, {}, get=get)
    assert [p.name for p in papers] == ["Agenda reports pack"]


def test_long_papers_lose_appendices_then_pages(monkeypatch, page):
    monkeypatch.setattr(meetings, "MAX_TOKENS", 50)
    get = fake_pdfs(monkeypatch, lambda url: 60 if "Budget" in url else 9)
    _, papers = meetings.gather(SITE, MEETING, page, {}, get=get)
    assert [p.read for p in papers] == [15, 0, 0]
    assert papers[1].record()["read"] == "not read: the papers were too long"


def test_the_prompt_numbers_each_paper_and_page(monkeypatch, page):
    get = fake_pdfs(monkeypatch, lambda url: 3)
    items, papers = meetings.gather(SITE, MEETING, page, {}, get=get)
    text, numbered = meetings.prompt("Testham", MEETING, items, papers)
    assert "Date: Wednesday 18 November 2026, 7pm" in text
    assert "## Agenda item 1: Apologies for Absence\n(Routine business: papers not read.)" in text
    assert "[D0] Decision: Resolved-\n1) That the Cabinet agree the draft budget for consultation." in text
    assert "[D1] Report: Draft Budget 2027-28 (3 pages, all read)" in text
    assert "[D2] Appendix: Appendix 1 - Savings proposals (3 pages, first 2 read)" in text
    assert "--- D2 page 2 ---" in text and "--- D2 page 3 ---" not in text
    assert "Minutes of previous meeting" not in text and "Housing Contract" not in text
    assert [p.name for p in numbered] == ["Draft Budget 2027-28", "Appendix 1 - Savings proposals",
                                          "Appendix 2 - Equalities"]


class FakeClient:
    """Answers like the API, and keeps what it was sent."""

    def __init__(self, answer, stop_reason="end_turn"):
        self.sent = []
        reply = SimpleNamespace(stop_reason=stop_reason, usage=SimpleNamespace(input_tokens=1200, output_tokens=300),
                                content=[SimpleNamespace(type="text", text=json.dumps(answer))])

        def create(**kwargs):
            self.sent.append(kwargs)
            return reply
        self.messages = SimpleNamespace(create=create)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=create))


ANSWER = {"summary": "The cabinet agreed a draft budget for 2027-28 to consult residents on.", "points": [
    {"title": "Draft budget", "text": "The cabinet agreed to consult on the draft budget.",
     "sources": [{"doc": 0, "page": 0}, {"doc": 1, "page": 2}, {"doc": 9, "page": 1}]},
    {"title": "Made up", "text": "A point with no real source.", "sources": [{"doc": 7, "page": 1}]},
]}


def test_each_point_links_to_the_pages_it_came_from(monkeypatch, page):
    get = fake_pdfs(monkeypatch, lambda url: 3)
    client = FakeClient(ANSWER)
    entry, why, usage = meetings.summarise(client, "Testham", SITE, MEETING, page, {}, get=get)
    assert why == "" and usage == {"input": 1200, "output": 300}
    assert entry["summary"] == ANSWER["summary"]
    # A source that isn't one of the papers is dropped, and so is a point left with none
    assert entry["points"] == [{"title": "Draft budget", "text": "The cabinet agreed to consult on the draft budget.",
                                "sources": [
        {"label": "the meeting's page", "url": SITE["list"] + "/ieListDocuments.aspx?CId=115&MId=9000"},
        {"label": "Draft Budget 2027-28, page 2",
         "url": SITE["docs"] + "/documents/s102/Budget%202027-28%20Cover%20Report.pdf#page=2"},
    ]}]
    sent = client.sent[0]
    assert sent["model"] == "claude-opus-5-5" and sent["fallbacks"] == "default"
    assert sent["betas"] == ["server-side-fallback-2026-07-01"]
    assert sent["output_config"]["format"]["type"] == "json_schema" and sent["output_config"]["effort"] == "medium"
    assert "--- D1 page 2 ---" in sent["messages"][0]["content"]


def test_a_model_without_fallbacks_is_asked_plainly(monkeypatch, page):
    get = fake_pdfs(monkeypatch, lambda url: 3)
    client = FakeClient(ANSWER)
    meetings.summarise(client, "Testham", SITE, MEETING, page, {}, get=get, model="claude-haiku-5-5")
    assert client.sent[0]["model"] == "claude-haiku-5-5" and "fallbacks" not in client.sent[0]


def test_a_declined_summary_is_not_saved(monkeypatch, page):
    get = fake_pdfs(monkeypatch, lambda url: 3)
    entry, why, _ = meetings.summarise(FakeClient({}, stop_reason="refusal"), "Testham", SITE, MEETING, page, {},
                                       get=get)
    assert entry is None and why == "Claude declined to summarise it"


def test_robots_txt_is_respected(monkeypatch):
    monkeypatch.setattr(moderngov, "_robots", {})
    monkeypatch.setattr(moderngov.http, "get_text", lambda url, **kw: "User-agent: *\nDisallow: /\n")
    with pytest.raises(moderngov.Disallowed):
        moderngov.get("https://blocked.example.gov.uk/ieListDocuments.aspx?MId=1")
    monkeypatch.setattr(moderngov, "_robots", {})
    monkeypatch.setattr(moderngov.http, "get_text", lambda url, **kw: "User-agent: *\nDisallow: /*.asmx$\n")
    assert moderngov.allowed("https://open.example.gov.uk/documents/s1/Report.pdf")


def test_run_adds_new_meetings_keeps_old_ones_and_skips_hearings(monkeypatch, tmp_path, page):
    path = tmp_path / "meetings.json"
    old = {"id": "1", "committee": "Council", "date": "2026-10-01T19:00", "papers": [], "summary": "Old."}
    stale = {"id": "2", "committee": "Council", "date": "2026-06-01T19:00", "papers": [], "summary": "Too old."}
    path.write_text(json.dumps({"checked": "2026-10-02", "councils": {"E1": {"held": [old, stale], "upcoming": []}}}))
    monkeypatch.setattr(meetings, "MEETINGS", str(path))
    monkeypatch.setattr(meetings, "SITES", {"E1": SITE})
    calendar = [MEETING,
                {**MEETING, "id": "9001", "committee": "Licensing Sub-Committee B"},
                {**MEETING, "id": "9002", "date": "2026-11-30T19:00"},
                {**MEETING, "id": "9003", "cancelled": True}]
    monkeypatch.setattr(moderngov, "calendar", lambda site, year, month: calendar if month == 11 else [])
    asked = []
    monkeypatch.setattr(moderngov, "read_meeting", lambda site, m: asked.append(m["id"]) or page)
    monkeypatch.setattr(moderngov, "get", fake_pdfs(monkeypatch, lambda url: 3))
    data, report, usage = meetings.run(FakeClient(ANSWER), now=datetime.datetime(2026, 11, 23, 9))
    assert asked == ["9000"]  # not the hearing, the cancelled meeting or the one still to come
    assert all(p["sha"] for p in data["councils"]["E1"]["held"][0]["papers"])
    council = data["councils"]["E1"]
    assert [m["id"] for m in council["held"]] == ["9000", "1"]  # newest first; June's has gone
    assert [m["id"] for m in council["upcoming"]] == ["9002"]
    assert report == [("Testham", 1, "")] and usage == [{"input": 1200, "output": 300}]
    assert "$0.01" in meetings.summary_text(report, usage)


def test_cost_counts_haikus_higher_price_for_long_requests():
    assert meetings.cost([{"input": 1_000_000, "output": 0}], "claude-opus-5-5") == 4
    assert meetings.cost([{"input": 200_000, "output": 0}], "claude-haiku-5-5") == pytest.approx(0.1)
    assert meetings.cost([{"input": 1, "output": 1}], "some-other-model") is None


def test_pdf_text_with_a_word_on_each_line_is_put_back_together():
    words = "The Policy statement sets out the Council’s policies on the pay of its Chief Officers , and lowest-paid employees ."
    broken = "\n \n".join(words.split())
    assert meetings.tidy(broken) == words.replace(" ,", ",").replace(" .", ".")
    # Ordinary text keeps its lines
    assert meetings.tidy("Report title:  Budget\n\nDate: 18 November 2026") == "Report title: Budget\n\nDate: 18 November 2026"


def test_meetings_about_one_persons_case_are_left_out():
    for name in ["Licensing Sub-Committee", "Adoption Panel", "Appointments Committee",
                 "Appointments of the Interim Executive Director of Housing, Appointments Sub Committee"]:
        assert meetings.CASEWORK.search(name), name
    for name in ["Cabinet", "Licensing and General Purposes Committee", "Brent Housing Scrutiny Committee"]:
        assert not meetings.CASEWORK.search(name), name


def test_a_meetings_own_title_is_taken_off_the_committee_name():
    name = moderngov.committee_name
    assert name("Call-In meeting, Resources and Public Realm Scrutiny Committee") == "Resources and Public Realm Scrutiny Committee"
    assert name("This meeting will take place at 11:15am or on the rising of the Cabinet, whichever is the later, "
                "General Purposes Committee") == "General Purposes Committee"
    assert name("To be hosted as an online meeting by the London Borough of Barnet, Welsh Harp Joint Consultative "
                "Committee") == "Welsh Harp Joint Consultative Committee"
    # Commas that are part of the name stay
    for whole in ["Brent, Lewisham and Southwark IT Committee", "Governance, Audit, Risk Management and Standards "
                  "Committee (GARMS)", "Joint Committee of the London Boroughs of Brent, Lewisham and Southwark",
                  "Cabinet"]:
        assert name(whole) == whole
