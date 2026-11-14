from .errors import NotFound
import csv,gzip,json,threading
from functools import lru_cache
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'simulation/generated'
NETWORK_DATA=ROOT/'simulation/network_generated'
_lock=threading.Lock(); _rows=None
INTS={'days_to_departure','capacity','booked_seats','available_seats','gross_bookings','cancellations'}
FLOATS={'empty_rate','normal_base_fare','mandatory_fees','normal_total_fare','interval_days','member_initial_base_fare'}

def manifest():
    original=json.loads((DATA/'manifest.json').read_text())
    # rows/files retain their original meaning for the original CSV export and
    # historical calibration. Catalog totals explicitly include additive history.
    supplemental=json.loads((NETWORK_DATA/'manifest.json').read_text()) if (NETWORK_DATA/'manifest.json').exists() else None
    return {**original,'catalog_rows':original['rows']+(supplemental['rows'] if supplemental else 0),
            'catalog_flights':original['flights']+(supplemental['flights'] if supplemental else 0),
            'supplemental':supplemental}
@lru_cache(maxsize=1)
def flights():
    original=json.loads((DATA/'flights.json').read_text())
    extra=json.loads((NETWORK_DATA/'flights.json').read_text()) if (NETWORK_DATA/'flights.json').exists() else []
    return original+extra
def histories():
    global _rows
    with _lock:
        if _rows is None:
            result={}
            paths=[DATA/'snapshots.csv.gz']
            if (NETWORK_DATA/'snapshots.csv.gz').exists():paths.append(NETWORK_DATA/'snapshots.csv.gz')
            for path in paths:
                with gzip.open(path,'rt',newline='') as f:
                    for r in csv.DictReader(f):
                        for k in INTS:
                            if k in r:r[k]=int(r[k])
                        for k in FLOATS:
                            if k in r:r[k]=float(r[k]) if r[k] else None
                        result.setdefault(r['flight_id'],[]).append(r)
            _rows=result
    return _rows

def history(flight_id):
    if flight_id not in histories():raise NotFound('Unknown flight')
    return histories()[flight_id]
