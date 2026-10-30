// Runs before the first paint (blocking <script> in index.html) so dark mode never flashes light.
// A separate same-origin file, not inline, so it keeps working under a strict CSP (default-src 'self').
// Same storage key and logic as src/lib/theme.ts: saved choice, else the device setting.
(function () {
  var theme = null;
  try {
    theme = window.localStorage.getItem("secondlook.theme");
  } catch (e) {
    // storage blocked: fall back to the device setting
  }
  if (theme !== "light" && theme !== "dark") {
    theme = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  document.documentElement.setAttribute("data-theme", theme);
})();
