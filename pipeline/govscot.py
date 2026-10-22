"""Finding the latest edition of a Scottish Government publication.

gov.scot has no content API like GOV.UK's, but each statistics release is a
page at /publications/<name>-<year>/ with its files listed on a /documents/
page, so the latest edition is the one with the newest year in its address.
"""

import re
from urllib.parse import unquote

from pipeline.http import get_text

WEB = "https://www.gov.scot"
YEAR = re.compile(r"(\d{4})-(\d\d)")


def latest(listing, pattern):
    """(the publication's URL, its year such as "2025-26") for the newest
    publication linked from listing whose path matches pattern."""
    found = {}
    for path in re.findall(r'href="(/publications/[^"#?]+)"', get_text(WEB + listing)):
        match = re.search(pattern, path)
        if match:
            found[match.group(1)] = WEB + path
    if not found:
        raise RuntimeError(f"No publication matching {pattern!r} on {listing}")
    year = max(found)
    return found[year], year


def files(page_url):
    """{file name: url} for every file a page links to."""
    html = get_text(page_url)
    links = re.findall(r'href="(/binaries/[^"]+\.(?:xlsx|xls|ods|csv))"', html)
    return {unquote(unquote(link.rsplit("/", 1)[-1])).replace("+", " "): WEB + link for link in links}


def find(found, pattern):
    """The url of the first file whose name matches pattern."""
    for name, url in found.items():
        if re.search(pattern, name, re.I):
            return url
    raise RuntimeError(f"No file matching {pattern!r} in {sorted(found)}")


def published(page_url):
    """The date a page was last changed, YYYY-MM-DD."""
    match = re.search(r'name="dc\.date\.modified" content="(\d{4}-\d\d-\d\d)', get_text(page_url))
    return match.group(1) if match else ""
