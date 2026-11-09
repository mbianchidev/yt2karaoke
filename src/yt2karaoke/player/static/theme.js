(() => {
  "use strict";

  const storageKey = "yt2karaoke-theme";
  const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
  let preference = readPreference();

  function readPreference() {
    let stored;
    try {
      stored = localStorage.getItem(storageKey);
    } catch (error) {
      console.warn("Karaoke studio: Could not read the theme preference. Following the system theme.", error);
      return "system";
    }
    if (stored === null) return "system";
    if (["system", "light", "dark"].includes(stored)) return stored;
    console.warn("Karaoke studio: Ignoring an invalid theme preference. Following the system theme.");
    return "system";
  }

  function applyTheme() {
    const theme = preference === "system" ? (systemTheme.matches ? "dark" : "light") : preference;
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]').content = theme === "dark" ? "#171722" : "#f5f5fa";
    const select = document.getElementById("theme-select");
    if (select) select.value = preference;
  }

  applyTheme();
  systemTheme.addEventListener("change", () => {
    if (preference === "system") applyTheme();
  });
  window.addEventListener("storage", (event) => {
    if (event.key !== storageKey && event.key !== null) return;
    preference = readPreference();
    applyTheme();
  });
  document.addEventListener("DOMContentLoaded", () => {
    const select = document.getElementById("theme-select");
    applyTheme();
    select.disabled = false;
    select.addEventListener("change", () => {
      preference = select.value;
      applyTheme();
      try {
        localStorage.setItem(storageKey, preference);
      } catch (error) {
        console.warn("Karaoke studio: Could not save the theme preference.", error);
        const notice = document.getElementById("error-notice");
        notice.querySelector("span").textContent = "Theme changed for this page, but your browser could not save it.";
        notice.hidden = false;
      }
    });
  });
})();
