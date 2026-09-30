#!/usr/bin/env python3
"""I035 candidate-zero NS noise-tracker update-regime decomposition."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import sys
import tempfile
from typing import Any

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tests"/"validation"))
import i033_ns_vad_causal_noise_delta_alignment as base  # type: ignore

HORIZONS=(1,2,4,8)
NOISE_DOMAINS=base.NOISE_DOMAINS
REGIME_FIELDS=(
    "slow_update_bin_fraction",
    "fast_update_bin_fraction",
    "slow_update_abs_contribution_fraction",
    "fast_update_abs_contribution_fraction",
    "slow_signed_update_fraction_of_previous_noise",
    "fast_signed_update_fraction_of_previous_noise",
    "total_abs_update_fraction_of_previous_noise",
    "slow_mean_post_ratio",
    "fast_mean_post_ratio",
    "mean_post_ratio",
    "max_post_ratio",
)


def require(condition: bool,message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_json(path: Path) -> dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value,dict),f"JSON object required: {path}")
    return value


def finite(value: Any) -> float:
    x=float(value)
    require(math.isfinite(x),"non-finite regime metric")
    return x


def regime_frame(row: dict[str,Any],local_index: int) -> dict[str,Any]:
    item={
        "local_frame_index":local_index,
        "absolute_frame_index":int(row["frame"]),
        "ns_noise_rms_dbfs":finite(row["ns_noise_rms_dbfs"]),
        "post_ns_rms_dbfs":finite(row["post_ns_rms_dbfs"]),
        "mirror_gap":finite(row["mirror_gap"]),
    }
    for field in REGIME_FIELDS:
        item[field]=finite(row[field])
    slow=item["slow_update_bin_fraction"]
    fast=item["fast_update_bin_fraction"]
    require(abs((slow+fast)-1.0)<=2.0e-5,
            "slow/fast bin accounting drift")
    abs_total=item["total_abs_update_fraction_of_previous_noise"]
    abs_split=(
        item["slow_update_abs_contribution_fraction"]
        +item["fast_update_abs_contribution_fraction"]
    )
    require(
        abs_total<=1.0e-15 or abs(abs_split-1.0)<=2.0e-5,
        "slow/fast absolute contribution accounting drift",
    )
    return item


def analyze_case(
    probe: Path,
    corpus_path: Path,
    case: dict[str,Any],
    upstream_guard: float,
    seed: int,
) -> dict[str,Any]:
    meta=base.metadata(case,seed)
    mic=base.engine.resolve(corpus_path,case.get("mic_audio"))
    labels_path=base.engine.resolve(corpus_path,case.get("vad_labels"))
    require(mic is not None and labels_path is not None,
            "case missing mic audio or VAD labels")

    with tempfile.TemporaryDirectory(prefix="ap-i035-") as tmp:
        _,raw=base.engine.stage_audio(mic,16000,1,Path(tmp),"mic.pcm")
        rows=base.run_probe(probe,raw)

    labels=[int(v) for v in base.engine.load_labels(labels_path)]
    count=min(len(rows),len(labels))
    require(count>base.WARMUP,"case too short")
    rows=rows[base.WARMUP:count]
    labels=labels[base.WARMUP:count]

    prior_references=[]
    first_pre_ready_target=None
    anchor=None
    later_references=[]
    max_ns_delta=0.0
    max_vad_delta=0.0
    active_mismatch=0

    for local_index,(row,label) in enumerate(zip(rows,labels)):
        require(label in (0,1),"invalid label")
        upstream=finite(row["upstream_probability"])
        gap=finite(row["mirror_gap"])
        public=finite(row["public_shipping_probability"])
        shipping=finite(row["shipping_probability"])

        max_ns_delta=max(max_ns_delta,abs(upstream-gap))
        max_vad_delta=max(max_vad_delta,abs(public-shipping))
        active_mismatch+=int(
            int(row["public_shipping_active"])!=int(row["shipping_active"])
        )

        frame=regime_frame(row,local_index)
        is_disagreement=base.disagreement(row,upstream_guard)
        is_reference=(label==0 and not is_disagreement)

        if (
            first_pre_ready_target is None
            and label==1
            and is_disagreement
            and len(prior_references)<base.REFERENCE_COUNT
        ):
            first_pre_ready_target=dict(frame)
            first_pre_ready_target["prior_reference_count"]=len(prior_references)
            if prior_references:
                anchor=prior_references[-1]
            continue

        if is_reference:
            if first_pre_ready_target is None:
                if len(prior_references)<base.REFERENCE_COUNT:
                    prior_references.append(frame)
            elif (
                local_index>first_pre_ready_target["local_frame_index"]
                and len(later_references)<base.REFERENCE_COUNT
            ):
                later_references.append(frame)

    return {
        "metadata":meta,
        "first_pre_ready_target":first_pre_ready_target,
        "causal_anchor":anchor,
        "later_reference_frames":later_references,
        "mirror":{
            "max_ns_upstream_gap_delta":max_ns_delta,
            "max_vad_probability_delta":max_vad_delta,
            "vad_active_mismatch_frames":active_mismatch,
        },
    }


def percentile_nearest_rank(values: list[float],q: float) -> float | None:
    if not values:
        return None
    ordered=sorted(values)
    rank=max(1,math.ceil(q*len(ordered)))
    return ordered[rank-1]


def rank_average(values: list[float]) -> list[float]:
    order=sorted(range(len(values)),key=lambda i: values[i])
    ranks=[0.0]*len(values)
    i=0
    while i<len(order):
        j=i+1
        while j<len(order) and values[order[j]]==values[order[i]]:
            j+=1
        rank=((i+1)+j)/2.0
        for k in range(i,j):
            ranks[order[k]]=rank
        i=j
    return ranks


def pearson(xs: list[float],ys: list[float]) -> float | None:
    if len(xs)!=len(ys) or len(xs)<2:
        return None
    mx=statistics.mean(xs)
    my=statistics.mean(ys)
    dx=[x-mx for x in xs]
    dy=[y-my for y in ys]
    denom=math.sqrt(sum(x*x for x in dx)*sum(y*y for y in dy))
    if denom<=1.0e-20:
        return None
    return sum(x*y for x,y in zip(dx,dy))/denom


def spearman(xs: list[float],ys: list[float]) -> float | None:
    if len(xs)!=len(ys) or len(xs)<2:
        return None
    return pearson(rank_average(xs),rank_average(ys))


def median_fields(rows: list[dict[str,Any]],fields: tuple[str,...]) -> dict[str,Any]:
    if not rows:
        return {"cases":0}
    out={"cases":len(rows)}
    for field in fields:
        out["median_"+field]=statistics.median(
            finite(row[field]) for row in rows
        )
    return out


def cumulative_horizon_row(
    target: dict[str,Any],
    anchor: dict[str,Any],
    later: list[dict[str,Any]],
    horizon: int,
    meta: dict[str,Any],
) -> dict[str,Any]:
    require(horizon in HORIZONS,"unregistered horizon")
    require(len(later)>=horizon,"horizon unavailable")
    prefix=later[:horizon]
    row={
        "target_case_key":meta["case_key"],
        "metadata":meta,
        "horizon_reference_count":horizon,
        "elapsed_frames_from_target":
            int(prefix[-1]["local_frame_index"])
            -int(target["local_frame_index"]),
    }
    for field in REGIME_FIELDS:
        row[field]=statistics.median(
            finite(frame[field]) for frame in prefix
        )
    ns_value=statistics.median(
        finite(frame["ns_noise_rms_dbfs"]) for frame in prefix
    )
    local_value=statistics.median(
        finite(frame["post_ns_rms_dbfs"]) for frame in prefix
    )
    ns_delta=ns_value-finite(anchor["ns_noise_rms_dbfs"])
    local_delta=local_value-finite(anchor["post_ns_rms_dbfs"])
    row.update({
        "ns_response_delta_db":ns_delta,
        "local_response_delta_db":local_delta,
        "response_deficit_db":abs(local_delta)-abs(ns_delta),
        "alignment_abs_error_db":abs(ns_delta-local_delta),
    })
    return row


def quartile_review(rows: list[dict[str,Any]],field: str) -> dict[str,Any]:
    if not rows:
        return {}
    ordered=sorted(rows,key=lambda row: finite(row[field]))
    groups=[[] for _ in range(4)]
    for index,row in enumerate(ordered):
        q=min(3,(index*4)//len(ordered))
        groups[q].append(row)
    result={}
    for index,group in enumerate(groups,1):
        result[f"q{index}"]={
            "cases":len(group),
            "median_"+field:statistics.median(
                finite(row[field]) for row in group
            ) if group else None,
            "median_response_deficit_db":statistics.median(
                finite(row["response_deficit_db"]) for row in group
            ) if group else None,
            "median_alignment_abs_error_db":statistics.median(
                finite(row["alignment_abs_error_db"]) for row in group
            ) if group else None,
        }
    return result


def horizon_review(rows: list[dict[str,Any]]) -> dict[str,Any]:
    if not rows:
        return {"cases":0}
    slow=[finite(r["slow_update_bin_fraction"]) for r in rows]
    fast_abs=[
        finite(r["fast_update_abs_contribution_fraction"]) for r in rows
    ]
    total_abs=[
        finite(r["total_abs_update_fraction_of_previous_noise"]) for r in rows
    ]
    deficit=[finite(r["response_deficit_db"]) for r in rows]
    alignment=[finite(r["alignment_abs_error_db"]) for r in rows]
    summary=median_fields(rows,REGIME_FIELDS)
    summary.update({
        "median_response_deficit_db":statistics.median(deficit),
        "p90_response_deficit_db":percentile_nearest_rank(deficit,0.90),
        "median_alignment_abs_error_db":statistics.median(alignment),
        "spearman_slow_update_bin_fraction_vs_response_deficit":
            spearman(slow,deficit),
        "spearman_fast_update_abs_contribution_fraction_vs_response_deficit":
            spearman(fast_abs,deficit),
        "spearman_total_abs_update_fraction_vs_response_deficit":
            spearman(total_abs,deficit),
        "slow_exposure_quartiles":
            quartile_review(rows,"slow_update_bin_fraction"),
        "fast_abs_contribution_quartiles":
            quartile_review(rows,"fast_update_abs_contribution_fraction"),
    })
    return summary


def evaluate(
    probe: Path,
    corpora: list[Path],
    contract_path: Path,
    output: Path,
) -> dict[str,Any]:
    contract=load_json(contract_path)
    require(
        contract["investigation_id"]
        =="i035-ns-noise-tracker-update-regime-decomposition-v1",
        "contract identity drift",
    )
    authority=contract["fresh_diagnostic_authority"]
    seeds=[int(v) for v in authority["target_seeds"]]
    require(len(corpora)==len(seeds),"target corpus count mismatch")
    require(len(set(seeds))==len(seeds),"duplicate target seeds")
    require(authority["diagnostic_execution_limit"]==1,
            "execution budget drift")
    require(authority["candidate_limit"]==0,"candidate budget drift")
    require(authority["confirmation_limit"]==0,
            "confirmation budget drift")

    mechanism=contract["fixed_tracker_mechanism"]
    require(mechanism["slow_update_speech_probability_threshold"]==0.35,
            "tracker branch threshold drift")
    require(mechanism["slow_alpha"]==0.995,"slow alpha drift")
    require(mechanism["fast_alpha"]==0.92,"fast alpha drift")
    require(mechanism["parameters_are_observed_not_changed"] is True,
            "tracker parameter authority drift")

    horizons=tuple(int(v) for v in contract["fixed_horizons"])
    require(horizons==HORIZONS,"fixed horizon grid drift")
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
        require(
            int(corpus.get("generator",{}).get("seed",-1))==seed,
            "seed mismatch",
        )
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
                max_ns_delta,finite(item["mirror"]["max_ns_upstream_gap_delta"])
            )
            max_vad_delta=max(
                max_vad_delta,finite(item["mirror"]["max_vad_probability_delta"])
            )
            active_mismatch+=int(item["mirror"]["vad_active_mismatch_frames"])

    identities={r["metadata"]["case_key"] for r in records}
    require(len(identities)==len(records),"duplicate target identity")
    causal=[r for r in records if r["first_pre_ready_target"] is not None]
    anchored=[r for r in causal if r["causal_anchor"] is not None]

    target_rows=[]
    rows_by_horizon={h:[] for h in HORIZONS}
    receipts=[]
    for record in records:
        target=record["first_pre_ready_target"]
        anchor=record["causal_anchor"]
        later=list(record["later_reference_frames"])
        receipt={
            "target_case_key":record["metadata"]["case_key"],
            "metadata":record["metadata"],
            "causal_target":target,
            "causal_anchor":anchor,
            "later_reference_count":len(later),
            "horizons":{},
        }
        if target is not None and anchor is not None:
            target_row={
                "target_case_key":record["metadata"]["case_key"],
                "metadata":record["metadata"],
            }
            for field in REGIME_FIELDS:
                target_row[field]=finite(target[field])
            target_rows.append(target_row)
            for horizon in HORIZONS:
                if len(later)<horizon:
                    continue
                row=cumulative_horizon_row(
                    target,anchor,later,horizon,record["metadata"]
                )
                rows_by_horizon[horizon].append(row)
                receipt["horizons"][str(horizon)]=row
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
    if anchor_coverage<float(gates["minimum_causal_anchor_coverage"]):
        invalid_reasons.append("causal_anchor_coverage")

    horizon_coverage={}
    for horizon in HORIZONS:
        coverage=(
            len(rows_by_horizon[horizon])/len(anchored)
            if anchored else 0.0
        )
        horizon_coverage[str(horizon)]=coverage
        if coverage<float(gates["minimum_fixed_horizon_coverage"]):
            invalid_reasons.append(f"horizon_{horizon}_coverage")

    if max_ns_delta>float(gates["max_ns_upstream_mirror_delta"]):
        invalid_reasons.append("ns_upstream_mirror")
    if max_vad_delta>float(
        gates["max_vad_shipping_mirror_probability_delta"]
    ):
        invalid_reasons.append("vad_probability_mirror")
    if active_mismatch!=int(
        gates["vad_shipping_mirror_active_mismatch_frames"]
    ):
        invalid_reasons.append("vad_active_mirror")

    global_review={
        str(h):horizon_review(rows_by_horizon[h])
        for h in HORIZONS
    }
    by_domain={
        domain:{
            str(h):horizon_review([
                row for row in rows_by_horizon[h]
                if row["metadata"]["noise_domain"]==domain
            ])
            for h in HORIZONS
        }
        for domain in NOISE_DOMAINS
    }

    decision=(
        "I035_INPUT_INVALID_REVIEW_REQUIRED"
        if invalid_reasons else
        "NS_NOISE_TRACKER_UPDATE_REGIME_DECOMPOSED_REVIEW_REQUIRED"
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
            "causal_anchor_coverage":anchor_coverage,
            "fixed_horizon_coverage":horizon_coverage,
        },
        "update_regime":{
            "target":median_fields(target_rows,REGIME_FIELDS),
            "global_fixed_horizons":global_review,
            "by_noise_domain":by_domain,
            "interpretation_authority":
                "diagnostic-only mechanism decomposition; correlations and "
                "quartiles cannot select alpha, tracker threshold, lag, mapping "
                "or source candidate",
        },
        "receipts":receipts,
        "decision":decision,
        "invalid_reasons":sorted(set(invalid_reasons)),
        "interpretation_boundary":{
            "target_only_no_donor_selection":True,
            "same_i034_causal_target_anchor_semantics":True,
            "fixed_reference_horizons_1_2_4_8_only":True,
            "shipping_tracker_function_reused_in_mirror":True,
            "tracker_threshold_0_35_observed_not_changed":True,
            "slow_alpha_0_995_observed_not_changed":True,
            "fast_alpha_0_92_observed_not_changed":True,
            "slow_fast_contribution_accounting_mirror_only":True,
            "correlations_and_quartiles_descriptive_only":True,
            "shipping_ns_vad_source_unchanged":True,
            "no_tracker_alpha_search":True,
            "no_tracker_threshold_search":True,
            "no_best_horizon_or_lag_selection":True,
            "no_normalization_mapping":True,
            "no_vad_noise_state_refresh_rule":True,
            "no_threshold_tuning":True,
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
    assert HORIZONS==(1,2,4,8)
    assert len(REGIME_FIELDS)==11
    assert rank_average([1.0,1.0,3.0])==[1.5,1.5,3.0]
    assert round(spearman([1,2,3],[3,2,1]) or 0.0,6)==-1.0
    rows=[
        {
            "slow_update_bin_fraction":0.1,
            "response_deficit_db":1.0,
            "alignment_abs_error_db":2.0,
        },
        {
            "slow_update_bin_fraction":0.9,
            "response_deficit_db":3.0,
            "alignment_abs_error_db":4.0,
        },
    ]
    q=quartile_review(rows,"slow_update_bin_fraction")
    assert sum(v["cases"] for v in q.values())==2
    print("I035 update-regime decomposition self-test: OK")


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
    if (
        not args.probe or not args.contract
        or not args.output or not args.target_corpus
    ):
        parser.error(
            "--probe --contract --target-corpus --output are required"
        )
    result=evaluate(args.probe,args.target_corpus,args.contract,args.output)
    print(json.dumps({
        "decision":result["decision"],
        "invalid_reasons":result["invalid_reasons"],
        "coverage":result["coverage"],
        "target_regime":result["update_regime"]["target"],
        "fixed_horizons":result["update_regime"]["global_fixed_horizons"],
    },sort_keys=True))
    return 0 if result["decision"]!="I035_INPUT_INVALID_REVIEW_REQUIRED" else 2


if __name__=="__main__":
    raise SystemExit(main())
