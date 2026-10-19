import json, re, urllib.request
UA = {"User-Agent": "councilscompared.com data updater"}
def get(u): return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=120).read()
out = []
s = json.loads(get("https://www.gov.uk/api/search.json?q=council+tax+stock+of+properties&count=10&fields=title,link,public_timestamp"))
for r in s["results"]: out.append(f"S {r.get('public_timestamp','')[:10]} {r['title']} {r['link']}")
for r in s["results"]:
    if "stock-of-properties" in r["link"] and r["link"].startswith("/government/statistics/"):
        d = json.loads(get("https://www.gov.uk/api/content" + r["link"]))
        out.append(f"== {d['title']} {r['link']}")
        for a in d["details"].get("attachments", []):
            out.append(f"  A {a.get('title')} | {a.get('url')}")
        for a in d["details"].get("attachments", []):
            if re.search(r"LSOA|lower layer|small area", a.get("title", "") + a.get("url", ""), re.I) and a["url"].endswith((".csv", ".zip", ".ods", ".xlsx")):
                body = get(a["url"]); out.append(f"  GOT {a['url']} {len(body)}")
                if a["url"].endswith(".csv"): out.append(body[:1500].decode("utf-8", "replace"))
                if a["url"].endswith(".zip"):
                    import zipfile, io
                    z = zipfile.ZipFile(io.BytesIO(body)); out.append(str(z.namelist()))
                    n = z.namelist()[0]; out.append(z.read(n)[:1500].decode("utf-8", "replace"))
                break
        break
open("probe5.txt", "w").write("\n".join(out))
