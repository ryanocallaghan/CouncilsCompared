import json, os, time, urllib.request
OUT = "raw3"; os.makedirs(OUT, exist_ok=True)
UA = "councilscompared.com data updater (+https://github.com/ryanocallaghan/CouncilsCompared)"
plan = {
 "ees_api.csv": "https://api.education.gov.uk/statistics/v1/data-sets/01a0aa36-b680-76f8-8e62-55b216223feb/csv",
 "ees_api_meta.json": "https://api.education.gov.uk/statistics/v1/data-sets/01a0aa36-b680-76f8-8e62-55b216223feb",
 "search_fly1.json": "https://www.gov.uk/api/search.json?q=fly-tipping+statistics+for+england&count=15&fields=title,link,public_timestamp,format",
 "search_fly2.json": "https://www.gov.uk/api/search.json?filter_organisations=department-for-environment-food-rural-affairs&q=fly-tipping&count=15&fields=title,link,public_timestamp,format",
 "search_ofsted.json": "https://www.gov.uk/api/search.json?q=local+authority+inspection+outcomes&count=10&fields=title,link,public_timestamp",
 "fly_guess1.json": "https://www.gov.uk/api/content/government/statistics/fly-tipping-statistics-for-england-2024-to-2025",
 "fly_guess2.json": "https://www.gov.uk/api/content/government/collections/fly-tipping",
 "fly_deleted.json": "https://www.gov.uk/api/content/government/statistics/deleted-fly-tipping-statistics-for-england",
 "lgo_fullname.html": "https://www.lgo.org.uk/Decisions/SearchResults?fd=2024-04-01&td=2026-03-31&dc=u%2B&aname=London+Borough+of+Lewisham&page=1",
 "lgo_page8.html": "https://www.lgo.org.uk/Decisions/SearchResults?fd=2024-04-01&td=2026-03-31&dc=u%2B&aname=London+Borough+of+Lewisham&page=8",
}
log = []
for n, u in plan.items():
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": UA}), timeout=300) as r:
            b = r.read(); log.append(f"OK {n} {len(b)} {r.headers.get('Content-Type')} {r.headers.get('Content-Encoding')}")
        open(os.path.join(OUT, n), "wb").write(b)
    except Exception as e:
        log.append(f"FAIL {n} {e!r}")
    time.sleep(1)
open(os.path.join(OUT, "_log.txt"), "w").write("\n".join(log) + "\n")
