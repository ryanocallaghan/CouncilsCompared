"""Our own checks of each council's cookies, in a real browser.

We open the council's homepage in Chromium, as a new visitor, click nothing
and wait a few seconds. Then:

- trackers: does the page set cookies from well-known analytics or
  advertising services (Google Analytics, Meta, Hotjar and so on) before
  the visitor has chosen anything?
- reject_cookies: if there's a button to accept cookies, is there one to
  reject them alongside it, rather than only in a settings page? A site
  that sets no analytics or advertising cookies has nothing to ask, so it
  passes without a banner.

These say what the council's website does, not whether it breaks the law.
The homepage comes from GOV.UK's Local Links Manager. When a site blocks
us, shows a bot challenge or can't be reached, the answer is "couldn't
check" (None), never a fail. We never get past a challenge or click
anything. Playwright is imported only when this runs, so nothing else
needs a browser.
"""

import datetime
import re
import time

from pipeline.sources import Result

ID = "cookies"
PAGE = "https://councilscompared.com/about/#our-checks"
MAX_AGE_DAYS = 28  # monthly
PAUSE = 1
WAIT_MS = 5000  # for banners and scripts that load after the page
# A browser's user agent, so pages render as they would for a resident, with who we are added on
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 "
              "Safari/537.36 councilscompared.com-checker (+https://github.com/ryanocallaghan/CouncilsCompared)")

# Cookie names, by the service that sets them
SERVICES = [
    (r"_ga($|_)|_gid$|_gat|__utm[abcz]", "Google Analytics"),
    (r"_gcl_|IDE$|test_cookie$|NID$|DSID$", "Google advertising"),
    (r"_fbp$|fr$", "Meta (Facebook)"),
    (r"_hj", "Hotjar"),
    (r"_clck$|_clsk$|MUID$|CLID$", "Microsoft Clarity"),
    (r"_uet(sid|vid)$", "Microsoft advertising"),
    (r"nmstat$|siteimproveses$", "Siteimprove Analytics"),
    (r"YSC$|VISITOR_INFO1_LIVE$|VISITOR_PRIVACY_METADATA$", "YouTube"),
    (r"li_|bcookie$|lidc$|UserMatchHistory$", "LinkedIn"),
    (r"_ttp$", "TikTok"),
    (r"_pk_(id|ses)", "Matomo"),
    (r"AMCV_|s_vi$|s_cc$", "Adobe Analytics"),
    (r"_scid", "Snapchat"),
    (r"_pin_unauth$", "Pinterest"),
]
# Cookies from these sites, whatever they're called
DOMAINS = [
    ("doubleclick.net", "Google advertising"), ("youtube.com", "YouTube"), ("facebook.com", "Meta (Facebook)"),
    ("linkedin.com", "LinkedIn"), ("hotjar.com", "Hotjar"), ("clarity.ms", "Microsoft Clarity"),
    ("bing.com", "Microsoft advertising"), ("twitter.com", "X (Twitter)"), ("x.com", "X (Twitter)"),
    ("tiktok.com", "TikTok"), ("adnxs.com", "Xandr advertising"), ("criteo.com", "Criteo advertising"),
]

# A button about cookies that accepts them, or a banner's usual short labels ("Accept all", "OK")
ACCEPT = re.compile(r"\b(accept|agree|allow|ok to use|i'?m happy|i'?m ok)\b.*cookie|cookie.*\b(accept|agree|allow)", re.I)
ACCEPT_SHORT = re.compile(r"(i )?(accept|agree)( all| and close| and continue)?|allow( all)?|ok|okay|got it|"
                          r"i'?m happy|that'?s fine", re.I)
REJECT = re.compile(r"\b(reject|decline|refuse|deny|disagree|don'?t (accept|use|allow)|do not (accept|use|allow)|no,? thanks|"
                    r"(necessary|essential|required) (cookies )?only|only (use )?(necessary|essential|required)|"
                    r"use (necessary|essential))", re.I)
CHALLENGE = re.compile(r"just a moment|attention required|access denied|are you a robot|verify you are human|"
                       r"request rejected|security check", re.I)


# Security cookies some of those sites set, which don't track anyone (Cloudflare's bot protection)
NOT_TRACKING = re.compile(r"__cf_bm$|cf_clearance$|__cfruid$|_cfuvid$")


def service(name, domain):
    """The analytics or advertising service a cookie is from, or None."""
    if NOT_TRACKING.match(name):
        return None
    for pattern, who in SERVICES:
        if re.match(pattern, name, re.I):
            return who
    domain = domain.lstrip(".").lower()
    for site, who in DOMAINS:
        if domain == site or domain.endswith("." + site):
            return who
    return None


def tracking(cookies):
    """[(service, "name on domain")] for the analytics and advertising cookies among cookies."""
    found = set()
    for c in cookies:
        who = service(c["name"], c["domain"])
        if who:
            found.add((who, f"{c['name']} on {c['domain'].lstrip('.')}"))
    return sorted(found)


def buttons(texts):
    """The accept and reject buttons among the texts of a page's buttons (and links about cookies)."""
    texts = [re.sub(r"\s+", " ", t).strip() for t in texts]
    reject = [t for t in texts if REJECT.search(t)]
    accept = [t for t in texts if (ACCEPT.search(t) or ACCEPT_SHORT.fullmatch(t.rstrip(".!"))) and t not in reject]
    return accept, reject


def couldnt(status, title):
    """Why we couldn't check a page, or None if we could."""
    if status is None:
        return "We couldn't load the homepage."
    if status >= 400:
        return f"We couldn't load the homepage (it returned {status})."
    if CHALLENGE.search(title or ""):
        return "The homepage showed a check for automated visitors, which we don't try to get past."
    return None


def judge(status, title, cookies, texts):
    """{check: (pass, reason, evidence)} for what a visit found."""
    blocked = couldnt(status, title)
    if blocked:
        return {"trackers": (None, blocked, ""), "reject_cookies": (None, blocked, "")}
    found = tracking(cookies)
    services = sorted({who for who, _ in found})
    if found:
        trackers = (False, f"Before we chose anything, the homepage set cookies from {join(services)}.",
                    ", ".join(cookie for _, cookie in found))
    else:
        trackers = (True, "", "")
    accept, reject = buttons(texts)
    if accept and reject:
        choice = (True, "", f"Buttons: {join(accept[:1] + reject[:1], quote=True)}")
    elif accept:
        choice = (False, f"Its cookie banner has a button to accept cookies (“{accept[0]}”) but not one to reject "
                         "them alongside it.", f"Buttons: {join(accept[:2], quote=True)}")
    elif found:
        choice = (False, "It sets analytics or advertising cookies without showing a banner that offers to refuse them.", "")
    else:
        choice = (True, "", "No analytics or advertising cookies, so nothing to ask")
    return {"trackers": trackers, "reject_cookies": choice}


def join(items, quote=False):
    items = [f"“{i}”" if quote else i for i in items]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


# The texts of visible buttons, and of visible links that mention cookies, in the page and any
# open shadow roots
BUTTON_TEXTS = """() => {
  const found = [];
  const walk = (root) => {
    for (const el of root.querySelectorAll('button, [role=button], input[type=button], input[type=submit], a')) {
      const box = el.getBoundingClientRect();
      if (!box.width || !box.height || getComputedStyle(el).visibility === 'hidden') continue;
      const text = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();
      if (!text || text.length > 80) continue;
      if (el.tagName === 'A' && el.getAttribute('role') !== 'button' && !/cookie/i.test(text)) continue;
      found.push(text);
    }
    for (const el of root.querySelectorAll('*')) if (el.shadowRoot) walk(el.shadowRoot);
  };
  walk(document);
  return found;
}"""


def visit(browser, url):
    """(status, title, cookies, button texts) for a first visit to url, clicking nothing."""
    context = browser.new_context(user_agent=USER_AGENT, locale="en-GB", viewport={"width": 1280, "height": 900})
    try:
        page = context.new_page()
        try:
            response = page.goto(url, wait_until="load", timeout=45000)
        except Exception:  # noqa: BLE001 (a timeout or a connection error: couldn't check)
            return None, "", [], []
        page.wait_for_timeout(WAIT_MS)
        texts = []
        for frame in page.frames:  # some banners are in a frame of their own
            try:
                texts += frame.evaluate(BUTTON_TEXTS)
            except Exception:  # noqa: BLE001 (a frame that went away)
                pass
        return response.status if response else None, page.title(), context.cookies(), texts
    finally:
        context.close()


def fetch(context):
    from playwright.sync_api import sync_playwright

    links = context["results"].get("local_links")
    if not links:
        raise ValueError("Our cookie checks need the homepages from Local Links Manager")
    homepages = {code: extra["homepage"] for code, extra in links.extra.items()
                 if code in context["population"] and isinstance(extra, dict) and extra.get("homepage")}
    today = datetime.date.today()
    result = Result(id=ID, title="Our checks of council websites' cookies", url=PAGE, period=today.strftime("%B %Y"),
                    published=today.isoformat())
    result.extra["checked"] = today.isoformat()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for code, homepage in sorted(homepages.items()):
                for check, (passed, reason, evidence) in judge(*visit(browser, homepage)).items():
                    result.check(code, check, passed, reason, evidence)
                if result.checks[code]["trackers"]["pass"] is None:
                    result.notes.append(f"{code}: couldn't check cookies ({result.checks[code]['trackers']['reason']})")
                time.sleep(PAUSE)
        finally:
            browser.close()
    return result
