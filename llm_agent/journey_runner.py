"""Execute six-stage journeys in deterministic or real provider mode."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

from .audit import Audit, sanitize
from .journey import PROMPT, PROMPT_VERSION, STAGES, apply_decision, canonical, context_for, deterministic, enrich, initial_world, packet_for, validate_decision
from .population import population
from .output_contract import RESPONSE_LANGUAGE, CURRENCY, CONTRACT_VERSION, validate_english_output


def _transport(request):
    from .runner import NoRedirect
    return urllib.request.build_opener(NoRedirect()).open(request, timeout=40)


def provider_decision(packet, audit):
    context = packet["context"]
    endpoint, key, model = (os.environ.get(k, "") for k in ("LLM_API_URL", "LLM_API_KEY", "LLM_MODEL"))
    messages = [{"role": "system", "content": PROMPT.read_text(encoding="utf-8")}, {"role": "user", "content": canonical(context)}]
    request_body = {"model": model, "messages": messages, "temperature": 0, "max_tokens": 600,
                    "response_format": {"type": "json_object"}}
    if urllib.parse.urlsplit(endpoint).hostname == "api.deepseek.com":
        # DeepSeek's host-specific extension: bounded choice explanations need
        # no hidden reasoning stream. Other providers never receive this field.
        request_body["thinking"] = {"type": "disabled"}
    record = {"packet_id": packet["packet_id"], "context_sha256": packet["context_sha256"],
              "prompt_version": PROMPT_VERSION, "model": model or None, "request": request_body,
              "response_language": RESPONSE_LANGUAGE, "currency": CURRENCY, "output_contract": CONTRACT_VERSION,
              "source": "provider_live", "validation": "pending", "cache_hit": False}
    # Persist request before network dispatch. Headers/credentials are never recorded.
    audit.append({**record, "event": "request_prepared"})
    start = time.monotonic()
    raw_text = None
    try:
        if packet.get("prompt_version") != PROMPT_VERSION or packet.get("system_prompt_sha256") != hashlib.sha256(PROMPT.read_bytes()).hexdigest():
            raise ValueError("Journey packet uses a different prompt; create a new English scenario")
        parsed = urllib.parse.urlsplit(endpoint)
        if not (endpoint and key and model):
            raise ValueError("Live LLM is not configured; no deterministic fallback is used")
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("LLM endpoint must be HTTPS without embedded credentials or query parameters")
        cache_dir = audit.path.parent.parent / "llm_journey_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_key = hashlib.sha256((endpoint + canonical(request_body)).encode()).hexdigest()
        cache = cache_dir / (cache_key + ".json")
        if cache.exists():
            envelope = json.loads(cache.read_text(encoding="utf-8"))
            raw_text = envelope["raw_response_text"]
            raw = json.loads(raw_text)
            record["cache_hit"] = True
            record["cache_original_source"] = "provider_live"
        else:
            request = urllib.request.Request(endpoint, data=canonical(request_body).encode(),
                                             headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            with _transport(request) as response:
                raw_bytes = response.read(2_000_001)
                if len(raw_bytes) > 2_000_000:
                    raw_text = raw_bytes[:2_000_000].decode("utf-8", errors="replace")
                    raise ValueError("Provider response exceeds audit size limit; truncated response preserved")
                raw_text = raw_bytes.decode("utf-8", errors="replace")
            raw = json.loads(raw_text)
        record.update(raw_response_text=raw_text, raw_response=raw, usage=raw.get("usage"),
                      latency_ms=round((time.monotonic()-start)*1000, 2))
        # Raw output is durable even when the subsequent action is illegal.
        audit.append({**record, "event": "response_received"})
        if raw["choices"][0].get("finish_reason") != "stop":
            raise ValueError("Provider response did not finish normally; truncated or filtered output is not accepted")
        decision = json.loads(raw["choices"][0]["message"]["content"])
        record["raw_decision"] = decision
        validate_english_output(decision)
        clean = validate_decision(decision, context)
        audit.append({**record, "event": "decision_validated", "validation": "passed", "validated_decision": clean})
        if not record["cache_hit"]:
            cache.write_text(json.dumps(sanitize({"raw_response_text": raw_text, "source": "provider_live", "model": model,
                                                  "prompt_version": PROMPT_VERSION}), ensure_ascii=False), encoding="utf-8")
        return clean
    except Exception as error:
        if isinstance(error, urllib.error.HTTPError):
            try:
                raw_text = error.read(2_000_000).decode("utf-8", errors="replace")
            except OSError:
                pass
        audit.append({**record, "event": "decision_failed", "raw_response_text": raw_text,
                      "validation": "failed", "error_type": type(error).__name__, "error": str(error),
                      "latency_ms": round((time.monotonic()-start)*1000, 2)})
        raise ValueError(f"Live journey failed; raw request and response retained in run {audit.run_id}. No simulated result was substituted.") from None


def run_journey(mode="deterministic", count=14, seed=117, membership_fee=399, member_fare=70):
    if mode not in ("deterministic", "live"):
        raise ValueError("Journey mode must be deterministic or live")
    limit = 14 if mode == "live" else 100
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= limit:
        raise ValueError(f"count must be 1..{limit}")
    source = "provider_live" if mode == "live" else "deterministic_assumption"
    people = [enrich(p, i) for i, p in enumerate(population(count, seed))]
    worlds = [initial_world(p, member_fare, membership_fee, "panel") for p in people]
    audit = Audit(source, {"mode": mode, "scenario_mode": "journey", "prompt_version": PROMPT_VERSION,
                           "response_language": RESPONSE_LANGUAGE, "currency": CURRENCY, "output_contract": CONTRACT_VERSION,
                           "customers": count, "seed": seed, "membership_fee": membership_fee, "member_fare": member_fare})
    results = []
    try:
        for world in worlds:
            events = []
            while world["stage_index"] < len(STAGES):
                packet = packet_for(world)
                if mode == "live":
                    decision = provider_decision(packet, audit)
                else:
                    decision = deterministic(packet["context"])
                    audit.append({"event": "decision_generated", "source": source, "model": None,
                                  "prompt_version": PROMPT_VERSION, "packet": packet,
                                  "request": {"context": packet["context"]}, "raw_response": decision,
                                  "usage": None, "latency_ms": 0, "cache_hit": False})
                clean = apply_decision(world, decision)
                event = {"packet": packet, "decision": clean, "state_after": copy.deepcopy(world["state"]),
                         "source": source, "inventory_committed": False}
                audit.append({"event": "state_transition", "validation": "passed", **event})
                events.append(event)
            purchase = next((e for e in events if e["decision"]["action"] in ("BUY_MEMBER", "BUY_REGULAR")), None)
            booking_event = purchase or events[3]
            results.append({"person": world["person"], "context": events[0]["packet"]["context"],
                            "decision": events[0]["decision"], "booking_context": booking_event["packet"]["context"],
                            "booking_decision": {**booking_event["decision"], "inventory_committed": False, "source": source},
                            "events": events, "final_state": copy.deepcopy(world["state"])})
        summary = {"customers": count, "joined": sum(w["state"]["joined_this_run"] for w in worlds),
                   "existing_members": sum(p["membership_active"] for p in people),
                   "booked": sum(w["state"]["ticket_spend"] > 0 for w in worlds),
                   "cancelled": sum(w["state"]["booking_cancelled"] for w in worlds),
                   "completed_stages": sum(w["stage_index"] for w in worlds)}
        result = {"mode": mode, "scenario_mode": "journey", "source": source, "prompt_version": PROMPT_VERSION,
                  "response_language": RESPONSE_LANGUAGE, "currency": CURRENCY, "output_contract": CONTRACT_VERSION,
                  "run_id": audit.run_id, "audit_path": f"data/private/llm_runs/{audit.run_id}", "results": results,
                  "summary": summary, "limitations": ["Synthetic scenario decisions, not observed HK Express market behaviour.",
                  "One detailed trip is followed across six stages; full-term benefit and future trips are stated expectations, not fabricated usage.",
                  "Each person's panel has independent scenario inventory; no live ticket reservation or payment.",
                  "Membership applies only to holder; companions pay normal fares. Renewal intention never charges another fee."]}
        (audit.path / "result.json").write_text(json.dumps(sanitize(result), ensure_ascii=False, indent=2), encoding="utf-8")
        audit.update(status="completed", summary=summary)
        return result
    except Exception as error:
        audit.append({"event": "run_failed", "error_type": type(error).__name__, "error": str(error)})
        audit.update(status="failed", error=str(error), completed_customers=len(results))
        raise
