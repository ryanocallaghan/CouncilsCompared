import json, re, urllib.request, zipfile, io
UA = {"User-Agent": "councilscompared.com data updater"}
def get(u): return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=300).read()
out = []
d = json.loads(get("https://www.gov.uk/api/content/government/statistics/council-tax-stock-of-properties-2026"))
out.append(json.dumps(d.get("links", {}).get("document_collections", []))[:400])
for a in d["details"].get("attachments", []):
    out.append(f"  A {a.get('title')} | {a.get('url')}")
for a in d["details"].get("attachments", []):
    if a.get("title", "").startswith("CTSOP1.1"):
        z = zipfile.ZipFile(io.BytesIO(get(a["url"]))); out.append(str([(i.filename, i.file_size) for i in z.infolist()]))
        for n in z.namelist():
            text = z.read(n).decode("utf-8", "replace").splitlines()
            out += [n] + text[:6] + [l for l in text if "E01003" in l][:3] + [l for l in text if "E09000023" in l][:3]
open("probe5.txt", "w").write("\n".join(out))
