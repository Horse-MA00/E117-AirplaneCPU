"""Uncached, paired price/repetition/order/language diagnostics for v3 prompts."""
from __future__ import annotations

import argparse
import copy
from .file_lock import exclusive_lock
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import uuid

from .audit import Audit, sanitize
from .experiment import load_local_env
from .journey import _save, canonical
from .market_adapter import choose, PROMPTS, VERSION, public_observation
from .market_experiment import iter_audit, runtime_counts


def _price_fixture(observation, fare, fee=199):
    """Only alter the member fare/fee and their displayed payable consequences."""
    out = copy.deepcopy(observation)
    out["membership"]["member_base_fare"] = fare
    out["membership"]["fee"] = fee
    for field in ("options", "legal_options"):
        for option in out[field]:
            if option["action"] == "JOIN_PASS":
                option["price"] = fee
    for option in out.get("current_quote_reference", []):
        if option["action"] == "BUY_MEMBER":
            option["price_breakdown"]["member_base_fare"] = fare
            option["price"] = round(sum(option["price_breakdown"].values()), 2)
    return out


def create(output, seed=117):
    from backend.shared_market import create_market, next_observation, apply_decision
    output = Path(output)
    if (output / "probes.json").exists():
        raise ValueError("Probe suite already exists; resume it")
    output.mkdir(parents=True, exist_ok=True)
    state = create_market({"customer_count": 14, "flight_count": 9}, seed,
                          {"name": "PROBE_FIXED_ENVIRONMENT", "member_fare": 0, "membership_fee": 199, "open_day": 28, "release_fraction": .75})
    # Two scenarios with counterintuitive membership responses in the previous
    # v2 experiment, plus a frequent-travel positive control. New prompt/world.
    wanted = {f"SYN-{seed}-{i:05d}" for i in (1, 12, 4)}
    fixtures = {}
    while len(fixtures) < len(wanted):
        observation = next_observation(state)
        if observation is None:
            break
        cid = observation["customer_id"]
        if observation["stage"] == "subscription" and cid in wanted and cid not in fixtures:
            if "JOIN_PASS" not in observation["allowed_actions"]:
                raise ValueError("Probe fixture has no membership choice")
            fixtures[cid] = public_observation(observation)
        action = "DECLINE" if "DECLINE" in observation["allowed_actions"] else observation["allowed_actions"][0]
        options = [o for o in observation["options"] if o["action"] == action]
        apply_decision(state, {"action": action, "option_id": options[0]["id"] if options else None})
    if len(fixtures) != len(wanted):
        raise ValueError("Failed to construct all fixed customer fixtures")
    probes = []
    for cid, fixture in sorted(fixtures.items()):
        # Identical ID across price conditions prevents the ID encoding price.
        fixture["packet_id"] = f"price-probe:{cid}"
        for fare in (0, 30, 70, 100):
            for variant in ("base_en", "repeat_en_1", "repeat_en_2", "reversed_en", "base_zh"):
                observation = _price_fixture(fixture, fare)
                if variant == "reversed_en":
                    for key in ("allowed_actions", "options", "legal_options", "current_quote_reference"):
                        observation[key] = list(reversed(observation.get(key, [])))
                probes.append({"probe_id": f"{cid}-P{fare}-{variant}", "customer_id": cid, "fare": fare,
                               "fee": 199, "variant": variant, "language": "zh" if variant.endswith("zh") else "en",
                               "observation": observation, "completed": False})
    spec = {"run_id": "market-probes-"+uuid.uuid4().hex[:16], "prompt_version": VERSION,
            "prompt_hashes": {lang: hashlib.sha256(path.read_bytes()).hexdigest() for lang, path in PROMPTS.items()},
            "engine_sha256": hashlib.sha256((Path(__file__).resolve().parents[1]/"backend/shared_market.py").read_bytes()).hexdigest(),
            "source": "isolated_paired_diagnostic_not_market_outcome", "probes": probes,
            "design": "3 fixed synthetic people x 4 member base fares x 5 uncached presentations = 60 choices. Membership fee is fixed at HKD199. Base plus two fresh repeats, order reversal, English/Chinese system prompt.",
            "caveat": "Selected diagnostic cases are not a population sample; future opportunity and inventory are held fixed. No transactions execute in these isolated probes."}
    _save(output/"probes.json", spec)
    return {"run_id": spec["run_id"], "probes": len(probes)}


def report(output):
    spec = json.loads((Path(output)/"probes.json").read_text(encoding="utf-8"))
    complete = [p for p in spec["probes"] if p["completed"]]
    groups = {}
    for p in complete:
        groups.setdefault(p["customer_id"], []).append(p)
    repetitions, permutations, languages, monotonicity = [], [], [], []
    for cid, probes in groups.items():
        lookup = {(p["fare"],p["variant"]):p["result"]["decision"]["action"] for p in probes}
        for fare in (0,30,70,100):
            base = lookup.get((fare,"base_en"))
            if base is None:
                continue
            repeats = [lookup.get((fare,v)) for v in ("base_en","repeat_en_1","repeat_en_2")]
            repetitions.append({"customer_id":cid,"fare":fare,"actions":repeats,"complete":all(repeats),"disagreement":len({a for a in repeats if a is not None})>1})
            for variant, target in (("reversed_en", permutations),("base_zh",languages)):
                if (fare,variant) in lookup:
                    target.append({"customer_id":cid,"fare":fare,"base":base,"variant":lookup[(fare,variant)],"disagreement":base!=lookup[(fare,variant)]})
        for variant in ("base_en","repeat_en_1","repeat_en_2","reversed_en","base_zh"):
            actions = [(fare,lookup.get((fare,variant))) for fare in (0,30,70,100)]
            flags = [{"lower_fare":low,"higher_fare":high} for low,a in actions for high,b in actions
                     if low<high and a=="DECLINE" and b=="JOIN_PASS"]
            monotonicity.append({"customer_id":cid,"variant":variant,"actions":dict(actions),"higher_price_join_after_lower_price_decline":flags})
    return {"run_id":spec["run_id"],"prompt_version":VERSION,"design":spec["design"],"planned":len(spec["probes"]),"completed":len(complete),
            "runtime":runtime_counts(spec["run_id"]),"repetition_checks":repetitions,"order_checks":permutations,"language_checks":languages,
            "price_checks":monotonicity,"summary":{"repetition_disagreements":sum(r["disagreement"] for r in repetitions),
              "repetition_groups_tested":sum(bool(r["complete"]) for r in repetitions),"order_pairs_tested":len(permutations),"language_pairs_tested":len(languages),
              "order_disagreements":sum(r["disagreement"] for r in permutations),"language_disagreements":sum(r["disagreement"] for r in languages),
              "price_monotonicity_flags":sum(bool(r["higher_price_join_after_lower_price_decline"]) for r in monotonicity)},
            "limitations":[spec["caveat"],"A monotonicity flag is a model robustness warning, not proof that real customers must be monotonic.",
                           "No failed response is replaced by a deterministic choice; repeated calls bypass cache and consume real provider tokens.",
                           "These diagnostics assess sensitivity, not real-world calibration or predictive accuracy."]}


def run_batch(output,max_calls=60,workers=3):
    if not isinstance(max_calls,int) or not 0<=max_calls<=60 or not 1<=workers<=5:
        raise ValueError("max_calls must be0..60; workers1..5")
    output=Path(output)
    with exclusive_lock(output / ".run.lock"):
        return _run_batch(output,max_calls,workers)


def _run_batch(output,max_calls,workers):
    spec=json.loads((output/"probes.json").read_text(encoding="utf-8"))
    if spec["prompt_hashes"] != {lang:hashlib.sha256(path.read_bytes()).hexdigest() for lang,path in PROMPTS.items()}:
        raise ValueError("Prompt changed; create another probe experiment")
    audit=Audit("shared_market_behavior_probes",{"prompt_version":VERSION,"design":spec["design"]},run_id=spec["run_id"],resume=True)
    pending=[p for p in spec["probes"] if not p["completed"]][:max_calls]
    def invoke(probe):
        audit.append({"event":"behavior_probe_start","probe_id":probe["probe_id"],"variant":probe["variant"],"fare":probe["fare"],"fee":probe["fee"]})
        return choose(probe["observation"],"live",audit,probe["language"],use_cache=False)
    with ThreadPoolExecutor(max_workers=min(workers,3)) as pool:
        # A systemic failure stops after at most one three-request wave. Never
        # enqueue a whole 60-request suite into a broken transport.
        for start in range(0,len(pending),min(workers,3)):
            wave=pending[start:start+min(workers,3)]
            futures={pool.submit(invoke,p):p for p in wave}
            failed=0
            for future in as_completed(futures):
                probe=futures[future]
                try:
                    probe["result"]=future.result()
                    probe["completed"]=True
                    probe.pop("last_error",None)
                    audit.append({"event":"behavior_probe_completed","probe_id":probe["probe_id"],"result":probe["result"]})
                except Exception as error:
                    failed+=1
                    probe["last_error"]=str(error)
                    audit.append({"event":"behavior_probe_failed","probe_id":probe["probe_id"],"error":str(error)})
                _save(output/"probes.json",spec)
            if failed==len(wave):
                audit.append({"event":"behavior_transport_circuit_paused","failed_wave":failed,"remaining_not_dispatched":len(pending)-start-len(wave)})
                break
    result=report(output)
    audit.update(status="completed" if result["completed"]==result["planned"] else "paused",summary=result["summary"])
    _save(output/"report.json",result)
    return {key:result[key] for key in ("run_id","completed","planned","runtime","summary")}


def export_public(output,destination):
    import gzip
    output,destination=Path(output),Path(destination)
    destination.mkdir(parents=True,exist_ok=True)
    spec=json.loads((output/"probes.json").read_text(encoding="utf-8"))
    _save(destination/"probes.json",sanitize(spec))
    _save(destination/"report.json",sanitize(report(output)))
    count=0
    with (destination/"audit.jsonl.gz").open("wb") as raw:
        with gzip.GzipFile(filename="",fileobj=raw,mode="wb",mtime=0) as zipped:
            for record in iter_audit(spec["run_id"]):
                zipped.write((canonical(sanitize(record))+"\n").encode());count+=1
    _save(destination/"manifest.json",{"run_id":spec["run_id"],"synthetic_only":True,"audit_records":count,
          "files":{name:hashlib.sha256((destination/name).read_bytes()).hexdigest() for name in ("probes.json","report.json","audit.jsonl.gz")}})
    return {"destination":str(destination),"records":count}


def main():
    load_local_env()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=("create","run","report","export"))
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--destination",type=Path)
    parser.add_argument("--max-calls",type=int,default=60)
    parser.add_argument("--workers",type=int,default=3)
    args=parser.parse_args()
    if args.command=="create":result=create(args.output)
    elif args.command=="run":result=run_batch(args.output,args.max_calls,args.workers)
    elif args.command=="report":result=report(args.output)
    else:result=export_public(args.output,args.destination)
    print(json.dumps(result,ensure_ascii=False))


if __name__=="__main__":main()
