#!/usr/bin/env python3
"""Confirm echo-path-change RES→NS recovery extension on 100w-50s geometry."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import build_aec_transition_corpus
from aec_recovery_rebaseline_100w50s import analyze_case

BASE_CASE = "echo-path-change"
PROFILES = ("prefix-res", "prefix-ns", "default")
PATH_KEYS = ("mic_audio","render_audio","clean_near_audio","echo_audio","vad_labels")


def load_json(path: Path) -> dict:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError(f"{path}: JSON object required")
    return value


def require_contract(c: dict) -> None:
    if c.get("authority")!="CANDIDATE_ZERO_SINGLE_HYPOTHESIS_CONFIRMATION":
        raise ValueError("authority drift")
    if c.get("candidate_limit")!=0 or c.get("confirmation_limit")!=0:
        raise ValueError("candidate budget drift")
    if tuple(c["corpus"]["profiles"])!=PROFILES:
        raise ValueError("profile set/order drift")
    if c["hypothesis"]["case_id"]!=BASE_CASE:
        raise ValueError("case drift")
    m=c["measurement"]
    expected={
        "geometry_id":"100w-50s",
        "post_window_ms":100,
        "post_stride_ms":50,
        "pre_baseline_window_ms":100,
        "pre_baseline_ms":[-1000,-200],
        "recovery_excess_db":3.01029995664,
        "continuous_hold_ms":300,
        "required_windows_for_300ms_coverage":5,
        "search_ms":[0,2500],
    }
    for k,v in expected.items():
        if m[k]!=v:
            raise ValueError(f"measurement drift: {k}")


def prefix_paths(case: dict,prefix: str)->dict:
    out=copy.deepcopy(case)
    for key in PATH_KEYS:
        value=out.get(key)
        if value:
            out[key]=f"{prefix}/{value}"
    return out


def build_corpus(output: Path,seed: int,seconds: float)->dict:
    output.mkdir(parents=True,exist_ok=True)
    source_root=output/"source"
    base=build_aec_transition_corpus.build(source_root,seed,seconds)
    by_id={case["case_id"]:case for case in base["cases"]}
    if BASE_CASE not in by_id:
        raise ValueError("echo-path case missing")
    source_case=by_id[BASE_CASE]
    cases=[]
    for order,profile in enumerate(PROFILES):
        case=prefix_paths(source_case,"source")
        case["case_id"]=f"{BASE_CASE}--{profile}"
        case["scenario"]=f"echo-res-ns-confirm::{source_case['scenario']}"
        case["processor_profile"]=profile
        case["expected"]={}
        dims=dict(case.get("dimensions",{}))
        dims.update({
            "base_case_id":BASE_CASE,
            "stage_profile":profile,
            "stage_order":order,
            "source_family":"deterministic-aec-transition-v1",
        })
        case["dimensions"]=dims
        cases.append(case)
    corpus={
        "schema_version":1,
        "corpus_id":f"aec-echo-res-ns-confirm-v1-seed-{seed}",
        "tier":"regression",
        "generator":{"name":"aec_echo_path_res_ns_confirmation.py","version":1,"seed":seed,"seconds":seconds},
        "sources":["deterministic-aec-transition-v1"],
        "sealed_data":True,
        "candidate_limit":0,
        "confirmation_limit":0,
        "promotion_allowed":False,
        "shipping_change_allowed":False,
        "cases":cases,
    }
    (output/"corpus.json").write_text(json.dumps(corpus,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return corpus


def run_seed(corpus_path:Path,report_path:Path,processor:Path,contract:dict)->dict:
    require_contract(contract)
    corpus=load_json(corpus_path)
    report=load_json(report_path)
    expected_ids={f"{BASE_CASE}--{p}" for p in PROFILES}
    if {c["case_id"] for c in corpus["cases"]}!=expected_ids:
        raise ValueError("corpus case-set drift")
    report_cases={c["case_id"]:c for c in report.get("cases",[])}
    if set(report_cases)!=expected_ids:
        raise ValueError("canonical report case-set drift")
    if not all(bool(x.get("passed",False)) for x in report_cases.values()):
        raise ValueError("canonical report policy failure")

    rows=[analyze_case(c,corpus_path,processor,contract) for c in corpus["cases"]]
    rows.sort(key=lambda r:r["stage_order"])
    if tuple(r["stage_profile"] for r in rows)!=PROFILES:
        raise ValueError("stage order drift")
    by={r["stage_profile"]:r for r in rows}
    res,ns,full=by["prefix-res"],by["prefix-ns"],by["default"]
    if res["censored"] or ns["censored"]:
        delta=None
        confirmed=False
    else:
        delta=int(ns["recovery_time_ms"])-int(res["recovery_time_ms"])
        confirmed=delta>=50
    return {
        "schema_version":1,
        "investigation_id":contract["id"],
        "seed":int(corpus["generator"]["seed"]),
        "authority":"candidate-zero-single-hypothesis-confirmation",
        "geometry_id":"100w-50s",
        "stages":rows,
        "hypothesis_observation":{
            "res_recovery_time_ms":res["recovery_time_ms"],
            "ns_recovery_time_ms":ns["recovery_time_ms"],
            "full_recovery_time_ms":full["recovery_time_ms"],
            "ns_minus_res_ms":delta,
            "confirmed_on_seed":confirmed,
        },
        "candidate_authority":False,
        "root_cause_claim_authority":False,
    }


def aggregate(items:list[dict],contract:dict)->dict:
    require_contract(contract)
    seeds=sorted(int(x) for x in contract["corpus"]["fresh_seeds"])
    by={int(x["seed"]):x for x in items}
    if sorted(by)!=seeds:
        raise ValueError("fresh seed mismatch")
    observations=[{"seed":s,**by[s]["hypothesis_observation"]} for s in seeds]
    confirmed=all(x["confirmed_on_seed"] for x in observations)
    return {
        "schema_version":1,
        "investigation_id":contract["id"],
        "fresh_seeds":seeds,
        "hypothesis":contract["hypothesis"],
        "observations":observations,
        "hypothesis_confirmed":confirmed,
        "outcome":"CONFIRMED" if confirmed else "REJECTED",
        "either_outcome_is_valid_evidence":True,
        "ns_root_cause_claim_authority":False,
        "ns_parameter_search_authority":False,
        "candidate_authority":False,
        "s004_open":False,
    }


def self_test()->None:
    c={
        "authority":"CANDIDATE_ZERO_SINGLE_HYPOTHESIS_CONFIRMATION",
        "candidate_limit":0,"confirmation_limit":0,
        "corpus":{"profiles":list(PROFILES)},
        "hypothesis":{"case_id":BASE_CASE},
        "measurement":{
            "geometry_id":"100w-50s","post_window_ms":100,"post_stride_ms":50,
            "pre_baseline_window_ms":100,"pre_baseline_ms":[-1000,-200],
            "recovery_excess_db":3.01029995664,"continuous_hold_ms":300,
            "required_windows_for_300ms_coverage":5,"search_ms":[0,2500],
        },
    }
    require_contract(c)
    print("echo-path RES-to-NS recovery confirmation self-test: OK")


def main()->int:
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("self-test")
    b=sub.add_parser("build"); b.add_argument("--output",type=Path,required=True); b.add_argument("--seed",type=int,required=True); b.add_argument("--seconds",type=float,default=6)
    r=sub.add_parser("run"); r.add_argument("--corpus",type=Path,required=True); r.add_argument("--report",type=Path,required=True); r.add_argument("--processor",type=Path,required=True); r.add_argument("--contract",type=Path,required=True); r.add_argument("--output",type=Path,required=True)
    a=sub.add_parser("aggregate"); a.add_argument("--contract",type=Path,required=True); a.add_argument("--input",type=Path,action="append",required=True); a.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    if args.command=="self-test":
        self_test(); return 0
    if args.command=="build":
        c=build_corpus(args.output,args.seed,args.seconds)
        print(json.dumps({"seed":args.seed,"cases":len(c["cases"]),"corpus":str(args.output/"corpus.json")},sort_keys=True)); return 0
    contract=load_json(args.contract)
    if args.command=="run":
        result=run_seed(args.corpus,args.report,args.processor,contract)
    else:
        result=aggregate([load_json(x) for x in args.input],contract)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    if args.command=="run":
        print(json.dumps({"seed":result["seed"],**result["hypothesis_observation"]},sort_keys=True))
    else:
        print(json.dumps({"outcome":result["outcome"],"hypothesis_confirmed":result["hypothesis_confirmed"],"observations":result["observations"]},sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
