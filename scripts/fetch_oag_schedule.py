#!/usr/bin/env python3
"""Fetch HK Express (UO) operating departures from OAG for a date range.

Real OAG calls need the current user's authorization and an explicit call cap.
The key is read from OAG_FLIGHT_INFO_KEY (or .env.local via backend.oag.load_env);
it is never written anywhere. Raw responses are cached under data/private/
(Git-ignored, licensed data, never published). Use
`python -m simulation.hkx_schedule_profile` to derive the aggregate profile.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.oag import load_env  # noqa: E402

BASE = "https://api.oag.com/flight-instances/"
CACHE = ROOT / "data/private/oag_uo_schedule"


def fetch(start, days, max_calls, origin="HKG"):
    load_env()
    key = os.environ.get("OAG_FLIGHT_INFO_KEY")
    if not key:
        raise SystemExit("Set OAG_FLIGHT_INFO_KEY (or add it to .env.local)")
    CACHE.mkdir(parents=True, exist_ok=True)
    calls, summary = 0, {}
    for offset in range(days):
        day = (start + timedelta(days=offset)).isoformat()
        target = CACHE / f"{origin}-{day}.json"
        if target.exists():
            summary[day] = len(json.loads(target.read_text())["data"])
            continue
        params = {"DepartureDateTime": day, "CarrierCode": "UO", "DepartureAirport": origin, "CodeType": "IATA",
                  "Codeshare": "OPERATING", "Limit": 10, "version": "v2"}
        url, records = BASE + "?" + urllib.parse.urlencode(params), []
        while url:
            if calls >= max_calls:
                raise SystemExit(f"Stopped at the --max-calls cap ({max_calls}); {day} incomplete and not cached")
            request = urllib.request.Request(url, headers={"Subscription-Key": key, "Accept": "application/json"})
            calls += 1
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    page = json.load(response)
            except urllib.error.HTTPError as error:
                # Never rotate keys or retry around a quota.
                raise SystemExit(f"OAG HTTP {error.code} on {day} after {calls} calls; stopping") from None
            records.extend(page.get("data", []))
            url = (page.get("paging") or {}).get("next")
            time.sleep(8)  # free tier is throttled per minute
        target.write_text(json.dumps({"date": day, "origin": origin, "data": records}))
        target.chmod(0o600)
        summary[day] = len(records)
    return {"calls": calls, "records_by_date": summary, "cache": str(CACHE.relative_to(ROOT))}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", default="2026-11-16")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--origin", default="HKG")
    parser.add_argument("--max-calls", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(fetch(date.fromisoformat(args.start), args.days, args.max_calls, args.origin), indent=2))


if __name__ == "__main__":
    main()
