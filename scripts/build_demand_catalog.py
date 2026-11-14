#!/usr/bin/env python3
"""Build the display-only D28 demand index without changing data or forecasts."""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import data
from backend.demand_catalog import INDEX_PATH, build_index


def main():
    started = time.monotonic()
    def progress(done, total):
        if done % 100 == 0 or done == total:
            print(f"Forecasted {done}/{total} D28 histories", flush=True)
    obj = build_index(data.histories(), progress=progress)
    path = ROOT/INDEX_PATH
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(obj, indent=2, ensure_ascii=False)+"\n")
    temporary.replace(path)
    print(json.dumps({"path": INDEX_PATH, "flights": obj["flight_count"],
                      "counts": obj["counts"], "seconds": round(time.monotonic()-started, 2)}), flush=True)


if __name__ == "__main__":
    main()
