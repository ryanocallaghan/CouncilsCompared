// The council search.
//   /go?q=SE14 6AF        -> that postcode's council page, with the calculator
//                            starting on the most common council tax band in
//                            the neighbourhood (postcodes.io gives both codes)
//   /go?q=lewisham        -> /lewisham/, or the closest names if it's not exact
//   /go?council=lewisham  -> /lewisham/ (and &group=region and so on)
//   /go?postcode=SE14 6AF -> as q, for links made before q
// The postcode is never put in the address it redirects to.

const POSTCODE = /^[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2}$/;
const OUTCODE = /^[A-Z]{1,2}\d[A-Z\d]?$/; // the first half of a postcode
const FILLER = / (london borough of|royal borough of|city of|county of|borough of|metropolitan borough|metropolitan district|city|borough|county|district|council|the) /g;

// "London Borough of Lewisham Council" and "lewisham" both -> "lewisham"
export function normalise(name) {
  let text = ` ${name.toLowerCase().replace(/&/g, " and ").replace(/[^a-z0-9]+/g, " ")} `;
  // Twice, as neighbouring words share the space between them
  text = text.replace(FILLER, " ").replace(FILLER, " ");
  return text.replace(/\s+/g, " ").trim();
}

function distance(a, b) {
  let row = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const next = [i];
    for (let j = 1; j <= b.length; j++) {
      next[j] = Math.min(row[j] + 1, next[j - 1] + 1, row[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    row = next;
  }
  return row[b.length];
}

// What a name search finds: {slug} for one council, {suggestions} for several
// close ones, or {} for none. names is [[slug, name, ONS name]].
export function match(query, names) {
  const q = normalise(query);
  if (!q) return {};
  const councils = names.map(([slug, name, ons]) => ({ slug, name, keys: [normalise(name), normalise(ons)] }));
  const pick = (found) => (found.length === 1 ? { slug: found[0].slug } : { suggestions: found.slice(0, 8) });
  const exact = councils.filter((c) => c.keys.includes(q));
  if (exact.length) return pick(exact);
  // Whole words first, so "hull" is Kingston upon Hull rather than Solihull too
  const words = councils.filter((c) => c.keys.some((k) => ` ${k} `.includes(` ${q} `)));
  if (words.length) return pick(words);
  const containing = councils.filter((c) => c.keys.some((k) => k.includes(q)));
  if (containing.length) return pick(containing);
  // Typing slips: one letter wrong in a short name, more in a long one
  const near = councils
    .map((c) => ({ ...c, d: Math.min(...c.keys.map((k) => distance(q, k))) }))
    .filter((c) => c.d <= Math.max(1, Math.floor(q.length / 4)))
    .sort((a, b) => a.d - b.d);
  return near.length ? { suggestions: near.slice(0, 3) } : {};
}

const escape = (text) => text.replace(/[&<>"']/g, (ch) => `&#${ch.charCodeAt(0)};`);

export async function onRequestGet({ request, env }) {
  const url = new URL(request.url);
  const to = (path) => Response.redirect(new URL(path, url.origin), 302);
  const asset = async (path) => env.ASSETS.fetch(new URL(path, url.origin));
  const json = async (path) => {
    const response = await asset(path);
    return response.ok ? response.json() : {};
  };

  const slug = url.searchParams.get("council") || "";
  const group = url.searchParams.get("group") || "";
  if (/^[a-z0-9-]+$/.test(slug)) {
    return to(["region", "type", "similar"].includes(group) ? `/${slug}/${group}/` : `/${slug}/`);
  }

  const query = (url.searchParams.get("q") || url.searchParams.get("postcode") || "").trim();
  if (!query) return to("/");
  const postcode = query.replace(/[^A-Za-z0-9]/g, "").toUpperCase();

  if (OUTCODE.test(postcode)) return to("/postcode-not-found/");
  if (!POSTCODE.test(postcode)) {
    const found = match(query, await json("/data/council-names.json"));
    if (found.slug) return to(`/${found.slug}/`);
    const page = await asset("/council-not-found/");
    const suggestions = found.suggestions
      ? `<p class="govuk-body">No council is called “${escape(query)}”. Did you mean:</p>\n<ul class="govuk-list">` +
        found.suggestions.map((c) => `<li><a class="govuk-link" href="/${c.slug}/">${escape(c.name)}</a></li>`).join("") +
        "</ul>"
      : `<p class="govuk-body">No council is called “${escape(query)}”.</p>`;
    const html = (await page.text()).replace("<!--suggestions-->", suggestions);
    return new Response(html, { status: 404, headers: { "Content-Type": "text/html; charset=utf-8" } });
  }

  const found = await fetch(`https://api.postcodes.io/postcodes/${postcode}`);
  if (!found.ok) return to("/postcode-not-found/");
  const { result } = await found.json();
  const district = result?.codes?.admin_district;
  const area = result?.codes?.lsoa;

  const pages = await json("/data/councils-by-code.json");
  const page = pages[district];
  if (!page) {
    if (result?.country === "England") return to("/not-covered/");
    return to("/not-covered/?outside=1");
  }
  let band = "";
  if (/^E01\d{6}$/.test(area || "")) {
    band = (await json(`/data/bands/${area.slice(0, 6)}.json`))[area] || "";
  }
  return to(band ? `/${page}/?band=${band}` : `/${page}/`);
}
