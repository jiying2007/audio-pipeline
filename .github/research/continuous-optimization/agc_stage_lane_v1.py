#!/usr/bin/env python3
"""Development-only AGC dynamics algorithm + runtime parameter lane."""
from __future__ import annotations
import argparse, array, json, math, os, sys
from pathlib import Path
from statistics import mean
from typing import Any

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"tests/validation"))
import agc_dynamics_diagnostic as diag

FRAME=160
MIN_SCORE=0.25
ALGORITHM_CANDIDATES=[
    {"algorithm":"shipping-asymmetric-ema","parameter":0.015},
    {"algorithm":"error-adaptive-release","parameter":0.025},
    {"algorithm":"error-adaptive-release","parameter":0.035},
    {"algorithm":"error-adaptive-release","parameter":0.050},
    {"algorithm":"slew-limited-release","parameter":0.25},
    {"algorithm":"slew-limited-release","parameter":0.50},
    {"algorithm":"slew-limited-release","parameter":0.75},
]

def read_pcm(path:Path)->list[int]:
    a=array.array("h"); a.frombytes(path.read_bytes())
    if os.sys.byteorder!="little": a.byteswap()
    return list(a)

def dbfs_rms(values:list[float])->float:
    e=sum(x*x for x in values)/max(1,len(values))
    return 10.0*math.log10(max(e,1e-18))

def dbfs_peak(values:list[float])->float:
    p=max((abs(x) for x in values),default=1e-9)
    return 20.0*math.log10(max(p,1e-9))

def simulate(samples:list[int],target_dbfs:float,limiter_dbfs:float,
             algorithm:str,parameter:float)->list[dict[str,float]]:
    target=10.0**(target_dbfs/20.0)
    limit=10.0**(limiter_dbfs/20.0)
    gain=1.0; rows=[]
    frames=len(samples)//FRAME
    for f in range(frames):
        frame=[x/32768.0 for x in samples[f*FRAME:(f+1)*FRAME]]
        e=1e-12+sum(x*x for x in frame)
        peak=max((abs(x) for x in frame),default=0.0)
        rms=math.sqrt(e/FRAME)
        target_gain=max(0.25,min(8.0,target/(rms+1e-6)))
        base_alpha=0.25 if target_gain<gain else 0.015
        if algorithm=="shipping-asymmetric-ema":
            alpha=base_alpha
            next_gain=gain+alpha*(target_gain-gain)
        elif algorithm=="error-adaptive-release":
            if target_gain<gain:
                alpha=0.25
            else:
                error_db=20.0*math.log10(max(target_gain,1e-9)/max(gain,1e-9))
                alpha=float(parameter) if error_db>3.0 else 0.015
            next_gain=gain+alpha*(target_gain-gain)
        elif algorithm=="slew-limited-release":
            alpha=base_alpha
            proposed=gain+alpha*(target_gain-gain)
            if proposed>gain:
                max_ratio=10.0**(float(parameter)/20.0)
                next_gain=min(proposed,gain*max_ratio)
            else:
                next_gain=proposed
        else:
            raise ValueError(f"unknown AGC algorithm: {algorithm}")
        gain=next_gain
        effective=gain
        if peak*effective>limit and peak>1e-6:
            effective=limit/peak
        out=[max(-limit,min(limit,x*effective)) for x in frame]
        rows.append({"frame":f,"output_rms_dbfs":dbfs_rms(out),
                     "output_peak_dbfs":dbfs_peak(out),
                     "gain_db":20.0*math.log10(max(effective,1e-9))})
    return rows

def evaluate_corpus(corpus_path:Path,algorithm:str,parameter:float,
                    target:float=-20.0,limiter:float=-2.0)->dict[str,Any]:
    corpus=json.loads(corpus_path.read_text())
    rows=[]
    for case in corpus["cases"]:
        if case.get("processor_profile")!="agc-isolated": continue
        samples=read_pcm(corpus_path.parent/case["mic_audio"])
        trace=simulate(samples,target,limiter,algorithm,parameter)
        summary=diag.summarize_case(case,trace,limiter_override=limiter)
        rows.append(summary)
    by={x["case_id"]:x for x in rows}
    step=by["agc-level-step"]
    steady_low=by["agc-steady-low"]; steady_hot=by["agc-steady-hot"]
    transient=by["agc-transient"]
    return {
        "validation_result":"PASS" if all(x["passed"] for x in rows) else "FAIL",
        "summary":{
            "steady_low_error_db":abs(float(steady_low["tail_output_rms_dbfs"])-target),
            "steady_hot_error_db":abs(float(steady_hot["tail_output_rms_dbfs"])-target),
            "low_to_hot_settle_frames":float(step.get("low_to_hot_settle_frames") or 1e6),
            "hot_to_low_settle_frames":float(step.get("hot_to_low_settle_frames") or 1e6),
            "level_step_gain_slew_p95_db":float(step["p95_abs_gain_step_db"] or 0.0),
            "max_output_peak_dbfs":max(float(x["max_output_peak_dbfs"]) for x in rows),
        },
        "cases":rows,
    }

def score(base:dict,cand:dict)->float:
    b,c=base["summary"],cand["summary"]
    return (
        (b["steady_low_error_db"]-c["steady_low_error_db"])/0.25+
        (b["steady_hot_error_db"]-c["steady_hot_error_db"])/0.25+
        (b["low_to_hot_settle_frames"]-c["low_to_hot_settle_frames"])/5.0+
        (b["hot_to_low_settle_frames"]-c["hot_to_low_settle_frames"])/20.0
    )

def regressions(base:dict,cand:dict)->list[dict]:
    out=[]
    if cand["validation_result"]!="PASS":
        out.append({"gate":"candidate_case_gates","actual":cand["validation_result"]})
    limits={
        "steady_low_error_db":0.35,"steady_hot_error_db":0.35,
        "low_to_hot_settle_frames":5.0,"hot_to_low_settle_frames":20.0,
        "level_step_gain_slew_p95_db":0.15,
    }
    for key,allowed in limits.items():
        regression=float(cand["summary"][key])-float(base["summary"][key])
        if regression>allowed:
            out.append({"gate":"metric_regression","metric":key,
                        "regression":regression,"allowed":allowed})
    # Peak is dBFS; larger/less-negative is worse.
    peak_reg=float(cand["summary"]["max_output_peak_dbfs"])-float(base["summary"]["max_output_peak_dbfs"])
    if peak_reg>0.20:
        out.append({"gate":"peak_regression","regression_db":peak_reg,"allowed_db":0.20})
    return out

def combine(reports:list[dict])->dict:
    keys=reports[0]["summary"].keys()
    return {"validation_result":"PASS" if all(r["validation_result"]=="PASS" for r in reports) else "FAIL",
            "summary":{k:mean(float(r["summary"][k]) for r in reports) for k in keys}}

def tuning_candidates(space:dict)->list[dict]:
    base=space["baseline"]; out=[{"label":"baseline","tuning":dict(base)}]
    seen={(float(base["agc_target_dbfs"]),float(base["limiter_dbfs"]))}
    for key in ("agc_target_dbfs","limiter_dbfs"):
        for value in space["parameters"][key]:
            t=dict(base); t[key]=float(value)
            ident=(float(t["agc_target_dbfs"]),float(t["limiter_dbfs"]))
            if ident in seen: continue
            seen.add(ident); out.append({"label":f"{key}={value}","tuning":t})
    return out

def run(dev:list[Path],validation:Path,shadow:Path,search_space:Path,output:Path)->dict:
    if len(dev)!=2: raise ValueError("exactly two development corpora required")
    space=json.loads(search_space.read_text())
    base_alg=ALGORITHM_CANDIDATES[0]
    base_dev=combine([evaluate_corpus(p,base_alg["algorithm"],base_alg["parameter"]) for p in dev])
    alg_rows=[]
    for a in ALGORITHM_CANDIDATES:
        report=combine([evaluate_corpus(p,a["algorithm"],a["parameter"]) for p in dev])
        v=regressions(base_dev,report)
        alg_rows.append({**a,"development_score":score(base_dev,report),
                         "eligible":not v,"violations":v,"summary":report["summary"]})
    eligible=[x for x in alg_rows if x["algorithm"]!="shipping-asymmetric-ema"
              and x["eligible"] and x["development_score"]>=MIN_SCORE]
    eligible.sort(key=lambda x:(-x["development_score"],x["algorithm"],float(x["parameter"])))
    selected_alg=eligible[0] if eligible else alg_rows[0]
    family_base=combine([evaluate_corpus(p,selected_alg["algorithm"],selected_alg["parameter"]) for p in dev])

    param_rows=[]
    for candidate in tuning_candidates(space):
        t=candidate["tuning"]
        report=combine([evaluate_corpus(p,selected_alg["algorithm"],selected_alg["parameter"],
                                       float(t["agc_target_dbfs"]),float(t["limiter_dbfs"])) for p in dev])
        v=regressions(family_base,report)
        param_rows.append({**candidate,"development_score":score(family_base,report),
                           "eligible":not v,"violations":v,"summary":report["summary"]})
    pgood=[x for x in param_rows if x["label"]!="baseline" and x["eligible"]
           and x["development_score"]>=0.10]
    pgood.sort(key=lambda x:(-x["development_score"],x["label"]))
    selected_param=pgood[0] if pgood else param_rows[0]
    t=selected_param["tuning"]

    val_base=evaluate_corpus(validation,base_alg["algorithm"],base_alg["parameter"])
    val_cand=evaluate_corpus(validation,selected_alg["algorithm"],selected_alg["parameter"],
                             float(t["agc_target_dbfs"]),float(t["limiter_dbfs"]))
    sh_base=evaluate_corpus(shadow,base_alg["algorithm"],base_alg["parameter"])
    sh_cand=evaluate_corpus(shadow,selected_alg["algorithm"],selected_alg["parameter"],
                            float(t["agc_target_dbfs"]),float(t["limiter_dbfs"]))
    vv=regressions(val_base,val_cand); sv=regressions(sh_base,sh_cand)
    same=(selected_alg["algorithm"]=="shipping-asymmetric-ema" and selected_param["label"]=="baseline")
    decision="KEEP_BASELINE" if same else (
        "FROZEN_STAGE_RESEARCH_CANDIDATE" if not vv and not sv else "REJECT_CANDIDATE")
    result={
        "schema_version":1,"authority":"research-stage-selection-only","lane_id":"agc",
        "decision":decision,
        "algorithm_screen":{"selected":{"algorithm":selected_alg["algorithm"],"parameter":selected_alg["parameter"]},
                            "ranking":sorted(alg_rows,key=lambda x:(-x["development_score"],x["algorithm"],float(x["parameter"])))},
        "parameter_search":{"selected":{k:selected_param[k] for k in ("label","tuning","development_score")},
                            "ranking":sorted(param_rows,key=lambda x:(-x["development_score"],x["label"]))},
        "selected":{"algorithm":selected_alg["algorithm"],"algorithm_parameter":selected_alg["parameter"],
                    "tuning":t},
        "validation":{"baseline":val_base["summary"],"candidate":val_cand["summary"],
                      "regression_violations":vv},
        "shadow":{"baseline":sh_base["summary"],"candidate":sh_cand["summary"],
                  "regression_violations":sv},
        "effective_winner":(
            {"algorithm":selected_alg["algorithm"],"algorithm_parameter":selected_alg["parameter"],"tuning":t}
            if decision=="FROZEN_STAGE_RESEARCH_CANDIDATE"
            else {"algorithm":"shipping-asymmetric-ema","algorithm_parameter":0.015,
                  "tuning":{"agc_target_dbfs":-20.0,"limiter_dbfs":-2.0}}
        ),
        "executable_binding":{
            "bound":decision!="FROZEN_STAGE_RESEARCH_CANDIDATE",
            "kind":"shipping-baseline" if decision!="FROZEN_STAGE_RESEARCH_CANDIDATE" else "research-emulator",
        },
        "automatic_main_mutation":False,"shipping_authority":False,"hil_authority":False,
        "product_certification_authority":False,
        "next_gate":"separate-source-candidate-review" if decision=="FROZEN_STAGE_RESEARCH_CANDIDATE" else None,
    }
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    return result

def self_test()->None:
    samples=[int(1000*math.sin(2*math.pi*440*n/16000)) for n in range(FRAME*100)]
    for a in ALGORITHM_CANDIDATES:
        rows=simulate(samples,-20,-2,a["algorithm"],a["parameter"])
        assert len(rows)==100
    print("AGC stage lane self-test: OK")

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--development-corpus",action="append",type=Path,default=[])
    p.add_argument("--validation-corpus",type=Path)
    p.add_argument("--shadow-corpus",type=Path)
    p.add_argument("--search-space",type=Path)
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    if a.self_test: self_test(); return 0
    if any(x is None for x in (a.validation_corpus,a.shadow_corpus,a.search_space,a.output)):
        p.error("validation/shadow/search-space/output required")
    r=run([x.resolve() for x in a.development_corpus],a.validation_corpus.resolve(),
          a.shadow_corpus.resolve(),a.search_space.resolve(),a.output.resolve())
    print(json.dumps({"decision":r["decision"],"selected":r["selected"]},sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
