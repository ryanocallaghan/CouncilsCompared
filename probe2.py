"""Throwaway: download the files each source would use."""
import json, os, re, time, urllib.request

OUT = "raw"
UA = "councilscompared.com data updater (+https://github.com/ryanocallaghan/CouncilsCompared)"
os.makedirs(OUT, exist_ok=True)
log = []

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()

def save(name, url):
    try:
        body = get(url)
        open(os.path.join(OUT, name), "wb").write(body)
        log.append(f"OK {name} {len(body)} {url}")
    except Exception as e:
        log.append(f"FAIL {name} {url} {e!r}")
    time.sleep(1)

def content(path):
    return json.loads(get("https://www.gov.uk/api/content" + path))

def attachments(path, pattern, prefix):
    try:
        d = content(path)
        open(os.path.join(OUT, prefix + "_content.json"), "w").write(json.dumps(d, indent=1))
        for a in d.get("details", {}).get("attachments", []):
            if re.search(pattern, a.get("title", "") + " " + a.get("url", ""), re.I):
                save(prefix + "_" + a["url"].split("/")[-1], a["url"])
    except Exception as e:
        log.append(f"FAIL content {path} {e!r}")

attachments("/government/statistics/collection-rates-for-council-tax-and-non-domestic-rates-in-england-2025-to-2026", r"Table 6", "ctax")
attachments("/government/statistics/council-tax-levels-set-by-local-authorities-in-england-2026-to-2027", r"\.(ods|xlsx)$", "bandd")
attachments("/government/statistical-data-sets/live-tables-on-homelessness", r"Detailed local authority level tables: January to March 2026", "homeless")
attachments("/government/statistical-data-sets/env18-local-authority-collected-waste-annual-results-tables", r"2023/24", "env18")
attachments("/government/statistics/fly-tipping-in-england", r"\.(ods|xlsx|csv)$", "fly")
attachments("/government/statistics/local-authority-revenue-expenditure-and-financing-england-2024-to-2025-individual-local-authority-data-outturn", r"RSX", "rsx")
attachments("/government/statistics/local-authority-revenue-expenditure-and-financing-england-2025-to-2026-individual-local-authority-data-outturn", r"RSX", "rsx2526")
attachments("/government/statistics/local-authority-inspection-outcomes-as-at-31-march-2026", r"Underlying", "ofsted")
attachments("/government/statistics/tenant-satisfaction-measures-202425", r"full data", "tsm")
attachments("/government/publications/local-authority-interactive-tool-lait", r"statistical neighbour", "lait")
for p, n in [("/government/collections/childrens-social-care-statistics", "col_ofsted"),
             ("/government/collections/tenant-satisfaction-measures", "col_tsm"),
             ("/government/collections/homelessness-statistics", "col_homeless")]:
    try:
        open(os.path.join(OUT, n + ".json"), "w").write(json.dumps(content(p), indent=1))
    except Exception as e:
        log.append(f"FAIL {p} {e!r}")

save("mye25tablesew.xlsx", "https://www.ons.gov.uk/file?uri=/peoplepopulationandcommunity/populationandmigration/populationestimates/datasets/estimatesofthepopulationforenglandandwales/mid20252023localauthorityboundaries/mye25tablesew.xlsx")
save("lad_rgn.json", "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/LAD25_RGN25_EN_LU_v2/FeatureServer/0/query?where=1%3D1&outFields=*&f=json&resultRecordCount=2000")
lgo = get("https://www.lgo.org.uk/information-centre/reports/annual-review-reports/local-government-complaint-reviews").decode()
for url in sorted(set(re.findall(r'href="(https://www\.lgo\.org\.uk/assets/attach/\d+/[^"]+\.xlsx)"', lgo))):
    save("lgo_" + url.split("/")[-1], url)
for name, url in [
    ("ees_rel1.json", "https://content.explore-education-statistics.service.gov.uk/api/publications/education-health-and-care-plans/releases/latest/summary"),
    ("ees_rel2.json", "https://content.explore-education-statistics.service.gov.uk/api/publications/education-health-and-care-plans/release"),
    ("ees_pub.json", "https://content.explore-education-statistics.service.gov.uk/api/publications/education-health-and-care-plans"),
    ("ees_api_datasets.json", "https://api.education.gov.uk/statistics/v1/publications/88312cc0-fe1d-4ab5-81df-33fd708185cb/data-sets"),
    ("ees_files.zip", "https://content.explore-education-statistics.service.gov.uk/api/releases/9b5381be-1851-4493-8ae4-54e7223837aa/files?fromPage=DataCatalogue&fileIds=0a1187d7-826f-4d4d-f296-08ded384b3ca"),
    ("silktide_lewisham.html", "https://index.silktide.com/website/london-borough-of-lewisham-council"),
]:
    save(name, url)
open(os.path.join(OUT, "_log.txt"), "w").write("\n".join(log) + "\n")
print("\n".join(log))
