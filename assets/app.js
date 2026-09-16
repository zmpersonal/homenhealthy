document.addEventListener("DOMContentLoaded", () => {
  const filter = document.querySelector("[data-city-search]");
  if (filter) {
    filter.addEventListener("input", () => {
      const query = filter.value.trim().toLowerCase();
      document.querySelectorAll("[data-city-row]").forEach((row) => {
        row.hidden = !row.innerText.toLowerCase().includes(query);
      });
    });
  }

  const lookup = document.querySelector("[data-home-lookup]");
  if (lookup) {
    lookup.addEventListener("submit", (event) => {
      event.preventDefault();
      const query = lookup.querySelector("input").value.trim().toLowerCase();
      if (!query) return;
      const cities = [...document.querySelectorAll("[data-lookup-city]")];
      const exact = cities.find((city) => city.dataset.lookupCity === query);
      const partial = cities.find((city) => city.dataset.lookupCity.includes(query));
      window.location.href = (exact || partial)?.href || "/cities/";
    });
  }

  document.querySelectorAll("[data-copy-text]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(button.dataset.copyText);
        const original = button.textContent;
        button.textContent = "Copied";
        setTimeout(() => { button.textContent = original; }, 1600);
      } catch {
        button.textContent = "Select and copy the citation above";
      }
    });
  });
});
