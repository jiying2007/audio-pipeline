#!/usr/bin/env python3
"""Independent confirmation for the physically valid freeze-geometry hypothesis."""

from __future__ import annotations
import argparse, json
from pathlib import Path

def load_json(path: Path) -> dict:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise ValueError(f"{path}: object required")
    return value

def require_contract(c: dict) -> None:
    if c.get("authority")!="CANDIDATE_ZERO_SINGLE_HYPOTHESIS_CONFIRMATION_ONLY":
        raise ValueError("authority drift")
    if c.get("candidate_limit")!=0 or c.get("confirmation_limit")!=1:
        raise ValueError("confirmation budget drift")
    if c["hypothesis"]["mode"]!="freeze_geometry":
        raise ValueError("confirmation mode drift")
    if int(c["hypothesis"]["required_recovery_time_ms"])!=0:
        raise ValueError("required recovery drift")
    for k,v in c["preregistered_rules"].items():
        if k.startswith("no_") and v is not True:
            raise ValueError(f"rule drift: {k}")

def evaluate(receipts: list[dict], c: dict) -> dict:
    require_contract(c)
    expected=sorted(int(x) for x in c["corpus"]["fresh_seeds"])
    by_seed={int(x["seed"]):x for x in receipts}
    if sorted(by_seed)!=expected: raise ValueError("fresh seed mismatch")
    per=[]
    required=int(c["hypothesis"]["required_recovery_time_ms"])
    for seed in expected:
        r=by_seed[seed]
        cf=r["counterfactuals"]["freeze_geometry"]
        confirmed=bool(cf["physically_admissible"]) and not bool(cf.get("censored",False)) and int(cf["recovery_time_ms"])==required
        per.append({
            "seed":seed,
            "standard_aec_recovery_ms":r["standard_aec_recovery_ms"],
            "freeze_geometry_physically_admissible":bool(cf["physically_admissible"]),
            "freeze_geometry_recovery_ms":cf["recovery_time_ms"],
            "freeze_scale":r["counterfactuals"]["freeze_scale"],
            "confirmed_on_seed":confirmed,
        })
    count=sum(x["confirmed_on_seed"] for x in per)
    all_ok=count==len(expected)
    return {
        "schema_version":1,
        "investigation_id":c["id"],
        "fresh_seeds":expected,
        "outcome":"CONFIRMED" if all_ok else "REJECTED",
        "confirmed_seed_count":count,
        "total_seed_count":len(expected),
        "required_recovery_time_ms":required,
        "per_seed":per,
        "candidate_authority":False,
        "root_cause_claim_authority":False,
        "s004_open":False,
    }

def self_test() -> None:
    c={"id":"self-test","authority":"CANDIDATE_ZERO_SINGLE_HYPOTHESIS_CONFIRMATION_ONLY","candidate_limit":0,"confirmation_limit":1,
       "corpus":{"fresh_seeds":[1,2]},"hypothesis":{"mode":"freeze_geometry","required_recovery_time_ms":0},
       "preregistered_rules":{"no_parameter_search":True}}
    receipts=[]
    for seed in (1,2):
        receipts.append({"seed":seed,"standard_aec_recovery_ms":100,
          "counterfactuals":{"freeze_geometry":{"physically_admissible":True,"censored":False,"recovery_time_ms":0},
                             "freeze_scale":{"physically_admissible":True,"recovery_time_ms":100}}})
    assert evaluate(receipts,c)["outcome"]=="CONFIRMED"
    receipts[1]["counterfactuals"]["freeze_geometry"]["recovery_time_ms"]=50
    assert evaluate(receipts,c)["outcome"]=="REJECTED"
    print("geometry-freeze confirmation self-test: OK")

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--contract",type=Path)
    p.add_argument("--receipt",type=Path,action="append")
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    if a.self_test:
        self_test(); return 0
    if a.contract is None or not a.receipt or a.output is None:
        p.error("--contract --receipt --output required")
    c=load_json(a.contract)
    out=evaluate([load_json(x) for x in a.receipt],c)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"outcome":out["outcome"],"confirmed_seed_count":out["confirmed_seed_count"],"total_seed_count":out["total_seed_count"],"per_seed":out["per_seed"]},sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
