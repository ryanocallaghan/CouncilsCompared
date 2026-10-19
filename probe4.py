import io, json, re, urllib.request
from python_calamine import CalamineWorkbook
UA = {"User-Agent": "councilscompared.com data updater"}
item = json.load(urllib.request.urlopen(urllib.request.Request("https://www.gov.uk/api/content/government/statistics/local-authority-revenue-expenditure-and-financing-england-2025-to-2026-individual-local-authority-data-outturn", headers=UA)))
out = []
for a in item["details"]["attachments"]:
    if re.search(r"\(RS\)", a.get("title", "")):
        data = urllib.request.urlopen(urllib.request.Request(a["url"], headers=UA)).read()
        book = CalamineWorkbook.from_filelike(io.BytesIO(data))
        out.append(a["url"]); out.append(str(book.sheet_names))
        for name in book.sheet_names:
            rows = book.get_sheet_by_name(name).to_python()
            for i, r in enumerate(rows):
                if any(str(c).strip() == "ONS Code" for c in r):
                    out += [f"{name} header row {i}"] + [f"{j}: {re.sub(chr(10), ' ', str(c))}" for j, c in enumerate(r)]
                if any(str(c).strip() in ("E09000023", "E08000010") for c in r):
                    out.append("ROW " + json.dumps([str(c) for c in r]))
open("probe4.txt", "w").write("\n".join(out))
