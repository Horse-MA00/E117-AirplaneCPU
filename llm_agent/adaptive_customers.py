"""Bounded parallel purchase-intent calls and auditable feedback analysis.

Parallelism applies to independent intentions at one shared quoted snapshot.
The caller must clear inventory afterwards in a recorded order; this adapter
never reserves seats, moves money or fabricates a substitute for a failed LLM.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .audit import sanitize
from .journey_runner import _transport
from .output_contract import validate_english_output

VERSION = "adaptive-member-decisions-v1"
PROMPTS = {kind: Path(__file__).parent / "prompts" / filename for kind, filename in (
    ("customer", "adaptive_customer_v1_en.txt"), ("analyst", "adaptive_analyst_v1_en.txt"))}


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def prompt_metadata():
    return {"version": VERSION, "prompts": {key: {"path": str(path.relative_to(Path(__file__).resolve().parents[1])),
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for key, path in PROMPTS.items()}}


def _money(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return float(value)


def public_observation(observation):
    """Allowlist public information; exclude sampling weights and optimizer state."""
    original = observation["person"]
    person_fields = ("customer_id", "segment", "segment_label", "base_fare_budget", "flexibility_days",
                     "minimum_notice_days", "eligible", "eligibility_reason", "date_match", "companions_confirmed",
                     "travel_party_context")
    person = {key: copy.deepcopy(original[key]) for key in person_fields if key in original}
    person.update(membership_active=True, membership_valid_at_departure=True, own_ticket_only=True, party_size=1)
    budget = _money(person["base_fare_budget"], "base_fare_budget")
    normal = _money(observation["normal_fare"], "normal_fare")
    fare = observation.get("member_fare")
    if fare is not None:
        fare = _money(fare, "member_fare")
    quota = observation.get("quota", 0)
    if isinstance(quota, bool) or not isinstance(quota, int) or quota < 0:
        raise ValueError("quota must be a nonnegative integer")
    eligible = person.get("eligible") is True
    allowed = ["DECLINE"]
    if eligible and observation.get("regular_available", True) and normal <= budget:
        allowed.append("BUY_REGULAR")
    if eligible and quota > 0 and fare is not None and fare <= budget:
        allowed.append("BUY_MEMBER")
    flight_fields = ("flight_id", "origin", "destination", "departure_date", "departure_time", "as_of_day")
    flight = {key: copy.deepcopy(observation.get("flight", {})[key]) for key in flight_fields
              if key in observation.get("flight", {})}
    return {"person": person, "flight": flight, "normal_fare": normal, "member_fare": fare,
            "quota": quota, "allowed_actions": allowed, "response_language": "en", "currency": "HKD",
            "payment_scope": "One existing member's basic fare only; all other payments are outside this decision.",
            "inventory_rule": "Simultaneous intentions, no seat reserved; allocation is cleared in a recorded order afterwards."}


def validate_decision(value, observation):
    validate_english_output(value)
    if value.get("action") not in observation["allowed_actions"]:
        raise ValueError("Customer selected an unavailable or unaffordable action")
    fallback = value.get("fallback_action", "DECLINE")
    if fallback not in ("BUY_REGULAR", "DECLINE"):
        raise ValueError("Invalid fallback action")
    if fallback == "BUY_REGULAR" and (value["action"] != "BUY_MEMBER" or "BUY_REGULAR" not in observation["allowed_actions"]):
        raise ValueError("Fallback regular purchase is not affordable or applicable")
    if len(value["reason"]) > 1800:
        raise ValueError("Customer reason is too long")
    return {"action": value["action"], "fallback_action": fallback,
            "reason_code": value.get("reason_code", "UNSPECIFIED"), "reason": value["reason"]}


def _feedback_rows(context):
    rows = context.get("feedback", [])
    if not isinstance(rows, list):
        raise ValueError("Analyst feedback must be an array")
    return rows


def validate_analysis(value, context):
    if not isinstance(value, dict):
        raise ValueError("Expected an analysis object")
    for key in ("summary", "hypothesis"):
        validate_english_output({"reason": value.get(key), "reason_code": "ANALYSIS"})
        if len(value[key]) > 2500:
            raise ValueError("Analyst text is too long")
    counts = value.get("reason_counts")
    categories = {"price", "date", "companions", "availability", "other"}
    if not isinstance(counts, dict) or set(counts) != categories:
        raise ValueError("Analyst must provide the five reason counts")
    feedback = _feedback_rows(context)
    if any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= len(feedback) for v in counts.values()):
        raise ValueError("Invalid analyst counts")
    if sum(counts.values()) > len(feedback):
        raise ValueError("Analyst double-counted customer feedback")
    known = {row.get("customer_id") for row in feedback if isinstance(row, dict)}
    ids = value.get("evidence_customer_ids")
    if not isinstance(ids, list) or len(ids) > len(feedback) or any(not isinstance(cid, str) or cid not in known for cid in ids):
        raise ValueError("Analyst cited an unknown customer")
    return {"summary": value["summary"], "reason_counts": counts, "hypothesis": value["hypothesis"],
            "evidence_customer_ids": list(dict.fromkeys(ids))}


def synthetic_probability(observation):
    """Independent assumed oracle for offline tests, never a real-user claim."""
    visible = public_observation(observation) if "allowed_actions" not in observation else observation
    p = visible["person"]
    fare = visible["member_fare"] if "BUY_MEMBER" in visible["allowed_actions"] else visible["normal_fare"]
    if not p.get("eligible") or fare > p["base_fare_budget"]:
        return 0.
    # A diverse, monotone random-utility curve creates an interior revenue
    # tradeoff for many budgets. These coefficients are declared assumptions.
    offset = {"urgent_trip": 1., "visiting_friends": .45, "small_business": .6,
              "student": -.25, "infrequent": -.25}.get(p.get("segment"), 0.)
    utility = 2.4 + offset + .04*p.get("flexibility_days", 0) - 4.2*fare/max(1., p["base_fare_budget"])
    return 1/(1+math.exp(-max(-40., min(40., utility))))


class DecisionClient:
    def __init__(self, mode="live", max_calls=0, concurrency=4, audit_callback=None, seed=117, use_cache=False):
        if mode not in ("live", "synthetic"):
            raise ValueError("mode must be live or synthetic")
        if isinstance(max_calls, bool) or not isinstance(max_calls, int) or not 0 <= max_calls <= 10000:
            raise ValueError("max_calls must be 0..10000")
        if isinstance(concurrency, bool) or not isinstance(concurrency, int) or not 1 <= concurrency <= 8:
            raise ValueError("concurrency must be 1..8")
        self.mode, self.max_calls, self.concurrency, self.seed = mode, max_calls, concurrency, seed
        self._audit_callback = audit_callback or (lambda record: None)
        self._lock, self._audit_lock = threading.Lock(), threading.Lock()
        self._cache, self.use_cache = {}, bool(use_cache)
        self._started, self._active = time.monotonic(), 0
        self._stopped_after_failure = False
        self._stats = {"provider_calls": 0, "fresh_responses": 0, "cache_hits": 0, "forced": 0,
                       "failures": 0, "synthetic_choices": 0, "total_tokens": 0, "peak_parallel_calls": 0,
                       "customer_calls": 0, "analyst_calls": 0, "key_slots": {"primary": 0, "secondary": 0}}
        self._keys = []
        for slot, env in (("primary", "LLM_API_KEY"), ("secondary", "LLM_API_KEY_SECONDARY")):
            key = os.environ.get(env, "")
            if key and key not in [k for _, k in self._keys]:
                self._keys.append((slot, key))
        self._endpoint = os.environ.get("LLM_API_URL", "")
        self._model = os.environ.get("LLM_MODEL", "")
        if mode == "live":
            parsed = urllib.parse.urlsplit(self._endpoint)
            if not self._keys or not self._model:
                raise ValueError("Live provider credentials/model are not configured")
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("LLM endpoint must be HTTPS without embedded credentials or query parameters")

    def _audit(self, value):
        # The shared sanitizer redacts environment secrets, and this extra pass
        # also redacts retained key values if the caller later changes its env.
        encoded = _canonical(sanitize({"recorded_at": time.time(), "version": VERSION, **value}))
        for _, key in self._keys:
            encoded = encoded.replace(key, "[REDACTED]")
        with self._audit_lock:
            self._audit_callback(json.loads(encoded))

    def stats(self):
        with self._lock:
            return copy.deepcopy(self._stats) | {"max_calls": self.max_calls, "remaining_calls": self.max_calls-self._stats["provider_calls"],
                "configured_key_slots": len(self._keys), "concurrency": self.concurrency,
                "peak_parallel": self._stats["peak_parallel_calls"], "stopped_after_failure": self._stopped_after_failure,
                "elapsed_seconds": round(time.monotonic()-self._started, 3)}

    def choose_many(self, observations):
        with ThreadPoolExecutor(max_workers=self.concurrency, thread_name_prefix="member-intent") as executor:
            # executor.map preserves input order even though responses finish in
            # a different order. Allocation must not depend on HTTP latency.
            return list(executor.map(self.choose, observations))

    def choose(self, observation):
        visible = public_observation(observation)
        learning = bool(visible["person"]["eligible"] and visible["member_fare"] is not None and visible["quota"] > 0)
        if len(visible["allowed_actions"]) == 1:
            reason = (visible["person"].get("eligibility_reason", "This trip does not match my requirements.")
                      if not visible["person"].get("eligible") else
                      "No offered ticket is both available and within my basic-fare budget.")
            clean = {"action": "DECLINE", "fallback_action": "DECLINE", "reason_code": "ENVIRONMENT_FORCED", "reason": reason}
            with self._lock:
                self._stats["forced"] += 1
            record = {"decision": clean, "observation": visible, "learning_eligible": learning,
                      "source": "environment_forced", "provider_call": False, "cache_hit": False, "forced": True, "latency_ms": 0}
            self._audit({"event": "customer_forced", **record})
            return record
        if self.mode == "synthetic":
            digest = hashlib.sha256(f"{self.seed}:{visible['person']['customer_id']}:choice".encode()).digest()
            uniform = int.from_bytes(digest[:8], "big") / 2**64
            probability = synthetic_probability(visible)
            action = "BUY_MEMBER" if "BUY_MEMBER" in visible["allowed_actions"] else "BUY_REGULAR"
            bought = uniform < probability
            regular = {**visible, "member_fare": None, "allowed_actions": [x for x in visible["allowed_actions"] if x != "BUY_MEMBER"]}
            fallback = "BUY_REGULAR" if (bought and action == "BUY_MEMBER" and "BUY_REGULAR" in visible["allowed_actions"]
                         and uniform < synthetic_probability(regular)) else "DECLINE"
            clean = {"action": action if bought else "DECLINE", "fallback_action": fallback,
                     "reason_code": "SYNTHETIC_VALUE" if bought else "SYNTHETIC_PRICE",
                     "reason": "The declared synthetic utility makes this ticket worthwhile." if bought else
                               "At this basic fare the declared synthetic utility favours not travelling."}
            with self._lock:
                self._stats["synthetic_choices"] += 1
            record = {"decision": clean, "observation": visible, "learning_eligible": learning,
                      "source": "synthetic_random_utility", "provider_call": False, "cache_hit": False,
                      "forced": False, "latency_ms": 0, "synthetic_purchase_probability": probability}
            self._audit({"event": "customer_synthetic", **record})
            return record
        record = self._call("customer", visible, lambda value: validate_decision(value, visible))
        return {**record, "observation": visible, "learning_eligible": learning}

    def analyse(self, context):
        context = copy.deepcopy(context)
        if self.mode == "synthetic":
            counts = dict.fromkeys(("price", "date", "companions", "availability", "other"), 0)
            for row in _feedback_rows(context):
                code = str(row.get("decision", {}).get("reason_code", ""))
                counts["price" if "PRICE" in code else "other"] += 1
            analysis = {"summary": "Synthetic feedback is recorded separately from live LLM feedback.", "reason_counts": counts,
                        "hypothesis": "Test whether a different basic fare improves the observed purchase and revenue tradeoff.",
                        "evidence_customer_ids": [r["customer_id"] for r in _feedback_rows(context)[:3] if "customer_id" in r]}
            record = {"analysis": analysis, "source": "synthetic_analysis", "provider_call": False,
                      "cache_hit": False, "forced": False, "latency_ms": 0}
            self._audit({"event": "analyst_synthetic", **record})
            return record
        return self._call("analyst", context, lambda value: validate_analysis(value, context))

    def _call(self, kind, context, validator):
        prompt = PROMPTS[kind].read_text(encoding="utf-8")
        body = {"model": self._model, "messages": [{"role": "system", "content": prompt},
                {"role": "user", "content": _canonical(context)}], "temperature": 0,
                "max_tokens": 550 if kind == "customer" else 850, "response_format": {"type": "json_object"}}
        if urllib.parse.urlsplit(self._endpoint).hostname == "api.deepseek.com":
            body["thinking"] = {"type": "disabled"}
        context_hash = hashlib.sha256((self._endpoint + _canonical(body)).encode()).hexdigest()
        with self._lock:
            cached = copy.deepcopy(self._cache.get(context_hash)) if self.use_cache else None
            if cached is not None:
                self._stats["cache_hits"] += 1
            else:
                if self._stopped_after_failure:
                    raise ValueError("Live requests stopped after a provider or validation failure; queued requests were not dispatched")
                if self._stats["provider_calls"] >= self.max_calls:
                    raise ValueError("Live call budget exhausted; no additional requests were dispatched")
                slot, key = self._keys[self._stats["provider_calls"] % len(self._keys)]
                self._stats["provider_calls"] += 1
                self._stats[f"{kind}_calls"] += 1
                self._stats["key_slots"][slot] += 1
                self._active += 1
                self._stats["peak_parallel_calls"] = max(self._stats["peak_parallel_calls"], self._active)
        if cached is not None:
            result = {**cached, "source": "provider_cache", "provider_call": False, "cache_hit": True, "latency_ms": 0}
            self._audit({"event": f"{kind}_cache", "context_sha256": context_hash, **result})
            return result
        started = time.monotonic()
        request_record = {"kind": kind, "context_sha256": context_hash, "request": body,
                          "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "key_slot": slot,
                          "model": self._model, "source": "provider_live"}
        raw_text = None
        try:
            self._audit({"event": f"{kind}_request", **request_record})
            request = urllib.request.Request(self._endpoint, data=_canonical(body).encode(),
                      headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            with _transport(request) as response:
                raw_bytes = response.read(2_000_001)
                raw_text = raw_bytes[:2_000_000].decode("utf-8", errors="replace")
                if len(raw_bytes) > 2_000_000:
                    raise ValueError("Provider response exceeds the audit limit")
            raw = json.loads(raw_text)
            elapsed = round((time.monotonic()-started)*1000, 2)
            self._audit({"event": f"{kind}_response", **request_record, "raw_response_text": raw_text,
                         "usage": raw.get("usage"), "latency_ms": elapsed})
            with self._lock:
                self._stats["fresh_responses"] += 1
                usage = raw.get("usage")
                tokens = usage.get("total_tokens", 0) if isinstance(usage, dict) else 0
                if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0:
                    self._stats["total_tokens"] += tokens
            choice = raw["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise ValueError("Provider response was truncated or did not finish normally")
            clean = validator(json.loads(choice["message"]["content"]))
            result = {"decision" if kind == "customer" else "analysis": clean, "source": "provider_live",
                      "provider_call": True, "cache_hit": False, "forced": False,
                      "latency_ms": elapsed, "key_slot": slot, "usage": raw.get("usage")}
            self._audit({"event": f"{kind}_validated", "context_sha256": context_hash, "validation": "passed", **result})
            if self.use_cache:
                with self._lock:
                    self._cache[context_hash] = copy.deepcopy(result)
            return result
        except Exception as error:
            # Stop queued work immediately, before reading an HTTP error body
            # or writing its audit. Already-dispatched requests may complete.
            with self._lock:
                self._stopped_after_failure = True
                self._stats["failures"] += 1
            if isinstance(error, urllib.error.HTTPError):
                try:
                    raw_text = error.read(2_000_000).decode("utf-8", errors="replace")
                except OSError:
                    pass
            self._audit({"event": f"{kind}_failed", **request_record, "raw_response_text": raw_text,
                         "error_type": type(error).__name__, "error": str(error), "validation": "failed",
                         "latency_ms": round((time.monotonic()-started)*1000, 2)})
            raise ValueError(f"Live {kind} response failed validation or transport; raw output was audited and no substitute was used") from None
        finally:
            with self._lock:
                self._active -= 1
