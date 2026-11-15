import { regions } from './airports.js';
export { regions } from './airports.js';

// Keep travel dates as calendar dates, independent of the viewer's time zone.
// The local fallback avoids a runtime CDN dependency and respects the server CSP.
const temporal = globalThis.Temporal ?? (await import('./vendor/temporal.js')).Temporal;

export function inRegion(airport, region) {
  return !region || Boolean(regions[region]?.airports.includes(airport));
}

// A place is '' (anywhere), an airport code, or 'region:XX' for every airport
// in a country / region. Origin and destination use the same picker.
export const REGION_PREFIX = 'region:';
export function placeRegion(place) { return String(place || '').startsWith(REGION_PREFIX) ? place.slice(REGION_PREFIX.length) : ''; }
export function matchesPlace(airport, place) {
  if (!place) return true;
  const region = placeRegion(place);
  return region ? inRegion(airport, region) : airport === place;
}

export function nextMonthRange(now = Date.now()) {
  const today = temporal.Instant.fromEpochMilliseconds(now).toZonedDateTimeISO('Asia/Hong_Kong').toPlainDate();
  const first = today.with({ day: 1 }).add({ months: 1 });
  return { from: first.toString(), to: first.with({ day: first.daysInMonth }).toString() };
}

export function dateLabel(value, options = { day: 'numeric', month: 'short', year: 'numeric' }) {
  return temporal.PlainDate.from(value).toLocaleString('en-GB', options);
}

export function dateParts(value) {
  const date = temporal.PlainDate.from(value);
  return { day: date.day, year: date.year };
}

export function reversedRange(from, to) {
  return Boolean(from && to && temporal.PlainDate.compare(from, to) > 0);
}

export function matchesSearch(flight, filters) {
  const date = temporal.PlainDate.from(flight.departure_date);
  return matchesPlace(flight.origin, filters.origin)
    && matchesPlace(flight.destination, filters.destination)
    && (!filters.from || temporal.PlainDate.compare(date, filters.from) >= 0)
    && (!filters.to || temporal.PlainDate.compare(date, filters.to) <= 0);
}
