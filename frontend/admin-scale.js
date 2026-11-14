/* Admin is laid out for a 1920px-wide screen. On other widths the whole page is scaled with CSS zoom,
   so it looks the same on a 14" laptop (≈1512px), a 1920 projector or a 4K display at 100% browser zoom,
   and the member site (same origin, same browser zoom) stays right too. Below 1360px the normal
   responsive layout takes over. Runs before first paint; see docs/FRONTEND_UI.md §4.4. */
(function () {
  var BASE = 1920,
    MIN = 0.7,
    MAX = 1.33,
    FLOOR = 1360,
    root = document.documentElement;
  function apply() {
    var w = window.innerWidth;
    var z = w < FLOOR ? 1 : Math.min(MAX, Math.max(MIN, w / BASE));
    z = Math.round(z * 1000) / 1000;
    root.style.zoom = z === 1 ? '' : String(z);
    root.style.setProperty('--zoom', String(z));
  }
  apply();
  window.addEventListener('resize', apply);
})();
