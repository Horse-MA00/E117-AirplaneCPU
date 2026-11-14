/** The single Optimize workspace, with backwards-compatible Admin deep links. */
const releaseDays = [28, 14, 7];
const safeId = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,80}$/.test(value);

export function releaseRound(day) {
  if (day === null || day === undefined || day === '') return null;
  const value = Number(day);
  return Number.isFinite(value) ? releaseDays.find(round => round <= value) ?? null : null;
}

export function thompsonUrl({flightId, day, runId, round} = {}) {
  const params = new URLSearchParams();
  if (safeId(runId) && runId.startsWith('adaptive-')) {
    params.set('run', runId);
    if (/^[1-9]\d*$/.test(String(round))) params.set('round', String(round));
  }
  if (safeId(flightId)) params.set('flight_id', flightId);
  const release = releaseRound(day);
  if (release !== null) params.set('forecast_day', String(release));
  return `/adaptive-pricing${params.size ? `?${params}` : ''}`;
}

export function redirectLegacyOptimization() {
  if (location.hash !== '#optimization') return false;
  const params = new URL(location.href).searchParams;
  location.replace(thompsonUrl({
    runId: params.get('run'), round: params.get('round'),
    flightId: params.get('flight_id'), day: params.get('forecast_day') ?? params.get('day'),
  }));
  return true;
}
