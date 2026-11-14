"""Audited LLM proposals for the isolated ticket-base-revenue experiment.

The provider proposes a price, never a customer action or accounting outcome.
The caller reserves its finite call budget and replays/validates proposals. There
is no mathematical price fallback, retry loop, or implicit duplicate adjustment.
"""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request

from .journey_runner import _transport
from .output_contract import validate_english_output

VERSION = "llm-ticket-revenue-proposer-v1"
PROMPT = Path(__file__).parent / "prompts/price_optimizer_v1_en.txt"
MAX_RESPONSE_BYTES = 2_000_000
_CONTEXT_FIELDS = {"fare_min", "fare_max", "initial_fare", "round", "history", "scope",
                   "objective", "baseline", "constraints", "feedback", "release_fraction"}
_HIDDEN_KEYS = {"seed", "simulation_seed", "ground_truth", "future_events", "future_quotes",
                "latent_beta", "latent_rate", "latent_scale", "validation", "holdout",
                "holdout_seeds", "validation_seeds", "world_state", "state", "provider_api_key"}


def _observed(value):
    """Strip known hidden fields even if accidentally passed by a future caller."""
    if isinstance(value, dict):
        return {str(k): _observed(v) for k, v in value.items()
                if str(k).lower() not in _HIDDEN_KEYS
                and not str(k).lower().startswith(("future_", "holdout_", "latent_"))}
    if isinstance(value, list):
        return [_observed(v) for v in value]
    return value


def _cents(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite JSON number")
    amount = Decimal(str(value)) * 100
    if amount != amount.to_integral_value():
        raise ValueError(f"{name} must have at most two decimal places")
    return int(amount)


def proposal_context(context):
    if not isinstance(context, dict):
        raise ValueError("Price proposal context must be an object")
    visible = _observed({k: v for k, v in context.items() if k in _CONTEXT_FIELDS})
    if visible.get("objective") != "base_ticket_revenue":
        raise ValueError("This proposer only supports base_ticket_revenue")
    low, high = (_cents(visible.get(k), k) for k in ("fare_min", "fare_max"))
    initial = _cents(visible.get("initial_fare"), "initial_fare")
    if low < 0 or low >= high or not low <= initial <= high:
        raise ValueError("Fare bounds must be nonnegative, increasing, and contain the initial fare")
    history = visible.get("history")
    if not isinstance(history, list) or not history:
        raise ValueError("At least one completed price evaluation is required")
    for row in history:
        if not isinstance(row, dict):
            raise ValueError("Each history row must be an object")
        _cents(row.get("fare"), "history fare")
    # Raises on unsupported objects/non-finite metrics before any transport.
    json.dumps(visible, allow_nan=False)
    return visible


def validate_proposal(proposal, context):
    if not isinstance(proposal, dict) or set(proposal) != {"fare", "reason", "hypothesis"}:
        raise ValueError("Proposal must contain exactly fare, reason and hypothesis")
    cents = _cents(proposal["fare"], "Proposed fare")
    low, high = (_cents(context[k], k) for k in ("fare_min", "fare_max"))
    if not low <= cents <= high:
        raise ValueError("Proposed fare is outside the authorized bounds")
    seen = {_cents(row["fare"], "history fare") for row in context["history"]}
    if cents in seen:
        raise ValueError("Proposed fare has already been evaluated; no replacement price was substituted")
    for key, limit in (("reason", 1200), ("hypothesis", 600)):
        value = proposal[key]
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f"{key} must be an English string of at most {limit} characters")
        validate_english_output({"reason": value})
    return {"fare": cents / 100, "reason": proposal["reason"], "hypothesis": proposal["hypothesis"]}


def propose(context, audit):
    """Request exactly one bounded proposal and preserve raw provider evidence."""
    visible = proposal_context(context)
    canonical = json.dumps(visible, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    context_hash = hashlib.sha256(canonical.encode()).hexdigest()
    prompt = PROMPT.read_text(encoding="utf-8")
    endpoint, key, model = (os.environ.get(k, "") for k in ("LLM_API_URL", "LLM_API_KEY", "LLM_MODEL"))
    parsed = urllib.parse.urlsplit(endpoint)
    body = {"model": model, "messages": [{"role": "system", "content": prompt},
            {"role": "user", "content": canonical}], "temperature": 0, "max_tokens": 900,
            "response_format": {"type": "json_object"}}
    if parsed.hostname == "api.deepseek.com":
        body["thinking"] = {"type": "disabled"}
    record = {"source": "provider_live", "role": "price_optimizer", "prompt_version": VERSION,
              "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "context_sha256": context_hash,
              "request": body, "model": model, "cache_hit": False, "provider_call": False,
              "validation": "pending"}
    audit.append({**record, "event": "price_proposal_request"})
    started, raw_text = time.monotonic(), None
    try:
        if not endpoint or not key or not model:
            raise ValueError("Price optimizer provider is not configured")
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Provider must use HTTPS without embedded credentials or query")
        request = urllib.request.Request(endpoint, data=json.dumps(body, ensure_ascii=False).encode(),
                    headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        record["provider_call"] = True
        audit.append({**record, "event": "price_proposal_dispatched"})
        with _transport(request) as response:
            raw_bytes = response.read(MAX_RESPONSE_BYTES + 1)
        raw_text = raw_bytes[:MAX_RESPONSE_BYTES].decode("utf-8", errors="replace")
        if len(raw_bytes) > MAX_RESPONSE_BYTES:
            raise ValueError("Oversized response; truncated raw text retained")
        raw = json.loads(raw_text)
        record.update(raw_response_text=raw_text, raw_response=raw, usage=raw.get("usage"),
                      latency_ms=round((time.monotonic() - started) * 1000, 2))
        audit.append({**record, "event": "price_proposal_response"})
        if raw["choices"][0].get("finish_reason") != "stop":
            raise ValueError("Price proposal did not finish normally")
        proposal = validate_proposal(json.loads(raw["choices"][0]["message"]["content"]), visible)
        audit.append({**record, "event": "price_proposal_validated", "proposal": proposal, "validation": "passed"})
        return {**proposal, "source": "provider_live", "provider_call": True, "cache_hit": False,
                "context_sha256": context_hash, "prompt_version": VERSION}
    except Exception as error:
        if isinstance(error, urllib.error.HTTPError):
            try:
                raw_text = error.read(MAX_RESPONSE_BYTES).decode("utf-8", errors="replace")
            except OSError:
                pass
        audit.append({**record, "event": "price_proposal_failed", "raw_response_text": raw_text,
                      "validation": "failed", "error_type": type(error).__name__, "error": str(error),
                      "latency_ms": round((time.monotonic() - started) * 1000, 2)})
        raise ValueError(f"LLM price proposal failed; inspect run {audit.run_id}. No fallback price was substituted.") from None
