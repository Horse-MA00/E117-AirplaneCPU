from .errors import NotFound
import csv,gzip,hashlib,json,threading
from functools import lru_cache
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'simulation/generated'
NETWORK_DATA=ROOT/'simulation/network_generated'
MEMBER_DEMO_DATA=ROOT/'simulation/member_demo_generated'
_lock=threading.Lock(); _rows=None
INTS={'days_to_departure','capacity','booked_seats','available_seats','gross_bookings','cancellations'}
FLOATS={'empty_rate','normal_base_fare','mandatory_fees','normal_total_fare','interval_days','member_initial_base_fare'}

def manifest():
    original=json.loads((DATA/'manifest.json').read_text())
    # rows/files retain their original meaning for the original CSV export and
    # historical calibration. Catalog totals explicitly include additive history.
    supplemental=json.loads((NETWORK_DATA/'manifest.json').read_text()) if (NETWORK_DATA/'manifest.json').exists() else None
    member_demo=json.loads((MEMBER_DEMO_DATA/'manifest.json').read_text()) if (MEMBER_DEMO_DATA/'manifest.json').exists() else None
    supplements=[value for value in (supplemental,member_demo) if value]
    return {**original,'catalog_rows':original['rows']+sum(value['rows'] for value in supplements),
            'catalog_flights':original['flights']+sum(value['flights'] for value in supplements),
            'supplemental':supplemental,'member_demo':member_demo,'supplements':supplements}
@lru_cache(maxsize=1)
def flights():
    original=json.loads((DATA/'flights.json').read_text())
    extra=[]
    for directory in (NETWORK_DATA,MEMBER_DEMO_DATA):
        if (directory/'flights.json').exists():extra.extend(json.loads((directory/'flights.json').read_text()))
    report_path=MEMBER_DEMO_DATA/'headroom_validation.json'
    if report_path.exists():
        report=json.loads(report_path.read_text())
        # These are display/default-selection hints from a frozen-model audit,
        # not guarantees or predictor inputs. Ignore them when inputs changed.
        current=hashlib.sha256((MEMBER_DEMO_DATA/'snapshots.csv.gz').read_bytes()).hexdigest()==report.get('snapshots_sha256')
        current=current and all((ROOT/name).exists() and hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest
                                for name,digest in report.get('source_files',{}).items())
        if current:
            checked={r['flight_id']:r['releasable_seats'] for r in report['records'] if r['days_to_departure']==28}
            for flight in extra:
                if flight['flight_id'] in checked:flight['demo_d28_releasable']=checked[flight['flight_id']]
    from .demand_catalog import enrich
    return enrich(original+extra, ROOT)
def histories():
    global _rows
    with _lock:
        if _rows is None:
            result={}
            paths=[DATA/'snapshots.csv.gz']
            for directory in (NETWORK_DATA,MEMBER_DEMO_DATA):
                if (directory/'snapshots.csv.gz').exists():paths.append(directory/'snapshots.csv.gz')
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
