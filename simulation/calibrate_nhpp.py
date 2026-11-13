"""Fit one protection residual guard on calibration flights, then test once.

Uses a predeclared global residual quantile, no route/scenario-specific tuning.
Calibration and holdout flights are deterministic and disjoint. The additional
guard is a synthetic robustness setting, not an aviation protection guarantee.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from simulation.evaluate_nhpp import evaluate


def calibrate(data_dir: Path | str | None = None, per_split: int = 180, seed: int = 271117) -> dict:
    root = Path(data_dir) if data_dir else Path(__file__).parent / "generated"
    flights = json.loads((root / "flights.json").read_text(encoding="utf-8"))
    if not isinstance(per_split, int) or per_split < 10 or len(flights) < 2 * per_split:
        raise ValueError("need at least 10 flights in each of two disjoint splits")
    order = np.random.default_rng(seed).permutation(len(flights))
    calibration_ids = [flights[int(i)]["flight_id"] for i in order[:per_split]]
    holdout_ids = [flights[int(i)]["flight_id"] for i in order[per_split:2 * per_split]]
    calibration_report = evaluate(root, day=28, seed=seed, flight_ids=calibration_ids, protection_allowance=0)
    residuals = sorted(row["actual_latent_demand"] - row["raw_protection_p90"] for row in calibration_report["flights"])
    # Finite-sample upper order statistic. Exchangeability is not established
    # for real airlines; no real-world conformal guarantee is claimed.
    rank = min(per_split, math.ceil((per_split + 1) * .9))
    allowance = max(0, int(math.ceil(residuals[rank - 1])))
    model_path = Path(__file__).resolve().parents[1] / "backend" / "nhpp.py"
    calibration = {
        "schema_version": "1.0", "allowance": allowance, "as_of_day": 28,
        "target_coverage": .9, "method": "nonnegative_global_upper_order_statistic_of_actual_demand_minus_raw_P90",
        "quantile_order_rank": rank, "selection_seed": seed, "flights_per_split": per_split,
        "calibration_flight_ids": sorted(calibration_ids), "holdout_flight_ids": sorted(holdout_ids),
        "disjoint": not bool(set(calibration_ids) & set(holdout_ids)),
        "source": "synthetic_assumed_demo",
        "forecast_code_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "data_manifest_sha256": hashlib.sha256((root / "manifest.json").read_bytes()).hexdigest(),
        "notes": [
            "Global additive demand guard selected only from calibration flights before evaluating the holdout.",
            "Raw posterior P90 remains available separately; guarded protection is raw P90 plus this allowance.",
            "Calibration is for D28 only. Applying the same full allowance at shorter horizons is conservative but not separately validated.",
            "Unknown shocks and different populations can still fail. This is not a real HK Express risk guarantee.",
            "No per-scenario retuning or selection was performed after inspecting the holdout.",
        ],
    }
    # Save the chosen guard before testing. Explicit allowance=0 above bypasses
    # any old calibration file, preventing recursive calibration.
    (root / "calibration.json").write_text(json.dumps(calibration, indent=2), encoding="utf-8")
    holdout_report = evaluate(root, day=28, seed=seed, flight_ids=holdout_ids, protection_allowance=allowance)
    holdout_report["split_role"] = "holdout_after_fixed_calibration"
    holdout_report["calibration_flight_ids"] = sorted(calibration_ids)
    holdout_report["calibration_overlap"] = sorted(set(calibration_ids) & set(holdout_ids))
    calibration_report["split_role"] = "calibration_raw_predictions"
    (root / "calibration_evaluation.json").write_text(json.dumps(calibration_report, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "nhpp_holdout.json").write_text(json.dumps(holdout_report, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"allowance": allowance, "disjoint": calibration["disjoint"],
            "calibration": calibration_report["overall"], "holdout": holdout_report["overall"],
            "by_scenario": holdout_report["by_scenario"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).parent / "generated")
    parser.add_argument("--per-split", type=int, default=180)
    parser.add_argument("--seed", type=int, default=271117)
    args = parser.parse_args()
    print(json.dumps(calibrate(args.data_dir, args.per_split, args.seed), ensure_ascii=False))


if __name__ == "__main__":
    main()
