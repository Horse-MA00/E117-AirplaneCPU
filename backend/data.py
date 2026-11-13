import csv,gzip,json,threading
from functools import lru_cache
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'simulation/generated'
_lock=threading.Lock(); _rows=None
INTS={'days_to_departure','capacity','booked_seats','available_seats','gross_bookings','cancellations'}
FLOATS={'empty_rate','normal_base_fare','mandatory_fees','normal_total_fare','interval_days'}

def manifest():return json.loads((DATA/'manifest.json').read_text())
@lru_cache(maxsize=1)
def flights():return json.loads((DATA/'flights.json').read_text())
def histories():
    global _rows
    with _lock:
        if _rows is None:
            result={}
            with gzip.open(DATA/'snapshots.csv.gz','rt',newline='') as f:
                for r in csv.DictReader(f):
                    for k in INTS:
                        if k in r:r[k]=int(r[k])
                    for k in FLOATS:
                        if k in r:r[k]=float(r[k]) if r[k] else None
                    result.setdefault(r['flight_id'],[]).append(r)
            _rows=result
    return _rows

def history(flight_id):
    if flight_id not in histories():raise ValueError('Unknown flight')
    return histories()[flight_id]
