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
    window.location.href = group === "england" ? `/${slug}/` : `/${slug}/${group}/`;
  });
}
