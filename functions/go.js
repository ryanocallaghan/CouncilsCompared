// The council chooser without JavaScript: /go?council=lewisham -> /lewisham/
export function onRequestGet({ request }) {
  const url = new URL(request.url);
  const slug = url.searchParams.get("council") || "";
  const target = /^[a-z0-9-]+$/.test(slug) ? `/${slug}/` : "/";
  return Response.redirect(new URL(target, url.origin), 302);
}
