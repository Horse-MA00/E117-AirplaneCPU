// Keep travel dates as calendar dates, independent of the viewer's time zone.
// The local fallback avoids a runtime CDN dependency and respects the server CSP.
const temporal = globalThis.Temporal ?? (await import('./vendor/temporal.js')).Temporal;

export const regions = {
  JP: { name: 'Japan', airports: ['FUK', 'KIX', 'NRT', 'HND', 'NGO', 'OKA'] },
  KR: { name: 'South Korea', airports: ['ICN', 'PUS'] },
  TW: { name: 'Taiwan', airports: ['TPE', 'KHH'] },
  TH: { name: 'Thailand', airports: ['BKK', 'DMK', 'CNX'] },
  VN: { name: 'Vietnam', airports: ['DAD', 'HAN', 'SGN'] },
  PH: { name: 'Philippines', airports: ['MNL', 'CEB'] },
  SG: { name: 'Singapore', airports: ['SIN'] },
  HK: { name: 'Hong Kong', airports: ['HKG'] },
};

export function inRegion(airport, region) {
  return !region || Boolean(regions[region]?.airports.includes(airport));
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
  return (!filters.origin || flight.origin === filters.origin)
    && inRegion(flight.destination, filters.region)
    && (!filters.destination || flight.destination === filters.destination)
    && (!filters.from || temporal.PlainDate.compare(date, filters.from) >= 0)
    && (!filters.to || temporal.PlainDate.compare(date, filters.to) <= 0);
}
