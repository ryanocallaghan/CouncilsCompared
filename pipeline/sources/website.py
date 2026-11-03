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

The homepage comes from GOV.UK's Local Links Manager. When a site blocks us
or can't be reached, the answer is "couldn't check" (None), never a fail.
We never get past a bot challenge, log in or submit a form.
"""

import datetime
import re
import time
import urllib.error
import urllib.request

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
                    response.read(200000).decode("utf-8", errors="replace"))
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
