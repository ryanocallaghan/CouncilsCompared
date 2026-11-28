"""Reads Glasgow City Council's committee site, which isn't Modern.gov.

It has the same functions as pipeline.moderngov (calendar, read_meeting and
meeting_url), returning the same shapes, so pipeline.meetings can use either.
Requests go through moderngov.get, so they're checked against robots.txt and
paced the same way.

The site has a "latest meetings" list (from about two weeks ago to two weeks
ahead), an agenda page for each meeting, and a page of papers for each agenda
item. Decisions aren't on the agenda page: they come later, in the minutes.
"""

import datetime
import html
import re
import urllib.parse

from pipeline import moderngov
from pipeline.moderngov import text

ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
BODY = re.compile(r'committee\.asp\?bodyid=(\d+)', re.I)
MEETING = re.compile(r'Agenda\.asp\?meetingid=(\d+)', re.I)
ITEM = re.compile(r'<tr class="tr\d"><td[^>]*>(.*?)</td><td>(.*?)</td></tr>', re.S | re.I)
PAPERS = re.compile(r'submissiondocuments\.asp\?submissionid=(\d+)', re.I)
DOC = re.compile(r'viewDoc\.asp\?c=([^"&]+)', re.I)
PACK = re.compile(r'<a href="(viewPack\.asp\?c=[^"]+)"[^>]*>(.*?)</a>', re.S | re.I)

_latest = {}
_schedules = {}


def _meeting(key_id, body_id, committee, date_cell, time_cell, row):
    day = re.search(r"(\d\d)/(\d\d)/(\d{4})", text(date_cell))
    if not day:
        return None
    clock = re.search(r"(\d\d):(\d\d)", text(time_cell))
    when = datetime.datetime(int(day[3]), int(day[2]), int(day[1]), *(int(clock[1]), int(clock[2])) if clock else (0, 0))
    meeting = MEETING.search(date_cell)
    # Meetings without an agenda yet have no id: name them by committee and time instead
    return {
        "id": meeting[1] if meeting else f"b{body_id}-{when:%Y%m%d%H%M}", "committee_id": body_id,
        "committee": committee, "date": when.isoformat(timespec="minutes"),
        "cancelled": bool(re.search(r"cancelled|postponed", text(row), re.I)),
    }


def latest(site):
    """Every meeting in the site's latest-meetings list (about four days back to three weeks ahead), read once per run."""
    if site not in _latest:
        page = moderngov.get(f"{site}/latestMeetings.asp?page=0&rec=26").decode("utf-8", "ignore")
        meetings = {}
        for row in ROW.findall(page):
            cells = CELL.findall(row)
            body = BODY.search(cells[0]) if len(cells) >= 3 else None
            m = body and _meeting(None, body[1], text(cells[0]), cells[1], cells[2], row)
            if m:
                meetings[m["id"]] = m
        _latest[site] = list(meetings.values())
    return _latest[site]


def schedule(site, body_id, committee, year):
    """A committee's meetings in a year, from its schedule page.

    The latest-meetings list only goes back a few days, so this catches meetings it has already dropped.
    The page needs the committee's name as well as its id, and shows ten meetings at a time unless
    its "Show All" link is followed.
    """
    if (site, body_id, year) not in _schedules:
        url = (f"{site}/allBodyMeetings.asp?bodyid={body_id}&bodytitle={urllib.parse.quote_plus(committee)}"
               f"&MeetingYear={year}")
        page = moderngov.get(url).decode("utf-8", "ignore")
        everything = re.search(r'href="(allBodyMeetings\.asp\?[^"]*?page=0&(?:amp;)?rec=\d+)"', page, re.I)
        if everything:
            page = moderngov.get(f"{site}/{html.unescape(everything[1])}").decode("utf-8", "ignore")
        meetings = []
        for row in ROW.findall(page):
            cells = CELL.findall(row)
            m = len(cells) >= 2 and _meeting(None, body_id, committee, cells[0], cells[1], row)
            if m:
                meetings.append(m)
        _schedules[site, body_id, year] = meetings
    return _schedules[site, body_id, year]


def calendar(site, year, month):
    """A month's meetings: those in the latest list, and those of the same committees from their schedules."""
    found = {m["id"]: m for m in latest(site)}
    for body_id, committee in {(m["committee_id"], m["committee"]) for m in latest(site)}:
        for m in schedule(site, body_id, committee, year):
            found.setdefault(m["id"], m)
    return [m for m in found.values() if m["date"].startswith(f"{year:04d}-{month:02d}")]


def meeting_url(site, meeting):
    if meeting["id"].isdigit():
        return f"{site}/Agenda.asp?meetingid={meeting['id']}"
    return f"{site}/committee.asp?bodyid={meeting['committee_id']}"


def short_title(title):
    """"Scheme of delegations - City Property - Report by Executive Director of ..." loses the "Report by"."""
    return re.sub(r"\s+-\s+(Joint )?Reports? by .*$", "", title).rstrip(" .") or title


def documents(site, submission):
    """The public documents for one agenda item: [{name, type, url}]."""
    page = moderngov.get(f"{site}/submissiondocuments.asp?submissionid={submission}").decode("utf-8", "ignore")
    out = []
    for row in ROW.findall(page):
        cells = CELL.findall(row)
        doc = DOC.search(row)
        if len(cells) < 4 or not doc:
            continue
        if text(cells[2]).lower() != "public":
            continue
        out.append({"name": text(cells[0]), "type": text(cells[1]),
                    # viewDoc.asp is a page with the PDF in a frame; this is the PDF itself
                    "url": f"{site}/viewSelectedDocument.asp?c={urllib.parse.quote(html.unescape(doc[1]), safe='')}"})
    return out


def read_meeting(site, meeting):
    """A meeting's agenda: {"items": [...], "packs": [...]}, as moderngov.read_meeting gives."""
    if not meeting["id"].isdigit():
        return {"items": [], "packs": []}
    page = moderngov.get(meeting_url(site, meeting)).decode("utf-8", "ignore")
    items = []
    for number, cell in ITEM.findall(page):
        papers = PAPERS.search(cell)
        title = text(re.sub(r"<a\b.*?</a>", "", cell, flags=re.S | re.I)).replace("\xa0", " ").strip()
        item = {"number": text(number), "title": title, "report": None, "appendices": [], "sections": {}}
        if papers:
            docs = documents(site, papers[1])
            name = short_title(title)
            reports = [d for d in docs if d["type"].lower() == "report"]
            others = [d for d in docs if d not in reports[:1]]
            if reports:
                item["report"] = {"name": name, "url": reports[0]["url"]}
            # Once the minutes are written, each item gets its part of them as a "Minute" document
            label = lambda d: "minutes of this meeting" if d["type"].lower() == "minute" else d["type"].lower()
            appendices = [d for d in others if label(d) != "minutes of this meeting"]
            item["appendices"] = [{"name": f"{name}: {label(d)}" + (f" {n}" if label(d) != "minutes of this meeting"
                                                                     and len(appendices) > 1 else ""),
                                   "url": d["url"], **({"minutes": True} if d["type"].lower() == "minute" else {})}
                                  for n, d in enumerate(others, 1)]
        items.append(item)
    packs = [{"name": re.sub(r"\(\s*[\d.]+\s*[KM]B\)", "", text(name)).strip(), "url": f"{site}/{html.unescape(href)}"}
             for href, name in PACK.findall(page)]
    return {"items": items, "packs": packs}
