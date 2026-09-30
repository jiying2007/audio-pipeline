#!/usr/bin/env python3
"""I032 candidate-zero target-side causal NS noise-scale observability diagnostic."""

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


def percentile_nearest_rank(values: list[float],q: float) -> float | None:
    if not values:
        return None
    require(0.0<q<=1.0,"nearest-rank percentile q out of range")
    ordered=sorted(values)
    rank=max(1,math.ceil(q*len(ordered)))
    return ordered[rank-1]


def rankdata(values: list[float]) -> list[float]:
    indexed=sorted(enumerate(values),key=lambda item:(item[1],item[0]))
    ranks=[0.0]*len(values)
    i=0
    while i<len(indexed):
        j=i+1
        while j<len(indexed) and indexed[j][1]==indexed[i][1]:
            j+=1
        average=((i+1)+j)/2.0
        for k in range(i,j):
            ranks[indexed[k][0]]=average
        i=j
    return ranks


def pearson(xs: list[float],ys: list[float]) -> float | None:
    require(len(xs)==len(ys),"pearson length mismatch")
    if len(xs)<2:
        return None
    mx=statistics.mean(xs)
    my=statistics.mean(ys)
    dx=[x-mx for x in xs]
    dy=[y-my for y in ys]
    denom=math.sqrt(sum(v*v for v in dx)*sum(v*v for v in dy))
    if denom<=1.0e-18:
        return None
    return sum(a*b for a,b in zip(dx,dy))/denom


def spearman(xs: list[float],ys: list[float]) -> float | None:
    if len(xs)<2:
        return None
    return pearson(rankdata(xs),rankdata(ys))


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


def summarize_reference_frames(frames: list[dict[str,float]]) -> dict[str,float] | None:
    if len(frames)!=REFERENCE_COUNT:
        return None
    return {
        key:statistics.median(float(frame[key]) for frame in frames)
        for key in ("mean","concentration","gap","ns_noise_rms_dbfs")
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

    with tempfile.TemporaryDirectory(prefix="ap-i032-") as tmp:
        _,raw=engine.stage_audio(mic,16000,1,Path(tmp),"mic.pcm")
        rows=run_probe(probe,raw)

    labels=[int(v) for v in engine.load_labels(labels_path)]
    count=min(len(rows),len(labels))
    require(count>WARMUP,"case too short")
    rows=rows[WARMUP:count]
    labels=labels[WARMUP:count]

    initial_refs=[]
    first_pre_ready_target=None
    later_refs=[]
    max_ns_delta=0.0
    max_vad_delta=0.0
    active_mismatch=0

    for local_index,(row,label) in enumerate(zip(rows,labels)):
        require(label in (0,1),"invalid label")
        upstream=float(row["upstream_probability"])
        gap=float(row["mirror_gap"])
        mean=float(row["mirror_mean"])
        concentration=float(row["mirror_concentration"])
        noise_db=float(row["ns_noise_rms_dbfs"])
        public=float(row["public_shipping_probability"])
        shipping=float(row["shipping_probability"])
        require(all(math.isfinite(v) for v in (
            upstream,gap,mean,concentration,noise_db,public,shipping
        )),"non-finite I032 metric")

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
            and len(initial_refs)<REFERENCE_COUNT
        ):
            first_pre_ready_target={
                "local_frame_index":local_index,
                "absolute_frame_index":int(row["frame"]),
                "prior_reference_count":len(initial_refs),
                "ns_noise_rms_dbfs":noise_db,
                "mirror_gap":gap,
                "mirror_mean":mean,
                "mirror_concentration":concentration,
            }
            continue

        if is_reference:
            frame={
                "local_frame_index":local_index,
                "absolute_frame_index":int(row["frame"]),
                "mean":mean,
                "concentration":concentration,
                "gap":gap,
                "ns_noise_rms_dbfs":noise_db,
            }
            if len(initial_refs)<REFERENCE_COUNT:
                initial_refs.append(frame)
            if (
                first_pre_ready_target is not None
                and local_index>first_pre_ready_target["local_frame_index"]
                and len(later_refs)<REFERENCE_COUNT
            ):
                later_refs.append(frame)

    return {
        "metadata":meta,
        "initial_reference_summary":summarize_reference_frames(initial_refs),
        "first_pre_ready_target":first_pre_ready_target,
        "later_reference_frames":later_refs,
        "later_reference_summary":summarize_reference_frames(later_refs),
        "mirror":{
            "max_ns_upstream_gap_delta":max_ns_delta,
            "max_vad_probability_delta":max_vad_delta,
            "vad_active_mismatch_frames":active_mismatch,
        },
    }


def frozen_donor_control(records: list[dict[str,Any]]) -> dict[str,float]:
    require(len(records)==DONOR_SELECT_K,"I032 donor control requires K records")
    return {
        key:statistics.median(
            float(record["initial_reference_summary"][key])
            for record in records
        )
        for key in ("mean","concentration","gap")
    }


def frozen_donor_noise_scale(records: list[dict[str,Any]]) -> float:
    require(len(records)==DONOR_SELECT_K,"I032 donor noise-scale requires K records")
    return statistics.median(
        float(record["initial_reference_summary"]["ns_noise_rms_dbfs"])
        for record in records
    )


def fidelity_summary(records: list[dict[str,Any]]) -> dict[str,Any]:
    if not records:
        return {"cases":0}
    errors=[float(r["causal_proxy_abs_error_db"]) for r in records]
    signed=[float(r["causal_proxy_signed_error_db"]) for r in records]
    return {
        "cases":len(records),
        "median_absolute_error_db":statistics.median(errors),
        "p90_absolute_error_db":percentile_nearest_rank(errors,0.90),
        "max_absolute_error_db":max(errors),
        "median_signed_error_db":statistics.median(signed),
    }


def quartile_summary(records: list[dict[str,Any]]) -> dict[str,Any]:
    if not records:
        return {}
    ordered=sorted(
        records,
        key=lambda r:(
            float(r["donor_vs_causal_noise_scale_mismatch_db"]),
            r["target_case_key"],
        ),
    )
    n=len(ordered)
    groups={}
    for q in range(4):
        lo=(q*n)//4
        hi=((q+1)*n)//4
        chunk=ordered[lo:hi]
        groups[f"q{q+1}"]={
            "cases":len(chunk),
            "median_noise_scale_mismatch_db":
                statistics.median(
                    float(r["donor_vs_causal_noise_scale_mismatch_db"])
                    for r in chunk
                ) if chunk else None,
            "median_frozen_donor_gap_transfer_error":
                statistics.median(
                    float(r["frozen_donor_gap_transfer_error"])
                    for r in chunk
                ) if chunk else None,
        }
    return groups


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
        =="i032-ns-upstream-target-causal-noise-scale-observability-v1",
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
        r for r in donor_records if r["initial_reference_summary"] is not None
    ]
    donor_by_domain={domain:[] for domain in NOISE_DOMAINS}
    for record in donor_ready:
        donor_by_domain[record["metadata"]["noise_domain"]].append(record)

    causal_targets=[
        r for r in target_records if r["first_pre_ready_target"] is not None
    ]
    benchmarkable=[
        r for r in causal_targets if r["later_reference_summary"] is not None
    ]
    paired=[]
    receipts=[]
    matched_covered=0

    for target in target_records:
        meta=target["metadata"]
        matched=select_donors(
            meta,donor_by_domain,meta["noise_domain"]
        )
        if len(matched)==DONOR_SELECT_K:
            matched_covered+=1

        receipt={
            "target_case_key":meta["case_key"],
            "metadata":meta,
            "causal_target":target["first_pre_ready_target"],
            "later_reference_count":len(target["later_reference_frames"]),
            "later_reference_summary":target["later_reference_summary"],
            "matched_donor_case_keys":[
                r["metadata"]["case_key"] for r in matched
            ],
        }

        if (
            target["first_pre_ready_target"] is not None
            and target["later_reference_summary"] is not None
            and len(matched)==DONOR_SELECT_K
        ):
            causal=target["first_pre_ready_target"]
            later=target["later_reference_summary"]
            donor=frozen_donor_control(matched)
            proxy=float(causal["ns_noise_rms_dbfs"])
            benchmark=float(later["ns_noise_rms_dbfs"])
            donor_noise=frozen_donor_noise_scale(matched)
            row={
                "target_case_key":meta["case_key"],
                "metadata":meta,
                "causal_frame_index":causal["absolute_frame_index"],
                "causal_prior_reference_count":causal["prior_reference_count"],
                "causal_ns_noise_rms_dbfs":proxy,
                "later_noise_scale_benchmark_dbfs":benchmark,
                "causal_proxy_signed_error_db":proxy-benchmark,
                "causal_proxy_abs_error_db":abs(proxy-benchmark),
                "frozen_donor_noise_scale_dbfs":donor_noise,
                "donor_vs_causal_noise_scale_mismatch_db":
                    abs(donor_noise-proxy),
                "later_gap_benchmark":float(later["gap"]),
                "frozen_donor_gap":float(donor["gap"]),
                "frozen_donor_gap_transfer_error":
                    abs(float(donor["gap"])-float(later["gap"])),
            }
            paired.append(row)
            receipt["paired"]=row
        receipts.append(receipt)

    gates=contract["diagnostic_gates"]
    invalid_reasons=[]
    if len(donor_records)!=int(gates["expected_donor_cases"]):
        invalid_reasons.append("donor_case_count")
    if len(target_records)!=int(gates["expected_target_cases"]):
        invalid_reasons.append("target_case_count")
    if len(donor_ready)<int(gates["minimum_ready_donor_cases"]):
        invalid_reasons.append("ready_donor_count")

    causal_count=len(causal_targets)
    benchmark_count=len(benchmarkable)
    benchmark_coverage=(
        benchmark_count/causal_count if causal_count else 0.0
    )
    if causal_count<int(gates["minimum_causal_target_cases"]):
        invalid_reasons.append("causal_target_cases")
    if benchmark_coverage<float(gates["minimum_causal_benchmark_coverage"]):
        invalid_reasons.append("causal_benchmark_coverage")
    if matched_covered/len(target_records)<float(
        gates["minimum_matched_donor_coverage"]
    ):
        invalid_reasons.append("matched_donor_coverage")

    per_domain={}
    for domain in NOISE_DOMAINS:
        donors=len(donor_by_domain[domain])
        causal=[
            r for r in causal_targets
            if r["metadata"]["noise_domain"]==domain
        ]
        benches=sum(r["later_reference_summary"] is not None for r in causal)
        per_domain[domain]={
            "ready_donors":donors,
            "causal_target_cases":len(causal),
            "benchmarkable_causal_cases":benches,
            "causal_benchmark_coverage":
                benches/len(causal) if causal else None,
        }
        if donors<int(gates["minimum_ready_donors_per_domain"]):
            invalid_reasons.append("ready_donor_domain:"+domain)

    if max_ns_delta>float(gates["max_ns_upstream_mirror_delta"]):
        invalid_reasons.append("ns_upstream_mirror")
    if max_vad_delta>float(gates["max_vad_shipping_mirror_probability_delta"]):
        invalid_reasons.append("vad_probability_mirror")
    if active_mismatch!=int(gates["vad_shipping_mirror_active_mismatch_frames"]):
        invalid_reasons.append("vad_active_mirror")

    fidelity=fidelity_summary(paired)
    bounds=contract["fidelity_hypothesis"]
    supported=(
        not invalid_reasons
        and fidelity.get("median_absolute_error_db") is not None
        and fidelity["median_absolute_error_db"]
            <=float(bounds["maximum_median_absolute_error_db"])
        and fidelity["p90_absolute_error_db"]
            <=float(bounds["maximum_p90_absolute_error_db"])
    )

    mismatch=[
        float(r["donor_vs_causal_noise_scale_mismatch_db"]) for r in paired
    ]
    gap_error=[
        float(r["frozen_donor_gap_transfer_error"]) for r in paired
    ]

    decision=(
        "I032_INPUT_INVALID_REVIEW_REQUIRED"
        if invalid_reasons else
        "NS_UPSTREAM_TARGET_CAUSAL_NOISE_SCALE_OBSERVABILITY_DECOMPOSED_REVIEW_REQUIRED"
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
            "target_cases":len(target_records),
            "causal_target_cases":causal_count,
            "benchmarkable_causal_cases":benchmark_count,
            "causal_benchmark_coverage":benchmark_coverage,
            "matched_donor_coverage":
                matched_covered/len(target_records),
            "per_domain":per_domain,
        },
        "fidelity":{
            "global":fidelity,
            "by_noise_domain":{
                domain:fidelity_summary([
                    r for r in paired
                    if r["metadata"]["noise_domain"]==domain
                ])
                for domain in NOISE_DOMAINS
            },
        },
        "fidelity_hypothesis":{
            "supported":supported,
            "maximum_median_absolute_error_db":
                bounds["maximum_median_absolute_error_db"],
            "maximum_p90_absolute_error_db":
                bounds["maximum_p90_absolute_error_db"],
        },
        "descriptive_donor_transfer_association":{
            "spearman_noise_scale_mismatch_vs_gap_transfer_error":
                spearman(mismatch,gap_error),
            "mismatch_quartiles":quartile_summary(paired),
            "use_for_mapping_or_candidate_selection":False,
        },
        "receipts":receipts,
        "decision":decision,
        "invalid_reasons":sorted(set(invalid_reasons)),
        "interpretation_boundary":{
            "causal_proxy_is_shipping_ns_noise_rms_dbfs":True,
            "proxy_captured_at_first_pre_ready_speech_target_frame":True,
            "later_benchmark_uses_only_post_target_reference_frames":True,
            "later_benchmark_is_retrospective_only":True,
            "i029_i030_donor_selection_frozen":True,
            "frozen_independent_component_median_donor_control":True,
            "no_joint_aggregation_operator_evaluated":True,
            "no_noise_scale_normalization_mapping":True,
            "donor_selection_metadata_only":True,
            "matching_metadata_development_only_not_shippable":True,
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
    assert percentile_nearest_rank([1,2,3,4,5,6,7,8,9,10],0.9)==9
    rho=spearman([1,2,3,4],[10,20,30,40])
    assert rho is not None and abs(rho-1.0)<1e-12
    target={
        "seed":99,"case_id":"t","case_key":"99:t",
        "scenario":"research-public-noisy-clean",
        "noise_domain":"cafeteria","reverb":False,"snr_db":5.0,
    }
    donors=[
        {"metadata":{
            "seed":1,"case_id":"a","case_key":"1:a",
            "scenario":"research-public-noisy-clean",
            "noise_domain":"cafeteria","reverb":False,"snr_db":5.0,
        }},
        {"metadata":{
            "seed":2,"case_id":"b","case_key":"2:b",
            "scenario":"research-public-noisy-clean",
            "noise_domain":"cafeteria","reverb":False,"snr_db":10.0,
        }},
        {"metadata":{
            "seed":3,"case_id":"c","case_key":"3:c",
            "scenario":"research-public-noise-only",
            "noise_domain":"cafeteria","reverb":None,"snr_db":None,
        }},
    ]
    ranked=sorted(donors,key=lambda r:compatibility_score(target,r["metadata"]))
    assert [r["metadata"]["case_id"] for r in ranked]==["a","b","c"]
    assert NEGATIVE_DOMAIN["cafeteria"]=="bus"
    print("I032 target causal noise-scale observability self-test: OK")


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
        "fidelity":result["fidelity"]["global"],
        "fidelity_hypothesis":result["fidelity_hypothesis"],
        "descriptive_donor_transfer_association":
            result["descriptive_donor_transfer_association"],
    },sort_keys=True))
    return 0 if result["decision"]!="I032_INPUT_INVALID_REVIEW_REQUIRED" else 2


if __name__=="__main__":
    raise SystemExit(main())
