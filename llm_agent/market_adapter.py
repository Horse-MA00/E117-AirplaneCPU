"""Same public observation for rule and real-LLM choices in a shared market."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.parse
import urllib.request
import urllib.error

from .audit import sanitize
from .journey import canonical
from .journey_runner import _transport

VERSION = "shared-market-customer-v3"
PROMPTS = {lang: Path(__file__).parent / f"prompts/shared_market_v3_{lang}.txt" for lang in ("en", "zh")}
HIDDEN_KEYS = {"latent_beta", "latent_rate", "latent_scale", "future_events", "future_quotes", "ground_truth",
               "baseline_normal_intent", "normal_intent", "airline_cost", "airline_profit", "profit", "objective",
               "counterfactual_outcome", "policy_name", "policy", "scenario", "simulation_seed", "seed"}


def public_observation(value):
    if isinstance(value, dict):
        return {k: public_observation(v) for k, v in value.items() if k not in HIDDEN_KEYS}
    if isinstance(value, list):
        return [public_observation(x) for x in value]
    return copy.deepcopy(value)


def legal_choices(observation):
    options = observation.get("options", observation.get("legal_options", []))
    choices = []
    for action in observation["allowed_actions"]:
        matching = [option for option in options if option.get("action") == action]
        if matching:
            choices.extend((action, option["id"]) for option in matching)
        else:
            choices.append((action, None))
    return choices


def validate_decision(decision, observation):
    if not isinstance(decision, dict) or (decision.get("action"), decision.get("option_id")) not in legal_choices(observation):
        raise ValueError("Shared-market decision is not an available action/option pair")
    return {"action": decision["action"], "option_id": decision.get("option_id"),
            "reason_code": str(decision.get("reason_code", "UNSPECIFIED"))[:80],
            "reason": str(decision.get("reason", ""))[:1200],
            "confidence": decision.get("confidence", "medium") if decision.get("confidence", "medium") in ("low", "medium", "high") else "low"}


def choose(observation, mode, audit, language="en", use_cache=True):
    """Choose once. Illegal/failed provider outputs never become rule decisions."""
    if mode not in ("deterministic", "live") or language not in PROMPTS:
        raise ValueError("Invalid market choice mode or prompt language")
    visible = public_observation(observation)
    choices = legal_choices(visible)
    if not choices:
        raise ValueError("Environment supplied no legal choices")
    context_hash = hashlib.sha256(canonical(visible).encode()).hexdigest()
    if len(choices) == 1:
        action, oid = choices[0]
        decision = {"action": action, "option_id": oid, "reason_code": "ENVIRONMENT_FORCED",
                    "reason": "Only one legal action is available; no model choice was requested.", "confidence": "high"}
        audit.append({"event": "market_choice", "source": "environment_forced", "mode_requested": mode,
                      "prompt_version": VERSION, "observation": visible, "context_sha256": context_hash,
                      "decision": decision, "validation": "passed", "model": None, "usage": None, "cache_hit": False})
        return {"decision": decision, "source": "environment_forced", "forced": True, "cache_hit": False, "provider_call": False}
    if mode == "deterministic":
        from backend.shared_market import deterministic_decision
        decision = validate_decision(deterministic_decision(visible), visible)
        audit.append({"event": "market_choice", "source": "deterministic_assumption", "prompt_version": VERSION,
                      "observation": visible, "context_sha256": context_hash, "decision": decision,
                      "validation": "passed", "model": None, "usage": None, "cache_hit": False})
        return {"decision": decision, "source": "deterministic_assumption", "forced": False, "cache_hit": False, "provider_call": False}

    endpoint, key, model = (os.environ.get(k, "") for k in ("LLM_API_URL", "LLM_API_KEY", "LLM_MODEL"))
    body = {"model": model, "messages": [{"role": "system", "content": PROMPTS[language].read_text()},
            {"role": "user", "content": canonical(visible)}], "temperature": 0, "max_tokens": 700,
            "response_format": {"type": "json_object"}}
    parsed = urllib.parse.urlsplit(endpoint)
    if parsed.hostname == "api.deepseek.com":
        body["thinking"] = {"type": "disabled"}
    record = {"event": "market_request", "source": "provider_live", "prompt_version": VERSION,
              "prompt_language": language, "model": model, "request": body,
              "context_sha256": context_hash, "cache_hit": False, "provider_call": False, "validation": "pending"}
    audit.append(record)
    raw_text = None
    started = time.monotonic()
    try:
        if not endpoint or not key or not model:
            raise ValueError("Provider is not configured")
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Provider must use HTTPS without embedded credentials or query")
        cache_dir = audit.path.parent.parent / "llm_shared_market_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache = cache_dir / (hashlib.sha256((endpoint + canonical(body)).encode()).hexdigest() + ".json")
        if use_cache and cache.exists():
            raw_text = json.loads(cache.read_text())["raw_response_text"]
            record["cache_hit"] = True
            record["cache_original_source"] = "provider_live"
        else:
            request = urllib.request.Request(endpoint, data=canonical(body).encode(), headers={"Authorization": "Bearer " + key,
                                                                                          "Content-Type": "application/json"})
            record["provider_call"] = True
            with _transport(request) as response:
                raw_bytes = response.read(2_000_001)
            raw_text = raw_bytes[:2_000_000].decode("utf-8", errors="replace")
            if len(raw_bytes) > 2_000_000:
                raise ValueError("Oversized provider response; truncated raw text retained")
        raw = json.loads(raw_text)
        record.update(raw_response_text=raw_text, raw_response=raw, usage=raw.get("usage"),
                      latency_ms=round((time.monotonic()-started)*1000, 2))
        audit.append({**record, "event": "market_response"})
        if raw["choices"][0].get("finish_reason") != "stop":
            raise ValueError("Provider output did not finish normally")
        decision = validate_decision(json.loads(raw["choices"][0]["message"]["content"]), visible)
        audit.append({**record, "event": "market_choice", "decision": decision, "validation": "passed"})
        if use_cache and not record["cache_hit"]:
            cache.write_text(json.dumps(sanitize({"raw_response_text": raw_text, "source": "provider_live", "prompt_version": VERSION}), ensure_ascii=False), encoding="utf-8")
        return {"decision": decision, "source": "provider_live", "forced": False,
                "cache_hit": record["cache_hit"], "provider_call": not record["cache_hit"]}
    except Exception as error:
        if isinstance(error, urllib.error.HTTPError):
            try:
                raw_text = error.read(2_000_000).decode("utf-8", errors="replace")
            except OSError:
                pass
        audit.append({**record, "event": "market_choice_failed", "raw_response_text": raw_text,
                      "validation": "failed", "error_type": type(error).__name__, "error": str(error),
                      "latency_ms": round((time.monotonic()-started)*1000, 2)})
        raise ValueError(f"Shared-market provider choice failed; inspect run {audit.run_id}. No fallback choice was substituted.") from None
