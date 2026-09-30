#!/usr/bin/env python3
"""I033 candidate-zero NS/VAD causal noise-delta alignment diagnostic."""

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
NOISE_DOMAINS=("kitchen","traffic","living","office","cafeteria","bus","field")


def require(condition: bool,message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_json(path: Path) -> dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value,dict),f"JSON object required: {path}")
    return value


def percentile_nearest_rank(values: list[float],q: float) -> float | None:
    if not values:
        return None
    require(0.0<q<=1.0,"nearest-rank percentile q out of range")
    ordered=sorted(values)
    rank=max(1,math.ceil(q*len(ordered)))
    return ordered[rank-1]


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


def reference_frame(
    row: dict[str,Any],
    local_index: int,
) -> dict[str,float|int]:
    return {
        "local_frame_index":local_index,
        "absolute_frame_index":int(row["frame"]),
        "ns_noise_rms_dbfs":float(row["ns_noise_rms_dbfs"]),
        "post_ns_rms_dbfs":float(row["post_ns_rms_dbfs"]),
        "mirror_gap":float(row["mirror_gap"]),
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

    with tempfile.TemporaryDirectory(prefix="ap-i033-") as tmp:
        _,raw=engine.stage_audio(mic,16000,1,Path(tmp),"mic.pcm")
        rows=run_probe(probe,raw)

    labels=[int(v) for v in engine.load_labels(labels_path)]
    count=min(len(rows),len(labels))
    require(count>WARMUP,"case too short")
    rows=rows[WARMUP:count]
    labels=labels[WARMUP:count]

    prior_references=[]
    first_pre_ready_target=None
    anchor=None
    later_references=[]
    max_ns_delta=0.0
    max_vad_delta=0.0
    active_mismatch=0

    for local_index,(row,label) in enumerate(zip(rows,labels)):
        require(label in (0,1),"invalid label")
        upstream=float(row["upstream_probability"])
        gap=float(row["mirror_gap"])
        ns_noise=float(row["ns_noise_rms_dbfs"])
        post_ns=float(row["post_ns_rms_dbfs"])
        public=float(row["public_shipping_probability"])
        shipping=float(row["shipping_probability"])
        require(all(math.isfinite(v) for v in (
            upstream,gap,ns_noise,post_ns,public,shipping
        )),"non-finite I033 metric")

        max_ns_delta=max(max_ns_delta,abs(upstream-gap))
        max_vad_delta=max(max_vad_delta,abs(public-shipping))
        active_mismatch+=int(
            int(row["public_shipping_active"])!=int(row["shipping_active"])
        )

        is_disagreement=disagreement(row,upstream_guard)
        is_reference=(label==0 and not is_disagreement)

        if (
            first_pre_ready_target is None
            and label==1
            and is_disagreement
            and len(prior_references)<REFERENCE_COUNT
        ):
            first_pre_ready_target={
                "local_frame_index":local_index,
                "absolute_frame_index":int(row["frame"]),
                "prior_reference_count":len(prior_references),
                "ns_noise_rms_dbfs":ns_noise,
                "post_ns_rms_dbfs":post_ns,
                "mirror_gap":gap,
            }
            if prior_references:
                anchor=prior_references[-1]
            continue

        if is_reference:
            frame=reference_frame(row,local_index)
            if first_pre_ready_target is None:
                if len(prior_references)<REFERENCE_COUNT:
                    prior_references.append(frame)
            elif (
                local_index>first_pre_ready_target["local_frame_index"]
                and len(later_references)<REFERENCE_COUNT
            ):
                later_references.append(frame)

    later_summary=None
    if len(later_references)==REFERENCE_COUNT:
        later_summary={
            "post_ns_rms_dbfs":statistics.median(
                float(frame["post_ns_rms_dbfs"])
                for frame in later_references
            ),
            "ns_noise_rms_dbfs":statistics.median(
                float(frame["ns_noise_rms_dbfs"])
                for frame in later_references
            ),
            "mirror_gap":statistics.median(
                float(frame["mirror_gap"])
                for frame in later_references
            ),
        }

    return {
        "metadata":meta,
        "first_pre_ready_target":first_pre_ready_target,
        "causal_anchor":anchor,
        "later_reference_frames":later_references,
        "later_reference_summary":later_summary,
        "mirror":{
            "max_ns_upstream_gap_delta":max_ns_delta,
            "max_vad_probability_delta":max_vad_delta,
            "vad_active_mismatch_frames":active_mismatch,
        },
    }


def delta_summary(records: list[dict[str,Any]]) -> dict[str,Any]:
    if not records:
        return {"cases":0}
    errors=[float(r["delta_abs_error_db"]) for r in records]
    signed=[float(r["delta_signed_error_db"]) for r in records]
    ns_delta=[float(r["causal_ns_delta_db"]) for r in records]
    local_delta=[float(r["future_local_delta_db"]) for r in records]
    return {
        "cases":len(records),
        "median_absolute_delta_error_db":statistics.median(errors),
        "p90_absolute_delta_error_db":percentile_nearest_rank(errors,0.90),
        "max_absolute_delta_error_db":max(errors),
        "median_signed_delta_error_db":statistics.median(signed),
        "median_causal_ns_delta_db":statistics.median(ns_delta),
        "median_future_local_delta_db":statistics.median(local_delta),
    }


def evaluate(
    probe: Path,
    corpora: list[Path],
    contract_path: Path,
    output: Path,
) -> dict[str,Any]:
    contract=load_json(contract_path)
    require(
        contract["investigation_id"]
        =="i033-ns-vad-causal-noise-delta-alignment-v1",
        "contract identity drift",
    )
    authority=contract["fresh_diagnostic_authority"]
    seeds=[int(v) for v in authority["target_seeds"]]
    require(len(corpora)==len(seeds),"target corpus count mismatch")
    require(len(set(seeds))==len(seeds),"duplicate target seeds")
    require(authority["diagnostic_execution_limit"]==1,"execution budget drift")
    require(authority["candidate_limit"]==0,"candidate budget drift")
    require(authority["confirmation_limit"]==0,"confirmation budget drift")

    upstream_guard=float(
        contract["fixed_shipping_semantics"]["vad_upstream_speech_guard"]
    )
    expected_lock=contract["dataset_authority"]["dataset_lock_sha256"]
    expected_cases=int(authority["expected_cases_per_seed"])
    expected_domain_cases=int(authority["expected_noise_domain_cases_per_seed"])

    records=[]
    max_ns_delta=0.0
    max_vad_delta=0.0
    active_mismatch=0

    for path,seed in zip(corpora,seeds):
        corpus=load_json(path)
        require(corpus.get("tier")=="research-validation","tier drift")
        require(corpus.get("dataset_lock_sha256")==expected_lock,"lock drift")
        actual_seed=int(corpus.get("generator",{}).get("seed",-1))
        require(actual_seed==seed,f"seed mismatch: {actual_seed} != {seed}")
        cases=corpus.get("cases",[])
        require(len(cases)==expected_cases,f"case count drift: {seed}")
        domain_cases=[
            case for case in cases
            if case.get("dimensions",{}).get("noise_domain")
        ]
        require(len(domain_cases)==expected_domain_cases,
                f"domain case count drift: {seed}")
        for case in domain_cases:
            item=analyze_case(probe,path,case,upstream_guard,seed)
            records.append(item)
            max_ns_delta=max(
                max_ns_delta,float(item["mirror"]["max_ns_upstream_gap_delta"])
            )
            max_vad_delta=max(
                max_vad_delta,float(item["mirror"]["max_vad_probability_delta"])
            )
            active_mismatch+=int(item["mirror"]["vad_active_mismatch_frames"])

    identities={r["metadata"]["case_key"] for r in records}
    require(len(identities)==len(records),"duplicate target identity")

    causal=[
        r for r in records if r["first_pre_ready_target"] is not None
    ]
    anchored=[
        r for r in causal if r["causal_anchor"] is not None
    ]
    benchmarkable=[
        r for r in anchored if r["later_reference_summary"] is not None
    ]

    paired=[]
    receipts=[]
    for record in records:
        target=record["first_pre_ready_target"]
        anchor=record["causal_anchor"]
        later=record["later_reference_summary"]
        receipt={
            "target_case_key":record["metadata"]["case_key"],
            "metadata":record["metadata"],
            "causal_target":target,
            "causal_anchor":anchor,
            "later_reference_count":len(record["later_reference_frames"]),
            "later_reference_summary":later,
        }
        if target is not None and anchor is not None and later is not None:
            ns_delta=(
                float(target["ns_noise_rms_dbfs"])
                - float(anchor["ns_noise_rms_dbfs"])
            )
            local_delta=(
                float(later["post_ns_rms_dbfs"])
                - float(anchor["post_ns_rms_dbfs"])
            )
            target_local_delta=(
                float(target["post_ns_rms_dbfs"])
                - float(anchor["post_ns_rms_dbfs"])
            )
            row={
                "target_case_key":record["metadata"]["case_key"],
                "metadata":record["metadata"],
                "target_prior_reference_count":
                    int(target["prior_reference_count"]),
                "anchor_absolute_frame_index":
                    int(anchor["absolute_frame_index"]),
                "target_absolute_frame_index":
                    int(target["absolute_frame_index"]),
                "causal_ns_delta_db":ns_delta,
                "future_local_delta_db":local_delta,
                "causal_target_local_delta_db":target_local_delta,
                "delta_signed_error_db":ns_delta-local_delta,
                "delta_abs_error_db":abs(ns_delta-local_delta),
                "anchor_ns_noise_rms_dbfs":
                    float(anchor["ns_noise_rms_dbfs"]),
                "target_ns_noise_rms_dbfs":
                    float(target["ns_noise_rms_dbfs"]),
                "anchor_post_ns_rms_dbfs":
                    float(anchor["post_ns_rms_dbfs"]),
                "later_post_ns_rms_dbfs":
                    float(later["post_ns_rms_dbfs"]),
            }
            paired.append(row)
            receipt["paired"]=row
        receipts.append(receipt)

    gates=contract["diagnostic_gates"]
    invalid_reasons=[]
    if len(records)!=int(gates["expected_target_cases"]):
        invalid_reasons.append("target_case_count")
    if len(causal)<int(gates["minimum_causal_target_cases"]):
        invalid_reasons.append("causal_target_cases")
    if len(anchored)<int(gates["minimum_causal_anchor_cases"]):
        invalid_reasons.append("causal_anchor_cases")
    anchor_coverage=len(anchored)/len(causal) if causal else 0.0
    benchmark_coverage=(
        len(benchmarkable)/len(anchored) if anchored else 0.0
    )
    if anchor_coverage<float(gates["minimum_causal_anchor_coverage"]):
        invalid_reasons.append("causal_anchor_coverage")
    if benchmark_coverage<float(gates["minimum_post_target_benchmark_coverage"]):
        invalid_reasons.append("post_target_benchmark_coverage")

    per_domain={}
    for domain in NOISE_DOMAINS:
        domain_causal=[
            r for r in causal
            if r["metadata"]["noise_domain"]==domain
        ]
        domain_anchored=[
            r for r in anchored
            if r["metadata"]["noise_domain"]==domain
        ]
        domain_benchmark=[
            r for r in benchmarkable
            if r["metadata"]["noise_domain"]==domain
        ]
        per_domain[domain]={
            "causal_target_cases":len(domain_causal),
            "causal_anchor_cases":len(domain_anchored),
            "benchmarkable_anchor_cases":len(domain_benchmark),
            "causal_anchor_coverage":
                len(domain_anchored)/len(domain_causal)
                if domain_causal else None,
            "post_target_benchmark_coverage":
                len(domain_benchmark)/len(domain_anchored)
                if domain_anchored else None,
        }

    if max_ns_delta>float(gates["max_ns_upstream_mirror_delta"]):
        invalid_reasons.append("ns_upstream_mirror")
    if max_vad_delta>float(gates["max_vad_shipping_mirror_probability_delta"]):
        invalid_reasons.append("vad_probability_mirror")
    if active_mismatch!=int(gates["vad_shipping_mirror_active_mismatch_frames"]):
        invalid_reasons.append("vad_active_mirror")

    fidelity=delta_summary(paired)
    bounds=contract["delta_alignment_hypothesis"]
    supported=(
        not invalid_reasons
        and fidelity.get("median_absolute_delta_error_db") is not None
        and fidelity["median_absolute_delta_error_db"]
            <=float(bounds["maximum_median_absolute_delta_error_db"])
        and fidelity["p90_absolute_delta_error_db"]
            <=float(bounds["maximum_p90_absolute_delta_error_db"])
    )

    decision=(
        "I033_INPUT_INVALID_REVIEW_REQUIRED"
        if invalid_reasons else
        "NS_VAD_CAUSAL_NOISE_DELTA_ALIGNMENT_DECOMPOSED_REVIEW_REQUIRED"
    )
    result={
        "schema_version":1,
        "investigation_id":contract["investigation_id"],
        "authority":contract["authority"],
        "source_base_sha":contract["source_base_sha"],
        "fresh_diagnostic_authority":{"target_seeds":seeds},
        "diagnostic_execution_consumed":1,
        "candidate_budget_consumed":0,
        "confirmation_budget_consumed":0,
        "shipping_mirror":{
            "max_ns_upstream_gap_delta":max_ns_delta,
            "max_vad_probability_delta":max_vad_delta,
            "vad_active_mismatch_frames":active_mismatch,
        },
        "coverage":{
            "target_cases":len(records),
            "causal_target_cases":len(causal),
            "causal_anchor_cases":len(anchored),
            "benchmarkable_anchor_cases":len(benchmarkable),
            "causal_anchor_coverage":anchor_coverage,
            "post_target_benchmark_coverage":benchmark_coverage,
            "per_domain":per_domain,
        },
        "delta_alignment":{
            "global":fidelity,
            "by_noise_domain":{
                domain:delta_summary([
                    r for r in paired
                    if r["metadata"]["noise_domain"]==domain
                ])
                for domain in NOISE_DOMAINS
            },
        },
        "delta_alignment_hypothesis":{
            "supported":supported,
            "maximum_median_absolute_delta_error_db":
                bounds["maximum_median_absolute_delta_error_db"],
            "maximum_p90_absolute_delta_error_db":
                bounds["maximum_p90_absolute_delta_error_db"],
        },
        "receipts":receipts,
        "decision":decision,
        "invalid_reasons":sorted(set(invalid_reasons)),
        "interpretation_boundary":{
            "target_only_no_donor_selection":True,
            "causal_anchor_is_last_prior_ordinary_noise_reference":True,
            "target_is_first_pre_ready_speech_disagreement":True,
            "anchor_and_target_are_causal":True,
            "post_target_benchmark_is_retrospective_only":True,
            "same_anchor_used_for_ns_and_local_deltas":True,
            "ns_delta_uses_shipping_ns_noise_rms_dbfs":True,
            "local_delta_uses_post_ns_frame_rms_dbfs":True,
            "shipping_ns_vad_source_unchanged":True,
            "no_absolute_normalization_mapping":True,
            "no_vad_noise_state_refresh_rule":True,
            "no_threshold_search":True,
            "no_source_candidate":True,
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
    assert percentile_nearest_rank([1,2,3,4,5,6,7,8,9,10],0.9)==9
    assert REFERENCE_COUNT==8
    assert len(NOISE_DOMAINS)==7
    print("I033 causal noise-delta alignment self-test: OK")


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--probe",type=Path)
    parser.add_argument("--contract",type=Path)
    parser.add_argument("--target-corpus",action="append",type=Path,default=[])
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.probe or not args.contract or not args.output or not args.target_corpus:
        parser.error(
            "--probe --contract --target-corpus --output are required"
        )
    result=evaluate(
        args.probe,args.target_corpus,args.contract,args.output
    )
    print(json.dumps({
        "decision":result["decision"],
        "invalid_reasons":result["invalid_reasons"],
        "coverage":result["coverage"],
        "delta_alignment":result["delta_alignment"]["global"],
        "delta_alignment_hypothesis":result["delta_alignment_hypothesis"],
    },sort_keys=True))
    return 0 if result["decision"]!="I033_INPUT_INVALID_REVIEW_REQUIRED" else 2


if __name__=="__main__":
    raise SystemExit(main())
