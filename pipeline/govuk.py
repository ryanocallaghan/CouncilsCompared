"""Finding the latest edition of a publication with the GOV.UK Content API.

Every page on GOV.UK is also available as JSON at /api/content/<path>,
including its attachments. Collections list their documents, newest first,
so the latest edition of a series and its spreadsheet can be found without
knowing its URL in advance.
"""

import re

from pipeline.http import get_json

API = "https://www.gov.uk/api/content"
WEB = "https://www.gov.uk"


def content(path):
    """A page's content item, following redirects (pages are often moved)."""
    for _ in range(6):
        item = get_json(API + path)
        if item.get("schema_name") != "redirect":
            item["web_url"] = WEB + item.get("base_path", path)
            return item
        redirect = next((r for r in item.get("redirects", []) if r["path"] == path), item["redirects"][0])
        path = redirect["destination"].split("#")[0]
    raise RuntimeError(f"Too many redirects from {path}")


def attachments(item):
    return item.get("details", {}).get("attachments", []) or []


def find_attachment(item, pattern, extensions=(".ods", ".xlsx", ".xls", ".csv", ".zip")):
    """The first attachment whose title matches pattern and is a data file."""
    for attachment in attachments(item):
        url = attachment.get("url", "")
        if re.search(pattern, attachment.get("title", ""), re.I) and url.lower().endswith(extensions):
            return attachment
    return None


def collection_documents(path):
    """[(title, base_path, document_type)] in the order the collection lists them."""
    item = content(path)
    by_id = {d["content_id"]: d for d in item.get("links", {}).get("documents", [])}
    documents = []
    for group in item.get("details", {}).get("collection_groups", []):
        for content_id in group.get("documents", []):
            document = by_id.get(content_id)
            if document:
                documents.append((document.get("title", ""), document.get("base_path", ""),
                                  document.get("document_type", "")))
    return documents


def years_in(title):
    """The latest year a title mentions: "2024 to 2025" -> 2025, "31 March 2026" -> 2026."""
    years = [int(y) for y in re.findall(r"(?<!\d)(20\d\d)(?!\d)", title)]
    years += [2000 + int(y) for y in re.findall(r"(?<!\d)20\d\d[-/](\d\d)(?!\d)", title)]
    return max(years) if years else 0


def latest(collection_path, title_pattern, attachment_pattern):
    """(page, attachment) for the newest published edition in a collection.

    Editions are tried newest year first; announcements of editions not yet
    published have no attachments, so they are skipped.
    """
    candidates = [(title, path) for title, path, kind in collection_documents(collection_path)
                  if re.search(title_pattern, title, re.I) and "announcement" not in kind]
    candidates.sort(key=lambda c: years_in(c[0]), reverse=True)
    for title, path in candidates:
        item = content(path)
        attachment = find_attachment(item, attachment_pattern)
        if attachment:
            return item, attachment
    raise RuntimeError(f"No edition of {title_pattern!r} in {collection_path} has a matching attachment")


def published(item):
    """The date a page was last published or updated, as YYYY-MM-DD.

    Series pages (fly-tipping, statistical neighbours) are updated in place,
    so their first publication date is years old.
    """
    return (item.get("public_updated_at") or item.get("first_published_at") or "")[:10]
