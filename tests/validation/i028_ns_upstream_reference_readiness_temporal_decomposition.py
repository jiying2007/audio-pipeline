#!/usr/bin/env python3
"""I028 candidate-zero temporal decomposition of NS reference readiness."""

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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "validation" / "tools"))
import run_validation_engine as engine  # type: ignore

WARMUP = 80
REFERENCE_READY_COUNT = 8
NOISE_DOMAINS = ("kitchen", "traffic", "living", "office", "cafeteria", "bus", "field")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_json(path: Path) -> dict[str, Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value,dict),f"JSON object required: {path}")
    return value


def run_probe(probe: Path, pcm: Path) -> list[dict[str, Any]]:
    proc=subprocess.run(
        [str(probe),str(pcm)],
        check=True,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
    )
    rows=[json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    require(bool(rows) and all(isinstance(row,dict) for row in rows),"probe output invalid")
    return rows


def disagreement(row: dict[str, Any], upstream_guard: float) -> bool:
    return (
        float(row["upstream_probability"]) > upstream_guard
        and not int(row["local_guard_pass"])
    )


def empty_accumulator() -> dict[str, Any]:
    return {
        "raw_noise_targets":0,
        "raw_speech_targets":0,
        "pre_ready_noise_targets":0,
        "pre_ready_speech_targets":0,
        "ready_noise_targets":0,
        "ready_speech_targets":0,
        "target_cases":0,
        "cases_first_target_before_ready":0,
        "cases_never_ready":0,
        "ordinary_reference_frames":0,
        "pre_ready_noise_frame_index":[],
        "pre_ready_speech_frame_index":[],
        "ready_noise_frame_index":[],
        "ready_speech_frame_index":[],
        "pre_ready_noise_prior_count":[],
        "pre_ready_speech_prior_count":[],
        "all_noise_prior_count":[],
        "all_speech_prior_count":[],
        "first_reference_frame_index":[],
        "first_target_frame_index":[],
        "first_ready_frame_index":[],
        "ready_minus_first_target_frames":[],
        "reference_frames_before_first_target":[],
        "median_reference_interarrival_frames":[],
        "max_reference_interarrival_frames":[],
    }


def append_case(acc: dict[str, Any], item: dict[str, Any]) -> None:
    for key in (
        "raw_noise_targets","raw_speech_targets",
        "pre_ready_noise_targets","pre_ready_speech_targets",
        "ready_noise_targets","ready_speech_targets",
        "target_cases","cases_first_target_before_ready",
        "cases_never_ready","ordinary_reference_frames",
    ):
        acc[key]+=int(item[key])
    for key in (
        "pre_ready_noise_frame_index","pre_ready_speech_frame_index",
        "ready_noise_frame_index","ready_speech_frame_index",
        "pre_ready_noise_prior_count","pre_ready_speech_prior_count",
        "all_noise_prior_count","all_speech_prior_count",
        "first_reference_frame_index",
        "first_target_frame_index","first_ready_frame_index",
        "ready_minus_first_target_frames",
        "reference_frames_before_first_target",
        "median_reference_interarrival_frames",
        "max_reference_interarrival_frames",
    ):
        acc[key].extend(item[key])


def median(values: list[int | float]) -> float | None:
    return statistics.median(values) if values else None


def histogram(values: list[int]) -> dict[str,int]:
    c=Counter(values)
    return {str(key):int(c.get(key,0)) for key in range(REFERENCE_READY_COUNT)}


def summary(acc: dict[str, Any]) -> dict[str, Any]:
    raw_noise=int(acc["raw_noise_targets"])
    raw_speech=int(acc["raw_speech_targets"])
    pre_noise=int(acc["pre_ready_noise_targets"])
    pre_speech=int(acc["pre_ready_speech_targets"])
    ready_noise=int(acc["ready_noise_targets"])
    ready_speech=int(acc["ready_speech_targets"])
    target_cases=int(acc["target_cases"])
    return {
        "raw_noise_targets":raw_noise,
        "raw_speech_targets":raw_speech,
        "pre_ready_noise_targets":pre_noise,
        "pre_ready_speech_targets":pre_speech,
        "ready_noise_targets":ready_noise,
        "ready_speech_targets":ready_speech,
        "pre_ready_fraction":{
            "noise":pre_noise/raw_noise if raw_noise else None,
            "speech":pre_speech/raw_speech if raw_speech else None,
        },
        "ready_fraction":{
            "noise":ready_noise/raw_noise if raw_noise else None,
            "speech":ready_speech/raw_speech if raw_speech else None,
        },
        "ordinary_reference_frames":int(acc["ordinary_reference_frames"]),
        "target_cases":target_cases,
        "cases_first_target_before_ready":int(acc["cases_first_target_before_ready"]),
        "first_target_before_ready_case_fraction":
            acc["cases_first_target_before_ready"]/target_cases if target_cases else None,
        "cases_never_ready":int(acc["cases_never_ready"]),
        "pre_ready_prior_reference_count_histogram":{
            "noise":histogram([int(v) for v in acc["pre_ready_noise_prior_count"]]),
            "speech":histogram([int(v) for v in acc["pre_ready_speech_prior_count"]]),
        },
        "median_pre_ready_prior_reference_count":{
            "noise":median(acc["pre_ready_noise_prior_count"]),
            "speech":median(acc["pre_ready_speech_prior_count"]),
        },
        "median_prior_reference_count_at_target":{
            "noise":median(acc["all_noise_prior_count"]),
            "speech":median(acc["all_speech_prior_count"]),
        },
        "median_target_frame_index":{
            "pre_ready_noise":median(acc["pre_ready_noise_frame_index"]),
            "pre_ready_speech":median(acc["pre_ready_speech_frame_index"]),
            "ready_noise":median(acc["ready_noise_frame_index"]),
            "ready_speech":median(acc["ready_speech_frame_index"]),
        },
        "median_first_reference_frame_index":
            median(acc["first_reference_frame_index"]),
        "median_first_target_frame_index":median(acc["first_target_frame_index"]),
        "median_first_ready_frame_index":median(acc["first_ready_frame_index"]),
        "median_ready_minus_first_target_frames":
            median(acc["ready_minus_first_target_frames"]),
        "median_reference_frames_before_first_target":
            median(acc["reference_frames_before_first_target"]),
        "median_reference_interarrival_frames":
            median(acc["median_reference_interarrival_frames"]),
        "median_max_reference_interarrival_frames":
            median(acc["max_reference_interarrival_frames"]),
    }


def slice_keys(case: dict[str,Any]) -> list[str]:
    dimensions=case.get("dimensions",{})
    keys=[f"scenario:{case['scenario']}"]
    domain=dimensions.get("noise_domain")
    if domain is not None:
        keys.append(f"noise_domain:{domain}")
    if "snr_db" in dimensions:
        keys.append(f"snr_db:{float(dimensions['snr_db']):g}")
    if "reverb" in dimensions:
        keys.append(f"reverb:{str(bool(dimensions['reverb'])).lower()}")
    if dimensions.get("clean_only") is True:
        keys.append("clean_only:true")
    return keys


def analyze_case(
    probe: Path,
    corpus_path: Path,
    case: dict[str,Any],
    upstream_guard: float,
) -> dict[str,Any]:
    mic=engine.resolve(corpus_path,case.get("mic_audio"))
    labels_path=engine.resolve(corpus_path,case.get("vad_labels"))
    require(mic is not None and labels_path is not None,
            "case missing mic audio or VAD labels")

    with tempfile.TemporaryDirectory(prefix="ap-i028-") as tmp:
        _,raw=engine.stage_audio(mic,16000,1,Path(tmp),"mic.pcm")
        rows=run_probe(probe,raw)

    labels=[int(v) for v in engine.load_labels(labels_path)]
    count=min(len(rows),len(labels))
    require(count>WARMUP,"case too short")
    rows=rows[WARMUP:count]
    labels=labels[WARMUP:count]

    result=empty_accumulator()
    target_receipts: list[dict[str,Any]]=[]
    reference_frame_indexes: list[int]=[]
    prior_reference_count=0
    first_ready_frame: int | None=None
    first_target_frame: int | None=None
    refs_before_first_target: int | None=None
    max_ns_delta=0.0
    max_vad_delta=0.0
    active_mismatch=0

    for frame_index,(row,label) in enumerate(zip(rows,labels)):
        require(label in (0,1),"invalid label")
        upstream=float(row["upstream_probability"])
        gap=float(row["mirror_gap"])
        public=float(row["public_shipping_probability"])
        shipping=float(row["shipping_probability"])
        require(all(math.isfinite(v) for v in (
            upstream,gap,public,shipping,
            float(row["mirror_mean"]),float(row["mirror_concentration"]),
        )),"non-finite I028 metric")
        max_ns_delta=max(max_ns_delta,abs(upstream-gap))
        max_vad_delta=max(max_vad_delta,abs(public-shipping))
        active_mismatch+=int(
            int(row["public_shipping_active"]) != int(row["shipping_active"])
        )

        is_disagreement=disagreement(row,upstream_guard)
        if label==0 and not is_disagreement:
            prior_reference_count+=1
            reference_frame_indexes.append(frame_index)
            result["ordinary_reference_frames"]+=1
            if (
                first_ready_frame is None
                and prior_reference_count>=REFERENCE_READY_COUNT
            ):
                first_ready_frame=frame_index
            continue

        if not is_disagreement:
            continue

        if first_target_frame is None:
            first_target_frame=frame_index
            refs_before_first_target=prior_reference_count

        speech=label==1
        raw_key="raw_speech_targets" if speech else "raw_noise_targets"
        all_prior_key="all_speech_prior_count" if speech else "all_noise_prior_count"
        result[raw_key]+=1
        result[all_prior_key].append(prior_reference_count)
        target_receipts.append({
            "class":"speech" if speech else "noise",
            "frame_index_from_warmup":frame_index,
            "prior_reference_count":prior_reference_count,
            "ready_at_target":prior_reference_count>=REFERENCE_READY_COUNT,
        })
        if prior_reference_count<REFERENCE_READY_COUNT:
            count_key=(
                "pre_ready_speech_targets"
                if speech else "pre_ready_noise_targets"
            )
            frame_key=(
                "pre_ready_speech_frame_index"
                if speech else "pre_ready_noise_frame_index"
            )
            prior_key=(
                "pre_ready_speech_prior_count"
                if speech else "pre_ready_noise_prior_count"
            )
            result[count_key]+=1
            result[frame_key].append(frame_index)
            result[prior_key].append(prior_reference_count)
        else:
            count_key="ready_speech_targets" if speech else "ready_noise_targets"
            frame_key="ready_speech_frame_index" if speech else "ready_noise_frame_index"
            result[count_key]+=1
            result[frame_key].append(frame_index)

    raw_targets=result["raw_noise_targets"]+result["raw_speech_targets"]
    if raw_targets:
        result["target_cases"]=1
        require(first_target_frame is not None and refs_before_first_target is not None,
                "target-case temporal accounting missing")
        result["first_target_frame_index"].append(first_target_frame)
        result["reference_frames_before_first_target"].append(
            refs_before_first_target
        )
        if first_ready_frame is None:
            result["cases_never_ready"]=1
            result["cases_first_target_before_ready"]=1
        else:
            result["first_ready_frame_index"].append(first_ready_frame)
            result["ready_minus_first_target_frames"].append(
                first_ready_frame-first_target_frame
            )
            result["cases_first_target_before_ready"]+=int(
                first_target_frame<=first_ready_frame
            )

    reference_interarrivals=[
        b-a for a,b in zip(reference_frame_indexes,reference_frame_indexes[1:])
    ]
    if reference_frame_indexes:
        result["first_reference_frame_index"].append(reference_frame_indexes[0])
    if reference_interarrivals:
        result["median_reference_interarrival_frames"].append(
            statistics.median(reference_interarrivals)
        )
        result["max_reference_interarrival_frames"].append(
            max(reference_interarrivals)
        )

    for receipt in target_receipts:
        receipt["first_ready_frame_index"]=first_ready_frame
        if first_ready_frame is None:
            receipt["frames_until_ready"]=None
            receipt["frames_since_ready"]=None
        elif receipt["ready_at_target"]:
            receipt["frames_until_ready"]=0
            receipt["frames_since_ready"]=(
                receipt["frame_index_from_warmup"]-first_ready_frame
            )
        else:
            receipt["frames_until_ready"]=max(
                0,first_ready_frame-receipt["frame_index_from_warmup"]
            )
            receipt["frames_since_ready"]=None

    require(
        result["pre_ready_noise_targets"]+result["ready_noise_targets"]
        == result["raw_noise_targets"],
        "noise readiness accounting mismatch",
    )
    require(
        result["pre_ready_speech_targets"]+result["ready_speech_targets"]
        == result["raw_speech_targets"],
        "speech readiness accounting mismatch",
    )

    return {
        "case_id":str(case["case_id"]),
        "scenario":str(case["scenario"]),
        "dimensions":case.get("dimensions",{}),
        "readiness":result,
        "target_receipts":target_receipts,
        "reference_arrival":{
            "first_reference_frame_index":
                reference_frame_indexes[0] if reference_frame_indexes else None,
            "first_target_frame_index":first_target_frame,
            "first_ready_frame_index":first_ready_frame,
            "reference_frames_before_first_target":refs_before_first_target,
            "ordinary_reference_frames_total":len(reference_frame_indexes),
            "median_reference_interarrival_frames":
                statistics.median(reference_interarrivals)
                if reference_interarrivals else None,
            "max_reference_interarrival_frames":
                max(reference_interarrivals) if reference_interarrivals else None,
            "ready_minus_first_target_frames":
                (first_ready_frame-first_target_frame)
                if first_ready_frame is not None and first_target_frame is not None
                else None,
        },
        "mirror":{
            "max_ns_upstream_gap_delta":max_ns_delta,
            "max_vad_probability_delta":max_vad_delta,
            "vad_active_mismatch_frames":active_mismatch,
        },
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
        == "i028-ns-upstream-reference-readiness-temporal-decomposition-v1",
        "contract identity drift",
    )
    authority=contract["fresh_diagnostic_authority"]
    expected_seeds=[int(v) for v in authority["seeds"]]
    require(len(corpora)==len(expected_seeds),"corpus count mismatch")
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
        "I028 budget drift",
    )
    require(
        int(contract["readiness_boundary"]["prior_reference_frames"])
        == REFERENCE_READY_COUNT,
        "readiness boundary drift",
    )

    upstream_guard=float(
        contract["fixed_shipping_semantics"]["vad_upstream_speech_guard"]
    )
    expected_lock=contract["dataset_authority"]["dataset_lock_sha256"]
    actual_seeds=[]
    global_acc=empty_accumulator()
    slice_acc: dict[str,dict[str,Any]]={}
    per_case=[]
    max_ns_delta=0.0
    max_vad_delta=0.0
    active_mismatch=0
    target_receipt_count=0
    domain_case_counts={
        domain:{"mix":0,"noise":0} for domain in NOISE_DOMAINS
    }

    for corpus_path in corpora:
        corpus=load_json(corpus_path)
        require(corpus.get("tier")=="research-validation",
                "public development tier drift")
        require(corpus.get("dataset_lock_sha256")==expected_lock,
                "dataset lock binding drift")
        seed=int(corpus.get("generator",{}).get("seed",-1))
        actual_seeds.append(seed)
        cases=corpus.get("cases",[])
        require(len(cases)==int(authority["expected_cases_per_seed"]),
                f"unexpected case count for seed={seed}")

        for case in cases:
            item=analyze_case(probe,corpus_path,case,upstream_guard)
            target_receipt_count+=len(item["target_receipts"])
            per_case.append({
                "case_id":item["case_id"],
                "scenario":item["scenario"],
                "dimensions":item["dimensions"],
                "readiness":summary(item["readiness"]),
                "reference_arrival":item["reference_arrival"],
                "target_receipts":item["target_receipts"],
                "mirror":item["mirror"],
            })
            append_case(global_acc,item["readiness"])
            for key in slice_keys(case):
                slice_acc.setdefault(key,empty_accumulator())
                append_case(slice_acc[key],item["readiness"])
            max_ns_delta=max(
                max_ns_delta,
                float(item["mirror"]["max_ns_upstream_gap_delta"]),
            )
            max_vad_delta=max(
                max_vad_delta,
                float(item["mirror"]["max_vad_probability_delta"]),
            )
            active_mismatch+=int(
                item["mirror"]["vad_active_mismatch_frames"]
            )
            dimensions=case.get("dimensions",{})
            domain=dimensions.get("noise_domain")
            if domain in domain_case_counts:
                if str(case["scenario"]).startswith("research-public-noisy"):
                    domain_case_counts[domain]["mix"]+=1
                elif case["scenario"]=="research-public-noise-only":
                    domain_case_counts[domain]["noise"]+=1

    require(actual_seeds==expected_seeds,f"fresh seed mismatch: {actual_seeds}")
    global_summary=summary(global_acc)
    expected_target_receipts=(
        int(global_summary["raw_noise_targets"])
        + int(global_summary["raw_speech_targets"])
    )
    require(
        target_receipt_count==expected_target_receipts,
        "raw target receipt accounting mismatch",
    )
    slices={
        key:summary(acc) for key,acc in sorted(slice_acc.items())
        if acc["raw_noise_targets"] or acc["raw_speech_targets"]
    }

    invalid_reasons=[]
    gates=contract["diagnostic_gates"]
    if len(per_case)<int(gates["minimum_total_cases"]):
        invalid_reasons.append("case_count")
    for label,raw_key in (
        ("noise","raw_noise_targets"),
        ("speech","raw_speech_targets"),
    ):
        if int(global_summary[raw_key])<int(
            gates["minimum_global_raw_targets_per_class"]
        ):
            invalid_reasons.append("global_raw_target_count:"+label)

    if max_ns_delta>float(gates["max_ns_upstream_mirror_delta"]):
        invalid_reasons.append("ns_upstream_mirror")
    if max_vad_delta>float(gates["max_vad_shipping_mirror_probability_delta"]):
        invalid_reasons.append("vad_probability_mirror")
    if active_mismatch!=int(
        gates["vad_shipping_mirror_active_mismatch_frames"]
    ):
        invalid_reasons.append("vad_active_mirror")

    for domain in NOISE_DOMAINS:
        item=slices.get("noise_domain:"+domain)
        if item is None:
            invalid_reasons.append("domain_population:"+domain)
            continue
        for label,raw_key in (
            ("noise","raw_noise_targets"),
            ("speech","raw_speech_targets"),
        ):
            if int(item[raw_key])<int(gates["minimum_raw_targets_per_noise_domain"]):
                invalid_reasons.append(
                    "domain_raw_target_count:"+domain+":"+label
                )
        counts=domain_case_counts[domain]
        if counts["mix"] < int(
            authority["minimum_mix_cases_per_noise_domain_per_seed"]
        )*len(expected_seeds):
            invalid_reasons.append("domain_mix_coverage:"+domain)
        if counts["noise"] < int(
            authority["minimum_noise_only_cases_per_noise_domain_per_seed"]
        )*len(expected_seeds):
            invalid_reasons.append("domain_noise_coverage:"+domain)

    decision=(
        "I028_INPUT_INVALID_REVIEW_REQUIRED"
        if invalid_reasons else
        "NS_UPSTREAM_REFERENCE_READINESS_TEMPORAL_DECOMPOSED_REVIEW_REQUIRED"
    )
    result={
        "schema_version":1,
        "investigation_id":contract["investigation_id"],
        "authority":contract["authority"],
        "source_base_sha":contract["source_base_sha"],
        "dataset_id":contract["dataset_authority"]["dataset_id"],
        "fresh_diagnostic_seeds":actual_seeds,
        "diagnostic_execution_consumed":1,
        "candidate_budget_consumed":0,
        "confirmation_budget_consumed":0,
        "shipping_mirror":{
            "max_ns_upstream_gap_delta":max_ns_delta,
            "max_vad_probability_delta":max_vad_delta,
            "vad_active_mismatch_frames":active_mismatch,
        },
        "global":global_summary,
        "slices":slices,
        "per_case":per_case,
        "domain_case_counts":domain_case_counts,
        "target_accounting":{
            "raw_target_count":expected_target_receipts,
            "target_receipt_count":target_receipt_count,
            "all_raw_targets_represented_exactly_once":
                target_receipt_count==expected_target_receipts,
        },
        "decision":decision,
        "invalid_reasons":sorted(set(invalid_reasons)),
        "interpretation_boundary":{
            "readiness_threshold_fixed_at_prior_reference_frames":REFERENCE_READY_COUNT,
            "no_alternative_readiness_threshold_evaluated":True,
            "no_component_counterfactual":True,
            "no_component_mapping_selected":True,
            "no_threshold_search":True,
            "no_shipping_candidate":True,
            "oracle_labels_diagnostic_only":True,
            "temporal_observation_only":True,
            "future_readiness_timestamp_retrospective_diagnostic_only":True,
            "per_target_prior_reference_count_recorded":True,
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
    acc=empty_accumulator()
    case=empty_accumulator()
    case["raw_noise_targets"]=4
    case["raw_speech_targets"]=5
    case["pre_ready_noise_targets"]=1
    case["pre_ready_speech_targets"]=2
    case["ready_noise_targets"]=3
    case["ready_speech_targets"]=3
    case["target_cases"]=1
    case["cases_first_target_before_ready"]=1
    case["ordinary_reference_frames"]=12
    case["pre_ready_noise_frame_index"]=[10]
    case["pre_ready_speech_frame_index"]=[11,12]
    case["ready_noise_frame_index"]=[20,21,22]
    case["ready_speech_frame_index"]=[23,24,25]
    case["pre_ready_noise_prior_count"]=[5]
    case["pre_ready_speech_prior_count"]=[5,6]
    case["all_noise_prior_count"]=[5,8,9,10]
    case["all_speech_prior_count"]=[5,6,8,9,10]
    case["first_reference_frame_index"]=[1]
    case["first_target_frame_index"]=[10]
    case["first_ready_frame_index"]=[19]
    case["ready_minus_first_target_frames"]=[9]
    case["reference_frames_before_first_target"]=[5]
    case["median_reference_interarrival_frames"]=[2]
    case["max_reference_interarrival_frames"]=[5]
    append_case(acc,case)
    value=summary(acc)
    assert value["pre_ready_fraction"]["noise"]==0.25
    assert value["pre_ready_fraction"]["speech"]==0.4
    assert value["ready_fraction"]["speech"]==0.6
    assert value["pre_ready_prior_reference_count_histogram"]["speech"]["5"]==1
    assert value["pre_ready_prior_reference_count_histogram"]["speech"]["6"]==1
    assert value["median_ready_minus_first_target_frames"]==9
    assert value["median_prior_reference_count_at_target"]["speech"]==8
    assert value["median_reference_interarrival_frames"]==2
    print("I028 reference-readiness temporal decomposition self-test: OK")


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--probe",type=Path)
    parser.add_argument("--contract",type=Path)
    parser.add_argument("--corpus",action="append",type=Path,default=[])
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.probe or not args.contract or not args.output or not args.corpus:
        parser.error("--probe --contract --corpus --output are required")
    result=evaluate(args.probe,args.corpus,args.contract,args.output)
    print(json.dumps({
        "decision":result["decision"],
        "invalid_reasons":result["invalid_reasons"],
        "pre_ready_fraction":result["global"]["pre_ready_fraction"],
        "cases_first_target_before_ready":
            result["global"]["cases_first_target_before_ready"],
        "median_ready_minus_first_target_frames":
            result["global"]["median_ready_minus_first_target_frames"],
    },sort_keys=True))
    return 0 if result["decision"]!="I028_INPUT_INVALID_REVIEW_REQUIRED" else 2


if __name__=="__main__":
    raise SystemExit(main())
