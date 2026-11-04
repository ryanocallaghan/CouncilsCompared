"""Our own checks of each council's website and email domain.

These aren't published statistics: we look at each council's site once a
month, the same way for every council, and keep what we found so anyone can
see why a council passed or failed.

- dmarc: the DMARC record for the website's domain tells mail servers to
  quarantine or reject email that fails the council's checks, for all mail.
- https: the homepage sends a Strict-Transport-Security header lasting at
  least a year, so browsers only ever connect securely.
- security_txt: /.well-known/security.txt says how to report a security
  problem (RFC 9116): it has a Contact line and hasn't expired.
- a11y_statement: the accessibility statement linked from the homepage says
  it was prepared, reviewed or updated in the last year. Only the dates the
  statement gives for itself count ("This statement was last reviewed on
  ..."), not when the page was edited or the website tested.

The homepage comes from GOV.UK's Local Links Manager. When a site blocks us
or can't be reached, the answer is "couldn't check" (None), never a fail.
We never get past a bot challenge, log in or submit a form.
"""

import datetime
import html
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urljoin

import dns.exception
import dns.resolver

from pipeline.http import USER_AGENT
from pipeline.sources import Result

ID = "website"
PAGE = "https://councilscompared.com/about/#our-checks"
MAX_AGE_DAYS = 28  # monthly
PAUSE = 0.5
YEAR = 31536000  # seconds: the shortest max-age browsers' HSTS preload lists accept


def host(homepage):
    """ "http://www.lewisham.gov.uk/home" -> "www.lewisham.gov.uk"."""
    return re.sub(r"^[a-z]+://", "", homepage.strip().lower()).split("/")[0].split(":")[0]


SUFFIXES = ("gov.uk", "gov.scot", "gov.wales", "org.uk", "co.uk")  # two-part endings, as in lewisham.gov.uk


def domain(homepage):
    """ "https://new.enfield.gov.uk/" -> "enfield.gov.uk": the council's own domain, which its email
    comes from, whatever part of it the website is on."""
    labels = host(homepage).split(".")
    keep = 3 if ".".join(labels[-2:]) in SUFFIXES else 2
    return ".".join(labels[-keep:])


def get_page(url):
    """(status, final url, headers in lower case, text) for url; status None if it couldn't be reached."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return (response.status, response.geturl(), {k.lower(): v for k, v in response.headers.items()},
                    response.read(2_000_000).decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        return e.code, url, {k.lower(): v for k, v in e.headers.items()}, ""
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return None, url, {}, ""


def dmarc_records(name):
    """The TXT records at _dmarc.<name> that are DMARC records ([] if none); None if DNS failed."""
    try:
        answers = dns.resolver.resolve(f"_dmarc.{name}", "TXT", lifetime=20)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return []
    except dns.exception.DNSException:
        return None
    records = [b"".join(r.strings).decode("utf-8", errors="replace").strip() for r in answers]
    return [r for r in records if r.lower().startswith("v=dmarc1")]


def dmarc(records):
    """(pass, reason, evidence) for the DMARC records found."""
    if records is None:
        return None, "We couldn't look up its DMARC record.", ""
    if not records:
        return False, "It has no DMARC record, so nothing stops email being faked to look as if it's from the council.", ""
    if len(records) > 1:
        return False, "It has more than one DMARC record, so mail servers ignore them all.", " | ".join(records)
    record = records[0]
    tags = dict((k.strip().lower(), v.strip().lower()) for k, _, v in
                (part.partition("=") for part in record.split(";") if "=" in part))
    policy = tags.get("p", "")
    if policy not in ("quarantine", "reject"):
        return (False, f"Its DMARC policy is “{policy or 'missing'}”, so faked email is still delivered. "
                       "It needs to be quarantine or reject.", record)
    pct = tags.get("pct", "100")
    if pct != "100":
        return False, f"Its DMARC policy only applies to {pct}% of email (pct={pct}).", record
    return True, "", record


def hsts(status, final, headers):
    """(pass, reason, evidence) for the homepage's response."""
    if status is None or status >= 400:
        return None, "We couldn't load the homepage" + (f" (it returned {status})." if status else "."), ""
    if not final.startswith("https://"):
        return False, "The homepage sends people to an insecure (http) address.", final
    header = headers.get("strict-transport-security", "")
    if not header:
        return False, "The homepage doesn't send a Strict-Transport-Security header.", ""
    match = re.search(r"max-age\s*=\s*\"?(\d+)", header, re.I)
    seconds = int(match[1]) if match else 0
    if seconds == 0:
        return False, "Its Strict-Transport-Security header turns the protection off (max-age=0).", header
    if seconds < YEAR:
        return False, f"Its Strict-Transport-Security header lasts only {lasts(seconds)}. It needs to last at least a year.", header
    return True, "", header


def lasts(seconds):
    days = seconds / 86400
    if days >= 1:
        return f"{round(days)} day{'s' if round(days) != 1 else ''}"
    return f"{seconds} second{'s' if seconds != 1 else ''}"


def security_txt(status, final, headers, text, today):
    """(pass, reason, evidence) for the response to /.well-known/security.txt."""
    if status is None or status in (401, 403, 429) or status >= 500:
        return None, "We couldn't check: the site didn't let us look" + (f" (it returned {status})." if status else "."), ""
    if status in (404, 410) or status >= 400:
        return False, "There's no security.txt file.", final
    if "text/plain" not in headers.get("content-type", "") or not re.search(r"(?im)^\s*contact\s*:", text):
        return False, "There's no security.txt file: the address shows a web page instead.", final
    expires = re.search(r"(?im)^\s*expires\s*:\s*(\d{4}-\d{2}-\d{2})", text)
    try:
        expired = expires and datetime.date.fromisoformat(expires[1]) < today
    except ValueError:  # not a real date, such as 30 February: not held against the council
        expired = False
    if expired:
        return False, f"Its security.txt file expired on {expires[1]}.", final
    return True, "", final


MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
               "november", "december"]
DATE = (r"(?:(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s+)?"
        r"(?:(?:the\s+)?(\d{1,2})\s*(?:st|nd|rd|th)?\s+(?:of\s+)?)?(" + "|".join(MONTH_NAMES) + r"),?\s+(\d{4})"
        r"|(\d{1,2})/(\d{1,2})/(\d{4})")
# "This statement was prepared on 7 May 2024. It was last reviewed on 1 February 2025." and the like:
# the dates a statement gives for itself
STATEMENT_DATE = re.compile(
    r"(?:statement|\bit)\s+(?:was|has been|is):?\s+(?:first\s+|last\s+|originally\s+)?(?:prepared|reviewed|updated|revised|published|created|written)"
    r"(?:\s+and\s+(?:last\s+)?(?:reviewed|updated))?\s*(?:on|in|:)?\s*:?\s*(" + DATE.replace("(", "(?:").replace("(?:?:", "(?:") + ")",
    re.I)
# Words every accessibility statement has, following the regulations' model statement
IS_STATEMENT = re.compile(r"(fully|partially|not) compliant|compliance status|preparation of this accessibility statement",
                          re.I)


# Soon after the word "statement": "This statement was: originally prepared on 8 April 2020 last reviewed
# on 16 September 2025". Not "updated" on its own, which is how pages say when they were last edited.
NEAR_STATEMENT = re.compile(r"\b(?:prepared|reviewed|revised|created)\s+(?:on|in)?\s*:?\s*("
                            + DATE.replace("(", "(?:").replace("(?:?:", "(?:") + ")", re.I)


def anchors(base, page):
    """[(url, text)] for each link on a page."""
    return [(urljoin(base, html.unescape(href)), re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip())
            for href, text in re.findall(r'<a\b[^>]*?href="([^"#]+)"[^>]*>(.*?)</a>', page, re.I | re.S)]


def plain(page):
    """A page's text, without its scripts, styles and markup."""
    page = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", page)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))


def to_date(text):
    """ "7 May 2024", "May 2024" (the end of the month) or "07/05/2024" -> a date, or None."""
    match = re.fullmatch(DATE, text.strip().rstrip(".,"), re.I)
    if not match:
        return None
    day, month, year, d2, m2, y2 = match.groups()
    try:
        if month:
            month_number = MONTH_NAMES.index(month.lower()) + 1
            if day:
                return datetime.date(int(year), month_number, int(day))
            following = datetime.date(int(year) + month_number // 12, month_number % 12 + 1, 1)
            return following - datetime.timedelta(days=1)
        return datetime.date(int(y2), int(m2), int(d2))
    except ValueError:
        return None


def statement_link(base, page):
    """The homepage's link to its accessibility statement, or None: one that says "statement" first,
    then a plain "Accessibility" on the council's own site."""
    site = domain(base)
    links = [(url, text) for url, text in anchors(base, page)
             if re.search(r"accessib", text, re.I) and len(text) < 60
             and not re.search(r"tool|reader|recite|translate|browsealoud|options|settings|help|support|recruit|job",
                               text, re.I)]

    def rank(link):
        url, text = link
        return ("statement" not in text.lower(), domain(url) != site,
                not re.fullmatch(r"(website |web )?accessibility", text, re.I))
    links.sort(key=rank)
    return links[0][0] if links else None


def statement_dates(text, today):
    """The dates a statement gives for itself, up to today."""
    found = STATEMENT_DATE.findall(text)
    for word in re.finditer(r"statement", text, re.I):
        found += NEAR_STATEMENT.findall(text[word.end():word.end() + 250])
    dates = {to_date(match) for match in found}
    return sorted(d for d in dates if d and d <= today)


def a11y_statement(found, today):
    """(pass, reason, evidence) for the statement found: (url, text) or None."""
    if not found:
        return None, "We couldn't find an accessibility statement linked from the homepage.", ""
    url, text = found
    dates = statement_dates(text, today)
    if not dates:
        return False, "Its accessibility statement doesn't say when it was prepared or last reviewed.", url
    latest = dates[-1]
    if (today - latest).days > 365:
        return False, f"Its accessibility statement was last reviewed or updated on {latest:%-d %B %Y}, more than a year ago.", url
    return True, f"Its accessibility statement was last reviewed or updated on {latest:%-d %B %Y}.", url


def find_statement(home, pause=PAUSE):
    """(url, text) of the council's accessibility statement, or None if we can't find one. We try the
    homepage's link first; then, for a homepage built by JavaScript (with no links for us to follow) or
    a link that doesn't lead to a statement, the usual addresses and the site's sitemap."""
    status, final, _, page = home
    if status is None or status >= 400:
        return None
    site = f"https://{host(final)}"
    tried = set()
    for candidate in [lambda: statement_link(final, page),
                      lambda: f"{site}/accessibility",
                      lambda: f"{site}/accessibility-statement",
                      lambda: from_sitemap(site, pause)]:
        url = candidate()
        if not url or url in tried:
            continue
        tried.add(url)
        found = read_statement(url, pause)
        if found:
            return found
    return None


def read_statement(url, pause=PAUSE):
    """(url, text) if url is an accessibility statement, or a page that links to one; else None."""
    for _ in range(2):
        time.sleep(pause)
        status, final, _, page = get_page(url)
        if status != 200:
            return None
        text = plain(page)
        if STATEMENT_DATE.search(text):
            return final, text
        if IS_STATEMENT.search(text):
            # A statement over several pages, with its dates on a later one
            return final, text + " " + " ".join(rest_of_statement(final, page, pause))
        # A page about accessibility that links to the statement itself
        onward = [u for u, label in anchors(final, page)
                  if re.search(r"statement|technical information", label, re.I) and re.search(r"accessib|website", label, re.I)
                  and u.rstrip("/") != final.rstrip("/")]
        if not onward:
            return None
        url = onward[0]
    return None


def from_sitemap(site, pause=PAUSE):
    """The address in a site's sitemap that looks most like its accessibility statement, or None."""
    time.sleep(pause)
    robots = get_page(f"{site}/robots.txt")
    maps = re.findall(r"(?im)^sitemap:\s*(\S+)", robots[3]) if robots[0] == 200 else []
    found = []
    for sitemap in (maps or [f"{site}/sitemap.xml"])[:2]:
        time.sleep(pause)
        locations = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", get_page(sitemap)[3])
        for part in [loc for loc in locations if loc.endswith(".xml")][:8]:  # a sitemap of sitemaps
            time.sleep(pause)
            locations += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", get_page(part)[3])
        found += [loc for loc in locations if re.search(r"accessibility-statement|accessibility/?$", loc, re.I)]
    found.sort(key=lambda loc: ("statement" not in loc.lower(), len(loc)))
    return found[0] if found else None


def rest_of_statement(url, page, pause=PAUSE, most=6):
    """The text of the other pages of a statement split over several, found by their addresses
    starting with the statement's own (/accessibility/2, /accessibility/preparation)."""
    base = re.sub(r"/[^/]*/?$", "/", url) if re.search(r"/\d+/?$", url) else url.rstrip("/") + "/"
    pages = []
    for other, _ in anchors(url, page):
        other = other.split("?")[0]
        if other.startswith(base) and other.rstrip("/") != url.rstrip("/") and other not in pages:
            pages.append(other)
    texts = []
    for other in pages[:most]:
        time.sleep(pause)
        status, _, _, more = get_page(other)
        if status == 200:
            texts.append(plain(more))
            if STATEMENT_DATE.search(texts[-1]):
                break
    return texts


def fetch_all(homepages, pause=PAUSE, today=None):
    """{ons code: {check: (pass, reason, evidence)}} for each council's homepage."""
    today = today or datetime.date.today()
    found = {}
    for code, homepage in sorted(homepages.items()):
        home = get_page(f"https://{host(homepage)}/")
        time.sleep(pause)
        # The file goes on the site the homepage ends up at (lewisham.gov.uk, not www.)
        security = get_page(f"https://{host(home[1])}/.well-known/security.txt")
        time.sleep(pause)
        found[code] = {
            "dmarc": dmarc(dmarc_records(domain(homepage))),
            "https": hsts(*home[:3]),
            "security_txt": security_txt(*security, today),
            "a11y_statement": a11y_statement(find_statement(home, pause), today) if home[0] and home[0] < 400
            else (None, "We couldn't load the homepage" + (f" (it returned {home[0]})." if home[0] else "."), ""),
        }
    return found


def fetch(context):
    links = context["results"].get("local_links")
    if not links:
        raise ValueError("Our website checks need the homepages from Local Links Manager")
    homepages = {code: extra["homepage"] for code, extra in links.extra.items()
                 if code in context["population"] and (extra or {}).get("homepage")}
    today = datetime.date.today()
    result = Result(id=ID, title="Our checks of council websites", url=PAGE, period=today.strftime("%B %Y"),
                    published=today.isoformat())
    result.extra["checked"] = today.isoformat()
    for code, checks in fetch_all(homepages, today=today).items():
        result.extra[code] = {"homepage": homepages[code]}
        for check, (passed, reason, evidence) in checks.items():
            result.check(code, check, passed, reason, evidence)
        blocked = [check for check, (passed, _, _) in checks.items() if passed is None]
        if blocked:
            result.notes.append(f"{code}: couldn't check {', '.join(blocked)}")
    for code in sorted(set(context["population"]) - set(homepages)):
        result.notes.append(f"{code} has no homepage in Local Links Manager")
    return result
