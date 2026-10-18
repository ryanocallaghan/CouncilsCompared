"""Throwaway: save what each source looks like, so parsers can be written against it."""
import json, os, sys, time, traceback, urllib.parse, urllib.request

OUT = "probe_out"
UA = "councilscompared.com data updater (+https://github.com/ryanocallaghan/CouncilsCompared)"
os.makedirs(OUT, exist_ok=True)
plan = json.load(open("probe_plan.json"))
log = []
for name, url in plan.items():
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=120) as r:
            body = r.read()
            final = r.geturl()
        path = os.path.join(OUT, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "wb").write(body)
        log.append(f"OK {name} {len(body)} {final}")
    except Exception as e:
        log.append(f"FAIL {name} {url} {e!r}")
    time.sleep(1)
open(os.path.join(OUT, "_log.txt"), "w").write("\n".join(log) + "\n")
print("\n".join(log))
