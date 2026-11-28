from pipeline import glasgow, meetings

SITE = "https://onlineservices.glasgow.gov.uk/councillorsandcommittees"

LATEST = """<table class="resultsNew" cellspacing="0">
<tr class="resultsHeader"><td>Committee</td><td>Date</td><td>Start Time</td><td>Agenda Published</td><td>Location</td></tr>
<tr>
 <td class="td0"><a href="committee.asp?bodyid=1882&amp;bodytitle=Contracts+and+Property+Committee" title="x">Contracts and Property Committee</a></td>
 <td class="td0"><a href="Agenda.asp?meetingid=20643">26/11/2026</a></td>
 <td class="td0">13:30&nbsp;</td><td class="td0">19/11/2026</td><td class="td0">City Chambers, Glasgow</td>
</tr>
<tr>
 <td class="td1"><a href="committee.asp?bodyid=1381&bodytitle=Licensing+Board" title="x">Licensing Board</a></td>
 <td class="td1">04/12/2026</td>
 <td class="td1">10:00 </td><td class="td1"> </td><td class="td1"> </td>
</tr>
</table>"""

SCHEDULE = """<table class="resultsNew">
<tr class="resultsHeader"><td>Date</td><td>Start Time</td><td>Location</td><td>Agenda Published</td></tr>
<tr><td class="td0"><a href="Agenda.asp?meetingid=20642">05/11/2026</a></td><td class="td0">13:30</td>
 <td class="td0">City Chambers, Glasgow</td><td class="td0">29/10/2026</td></tr>
<tr><td class="td1"><a href="Agenda.asp?meetingid=20643">26/11/2026</a></td><td class="td1">13:30</td>
 <td class="td1">City Chambers, Glasgow</td><td class="td1">19/11/2026</td></tr>
</table>"""

AGENDA = """<div id="docPacks"><ul><li><a href="viewPack.asp?c=PACK1" title="Opens as a PDF document">Public Agenda(3.47MB)</a></li></ul></div>
<table class="agendaItems" cellspacing="0">
<tr><th class="number">Number</th><th class="item">Item</th></tr>
<tr class="tr0"><td class="valignTop" align="left">1</td><td>Minutes of previous meeting.</td></tr><tr class="tr1"><td class="valignTop" align="left">3</td><td>Authority to negotiate an off-market disposal of site at Glenacre Terrace (Ward 1) - Report by Executive Director of Neighbourhoods, Regeneration and Sustainability.&nbsp;<a href="submissiondocuments.asp?submissionid=124188">View Papers</a></td></tr>
</table>"""

PAPERS = """<table class="resultsNew" cellspacing="0">
<tr class="resultsHeader"><td>Name</td><td>Type of Document</td><td>Access</td><td align="center">View Document</td></tr>
<tr><td class="td0">Item 3 - 0064-26CP.docx</td><td class="td0">Report</td><td class="td0">Public</td>
 <td align="center" class="td0"><a href="viewDoc.asp?c=P62AFQDNUT81UTNTT1"><img src="pdf.gif" /></a><br />(218 KB)</td></tr>
<tr><td class="td1">Item 3 - 0064-26CPPlan.pdf</td><td class="td1">Appendix</td><td class="td1">Public</td>
 <td align="center" class="td1"><a href="viewDoc.asp?c=P62AFQDNUT81UTNTDN"><img src="pdf.gif" /></a><br />(392 KB)</td></tr>
<tr><td class="td1">Item 3 - minute.pdf</td><td class="td1">Minute</td><td class="td1">Public</td>
 <td align="center" class="td1"><a href="viewDoc.asp?c=MINUTE1"><img src="pdf.gif" /></a></td></tr>
<tr><td class="td0">Item 3 - valuation.pdf</td><td class="td0">Appendix</td><td class="td0">Private</td>
 <td align="center" class="td0"><a href="viewDoc.asp?c=SECRET"><img src="pdf.gif" /></a></td></tr>
</table>"""


def fake_get(pages):
    def get(url, **kwargs):
        for key, body in pages.items():
            if key in url:
                return body.encode()
        raise AssertionError(url)
    return get


def test_latest_meetings(monkeypatch):
    glasgow._latest.clear()
    glasgow._schedules.clear()
    monkeypatch.setattr(glasgow.moderngov, "get", fake_get({"latestMeetings.asp": LATEST, "bodyid=1882&bodytitle=Contracts+and+Property+Committee": SCHEDULE,
                                                            "bodyid=1381&bodytitle=Licensing+Board": "<p>No meetings were found.</p>"}))
    november = sorted(glasgow.calendar(SITE, 2026, 11), key=lambda m: m["date"])
    # One the latest list has already dropped comes from the committee's schedule
    assert november[0] == {"id": "20642", "committee_id": "1882", "committee": "Contracts and Property Committee",
                           "date": "2026-11-05T13:30", "cancelled": False}
    november = november[1:]
    assert november == [{"id": "20643", "committee_id": "1882", "committee": "Contracts and Property Committee",
                         "date": "2026-11-26T13:30", "cancelled": False}]
    # A meeting with no agenda yet is named by its committee and time, and links to the committee's page
    december = glasgow.calendar(SITE, 2026, 12)[0]
    assert december["id"] == "b1381-202612041000"
    assert glasgow.meeting_url(SITE, december) == SITE + "/committee.asp?bodyid=1381"
    assert glasgow.meeting_url(SITE, november[0]) == SITE + "/Agenda.asp?meetingid=20643"
    assert meetings.CASEWORK.search(december["committee"])


def test_agenda_and_public_papers_only(monkeypatch):
    monkeypatch.setattr(glasgow.moderngov, "get", fake_get({"Agenda.asp": AGENDA, "submissiondocuments.asp": PAPERS}))
    page = glasgow.read_meeting(SITE, {"id": "20643", "committee_id": "1882"})
    minutes, disposal = page["items"]
    assert meetings.routine(minutes) and minutes["report"] is None
    assert disposal["number"] == "3"
    assert disposal["report"] == {"name": "Authority to negotiate an off-market disposal of site at Glenacre Terrace (Ward 1)",
                                  "url": SITE + "/viewSelectedDocument.asp?c=P62AFQDNUT81UTNTT1"}
    # The private valuation isn't included
    # The minute is labelled as the record of the meeting, and read in full
    assert disposal["appendices"] == [{"name": disposal["report"]["name"] + ": appendix",
                                       "url": SITE + "/viewSelectedDocument.asp?c=P62AFQDNUT81UTNTDN"},
                                      {"name": disposal["report"]["name"] + ": minutes of this meeting",
                                       "url": SITE + "/viewSelectedDocument.asp?c=MINUTE1", "minutes": True}]
    assert page["packs"] == [{"name": "Public Agenda", "url": SITE + "/viewPack.asp?c=PACK1"}]
    # Its papers are downloaded from the address the site gave, not one built from a path
    assert meetings.doc_url(meetings.SITES["S12000049"], disposal["report"]) == disposal["report"]["url"]
