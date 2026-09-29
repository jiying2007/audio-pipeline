#!/usr/bin/env python3
"""I029 candidate-zero feasibility diagnostic for independent donor NS references."""

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
NOISE_DOMAINS=("kitchen","traffic","living","office","cafeteria","bus","field")
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
    # Noise-domain equality is enforced before this score is called.
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


def sign_test_one_sided(wins: int,losses: int) -> float | None:
    n=wins+losses
    if n==0:
        return None
    return sum(math.comb(n,k) for k in range(wins,n+1))/(2**n)


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

    with tempfile.TemporaryDirectory(prefix="ap-i029-") as tmp:
        _,raw=engine.stage_audio(mic,16000,1,Path(tmp),"mic.pcm")
        rows=run_probe(probe,raw)

    labels=[int(v) for v in engine.load_labels(labels_path)]
    count=min(len(rows),len(labels))
    require(count>WARMUP,"case too short")
    rows=rows[WARMUP:count]
    labels=labels[WARMUP:count]

    refs=[]
    pre_ready_noise=0
    pre_ready_speech=0
    raw_noise=0
    raw_speech=0
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
        )),"non-finite I029 metric")
        max_ns_delta=max(max_ns_delta,abs(upstream-gap))
        max_vad_delta=max(max_vad_delta,abs(public-shipping))
        active_mismatch+=int(
            int(row["public_shipping_active"])!=int(row["shipping_active"])
        )

        is_disagreement=disagreement(row,upstream_guard)
        if label==0 and not is_disagreement:
            if len(refs)<REFERENCE_COUNT:
                refs.append({
                    "mean":mean,
                    "concentration":concentration,
                    "gap":gap,
                })
            continue

        if not is_disagreement:
            continue
        if label==0:
            raw_noise+=1
            if len(refs)<REFERENCE_COUNT:
                pre_ready_noise+=1
        else:
            raw_speech+=1
            if len(refs)<REFERENCE_COUNT:
                pre_ready_speech+=1

    first_ready=None
    if len(refs)==REFERENCE_COUNT:
        first_ready={
            "mean":statistics.median(x["mean"] for x in refs),
            "concentration":statistics.median(x["concentration"] for x in refs),
            "gap":statistics.median(x["gap"] for x in refs),
            "reference_frames":REFERENCE_COUNT,
        }

    return {
        "metadata":meta,
        "first_ready_reference":first_ready,
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


def aggregate_reference(records: list[dict[str,Any]]) -> dict[str,float]:
    require(bool(records),"cannot aggregate empty donor set")
    return {
        "mean":statistics.median(r["first_ready_reference"]["mean"] for r in records),
        "concentration":statistics.median(
            r["first_ready_reference"]["concentration"] for r in records
        ),
        "gap":statistics.median(r["first_ready_reference"]["gap"] for r in records),
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


def error_record(
    target_ref: dict[str,float],
    donor_ref: dict[str,float],
) -> dict[str,float]:
    return {
        key:abs(float(donor_ref[key])-float(target_ref[key]))
        for key in ("mean","concentration","gap")
    }


def paired_summary(records: list[dict[str,Any]]) -> dict[str,Any]:
    if not records:
        return {
            "paired_cases":0,
            "median_matched_abs_error":{},
            "median_negative_abs_error":{},
            "median_paired_improvement":{},
            "matched_better_fraction":{},
            "sign_test_one_sided_p":{},
        }
    result={
        "paired_cases":len(records),
        "median_matched_abs_error":{},
        "median_negative_abs_error":{},
        "median_paired_improvement":{},
        "matched_better_fraction":{},
        "sign_test_one_sided_p":{},
    }
    for metric in ("mean","concentration","gap"):
        matched=[r["matched_error"][metric] for r in records]
        negative=[r["negative_error"][metric] for r in records]
        improvements=[n-m for m,n in zip(matched,negative)]
        wins=sum(v>0 for v in improvements)
        losses=sum(v<0 for v in improvements)
        result["median_matched_abs_error"][metric]=statistics.median(matched)
        result["median_negative_abs_error"][metric]=statistics.median(negative)
        result["median_paired_improvement"][metric]=statistics.median(improvements)
        result["matched_better_fraction"][metric]=(
            wins/(wins+losses) if wins+losses else None
        )
        result["sign_test_one_sided_p"][metric]=sign_test_one_sided(wins,losses)
    return result


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
        =="i029-ns-upstream-independent-donor-reference-feasibility-v1",
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
        "I029 budget drift",
    )

    upstream_guard=float(
        contract["fixed_shipping_semantics"]["vad_upstream_speech_guard"]
    )
    expected_lock=contract["dataset_authority"]["dataset_lock_sha256"]
    expected_cases=int(authority["expected_cases_per_seed"])
    expected_domain_cases=int(authority["expected_noise_domain_cases_per_seed"])

    donor_records=[]
    target_records=[]
    actual_donor_seeds=[]
    actual_target_seeds=[]
    max_ns_delta=0.0
    max_vad_delta=0.0
    active_mismatch=0

    def process_corpus(path: Path, expected_seed: int, out: list[dict[str,Any]]) -> None:
        nonlocal max_ns_delta,max_vad_delta,active_mismatch
        corpus=load_json(path)
        require(corpus.get("tier")=="research-validation",
                "public development tier drift")
        require(corpus.get("dataset_lock_sha256")==expected_lock,
                "dataset lock binding drift")
        seed=int(corpus.get("generator",{}).get("seed",-1))
        require(seed==expected_seed,f"seed mismatch: {seed} != {expected_seed}")
        cases=corpus.get("cases",[])
        require(len(cases)==expected_cases,
                f"unexpected case count for seed={seed}")
        domain_cases=[c for c in cases if c.get("dimensions",{}).get("noise_domain")]
        require(len(domain_cases)==expected_domain_cases,
                f"unexpected domain case count for seed={seed}")
        for case in domain_cases:
            record=analyze_case(probe,path,case,upstream_guard,seed)
            out.append(record)
            max_ns_delta=max(
                max_ns_delta,float(record["mirror"]["max_ns_upstream_gap_delta"])
            )
            max_vad_delta=max(
                max_vad_delta,float(record["mirror"]["max_vad_probability_delta"])
            )
            active_mismatch+=int(
                record["mirror"]["vad_active_mismatch_frames"]
            )

    for path,seed in zip(donor_corpora,donor_seeds):
        process_corpus(path,seed,donor_records)
        actual_donor_seeds.append(seed)
    for path,seed in zip(target_corpora,target_seeds):
        process_corpus(path,seed,target_records)
        actual_target_seeds.append(seed)

    donor_ids={r["metadata"]["case_key"] for r in donor_records}
    target_ids={r["metadata"]["case_key"] for r in target_records}
    require(len(donor_ids)==len(donor_records),"duplicate donor case identity")
    require(len(target_ids)==len(target_records),"duplicate target case identity")
    require(donor_ids.isdisjoint(target_ids),"donor/target case identity overlap")

    donor_ready=[r for r in donor_records if r["first_ready_reference"] is not None]
    donor_by_domain={domain:[] for domain in NOISE_DOMAINS}
    for record in donor_ready:
        donor_by_domain[record["metadata"]["noise_domain"]].append(record)

    target_benchmark=[
        r for r in target_records if r["first_ready_reference"] is not None
    ]
    paired=[]
    receipts=[]
    domain_pairs={domain:[] for domain in NOISE_DOMAINS}
    matched_covered=0
    negative_covered=0

    for target in target_records:
        meta=target["metadata"]
        domain=meta["noise_domain"]
        matched=select_donors(meta,donor_by_domain,domain)
        negative_domain=NEGATIVE_DOMAIN[domain]
        negative=select_donors(meta,donor_by_domain,negative_domain)
        if len(matched)==DONOR_SELECT_K:
            matched_covered+=1
        if len(negative)==DONOR_SELECT_K:
            negative_covered+=1

        receipt={
            "target_case_key":meta["case_key"],
            "target_case_id":meta["case_id"],
            "target_seed":meta["seed"],
            "metadata":meta,
            "pre_ready_speech_targets":target["raw_targets"]["pre_ready_speech"],
            "pre_ready_noise_targets":target["raw_targets"]["pre_ready_noise"],
            "target_first_ready_reference_available":
                target["first_ready_reference"] is not None,
            "matched_domain":domain,
            "negative_control_domain":negative_domain,
            "matched_donor_case_keys":[r["metadata"]["case_key"] for r in matched],
            "negative_donor_case_keys":[r["metadata"]["case_key"] for r in negative],
        }

        if (
            target["first_ready_reference"] is not None
            and len(matched)==DONOR_SELECT_K
            and len(negative)==DONOR_SELECT_K
        ):
            matched_ref=aggregate_reference(matched)
            negative_ref=aggregate_reference(negative)
            benchmark=target["first_ready_reference"]
            pair={
                "target_case_key":meta["case_key"],
                "target_case_id":meta["case_id"],
                "target_seed":meta["seed"],
                "noise_domain":domain,
                "has_pre_ready_speech":
                    target["raw_targets"]["pre_ready_speech"]>0,
                "benchmark":benchmark,
                "matched_reference":matched_ref,
                "negative_reference":negative_ref,
                "matched_error":error_record(benchmark,matched_ref),
                "negative_error":error_record(benchmark,negative_ref),
            }
            paired.append(pair)
            domain_pairs[domain].append(pair)
            receipt["paired_error"]=pair
        receipts.append(receipt)

    gates=contract["diagnostic_gates"]
    invalid_reasons=[]
    total_targets=len(target_records)
    if total_targets!=int(gates["expected_target_cases"]):
        invalid_reasons.append("target_case_count")
    if len(donor_records)!=int(gates["expected_donor_cases"]):
        invalid_reasons.append("donor_case_count")
    if len(donor_ready)<int(gates["minimum_ready_donor_cases"]):
        invalid_reasons.append("ready_donor_count")

    benchmark_fraction=(
        len(target_benchmark)/total_targets if total_targets else 0.0
    )
    matched_coverage=matched_covered/total_targets if total_targets else 0.0
    negative_coverage=negative_covered/total_targets if total_targets else 0.0
    if benchmark_fraction<float(gates["minimum_target_benchmark_coverage"]):
        invalid_reasons.append("target_benchmark_coverage")
    if matched_coverage<float(gates["minimum_matched_donor_coverage"]):
        invalid_reasons.append("matched_donor_coverage")
    if negative_coverage<float(gates["minimum_negative_control_coverage"]):
        invalid_reasons.append("negative_control_coverage")

    for domain in NOISE_DOMAINS:
        donors=len(donor_by_domain[domain])
        if donors<int(gates["minimum_ready_donors_per_domain"]):
            invalid_reasons.append("ready_donor_domain:"+domain)
        domain_targets=sum(
            r["metadata"]["noise_domain"]==domain for r in target_records
        )
        domain_bench=sum(
            r["metadata"]["noise_domain"]==domain
            and r["first_ready_reference"] is not None
            for r in target_records
        )
        fraction=domain_bench/domain_targets if domain_targets else 0.0
        if fraction<float(gates["minimum_target_benchmark_coverage_per_domain"]):
            invalid_reasons.append("target_benchmark_domain:"+domain)

    if max_ns_delta>float(gates["max_ns_upstream_mirror_delta"]):
        invalid_reasons.append("ns_upstream_mirror")
    if max_vad_delta>float(gates["max_vad_shipping_mirror_probability_delta"]):
        invalid_reasons.append("vad_probability_mirror")
    if active_mismatch!=int(gates["vad_shipping_mirror_active_mismatch_frames"]):
        invalid_reasons.append("vad_active_mirror")

    paired_global=paired_summary(paired)
    domain_summary={
        domain:paired_summary(items)
        for domain,items in domain_pairs.items()
    }
    pre_ready_speech_pairs=[
        item for item in paired if item["has_pre_ready_speech"]
    ]

    pre_ready_speech_summary=paired_summary(pre_ready_speech_pairs)
    directional=contract["directional_hypothesis"]
    primary=directional["primary_metric"]
    p=pre_ready_speech_summary["sign_test_one_sided_p"].get(primary)
    improvement=pre_ready_speech_summary["median_paired_improvement"].get(primary)
    better=pre_ready_speech_summary["matched_better_fraction"].get(primary)
    if len(pre_ready_speech_pairs)<int(
        gates["minimum_primary_pre_ready_speech_paired_cases"]
    ):
        invalid_reasons.append("primary_pre_ready_speech_paired_cases")
    cafeteria_pairs=domain_pairs["cafeteria"]
    if len(cafeteria_pairs)<int(gates["minimum_cafeteria_paired_cases"]):
        invalid_reasons.append("cafeteria_paired_cases")
    supported=(
        not invalid_reasons
        and p is not None
        and p<=float(directional["maximum_one_sided_sign_test_p"])
        and improvement is not None and improvement>0
        and better is not None and better>0.5
    )

    decision=(
        "I029_INPUT_INVALID_REVIEW_REQUIRED"
        if invalid_reasons else
        "NS_UPSTREAM_INDEPENDENT_DONOR_REFERENCE_FEASIBILITY_DECOMPOSED_REVIEW_REQUIRED"
    )
    result={
        "schema_version":1,
        "investigation_id":contract["investigation_id"],
        "authority":contract["authority"],
        "source_base_sha":contract["source_base_sha"],
        "dataset_id":contract["dataset_authority"]["dataset_id"],
        "fresh_diagnostic_authority":{
            "donor_seeds":actual_donor_seeds,
            "target_seeds":actual_target_seeds,
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
            "target_benchmark_cases":len(target_benchmark),
            "target_benchmark_coverage":benchmark_fraction,
            "matched_donor_coverage":matched_coverage,
            "negative_control_coverage":negative_coverage,
            "ready_donors_per_domain":{
                domain:len(donor_by_domain[domain])
                for domain in NOISE_DOMAINS
            },
        },
        "paired_global":paired_global,
        "paired_pre_ready_speech_cases":pre_ready_speech_summary,
        "paired_by_noise_domain":domain_summary,
        "directional_hypothesis":{
            "primary_population":"target cases with at least one pre-ready speech target",
            "primary_metric":primary,
            "paired_cases":len(pre_ready_speech_pairs),
            "supported":supported,
            "maximum_one_sided_sign_test_p":
                directional["maximum_one_sided_sign_test_p"],
        },
        "receipts":receipts,
        "decision":decision,
        "invalid_reasons":sorted(set(invalid_reasons)),
        "interpretation_boundary":{
            "donor_and_target_cases_disjoint":True,
            "donor_selection_metadata_only":True,
            "matching_metadata_development_only_not_shippable":True,
            "target_first_ready_reference_retrospective_benchmark_only":True,
            "same_target_future_frames_never_enter_donor_reference":True,
            "readiness_threshold_fixed_at_prior_reference_frames":REFERENCE_COUNT,
            "no_component_counterfactual":True,
            "no_component_mapping_selected":True,
            "no_threshold_search":True,
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
    target={
        "seed":999,
        "case_id":"target",
        "case_key":"999:target",
        "scenario":"research-public-noisy-clean",
        "noise_domain":"cafeteria",
        "reverb":False,
        "snr_db":5.0,
    }
    donors=[
        {"metadata":{
            "seed":1,"case_id":"a","case_key":"1:a","scenario":"research-public-noisy-clean",
            "noise_domain":"cafeteria","reverb":False,"snr_db":5.0,
        }},
        {"metadata":{
            "seed":2,"case_id":"b","case_key":"2:b","scenario":"research-public-noisy-clean",
            "noise_domain":"cafeteria","reverb":False,"snr_db":10.0,
        }},
        {"metadata":{
            "seed":3,"case_id":"c","case_key":"3:c","scenario":"research-public-noise-only",
            "noise_domain":"cafeteria","reverb":None,"snr_db":None,
        }},
    ]
    ranked=sorted(donors,key=lambda r:compatibility_score(target,r["metadata"]))
    assert [r["metadata"]["case_id"] for r in ranked]==["a","b","c"]
    assert NEGATIVE_DOMAIN["cafeteria"]=="bus"
    p=sign_test_one_sided(9,1)
    assert p is not None and p<0.02
    records=[
        {
            "matched_error":{"mean":0.1,"concentration":0.1,"gap":0.1},
            "negative_error":{"mean":0.2,"concentration":0.3,"gap":0.4},
        },
        {
            "matched_error":{"mean":0.2,"concentration":0.2,"gap":0.2},
            "negative_error":{"mean":0.3,"concentration":0.1,"gap":0.3},
        },
    ]
    summary=paired_summary(records)
    assert summary["median_paired_improvement"]["gap"]>0
    assert summary["matched_better_fraction"]["gap"]==1.0
    print("I029 independent donor reference feasibility self-test: OK")


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
        "primary_directional_hypothesis":
            result["directional_hypothesis"],
        "paired_global":result["paired_global"],
    },sort_keys=True))
    return 0 if result["decision"]!="I029_INPUT_INVALID_REVIEW_REQUIRED" else 2


if __name__=="__main__":
    raise SystemExit(main())
