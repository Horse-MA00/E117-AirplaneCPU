/** Route search: a magnifier in a route field opens a filter box over that field's <select>.
 *  Matches airport codes and city names ("hnd", "tokyo", "hkg fuk"). Choosing a result sets the
 *  select and fires its normal change event, so page logic is unchanged. */
const ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>';
let names = null;
async function airportNames() {
  if (names) return names;
  try { names = (await import('/members/airports.js')).airportNames || {}; } catch { names = {}; }
  return names;
}
const parts = (value) => String(value).split(/\s*(?:→|->|-)\s*/);

export function attachRouteSearch(select, { label = 'Search routes' } = {}) {
  const field = select.closest('.ctx-field'); if (!field) return;
  field.classList.add('has-search');
  const button = document.createElement('button');
  button.type = 'button'; button.className = 'ctx-search-btn'; button.innerHTML = ICON;
  button.setAttribute('aria-label', label); button.setAttribute('aria-expanded', 'false');
  const panel = document.createElement('div'); panel.className = 'route-search'; panel.hidden = true;
  const input = document.createElement('input');
  input.type = 'search'; input.placeholder = 'Airport code or city, e.g. HND or Tokyo'; input.autocomplete = 'off';
  input.setAttribute('aria-label', 'Search routes by airport code or city');
  const list = document.createElement('ul'); list.className = 'route-search-list'; list.setAttribute('role', 'listbox');
  list.id = `${select.id}-search-results`; input.setAttribute('aria-controls', list.id);
  const empty = document.createElement('p'); empty.className = 'route-search-empty'; empty.textContent = 'No matching routes.'; empty.hidden = true;
  panel.append(input, list, empty); field.append(button, panel);
  let active = 0, shown = [];

  function render() {
    const query = input.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const routes = [...select.options].filter((o) => o.value).map((o) => {
      const [from, to] = parts(o.value), n = names || {};
      return { value: o.value, from, to, text: `${n[from] || from} → ${n[to] || to}` };
    });
    shown = routes.filter((r) => { const hay = `${r.from} ${r.to} ${r.from}${r.to} ${r.text}`.toLowerCase(); return query.every((q) => hay.includes(q)); }).slice(0, 40);
    active = Math.min(active, Math.max(0, shown.length - 1));
    list.replaceChildren(...shown.map((r, i) => {
      const li = document.createElement('li'); li.setAttribute('role', 'option'); li.id = `${list.id}-${i}`;
      li.setAttribute('aria-selected', String(i === active)); if (r.value === select.value) li.classList.add('current');
      const code = document.createElement('strong'); code.textContent = `${r.from} → ${r.to}`;
      const city = document.createElement('span'); city.textContent = r.text;
      li.append(code, city);
      li.addEventListener('mousedown', (event) => { event.preventDefault(); choose(r.value); });
      return li;
    }));
    empty.hidden = shown.length > 0;
    input.setAttribute('aria-activedescendant', shown.length ? `${list.id}-${active}` : '');
    list.querySelector('[aria-selected=true]')?.scrollIntoView({ block: 'nearest' });
  }
  function open() {
    if (select.disabled) return;
    panel.hidden = false; button.setAttribute('aria-expanded', 'true'); input.value = ''; active = 0; render(); input.focus();
    airportNames().then(() => { if (!panel.hidden) render(); });
  }
  function close(returnFocus) { panel.hidden = true; button.setAttribute('aria-expanded', 'false'); if (returnFocus) button.focus(); }
  function choose(value) {
    close(true);
    if (value && value !== select.value) { select.value = value; select.dispatchEvent(new Event('change', { bubbles: true })); }
  }
  button.addEventListener('click', () => (panel.hidden ? open() : close(true)));
  input.addEventListener('input', () => { active = 0; render(); });
  input.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); if (shown.length) { active = (active + (event.key === 'ArrowDown' ? 1 : shown.length - 1)) % shown.length; render(); } }
    else if (event.key === 'Enter') { event.preventDefault(); if (shown[active]) choose(shown[active].value); }
    else if (event.key === 'Escape') { event.preventDefault(); close(true); }
  });
  document.addEventListener('mousedown', (event) => { if (!panel.hidden && !field.contains(event.target)) close(false); });
}
