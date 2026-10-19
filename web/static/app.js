// Choosing a council goes straight to its page. Without JavaScript the form
// is sent to /go (functions/go.js), which redirects there instead.
for (const form of document.querySelectorAll('[data-module="app-choose"]')) {
  form.addEventListener("submit", (event) => {
    const slug = form.elements.council.value;
    if (/^[a-z0-9-]+$/.test(slug)) {
      event.preventDefault();
      window.location.href = `/${slug}/`;
    }
  });
}

// Where your council tax goes: every [data-band-d] amount is a Band D
// figure, recalculated for the band chosen and the single person discount
const money = (value, pence) =>
  "£" + value.toLocaleString("en-GB", { minimumFractionDigits: pence ? 2 : 0, maximumFractionDigits: pence ? 2 : 0 });

for (const section of document.querySelectorAll('[data-module="app-ctax"]')) {
  const controls = section.querySelector(".app-ctax__controls");
  const band = section.querySelector("#ctax-band");
  const alone = section.querySelector("#ctax-alone");
  const note = section.querySelector(".app-ctax__band-note");
  controls.hidden = false;
  const update = () => {
    const factor = Number(band.value) * (alone.checked ? 0.75 : 1);
    for (const el of section.querySelectorAll("[data-band-d]")) {
      const yearly = Number(el.dataset.bandD) * factor;
      el.textContent = el.dataset.per === "week" ? money(yearly / 52, yearly / 52 < 10) : money(yearly);
    }
    const label = band.options[band.selectedIndex].text;
    note.textContent = `(${label}${alone.checked ? ", with the single person discount" : ""})`;
  };
  band.addEventListener("change", update);
  alone.addEventListener("change", update);
}

// Arriving from a postcode search: start on the most common band nearby
for (const section of document.querySelectorAll('[data-module="app-ctax"]')) {
  const band = new URLSearchParams(window.location.search).get("band");
  const select = section.querySelector("#ctax-band");
  const option = [...select.options].find((o) => o.text === `Band ${band}`);
  if (option) {
    select.value = option.value;
    select.dispatchEvent(new Event("change"));
    const note = section.querySelector(".app-ctax__suggested");
    note.innerHTML = `<strong>Band ${band}</strong> is the most common band for homes near your postcode, so we've started there. <a class="govuk-link" href="https://www.gov.uk/council-tax-bands">Check your own band on GOV.UK</a>.`;
    note.hidden = false;
  }
}

// "Compared with": go straight to the group's page when it changes
for (const form of document.querySelectorAll('[data-module="app-group"]')) {
  const button = form.querySelector(".app-group__button");
  if (button) button.hidden = true;
  form.elements.group.addEventListener("change", () => {
    const slug = form.elements.council.value;
    const group = form.elements.group.value;
    const other = new URLSearchParams(window.location.search).get("with");
    const query = other ? `?with=${encodeURIComponent(other)}` : "";
    window.location.href = (group === "england" ? `/${slug}/` : `/${slug}/${group}/`) + query;
  });
}

// ---------------------------------------------------------------------------
// Charts: name the councils on the "Across England" lines, and draw a second
// council for comparison. Every council's figures are in /data/site.json.

const strips = document.querySelectorAll(".app-strip");
let siteData = null;
const loadSite = () => (siteData ??= fetch("/data/site.json").then((r) => r.json()));

const format = (value, unit) => {
  if (value === null || value === undefined) return "No figure";
  if (unit === "%") return `${value.toFixed(1)}%`;
  if (unit === "£") return (value < 0 ? "−£" : "£") + Math.round(Math.abs(value)).toLocaleString("en-GB");
  return String(Number(value.toFixed(1)));
};
const ordinal = (n) => {
  const s = n % 100 >= 10 && n % 100 <= 20 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[n % 10] || "th";
  return `${n}${s}`;
};

// Where each council sits on one strip: the same sums as web/model.py strip()
function positions(site, strip) {
  const measure = strip.dataset.measure;
  const spend = strip.dataset.spend;
  const better = measure ? site.measures[measure].better : "higher";
  const unit = measure ? site.measures[measure].unit : "£";
  const get = (c) => (measure ? c.values[measure] : c.spend[spend]);
  const placed = site.councils.filter((c) => get(c) !== undefined && get(c) !== null);
  const values = placed.map(get);
  const low = Math.min(...values);
  const span = Math.max(...values) - low || 1;
  const sorted = [...values].sort((a, b) => (better === "higher" ? b - a : a - b));
  return placed
    .map((c) => {
      let share = (get(c) - low) / span;
      if (better === "lower") share = 1 - share;
      const rank = sorted.findIndex((v) => v === get(c)) + 1;
      return { council: c, value: get(c), left: 2 + share * 96, text: `${c.name}: ${format(get(c), unit)}`,
               rank: measure ? `${ordinal(rank)} of ${values.length}` : "" };
    })
    .sort((a, b) => a.left - b.left);
}

const svgNS = "http://www.w3.org/2000/svg";
const me = document.querySelector('[data-module="app-with"]')?.closest("main")
  ? document.querySelector('input[name="council"]')?.value
  : null;

function tooltipFor(strip) {
  const cell = strip.parentElement;
  let tip = cell.querySelector(".app-tip");
  if (!tip) {
    tip = document.createElement("div");
    tip.className = "app-tip";
    tip.setAttribute("role", "status");
    tip.hidden = true;
    cell.style.position = "relative";
    cell.append(tip);
  }
  let ring = strip.querySelector(".app-strip__hover");
  if (!ring) {
    ring = document.createElementNS(svgNS, "circle");
    ring.setAttribute("class", "app-strip__hover");
    ring.setAttribute("cy", "13");
    ring.setAttribute("r", "7");
    strip.append(ring);
  }
  return { tip, ring };
}

function show(strip, point) {
  const { tip, ring } = tooltipFor(strip);
  ring.setAttribute("cx", `${point.left}%`);
  ring.style.display = "";
  tip.textContent = point.rank ? `${point.text}, ${point.rank}` : point.text;
  tip.style.left = `${Math.min(Math.max(point.left, 15), 85)}%`;
  tip.hidden = false;
}

function hide(strip) {
  const tip = strip.parentElement.querySelector(".app-tip");
  const ring = strip.querySelector(".app-strip__hover");
  if (tip) tip.hidden = true;
  if (ring) ring.style.display = "none";
}

for (const strip of strips) {
  strip.setAttribute("tabindex", "0");
  strip.setAttribute("focusable", "true");
  strip.setAttribute("aria-description", "Use the left and right arrow keys to go through each council, and Enter to open one.");
  let points = null;
  let index = -1;
  const ready = async () => (points ??= positions(await loadSite(), strip));
  const nearest = (pct) =>
    points.reduce((best, p, i) => (Math.abs(p.left - pct) < Math.abs(points[best].left - pct) ? i : best), 0);

  strip.addEventListener("pointermove", async (event) => {
    await ready();
    const box = strip.getBoundingClientRect();
    index = nearest(((event.clientX - box.left) / box.width) * 100);
    show(strip, points[index]);
  });
  strip.addEventListener("pointerleave", () => hide(strip));
  strip.addEventListener("click", async (event) => {
    await ready();
    const box = strip.getBoundingClientRect();
    index = nearest(((event.clientX - box.left) / box.width) * 100);
    window.location.href = `/${points[index].council.slug}/`;
  });
  strip.addEventListener("focus", async () => {
    await ready();
    index = Math.max(0, points.findIndex((p) => p.council.slug === me));
    show(strip, points[index]);
  });
  strip.addEventListener("blur", () => hide(strip));
  strip.addEventListener("keydown", async (event) => {
    await ready();
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      index = Math.min(points.length - 1, Math.max(0, index + (event.key === "ArrowRight" ? 1 : -1)));
      show(strip, points[index]);
    } else if (event.key === "Enter" && index >= 0) {
      window.location.href = `/${points[index].council.slug}/`;
    } else if (event.key === "Escape") {
      hide(strip);
    }
  });
}

// A second council on every chart
for (const form of document.querySelectorAll('[data-module="app-with"]')) {
  form.hidden = false;
  const select = form.elements.with;
  const summary = form.querySelector(".app-with__summary");

  const render = async () => {
    const slug = select.value;
    const url = new URL(window.location.href);
    if (slug) url.searchParams.set("with", slug);
    else url.searchParams.delete("with");
    history.replaceState(null, "", url);
    for (const el of document.querySelectorAll(".app-strip__with, .app-chart__line--with, .app-with-key")) el.remove();
    for (const el of document.querySelectorAll(".app-area__with")) el.hidden = true;
    summary.textContent = "";
    if (!slug) return;

    const site = await loadSite();
    const mine = site.councils.find((c) => c.slug === me);
    const other = site.councils.find((c) => c.slug === slug);
    if (!mine || !other) return;

    for (const strip of strips) {
      const point = positions(site, strip).find((p) => p.council.slug === slug);
      if (!point) continue;
      const dot = document.createElementNS(svgNS, "circle");
      dot.setAttribute("class", "app-strip__with");
      dot.setAttribute("cx", `${point.left}%`);
      dot.setAttribute("cy", "13");
      dot.setAttribute("r", "7");
      strip.querySelector(".app-strip__me").before(dot);
    }

    let better = 0, worse = 0, same = 0;
    for (const el of document.querySelectorAll(".app-area__with")) {
      const m = site.measures[el.dataset.measure];
      const a = mine.values[el.dataset.measure];
      const b = other.values[el.dataset.measure];
      el.hidden = false;
      if (b === undefined || b === null) {
        el.textContent = `${other.name}: no figure`;
        continue;
      }
      const verdict = a === b ? "same" : (a > b) === (m.better === "higher") ? "better" : "worse";
      if (verdict === "better") better += 1;
      else if (verdict === "worse") worse += 1;
      else same += 1;
      const words = { better: `${mine.name} does better`, worse: `${mine.name} does worse`, same: "the same" };
      el.textContent = `${other.name}: ${format(b, m.unit)} (${words[verdict]})`;
      el.dataset.verdict = verdict;
    }
    summary.textContent = `${mine.name} does better than ${other.name} on ${better} of ${better + worse + same} measures they both have figures for, and worse on ${worse}.`;

    for (const svg of document.querySelectorAll("svg[data-trend]")) {
      const series = other.trends[svg.dataset.trend] || {};
      const periods = svg.dataset.periods.split(",");
      const [left, right, top, padT, plotH] = ["left", "right", "top", "padT", "plotH"].map((k) => Number(svg.dataset[k]));
      const x = (i) => left + (periods.length > 1 ? i / (periods.length - 1) : 0) * (right - left);
      const y = (v) => padT + (1 - Math.min(v, top) / top) * plotH;
      const points = periods.map((p, i) => (series[p] === undefined ? null : [x(i), y(series[p])])).filter(Boolean);
      if (!points.length) continue;
      const path = document.createElementNS(svgNS, "path");
      path.setAttribute("class", "app-chart__line app-chart__line--with");
      path.setAttribute("d", points.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join(" "));
      svg.append(path);
      const key = svg.parentElement.querySelector("[data-trend-key]");
      const last = [...periods].reverse().find((p) => series[p] !== undefined);
      const unit = svg.dataset.trend === "ehcp_20wk" || svg.dataset.trend === "recycling" ? "%" : "";
      const li = document.createElement("li");
      li.className = "app-with-key";
      li.innerHTML = '<span class="app-chart__swatch app-chart__line--with"></span>';
      li.append(`${other.name}: ${format(series[last], unit)}`);
      key.append(li);
    }
  };

  select.addEventListener("change", render);
  const initial = new URLSearchParams(window.location.search).get("with");
  if (initial && [...select.options].some((o) => o.value === initial)) {
    select.value = initial;
    render();
  }
}

// Measure pages: filter the map and table by region and type of council
for (const explore of document.querySelectorAll('[data-module="app-explore"]')) {
  const filters = explore.querySelector(".app-explore__filters");
  filters.hidden = false;
  const region = explore.querySelector("#filter-region");
  const type = explore.querySelector("#filter-type");
  const apply = () => {
    const keep = (el) => (!region.value || el.dataset.region === region.value) && (!type.value || el.dataset.type === type.value);
    for (const row of explore.querySelectorAll("tr[data-region]")) row.hidden = !keep(row);
    for (const hex of explore.querySelectorAll("a[data-region]")) hex.classList.toggle("app-hex--dim", !keep(hex));
  };
  region.addEventListener("change", apply);
  type.addEventListener("change", apply);
}
