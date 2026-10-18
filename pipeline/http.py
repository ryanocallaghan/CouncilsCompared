"""Downloads, with retries and an optional cache.

Set CC_CACHE to a folder to keep every response there and reuse it on the
next run: useful when working on a parser, so the sources are only asked
once.
"""

import gzip
import hashlib
import json
import os
import time
import urllib.error
import urllib.request

USER_AGENT = "councilscompared.com data updater (+https://github.com/ryanocallaghan/CouncilsCompared)"


def _cache_path(url):
    folder = os.environ.get("CC_CACHE")
    if not folder:
        return None
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, hashlib.sha1(url.encode()).hexdigest())


def _remember(url, path):
    index_path = os.path.join(os.path.dirname(path), "index.json")
    try:
        index = json.load(open(index_path))
    except (OSError, ValueError):
        index = {}
    index[os.path.basename(path)] = url
    with open(index_path, "w") as f:
        json.dump(index, f, indent=1, sort_keys=True)


def get(url, retries=3, pause=0):
    """The body of url as bytes, gunzipped if the server sent it compressed."""
    path = _cache_path(url)
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    error = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=300) as response:
                body = response.read()
            break
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                raise
            error = e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            error = e
        time.sleep(5 * (attempt + 1))
    else:
        raise error
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    if path:
        with open(path, "wb") as f:
            f.write(body)
        _remember(url, path)
    if pause:
        time.sleep(pause)
    return body


def get_text(url, **kwargs):
    return get(url, **kwargs).decode("utf-8-sig", errors="replace")


def get_json(url, **kwargs):
    return json.loads(get(url, **kwargs))
