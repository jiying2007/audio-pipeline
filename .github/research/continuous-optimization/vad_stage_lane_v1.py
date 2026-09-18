#!/usr/bin/env python3
"""Development-only VAD policy algorithm lane over exact shipping probability traces."""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
from statistics import mean
from typing import Any

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"validation/tools"))
sys.path.insert(0,str(ROOT/"tests/validation"))
import run_validation_engine as engine
import vad_operating_point_selector as selector

LOCAL_THRESHOLD=0.45
NS_THRESHOLD=0.35
MIN_SCORE=0.50
MAX_RECALL_REGRESSION=0.03
MAX_F1_REGRESSION=0.03
MAX_FPR_REGRESSION=0.03

CANDIDATES=[
    {"algorithm":"shipping-strong-weak","parameter":6},
    {"algorithm":"hysteresis-hold","parameter":0.05},
    {"algorithm":"hysteresis-hold","parameter":0.08},
    {"algorithm":"hysteresis-hold","parameter":0.12},
    {"algorithm":"confidence-tiered-hold","parameter":4},
    {"algorithm":"confidence-tiered-hold","parameter":5},
    {"algorithm":"confidence-tiered-hold","parameter":6},
    {"algorithm":"decaying-weak-hold","parameter":3},
    {"algorithm":"decaying-weak-hold","parameter":4},
    {"algorithm":"decaying-weak-hold","parameter":5},
]

def threshold(profile:str)->float:
    return NS_THRESHOLD if profile=="ns-isolated" else LOCAL_THRESHOLD

def decision_trace(probabilities:list[float],profile:str,algorithm:str,parameter:float)->list[dict]:
    th=threshold(profile); hold=0; out=[]
    for raw in probabilities:
        p=float(raw) if math.isfinite(float(raw)) else 0.0
        if algorithm=="shipping-strong-weak":
            if p>=0.50: hold=8
            elif p>th: hold=max(hold,6)
            elif hold: hold-=1
        elif algorithm=="hysteresis-hold":
            release=max(0.01,th-float(parameter))
            if p>=0.50: hold=8
            elif p>th: hold=max(hold,6)
            elif hold and p>release: hold=max(hold,2)
            elif hold: hold-=1
        elif algorithm=="confidence-tiered-hold":
            weak=int(parameter)
            if p>=0.70: hold=10
            elif p>=0.50: hold=max(hold,8)
            elif p>th: hold=max(hold,weak)
            elif hold: hold-=1
        elif algorithm=="decaying-weak-hold":
            entry=int(parameter)
            if p>=0.50: hold=8
            elif p>th and hold==0: hold=entry
            elif p>th and hold>0: hold=max(1,hold-1)
            elif hold: hold-=1
        else:
            raise ValueError(f"unknown VAD policy: {algorithm}")
        out.append({"vad_active":1 if hold>0 else 0})
    return out

def evaluate(partition:dict[str,Any],algorithm:str,parameter:float)->dict[str,Any]:
    rows=[]; positive=set()
    for case in partition["cases"]:
        if any(case["labels"]): positive.add(case["case_id"])
        stats=engine.vad_stats(case["labels"],decision_trace(
            case["probabilities"],case["processor_profile"],algorithm,parameter))
        metrics={
            "vad_f1":stats["f1"],"vad_precision":stats["precision"],
            "vad_recall":stats["recall"],"vad_false_positive_rate":stats["false_positive_rate"],
            "vad_false_negative_rate":stats["false_negative_rate"],
        }
        violations=engine.threshold_violations(metrics,case["expected"])
        rows.append({"case_id":case["case_id"],"processor_profile":case["processor_profile"],
                     "metrics":metrics,"violations":violations,"passed":not violations})
    recalls=[float(x["metrics"]["vad_recall"]) for x in rows if x["case_id"] in positive]
    f1=[float(x["metrics"]["vad_f1"]) for x in rows if x["case_id"] in positive]
    fpr=[float(x["metrics"]["vad_false_positive_rate"]) for x in rows]
    return {"validation_result":"PASS" if all(x["passed"] for x in rows) else "FAIL",
            "summary":{"pass_rate":sum(x["passed"] for x in rows)/max(1,len(rows)),
                       "min_vad_recall":min(recalls),"min_vad_f1":min(f1),
                       "max_vad_false_positive_rate":max(fpr)},"cases":rows}

def metric(r:dict,name:str)->float: return float(r["summary"][name])

def regressions(base:dict,cand:dict)->list[dict]:
    out=[]
    if cand["validation_result"]!="PASS":
        out.append({"gate":"candidate_case_gates","actual":cand["validation_result"]})
    checks=(("min_vad_recall","drop",MAX_RECALL_REGRESSION),
            ("min_vad_f1","drop",MAX_F1_REGRESSION),
            ("max_vad_false_positive_rate","rise",MAX_FPR_REGRESSION))
    for name,kind,allowed in checks:
        b,c=metric(base,name),metric(cand,name)
        reg=b-c if kind=="drop" else c-b
        if reg>allowed+1e-12:
            out.append({"gate":"aggregate_regression","metric":name,
                        "baseline":b,"candidate":c,"regression":reg,"allowed":allowed})
    return out

def score(base:dict,cand:dict)->float:
    return (2.0*(metric(cand,"min_vad_recall")-metric(base,"min_vad_recall"))/0.02+
            1.0*(metric(cand,"min_vad_f1")-metric(base,"min_vad_f1"))/0.02+
            1.5*(metric(base,"max_vad_false_positive_rate")-
                 metric(cand,"max_vad_false_positive_rate"))/0.02)

def collect(processor:Path,paths:list[Path])->list[dict]:
    return [selector.collect_partition(processor,p) for p in paths]

def run(processor:Path,dev_paths:list[Path],validation:Path,shadow:Path,output:Path)->dict:
    if len(dev_paths)!=2: raise ValueError("exactly two development corpora required")
    dev=collect(processor,dev_paths)
    val=selector.collect_partition(processor,validation)
    sh=selector.collect_partition(processor,shadow)
    baseline_dev=[evaluate(p,"shipping-strong-weak",6) for p in dev]
    ranking=[]
    for candidate in CANDIDATES:
        reports=[evaluate(p,candidate["algorithm"],candidate["parameter"]) for p in dev]
        scores=[score(b,c) for b,c in zip(baseline_dev,reports)]
        violations=[]
        for i,(b,c) in enumerate(zip(baseline_dev,reports)):
            v=regressions(b,c)
            if v: violations.append({"development_index":i,"violations":v})
        ranking.append({**candidate,"development_score":mean(scores),
                        "eligible":not violations,"violations":violations,
                        "summaries":[r["summary"] for r in reports]})
    baseline=next(x for x in ranking if x["algorithm"]=="shipping-strong-weak")
    eligible=[x for x in ranking if x["algorithm"]!="shipping-strong-weak"
              and x["eligible"] and x["development_score"]>=MIN_SCORE]
    eligible.sort(key=lambda x:(-x["development_score"],x["algorithm"],float(x["parameter"])))
    selected=eligible[0] if eligible else baseline
    val_base=evaluate(val,"shipping-strong-weak",6)
    val_cand=evaluate(val,selected["algorithm"],selected["parameter"])
    sh_base=evaluate(sh,"shipping-strong-weak",6)
    sh_cand=evaluate(sh,selected["algorithm"],selected["parameter"])
    vv=regressions(val_base,val_cand); sv=regressions(sh_base,sh_cand)
    same=selected["algorithm"]=="shipping-strong-weak"
    decision="KEEP_BASELINE" if same else (
        "FROZEN_STAGE_RESEARCH_CANDIDATE" if not vv and not sv else "REJECT_CANDIDATE")
    result={
        "schema_version":1,"authority":"research-stage-selection-only","lane_id":"vad",
        "decision":decision,
        "frozen_thresholds":{"local":LOCAL_THRESHOLD,"ns_assisted":NS_THRESHOLD},
        "baseline":{"algorithm":"shipping-strong-weak","parameter":6},
        "selected":{"algorithm":selected["algorithm"],"parameter":selected["parameter"],
                    "development_score":selected["development_score"]},
        "development":{"ranking":sorted(ranking,key=lambda x:(-x["development_score"],x["algorithm"],float(x["parameter"])))},
        "validation":{"baseline":val_base["summary"],"candidate":val_cand["summary"],
                      "regression_violations":vv},
        "shadow":{"baseline":sh_base["summary"],"candidate":sh_cand["summary"],
                  "regression_violations":sv},
        "probability_generation_mutated":False,"threshold_search_performed":False,
        "executable_binding":False,
        "automatic_main_mutation":False,"shipping_authority":False,"hil_authority":False,
        "product_certification_authority":False,
        "next_gate":"separate-source-candidate-review" if decision=="FROZEN_STAGE_RESEARCH_CANDIDATE" else None,
    }
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    return result

def self_test()->None:
    probs=[0.1,0.6,0.4]+[0.1]*10
    trace=decision_trace(probs,"vad-isolated","shipping-strong-weak",6)
    assert trace[1]["vad_active"]==1 and trace[8]["vad_active"]==0
    for c in CANDIDATES:
        t=decision_trace(probs,"ns-isolated",c["algorithm"],c["parameter"])
        assert len(t)==len(probs)
    print("VAD stage lane self-test: OK")

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--processor",type=Path)
    p.add_argument("--development-corpus",action="append",type=Path,default=[])
    p.add_argument("--validation-corpus",type=Path)
    p.add_argument("--shadow-corpus",type=Path)
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    if a.self_test: self_test(); return 0
    if any(x is None for x in (a.processor,a.validation_corpus,a.shadow_corpus,a.output)):
        p.error("processor/validation/shadow/output required")
    r=run(a.processor.resolve(),[x.resolve() for x in a.development_corpus],
          a.validation_corpus.resolve(),a.shadow_corpus.resolve(),a.output.resolve())
    print(json.dumps({"decision":r["decision"],"selected":r["selected"]},sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
