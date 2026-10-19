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
