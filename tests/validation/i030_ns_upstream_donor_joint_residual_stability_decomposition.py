#!/usr/bin/env python3
"""I030 candidate-zero donor joint-residual and stability decomposition."""

from __future__ import annotations

import argparse
from collections import Counter
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
EPS=1.0e-12
NOISE_DOMAINS=("kitchen","traffic","living","office","cafeteria","bus","field")
STRESS_DOMAINS=("bus","field")
COMPARISON_DOMAINS=("living","cafeteria")
SNR_STRATA=(-5.0,0.0,5.0,10.0,15.0)
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


def median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def mad(values: list[float]) -> float | None:
    if not values:
        return None
    center=statistics.median(values)
    return statistics.median(abs(v-center) for v in values)


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
    # This is intentionally byte-for-byte equivalent in semantics to I029.
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
    summary={}
    dispersion={}
    for key in ("mean","concentration","gap"):
        values=[float(frame[key]) for frame in frames]
        summary[key]=statistics.median(values)
        dispersion[key]=mad(values)
    joint_l1=[
        (
            abs(float(frame["mean"])-summary["mean"])
            + abs(float(frame["concentration"])-summary["concentration"])
            + abs(float(frame["gap"])-summary["gap"])
        )
        for frame in frames
    ]
    dispersion["joint_l1_median"]=statistics.median(joint_l1)
    return {
        "frames":frames,
        "summary":summary,
        "within_frame_dispersion":dispersion,
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

    with tempfile.TemporaryDirectory(prefix="ap-i030-") as tmp:
        _,raw=engine.stage_audio(mic,16000,1,Path(tmp),"mic.pcm")
        rows=run_probe(probe,raw)

    labels=[int(v) for v in engine.load_labels(labels_path)]
    count=min(len(rows),len(labels))
    require(count>WARMUP,"case too short")
    rows=rows[WARMUP:count]
    labels=labels[WARMUP:count]

    joint_frames=[]
    raw_noise=0
    raw_speech=0
    pre_ready_noise=0
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
        )),"non-finite I030 metric")

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

        if not is_disagreement:
            continue

        if label==0:
            raw_noise+=1
            if len(joint_frames)<REFERENCE_COUNT:
                pre_ready_noise+=1
        else:
            raw_speech+=1
            if len(joint_frames)<REFERENCE_COUNT:
                pre_ready_speech+=1

    return {
        "metadata":meta,
        "first_ready_joint_reference":summarize_joint_frames(joint_frames),
        "raw_targets":{
            "noise":raw_noise,
            "speech":raw_speech,
            "pre_ready_noise":pre_ready_noise,
            "pre_ready_speech":pre_ready_speech,
        },
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


def aggregate_reference(records: list[dict[str,Any]]) -> dict[str,float]:
    require(len(records)==DONOR_SELECT_K,"I030 requires exactly K donor records")
    return {
        key:statistics.median(
            float(r["first_ready_joint_reference"]["summary"][key])
            for r in records
        )
        for key in ("mean","concentration","gap")
    }


def signed_residual(
    donor_summary: dict[str,float],
    target_summary: dict[str,float],
) -> dict[str,float]:
    return {
        key:float(donor_summary[key])-float(target_summary[key])
        for key in ("mean","concentration","gap")
    }


def abs_error(residual: dict[str,float]) -> dict[str,float]:
    return {key:abs(value) for key,value in residual.items()}


def selected_donor_stability(records: list[dict[str,Any]]) -> dict[str,Any]:
    require(len(records)==DONOR_SELECT_K,"I030 requires K donors for stability")
    within={}
    between={}
    for key in ("mean","concentration","gap"):
        within_values=[
            float(r["first_ready_joint_reference"]["within_frame_dispersion"][key])
            for r in records
        ]
        donor_medians=[
            float(r["first_ready_joint_reference"]["summary"][key])
            for r in records
        ]
        within[key]=statistics.median(within_values)
        between[key]=mad(donor_medians)
    within["joint_l1_median"]=statistics.median(
        float(r["first_ready_joint_reference"]["within_frame_dispersion"]["joint_l1_median"])
        for r in records
    )
    return {
        "median_within_donor_mad":within,
        "between_donor_mad":between,
    }


def target_stability(record: dict[str,Any]) -> dict[str,float]:
    ref=record["first_ready_joint_reference"]
    require(ref is not None,"target benchmark required")
    return {
        key:float(ref["within_frame_dispersion"][key])
        for key in ("mean","concentration","gap","joint_l1_median")
    }


def joint_alignment(residual: dict[str,float]) -> dict[str,float]:
    mean_r=float(residual["mean"])
    concentration_r=float(residual["concentration"])
    gap_r=float(residual["gap"])
    implied_gap=concentration_r-mean_r
    gap_axis=(concentration_r-mean_r)/math.sqrt(2.0)
    common_mode=(concentration_r+mean_r)/math.sqrt(2.0)
    return {
        "component_implied_gap_residual":implied_gap,
        "observed_gap_residual":gap_r,
        "gap_alignment_error":abs(gap_r-implied_gap),
        "gap_axis_projection":gap_axis,
        "common_mode_projection":common_mode,
        "gap_axis_fraction":
            abs(gap_axis)/(abs(gap_axis)+abs(common_mode)+EPS),
        "component_residual_same_sign":
            1.0 if mean_r*concentration_r>0.0 else 0.0,
    }


def median_dict(records: list[dict[str,Any]],path: tuple[str,...]) -> float | None:
    values=[]
    for record in records:
        value: Any=record
        ok=True
        for key in path:
            if not isinstance(value,dict) or key not in value:
                ok=False
                break
            value=value[key]
        if ok and value is not None:
            values.append(float(value))
    return median(values)


def sign_counts(values: list[float]) -> dict[str,int]:
    return {
        "positive":sum(v>0 for v in values),
        "negative":sum(v<0 for v in values),
        "zero":sum(v==0 for v in values),
    }


def population_summary(records: list[dict[str,Any]]) -> dict[str,Any]:
    if not records:
        return {"paired_cases":0}
    improvements={
        key:[
            float(r["negative_abs_error"][key])
            - float(r["matched_abs_error"][key])
            for r in records
        ]
        for key in ("mean","concentration","gap")
    }
    return {
        "paired_cases":len(records),
        "median_matched_abs_error":{
            key:median_dict(records,("matched_abs_error",key))
            for key in ("mean","concentration","gap")
        },
        "median_negative_abs_error":{
            key:median_dict(records,("negative_abs_error",key))
            for key in ("mean","concentration","gap")
        },
        "median_paired_improvement":{
            key:median(improvements[key])
            for key in ("mean","concentration","gap")
        },
        "paired_improvement_sign_counts":{
            key:sign_counts(improvements[key])
            for key in ("mean","concentration","gap")
        },
        "median_signed_residual":{
            key:median_dict(records,("matched_signed_residual",key))
            for key in ("mean","concentration","gap")
        },
        "median_donor_between_mad":{
            key:median_dict(records,("matched_stability","between_donor_mad",key))
            for key in ("mean","concentration","gap")
        },
        "median_donor_within_mad":{
            key:median_dict(records,("matched_stability","median_within_donor_mad",key))
            for key in ("mean","concentration","gap")
        },
        "median_target_mad":{
            key:median_dict(records,("target_stability",key))
            for key in ("mean","concentration","gap")
        },
        "median_gap_alignment_error":
            median_dict(records,("matched_alignment","gap_alignment_error")),
        "median_gap_axis_fraction":
            median_dict(records,("matched_alignment","gap_axis_fraction")),
        "same_sign_component_residual_fraction":
            median_dict(records,("matched_alignment","component_residual_same_sign")),
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
        =="i030-ns-upstream-donor-joint-residual-stability-decomposition-v1",
        "contract identity drift",
    )
    authority=contract["fresh_diagnostic_authority"]
    donor_seeds=[int(v) for v in authority["donor_seeds"]]
    target_seeds=[int(v) for v in authority["target_seeds"]]
    require(len(donor_corpora)==len(donor_seeds),"donor corpus count mismatch")
    require(len(target_corpora)==len(target_seeds),"target corpus count mismatch")
    require(set(donor_seeds).isdisjoint(target_seeds),
            "donor and target seeds overlap")
    require(
        {
            "diagnostic_execution_limit":authority["diagnostic_execution_limit"],
            "candidate_limit":authority["candidate_limit"],
            "confirmation_limit":authority["confirmation_limit"],
        } == {
            "diagnostic_execution_limit":1,
            "candidate_limit":0,
            "confirmation_limit":0,
        },
        "I030 budget drift",
    )

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
        require(corpus.get("tier")=="research-validation",
                "public development tier drift")
        require(corpus.get("dataset_lock_sha256")==expected_lock,
                "dataset lock binding drift")
        actual_seed=int(corpus.get("generator",{}).get("seed",-1))
        require(actual_seed==seed,f"seed mismatch: {actual_seed} != {seed}")
        cases=corpus.get("cases",[])
        require(len(cases)==expected_cases,
                f"unexpected case count for seed={seed}")
        domain_cases=[
            c for c in cases if c.get("dimensions",{}).get("noise_domain")
        ]
        require(len(domain_cases)==expected_domain_cases,
                f"unexpected domain case count for seed={seed}")
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
    require(len(donor_ids)==len(donor_records),"duplicate donor case identity")
    require(len(target_ids)==len(target_records),"duplicate target case identity")
    require(donor_ids.isdisjoint(target_ids),"donor/target case identity overlap")

    donor_ready=[
        r for r in donor_records
        if r["first_ready_joint_reference"] is not None
    ]
    donor_by_domain={domain:[] for domain in NOISE_DOMAINS}
    for record in donor_ready:
        donor_by_domain[record["metadata"]["noise_domain"]].append(record)

    paired=[]
    receipts=[]
    matched_covered=0
    negative_covered=0
    benchmark_cases=0

    for target in target_records:
        meta=target["metadata"]
        domain=meta["noise_domain"]
        matched=select_donors(meta,donor_by_domain,domain)
        negative_domain=NEGATIVE_DOMAIN[domain]
        negative=select_donors(meta,donor_by_domain,negative_domain)
        benchmark=target["first_ready_joint_reference"]
        if len(matched)==DONOR_SELECT_K:
            matched_covered+=1
        if len(negative)==DONOR_SELECT_K:
            negative_covered+=1
        if benchmark is not None:
            benchmark_cases+=1

        receipt={
            "target_case_key":meta["case_key"],
            "metadata":meta,
            "pre_ready_speech_targets":target["raw_targets"]["pre_ready_speech"],
            "pre_ready_noise_targets":target["raw_targets"]["pre_ready_noise"],
            "target_first_ready_reference_available":benchmark is not None,
            "matched_donor_case_keys":[
                r["metadata"]["case_key"] for r in matched
            ],
            "negative_donor_case_keys":[
                r["metadata"]["case_key"] for r in negative
            ],
        }

        if (
            benchmark is not None
            and len(matched)==DONOR_SELECT_K
            and len(negative)==DONOR_SELECT_K
        ):
            target_summary=benchmark["summary"]
            matched_summary=aggregate_reference(matched)
            negative_summary=aggregate_reference(negative)
            matched_residual=signed_residual(matched_summary,target_summary)
            negative_residual=signed_residual(negative_summary,target_summary)
            record={
                "target_case_key":meta["case_key"],
                "metadata":meta,
                "has_pre_ready_speech":
                    target["raw_targets"]["pre_ready_speech"]>0,
                "target_reference_frames":benchmark["frames"],
                "matched_donor_case_keys":[
                    r["metadata"]["case_key"] for r in matched
                ],
                "negative_donor_case_keys":[
                    r["metadata"]["case_key"] for r in negative
                ],
                "matched_donor_joint_frames":{
                    r["metadata"]["case_key"]:
                        r["first_ready_joint_reference"]["frames"]
                    for r in matched
                },
                "negative_donor_joint_frames":{
                    r["metadata"]["case_key"]:
                        r["first_ready_joint_reference"]["frames"]
                    for r in negative
                },
                "target_summary":target_summary,
                "matched_summary":matched_summary,
                "negative_summary":negative_summary,
                "matched_signed_residual":matched_residual,
                "negative_signed_residual":negative_residual,
                "matched_abs_error":abs_error(matched_residual),
                "negative_abs_error":abs_error(negative_residual),
                "matched_stability":selected_donor_stability(matched),
                "negative_stability":selected_donor_stability(negative),
                "target_stability":target_stability(target),
                "matched_alignment":joint_alignment(matched_residual),
                "negative_alignment":joint_alignment(negative_residual),
            }
            paired.append(record)
            receipt["paired"]=record
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

    domain_counts={}
    for domain in NOISE_DOMAINS:
        ready_donors=len(donor_by_domain[domain])
        targets=[
            r for r in target_records
            if r["metadata"]["noise_domain"]==domain
        ]
        benchmarks=sum(
            r["first_ready_joint_reference"] is not None for r in targets
        )
        domain_counts[domain]={
            "ready_donors":ready_donors,
            "target_cases":len(targets),
            "benchmark_cases":benchmarks,
            "benchmark_coverage":benchmarks/len(targets) if targets else 0.0,
        }
        if ready_donors<int(gates["minimum_ready_donors_per_domain"]):
            invalid_reasons.append("ready_donor_domain:"+domain)
        if domain_counts[domain]["benchmark_coverage"]<float(
            gates["minimum_target_benchmark_coverage_per_domain"]
        ):
            invalid_reasons.append("target_benchmark_domain:"+domain)

    pre_ready=[r for r in paired if r["has_pre_ready_speech"]]
    if len(pre_ready)<int(gates["minimum_pre_ready_speech_paired_cases"]):
        invalid_reasons.append("pre_ready_speech_paired_cases")

    for domain in STRESS_DOMAINS+COMPARISON_DOMAINS:
        count=sum(r["metadata"]["noise_domain"]==domain for r in paired)
        if count<int(gates["minimum_named_domain_paired_cases"]):
            invalid_reasons.append("named_domain_paired_cases:"+domain)

    if max_ns_delta>float(gates["max_ns_upstream_mirror_delta"]):
        invalid_reasons.append("ns_upstream_mirror")
    if max_vad_delta>float(gates["max_vad_shipping_mirror_probability_delta"]):
        invalid_reasons.append("vad_probability_mirror")
    if active_mismatch!=int(gates["vad_shipping_mirror_active_mismatch_frames"]):
        invalid_reasons.append("vad_active_mirror")

    by_domain={
        domain:population_summary([
            r for r in paired if r["metadata"]["noise_domain"]==domain
        ])
        for domain in NOISE_DOMAINS
    }
    by_snr={
        f"{snr:g}":population_summary([
            r for r in paired
            if r["metadata"].get("snr_db") is not None
            and float(r["metadata"]["snr_db"])==snr
        ])
        for snr in SNR_STRATA
    }
    by_reverb={
        str(value).lower():population_summary([
            r for r in paired
            if r["metadata"].get("reverb") is not None
            and bool(r["metadata"]["reverb"])==value
        ])
        for value in (False,True)
    }
    decision=(
        "I030_INPUT_INVALID_REVIEW_REQUIRED"
        if invalid_reasons else
        "NS_UPSTREAM_DONOR_JOINT_RESIDUAL_STABILITY_DECOMPOSED_REVIEW_REQUIRED"
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
            "per_domain":domain_counts,
        },
        "decomposition":{
            "global":population_summary(paired),
            "pre_ready_speech":population_summary(pre_ready),
            "by_noise_domain":by_domain,
            "by_snr_db":by_snr,
            "by_reverb":by_reverb,
            "stress_domains":list(STRESS_DOMAINS),
            "comparison_domains":list(COMPARISON_DOMAINS),
        },
        "receipts":receipts,
        "decision":decision,
        "invalid_reasons":sorted(set(invalid_reasons)),
        "interpretation_boundary":{
            "i029_k3_matching_rule_frozen":True,
            "i029_negative_control_map_frozen":True,
            "joint_eight_frame_references_preserved":True,
            "donor_and_target_cases_disjoint":True,
            "donor_selection_metadata_only":True,
            "matching_metadata_development_only_not_shippable":True,
            "target_first_ready_reference_retrospective_benchmark_only":True,
            "same_target_future_frames_never_enter_donor_reference":True,
            "no_matching_rule_tuning":True,
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
    frames=[
        {"mean":0.1+i*0.01,"concentration":0.4+i*0.01,"gap":0.3}
        for i in range(REFERENCE_COUNT)
    ]
    summary=summarize_joint_frames(frames)
    assert summary is not None
    assert len(summary["frames"])==8
    assert summary["within_frame_dispersion"]["mean"]>0
    target={
        "seed":1,"case_id":"t","case_key":"1:t",
        "scenario":"research-public-noisy-clean",
        "noise_domain":"cafeteria","reverb":False,"snr_db":5.0,
    }
    donors=[
        {"metadata":{
            "seed":2,"case_id":"a","case_key":"2:a",
            "scenario":"research-public-noisy-clean",
            "noise_domain":"cafeteria","reverb":False,"snr_db":5.0,
        }},
        {"metadata":{
            "seed":3,"case_id":"b","case_key":"3:b",
            "scenario":"research-public-noisy-clean",
            "noise_domain":"cafeteria","reverb":False,"snr_db":10.0,
        }},
        {"metadata":{
            "seed":4,"case_id":"c","case_key":"4:c",
            "scenario":"research-public-noise-only",
            "noise_domain":"cafeteria","reverb":None,"snr_db":None,
        }},
    ]
    ranked=sorted(donors,key=lambda r:compatibility_score(target,r["metadata"]))
    assert [r["metadata"]["case_id"] for r in ranked]==["a","b","c"]
    residual={"mean":0.1,"concentration":0.3,"gap":0.18}
    align=joint_alignment(residual)
    assert abs(align["component_implied_gap_residual"]-0.2)<1e-9
    assert abs(align["gap_alignment_error"]-0.02)<1e-9
    assert NEGATIVE_DOMAIN["bus"]=="field"
    assert STRESS_DOMAINS==("bus","field")
    assert COMPARISON_DOMAINS==("living","cafeteria")
    assert SNR_STRATA==(-5.0,0.0,5.0,10.0,15.0)
    print("I030 donor joint-residual stability decomposition self-test: OK")


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
        "pre_ready_speech":
            result["decomposition"]["pre_ready_speech"],
        "stress_domains":{
            key:result["decomposition"]["by_noise_domain"][key]
            for key in STRESS_DOMAINS
        },
        "comparison_domains":{
            key:result["decomposition"]["by_noise_domain"][key]
            for key in COMPARISON_DOMAINS
        },
    },sort_keys=True))
    return 0 if result["decision"]!="I030_INPUT_INVALID_REVIEW_REQUIRED" else 2


if __name__=="__main__":
    raise SystemExit(main())
