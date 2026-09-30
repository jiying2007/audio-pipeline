#!/usr/bin/env python3
"""I031 candidate-zero joint-coherent donor aggregation diagnostic."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
from typing import Any

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"validation"/"tools"))
import run_validation_engine as engine  # type: ignore

WARMUP=80
REFERENCE_COUNT=8
DONOR_SELECT_K=3
NOISE_DOMAINS=("kitchen","traffic","living","office","cafeteria","bus","field")
NAMED_DOMAINS=("bus","field","living","cafeteria")
NEGATIVE_DOMAIN={
    "kitchen":"traffic",
    "traffic":"living",
    "living":"office",
    "office":"cafeteria",
    "cafeteria":"bus",
    "bus":"field",
    "field":"kitchen",
}


def require(condition: bool,message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_json(path: Path) -> dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value,dict),f"JSON object required: {path}")
    return value


def clamp01(value: float) -> float:
    return max(0.0,min(1.0,value))


def sign_test_one_sided(wins: int,losses: int) -> float | None:
    n=wins+losses
    if n==0:
        return None
    return sum(math.comb(n,k) for k in range(wins,n+1))/(2**n)


def run_probe(probe: Path,pcm: Path) -> list[dict[str,Any]]:
    proc=subprocess.run(
        [str(probe),str(pcm)],
        check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
    )
    rows=[json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    require(bool(rows) and all(isinstance(row,dict) for row in rows),
            "probe output invalid")
    return rows


def disagreement(row: dict[str,Any],upstream_guard: float) -> bool:
    return (
        float(row["upstream_probability"])>upstream_guard
        and not int(row["local_guard_pass"])
    )


def metadata(case: dict[str,Any],seed: int) -> dict[str,Any]:
    dims=case.get("dimensions",{})
    case_id=str(case["case_id"])
    return {
        "seed":seed,
        "case_id":case_id,
        "case_key":f"{seed}:{case_id}",
        "scenario":str(case["scenario"]),
        "noise_domain":dims.get("noise_domain"),
        "reverb":dims.get("reverb"),
        "snr_db":dims.get("snr_db"),
    }


def scenario_group(meta: dict[str,Any]) -> str:
    scenario=meta["scenario"]
    if scenario=="research-public-noise-only":
        return "noise-only"
    if scenario.startswith("research-public-noisy"):
        return "mix"
    return "other"


def compatibility_score(target: dict[str,Any],donor: dict[str,Any]) -> tuple:
    target_group=scenario_group(target)
    donor_group=scenario_group(donor)
    group_penalty=int(target_group!=donor_group)

    target_reverb=target.get("reverb")
    donor_reverb=donor.get("reverb")
    if target_reverb is None:
        reverb_penalty=0 if donor_reverb is None else 1
    elif donor_reverb is None:
        reverb_penalty=2
    else:
        reverb_penalty=int(bool(target_reverb)!=bool(donor_reverb))

    target_snr=target.get("snr_db")
    donor_snr=donor.get("snr_db")
    if target_snr is None:
        snr_missing_penalty=0 if donor_snr is None else 1
        snr_distance=0.0
    elif donor_snr is None:
        snr_missing_penalty=1
        snr_distance=100.0
    else:
        snr_missing_penalty=0
        snr_distance=abs(float(target_snr)-float(donor_snr))

    scenario_penalty=int(target["scenario"]!=donor["scenario"])
    return (
        group_penalty,
        reverb_penalty,
        snr_missing_penalty,
        snr_distance,
        scenario_penalty,
        donor["case_key"],
    )


def summarize_joint_frames(frames: list[dict[str,float]]) -> dict[str,Any] | None:
    if len(frames)!=REFERENCE_COUNT:
        return None
    return {
        "frames":frames,
        "summary":{
            key:statistics.median(float(frame[key]) for frame in frames)
            for key in ("mean","concentration","gap")
        },
    }


def analyze_case(
    probe: Path,
    corpus_path: Path,
    case: dict[str,Any],
    upstream_guard: float,
    seed: int,
) -> dict[str,Any]:
    meta=metadata(case,seed)
    mic=engine.resolve(corpus_path,case.get("mic_audio"))
    labels_path=engine.resolve(corpus_path,case.get("vad_labels"))
    require(mic is not None and labels_path is not None,
            "case missing mic audio or VAD labels")

    with tempfile.TemporaryDirectory(prefix="ap-i031-") as tmp:
        _,raw=engine.stage_audio(mic,16000,1,Path(tmp),"mic.pcm")
        rows=run_probe(probe,raw)

    labels=[int(v) for v in engine.load_labels(labels_path)]
    count=min(len(rows),len(labels))
    require(count>WARMUP,"case too short")
    rows=rows[WARMUP:count]
    labels=labels[WARMUP:count]

    joint_frames=[]
    pre_ready_speech=0
    max_ns_delta=0.0
    max_vad_delta=0.0
    active_mismatch=0

    for row,label in zip(rows,labels):
        require(label in (0,1),"invalid label")
        upstream=float(row["upstream_probability"])
        gap=float(row["mirror_gap"])
        public=float(row["public_shipping_probability"])
        shipping=float(row["shipping_probability"])
        mean=float(row["mirror_mean"])
        concentration=float(row["mirror_concentration"])
        require(all(math.isfinite(v) for v in (
            upstream,gap,public,shipping,mean,concentration
        )),"non-finite I031 metric")

        max_ns_delta=max(max_ns_delta,abs(upstream-gap))
        max_vad_delta=max(max_vad_delta,abs(public-shipping))
        active_mismatch+=int(
            int(row["public_shipping_active"])!=int(row["shipping_active"])
        )

        is_disagreement=disagreement(row,upstream_guard)
        if label==0 and not is_disagreement:
            if len(joint_frames)<REFERENCE_COUNT:
                joint_frames.append({
                    "mean":mean,
                    "concentration":concentration,
                    "gap":gap,
                })
            continue

        if label==1 and is_disagreement and len(joint_frames)<REFERENCE_COUNT:
            pre_ready_speech+=1

    return {
        "metadata":meta,
        "first_ready_joint_reference":summarize_joint_frames(joint_frames),
        "pre_ready_speech_targets":pre_ready_speech,
        "mirror":{
            "max_ns_upstream_gap_delta":max_ns_delta,
            "max_vad_probability_delta":max_vad_delta,
            "vad_active_mismatch_frames":active_mismatch,
        },
    }


def select_donors(
    target_meta: dict[str,Any],
    donor_by_domain: dict[str,list[dict[str,Any]]],
    domain: str,
) -> list[dict[str,Any]]:
    candidates=donor_by_domain.get(domain,[])
    ranked=sorted(
        candidates,
        key=lambda record: compatibility_score(
            target_meta,record["metadata"]
        ),
    )
    return ranked[:DONOR_SELECT_K]


def control_aggregate(records: list[dict[str,Any]]) -> dict[str,float]:
    require(len(records)==DONOR_SELECT_K,"I031 control requires K donor records")
    return {
        key:statistics.median(
            float(r["first_ready_joint_reference"]["summary"][key])
            for r in records
        )
        for key in ("mean","concentration","gap")
    }


def algebraic_inconsistency(summary: dict[str,float]) -> float:
    expected=clamp01(float(summary["concentration"])-float(summary["mean"]))
    return abs(float(summary["gap"])-expected)


def joint_coherent_aggregate(records: list[dict[str,Any]]) -> dict[str,Any]:
    require(len(records)==DONOR_SELECT_K,"I031 coherent aggregate requires K donors")
    pooled=[]
    for record in records:
        case_key=record["metadata"]["case_key"]
        frames=record["first_ready_joint_reference"]["frames"]
        require(len(frames)==REFERENCE_COUNT,"I031 donor joint frame count drift")
        for frame_index,frame in enumerate(frames):
            pooled.append({
                "case_key":case_key,
                "frame_index":frame_index,
                "mean":float(frame["mean"]),
                "concentration":float(frame["concentration"]),
                "gap":float(frame["gap"]),
            })
    require(len(pooled)==DONOR_SELECT_K*REFERENCE_COUNT,
            "I031 pooled frame count drift")
    center={
        key:statistics.median(frame[key] for frame in pooled)
        for key in ("mean","concentration","gap")
    }
    ranked=sorted(
        pooled,
        key=lambda frame:(
            abs(frame["mean"]-center["mean"])
            + abs(frame["concentration"]-center["concentration"])
            + abs(frame["gap"]-center["gap"]),
            frame["case_key"],
            frame["frame_index"],
        ),
    )
    selected=ranked[0]
    summary={key:selected[key] for key in ("mean","concentration","gap")}
    return {
        "summary":summary,
        "center":center,
        "selected_case_key":selected["case_key"],
        "selected_frame_index":selected["frame_index"],
        "selected_l1_distance":(
            abs(selected["mean"]-center["mean"])
            + abs(selected["concentration"]-center["concentration"])
            + abs(selected["gap"]-center["gap"])
        ),
        "algebraic_inconsistency":algebraic_inconsistency(summary),
        "selected_from_observed_pool":True,
        "pooled_frame_count":len(pooled),
    }


def abs_error(summary: dict[str,float],target: dict[str,float]) -> dict[str,float]:
    return {
        key:abs(float(summary[key])-float(target[key]))
        for key in ("mean","concentration","gap")
    }


def comparison_summary(records: list[dict[str,Any]]) -> dict[str,Any]:
    if not records:
        return {"paired_cases":0}
    gap_improvements=[
        float(r["control_abs_error"]["gap"])
        - float(r["coherent_abs_error"]["gap"])
        for r in records
    ]
    wins=sum(v>0 for v in gap_improvements)
    losses=sum(v<0 for v in gap_improvements)
    return {
        "paired_cases":len(records),
        "median_control_gap_abs_error":
            statistics.median(r["control_abs_error"]["gap"] for r in records),
        "median_coherent_gap_abs_error":
            statistics.median(r["coherent_abs_error"]["gap"] for r in records),
        "median_gap_error_improvement":statistics.median(gap_improvements),
        "gap_better_fraction":wins/(wins+losses) if wins+losses else None,
        "gap_sign_test_one_sided_p":sign_test_one_sided(wins,losses),
        "gap_improvement_sign_counts":{
            "positive":wins,
            "negative":losses,
            "zero":sum(v==0 for v in gap_improvements),
        },
        "median_control_algebraic_inconsistency":
            statistics.median(r["control_algebraic_inconsistency"] for r in records),
        "max_coherent_algebraic_inconsistency":
            max(r["coherent_algebraic_inconsistency"] for r in records),
        "median_coherent_selected_l1":
            statistics.median(r["coherent_selected_l1_distance"] for r in records),
    }


def evaluate(
    probe: Path,
    donor_corpora: list[Path],
    target_corpora: list[Path],
    contract_path: Path,
    output: Path,
) -> dict[str,Any]:
    contract=load_json(contract_path)
    require(
        contract["investigation_id"]
        =="i031-ns-upstream-joint-coherent-donor-aggregation-v1",
        "contract identity drift",
    )
    authority=contract["fresh_diagnostic_authority"]
    donor_seeds=[int(v) for v in authority["donor_seeds"]]
    target_seeds=[int(v) for v in authority["target_seeds"]]
    require(len(donor_corpora)==len(donor_seeds),"donor corpus count mismatch")
    require(len(target_corpora)==len(target_seeds),"target corpus count mismatch")
    require(set(donor_seeds).isdisjoint(target_seeds),"donor/target seed overlap")
    require(authority["diagnostic_execution_limit"]==1,"execution budget drift")
    require(authority["candidate_limit"]==0,"candidate budget drift")
    require(authority["confirmation_limit"]==0,"confirmation budget drift")

    upstream_guard=float(
        contract["fixed_shipping_semantics"]["vad_upstream_speech_guard"]
    )
    expected_lock=contract["dataset_authority"]["dataset_lock_sha256"]
    expected_cases=int(authority["expected_cases_per_seed"])
    expected_domain_cases=int(authority["expected_noise_domain_cases_per_seed"])

    donor_records=[]
    target_records=[]
    max_ns_delta=0.0
    max_vad_delta=0.0
    active_mismatch=0

    def process_corpus(path: Path,seed: int,out: list[dict[str,Any]]) -> None:
        nonlocal max_ns_delta,max_vad_delta,active_mismatch
        corpus=load_json(path)
        require(corpus.get("tier")=="research-validation","tier drift")
        require(corpus.get("dataset_lock_sha256")==expected_lock,"lock drift")
        actual_seed=int(corpus.get("generator",{}).get("seed",-1))
        require(actual_seed==seed,f"seed mismatch: {actual_seed} != {seed}")
        cases=corpus.get("cases",[])
        require(len(cases)==expected_cases,f"case count drift: {seed}")
        domain_cases=[
            c for c in cases if c.get("dimensions",{}).get("noise_domain")
        ]
        require(len(domain_cases)==expected_domain_cases,
                f"domain case count drift: {seed}")
        for case in domain_cases:
            item=analyze_case(probe,path,case,upstream_guard,seed)
            out.append(item)
            max_ns_delta=max(
                max_ns_delta,float(item["mirror"]["max_ns_upstream_gap_delta"])
            )
            max_vad_delta=max(
                max_vad_delta,float(item["mirror"]["max_vad_probability_delta"])
            )
            active_mismatch+=int(item["mirror"]["vad_active_mismatch_frames"])

    for path,seed in zip(donor_corpora,donor_seeds):
        process_corpus(path,seed,donor_records)
    for path,seed in zip(target_corpora,target_seeds):
        process_corpus(path,seed,target_records)

    donor_ids={r["metadata"]["case_key"] for r in donor_records}
    target_ids={r["metadata"]["case_key"] for r in target_records}
    require(len(donor_ids)==len(donor_records),"duplicate donor identity")
    require(len(target_ids)==len(target_records),"duplicate target identity")
    require(donor_ids.isdisjoint(target_ids),"donor/target identity overlap")

    donor_ready=[
        r for r in donor_records
        if r["first_ready_joint_reference"] is not None
    ]
    donor_by_domain={domain:[] for domain in NOISE_DOMAINS}
    for record in donor_ready:
        donor_by_domain[record["metadata"]["noise_domain"]].append(record)

    paired=[]
    receipts=[]
    benchmark_cases=0
    matched_covered=0
    negative_covered=0
    max_coherent_inconsistency=0.0

    for target in target_records:
        meta=target["metadata"]
        domain=meta["noise_domain"]
        matched=select_donors(meta,donor_by_domain,domain)
        negative=select_donors(meta,donor_by_domain,NEGATIVE_DOMAIN[domain])
        benchmark=target["first_ready_joint_reference"]
        if benchmark is not None:
            benchmark_cases+=1
        if len(matched)==DONOR_SELECT_K:
            matched_covered+=1
        if len(negative)==DONOR_SELECT_K:
            negative_covered+=1

        receipt={
            "target_case_key":meta["case_key"],
            "metadata":meta,
            "pre_ready_speech_targets":target["pre_ready_speech_targets"],
            "benchmark_available":benchmark is not None,
            "matched_donor_case_keys":[r["metadata"]["case_key"] for r in matched],
            "negative_donor_case_keys":[r["metadata"]["case_key"] for r in negative],
        }

        if (
            benchmark is not None
            and len(matched)==DONOR_SELECT_K
            and len(negative)==DONOR_SELECT_K
        ):
            target_summary=benchmark["summary"]
            control=control_aggregate(matched)
            coherent=joint_coherent_aggregate(matched)
            negative_control=control_aggregate(negative)
            negative_coherent=joint_coherent_aggregate(negative)
            max_coherent_inconsistency=max(
                max_coherent_inconsistency,
                coherent["algebraic_inconsistency"],
                negative_coherent["algebraic_inconsistency"],
            )
            row={
                "target_case_key":meta["case_key"],
                "metadata":meta,
                "has_pre_ready_speech":target["pre_ready_speech_targets"]>0,
                "target_summary":target_summary,
                "target_algebraic_inconsistency":
                    algebraic_inconsistency(target_summary),
                "control_summary":control,
                "control_abs_error":abs_error(control,target_summary),
                "control_algebraic_inconsistency":
                    algebraic_inconsistency(control),
                "coherent_summary":coherent["summary"],
                "coherent_abs_error":
                    abs_error(coherent["summary"],target_summary),
                "coherent_algebraic_inconsistency":
                    coherent["algebraic_inconsistency"],
                "coherent_selected_case_key":coherent["selected_case_key"],
                "coherent_selected_frame_index":coherent["selected_frame_index"],
                "coherent_selected_l1_distance":
                    coherent["selected_l1_distance"],
                "negative_control_gap_abs_error":
                    abs_error(negative_control,target_summary)["gap"],
                "negative_coherent_gap_abs_error":
                    abs_error(negative_coherent["summary"],target_summary)["gap"],
            }
            paired.append(row)
            receipt["paired"]=row
        receipts.append(receipt)

    gates=contract["diagnostic_gates"]
    invalid_reasons=[]
    total_targets=len(target_records)
    if len(donor_records)!=int(gates["expected_donor_cases"]):
        invalid_reasons.append("donor_case_count")
    if total_targets!=int(gates["expected_target_cases"]):
        invalid_reasons.append("target_case_count")
    if len(donor_ready)<int(gates["minimum_ready_donor_cases"]):
        invalid_reasons.append("ready_donor_count")

    benchmark_coverage=benchmark_cases/total_targets if total_targets else 0.0
    matched_coverage=matched_covered/total_targets if total_targets else 0.0
    negative_coverage=negative_covered/total_targets if total_targets else 0.0
    if benchmark_coverage<float(gates["minimum_target_benchmark_coverage"]):
        invalid_reasons.append("target_benchmark_coverage")
    if matched_coverage<float(gates["minimum_matched_donor_coverage"]):
        invalid_reasons.append("matched_donor_coverage")
    if negative_coverage<float(gates["minimum_negative_control_coverage"]):
        invalid_reasons.append("negative_control_coverage")
    if max_coherent_inconsistency>float(
        gates["max_joint_coherent_algebraic_inconsistency"]
    ):
        invalid_reasons.append("joint_coherent_algebraic_inconsistency")

    per_domain={}
    for domain in NOISE_DOMAINS:
        donors=len(donor_by_domain[domain])
        targets=[r for r in target_records if r["metadata"]["noise_domain"]==domain]
        benches=sum(r["first_ready_joint_reference"] is not None for r in targets)
        per_domain[domain]={
            "ready_donors":donors,
            "target_cases":len(targets),
            "benchmark_cases":benches,
            "benchmark_coverage":benches/len(targets) if targets else 0.0,
        }
        if donors<int(gates["minimum_ready_donors_per_domain"]):
            invalid_reasons.append("ready_donor_domain:"+domain)
        if per_domain[domain]["benchmark_coverage"]<float(
            gates["minimum_target_benchmark_coverage_per_domain"]
        ):
            invalid_reasons.append("target_benchmark_domain:"+domain)

    pre_ready=[r for r in paired if r["has_pre_ready_speech"]]
    if len(pre_ready)<int(gates["minimum_pre_ready_speech_paired_cases"]):
        invalid_reasons.append("pre_ready_speech_paired_cases")
    for domain in NAMED_DOMAINS:
        count=sum(r["metadata"]["noise_domain"]==domain for r in paired)
        if count<int(gates["minimum_named_domain_paired_cases"]):
            invalid_reasons.append("named_domain_paired_cases:"+domain)

    if max_ns_delta>float(gates["max_ns_upstream_mirror_delta"]):
        invalid_reasons.append("ns_upstream_mirror")
    if max_vad_delta>float(gates["max_vad_shipping_mirror_probability_delta"]):
        invalid_reasons.append("vad_probability_mirror")
    if active_mismatch!=int(gates["vad_shipping_mirror_active_mismatch_frames"]):
        invalid_reasons.append("vad_active_mirror")

    primary=comparison_summary(pre_ready)
    hyp=contract["directional_hypothesis"]
    supported=(
        not invalid_reasons
        and primary.get("gap_sign_test_one_sided_p") is not None
        and primary["gap_sign_test_one_sided_p"]
            <=float(hyp["maximum_one_sided_sign_test_p"])
        and primary["median_gap_error_improvement"]>0.0
        and primary["gap_better_fraction"]>0.5
    )

    decision=(
        "I031_INPUT_INVALID_REVIEW_REQUIRED"
        if invalid_reasons else
        "NS_UPSTREAM_JOINT_COHERENT_DONOR_AGGREGATION_DECOMPOSED_REVIEW_REQUIRED"
    )
    result={
        "schema_version":1,
        "investigation_id":contract["investigation_id"],
        "authority":contract["authority"],
        "source_base_sha":contract["source_base_sha"],
        "fresh_diagnostic_authority":{
            "donor_seeds":donor_seeds,
            "target_seeds":target_seeds,
        },
        "diagnostic_execution_consumed":1,
        "candidate_budget_consumed":0,
        "confirmation_budget_consumed":0,
        "shipping_mirror":{
            "max_ns_upstream_gap_delta":max_ns_delta,
            "max_vad_probability_delta":max_vad_delta,
            "vad_active_mismatch_frames":active_mismatch,
        },
        "coverage":{
            "donor_cases":len(donor_records),
            "ready_donor_cases":len(donor_ready),
            "target_cases":total_targets,
            "target_benchmark_cases":benchmark_cases,
            "target_benchmark_coverage":benchmark_coverage,
            "matched_donor_coverage":matched_coverage,
            "negative_control_coverage":negative_coverage,
            "per_domain":per_domain,
        },
        "comparison":{
            "global":comparison_summary(paired),
            "pre_ready_speech":primary,
            "by_noise_domain":{
                domain:comparison_summary([
                    r for r in paired if r["metadata"]["noise_domain"]==domain
                ])
                for domain in NOISE_DOMAINS
            },
        },
        "directional_hypothesis":{
            "primary_population":"pre_ready_speech",
            "primary_metric":"gap_absolute_error",
            "supported":supported,
            "maximum_one_sided_sign_test_p":
                hyp["maximum_one_sided_sign_test_p"],
        },
        "max_joint_coherent_algebraic_inconsistency":
            max_coherent_inconsistency,
        "receipts":receipts,
        "decision":decision,
        "invalid_reasons":sorted(set(invalid_reasons)),
        "interpretation_boundary":{
            "i029_i030_k3_matching_rule_frozen":True,
            "i029_i030_negative_control_map_frozen":True,
            "control_independent_component_median_frozen":True,
            "exactly_one_joint_coherent_operator":True,
            "joint_operator_returns_observed_frame":True,
            "joint_operator_unweighted_l1_locator":True,
            "deterministic_tie_break_case_key_then_frame_index":True,
            "donor_and_target_cases_disjoint":True,
            "donor_selection_metadata_only":True,
            "matching_metadata_development_only_not_shippable":True,
            "target_first_ready_reference_retrospective_benchmark_only":True,
            "same_target_future_frames_never_enter_donor_reference":True,
            "no_donor_rule_tuning":True,
            "no_operator_search":True,
            "no_component_counterfactual":True,
            "no_reference_source_candidate_selected":True,
            "no_shipping_candidate":True,
        },
        "authority_boundary":contract["authority_boundary"],
    }
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(
        json.dumps(result,indent=2,sort_keys=True)+"\n",
        encoding="utf-8",
    )
    return result


def self_test() -> None:
    records=[]
    for donor_index in range(3):
        frames=[]
        for i in range(8):
            mean=0.10+0.01*i+0.005*donor_index
            concentration=0.40+0.01*i+0.005*donor_index
            gap=clamp01(concentration-mean)
            frames.append({
                "mean":mean,
                "concentration":concentration,
                "gap":gap,
            })
        records.append({
            "metadata":{
                "seed":donor_index+1,
                "case_id":chr(ord("a")+donor_index),
                "case_key":f"{donor_index+1}:{chr(ord('a')+donor_index)}",
                "scenario":"research-public-noisy-clean",
                "noise_domain":"cafeteria",
                "reverb":False,
                "snr_db":5.0+5.0*donor_index,
            },
            "first_ready_joint_reference":summarize_joint_frames(frames),
        })
    coherent=joint_coherent_aggregate(records)
    assert coherent["pooled_frame_count"]==24
    assert coherent["selected_from_observed_pool"] is True
    assert coherent["algebraic_inconsistency"]<1.0e-12
    control=control_aggregate(records)
    assert set(control)=={"mean","concentration","gap"}

    target={
        "seed":99,"case_id":"t","case_key":"99:t",
        "scenario":"research-public-noisy-clean",
        "noise_domain":"cafeteria","reverb":False,"snr_db":5.0,
    }
    ranked=sorted(records,key=lambda r:compatibility_score(target,r["metadata"]))
    assert len(ranked)==3
    assert NEGATIVE_DOMAIN["cafeteria"]=="bus"
    assert sign_test_one_sided(9,1)<0.02
    print("I031 joint-coherent donor aggregation self-test: OK")


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--probe",type=Path)
    parser.add_argument("--contract",type=Path)
    parser.add_argument("--donor-corpus",action="append",type=Path,default=[])
    parser.add_argument("--target-corpus",action="append",type=Path,default=[])
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if (
        not args.probe or not args.contract or not args.output
        or not args.donor_corpus or not args.target_corpus
    ):
        parser.error(
            "--probe --contract --donor-corpus --target-corpus --output are required"
        )
    result=evaluate(
        args.probe,args.donor_corpus,args.target_corpus,args.contract,args.output
    )
    print(json.dumps({
        "decision":result["decision"],
        "invalid_reasons":result["invalid_reasons"],
        "coverage":result["coverage"],
        "pre_ready_speech":result["comparison"]["pre_ready_speech"],
        "directional_hypothesis":result["directional_hypothesis"],
        "max_joint_coherent_algebraic_inconsistency":
            result["max_joint_coherent_algebraic_inconsistency"],
    },sort_keys=True))
    return 0 if result["decision"]!="I031_INPUT_INVALID_REVIEW_REQUIRED" else 2


if __name__=="__main__":
    raise SystemExit(main())
