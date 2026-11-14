// Search locations are independent of released inventory. Verified 2026-11-14:
// https://www.hkexpress.com/en/destinations
// https://www.hkexpress.com/zh/sitemap/flights-from-cities/page-1
// Status/source details: docs/CLIENT_FLEXIBLE_SEARCH.md.
export const airports = {
  HKG: { name: 'Hong Kong', region: 'HK' },
  HND: { name: 'Tokyo Haneda', region: 'JP' },
  NRT: { name: 'Tokyo Narita', region: 'JP' },
  KIX: { name: 'Osaka Kansai', region: 'JP' },
  NGO: { name: 'Nagoya Chubu Centrair', region: 'JP' },
  FUK: { name: 'Fukuoka', region: 'JP' },
  OKA: { name: 'Okinawa Naha', region: 'JP' },
  HIJ: { name: 'Hiroshima', region: 'JP' },
  TAK: { name: 'Takamatsu', region: 'JP' },
  SDJ: { name: 'Sendai', region: 'JP' },
  KMQ: { name: 'Komatsu', region: 'JP' },
  ISG: { name: 'Ishigaki', region: 'JP' },
  // Requested by the team; absent from the current official scheduled catalog.
  CTS: { name: 'Sapporo New Chitose', region: 'JP', note: 'Schedule unconfirmed', status: 'requested' },
  ICN: { name: 'Seoul Incheon', region: 'KR' },
  PUS: { name: 'Busan Gimhae', region: 'KR' },
  TAE: { name: 'Daegu', region: 'KR' },
  CJU: { name: 'Jeju', region: 'KR' },
  TPE: { name: 'Taipei Taoyuan', region: 'TW' },
  KHH: { name: 'Kaohsiung', region: 'TW' },
  RMQ: { name: 'Taichung', region: 'TW' },
  PKX: { name: 'Beijing Daxing', region: 'CN' },
  CZX: { name: 'Changzhou Benniu', region: 'CN' },
  WUX: { name: 'Wuxi Sunan Shuofang', region: 'CN' },
  NGB: { name: 'Ningbo Lishe', region: 'CN' },
  SYX: { name: 'Sanya Phoenix', region: 'CN' },
  YIW: { name: 'Yiwu', region: 'CN' },
  HFE: { name: 'Hefei Xinqiao', region: 'CN', note: 'Announced: 3 Dec 2026', serviceStartsOn: '2026-12-03', status: 'announced' },
  BKK: { name: 'Bangkok Suvarnabhumi', region: 'TH' },
  CNX: { name: 'Chiang Mai', region: 'TH' },
  HKT: { name: 'Phuket', region: 'TH' },
  HAN: { name: 'Hanoi Noi Bai', region: 'VN' },
  DAD: { name: 'Da Nang', region: 'VN' },
  PQC: { name: 'Phu Quoc', region: 'VN' },
  SZB: { name: 'Kuala Lumpur Subang', region: 'MY' },
  BKI: { name: 'Kota Kinabalu', region: 'MY' },
  PEN: { name: 'Penang', region: 'MY' },
  MNL: { name: 'Manila Ninoy Aquino', region: 'PH' },
  CRK: { name: 'Clark', region: 'PH' },
  // Existing prototype/legacy codes stay recognizable if a published offer uses
  // them; they are not advertised as part of the verified selectable network.
  DMK: { name: 'Bangkok Don Mueang', region: 'TH', catalog: false },
  SGN: { name: 'Ho Chi Minh City', region: 'VN', catalog: false },
  CEB: { name: 'Cebu', region: 'PH', catalog: false },
  SIN: { name: 'Singapore', region: 'SG', catalog: false },
};
const regionNames = { HK: 'Hong Kong', JP: 'Japan', KR: 'South Korea', TW: 'Taiwan, China', CN: 'Chinese Mainland', TH: 'Thailand', VN: 'Vietnam', MY: 'Malaysia', PH: 'Philippines', SG: 'Singapore' };
export const regions = Object.fromEntries(Object.entries(regionNames).map(([code, name]) => [code, { name, airports: Object.keys(airports).filter((airport) => airports[airport].region === code) }]));
export const catalogAirportCodes = Object.keys(airports).filter((code) => airports[code].catalog !== false);
export const airportNames = Object.fromEntries(Object.entries(airports).map(([code, value]) => [code, value.name]));
export function airportLabel(code) {
  const info = airports[code];
  return info ? `${info.name} (${code})${info.note ? ` · ${info.note}` : ''}` : code;
}
