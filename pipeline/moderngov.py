"""Reading a council's Modern.gov site: its meetings, and each meeting's agenda.

Most councils publish their meetings with Modern.gov. Its pages are the same
everywhere: a calendar of meetings by month, and a page for each meeting
listing the agenda items, each with its report, any appendices, and the
decision once it has been made.

Every address is checked against the site's robots.txt before it is asked
for, and a site that says no is not read.
"""

import datetime
import html
import re
import urllib.error
import urllib.parse
import urllib.robotparser

from pipeline import http

PAUSE = 2  # seconds between requests, so a council's site is never busy because of us


class Disallowed(Exception):
    """The site's robots.txt asks automated readers not to fetch this address."""


_robots = {}


def allowed(url):
    """Whether the site's robots.txt lets us fetch url. No robots.txt means yes."""
    parts = urllib.parse.urlsplit(url)
    site = f"{parts.scheme}://{parts.netloc}"
    if site not in _robots:
        parser = urllib.robotparser.RobotFileParser()
        try:
            parser.parse(http.get_text(f"{site}/robots.txt", retries=1).splitlines())
        except urllib.error.HTTPError as e:
            if e.code not in (404, 410):
                raise
            parser.parse([])
        _robots[site] = parser
    return _robots[site].can_fetch(http.USER_AGENT, url)


def get(url, **kwargs):
    if not allowed(url):
        raise Disallowed(url)
    return http.get(url, pause=PAUSE, **kwargs)


def text(fragment):
    """Plain text from a piece of a page, with paragraphs on lines of their own."""
    fragment = re.sub(r"\s+", " ", fragment)  # line breaks in the page's source aren't line breaks in the text
    fragment = re.sub(r"<span\s+class=\"mgFileSize\".*?</span>", " ", fragment, flags=re.S | re.I)
    fragment = re.sub(r"<(br|/p|/div|/li|/tr|/h\d)\b[^>]*>", "\n", fragment, flags=re.I)
    fragment = html.unescape(re.sub(r"<[^>]+>", " ", fragment)).replace("\xa0", " ")
    lines = (re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in fragment.split("\n"))
    return "\n".join(line for line in lines if line)


# "Meeting of CANCELLED - Licensing Sub-Committee, 04/11/2026 10.00 am", or without "Meeting of"
# "Meeting of MOVED - Moved from 5 Nov, Planning Committee, 29/10/2026 6.30 pm"
CALENDAR_ITEM = re.compile(r'ieListDocuments\.aspx\?CId=(\d+)&(?:amp;)?MId=(\d+)"[^>]*?title="([^"]+)"')
MEETING_TITLE = re.compile(r"^(?:(?P<flag>[A-Z][A-Z ]+?)\s+-\s+(?:(?:Moved|Rescheduled|Postponed)\b[^,]*,\s*)?)?"
                           r"(?P<committee>.+?),\s*(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<time>\d{1,2}\.\d{2}\s*[ap]m)")


def calendar(site, year, month):
    """The meetings in a month: [{id, committee_id, committee, date, cancelled}], date as ISO date and time."""
    page = get(f"{site}/mgCalendarMonthView.aspx?M={month}&DD={year}&CID=0&OT=&C=-1&MD=0").decode("utf-8", "ignore")
    meetings = {}
    for committee_id, meeting_id, title in CALENDAR_ITEM.findall(page):
        match = MEETING_TITLE.match(text(title).removeprefix("Meeting of "))  # some sites leave it out
        if not match:
            continue
        when = datetime.datetime.strptime(f"{match['date']} {match['time'].replace(' ', '')}", "%d/%m/%Y %I.%M%p")
        flag = (match["flag"] or "").upper()
        meetings[meeting_id] = {
            "id": meeting_id,
            "committee_id": committee_id,
            "committee": committee_name(match["committee"].strip()),
            "date": when.isoformat(timespec="minutes"),
            "cancelled": flag.startswith(("CANCELLED", "POSTPONED")),
        }
    return list(meetings.values())


COMMITTEE_WORDS = re.compile(r"\b(committee|sub-committee|board|panel|council|cabinet|forum|commission|"
                             r"partnership|group|assembly)$", re.I)


def committee_name(name):
    """The committee, without a title given to this one meeting. Modern.gov puts that first:
    "Call-In meeting, Resources and Public Realm Scrutiny Committee". Committee names can have commas
    too ("Brent, Lewisham and Southwark IT Committee"), so a title is only taken off when what's left
    is itself a committee's name and what comes before is more than one word."""
    title, sep, rest = name.rpartition(", ")
    if sep and COMMITTEE_WORDS.search(rest) and len(title.split()) > 1:
        return rest
    return name


def meeting_url(site, meeting):
    return f"{site}/ieListDocuments.aspx?CId={meeting['committee_id']}&MId={meeting['id']}"


ITEM_START = re.compile(r'<td\s+class="mgItemNumberCell"\s*>', re.I)
DOC_LINK = re.compile(r'<a\s[^>]*?href="([^"]+?\.pdf)(?:\?[^"]*)?"[^>]*?>', re.I)
DOC_TITLE = re.compile(r"title=\"Link to document '(.*?)' pdf file\"", re.I)
SECTION = re.compile(r'<p\s+class="mgSubItemTitleTxt"\s*>\s*(.*?)\s*</p>', re.I | re.S)


def _doc(site, tag, fallback_name):
    href = html.unescape(DOC_LINK.match(tag).group(1))
    path = urllib.parse.urlsplit(urllib.parse.urljoin(site + "/", href)).path
    title = DOC_TITLE.search(html.unescape(tag))
    name = title.group(1) if title else urllib.parse.unquote(path.rsplit("/", 1)[-1]).removesuffix(".pdf")
    return {"name": re.sub(r"\s+", " ", name or fallback_name).strip(), "path": urllib.parse.unquote(path)}


def read_meeting(site, meeting):
    """A meeting's page: {"items": agenda items, "packs": documents for the whole meeting}."""
    page = get(meeting_url(site, meeting)).decode("utf-8", "ignore")
    return {"items": agenda(site, page), "packs": packs(site, page)}


def agenda(site, page):
    """The agenda items on a meeting's page: [{number, title, report, appendices, sections}].

    report is the item's main document ({name, path}) or None; appendices are
    its other documents; sections is the text under each heading on the
    page, such as {"Decision": "..."} or {"Minutes": "..."}.
    """
    starts = [m.start() for m in ITEM_START.finditer(page)]
    end = page.find("</table>", starts[-1]) if starts else -1
    items = []
    for i, start in enumerate(starts):
        chunk = page[start:starts[i + 1] if i + 1 < len(starts) else end]
        cells = re.findall(r'<p\s+class="mgAiTitleTxt"\s*>(.*?)</p>', chunk, re.S | re.I)
        if len(cells) < 2:
            continue
        number, heading = text(cells[0]).rstrip("."), cells[1]
        title = text(heading)
        link = DOC_LINK.search(heading)
        report = _doc(site, link.group(0), title) if link else None
        appendices, sections = [], {}
        # The text after each heading ("Additional documents:", "Decision:", "Minutes:")
        marks = list(SECTION.finditer(chunk))
        for j, mark in enumerate(marks):
            label = text(mark.group(1)).rstrip(":")
            body = chunk[mark.end():marks[j + 1].start() if j + 1 < len(marks) else len(chunk)]
            if label.lower().startswith("additional document"):
                appendices += [_doc(site, m.group(0), "Appendix") for m in DOC_LINK.finditer(body)]
            elif text(body):
                sections[label] = text(body)
        # Text straight after the title, before any heading, says what the item is about
        intro = chunk[chunk.find(heading) + len(heading):marks[0].start() if marks else len(chunk)]
        if text(intro):
            sections = {"About": text(intro), **sections}
        items.append({"number": number, "title": title, "report": report, "appendices": appendices,
                      "sections": sections})
    return items


def packs(site, page):
    """The documents for the whole meeting ("Agenda reports pack", "Printed decisions"), from its page."""
    head = page.split('class="mgItemNumberCell"', 1)[0]
    out = []
    for m in re.finditer(r'<a\s[^>]*?href="([^"]*?/g\d+/[^"]+?\.pdf)(?:\?[^"]*)?"[^>]*>(.*?)</a>', head, re.S | re.I):
        path = urllib.parse.urlsplit(urllib.parse.urljoin(site + "/", html.unescape(m.group(1)))).path
        out.append({"name": text(m.group(2)), "path": urllib.parse.unquote(path)})
    return out
