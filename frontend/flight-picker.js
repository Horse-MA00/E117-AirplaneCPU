import { airports, catalogAirportCodes, regions, airportLabel } from './members/airports.js';

const regionPrefix = 'region:';
const otherAirports = 'Other published airports';
const shortDate = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC',
});

function airportCode(value) {
  const code = typeof value === 'string' ? value.trim().toUpperCase() : '';
  return /^[A-Z]{3}$/.test(code) ? code : '';
}

function option(document, label, value) {
  const element = document.createElement('option');
  element.textContent = label;
  element.value = value;
  return element;
}

/** Both pickers use the whole catalog plus BOTH endpoints of all supplied flights.
 * Pass the unfiltered flight catalog, not a demand or opposite-place subset.
 */
export function populatePlaces(select, flights, selected = select.value) {
  const document = select.ownerDocument;
  const codes = new Set(catalogAirportCodes);
  for (const flight of flights || []) {
    for (const endpoint of [flight?.origin, flight?.destination]) {
      const code = airportCode(endpoint);
      if (code) codes.add(code);
    }
  }
  const groups = new Map();
  for (const code of [...codes].sort((a, b) => airportLabel(a).localeCompare(airportLabel(b), 'en'))) {
    const region = airports[code]?.region || '';
    if (!groups.has(region)) groups.set(region, []);
    groups.get(region).push(code);
  }
  const groupName = region => regions[region]?.name || otherAirports;
  const order = [...groups.keys()].sort((a, b) => {
    if (a === b) return 0;
    if (a === 'HK' || !b) return -1;
    if (b === 'HK' || !a) return 1;
    return groupName(a).localeCompare(groupName(b), 'en');
  });
  const children = order.map(region => {
    const group = document.createElement('optgroup');
    group.label = groupName(region);
    // A one-airport region would list the same choice twice ("Entire Hong Kong" / "Hong Kong (HKG)").
    if (region && groups.get(region).length > 1) group.append(option(document, `Entire ${groupName(region)}`, `${regionPrefix}${region}`));
    group.append(...groups.get(region).map(code => option(document, airportLabel(code), code)));
    return group;
  });
  select.replaceChildren(option(document, 'Anywhere', ''), ...children);
  if (typeof selected === 'string' && selected.startsWith(regionPrefix) && groups.get(selected.slice(regionPrefix.length))?.length === 1) {
    selected = groups.get(selected.slice(regionPrefix.length))[0];
  }
  select.value = [...select.options].some(item => item.value === selected) ? selected : '';
}

function matchesPlace(code, place) {
  if (!place) return true;
  if (place.startsWith(regionPrefix)) {
    const region = place.slice(regionPrefix.length);
    return Boolean(region && airports[airportCode(code)]?.region === region);
  }
  return Boolean(airportCode(place) && airportCode(code) === airportCode(place));
}

export function matchesFlightPlaces(flight, from, to) {
  return matchesPlace(flight?.origin, from) && matchesPlace(flight?.destination, to);
}

/** Set a selected flight after populating both controls from the full catalog. */
export function setFlightPlaces(fromSelect, toSelect, flight) {
  fromSelect.value = airportCode(flight?.origin);
  toSelect.value = airportCode(flight?.destination);
}

function departureLabel(flight) {
  // Interpret the calendar day written in the source, never the viewer's zone.
  const value = String(flight?.departure_date || flight?.departure_at || '').slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return 'Date unavailable';
  const date = new Date(`${value}T00:00:00Z`);
  if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, 10) !== value) return 'Date unavailable';
  return shortDate.format(date);
}

export function flightOptionLabel(flight, { includeRoute = false } = {}) {
  const parts = [departureLabel(flight)];
  if (includeRoute) parts.push(`${flight?.origin || '—'} → ${flight?.destination || '—'}`);
  parts.push(String(flight?.flight_id || 'Flight identifier unavailable'));
  return parts.join(' · ');
}
