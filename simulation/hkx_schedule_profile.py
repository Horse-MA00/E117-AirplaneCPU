"""Derive the weekly HK Express departure template used by hkx_generate.

Input: OAG Flight Info responses cached by scripts/fetch_oag_schedule.py under
data/private/ (licensed, never committed). Output: a compact timetable profile
(weekday, flight number, destination, departure time, aircraft code, elapsed
minutes) with no other OAG fields. Run only after a fresh authorized fetch.
"""
import glob
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data/private/oag_uo_schedule"
PROFILE = Path(__file__).parent / "hkx_schedule_profile.json"


def build():
    entries, dates = [], []
    for path in sorted(glob.glob(str(CACHE / "HKG-*.json"))):
        obj = json.loads(Path(path).read_text())
        dates.append(obj["date"])
        for record in obj["data"]:
            if record.get("flightType") != "Scheduled" or record["segmentInfo"]["numberOfStops"]:
                continue
            departure = record["departure"]
            entries.append({
                "weekday": date.fromisoformat(departure["date"]["local"]).weekday(),
                "flight_number": f"UO{record['flightNumber']}",
                "destination": record["arrival"]["airport"]["iata"],
                "departure_local": departure["time"]["local"],
                "aircraft_iata": record["aircraftType"]["iata"],
                "elapsed_minutes": record["elapsedTime"],
            })
    if sorted({e["weekday"] for e in entries}) != list(range(7)):
        raise ValueError("profile needs one complete week of departures")
    entries.sort(key=lambda e: (e["weekday"], e["departure_local"], e["flight_number"]))
    profile = {
        "source": "Derived from OAG Flight Info (flight-instances), carrier UO, operating, non-stop departures from HKG.",
        "sample_week": [min(dates), max(dates)], "season": "IATA northern winter 2026/27 (sample week)",
        "fields": "Only weekday, flight number, destination, local departure time, aircraft code and elapsed time are kept.",
        "departures": len(entries), "entries": entries,
    }
    PROFILE.write_text(json.dumps(profile, indent=1) + "\n", encoding="utf-8")
    return profile


if __name__ == "__main__":
    result = build()
    print(json.dumps({k: result[k] for k in ("sample_week", "departures")}))
