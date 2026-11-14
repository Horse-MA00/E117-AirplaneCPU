/** Explicit navigation to the current Thompson workspace. */
const releaseDays = [28, 14, 7];
const safeId = (value) => typeof value === 'string' && /^[A-Za-z0-9_-]{1,80}$/.test(value);

export function releaseRound(day) {
  if (day === null || day === undefined || day === '') return null;
  const value = Number(day);
  return Number.isFinite(value) ? (releaseDays.find((round) => round <= value) ?? null) : null;
}

export function thompsonUrl({ flightId, day } = {}) {
  const params = new URLSearchParams();
  if (safeId(flightId)) params.set('flight_id', flightId);
  const release = releaseRound(day);
  if (release !== null) params.set('forecast_day', String(release));
  return `/adaptive-pricing${params.size ? `?${params}` : ''}`;
}
