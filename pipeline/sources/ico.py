"""Enforcement action against councils by the Information Commissioner's Office.

The ICO, which enforces data protection law across the UK, publishes the
action it takes: reprimands, enforcement notices, fines and prosecutions.
The check is whether there has been any against the council in the last
three years.

The ICO's enforcement page gets its list from a search API, which we ask
for each sector councils are filed under. (It wants its JSON without
spaces, and returns at most 100 results for a search, which each sector is
well within.)
"""

import datetime
import json
import re
import time
import urllib.request

from pipeline.http import USER_AGENT
from pipeline.sources import Result

ID = "ico"
PAGE = "https://ico.org.uk/action-weve-taken/enforcement/"
API = "https://ico.org.uk/api/search"
ROOT_PAGE = 17222  # the enforcement page, which the API needs to know
SECTORS = ["local-government", "social-care", "education-and-childcare"]  # where councils' actions are filed
YEARS = 3
PAUSE = 0.5


def search(sector, page=1):
    """One page of the ICO's enforcement actions in a sector, newest first."""
    body = json.dumps({"filters": [{"key": "ensector", "values": [sector]}], "pageNumber": page, "order": "newest",
                       "rootPageId": ROOT_PAGE}, separators=(",", ":")).encode()
    request = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def actions(pause=PAUSE):
    """Every action in the sectors councils are filed under, once each."""
    found = {}
    for sector in SECTORS:
        page = 1
        while True:
            answer = search(sector, page)
            for item in answer["results"]:
                found.setdefault(item["url"], item)
            if not answer["pagination"]["hasMore"]:
                break
            page += 1
            time.sleep(pause)
        time.sleep(pause)
    return list(found.values())


def parse(item):
    """(date, kind, title, url) for one action: "16 May 2025, Reprimands, Local government"."""
    when, kind = (part.strip() for part in item["filterItemMetaData"].split(",")[:2])
    date = datetime.datetime.strptime(when, "%d %B %Y").date()
    kind = {"Reprimands": "a reprimand", "Enforcement notices": "an enforcement notice",
            "Monetary penalties": "a fine", "Prosecutions": "a prosecution"}.get(kind, kind.lower())
    return date, kind, item["title"], "https://ico.org.uk" + item["url"]


def fetch(context):
    today = datetime.date.today()
    since = today.replace(year=today.year - YEARS)
    against = {}
    items = actions()
    if not items:
        raise ValueError("The ICO's enforcement search returned nothing")
    for item in items:
        date, kind, title, url = parse(item)
        code = context["matcher"].code(title)
        if code in context["population"] and date >= since:
            against.setdefault(code, []).append((date, kind, url))
    result = Result(id=ID, title="ICO: enforcement action", url=PAGE, period=f"{since:%B %Y} to {today:%B %Y}",
                    published=today.isoformat())
    for code in sorted(context["population"]):
        if code[0] not in "ES":  # on the site so far
            continue
        found = sorted(against.get(code, []), reverse=True)
        if not found:
            result.check(code, "ico_action", True, "")
            continue
        listed = "; ".join(f"{kind} on {date:%-d %B %Y}" for date, kind, _ in found)
        result.check(code, "ico_action", False, f"The ICO took action against the council: {listed}.",
                     " ".join(url for _, _, url in found))
    return result
