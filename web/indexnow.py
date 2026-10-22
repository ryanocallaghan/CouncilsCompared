"""Tell search engines which pages have changed, through IndexNow.

    python -m web.indexnow dist/sitemap.xml

Bing (whose index ChatGPT search and Copilot use), Yandex and others share
IndexNow submissions, so new figures are picked up in days rather than
weeks. It sends every page in the sitemap: run after the site is published
with new figures or new pages (see .github/workflows/indexnow.yml).

The key proves the site is ours: build.py publishes it at /<key>.txt.
"""

import json
import sys
import urllib.request
import xml.etree.ElementTree as ET

from web.build import INDEXNOW_KEY, SITE_URL

ENDPOINT = "https://api.indexnow.org/indexnow"
LIMIT = 10_000  # URLs per submission


def urls(sitemap):
    namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [loc.text for loc in ET.parse(sitemap).getroot().findall("s:url/s:loc", namespace)]


def submit(url_list):
    body = json.dumps({
        "host": SITE_URL.removeprefix("https://"),
        "key": INDEXNOW_KEY,
        "keyLocation": f"{SITE_URL}/{INDEXNOW_KEY}.txt",
        "urlList": url_list[:LIMIT],
    }).encode()
    request = urllib.request.Request(ENDPOINT, data=body, method="POST",
                                     headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.status


if __name__ == "__main__":
    pages = urls(sys.argv[1] if len(sys.argv) > 1 else "dist/sitemap.xml")
    status = submit(pages)
    print(f"Sent {len(pages)} pages to IndexNow: {status}")
