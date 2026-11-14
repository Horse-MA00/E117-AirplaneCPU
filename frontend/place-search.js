/** Place search for the From / To pickers (flight-picker.js fills the <select>).
 *  A magnifier in the field opens a filter box over the select's own options, so it always offers
 *  exactly what the select offers: airports ("Tokyo Haneda (HND)"), whole regions ("Entire Japan")
 *  and Anywhere. Matches the option text, the code and the region name ("hnd", "tokyo", "japan").
 *  Choosing a result sets the select and fires its normal change event, so page logic is unchanged. */
const ICON = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/></svg>';

export function attachPlaceSearch(select, { label = 'Search places' } = {}) {
  const field = select.closest('.ctx-field'); if (!field || field.querySelector('.ctx-search-btn')) return;
  field.classList.add('has-search');
  const button = document.createElement('button');
  button.type = 'button'; button.className = 'ctx-search-btn'; button.innerHTML = ICON;
  button.setAttribute('aria-label', label); button.setAttribute('aria-expanded', 'false');
  const panel = document.createElement('div'); panel.className = 'place-search'; panel.hidden = true;
  const input = document.createElement('input');
  input.type = 'search'; input.placeholder = 'City, airport code or region'; input.autocomplete = 'off';
  input.setAttribute('aria-label', label);
  const list = document.createElement('ul'); list.className = 'place-search-list'; list.setAttribute('role', 'listbox');
  list.id = `${select.id}-search-results`; input.setAttribute('aria-controls', list.id);
  const empty = document.createElement('p'); empty.className = 'place-search-empty'; empty.textContent = 'No matching places.'; empty.hidden = true;
  panel.append(input, list, empty); field.append(button, panel);
  let active = 0, shown = [];

  function entries() {
    return [...select.options].map((o) => ({ value: o.value, text: o.textContent, group: o.parentElement?.tagName === 'OPTGROUP' ? o.parentElement.label : '' }));
  }
  function render() {
    const query = input.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
    shown = entries().filter((e) => { const hay = `${e.text} ${e.value} ${e.group}`.toLowerCase(); return query.every((q) => hay.includes(q)); }).slice(0, 60);
    active = Math.min(active, Math.max(0, shown.length - 1));
    list.replaceChildren(...shown.map((e, i) => {
      const li = document.createElement('li'); li.setAttribute('role', 'option'); li.id = `${list.id}-${i}`;
      li.setAttribute('aria-selected', String(i === active)); if (e.value === select.value) li.classList.add('current');
      const name = document.createElement('strong'); name.textContent = e.text;
      li.append(name);
      if (e.group) { const group = document.createElement('span'); group.textContent = e.group; li.append(group); }
      li.addEventListener('mousedown', (event) => { event.preventDefault(); choose(e.value); });
      return li;
    }));
    empty.hidden = shown.length > 0;
    input.setAttribute('aria-activedescendant', shown.length ? `${list.id}-${active}` : '');
    // Keep the active row visible by scrolling the list only (scrollIntoView could shift the whole page).
    const row = list.querySelector('[aria-selected=true]');
    if (row) {
      if (row.offsetTop < list.scrollTop) list.scrollTop = row.offsetTop;
      else if (row.offsetTop + row.offsetHeight > list.scrollTop + list.clientHeight) list.scrollTop = row.offsetTop + row.offsetHeight - list.clientHeight;
    }
  }
  function open() {
    if (select.disabled) return;
    panel.classList.remove('align-right'); panel.hidden = false;
    // Open leftwards when the panel would run past the window edge (rects already include the Admin zoom).
    if (panel.getBoundingClientRect().right > document.documentElement.clientWidth - 8) panel.classList.add('align-right');
    button.setAttribute('aria-expanded', 'true'); input.value = ''; active = 0; render(); input.focus({ preventScroll: true });
  }
  function close(returnFocus) { panel.hidden = true; button.setAttribute('aria-expanded', 'false'); if (returnFocus) button.focus(); }
  function choose(value) {
    close(true);
    if (value !== select.value) { select.value = value; select.dispatchEvent(new Event('change', { bubbles: true })); }
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
