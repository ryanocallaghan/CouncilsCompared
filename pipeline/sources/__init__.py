"""One module per publication. Each has ID, TITLE and fetch(context) -> Result."""

import math
from dataclasses import dataclass, field


def _missing(value):
    return value is None or (isinstance(value, float) and math.isnan(value))


@dataclass
class Result:
    id: str
    title: str  # what the publication is called, for the sources list
    url: str  # the page people can read it on
    period: str  # what the figures cover, e.g. "2025-26"
    published: str = ""  # YYYY-MM-DD
    files: list = field(default_factory=list)  # what was downloaded
    values: dict = field(default_factory=dict)  # {ons code: {measure: value}}
    trends: dict = field(default_factory=dict)  # {ons code: {trend: {period: value}}}
    # {ons code: {check: {"pass": True, False or None (couldn't check), "reason": str, "evidence": str}}}
    checks: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)  # anything else a later step needs
    notes: list = field(default_factory=list)  # warnings for the update summary

    def set(self, code, measure, value, places=1):
        if _missing(value):
            return
        self.values.setdefault(code, {})[measure] = round(value, places) if places is not None else value

    def check(self, code, check, passed, reason="", evidence=""):
        """A yes or no (or None: we couldn't check), with why in a sentence and what was
        found: not ranked, so kept apart from values."""
        entry = {"pass": None if passed is None else bool(passed), "reason": reason}
        if evidence:
            entry["evidence"] = evidence
        self.checks.setdefault(code, {})[check] = entry

    def trend(self, code, trend, period, value, places=1):
        if _missing(value):
            return
        self.trends.setdefault(code, {}).setdefault(trend, {})[period] = round(value, places)


def financial_year(start):
    """2025 -> "2025-26"."""
    return f"{start}-{str(start + 1)[2:]}"
