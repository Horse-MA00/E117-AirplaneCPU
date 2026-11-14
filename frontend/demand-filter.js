// Catalogue labels come from the backend's verified, fixed D28 forecast index.
// Never infer demand from the synthetic scenario name or final observed load.
export const demandLabels = Object.freeze({
  all: 'All demand',
  low: 'Low demand',
  medium: 'Medium demand',
  high: 'High demand',
  unknown: 'Unclassified',
});

export function demandBand(flight) {
  return ['low', 'medium', 'high'].includes(flight?.demand_band) ? flight.demand_band : 'unknown';
}

export function matchesDemand(flight, selected) {
  return selected === 'all' || demandBand(flight) === selected;
}

export function populateDemandFilter(select, flights) {
  const selected = select.value || 'all';
  const counts = { all: flights.length, low: 0, medium: 0, high: 0, unknown: 0 };
  for (const flight of flights) counts[demandBand(flight)]++;
  select.replaceChildren(
    ...Object.entries(demandLabels).map(
      ([value, label]) => new Option(`${label} (${counts[value].toLocaleString('en-HK')})`, value),
    ),
  );
  select.value = selected in counts ? selected : 'all';
  select.disabled = false;
  return counts;
}

export function demandDescription(flight) {
  const band = demandBand(flight),
    rate = flight?.demand_expected_load_rate;
  return band === 'unknown'
    ? 'Unclassified demand'
    : `${demandLabels[band]}${Number.isFinite(rate) ? ` · D28 expected occupancy ${(rate * 100).toFixed(1)}%` : ''}`;
}
