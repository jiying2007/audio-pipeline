#!/usr/bin/env python3
"""Candidate-zero RES instantaneous-target driver decomposition.

Reuses the mechanically validated RES contribution probe. Counterfactuals alter
only the residual/echo inputs used to compute target_gain; actual AEC residual
energy remains unchanged in every output-energy path.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import tempfile
from pathlib import Path

import aec_res_gain_contribution_decomposition as contrib

PROFILES=("prefix-aec","prefix-res")
FRAME_MS=10

def load_json(path:Path)->dict:
    v=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(v,dict): raise ValueError(f"{path}: JSON object required")
    return v

def require_contract(c:dict)->None:
    if c.get("authority")!="CANDIDATE_ZERO_TARGET_DRIVER_COUNTERFACTUAL_ONLY":
        raise ValueError("target-driver authority drift")
    if c.get("candidate_limit")!=0 or c.get("confirmation_limit")!=0:
        raise ValueError("target-driver budget drift")
    if tuple(c["corpus"]["profiles"])!=PROFILES:
        raise ValueError("profile drift")
    m=c["measurement"]
    expected={
      "geometry_id":"100w-50s","post_window_ms":100,"post_stride_ms":50,
      "pre_baseline_window_ms":100,"pre_baseline_ms":[-1000,-200],
      "recovery_excess_db":3.01029995664,"continuous_hold_ms":300,
      "required_windows_for_300ms_coverage":5,"search_ms":[0,2500],
    }
    for k,v in expected.items():
        if m[k]!=v: raise ValueError(f"measurement drift: {k}")
    for k,v in c["preregistered_rules"].items():
        if k.startswith("no_") and v is not True:
            raise ValueError(f"rule drift: {k}")

def target_gain(residual:float,echo:float,far:int,dt:int,c:dict)->float:
    f=c["shipping_target_formula"]
    if not far or dt: return 1.0
    value=math.sqrt(
        residual/(residual+float(f["echo_weight"])*echo+float(f["epsilon"]))
    )
    return min(1.0,max(float(f["floor_gain"]),value))

def pre_reference(rows:list[dict],transition_frame:int,c:dict)->tuple[float,float]:
    start_ms,end_ms=c["pre_transition_references"]["interval_ms"]
    start=transition_frame+int(start_ms)//FRAME_MS
    end=transition_frame+int(end_ms)//FRAME_MS
    if start<0 or end<=start or end>len(rows): raise ValueError("pre reference window invalid")
    residual=[float(r["pre_res_energy"]) for r in rows[start:end]]
    echo=[float(r["echo_energy"]) for r in rows[start:end]]
    return float(statistics.median(residual)),float(statistics.median(echo))

def curve_energy(rows:list[dict],res_ref:float,echo_ref:float,c:dict,mode:str)->list[float]:
    out=[]
    for row in rows:
        actual_r=float(row["pre_res_energy"])
        actual_e=float(row["echo_energy"])
        if mode=="actual":
            r,e=actual_r,actual_e
        elif mode=="freeze_echo":
            r,e=actual_r,echo_ref
        elif mode=="freeze_residual":
            r,e=res_ref,actual_e
        elif mode=="freeze_both":
            r,e=res_ref,echo_ref
        else:
            raise ValueError(mode)
        g=target_gain(r,e,int(row["far_end_active"]),int(row["double_talk_active"]),c)
        out.append(actual_r*g*g)
    return out

def delta(a:int|None,b:int|None)->int|None:
    if a is None or b is None:return None
    return int(b)-int(a)

def analyze_seed(corpus_path:Path,report_path:Path,processor:Path,probe:Path,c:dict,trace_output:Path)->dict:
    require_contract(c)
    corpus=load_json(corpus_path); report=load_json(report_path)
    expected={f"echo-path-change--{p}" for p in PROFILES}
    cases={x["case_id"]:x for x in corpus["cases"]}
    if set(cases)!=expected: raise ValueError("case set drift")
    rmap={x["case_id"]:x for x in report.get("cases",[])}
    if set(rmap)!=expected or not all(bool(x.get("passed",False)) for x in rmap.values()):
        raise ValueError("canonical report invalid")
    aec_case=cases["echo-path-change--prefix-aec"]
    res_case=cases["echo-path-change--prefix-res"]
    aec_std=contrib.analyze_standard_recovery(aec_case,corpus_path,processor,c)
    res_std=contrib.analyze_standard_recovery(res_case,corpus_path,processor,c)

    with tempfile.TemporaryDirectory(prefix="ap-target-driver-") as raw:
        root=Path(raw)
        reference=contrib.standard_output(processor,corpus_path,res_case,root/"reference")
        observed,rows=contrib.run_probe(probe,corpus_path,res_case,root/"probe")
    equivalent=reference==observed
    trace_output.parent.mkdir(parents=True,exist_ok=True)
    trace_output.write_text("\n".join(json.dumps(x,sort_keys=True) for x in rows)+"\n",encoding="utf-8")

    transition_frame=int(res_case["control"]["echo_path_change_frame"])
    res_ref,echo_ref=pre_reference(rows,transition_frame,c)
    echo_energy=contrib.echo_frame_energy(corpus_path,res_case,len(rows))

    # Reconstruct the observed target exactly as a mechanical validity check.
    max_target_error=max(
        abs(target_gain(float(row["pre_res_energy"]),float(row["echo_energy"]),
                        int(row["far_end_active"]),int(row["double_talk_active"]),c)
            -float(row["target_gain"]))
        for row in rows
    )
    paths={}
    for mode in ("actual","freeze_echo","freeze_residual","freeze_both"):
        measured=contrib.measure_curve(
            curve_energy(rows,res_ref,echo_ref,c,mode),
            echo_energy,transition_frame,c
        )
        paths[mode]={
          "recovery_time_ms":measured["recovery_time_ms"],
          "censored":bool(measured["censored"]),
          "pre_baseline_db":measured["pre_baseline_db"],
          "recovery_limit_db":measured["recovery_limit_db"],
        }

    # Independently reconstruct AEC residual recovery from the same trace.
    aec_analytic=contrib.measure_curve(
        [float(row["pre_res_energy"]) for row in rows],
        echo_energy,transition_frame,c
    )
    aec_ms=aec_std["recovery_time_ms"]
    if aec_analytic["recovery_time_ms"]!=aec_ms:
        raise ValueError("analytic AEC recovery drift")

    actual_delay=delta(aec_ms,paths["actual"]["recovery_time_ms"])
    receipts={}
    for mode in ("freeze_echo","freeze_residual","freeze_both"):
        cf_delay=delta(aec_ms,paths[mode]["recovery_time_ms"])
        receipts[mode]={
          "target_delay_vs_aec_ms":cf_delay,
          "delay_reduction_vs_actual_target_ms":
              None if actual_delay is None or cf_delay is None else actual_delay-cf_delay,
          "eliminates_positive_actual_target_delay":
              bool(actual_delay is not None and actual_delay>=50 and cf_delay is not None and cf_delay<=0),
        }

    return {
      "schema_version":1,"investigation_id":c["id"],
      "seed":int(corpus["generator"]["seed"]),
      "authority":"candidate-zero-target-driver-counterfactual-only",
      "probe_output_bitwise_equivalent":equivalent,
      "target_formula_max_abs_error":max_target_error,
      "pre_transition_reference":{"residual_energy":res_ref,"echo_energy":echo_ref},
      "standard_recovery_ms":{"AEC":aec_ms,"RES":res_std["recovery_time_ms"]},
      "counterfactual_recovery":paths,
      "actual_target_delay_vs_aec_ms":actual_delay,
      "driver_receipts":receipts,
      "candidate_authority":False,"root_cause_claim_authority":False,
    }

def aggregate(items:list[dict],c:dict)->dict:
    require_contract(c)
    expected=sorted(int(x) for x in c["corpus"]["fresh_seeds"])
    by={int(x["seed"]):x for x in items}
    if sorted(by)!=expected: raise ValueError("seed drift")
    max_formula=max(float(by[s]["target_formula_max_abs_error"]) for s in expected)
    equivalent=all(by[s]["probe_output_bitwise_equivalent"] for s in expected)
    actual={str(s):by[s]["actual_target_delay_vs_aec_ms"] for s in expected}
    summary={}
    for mode in ("freeze_echo","freeze_residual","freeze_both"):
        summary[mode]={
          "target_delay_vs_aec_ms":{str(s):by[s]["driver_receipts"][mode]["target_delay_vs_aec_ms"] for s in expected},
          "delay_reduction_vs_actual_target_ms":{str(s):by[s]["driver_receipts"][mode]["delay_reduction_vs_actual_target_ms"] for s in expected},
          "eliminates_positive_actual_target_delay_seeds":[
              s for s in expected if by[s]["driver_receipts"][mode]["eliminates_positive_actual_target_delay"]
          ],
        }
    return {
      "schema_version":1,"investigation_id":c["id"],"fresh_seeds":expected,
      "mechanical_validity":{
        "probe_output_bitwise_equivalent_all_seeds":equivalent,
        "target_formula_max_abs_error":max_formula,
        "target_formula_reconstruction_valid":max_formula<=1e-6,
        "evidence_accepted":equivalent and max_formula<=1e-6,
      },
      "actual_target_delay_vs_aec_ms":actual,
      "counterfactual_driver_summary":summary,
      "receipts":[by[s] for s in expected],
      "driver_root_cause_attribution":"NOT_AUTHORIZED",
      "candidate_authority":False,"s004_open":False,
    }

def self_test():
    c={"shipping_target_formula":{"floor_gain":0.1,"echo_weight":0.8,"epsilon":1e-12}}
    g=target_gain(1.0,1.0,1,0,c)
    assert 0.1<g<1.0
    assert target_gain(1.0,1.0,0,0,c)==1.0
    assert target_gain(1.0,1.0,1,1,c)==1.0
    print("RES target-driver decomposition self-test: OK")

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("self-test")
    run=sub.add_parser("run")
    for name in ("corpus","report","processor","probe","contract","trace-output","output"):
        run.add_argument("--"+name,type=Path,required=True)
    agg=sub.add_parser("aggregate")
    agg.add_argument("--contract",type=Path,required=True)
    agg.add_argument("--input",type=Path,action="append",required=True)
    agg.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    if a.command=="self-test": self_test(); return 0
    c=load_json(a.contract)
    if a.command=="run":
        r=analyze_seed(a.corpus,a.report,a.processor,a.probe,c,a.trace_output)
    else:
        r=aggregate([load_json(x) for x in a.input],c)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    if a.command=="run":
        print(json.dumps({"seed":r["seed"],"actual_target_delay_vs_aec_ms":r["actual_target_delay_vs_aec_ms"],"driver_receipts":r["driver_receipts"]},sort_keys=True))
    else:
        print(json.dumps({"mechanical_validity":r["mechanical_validity"],"actual_target_delay_vs_aec_ms":r["actual_target_delay_vs_aec_ms"],"counterfactual_driver_summary":r["counterfactual_driver_summary"]},sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
