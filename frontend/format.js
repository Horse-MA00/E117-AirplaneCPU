// Number formatting shared by the Admin pages. All amounts are HKD.

export const isFiniteNumber = (value) => typeof value === 'number' && Number.isFinite(value);

const hasNumber = (value) => value !== null && value !== undefined && Number.isFinite(Number(value));

/**
 * Format an HKD amount, or '—' when there is no number.
 * With `cents: true`, fractional amounts always show two decimals (HK$12.50).
 */
export function money(value, { cents = false } = {}) {
  if (!hasNumber(value)) return '—';
  const amount = Number(value);
  const minimumFractionDigits = cents && amount % 1 ? 2 : 0;
  return `HK$${amount.toLocaleString('en-HK', { minimumFractionDigits, maximumFractionDigits: 2 })}`;
}

/** Signed HKD difference using a true minus sign, e.g. +HK$20 or −HK$15. */
export function signedMoney(value, options) {
  if (!isFiniteNumber(value)) return '—';
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return `${sign}${money(Math.abs(value), options)}`;
}
