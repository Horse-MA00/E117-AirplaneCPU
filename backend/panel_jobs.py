"""Durable, bounded background batches for independent synthetic journeys.

One compact checkpoint per traveller keeps 1,000-person panels inexpensive to
poll. Detailed packets are loaded only when a traveller is opened. A new batch
always requires an explicit start/resume request; reading never calls an LLM.
"""
from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import threading
import time
import urllib.parse
import uuid

from llm_agent import audit as audit_module, journey, journey_runner
from llm_agent.output_contract import CURRENCY, RESPONSE_LANGUAGE, validate_english_output
from llm_agent.population import population

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/private/customer_panels"
VERSION = "customer-panel-v1"
_lock = threading.Lock()
_active = set()
_threads = {}
RUNTIME_KEYS = ("provider_calls", "cache_hits", "forced_actions", "rule_decisions", "failures", "provider_decision_attempts")


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value):
        raise ValueError("Invalid panel or traveller ID")
    return value


def _folder(run_id):
    return BASE / _identifier(run_id)


def _number(value, name, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high or (integer and int(value) != value):
        raise ValueError(f"{name} must be {low}..{high}")
    return int(value) if integer else float(value)


def _save(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(audit_module.sanitize(value), ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _provenance(mode):
    files = ("backend/panel_jobs.py", "llm_agent/journey.py", "llm_agent/journey_runner.py",
             "llm_agent/population.py", "llm_agent/output_contract.py")
    return {"version": VERSION, "prompt_version": journey.PROMPT_VERSION,
            "prompt_sha256": hashlib.sha256(journey.PROMPT.read_bytes()).hexdigest(),
            "implementation_hashes": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files},
            "model": os.environ.get("LLM_MODEL") if mode == "live" else None,
            "endpoint_sha256": hashlib.sha256(os.environ.get("LLM_API_URL", "").encode()).hexdigest() if mode == "live" else None}


def _require_current(spec):
    if spec.get("provenance") != _provenance(spec["mode"]):
        raise ValueError("Panel implementation, prompt or provider changed. Start a new panel; historical results remain readable.")


def _configured():
    endpoint, key, model = (os.environ.get(k, "") for k in ("LLM_API_URL", "LLM_API_KEY", "LLM_MODEL"))
    parsed = urllib.parse.urlsplit(endpoint)
    if not (endpoint and key and model):
        raise ValueError("Live provider is not configured")
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Live provider requires HTTPS without embedded credentials or query parameters")


def _choices(context):
    result = []
    for action in context["allowed_actions"]:
        options = [o for o in context["legal_options"] if o["action"] == action]
        result.extend((action, o["id"]) for o in options)
        if not options:
            result.append((action, None))
    return result


class _CallAudit:
    """Forward durable records while tracking this one concurrent decision."""
    def __init__(self, parent):
        self.parent, self.path, self.run_id = parent, parent.path, parent.run_id
        self.provider_calls = self.cache_hits = 0

    def append(self, record):
        self.parent.append(record)
        if record.get("event") == "provider_dispatched":
            self.provider_calls += 1
        if record.get("event") == "decision_validated" and record.get("cache_hit"):
            self.cache_hits += 1


def _step(checkpoint, mode, record):
    world = copy.deepcopy(checkpoint["world"])
    packet = journey.packet_for(world)
    choices = _choices(packet["context"])
    counts = dict.fromkeys(RUNTIME_KEYS, 0)
    call_audit = _CallAudit(record)
    source = "environment_forced" if len(choices) == 1 else "provider_live" if mode == "live" else "deterministic_assumption"
    try:
        if source == "environment_forced":
            action, option = choices[0]
            decision = {"action": action, "option_id": option, "reason_code": "ENVIRONMENT_FORCED",
                        "reason": "Only one legal action is available; no model choice was requested.", "confidence": "high"}
            counts["forced_actions"] = 1
        elif mode == "live":
            counts["provider_decision_attempts"] = 1
            decision = journey_runner.provider_decision(packet, call_audit)
        else:
            decision = journey.deterministic(packet["context"])
            counts["rule_decisions"] = 1
        validate_english_output(decision)
        clean = journey.apply_decision(world, decision)
        event = {"packet": packet, "decision": clean, "state_after": copy.deepcopy(world["state"]),
                 "source": source, "inventory_committed": False}
        record.append({"event": "panel_state_transition", "source": source, "validation": "passed", **event})
        error = None
    except Exception as exc:
        counts["failures"] = 1
        error = str(exc)
        event = None
        record.append({"event": "panel_person_paused", "customer_id": world["person"]["customer_id"],
                       "stage_index": checkpoint["world"]["stage_index"], "error": error, "state_committed": False})
    counts["provider_calls"], counts["cache_hits"] = call_audit.provider_calls, call_audit.cache_hits
    return world, event, counts, error


def _checkpoint_path(folder, customer_id):
    return folder / "people" / (_identifier(customer_id) + ".json")


def _save_detail(folder, customer_id, event):
    """At most six packets: replace atomically so a crash cannot tear a line."""
    path = folder / "people" / (customer_id + ".events.jsonl")
    previous = []
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.endswith("\n"):
                    item = json.loads(line)
                    if item["packet"]["stage_index"] < event["packet"]["stage_index"]:
                        previous.append(item)
    temporary = path.with_suffix(".tmp")
    temporary.write_text("".join(journey.canonical(audit_module.sanitize(item))+"\n" for item in [*previous, event]), encoding="utf-8")
    temporary.replace(path)


def _recover_provider_counts(record, checkpoints):
    """Recover dispatched/failed attempts whose response preceded a crash.

    Raw audit is authoritative for network evidence; world checkpoints remain
    authoritative for committed actions. This streams once on explicit resume,
    never on a normal progress poll.
    """
    fields = ("provider_calls", "cache_hits", "failures", "provider_decision_attempts")
    by_world = {c["world"]["world_id"]: c for c in checkpoints}
    for checkpoint in checkpoints:
        for key in fields:
            checkpoint["runtime"][key] = 0
    path = record.path / "events.jsonl"
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.endswith("\n"):
                break
            event = json.loads(line)
            world_id = event.get("packet_id", "").split(":", 1)[0]
            checkpoint = by_world.get(world_id)
            if event.get("event") == "panel_person_paused":
                checkpoint = next((c for c in checkpoints if c["world"]["person"]["customer_id"] == event["customer_id"]), None)
                key = "failures"
            else:
                key = {"provider_dispatched": "provider_calls", "request_prepared": "provider_decision_attempts"}.get(event.get("event"))
                if event.get("event") == "decision_validated" and event.get("cache_hit"):
                    key = "cache_hits"
            if checkpoint is not None and key:
                checkpoint["runtime"][key] += 1


def _row(checkpoint):
    world = checkpoint["world"]
    state = world["state"]
    purchase = checkpoint.get("booking_decision")
    # A D7 WAIT/DECLINE becomes the displayed outcome only when no purchase was
    # made. Pending travellers never acquire an invented decision.
    return {"person": world["person"], "decision": checkpoint.get("decision"),
            "booking_decision": purchase, "final_state": state,
            "completed_stages": world["stage_index"], "source": checkpoint["source"],
            "error": checkpoint.get("error"), "runtime": checkpoint["runtime"]}


def _empty_counts():
    return {"customers": 0, "completed_customers": 0, "eligible_new_members": 0,
            "subscription_decisions": 0, "eligible_decided": 0, "booking_decisions": 0,
            "joined": 0, "existing_members": 0, "booked": 0, "cancelled": 0, "renewal_intent": 0}


def _add_counts(counts, row):
    p, s, n = row["person"], row["final_state"], row["completed_stages"]
    counts["customers"] += 1
    counts["completed_customers"] += n == len(journey.STAGES)
    counts["eligible_new_members"] += not p["membership_active"]
    counts["existing_members"] += bool(p["membership_active"])
    counts["subscription_decisions"] += n > 0
    counts["eligible_decided"] += n > 0 and not p["membership_active"]
    counts["booking_decisions"] += n >= 4
    counts["joined"] += bool(s["joined_this_run"])
    counts["booked"] += s["ticket_spend"] > 0
    counts["cancelled"] += bool(s["booking_cancelled"])
    counts["renewal_intent"] += s["renewal_intention"] == "RENEW_INTENT"


def _aggregate(spec, checkpoints):
    rows = [_row(c) for c in checkpoints]
    summary, segments = _empty_counts(), {}
    runtime = dict.fromkeys(RUNTIME_KEYS, 0)
    for row in rows:
        _add_counts(summary, row)
        person = row["person"]
        group = segments.setdefault(person["segment"], {"segment": person["segment"], "segment_label": person["segment_label"], **_empty_counts()})
        _add_counts(group, row)
        for key in RUNTIME_KEYS:
            runtime[key] += row["runtime"][key]
    completed_stages = sum(r["completed_stages"] for r in rows)
    return {"summary": summary, "segments": list(segments.values()), "runtime": runtime,
            "progress": {"completed_stages": completed_stages, "total_stages": spec["count"] * len(journey.STAGES),
                         "completed_customers": summary["completed_customers"], "total_customers": spec["count"]},
            "results": rows}


def _initialize(folder, spec):
    people_dir = folder / "people"
    people_dir.mkdir(exist_ok=True)
    people = [journey.enrich(p, i) for i, p in enumerate(population(spec["count"], spec["seed"]))]
    checkpoints = []
    for person in people:
        path = _checkpoint_path(folder, person["customer_id"])
        if path.exists():
            checkpoint = _read(path)
        else:
            checkpoint = {"world": journey.initial_world(person, spec["member_fare"], spec["membership_fee"], "panel"),
                          "source": "provider_live" if spec["mode"] == "live" else "deterministic_assumption",
                          "runtime": dict.fromkeys(RUNTIME_KEYS, 0), "decision": None, "booking_decision": None, "error": None}
            _save(path, checkpoint)
        checkpoints.append(checkpoint)
    return checkpoints


def _worker(run_id, max_calls):
    folder = _folder(run_id)
    job = _read(folder / "job.json")
    spec = _read(folder / "panel.json")
    record = None
    try:
        with (folder / ".run.lock").open("a") as process_lock:
            fcntl.flock(process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _require_current(spec)
            record = audit_module.Audit("customer_panel", {"prompt_version": journey.PROMPT_VERSION,
                "panel_id": run_id, "mode": spec["mode"], "customers": spec["count"], "provenance": spec["provenance"]},
                run_id=spec["audit_run_id"], resume=True)
            record.update(status="running")
            job.update(status="running", updated_at=time.time(), error=None)
            _save(folder / "job.json", job)
            checkpoints = _initialize(folder, spec)
            if spec["mode"] == "live":
                _recover_provider_counts(record, checkpoints)
                for checkpoint in checkpoints:
                    _save(_checkpoint_path(folder, checkpoint["world"]["person"]["customer_id"]), checkpoint)
            attempted = failures = 0
            failed_people = set()
            with ThreadPoolExecutor(max_workers=3) as pool:
                while True:
                    pending = [c for c in checkpoints if c["world"]["stage_index"] < len(journey.STAGES)
                               and c["world"]["person"]["customer_id"] not in failed_people]
                    if not pending or failures >= 3:
                        break
                    pending.sort(key=lambda c: (c["world"]["stage_index"], c["world"]["person"]["customer_id"]))
                    chosen = []
                    for checkpoint in pending:
                        needs_model = spec["mode"] == "live" and len(_choices(journey.context_for(checkpoint["world"]))) > 1
                        if needs_model and attempted >= max_calls:
                            continue
                        chosen.append(checkpoint)
                        attempted += int(needs_model)
                        if len(chosen) == 3:
                            break
                    if not chosen:
                        break
                    tasks = [pool.submit(_step, checkpoint, spec["mode"], record) for checkpoint in chosen]
                    for checkpoint, task in zip(chosen, tasks):
                        world, event, counts, error = task.result()
                        customer_id = world["person"]["customer_id"]
                        for key in RUNTIME_KEYS:
                            checkpoint["runtime"][key] += counts[key]
                        checkpoint["error"] = error
                        if error:
                            failed_people.add(customer_id)
                            failures += 1
                        else:
                            _save_detail(folder, customer_id, event)
                            checkpoint["world"] = world
                            if event["packet"]["context"]["stage"] == "subscription":
                                checkpoint["decision"] = event["decision"]
                            if event["decision"]["action"] in ("BUY_MEMBER", "BUY_REGULAR") or (event["packet"]["context"]["stage"] == "quote_d7" and checkpoint["booking_decision"] is None):
                                checkpoint["booking_decision"] = {**event["decision"], "source": event["source"], "inventory_committed": False}
                        _save(_checkpoint_path(folder, customer_id), checkpoint)
                    job.update(updated_at=time.time(), batch={"decision_attempts": attempted, "failures": failures, "max_calls": max_calls})
                    _save(folder / "job.json", job)
            complete = all(c["world"]["stage_index"] == len(journey.STAGES) for c in checkpoints)
            job.update(status="completed" if complete else "paused_after_errors" if failures else "paused_at_budget",
                       batch={"decision_attempts": attempted, "failures": failures, "max_calls": max_calls})
            aggregate = _aggregate(spec, checkpoints)
            record.update(status=job["status"], summary=aggregate["summary"], runtime=aggregate["runtime"])
    except Exception as exc:
        job.update(status="failed", error=str(exc))
        if record:
            record.append({"event": "panel_batch_failed", "error": str(exc)})
            record.update(status="failed", error=str(exc))
    finally:
        job["updated_at"] = time.time()
        _save(folder / "job.json", job)
        with _lock:
            _active.discard(run_id)


def start(body, run_id=None):
    if not isinstance(body, dict):
        raise ValueError("Panel options must be an object")
    max_calls = _number(body.get("max_calls", 60), "max_calls", 0, 120, True)
    if run_id is None:
        mode = body.get("mode", "deterministic")
        if mode not in ("deterministic", "live"):
            raise ValueError("Unknown decision mode")
        if mode == "live":
            _configured()
        count = _number(body.get("count", 100), "count", 1, 100 if mode == "live" else 1000, True)
        run_id = "panel-" + uuid.uuid4().hex[:16]
        spec = {"run_id": run_id, "audit_run_id": "panel-audit-" + uuid.uuid4().hex[:16],
                "mode": mode, "count": count, "created_at": time.time(),
                "seed": _number(body.get("seed", 117), "seed", 0, 2**31-1, True),
                "membership_fee": _number(body.get("membership_fee", 399), "membership_fee", 0, 5000),
                "member_fare": _number(body.get("member_fare", 70), "member_fare", 0, 2000),
                "provenance": _provenance(mode)}
        folder = _folder(run_id)
    else:
        folder = _folder(run_id)
        if not (folder / "panel.json").is_file():
            raise ValueError("Panel not found")
        spec = _read(folder / "panel.json")
        _require_current(spec)
        if spec["mode"] == "live":
            _configured()
        if _read(folder / "job.json")["status"] == "completed":
            raise ValueError("This panel is already complete")
    with _lock:
        if _active:
            raise ValueError("A customer panel batch is already running; wait for its checkpoint")
        _active.add(run_id)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        if not (folder / "panel.json").exists():
            _save(folder / "panel.json", spec)
        _save(folder / "job.json", {"run_id": run_id, "status": "queued", "updated_at": time.time(), "batch": {"max_calls": max_calls}})
        thread = threading.Thread(target=_worker, args=(run_id, max_calls), daemon=True)
        _threads[run_id] = thread
        thread.start()
    except Exception:
        with _lock:
            _active.discard(run_id)
        raise
    return {"run_id": run_id, "status": "queued"}


def read(run_id):
    folder = _folder(run_id)
    if not (folder / "panel.json").is_file():
        raise ValueError("Panel not found")
    spec, job = _read(folder / "panel.json"), _read(folder / "job.json")
    if job["status"] in ("running", "queued") and run_id not in _active:
        job["status"] = "interrupted"
    checkpoints = [_read(path) for path in sorted((folder / "people").glob("*.json"))]
    result = {**spec, **job, "prompt_version": spec["provenance"]["prompt_version"],
              "response_language": RESPONSE_LANGUAGE, "currency": CURRENCY,
              "scenario_mode": "journey", "source": "provider_live" if spec["mode"] == "live" else "deterministic_assumption",
              **_aggregate(spec, checkpoints),
              "limitations": ["Independent synthetic one-trip journeys, not shared inventory or observed customer conversion.",
                              "Expected term trips are intentions; only this trip and a new membership fee use the stated budget.",
                              "Panel size expands hypothetical coverage, not verified HK Express market shares.",
                              "The live batch limit counts decision attempts including cache reads; provider dispatches and cache hits are reported separately."]}
    return audit_module.sanitize(result)


def list_runs():
    if not BASE.exists():
        return []
    runs = []
    for folder in sorted(BASE.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if folder.is_dir() and (folder / "panel.json").is_file() and (folder / "job.json").is_file():
            item = read(folder.name)
            runs.append({k: item[k] for k in ("run_id", "status", "mode", "count", "updated_at", "progress", "summary", "member_fare", "membership_fee")})
        if len(runs) == 50:
            break
    return runs


def read_person(run_id, customer_id):
    folder = _folder(run_id)
    path = _checkpoint_path(folder, customer_id)
    if not path.is_file():
        raise ValueError("Panel traveller not found")
    checkpoint = _read(path)
    committed = checkpoint["world"]["stage_index"]
    events = {}
    log = path.with_suffix(".events.jsonl")
    if log.exists():
        with log.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.endswith("\n"):
                    break
                event = json.loads(line)
                stage = event["packet"]["stage_index"]
                if stage < committed:
                    events[stage] = event
    return audit_module.sanitize({**_row(checkpoint), "events": [events[k] for k in sorted(events)]})
