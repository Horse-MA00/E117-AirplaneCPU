"""Prepare anonymous, single-quote pilot cases and validate human self-reports.

This tool contacts nobody and makes no provider calls. Blank templates are not
observations. Source declarations are checked, but respondent authenticity is
not verified; collected choices are descriptive and never train a model here.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.fare_policy import member_fare_cap, quoted_base_fare

VERSION = "member-choice-calibration-v1"
DEFAULT_DIRECTORY = ROOT / "data/private/member_choice_calibration"
ACTIONS = ("BUY_MEMBER", "BUY_REGULAR", "DECLINE")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def make_study(scope, participants=24, seed=20261117):
    if isinstance(participants, bool) or not isinstance(participants, int) or not 3 <= participants <= 300:
        raise ValueError("participants must be 3..300")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 100000000:
        raise ValueError("seed must be 0..100000000")
    normal = quoted_base_fare(scope["normal_base_fare"])
    cap = member_fare_cap(normal)
    if cap < 1 or scope.get("releasable_seats", 0) < 1:
        raise ValueError("Choose a snapshot with a positive whole-HKD member fare and available member inventory")
    flight = {key: scope[key] for key in
              ("flight_id", "origin", "destination", "departure_date", "departure_time", "as_of_day")}
    fares = sorted({cap, cap*3//4, cap//2})
    cases = []
    for fare in fares:
        context = {
            "scenario": "An optional leisure trip for an already-valid member; use your own interest in travelling.",
            "flight": flight, "flight_source": "project_synthetic_flight_snapshot",
            "normal_base_fare_hkd": normal, "member_base_fare_hkd": fare,
            "membership_active": True, "personal_tickets": 1, "member_seat_available": True,
            "payment_scope": "Basic ticket fare only; membership fees, taxes, fuel and other payments are outside this question.",
            "question": "Would you buy this member ticket, buy the normal ticket, or decline this optional trip? Briefly explain your own reason.",
            "allowed_actions": list(ACTIONS), "real_booking": False,
        }
        digest = _digest(context)
        cases.append({"case_id": "case-"+digest[:16], "context_sha256": digest, "context": context})
    assigned = [cases[i % len(cases)]["case_id"] for i in range(participants)]
    random.Random(seed).shuffle(assigned)
    assignments = [{"participant_id": f"pilot-{seed}-{i+1:04d}", "case_id": case}
                   for i, case in enumerate(assigned)]
    study = {"version": VERSION, "seed": seed, "member_fare_cap_hkd": cap,
             "cases": cases, "assignments": assignments,
             "collection_status": "blank_pilot_no_observations", "provider_calls": 0,
             "instructions": [
                 "Give each anonymous participant only their assigned participant file; do not share this coordinator file or the price ladder.",
                 "Assign codes without names, email addresses or a public identity mapping. Ask respondents not to include personal details in their reason.",
                 "Use the same wording and collection conditions. Small pilots can remain confounded by timing, interest and who answers; they are not representative HK Express demand.",
                 "Record actual self-reports only. Never fill a human response with an LLM or synthetic choice.",
                 "No collected response automatically updates a pricing model or an experiment holdout.",
             ]}
    study["study_sha256"] = _digest(study)
    study["study_id"] = "member-pilot-"+study["study_sha256"][:16]
    return study


def _validated_study(study):
    if not isinstance(study, dict) or study.get("version") != VERSION:
        raise ValueError("Unknown pilot study version")
    content = {key: value for key, value in study.items() if key not in ("study_id", "study_sha256")}
    digest = _digest(content)
    if study.get("study_sha256") != digest or study.get("study_id") != "member-pilot-"+digest[:16]:
        raise ValueError("Study content hash does not match")
    cases = {}
    for case in study["cases"]:
        context_hash = _digest(case["context"])
        if case["context_sha256"] != context_hash or case["case_id"] != "case-"+context_hash[:16]:
            raise ValueError("Displayed case context hash does not match")
        if case["case_id"] in cases:
            raise ValueError("Duplicate study case")
        cases[case["case_id"]] = case
    assignments = {}
    for assignment in study["assignments"]:
        if assignment["participant_id"] in assignments or assignment["case_id"] not in cases:
            raise ValueError("Invalid participant assignment")
        assignments[assignment["participant_id"]] = assignment["case_id"]
    return cases, assignments


def response_template(study):
    cases, assignments = _validated_study(study)
    return {"study_id": study["study_id"], "study_sha256": study["study_sha256"],
            "responses": [{"participant_id": participant, "case_id": case_id,
                           "context_sha256": cases[case_id]["context_sha256"],
                           "source": None, "action": None, "reason": "", "answered_at": None}
                          for participant, case_id in assignments.items()]}


def write_study(study, output=None):
    cases, assignments = _validated_study(study)
    output = Path(output) if output else DEFAULT_DIRECTORY / study["study_id"]
    if output.exists():
        raise FileExistsError("Refusing to overwrite an existing pilot directory")
    output.mkdir(parents=True)
    _write_new(output / "study.json", study)
    template = response_template(study)
    _write_new(output / "responses_template.json", template)
    destination = output / "participants"
    destination.mkdir()
    for row in template["responses"]:
        _write_new(destination / (row["participant_id"]+".json"), {
            "study_id": study["study_id"], "study_sha256": study["study_sha256"],
            "case": cases[row["case_id"]], "response": row,
            "answer_instructions": "Use your own choice. Set source to human_self_report only after an actual human answers; use a timezone-aware ISO timestamp. This is hypothetical and makes no booking.",
        })
    return {"output": str(output), "study_id": study["study_id"], "participants": len(assignments),
            "recorded_responses": 0, "status": "awaiting_human_responses"}


def summarize(study, supplied):
    cases, assignments = _validated_study(study)
    if (not isinstance(supplied, dict) or supplied.get("study_id") != study["study_id"]
            or supplied.get("study_sha256") != study["study_sha256"]):
        raise ValueError("Responses belong to a different study")
    rows = supplied.get("responses")
    if not isinstance(rows, list) or len(rows) > len(assignments):
        raise ValueError("Responses must be an array within the assigned participant count")
    counts = {case_id: {"answered": 0, **dict.fromkeys(ACTIONS, 0)} for case_id in cases}
    seen, blank = set(), 0
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Response must be an object")
        participant = row.get("participant_id")
        case_id = row.get("case_id")
        if not isinstance(participant, str) or participant not in assignments or participant in seen:
            raise ValueError("Unknown or duplicate anonymous participant")
        seen.add(participant)
        if (assignments[participant] != case_id or case_id not in cases
                or row.get("context_sha256") != cases[case_id]["context_sha256"]):
            raise ValueError("Response does not match the assigned displayed context")
        if all(row.get(key) in (None, "") for key in ("source", "action", "reason", "answered_at")):
            blank += 1
            continue
        if row.get("source") != "human_self_report":
            raise ValueError("Answered responses must explicitly declare human_self_report; LLM/synthetic sources are not human data")
        if row.get("action") not in ACTIONS:
            raise ValueError("Unknown or missing observed action")
        if not isinstance(row.get("reason"), str) or len(row["reason"]) > 1000:
            raise ValueError("Reason must be a short string without identifying details")
        try:
            answered_at = datetime.fromisoformat(row.get("answered_at", "").replace("Z", "+00:00"))
            if answered_at.tzinfo is None:
                raise ValueError("Timezone required")
        except (AttributeError, TypeError, ValueError):
            raise ValueError("answered_at must be a timezone-aware ISO timestamp") from None
        counts[case_id]["answered"] += 1
        counts[case_id][row["action"]] += 1
    aggregates = []
    for case_id, count in counts.items():
        n = count["answered"]
        aggregates.append({"case_id": case_id, "member_base_fare_hkd": cases[case_id]["context"]["member_base_fare_hkd"],
                           **count, "member_purchase_rate": count["BUY_MEMBER"]/n if n else None,
                           "any_purchase_rate": (count["BUY_MEMBER"]+count["BUY_REGULAR"])/n if n else None})
    total = sum(c["answered"] for c in counts.values())
    return {"version": VERSION, "study_id": study["study_id"], "study_sha256": study["study_sha256"],
            "status": "descriptive_pilot" if total else "awaiting_human_responses",
            "response_source": "human_self_report" if total else None,
            "authenticity": "self_report_unverified" if total else "no_observations",
            "recorded_responses": total, "blank_rows": blank, "not_answered": len(assignments)-total,
            "by_price": sorted(aggregates, key=lambda row: row["member_base_fare_hkd"]),
            "automatic_model_updates": False, "provider_calls": 0,
            "limitations": ["Descriptive hypothetical choices, not purchases or a representative demand estimate.",
                            "Small groups, nonresponse, collection timing and personal context can affect apparent price differences.",
                            "Source labels cannot prove human authenticity. No private identity or respondent reason is published in this summary."]}


def _write_new(path, value):
    with Path(path).open("x", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Prepare blank individual survey cases, without contacting anyone")
    create.add_argument("--flight-id", default="UO814-20271116", help="HK Express catalogue flight; legacy ids need UOPTION_DATASET=legacy")
    create.add_argument("--day", type=int, choices=(28, 14, 7), default=28)
    create.add_argument("--participants", type=int, default=24)
    create.add_argument("--seed", type=int, default=20261117)
    create.add_argument("--output", type=Path)
    aggregate = commands.add_parser("summarize", help="Validate locally collected answers and save a private descriptive summary")
    aggregate.add_argument("--study", type=Path, required=True)
    aggregate.add_argument("--responses", type=Path, required=True)
    aggregate.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "create":
        from backend.initial_policy import flight_scope
        print(json.dumps(write_study(make_study(flight_scope(args.flight_id, args.day), args.participants, args.seed), args.output)))
    else:
        result = summarize(json.loads(args.study.read_text()), json.loads(args.responses.read_text()))
        target = args.output or DEFAULT_DIRECTORY / (result["study_id"]+"-summary.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_new(target, result)
        print(json.dumps({"output": str(target), "recorded_responses": result["recorded_responses"], "status": result["status"]}))


if __name__ == "__main__":
    main()
