// The council and postcode search.
//   /go?council=lewisham  -> /lewisham/
//   /go?postcode=SE14 6AF -> that postcode's council page, with the calculator
//                            starting on the most common council tax band in
//                            the neighbourhood (postcodes.io gives both codes)
// The postcode is never put in the address it redirects to.
export async function onRequestGet({ request, env }) {
  const url = new URL(request.url);
  const to = (path) => Response.redirect(new URL(path, url.origin), 302);

  const slug = url.searchParams.get("council") || "";
  const group = url.searchParams.get("group") || "";
  if (/^[a-z0-9-]+$/.test(slug)) {
    return to(["region", "type", "similar"].includes(group) ? `/${slug}/${group}/` : `/${slug}/`);
  }

  const postcode = (url.searchParams.get("postcode") || "").replace(/[^A-Za-z0-9]/g, "").toUpperCase();
  if (!postcode) return to("/");
  if (postcode.length < 5 || postcode.length > 7) return to("/postcode-not-found/");

  const found = await fetch(`https://api.postcodes.io/postcodes/${postcode}`);
  if (!found.ok) return to("/postcode-not-found/");
  const { result } = await found.json();
  const district = result?.codes?.admin_district;
  const area = result?.codes?.lsoa;

  const asset = async (path) => {
    const response = await env.ASSETS.fetch(new URL(path, url.origin));
    return response.ok ? response.json() : {};
  };
  const pages = await asset("/data/councils-by-code.json");
  const page = pages[district];
  if (!page) {
    if (result?.country === "England") return to("/not-covered/");
    return to("/not-covered/?outside=1");
  }
  let band = "";
  if (/^E01\d{6}$/.test(area || "")) {
    band = (await asset(`/data/bands/${area.slice(0, 6)}.json`))[area] || "";
  }
  return to(band ? `/${page}/?band=${band}#council-tax` : `/${page}/#council-tax`);
}
