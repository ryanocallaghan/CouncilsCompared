"""Fetch every source and rebuild the data the site is made from.

    python -m pipeline.update [--only ehcp,lgo] [--summary summary.md]

Each source's figures are saved in data/sources/<id>.json. If a source
fails (a site is down, or a spreadsheet changed shape), its previous file is
kept, and the failure is reported in the summary, so one broken source never
stops the others updating. Then data/councils.json is assembled from them.
"""

import argparse
import dataclasses
import datetime
import importlib
import json
import os
import sys
import traceback

from pipeline import sheets
from pipeline.names import Matcher
from pipeline.sources import Result

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
SOURCES = os.path.join(DATA, "sources")
COUNCILS = os.path.join(DATA, "councils.json")

# (id, module, function): run in this order, as some need earlier results
STEPS = [
    ("population", "population", "fetch"),
    ("neighbours", "neighbours", "fetch"),
    ("ehcp", "ehcp", "fetch"),
    ("lgo", "lgo", "fetch"),
    ("lgo_decisions", "lgo_decisions", "fetch"),
    ("tsm", "tsm", "fetch"),
    ("ctax", "ctax", "collection_rates"),
    ("band_d", "ctax", "band_d"),
    ("waste", "waste", "fetch"),
    ("fly", "fly", "fetch"),
    ("homelessness", "homelessness", "fetch"),
    ("spending", "spending", "fetch"),
    ("funding", "spending", "funding"),
    ("ofsted", "ofsted", "fetch"),
    ("silktide", "silktide", "fetch"),
    ("area_bands", "area_bands", "fetch"),
    ("lgbf", "lgbf", "fetch"),
    ("spso", "spso", "fetch"),
    ("scot_homelessness", "scot_homelessness", "fetch"),
    ("scot_spending", "scot_spending", "fetch"),
    ("scot_band_d", "scot_ctax", "fetch"),
]

# Measures each source provides, in data/councils.json "values"
VALUE_SOURCES = ["ehcp", "lgo", "lgo_decisions", "tsm", "ctax", "waste", "fly", "homelessness", "silktide", "lgbf",
                 "spso", "scot_homelessness"]
# Trends each source provides; a council only has figures in one source per trend
TRENDS = {"ehcp_20wk": ["ehcp"], "om_upheld": ["lgo"], "recycling": ["waste", "lgbf"], "fly_rate": ["fly"],
          "fly_fpn": ["fly"], "ta_days": ["scot_homelessness"]}
# Where Scotland's figures come from, for the parts of a council's page that aren't measures
SCOTLAND = {"homelessness": "scot_homelessness", "band_d": "scot_band_d", "spending": "scot_spending"}


def load(source_id):
    path = os.path.join(SOURCES, f"{source_id}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return Result(**json.load(f))


def save(result):
    os.makedirs(SOURCES, exist_ok=True)
    with open(os.path.join(SOURCES, f"{result.id}.json"), "w") as f:
        json.dump(dataclasses.asdict(result), f, indent=1, sort_keys=True, ensure_ascii=False, allow_nan=False)
        f.write("\n")


def context_from(population):
    councils = {code: extra["ons_name"] for code, extra in population.extra.items()}
    sheets.KNOWN.clear()
    sheets.KNOWN.update(councils)
    return {
        "councils": councils,
        "population": {code: v["population"] for code, v in population.values.items()},
        "matcher": Matcher(councils),
    }


def is_fresh(module, previous, context):
    """Whether a slow source was checked recently enough to skip."""
    max_age = getattr(module, "MAX_AGE_DAYS", None)
    if not max_age or not previous:
        return False
    checked = previous.extra.get("checked")
    if not checked:
        return False
    if module.ID == "lgo_decisions" and "lgo" in context["results"]:
        latest = context["results"]["lgo"].extra.get("latest")
        if previous.period != f"{latest - 1}-{str(latest)[2:]} and {latest}-{str(latest + 1)[2:]}":
            return False
    age = (datetime.date.today() - datetime.date.fromisoformat(checked)).days
    return age < max_age


def run(only=None):
    """Fetch the sources. Returns {id: "updated" | "fresh" | "kept" | "failed: ..."}."""
    status = {}
    context = {"results": {}}
    for source_id, module_name, function in STEPS:
        previous = load(source_id)
        module = importlib.import_module(f"pipeline.sources.{module_name}")
        if (only and source_id not in only) or is_fresh(module, previous, context):
            result, status[source_id] = previous, "skipped" if only and source_id not in only else "fresh"
        else:
            try:
                result = getattr(module, function)(context)
                save(result)
                status[source_id] = "fetched"
            except Exception as e:
                traceback.print_exc()
                status[source_id] = f"failed: {type(e).__name__}: {e}"
                result = previous
        if source_id == "population":
            if result is None:
                raise SystemExit("No population figures, so nothing can be compared")
            context.update(context_from(result))
        if result is not None:
            context["results"][source_id] = result
    return status


NATIONS = {"E": "England", "S": "Scotland", "W": "Wales"}  # by the first letter of the ONS code


def slugify(name):
    import re
    return re.sub(r"[^a-z0-9]+", "-", name.lower().replace("&", "and").replace("'", "")).strip("-")


def assemble():
    """data/councils.json from data/sources/*.json."""
    population = load("population")
    sources = {s: load(s) for s, _, _ in STEPS}
    councils = []
    for code, extra in sorted(population.extra.items(), key=lambda item: item[1]["name"]):
        def source(source_id):
            if code.startswith("S"):
                source_id = SCOTLAND.get(source_id, source_id)
            return sources.get(source_id)
        households = source("homelessness").extra.get("households", {}) if source("homelessness") else {}
        council = {
            "code": code,
            "name": extra["name"],
            "slug": slugify(extra["name"]),
            "type": extra["type"],
            "region": extra["region"],
            "nation": NATIONS[code[0]],
            "population": population.values[code]["population"],
            "households": households.get(code),
            "band_d": None,
            "band_d_parts": None,
            "funding": None,
            "values": {},
            "spend": {},
            "ofsted": None,
            "fly": None,
            "neighbours": [],
            "trends": {},
        }
        for source_id in VALUE_SOURCES:
            if sources[source_id]:
                council["values"].update(sources[source_id].values.get(code, {}))
        if source("band_d"):
            council["band_d"] = source("band_d").values.get(code, {}).get("band_d")
            council["band_d_parts"] = source("band_d").extra.get(code)
        if source("spending"):
            council["spend"] = source("spending").values.get(code, {})
        if sources["funding"]:
            council["funding"] = sources["funding"].extra.get(code)
        if sources["fly"]:
            council["fly"] = sources["fly"].extra.get("detail", {}).get(code)
        if sources["ofsted"]:
            council["ofsted"] = sources["ofsted"].extra.get(code)
        if sources["neighbours"]:
            council["neighbours"] = sources["neighbours"].extra.get(code, [])
        if sources["lgbf"] and code.startswith("S"):  # the LGBF family group
            council["neighbours"] = sources["lgbf"].extra["neighbours"].get(code, [])
        for trend, source_ids in TRENDS.items():
            for source_id in source_ids:
                series = sources[source_id].trends.get(code, {}).get(trend) if sources[source_id] else None
                if series:
                    council["trends"][trend] = dict(sorted(series.items()))
        councils.append(council)
    data = {
        "sources": {s: {"title": r.title, "url": r.url, "period": r.period, "published": r.published,
                        # Where measures from one source cover different years
                        **({"periods": r.extra["periods"]} if "periods" in r.extra else {})}
                    for s, r in sources.items() if r},
        "councils": councils,
    }
    with open(COUNCILS, "w") as f:
        json.dump(data, f, indent=1, ensure_ascii=False, allow_nan=False)
        f.write("\n")
    return data


def changes(before, after):
    """Markdown describing what changed between two versions of councils.json."""
    lines = []
    old_sources = (before or {}).get("sources", {})
    old = {c["code"]: c for c in (before or {}).get("councils", [])}
    for source_id, meta in after["sources"].items():
        was = old_sources.get(source_id, {})
        if was.get("period") != meta["period"]:
            lines.append(f"| {meta['title']} | {was.get('period', 'none')} → **{meta['period']}** | New edition |")
    changed = {}
    for council in after["councils"]:
        previous = old.get(council["code"], {})
        for measure, value in council["values"].items():
            if previous.get("values", {}).get(measure) != value:
                changed.setdefault(measure, []).append(
                    (council["name"], previous.get("values", {}).get(measure), value))
    if lines:
        lines.insert(0, "| Source | Period | |\n|---|---|---|")
    if changed:
        lines.append("\n### Figures that changed\n")
        lines.append("| Measure | Councils | Example |\n|---|---|---|")
        for measure, rows in sorted(changed.items()):
            name, was, now = max(rows, key=lambda r: abs((r[2] or 0) - (r[1] or 0)))
            lines.append(f"| `{measure}` | {len(rows)} | {name}: {was} → {now} |")
    return "\n".join(lines) or "No figures changed."


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="comma-separated source ids to fetch; the rest keep their files")
    parser.add_argument("--summary", help="write a markdown summary of the changes here")
    args = parser.parse_args(argv)
    before = None
    if os.path.exists(COUNCILS):
        with open(COUNCILS) as f:
            before = json.load(f)
    status = run(set(args.only.split(",")) if args.only else None)
    after = assemble()
    failures = {s: v for s, v in status.items() if v.startswith("failed")}
    summary = ["## Data update", "", changes(before, after), ""]
    if failures:
        summary += ["### Sources that could not be updated", "",
                    "These kept their previous figures. A spreadsheet may have changed shape: check the workflow log.",
                    ""]
        summary += [f"- `{s}`: {v[len('failed: '):]}" for s, v in failures.items()]
    summary.append("")
    text = "\n".join(summary)
    print(text)
    print({s: v.split(":")[0] for s, v in status.items()})
    if args.summary:
        with open(args.summary, "w") as f:
            f.write(text)
    return 1 if len(failures) == len(status) else 0


if __name__ == "__main__":
    sys.exit(main())
