#!/usr/bin/env python3
"""Hierarchical exact-build NS algorithm + parameter research lane."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from statistics import mean
from typing import Any

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"validation/tools"))
import tuning_iteration as guarded
import tuning_iteration_engine as engine

guarded.install_fail_closed_guards()
MIN_SCORE=0.10

def avg_score(space:dict, base_reports:list[dict], cand_reports:list[dict])->tuple[float,list[dict]]:
    scores=[]; violations=[]
    for index,(base,cand) in enumerate(zip(base_reports,cand_reports)):
        score,_=engine.score_against_baseline(space,base,cand)
        scores.append(score)
        local=engine.regression_violations(space,base,cand)
        case_summary,case_v=engine.case_delta_gate_violations(space,base,cand)
        if local or case_v:
            violations.append({"development_index":index,"metric_violations":local,
                               "case_violations":case_v,"case_summary":case_summary})
        if cand.get("validation_result")!="PASS":
            violations.append({"development_index":index,"gate":"candidate_validation_result",
                               "actual":cand.get("validation_result")})
    return mean(scores),violations

def evaluate(repo:Path, processor:Path, corpora:list[Path], policy:Path, lock:Path,
             tuning:dict[str,float], out:Path, label:str)->list[dict]:
    reports=[]
    for i,corpus in enumerate(corpora):
        report,_=engine.run_validation(repo,processor,corpus,policy,lock,tuning,
                                       out/f"{label}-{i}.json")
        reports.append(report)
    return reports

def bind_summary(reports:list[dict])->list[dict]:
    return [{"validation_result":r.get("validation_result"),"summary":r.get("summary",{})}
            for r in reports]

def run(repo:Path, ema:Path, mcra:Path, dev:list[Path], validation:Path, shadow:Path,
        policy:Path, lock:Path, search_space:Path, output:Path)->dict:
    if len(dev)!=2: raise ValueError("exactly two development corpora required")
    space=json.loads(search_space.read_text())
    engine.validate_search_space(space)
    candidates=engine.generate_candidates(space)
    baseline=candidates[0]["tuning"]
    output.mkdir(parents=True,exist_ok=True)

    ema_dev=evaluate(repo,ema,dev,policy,lock,baseline,output/"algorithm","ema")
    algorithm_rows=[]
    for algorithm,processor in (("ema",ema),("mcra",mcra)):
        reports=ema_dev if algorithm=="ema" else evaluate(
            repo,processor,dev,policy,lock,baseline,output/"algorithm",algorithm)
        score,violations=avg_score(space,ema_dev,reports)
        algorithm_rows.append({"algorithm":algorithm,"development_score":score,
                               "eligible":not violations,"violations":violations,
                               "reports":bind_summary(reports)})
    alternatives=[x for x in algorithm_rows if x["algorithm"]!="ema" and x["eligible"]
                  and x["development_score"]>=MIN_SCORE]
    alternatives.sort(key=lambda x:(-x["development_score"],x["algorithm"]))
    selected_algorithm=alternatives[0]["algorithm"] if alternatives else "ema"
    selected_processor=ema if selected_algorithm=="ema" else mcra
    family_base=evaluate(repo,selected_processor,dev,policy,lock,baseline,
                         output/"parameter","family-baseline")

    param_rows=[]
    for candidate in candidates:
        reports=family_base if candidate["label"]=="baseline" else evaluate(
            repo,selected_processor,dev,policy,lock,candidate["tuning"],
            output/"parameter",candidate["candidate_id"])
        score,violations=avg_score(space,family_base,reports)
        param_rows.append({**candidate,"development_score":score,
                           "eligible":not violations,"violations":violations,
                           "reports":bind_summary(reports)})
    eligible=[x for x in param_rows if x["label"]!="baseline" and x["eligible"]
              and x["development_score"]>=float(space["objective"]["minimum_improvement_score"])]
    eligible.sort(key=lambda x:(-x["development_score"],x["candidate_id"]))
    selected_param=eligible[0] if eligible else next(x for x in param_rows if x["label"]=="baseline")

    final_tuning=selected_param["tuning"]
    val_base=evaluate(repo,ema,[validation],policy,lock,baseline,output/"validation","baseline")[0]
    val_cand=evaluate(repo,selected_processor,[validation],policy,lock,final_tuning,
                      output/"validation","candidate")[0]
    shadow_base=evaluate(repo,ema,[shadow],policy,lock,baseline,output/"shadow","baseline")[0]
    shadow_cand=evaluate(repo,selected_processor,[shadow],policy,lock,final_tuning,
                         output/"shadow","candidate")[0]
    val_score,val_v=avg_score(space,[val_base],[val_cand])
    shadow_score,shadow_v=avg_score(space,[shadow_base],[shadow_cand])

    same=(selected_algorithm=="ema" and selected_param["label"]=="baseline")
    decision="KEEP_BASELINE" if same else (
        "FROZEN_STAGE_RESEARCH_CANDIDATE" if not val_v and not shadow_v else "REJECT_CANDIDATE")
    result={
        "schema_version":1,"authority":"research-stage-selection-only","lane_id":"ns",
        "decision":decision,
        "algorithm_screen":{"selected_algorithm":selected_algorithm,
                            "ranking":sorted(algorithm_rows,key=lambda x:(-x["development_score"],x["algorithm"]))},
        "parameter_search":{"selected":{k:selected_param[k] for k in ("candidate_id","label","tuning","development_score")},
                            "ranking":sorted(param_rows,key=lambda x:(-x["development_score"],x["candidate_id"]))},
        "validation":{"score_vs_shipping_baseline":val_score,"regression_violations":val_v,
                      "baseline":val_base.get("summary",{}),"candidate":val_cand.get("summary",{})},
        "shadow":{"score_vs_shipping_baseline":shadow_score,"regression_violations":shadow_v,
                  "baseline":shadow_base.get("summary",{}),"candidate":shadow_cand.get("summary",{})},
        "selected":{"algorithm":selected_algorithm,"tuning":final_tuning},
        "executable_binding":{
            "bound":True,
            "processor_sha256":engine.sha256_file(selected_processor),
            "build_variant":selected_algorithm,
        },
        "automatic_main_mutation":False,"shipping_authority":False,"hil_authority":False,
        "product_certification_authority":False,
        "next_gate":"stage-composition-development" if decision=="FROZEN_STAGE_RESEARCH_CANDIDATE" else None,
    }
    (output/"ns-stage-lane-result.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    return result

def self_test()->None:
    space={"objective":{"minimum_improvement_score":0.1,"metrics":[
        {"name":"pass_rate","direction":"max","weight":1.0,"scale":0.1,"max_regression":0.0}]}}
    base=[{"validation_result":"PASS","summary":{"pass_rate":1.0},"cases":[{"case_id":"x","metrics":{}}]}]
    cand=[{"validation_result":"PASS","summary":{"pass_rate":1.0},"cases":[{"case_id":"x","metrics":{}}]}]
    score,v=avg_score(space,base,cand)
    assert score==0 and not v
    print("NS stage lane self-test: OK")

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--repo-root",type=Path,default=Path("."))
    p.add_argument("--ema-processor",type=Path)
    p.add_argument("--mcra-processor",type=Path)
    p.add_argument("--development-corpus",action="append",type=Path,default=[])
    p.add_argument("--validation-corpus",type=Path)
    p.add_argument("--shadow-corpus",type=Path)
    p.add_argument("--policy",type=Path)
    p.add_argument("--dataset-lock",type=Path,default=Path("validation/datasets.lock.json"))
    p.add_argument("--search-space",type=Path)
    p.add_argument("--output-dir",type=Path)
    a=p.parse_args()
    if a.self_test: self_test(); return 0
    required=(a.ema_processor,a.mcra_processor,a.validation_corpus,a.shadow_corpus,
              a.policy,a.search_space,a.output_dir)
    if any(x is None for x in required): p.error("missing required lane argument")
    r=run(a.repo_root.resolve(),a.ema_processor.resolve(),a.mcra_processor.resolve(),
          [x.resolve() for x in a.development_corpus],a.validation_corpus.resolve(),
          a.shadow_corpus.resolve(),a.policy.resolve(),a.dataset_lock.resolve(),
          a.search_space.resolve(),a.output_dir.resolve())
    print(json.dumps({"decision":r["decision"],"selected":r["selected"]},sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
