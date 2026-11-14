"""Explicit, backed-up fee refresh for six synthetic pitch offers, never real fares.
Run without --apply to preview. Reference rates are deliberately frozen.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.store import Store

HKE = 'https://www.hkexpress.com/en-hk/travel-help/fees-and-surcharges'
FX_SOURCE = 'https://www.ecb.europa.eu/stats/shared/pdf/eurofxref.pdf'
FX = Decimal('8.6714') / Decimal('176.83')  # ECB 2026-11-13 EUR cross rates
AIRPORTS = {
    'NRT': (2460, 700, 'Terminal 2', 'https://www.narita-airport.jp/en/airportguide/psfc/'),
    'HND': (2950, 0, 'Terminal 3', 'https://www.tokyo-haneda.com/site_resource/flight/pdf/qualified_simplified_invoices_for_psfc_en.pdf'),
    'KIX': (3310, 320, 'Terminal 1', 'https://www.kansai-airports.co.jp/en/business/airlinepartners/charges/'),
}
ROUTES = {}
for airport in AIRPORTS:
    ROUTES[f'DEMO-HKG-{airport}-20270515'] = ('HKG', airport)
    ROUTES[f'DEMO-{airport}-HKG-20270518'] = (airport, 'HKG')


def reference(origin, destination):
    if (origin, destination) not in ROUTES.values():
        raise ValueError('No verified reference for this route')
    currency = 'HKD' if origin == 'HKG' else 'JPY'
    fx = Decimal(1) if currency == 'HKD' else FX
    components = []
    def add(group, code, label, amount, source):
        components.append(dict(group=group, code=code, label=label, native_amount=amount,
                               native_currency=currency, amount=float((Decimal(amount)*fx).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)), source=source))
    if origin == 'HKG':
        add('fuel','YR','Fuel surcharge',318,HKE)
        add('tax','HK','Air passenger departure tax',200,'https://www.cad.gov.hk/english/departure_tax.html')
        add('tax','G3','Airport construction fee',90,'https://www.hongkongairport.com/en/passenger-guide/departures/airport-construction-fee.page')
        add('tax','I5','Passenger security charge',65,'https://www.hongkongairport.com/en/media-centre/press-release/2024/pr-1716')
        terminal = 'Hong Kong; short-haul economy'
    else:
        facility, security, terminal, source = AIRPORTS[origin]
        add('fuel','YR','Fuel surcharge',12600,HKE)
        add('tax','SW','Passenger service facility charge',facility,source)
        if security:
            add('tax','OI / 6I','Passenger security service charge',security,source)
        add('tax','TK','International tourist tax',3000,'https://www.nta.go.jp/english/taxes/indirect/basic_knowledge.htm')
        add('payment',None,'E-payment fee',810,HKE)
    lines = []
    for group, label in [('fuel','YR · Fuel surcharge'),('tax','Government & airport charges'),('payment','E-payment fee')]:
        selected = [c for c in components if c['group'] == group]
        if selected:
            lines.append(dict(label=label, amount=float(sum(Decimal(str(c['amount'])) for c in selected))))
    return dict(currency='HKD', kind='reference_estimate', checked_on='2026-11-14',
                tariff_date='2026-11-01', fx_date='2026-11-13' if currency=='JPY' else None,
                fx_rate=float(fx), fx_source=FX_SOURCE if currency=='JPY' else None,
                note='Demo estimate using published reference fees, not an airline quote. One adult, non-exempt, separate one-way booking. Future fees may change.',
                terminal_assumption=terminal, components=components, lines=lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default='data/private/demo.sqlite3')
    parser.add_argument('--apply', action='store_true')
    args=parser.parse_args()
    path=Path(args.database)
    if not path.is_file():
        raise SystemExit('Existing demo database required')
    if args.apply:
        backup=path.with_name('demo-before-fee-reference-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')
        with sqlite3.connect(path) as source, sqlite3.connect(backup) as target:
            source.backup(target)
        print('Backup:',backup)
    store=Store(path)
    for offer in store.offers():
        route=ROUTES.get(offer['flight_id'])
        if not route:
            continue
        detail=reference(*route)
        total=round(sum(line['amount'] for line in detail['lines']),2)
        if args.apply:
            store.set_offer_fee_breakdown(offer['id'],detail)
        print(json.dumps(dict(flight=offer['flight_id'],fees=total,ticket_total=round(offer['base_fare']+total,2),applied=args.apply)))

if __name__ == '__main__':
    main()
