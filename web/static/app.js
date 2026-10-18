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
