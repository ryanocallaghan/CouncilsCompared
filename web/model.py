"""How each council compares with a group of others, for the council pages.

The figures are in data/councils.json, built by pipeline.update: one entry
per council with its value for each measure, its spending per resident, its
Ofsted grade, its similar councils and a few figures over time.

This module ranks a council against a comparison group and lays out what a
page draws, so the templates stay simple and the logic can be tested.
"""

import json
import math
import os
from dataclasses import dataclass, field
from datetime import date
from functools import cache
from statistics import median

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(ROOT, "data", "councils.json")

# The groups a council can be compared with, in the order of the tabs.
# "nation" (every council in England, Scotland or Wales) is the council's
# own page; the others are under it. Councils are only ever compared with
# others in the same nation: services and statistics differ between them.
GROUPS = ["nation", "region", "type", "similar"]
NATIONS = {"E": "England", "S": "Scotland", "W": "Wales"}  # by the first letter of the ONS code
# The nations on the site. A nation's figures can be in the data before its
# pages are ready: set CC_NATIONS=England,Scotland to build them anyway (as
# Cloudflare does for previews).
PUBLISHED = [n.strip() for n in os.environ.get("CC_NATIONS", "England").split(",") if n.strip()]
TYPE_PLURAL = {
    "London borough": "London boroughs",
    "Metropolitan district": "metropolitan districts",
    "Unitary authority": "unitary authorities",
    "Council area": "councils",
}
MIN_SIMILAR = 3  # fewer similar councils than this, and the group is not offered

AREAS = [
    ("send", "Special educational needs",
     "Education, health and care plans set out support for children with special educational needs. "
     "The law says a new plan should be issued within 20 weeks."),
    ("schools", "Schools",
     "Primary pupils reaching the expected level for their stage (P1, P4 and P7), school attendance, and "
     "school leavers going on to work, study or training."),
    ("care", "Adult social care",
     "Adults who get care at home, inspections of care services, and how long older people stay in hospital "
     "once they are ready to leave."),
    ("complaints", "Ombudsman complaints",
     "The Local Government and Social Care Ombudsman looks at complaints the council's own complaints "
     "process has not resolved. Upheld means the Ombudsman found the council at fault."),
    ("housing", "Council housing",
     "From the tenant survey and performance figures every council landlord reports to the "
     "Regulator of Social Housing. Only councils that still own council homes are included."),
    ("ctax", "Council tax",
     "How much of the year's council tax and business rates bills the council collected by 31 March."),
    ("streets", "Streets and waste",
     "Fly-tipping the council recorded, how often it took enforcement action or issued a fixed penalty "
     "notice (an on-the-spot fine), how much household waste was recycled, and how much was left over "
     "for the bin."),
    ("homeless", "Homelessness",
     "Temporary accommodation and the outcomes of homelessness cases, from the council's statutory returns."),
    ("digital", "Website",
     "An automated test of the council website's accessibility."),
]

# Where a nation's figures need a different explanation from England's
AREA_NOTES = {
    ("Scotland", "housing"):
        "From the figures every council landlord reports to the Scottish Housing Regulator. Only councils "
        "that still own council homes are included.",
    ("Scotland", "ctax"):
        "How much of the council tax due for the year the council received by the end of the year.",
    ("Scotland", "complaints"):
        "The Scottish Public Services Ombudsman looks at complaints the council's own complaints process has "
        "not resolved. Few go on to a full investigation in Scotland, so the number of complaints that reached "
        "the Ombudsman is compared.",
    ("Scotland", "homeless"):
        "Temporary accommodation and what happened to homeless households, from the council's returns to the "
        "Scottish Government.",
    ("Scotland", "streets"):
        "Inspections of how clean streets are, how much household waste was recycled, and how satisfied "
        "people are with bin collections and street cleaning. Satisfaction comes from the Scottish Household "
        "Survey, averaged over three years because the samples in each council are small.",
}


def area_note(area_id, nation="England"):
    return AREA_NOTES.get((nation, area_id)) or next(note for a, _, note in AREAS if a == area_id)


@dataclass(frozen=True)
class Measure:
    id: str
    area: str
    label: str  # in plain English
    unit: str  # "%" or "" (a rate or count)
    better: str  # "higher" or "lower"
    source: str  # its id in data/councils.json "sources", which gives the period
    official: str = ""  # the publication's own name for it, if different
    nations: tuple = ("England",)  # where it is published; ranked within each separately
    other_sources: tuple = ()  # ((nation, source id),) where a nation's figures come from another source

    def source_for(self, nation="England"):
        return dict(self.other_sources).get(nation, self.source)


MEASURES = [
    Measure("ehcp_20wk", "send", "Special educational needs plans issued on time", "%", "higher", "ehcp",
            "New education, health and care (EHC) plans issued within the legal limit of 20 weeks"),
    Measure("om_upheld", "complaints", "Complaints the Ombudsman upheld, per 100,000 residents", "", "lower", "lgo"),
    Measure("om_received", "complaints", "Complaints that reached the Ombudsman, per 100,000 residents", "", "lower",
            "lgo", nations=("England", "Scotland"), other_sources=(("Scotland", "spso"),)),
    Measure("om_children", "complaints", "Upheld complaints about children's services, per 100,000 residents",
            "", "lower", "lgo_decisions"),
    Measure("om_sen", "complaints", "Upheld complaints about special educational needs, per 100,000 residents",
            "", "lower", "lgo_decisions"),
    Measure("om_homeless", "complaints", "Upheld complaints about homelessness, per 100,000 residents",
            "", "lower", "lgo_decisions"),
    Measure("om_remedy_before", "complaints", "Upheld complaints the council had already put right", "%", "higher",
            "lgo", "Upheld cases where the council provided a satisfactory remedy before the complaint reached "
            "the Ombudsman"),
    Measure("om_timely", "complaints", "Ombudsman's recommendations carried out on time", "%", "higher", "lgo",
            "Compliance outcomes recorded as delivered on time"),
    Measure("tsm_overall", "housing", "Tenants satisfied with the overall service", "%", "higher", "tsm",
            "Tenant Satisfaction Measure TP01"),
    Measure("tsm_maintained", "housing", "Tenants who say their home is well maintained", "%", "higher", "tsm",
            "Tenant Satisfaction Measure TP04"),
    Measure("tsm_safe", "housing", "Tenants who say their home is safe", "%", "higher", "tsm",
            "Tenant Satisfaction Measure TP05"),
    Measure("tsm_listens", "housing", "Tenants who say the council listens and acts", "%", "higher", "tsm",
            "Tenant Satisfaction Measure TP06"),
    Measure("tsm_repairs", "housing", "Routine repairs done on time", "%", "higher", "tsm",
            "Non-emergency responsive repairs completed within target (RP02)"),
    Measure("tsm_decent", "housing", "Council homes below the Decent Homes Standard", "%", "lower", "tsm",
            "Homes that do not meet the Decent Homes Standard (RP01)"),
    Measure("tsm_complaints", "housing", "Tenants' complaints answered on time", "%", "higher", "tsm",
            "Stage 1 complaints responded to within the Housing Ombudsman's timescales (CH02)"),
    Measure("ctax_collect", "ctax", "Council tax collected in the year it was due", "%", "higher", "ctax",
            nations=("England", "Scotland"), other_sources=(("Scotland", "lgbf"),)),
    Measure("nndr_collect", "ctax", "Business rates collected in the year they were due", "%", "higher", "ctax",
            "Non-domestic rates collected by 31 March as a percentage of the amount collectable"),
    Measure("fly_rate", "streets", "Fly-tipping incidents, per 1,000 residents", "", "lower", "fly"),
    Measure("fly_enforce", "streets", "Enforcement actions, per 100 fly-tipping incidents", "", "higher", "fly"),
    Measure("fly_fpn", "streets", "Fixed penalty notices, per 100 fly-tipping incidents", "", "higher", "fly",
            "Fixed penalty notices for fly-tipping and for breaches of household duty of care"),
    Measure("recycling", "streets", "Household waste reused, recycled or composted", "%", "higher", "waste",
            nations=("England", "Scotland"), other_sources=(("Scotland", "lgbf"),)),
    Measure("residual_waste", "streets", "Household waste not recycled, in kg per household", "", "lower", "waste",
            "Residual household waste per household (formerly NI191)"),
    Measure("ta_rate", "homeless", "Households in temporary accommodation, per 1,000 households", "", "lower",
            "homelessness", nations=("England", "Scotland"), other_sources=(("Scotland", "scot_homelessness"),)),
    Measure("ta_long", "homeless", "Families in temporary accommodation for 2 years or more", "%", "lower",
            "homelessness"),
    Measure("prevention", "homeless", "People at risk of homelessness helped to keep or find a home", "%", "higher",
            "homelessness", "Prevention duty cases ending with accommodation secured for 6 months or more"),
    Measure("relief", "homeless", "Homeless people helped to find a home", "%", "higher", "homelessness",
            "Relief duty cases ending with accommodation secured for 6 months or more"),
    Measure("web_access", "digital", "Council website accessibility score", "%", "higher", "silktide",
            "Silktide Index WCAG 2.2 AA score", nations=("England", "Scotland")),
    # Scotland, from the Local Government Benchmarking Framework
    Measure("literacy", "schools", "Primary pupils at the expected level in literacy", "%", "higher", "lgbf",
            "Pupils in P1, P4 and P7 achieving the expected Curriculum for Excellence level in literacy",
            nations=("Scotland",)),
    Measure("numeracy", "schools", "Primary pupils at the expected level in numeracy", "%", "higher", "lgbf",
            "Pupils in P1, P4 and P7 achieving the expected Curriculum for Excellence level in numeracy",
            nations=("Scotland",)),
    Measure("attendance", "schools", "School attendance", "%", "higher", "lgbf",
            "School attendance rate (per 100 pupils)", nations=("Scotland",)),
    Measure("destinations", "schools", "School leavers going on to work, study or training", "%", "higher",
            "lgbf", "Pupils entering positive destinations", nations=("Scotland",)),
    Measure("care_impact", "care", "Adults cared for at home who say it improves their quality of life", "%",
            "higher", "lgbf", "Adults supported at home who agree that their services and support had an "
            "impact in improving or maintaining their quality of life", nations=("Scotland",)),
    Measure("care_graded", "care", "Adult care services graded good or better", "%", "higher", "lgbf",
            nations=("Scotland",)),
    Measure("delayed_discharge", "care",
            "Days older people spend in hospital when ready to leave, per 1,000 people aged 75 or over", "",
            "lower", "lgbf", nations=("Scotland",)),
    Measure("housing_quality", "housing", "Council homes meeting the Scottish Housing Quality Standard", "%",
            "higher", "lgbf", nations=("Scotland",)),
    Measure("repair_days", "housing", "Days to complete a non-emergency repair", "", "lower", "lgbf",
            "Average number of days taken to complete non-emergency repairs", nations=("Scotland",)),
    Measure("ta_days", "homeless", "Days households spent in temporary accommodation, on average", "", "lower",
            "scot_homelessness", "Average total time spent in temporary accommodation, for cases that closed",
            nations=("Scotland",)),
    Measure("settled", "homeless", "Homeless households who found a settled home", "%", "higher",
            "scot_homelessness", "Unintentionally homeless households securing settled accommodation (known "
            "outcomes where contact was maintained)", nations=("Scotland",)),
    Measure("street_clean", "streets", "Street cleanliness score", "%", "higher", "lgbf", nations=("Scotland",)),
    Measure("bins_satisfied", "streets", "Adults satisfied with bin collections", "%", "higher", "lgbf",
            "Adults satisfied with refuse collection (three-year average)", nations=("Scotland",)),
    Measure("streets_satisfied", "streets", "Adults satisfied with street cleaning", "%", "higher", "lgbf",
            "Adults satisfied with street cleaning (three-year average)", nations=("Scotland",)),
]

SPENDING = [
    "Children's social care", "Adult social care", "Social work and social care", "Public health", "Housing (general fund)",
    "Environmental and regulatory", "Highways and transport", "Culture and leisure", "Planning and development",
    "Central services", "All services excluding schools",
]

GRADES = ["Outstanding", "Good", "Requires improvement", "Inadequate"]

# Where a council sits, by position in its group: which quarter, best first.
# The same names and colours on council pages, hub pages and measure maps.
BANDS = {
    "top": ("Top quarter", "app-q1"),
    "second": ("Second quarter", "app-q2"),
    "third": ("Third quarter", "app-q3"),
    "bottom": ("Bottom quarter", "app-q4"),
}
QUARTERS = list(BANDS)  # best first


def load():
    """{"sources": {...}, "councils": {slug: council}, "by_code": {code: council}}."""
    return _load(DATA_FILE, tuple(PUBLISHED))


@cache
def _load(path, published=("England",)):
    with open(path) as f:
        data = json.load(f)
    councils = {}
    for council in data["councils"]:
        if council.get("ofsted") and council["ofsted"].get("inspected"):
            council["ofsted"]["date"] = date.fromisoformat(council["ofsted"]["inspected"])
        council.setdefault("nation", NATIONS[council["code"][0]])
        if council["nation"] in published:
            councils[council["slug"]] = council
    return {"sources": data["sources"], "councils": councils,
            "by_code": {c["code"]: c for c in councils.values()}}


def councils():
    return load()["councils"]


def sources():
    return load()["sources"]


MIN_COVERAGE = 0.75  # the share of councils a measure needs figures for before it is shown


def nations():
    """The nations with councils, England first."""
    present = {c["nation"] for c in councils().values()}
    return [n for n in NATIONS.values() if n in present]


def coverage():
    """The councils on the site, in words: "every single-tier council in England"."""
    return " and ".join(["every single-tier council in England"]
                        + [f"every council in {n}" for n in nations() if n != "England"])


def in_nation(nation):
    return [c for c in councils().values() if c["nation"] == nation]


@cache
def _coverage(path, published, nation):
    return {m.id: sum(1 for c in _load(path, published)["councils"].values()
                      if c["nation"] == nation and m.id in c["values"])
            for m in MEASURES}


def available(measure, nation="England"):
    """Whether a measure covers enough of a nation's councils to rank them
    fairly. Council housing is the exception: only councils with homes have
    figures."""
    if nation not in measure.nations:
        return False
    total = sum(1 for c in councils().values() if c["nation"] == nation)
    return measure.area == "housing" or _coverage(DATA_FILE, tuple(PUBLISHED), nation)[measure.id] >= MIN_COVERAGE * total


def period(measure, nation="England"):
    """The period a measure's figures cover, in a nation: the source's own
    period for each measure if it has them, or the source's period."""
    source = sources().get(measure.source_for(nation), {})
    return source.get("periods", {}).get(measure.id) or source.get("period", "")


def groups_for(council):
    """The groups this council can be compared with."""
    available = []
    for group in GROUPS:
        if group in ("region", "type") and council["nation"] != "England":
            continue  # Scotland and Wales have no regions, and one type of council each
        if group == "type" and council["type"] == "London borough":
            continue  # the same as its region, London
        if group == "similar" and len(council["neighbours"]) < MIN_SIMILAR:
            continue
        available.append(group)
    return available


def group_members(council, group):
    """The councils to compare with, including the council itself."""
    everyone = in_nation(council["nation"])
    if group == "region":
        return [c for c in everyone if c["region"] == council["region"]]
    if group == "type":
        return [c for c in everyone if c["type"] == council["type"]]
    if group == "similar":
        by_code = load()["by_code"]
        return [council] + [by_code[code] for code in council["neighbours"] if code in by_code]
    return everyone


def group_tab(council, group):
    """The group's name on its tab: "All England", "London", "Metropolitan districts"."""
    if group == "region":
        return council["region"]
    if group == "type":
        plural = TYPE_PLURAL[council["type"]]
        return plural[0].upper() + plural[1:]
    if group == "similar":
        return "Similar councils"
    return f"All {council['nation']}"


def group_phrase(council, group):
    """The group in a sentence: "all councils in England", "councils in London"."""
    if group == "region":
        return "London boroughs" if council["region"] == "London" else f"councils in {council['region']}"
    if group == "type":
        return f"{TYPE_PLURAL[council['type']]}"
    if group == "similar":
        return "similar councils"
    return f"all councils in {council['nation']}"


def group_option(council, group):
    """What the "Compared with" menu says: "All councils in England (130)"."""
    count = len(group_members(council, group))
    names = {"nation": f"All councils in {council['nation']}", "region": group_tab(council, "region"),
             "type": group_tab(council, "type"), "similar": "Similar councils"}
    if group == "region" and council["region"] == "London":
        names["region"] = "London boroughs"
    elif group == "region":
        names["region"] = f"Councils in {council['region']}"
    return f"{names[group]} ({count})"


def path(council, group="nation"):
    return f"/{council['slug']}/" if group == "nation" else f"/{council['slug']}/{group}/"


def fmt(value, unit="", places=1):
    """22.9 -> "22.9%", 111.2 -> "111.2", 7.0 -> "7"."""
    if value is None:
        return "No figure"
    if unit == "%":
        return f"{value:.{places}f}%"
    if unit == "£":
        return f"−£{-value:,.0f}" if value < 0 else f"£{value:,.0f}"
    text = f"{value:.{places}f}"
    return text[:-2] if text.endswith(".0") else text


def fmt_pair(value, other, unit=""):
    """A figure and the median it's compared with, with one more decimal
    place when they'd otherwise look the same but aren't: 0.9 against 0.95
    shouldn't read as "0.9 against 0.9"."""
    if value is not None and other is not None and value != other and fmt(value, unit) == fmt(other, unit):
        return fmt(value, unit, 2), fmt(other, unit, 2)
    return fmt(value, unit), fmt(other, unit)


def fmt_pence(value):
    """3.456 -> "£3.46", for small weekly amounts."""
    return f"£{value:,.2f}"


def ordinal(n):
    """1 -> "1st", 22 -> "22nd", 13 -> "13th"."""
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def lower_first(text):
    """ "New EHC plans..." -> "new EHC plans...", leaving acronyms alone."""
    if len(text) > 1 and text[0].isupper() and text[1].islower():
        return text[0].lower() + text[1:]
    return text


def quarter(position, count):
    """0 for the top quarter of a group to 3 for the bottom; ties share a position."""
    for q in (3, 2, 1):
        if position > count * q / 4:
            return q
    return 0


def band(position, count):
    return QUARTERS[quarter(position, count)]


def position(value, values, better):
    """1 for the best; ties share a position."""
    if better == "higher":
        return sum(1 for v in values if v > value) + 1
    return sum(1 for v in values if v < value) + 1


@dataclass
class Strip:
    """Every council as a mark on one line, better to the right.

    Positions are percentages across. The other councils are drawn as short
    vertical marks in one SVG path each (in and out of the group), which
    keeps pages small with 130 councils on every row.
    """
    dots: list  # [(left %, in the group)]
    me: float
    median: float

    def path(self, in_group):
        return " ".join(f"M{left * 10:.0f} 7v12" for left, group in self.dots if group == in_group)


def strip(values_by_code, me_code, group_codes, better, group_median):
    values = list(values_by_code.values())
    low, high = min(values), max(values)
    span = (high - low) or 1

    def left(value):
        share = (value - low) / span
        if better == "lower":
            share = 1 - share
        return round(2 + share * 96, 1)

    dots = [(left(v), code in group_codes) for code, v in values_by_code.items() if code != me_code]
    # Group members drawn last, over the rest
    dots.sort(key=lambda dot: dot[1])
    return Strip(dots=dots, me=left(values_by_code[me_code]), median=left(group_median))


@dataclass
class Row:
    measure: Measure
    period: str
    value: str
    median: str
    position: int = None
    count: int = 0
    band: str = None
    strip: Strip = None
    caveat: str = None

    @property
    def band_text(self):
        return BANDS[self.band][0] if self.band else None

    @property
    def band_class(self):
        return BANDS[self.band][1] if self.band else None


@dataclass
class Area:
    id: str
    name: str
    note: str
    rows: list  # [Row], only measures with a figure for this council
    missing: int  # measures with no figure

    @property
    def counts(self):
        return {key: sum(1 for r in self.rows if r.band == key) for key in BANDS}

    @property
    def uniform(self):
        """The band every measure is in, when there are several and they're all
        in the same one: then the headline says so and the rows don't repeat it."""
        bands = {r.band for r in self.rows if r.band}
        return bands.pop() if len(bands) == 1 and len(self.rows) > 1 else None

    @property
    def headline(self):
        """ "2 of 7 measures in the bottom quarter", the worst news first. None
        for a single measure, whose tag says it."""
        ranked = [r for r in self.rows if r.band]
        if len(ranked) < 2:
            return None
        if self.uniform:
            return f"All {len(ranked)} measures in the {BANDS[self.uniform][0].lower()}"
        counts = self.counts
        for key in reversed(QUARTERS):
            if counts[key]:
                return f"{counts[key]} of {len(ranked)} measures in the {BANDS[key][0].lower()}"
        return None


@dataclass
class Comparison:
    council: dict
    group: str
    tab: str
    phrase: str
    members: list
    areas: list = field(default_factory=list)  # [Area]
    counts: dict = field(default_factory=dict)
    compares_worst: list = field(default_factory=list)  # [str], the worst first
    compares_best: list = field(default_factory=list)
    ranked: int = 0  # measures with a figure and a position
    spending: list = field(default_factory=list)
    grades: list = field(default_factory=list)
    trends: list = field(default_factory=list)
    fly: dict = None


def _summary(rows, worst=True):
    # The bottom (or top) quarter, or the next quarter in if there's nothing there
    ends = ["bottom", "third"] if worst else ["top", "second"]
    picked = next(([r for r in rows if r.band == end] for end in ends if any(r.band == end for r in rows)), [])
    picked.sort(key=lambda r: r.position / r.count, reverse=worst)
    # Each with its position and which end is best, so "6th of 6" can't be
    # read as good on a measure where a low number is best
    return [
        f"{r.measure.label} ({ordinal(r.position)} of {r.count}; "
        f"1st is {'highest' if r.measure.better == 'higher' else 'lowest'})"
        for r in picked[:3]
    ]


def compare(council, group="nation"):
    members = group_members(council, group)
    member_codes = {c["code"] for c in members}
    everyone = in_nation(council["nation"])  # the marks on each chart
    result = Comparison(council=council, group=group, tab=group_tab(council, group),
                        phrase=group_phrase(council, group), members=members)
    rows = []
    for area_id, area_name, note in AREAS:
        area_rows = []
        for m in (m for m in MEASURES if m.area == area_id and available(m, council["nation"])):
            group_values = [c["values"][m.id] for c in members if m.id in c["values"]]
            value = council["values"].get(m.id)
            shown_value, shown_median = fmt_pair(value, median(group_values) if group_values else None, m.unit)
            row = Row(measure=m, period=period(m, council["nation"]), value=shown_value, median=shown_median,
                      caveat=caveat(council, m.id))
            if value is not None and len(group_values) > 1:
                row.position = position(value, group_values, m.better)
                row.count = len(group_values)
                row.band = band(row.position, row.count)
                all_values = {c["code"]: c["values"][m.id] for c in everyone if m.id in c["values"]}
                row.strip = strip(all_values, council["code"], member_codes, m.better, median(group_values))
            area_rows.append(row)
            rows.append(row)
        if not any(m.area == area_id and council["nation"] in m.nations for m in MEASURES):
            continue  # an area with no measures in the council's nation, such as schools in England
        shown = [r for r in area_rows if r.band]
        result.areas.append(Area(area_id, area_name, area_note(area_id, council["nation"]), shown,
                                 len(area_rows) - len(shown)))
    banded = [r for r in rows if r.band]
    result.ranked = len(banded)
    result.counts = {key: sum(1 for r in banded if r.band == key) for key in BANDS}
    result.compares_worst = _summary(banded, worst=True)
    result.compares_best = _summary(banded, worst=False)
    result.spending = _spending(council, members, member_codes, everyone)
    result.grades = [(grade, sum(1 for c in members if (c.get("ofsted") or {}).get("grade") == grade))
                     for grade in GRADES]
    result.trends = _trends(council, members)
    result.fly = fly_detail(council, members)
    return result


def caveat(council, measure_id):
    """Why a council's figure on a measure isn't quite like the others', if it isn't."""
    if measure_id == "fly_rate" and (council.get("fly") or {}).get("basis") == "public":
        return ("Counts only fly-tips reported by the public, not those council staff find, so it may look lower "
                "than councils that count both.")
    return None


def fly_detail(council, members):
    """Where fly-tips were found, what was dumped and what the council did
    about them, for the council page. Not ranked: most councils prosecute
    nobody in a year, and sizes are recorded differently."""
    fly = council.get("fly")
    if not fly:
        return None
    large = [c["fly"]["large"] for c in members if (c.get("fly") or {}).get("large") is not None]
    return {**fly, "large_median": round(median(large)) if large else None}


def key_figures(comparison):
    """One sentence for each area, on its first measure with a position:
    each stands on its own, so it can be quoted with the council, figure,
    year and position together."""
    name = comparison.council["name"]
    sentences = []
    for area in comparison.areas:
        r = next((r for r in area.rows if r.band), None)
        if not r:
            continue
        end = "highest" if r.measure.better == "higher" else "lowest"
        when = f"In {r.period}, " if r.period else ""
        sentences.append(f"{when}{name} was {ordinal(r.position)} of {r.count} among {comparison.phrase} "
                         f"for {lower_first(r.measure.label)} (1st is {end}), at {r.value} against a median "
                         f"of {r.median}.")
    return sentences


def measure_summary(measure, rows, nation="England"):
    """The highest, the lowest and the median on a measure page, in a sentence."""
    if len(rows) < 2:
        return None
    by_value = sorted(rows, key=lambda r: (r[2], r[1]["name"]))
    low, high = by_value[0], by_value[-1]
    middle = fmt(median(r[2] for r in rows), measure.unit)
    when = f"In {period(measure, nation)}, " if period(measure, nation) else ""
    return (f"{when}the highest figure was {high[1]['name']}’s ({fmt(high[2], measure.unit)}) and the lowest "
            f"{low[1]['name']}’s ({fmt(low[2], measure.unit)}). The median across {len(rows)} councils in "
            f"{nation} was {middle}.")


# Sources each nation's pages use beyond its measures' own
PAGE_SOURCES = {
    "England": {"band_d", "spending", "funding", "ofsted", "neighbours", "area_bands"},
    "Scotland": {"scot_band_d", "scot_spending"},
}
# Where a nation's council tax and spending figures come from, if not England's sources
NATION_SOURCES = {("Scotland", "band_d"): "scot_band_d", ("Scotland", "spending"): "scot_spending"}


def nation_source(source_id, nation="England"):
    """The source that gives a nation's figures of this kind: "spending" -> "scot_spending"."""
    return NATION_SOURCES.get((nation, source_id), source_id)


def nation_sources(nation):
    """The sources a nation's pages use."""
    used = {m.source_for(nation) for m in MEASURES if nation in m.nations} | {"population"}
    return used | PAGE_SOURCES.get(nation, set())


def updated(source_ids=None):
    """The date the newest of these sources (or of every source the site's
    nations use) was published."""
    if source_ids is None:
        source_ids = set().union(*(nation_sources(n) for n in nations()))
    dates = [s.get("published") for key, s in sources().items() if key in source_ids]
    return max((d for d in dates if d), default="")


def _spending(council, members, member_codes, everyone):
    rows = []
    for service in SPENDING:
        value = council["spend"].get(service)
        values = [c["spend"][service] for c in members if service in c["spend"]]
        if value is None or not values:
            continue
        all_values = {c["code"]: c["spend"][service] for c in everyone if service in c["spend"]}
        rows.append({
            "service": service,
            "value": fmt(value, "£"),
            "median": fmt(median(values), "£"),
            "rank": sum(1 for v in values if v > value) + 1,
            "count": len(values),
            # Not better or worse, so lower to the left and no colour
            "strip": strip(all_values, council["code"], member_codes, "higher", median(values)),
        })
    return rows


# Line charts: a fixed coordinate space, scaled by the browser
CHART_W, CHART_H = 320, 180
PAD_L, PAD_R, PAD_T, PAD_B = 40, 10, 10, 26


def _nice_max(high, unit):
    if unit == "%" and high > 50:
        return 100, 25
    raw = (high * 1.1 or 1) / 4
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(s * magnitude for s in (1, 2, 2.5, 5, 10) if s * magnitude >= raw)
    return step * 4, step


def line_chart(periods, series, unit):
    """SVG coordinates for a line chart. series: [(name, {period: value}, css class)]."""
    values = [v for _, data, _ in series for v in data.values() if v is not None]
    if not values or not periods:
        return None
    top, step = _nice_max(max(values), unit)
    width = CHART_W - PAD_L - PAD_R
    height = CHART_H - PAD_T - PAD_B

    def x(i):
        return round(PAD_L + (i / (len(periods) - 1) if len(periods) > 1 else 0) * width, 1)

    def y(v):
        return round(PAD_T + (1 - v / top) * height, 1)

    ticks = []
    t = 0
    while t <= top + 1e-9:
        ticks.append({"y": y(t), "label": fmt(t, unit).replace(".0%", "%")})
        t += step
    # About four labels, always the last, never two crowded together
    last_i = len(periods) - 1
    every = max(1, -(-len(periods) // 4))
    shown = [i for i in range(last_i) if i % every == 0 and last_i - i >= every] + [last_i]
    labels = [{"x": x(i), "text": periods[i][2:] if len(periods[i]) > 4 else periods[i]} for i in shown]
    lines = []
    for name, data, css in series:
        points = [(x(i), y(data[p])) for i, p in enumerate(periods) if data.get(p) is not None]
        path_d = " ".join(f"{'M' if n == 0 else 'L'}{px},{py}" for n, (px, py) in enumerate(points))
        last = next((data[p] for p in reversed(periods) if data.get(p) is not None), None)
        lines.append({"name": name, "path": path_d, "points": points, "class": css, "last": fmt(last, unit)})
    return {"width": CHART_W, "height": CHART_H, "left": PAD_L, "right": CHART_W - PAD_R, "ticks": ticks,
            "labels": labels, "lines": lines, "top": top, "periods": periods, "pad_t": PAD_T, "plot_h": height}


TRENDS = [
    ("ehcp_20wk", "EHC plans issued within 20 weeks", "By calendar year.", "%"),
    ("om_upheld", "Upheld Ombudsman complaints per 100,000 residents",
     "Using the latest population estimate for every year.", ""),
    ("recycling", "Household waste recycling rate", "Reused, recycled or composted.", "%"),
    ("fly_rate", "Fly-tipping incidents per 1,000 residents", "As recorded by the council.", ""),
    ("fly_fpn", "Fixed penalty notices per 100 fly-tipping incidents",
     "For fly-tipping and household duty of care. Councils could fine fly-tippers on the spot from May 2016.", ""),
    ("ta_days", "Average days in temporary accommodation", "For homelessness cases that closed in each year.", ""),
]


def _trends(council, members):
    charts = []
    for trend_id, title, note, unit in TRENDS:
        periods = sorted({p for c in members for p in c["trends"].get(trend_id, {})})[-10:]
        mine = council["trends"].get(trend_id, {})
        if not mine:
            continue
        medians = {}
        for p in periods:
            values = [c["trends"][trend_id][p] for c in members if p in c["trends"].get(trend_id, {})]
            medians[p] = round(median(values), 1) if values else None
        chart = line_chart(periods, [(council["name"], mine, "app-chart__line--me"),
                                     ("Median", medians, "app-chart__line--median")], unit)
        if chart:
            charts.append({"id": trend_id, "title": title, "note": note, "chart": chart})
    return charts


# Council tax bands as a share of Band D (they are fixed by law). Scotland
# raised bands E to H in 2017.
BANDS_CT = {
    "England": [("A", 6 / 9), ("B", 7 / 9), ("C", 8 / 9), ("D", 1), ("E", 11 / 9), ("F", 13 / 9), ("G", 15 / 9),
                ("H", 18 / 9)],
    "Scotland": [("A", 240 / 360), ("B", 280 / 360), ("C", 320 / 360), ("D", 1), ("E", 473 / 360),
                 ("F", 585 / 360), ("G", 705 / 360), ("H", 882 / 360)],
}
# Where to find your band
BAND_CHECK = {
    "England": ("https://www.gov.uk/council-tax-bands", "Check your council tax band on GOV.UK"),
    "Scotland": ("https://www.saa.gov.uk/", "Check your council tax band with the Scottish Assessors"),
}
# What else is on the bill
BILL_NOTES = {
    "Scotland": "Scottish Water’s water and sewerage charges are added to council tax bills too, and are not "
                "included here.",
}

# The council's own spending, as split on the council tax calculator
CT_SERVICES = [
    ("Adult social care", "Adult social care"),
    ("Children's social care", "Children's social care"),
    ("Social work and social care", "Social work and social care"),
    ("Housing and homelessness", "Housing (general fund)"),
    ("Bins, streets, parks and environment", "Environmental and regulatory"),
    ("Public health", "Public health"),
    ("Roads and transport", "Highways and transport"),
    ("Libraries, culture and leisure", "Culture and leisure"),
    ("Planning and development", "Planning and development"),
    ("Running the council", "Central services"),
]


def council_tax(council):
    """What the council tax calculator shows, for a Band D bill.

    The bill is split by who sets it; the council's part is then split in
    proportion to the council's net spending on each service. Services that
    bring in more than they cost (roads, where parking pays) are left out of
    the split rather than shown as negative.
    """
    parts = council.get("band_d_parts")
    if not parts or not council.get("band_d"):
        return None
    london = council["region"] == "London"
    labels = [
        ("council", f"{council['name']} council"),
        ("parish", "Parish or town council (average across the area)"),
        ("gla_or_county", "Mayor of London (GLA), including police and fire" if london else "County council"),
        ("combined", "Combined authority (regional mayor)"),
        ("police", "Police"),
        ("fire", "Fire and rescue"),
    ]
    who = [{"key": key, "label": label, "band_d": parts[key]} for key, label in labels if parts.get(key, 0) > 0.5]
    nation = council["nation"]
    spend = council.get("spend", {})
    positive = [(label, spend[key]) for label, key in CT_SERVICES if spend.get(key, 0) > 0]
    total = sum(v for _, v in positive)
    services = []
    if total:
        for label, value in sorted(positive, key=lambda s: -s[1]):
            services.append({"label": label, "share": value / total * 100,
                             "band_d": parts["council"] * value / total})
    return {
        "band_d": council["band_d"],
        "council_band_d": parts["council"],
        "bands": [{"band": b, "ratio": r} for b, r in BANDS_CT[nation]],
        "period": sources().get(nation_source("band_d", nation), {}).get("period", ""),
        "spend_period": sources().get(nation_source("spending", nation), {}).get("period", ""),
        "check": BAND_CHECK[nation],
        "note": BILL_NOTES.get(nation),
        "who": who,
        "services": services,
        "left_out": [label for label, key in CT_SERVICES if key in spend and spend[key] <= 0],
        "funding": council.get("funding"),
    }


# Measure pages: a hexagon map of England and every council ranked

HEXMAP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hexmap.json")
# Colour by quarter of the nation, best first, as on the council pages
QUARTER_CLASSES = [cls for _, cls in BANDS.values()]
QUARTER_NAMES = [name for name, _ in BANDS.values()]


def measure_by_id(measure_id):
    return next(m for m in MEASURES if m.id == measure_id)


def measure_path(measure, nation="England"):
    """England's measure pages are at /measures/<id>/, the others under them."""
    base = f"/measures/{measure.id.replace('_', '-')}/"
    return base if nation == "England" else f"{base}{slugify(nation)}/"


def ranking(measure, nation="England", members=None):
    """[(position, council, value, quarter 0-3)] for every council in the
    nation (or every one of members) with a figure, best first."""
    with_values = [c for c in members or in_nation(nation) if measure.id in c["values"]]
    values = [c["values"][measure.id] for c in with_values]
    rows = []
    for c in with_values:
        pos = position(c["values"][measure.id], values, measure.better)
        rows.append((pos, c, c["values"][measure.id], quarter(pos, len(values))))
    rows.sort(key=lambda r: (r[0], r[1]["name"]))
    return rows


def measure_overview(measure, nation="England"):
    """The best and worst councils and the median on a measure, for the list
    of measures: {"best": (names, figure), "worst": ..., "median": figure}."""
    ranked = ranking(measure, nation)
    if len(ranked) < 2:
        return None
    def end(value):
        """ "Rutland" or, when others share the figure, "Rutland and 12 others"."""
        tied = sorted(c["name"] for _, c, v, _ in ranked if v == value)
        name = tied[0] if len(tied) == 1 else f"{tied[0]} and {len(tied) - 1} other{'s' if len(tied) > 2 else ''}"
        return name, fmt(value, measure.unit)
    return {"best": end(ranked[0][2]), "worst": end(ranked[-1][2]),
            "median": fmt(median(v for _, _, v, _ in ranked), measure.unit)}


def recent_updates(n=4):
    """The newest figures on the site, for the home page: [{"date", "measure",
    "nation", "period"}], one measure per source, newest first."""
    found = []
    for source_id, source in sources().items():
        nation = next((nat for nat in nations() if source_id in nation_sources(nat)), None)
        measure = next((m for m in MEASURES if nation and m.source_for(nation) == source_id and available(m, nation)),
                       None)
        if measure and source.get("published"):
            found.append({"date": source["published"], "measure": measure, "nation": nation,
                          "period": period(measure, nation)})
    return sorted(found, key=lambda u: u["date"], reverse=True)[:n]


# Hub pages: every council in a region, or of a type, side by side

def slugify(text):
    import re
    return re.sub(r"[^a-z0-9]+", "-", text.lower().replace("&", "and").replace("'", "")).strip("-")


def hubs():
    """[(group, value)] for every hub page: each region of England, then each
    type of council apart from London boroughs, which are the same as London,
    then each other nation, which has no regions and one type of council."""
    everyone = in_nation("England")
    return ([("region", r) for r in sorted({c["region"] for c in everyone})]
            + [("type", t) for t in sorted({c["type"] for c in everyone}) if t != "London borough"]
            + [("nation", n) for n in nations() if n != "England"])


def hub_path(group, value):
    if group == "region":
        return f"/regions/{slugify(value)}/"
    if group == "nation":
        return f"/{slugify(value)}/"
    return f"/types/{slugify(TYPE_PLURAL[value])}/"


def hub_for(council, group):
    """The hub page a council's region or type links to, if there is one."""
    if group == "type" and council["type"] == "London borough":
        return hub_path("region", "London")
    return hub_path(group, council[group])


def hub(group, value):
    """What a hub page shows: each council's spread of positions within the
    group, and every measure ranked within it."""
    nation = value if group == "nation" else "England"
    members = sorted((c for c in in_nation(nation) if c[group] == value), key=lambda c: c["name"])
    phrase = f"councils in {nation}" if group == "nation" else group_phrase(members[0], group)
    rows = []
    for c in members:
        comparison = compare(c, group)
        rows.append({"council": c, "counts": comparison.counts, "ranked": comparison.ranked,
                     "path": path(c, group if group in groups_for(c) else "nation")})
    measures = []
    for m in MEASURES:
        if not available(m, nation):
            continue
        ranked = ranking(m, members=members)
        if len(ranked) > 1:
            measures.append({"measure": m, "rows": ranked, "period": period(m, nation),
                             "median": fmt(median(v for _, _, v, _ in ranked), m.unit)})
    return {"group": group, "value": value, "nation": nation, "members": members, "phrase": phrase,
            "title": phrase[0].upper() + phrase[1:], "rows": rows, "measures": measures}


# The council tax page: every council's Band D bill

def band_d_ranking(nation="England"):
    """[(position, council, Band D, the council's own part)], lowest first,
    within a nation: bands and bills are set differently in each."""
    with_values = [c for c in in_nation(nation) if c.get("band_d")]
    values = [c["band_d"] for c in with_values]
    rows = [(position(c["band_d"], values, "lower"), c, c["band_d"], (c.get("band_d_parts") or {}).get("council"))
            for c in with_values]
    rows.sort(key=lambda r: (r[0], r[1]["name"]))
    return rows


def band_d_path(nation="England"):
    return "/council-tax/" if nation == "England" else f"/council-tax/{slugify(nation)}/"


def band_d_summary(rows, nation="England"):
    if len(rows) < 2:
        return None
    low, high = rows[0], rows[-1]
    when = sources().get(nation_source("band_d", nation), {}).get("period", "")
    return (f"{'In ' + when + ', ' if when else ''}the highest Band D council tax was {high[1]['name']}’s "
            f"({fmt(high[2], '£')} a year) and the lowest {low[1]['name']}’s ({fmt(low[2], '£')}). "
            f"The median across {len(rows)} councils in {nation} was {fmt(median(r[2] for r in rows), '£')}.")


@cache
def _hexes():
    with open(HEXMAP_FILE) as f:
        return json.load(f)


def hexmap(measure, nation="England"):
    """SVG geometry for the map: every district in the nation, its councils
    coloured (in England, county and district areas are grey).

    Hexagons are pointy-topped in odd-r layout (odd rows shifted right), and
    r counts up from the south, so it is flipped to draw north at the top.
    """
    from pipeline.sheets import SAME_COUNCIL
    alias = {a: b for pair in SAME_COUNCIL for a, b in (pair, pair[::-1])}
    by_code = load()["by_code"]
    ranked = ranking(measure, nation)
    quarter_of = {c["code"]: q for _, c, _, q in ranked}
    value = {c["code"]: v for _, c, v, _ in ranked}
    hexes = {code: h for code, h in _hexes()["hexes"].items() if NATIONS.get(code[0]) == nation}
    size = 10  # centre to corner
    w = math.sqrt(3) * size
    min_q = min(h["q"] for h in hexes.values())
    min_r, max_r = min(h["r"] for h in hexes.values()), max(h["r"] for h in hexes.values())
    corners = [(round(math.cos(math.radians(a)) * size, 2), round(math.sin(math.radians(a)) * size, 2))
               for a in (30, 90, 150, 210, 270, 330)]
    cells = []
    for code, h in hexes.items():
        council = by_code.get(code) or by_code.get(alias.get(code))
        x = (h["q"] - min_q) * w + (w / 2 if h["r"] % 2 else 0) + w
        y = (max_r - h["r"]) * size * 1.5 + size * 1.5
        points = " ".join(f"{round(x + dx, 1)},{round(y + dy, 1)}" for dx, dy in corners)
        if council and council["code"] in quarter_of:
            q = quarter_of[council["code"]]
            cells.append({"points": points, "class": QUARTER_CLASSES[q], "council": council,
                          "label": f"{council['name']}: {fmt(value[council['code']], measure.unit)}, "
                                   f"{QUARTER_NAMES[q].lower()}"})
        elif council:
            cells.append({"points": points, "class": "app-hex--none", "council": council,
                          "label": f"{council['name']}: no figure"})
        else:
            cells.append({"points": points, "class": "app-hex--other", "council": None, "label": h["n"]})
    width = (max(h["q"] for h in hexes.values()) - min_q) * w + w * 2.5
    height = (max_r - min_r + 1) * size * 1.5 + size * 2
    return {"cells": cells, "width": round(width), "height": round(height)}


def site_data():
    """What the charts' JavaScript needs, in one file every page shares:
    each council's figures, so marks can be named and a second council
    drawn on any page."""
    everyone = sorted(councils().values(), key=lambda c: c["name"])
    return {
        "councils": [{"slug": c["slug"], "name": c["name"], "code": c["code"], "region": c["region"],
                      "nation": c["nation"], "type": c["type"], "values": c["values"], "spend": c["spend"], "trends": c["trends"]}
                     for c in everyone],
        "measures": {m.id: {"label": m.label, "unit": m.unit, "better": m.better} for m in MEASURES},
    }
