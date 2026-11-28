"""Summaries of what happened at council meetings, from the councils' own papers.

    python -m pipeline.meetings [--only lewisham,brent] [--days 14] [--dry-run] [--summary summary.md]

A trial, for a few councils whose Modern.gov sites let automated readers
download their papers (see SITES). For each meeting held in the last --days
days that hasn't been summarised yet:

1. read its page: the agenda items, their reports and appendices, and the
   decisions once they're published
2. download the reports, leaving out routine papers (apologies, the last
   meeting's minutes, work programmes), confidential items, and any file
   already summarised for another meeting. Main reports are read in full (up
   to MAX_PAGES pages), appendices only their first pages.
3. ask Claude for a short, neutral, plain-English summary, with every point
   linked to the page of the papers it came from

Meetings in the next fortnight are listed too, without summaries. Results go
in data/meetings.json, which a person checks in the weekly pull request
before anything is published. Needs ANTHROPIC_API_KEY, except with --dry-run,
which reads the papers and says how much would be sent, without sending it.
"""

import argparse
import datetime
import hashlib
import io
import json
import logging
import os
import re
import sys
import traceback
import urllib.error
import urllib.parse

from pipeline import glasgow, moderngov

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
MEETINGS = os.path.join(DATA, "meetings.json")

# Where each council's meetings are listed, and where its papers can be downloaded. Lewisham's
# own address blocks automated downloads, but the Modern.gov address its RSS feed links to doesn't.
SITES = {
    "E09000003": {"name": "Barnet", "list": "https://barnet.moderngov.co.uk", "docs": "https://barnet.moderngov.co.uk"},
    "E09000005": {"name": "Brent", "list": "https://democracy.brent.gov.uk", "docs": "https://democracy.brent.gov.uk"},
    "E09000012": {"name": "Hackney", "list": "https://hackney.moderngov.co.uk",
                  "docs": "https://hackney.moderngov.co.uk"},
    "E09000023": {"name": "Lewisham", "list": "https://councilmeetings.lewisham.gov.uk",
                  "docs": "https://lewisham.moderngov.co.uk"},
    # Glasgow's own committee system: its pages are only built when CC_NATIONS includes Scotland
    "S12000049": {"name": "Glasgow", "list": "https://onlineservices.glasgow.gov.uk/councillorsandcommittees",
                  "docs": "https://onlineservices.glasgow.gov.uk/councillorsandcommittees", "reader": glasgow},
}


def reader(site):
    """The module that reads this council's committee site."""
    return site.get("reader", moderngov)


def doc_url(site, doc):
    return doc.get("url") or site["docs"] + urllib.parse.quote(doc["path"])

MODEL = os.environ.get("CC_MEETINGS_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("CC_MEETINGS_EFFORT", "medium")
# Models that can hand a declined request to another model rather than stop (server-side fallbacks)
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-2"}
# Dollars per million tokens (input, output), for the cost in the summary. Haiku costs 5 times as
# much for requests over 100,000 tokens.
PRICES = {"claude-opus-5-5": (4, 20), "claude-sonnet-5-5": (2, 10), "claude-haiku-5-5": (0.1, 0.5)}

DAYS = 14  # how far back to look for meetings not yet summarised
AHEAD = 14  # how far ahead to list meetings coming up
KEEP_DAYS = 92  # how long summaries stay on the site
MAX_PAGES = 40  # of one report
APPENDIX_PAGES = 2  # of each appendix: enough to say what it is
MAX_TOKENS = 150_000  # roughly, sent for one meeting: beyond this, appendices then long reports are cut

ROUTINE = re.compile(
    r"apolog|declarations? of (pecuniary )?interest|^minutes|minutes of (the )?(last|previous)|urgent business|"
    r"work ?programme|forward (work )?plan|action (log|tracker)|date of (the )?next|exclusion of (the )?press|"
    r"any other business|^chair|^substitut|^membership|public information|procedure for|order of business|"
    r"notification of|terms of reference|^webcast|^attendance", re.I)
# "Exempt accommodation" is a kind of supported housing, not a confidential item
EXEMPT = re.compile(r"\bexempt\b(?! accommodation)|\bconfidential\b|\bpart (2|ii|b)\b|restricted", re.I)
# Meetings about one person's case (a licence, an adoption, an appeal, a job): nothing for residents, and
# private people's details, so they aren't sent at all
CASEWORK = re.compile(r"licensing (sub|hearing|panel)|adoption|fostering|permanence|appeals?\b|hearings?\b|"
                      r"admissions? panel|exclusions? panel|grievance|disciplinary|appointments?\b|"
                      r"licensing board|licensing and regulatory|local review", re.I)


def routine(item):
    return bool(ROUTINE.search(item["title"]))


def exempt(item):
    return bool(EXEMPT.search(item["title"]) or EXEMPT.search(item["sections"].get("About", "")))


def pdf_pages(data):
    """The text of each page of a PDF."""
    from pypdf import PdfReader
    logging.getLogger("pypdf").setLevel(logging.ERROR)  # it warns about every slightly malformed file
    reader = PdfReader(io.BytesIO(data))
    return [tidy(page.extract_text() or "") for page in reader.pages]


def tidy(text):
    """A page's text with runs of spaces joined up. Some PDFs (those saved from Google Docs) come out
    with every word on its own line, between blank ones: those words are put back into lines."""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    words = [line for line in lines if line]
    if len(words) > 10 and sum(" " not in w for w in words) > 0.8 * len(words) and len(words) < 0.7 * len(lines):
        return re.sub(r" ([,.;:)])", r"\1", " ".join(words))
    return "\n".join(lines).strip()


def tokens(text):
    return len(text) // 4  # a rough count, good enough for a budget


def long_date(iso):
    """ "2026-11-19T19:30" -> "Thursday 19 November 2026, 7.30pm"."""
    when = datetime.datetime.fromisoformat(iso)
    minutes = "" if when.minute == 0 else f".{when.minute:02d}"
    return f"{when:%A} {when.day} {when:%B %Y}, {when.hour % 12 or 12}{minutes}{'am' if when.hour < 12 else 'pm'}"


def short_date(iso):
    when = datetime.datetime.fromisoformat(iso)
    return f"{when.day} {when:%B %Y}"


class Paper:
    """A document on the agenda, and how much of it is read."""

    def __init__(self, item, doc, kind, url):
        self.item, self.doc, self.name, self.kind, self.url = item, doc, doc["name"], kind, url
        self.pages, self.sha, self.read, self.note = [], None, 0, ""

    def record(self):
        if self.read == 0:
            read = self.note or "not read"
        elif self.read >= len(self.pages):
            read = "all"
        else:
            read = f"first {self.read} of {len(self.pages)} pages"
        return {"name": self.name, "url": self.url, "pages": len(self.pages), "read": read, "sha": self.sha}


def gather(site, meeting, page, seen, get=None):
    """The agenda items worth reading, and the papers for them, with how much of each to read.

    seen is {file hash: "Committee, date"} for papers already summarised: they aren't read again,
    and nor is a file that appears twice in this meeting.
    """
    get = get or moderngov.get
    seen = dict(seen)
    items = [i for i in page["items"] if not exempt(i)]
    papers = []
    for item in items:
        if routine(item):
            continue
        docs = ([("report", item["report"])] if item["report"] else []) + [("appendix", d) for d in item["appendices"]]
        for kind, doc in docs:
            papers.append(Paper(item, doc, kind, doc_url(site, doc)))
    # A meeting run by another council may only have the whole pack of papers
    if not any(i["report"] or i["appendices"] for i in page["items"]):
        pack = next((p for p in page["packs"] if re.search(r"reports pack|public agenda", p["name"], re.I)), None)
        if pack:
            whole = {"number": "", "title": "All the papers", "report": pack, "appendices": [], "sections": {}}
            papers.append(Paper(whole, pack, "report", doc_url(site, pack)))
    for paper in papers:
        try:
            data = get(paper.url)
        except (OSError, moderngov.Disallowed) as e:
            paper.note = "couldn't download"
            print(f"  couldn't download {paper.url}: {e}", file=sys.stderr)
            continue
        paper.sha = hashlib.sha256(data).hexdigest()
        if paper.sha in seen:
            paper.note = f"same as the papers for {seen[paper.sha]}"
            continue
        seen[paper.sha] = f"{meeting['committee']}, {short_date(meeting['date'])}"
        try:
            paper.pages = pdf_pages(data)
        except Exception as e:  # a damaged or unusual PDF: say so, and carry on
            paper.note = "couldn't read"
            print(f"  couldn't read {paper.url}: {e}", file=sys.stderr)
            continue
        # Minutes are the record of what was decided, so they're read in full like a report
        whole = paper.kind == "report" or paper.doc.get("minutes")
        paper.read = min(len(paper.pages), MAX_PAGES if whole else APPENDIX_PAGES)
    # Keep within budget: appendices go first, then long reports are shortened
    for kind, limit in (("appendix", 0), ("report", 15)):
        if sum(tokens(t) for p in papers for t in p.pages[:p.read]) <= MAX_TOKENS:
            break
        for p in papers:
            if p.kind == kind and p.read > limit:
                p.read = limit
                if limit == 0:
                    p.note = "not read: the papers were too long"
    return items, papers


def prompt(council, meeting, items, papers):
    """What Claude is sent: the meeting, then each agenda item with its decision and papers."""
    numbered = [p for p in papers if p.read]
    lines = [f"Council: {council}", f"Meeting: {meeting['committee']}", f"Date: {long_date(meeting['date'])}",
             "", "[D0] is this meeting's page on the council's website, which lists the agenda and, once they're "
             "made, the decisions.", ""]
    by_item = {}
    for p in papers:
        by_item.setdefault(id(p.item), []).append(p)
    whole = [p for p in papers if p.item["title"] == "All the papers"]
    for item in items + ([whole[0].item] if whole else []):
        lines.append(f"## Agenda item {item['number']}: {item['title']}".replace("item : ", "item: "))
        if routine(item):
            lines.append("(Routine business: papers not read.)")
        for label, body in item["sections"].items():
            if label != "About" or not routine(item):
                lines.append(f"[D0] {label}: {body}")
        for p in by_item.get(id(item), []):
            if not p.read:
                lines.append(f"{p.kind.title()}: {p.name} ({p.note or 'not read'})")
                continue
            n = numbered.index(p) + 1
            extent = "all read" if p.read == len(p.pages) else f"first {p.read} read"
            lines.append(f"[D{n}] {p.kind.title()}: {p.name} ({len(p.pages)} pages, {extent})")
            for number, text in enumerate(p.pages[:p.read], 1):
                lines.append(f"--- D{n} page {number} ---\n{text}")
        lines.append("")
    return "\n".join(lines), numbered


SYSTEM = """You summarise council meetings for residents, for Councils compared, an independent website that compares English councils. You're given one meeting's agenda, the decisions recorded on the council's website (if they're published yet) and the text of its reports.

Write for someone who lives in the area and has a minute to spare:
- Plain English: short sentences and everyday words. Explain jargon and abbreviations the first time ("the Medium Term Financial Strategy, the council's plan for its budget over the next four years"). UK spelling. No markdown.
- Say what matters to residents: money, services, homes, schools, streets, care, and changes to them. Leave out routine business (apologies, declarations of interest, approving the last minutes, work programmes) unless something unusual happened.
- Give figures exactly as the papers do, with what they're for and the period they cover.

Be accurate and neutral:
- Use only what's in the papers here. Don't add background from anywhere else, guess at reasons or say what might happen next unless the papers do.
- Only say something was decided or agreed when a Decision or Minutes section says so. Otherwise say what the meeting was asked to do ("was asked to agree", "was due to discuss").
- Say who proposed or decided something (the cabinet, the committee, council officers, the auditors). Don't praise, criticise or use loaded words ("controversial", "slashed", "boost"). Report disagreements only as the papers record them.
- Don't name members of the public, people applying for licences or planning permission, children, or staff. Councillors may be named only where the papers name them for something they did at this meeting, by their role ("the cabinet member for housing"). If an item is about one person's case, describe it in general terms or leave it out.

Every point needs its sources: the paper number and page from the markers ("--- D3 page 5 ---" is doc 3, page 5), or doc 0 with page 0 for the meeting's page. Cite only pages that say what the point says.

Give at most 6 points, most important first, each a short title and one to three sentences. The summary is one or two sentences on the meeting as a whole. If the meeting only dealt with routine business, or one person's case (such as a licensing hearing), give no points and say so in the summary in general terms."""

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "points": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "text": {"type": "string"},
                "sources": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"doc": {"type": "integer"}, "page": {"type": "integer"}},
                    "required": ["doc", "page"],
                    "additionalProperties": False,
                }},
            },
            "required": ["title", "text", "sources"],
            "additionalProperties": False,
        }},
    },
    "required": ["summary", "points"],
    "additionalProperties": False,
}


def ask(client, text, model=None):
    """Claude's summary of the meeting: (parsed JSON or None, why not, {"input": n, "output": n})."""
    model = model or MODEL
    params = {
        "model": model, "max_tokens": 16000, "system": SYSTEM, "messages": [{"role": "user", "content": text}],
        "output_config": {"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
    }
    if model in FALLBACK_MODELS:
        # If the model declines (its safety checks can misfire on, say, a report about child protection),
        # the API passes the request to another model instead of stopping
        response = client.beta.messages.create(**params, betas=["server-side-fallback-2026-07-01"],
                                               fallbacks="default")
    else:
        response = client.messages.create(**params)
    usage = {"input": response.usage.input_tokens, "output": response.usage.output_tokens}
    if response.stop_reason == "refusal":
        return None, "Claude declined to summarise it", usage
    if response.stop_reason == "max_tokens":
        return None, "the summary was cut off", usage
    return json.loads("".join(b.text for b in response.content if b.type == "text")), "", usage


def sources_for(point, meeting_url, numbered):
    """A point's sources as links: the meeting's page, or a page of one of the papers."""
    out = []
    for source in point["sources"]:
        doc, page = source["doc"], source["page"]
        if doc == 0:
            link = {"label": "the meeting's page", "url": meeting_url}
        elif 1 <= doc <= len(numbered):
            paper = numbered[doc - 1]
            if 1 <= page <= paper.read:
                link = {"label": f"{paper.name}, page {page}", "url": f"{paper.url}#page={page}"}
            else:
                link = {"label": paper.name, "url": paper.url}
        else:
            continue  # a paper that doesn't exist: leave it out rather than link to the wrong one
        if link not in out:
            out.append(link)
    return out


def summarise(client, council, site, meeting, page, seen, get=None, model=None):
    """A summary of one meeting, ready to save, or (None, why not)."""
    items, papers = gather(site, meeting, page, seen, get=get)
    text, numbered = prompt(council, meeting, items, papers)
    has_decisions = any(s for i in items if not routine(i) for k, s in i["sections"].items() if k != "About")
    if not numbered and not has_decisions:
        return None, "no papers or decisions published yet", 0
    if client is None:  # a dry run
        return None, f"would send about {tokens(text):,} tokens", tokens(text)
    result, why, usage = ask(client, text, model=model)
    if result is None:
        return None, why, usage
    url = reader(site).meeting_url(site["list"], meeting)
    points = []
    for point in result["points"]:
        links = sources_for(point, url, numbered)
        if links:  # every point must link to where it came from
            points.append({"title": point["title"].strip(), "text": point["text"].strip(), "sources": links})
    return {
        "id": meeting["id"], "committee": meeting["committee"], "date": meeting["date"], "url": url,
        "summary": result["summary"].strip(), "points": points, "papers": [p.record() for p in papers],
        "model": model or MODEL, "summarised": datetime.date.today().isoformat(), "tokens": usage,
    }, "", usage


def months(start, end):
    """(year, month) for each month from start to end."""
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def load():
    if not os.path.exists(MEETINGS):
        return {"checked": None, "councils": {}}
    with open(MEETINGS) as f:
        return json.load(f)


def save(data):
    with open(MEETINGS, "w") as f:
        json.dump(data, f, indent=1, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def run(client, codes=None, days=DAYS, now=None, fatal=(), model=None):
    """Summarise each council's new meetings. Returns (data, report rows, token counts)."""
    now = now or datetime.datetime.now()
    data = load()
    report, usage = [], []
    for code, site in SITES.items():
        if codes and code not in codes:
            continue
        previous = data["councils"].get(code, {"held": [], "upcoming": []})
        held = list(previous["held"])
        done = {m["id"] for m in held}
        seen = {p["sha"]: f"{m['committee']}, {short_date(m['date'])}" for m in held for p in m["papers"] if p["sha"]}
        notes, added = [], 0
        try:
            # A month's calendar also shows the days either side of it, so the same meeting can come twice
            meetings = list({m["id"]: m for y, mo in months(now - datetime.timedelta(days=days),
                                                             now + datetime.timedelta(days=AHEAD))
                             for m in reader(site).calendar(site["list"], y, mo)}.values())
        except (OSError, moderngov.Disallowed) as e:
            report.append((site["name"], 0, f"couldn't read the meetings calendar ({e}), so kept what we had"))
            continue
        upcoming = sorted(({**m, "url": reader(site).meeting_url(site["list"], m)} for m in meetings
                           if now <= datetime.datetime.fromisoformat(m["date"]) <= now + datetime.timedelta(days=AHEAD)),
                          key=lambda m: m["date"])
        due = sorted((m for m in meetings if not m["cancelled"] and m["id"] not in done
                      and not CASEWORK.search(m["committee"])
                      and now - datetime.timedelta(days=days) <= datetime.datetime.fromisoformat(m["date"]) < now),
                     key=lambda m: m["date"])
        for meeting in due:
            label = f"{meeting['committee']}, {short_date(meeting['date'])}"
            try:
                page = reader(site).read_meeting(site["list"], meeting)
                entry, why, spent = summarise(client, site["name"], site, meeting, page, seen, model=model)
            except fatal:
                raise
            except Exception as e:
                traceback.print_exc()
                notes.append(f"{label}: failed ({type(e).__name__})")
                continue
            if spent:
                usage.append(spent)
            if entry:
                held.append(entry)
                added += 1
                # Its papers count as summarised now, so a later meeting with the same file won't read it again
                seen.update({p["sha"]: label for p in entry["papers"] if p["sha"] and p["sha"] not in seen})
            else:
                notes.append(f"{label}: {why}")
        cutoff = (now - datetime.timedelta(days=KEEP_DAYS)).isoformat()
        held = sorted((m for m in held if m["date"] >= cutoff), key=lambda m: m["date"], reverse=True)
        data["councils"][code] = {"name": site["name"], "site": site["list"], "held": held, "upcoming": upcoming}
        report.append((site["name"], added, "; ".join(notes)))
    data["checked"] = now.date().isoformat()
    return data, report, usage


def cost(usage, model=None):
    """Roughly what the requests cost, in dollars, or None for a model without a price here."""
    model = model or MODEL
    if model not in PRICES:
        return None
    total = 0.0
    for u in usage:
        price_in, price_out = PRICES[model]
        if model == "claude-haiku-5-5" and u["input"] > 100_000:
            price_in, price_out = price_in * 5, price_out * 5
        total += (u["input"] * price_in + u["output"] * price_out) / 1_000_000
    return total


def summary_text(report, usage, dry_run=False, model=None):
    lines = ["### Council meetings", "",
             "Summaries written by Claude from the councils' papers. Read a few on the preview against the "
             "papers they link to before merging.", "",
             "| Council | New summaries | Notes |", "|---|---|---|"]
    lines += [f"| {name} | {added} | {notes or ''} |" for name, added, notes in report]
    if dry_run:
        lines += ["", f"Dry run: about {sum(usage):,} tokens would have been sent."]
    elif usage:
        spent = cost(usage, model)
        dollars = f", about ${spent:.2f}" if spent is not None else ""
        lines += ["", f"{len(usage)} requests to {model or MODEL}: {sum(u['input'] for u in usage):,} tokens in, "
                      f"{sum(u['output'] for u in usage):,} out{dollars}."]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="comma-separated council names, e.g. lewisham,brent")
    parser.add_argument("--days", type=int, default=DAYS, help="how far back to look for meetings")
    parser.add_argument("--dry-run", action="store_true", help="read the papers but don't send them to Claude")
    parser.add_argument("--model", default=MODEL, help=f"the Claude model to use (default {MODEL})")
    parser.add_argument("--summary", help="add a markdown summary to this file")
    args = parser.parse_args(argv)
    codes = None
    if args.only:
        wanted = {n.strip().lower() for n in args.only.split(",")}
        codes = {code for code, site in SITES.items() if site["name"].lower() in wanted}
        if not codes:
            raise SystemExit(f"None of {args.only} are in the trial: {', '.join(s['name'] for s in SITES.values())}")
    client, fatal = None, ()
    if not args.dry_run:
        import anthropic
        client = anthropic.Anthropic()
        # A wrong key or model name would fail every request the same way: stop at the first
        fatal = (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError)
    data, report, usage = run(client, codes, days=args.days, fatal=fatal, model=args.model)
    if not args.dry_run:
        save(data)
    text = summary_text(report, usage, dry_run=args.dry_run, model=args.model)
    print(text)
    if args.summary:
        with open(args.summary, "a") as f:
            f.write("\n" + text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
