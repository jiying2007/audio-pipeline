#!/usr/bin/env python3
"""I036 candidate-zero NS noise-estimate aggregation-domain decomposition."""

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
FRAME_FIELDS=(
    "all_noise_rms_dbfs",
    "low_mean_noise_dbfs",
    "speech_mean_noise_dbfs",
    "high_mean_noise_dbfs",
    "low_noise_energy_share",
    "speech_noise_energy_share",
    "high_noise_energy_share",
    "low_update_abs_contribution_fraction",
    "speech_update_abs_contribution_fraction",
    "high_update_abs_contribution_fraction",
    "low_signed_update_fraction_of_previous_noise",
    "speech_signed_update_fraction_of_previous_noise",
    "high_signed_update_fraction_of_previous_noise",
    "all_abs_update_fraction_of_previous_noise",
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
    require(math.isfinite(x),"non-finite aggregation metric")
    return x


def aggregation_frame(row: dict[str,Any],local_index: int) -> dict[str,Any]:
    item={
        "local_frame_index":local_index,
        "absolute_frame_index":int(row["frame"]),
        "ns_noise_rms_dbfs":finite(row["ns_noise_rms_dbfs"]),
        "post_ns_rms_dbfs":finite(row["post_ns_rms_dbfs"]),
        "mirror_gap":finite(row["mirror_gap"]),
        "noise_rms_reconstruction_gap":
            finite(row["noise_rms_reconstruction_gap"]),
    }
    for field in FRAME_FIELDS:
        item[field]=finite(row[field])

    require(int(row["low_bins"])==9,"low partition bin-count drift")
    require(int(row["speech_bins"])==215,"speech partition bin-count drift")
    require(int(row["high_bins"])==33,"high partition bin-count drift")

    share_sum=(
        item["low_noise_energy_share"]
        +item["speech_noise_energy_share"]
        +item["high_noise_energy_share"]
    )
    require(abs(share_sum-1.0)<=2.0e-5,
            "partition estimate-energy share accounting drift")

    update_sum=(
        item["low_update_abs_contribution_fraction"]
        +item["speech_update_abs_contribution_fraction"]
        +item["high_update_abs_contribution_fraction"]
    )
    if item["all_abs_update_fraction_of_previous_noise"]>1.0e-15:
        require(abs(update_sum-1.0)<=2.0e-5,
                "partition update contribution accounting drift")
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

    with tempfile.TemporaryDirectory(prefix="ap-i036-") as tmp:
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
    max_reconstruction_gap=0.0

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

        frame=aggregation_frame(row,local_index)
        max_reconstruction_gap=max(
            max_reconstruction_gap,
            abs(frame["noise_rms_reconstruction_gap"]),
        )
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
            "max_noise_rms_reconstruction_gap":max_reconstruction_gap,
        },
    }


def percentile_nearest_rank(values: list[float],q: float) -> float | None:
    if not values:
        return None
    ordered=sorted(values)
    rank=max(1,math.ceil(q*len(ordered)))
    return ordered[rank-1]


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
    for field in FRAME_FIELDS:
        row[field]=statistics.median(
            finite(frame[field]) for frame in prefix
        )

    local=statistics.median(
        finite(frame["post_ns_rms_dbfs"]) for frame in prefix
    )-finite(anchor["post_ns_rms_dbfs"])
    all_delta=(
        row["all_noise_rms_dbfs"]
        -finite(anchor["all_noise_rms_dbfs"])
    )
    low_delta=(
        row["low_mean_noise_dbfs"]
        -finite(anchor["low_mean_noise_dbfs"])
    )
    speech_delta=(
        row["speech_mean_noise_dbfs"]
        -finite(anchor["speech_mean_noise_dbfs"])
    )
    high_delta=(
        row["high_mean_noise_dbfs"]
        -finite(anchor["high_mean_noise_dbfs"])
    )
    all_alignment=abs(all_delta-local)
    speech_alignment=abs(speech_delta-local)
    all_deficit=abs(local)-abs(all_delta)
    speech_deficit=abs(local)-abs(speech_delta)
    row.update({
        "local_response_delta_db":local,
        "all_response_delta_db":all_delta,
        "low_response_delta_db":low_delta,
        "speech_response_delta_db":speech_delta,
        "high_response_delta_db":high_delta,
        "all_response_deficit_db":all_deficit,
        "speech_response_deficit_db":speech_deficit,
        "all_alignment_abs_error_db":all_alignment,
        "speech_alignment_abs_error_db":speech_alignment,
        "speech_vs_all_alignment_improvement_db":
            all_alignment-speech_alignment,
        "speech_vs_all_deficit_improvement_db":
            all_deficit-speech_deficit,
        "speech_minus_all_response_magnitude_db":
            abs(speech_delta)-abs(all_delta),
    })
    return row


def horizon_review(rows: list[dict[str,Any]]) -> dict[str,Any]:
    if not rows:
        return {"cases":0}
    out=median_fields(rows,(
        "low_noise_energy_share",
        "speech_noise_energy_share",
        "high_noise_energy_share",
        "low_update_abs_contribution_fraction",
        "speech_update_abs_contribution_fraction",
        "high_update_abs_contribution_fraction",
        "all_abs_update_fraction_of_previous_noise",
        "local_response_delta_db",
        "all_response_delta_db",
        "low_response_delta_db",
        "speech_response_delta_db",
        "high_response_delta_db",
        "all_response_deficit_db",
        "speech_response_deficit_db",
        "all_alignment_abs_error_db",
        "speech_alignment_abs_error_db",
        "speech_vs_all_alignment_improvement_db",
        "speech_vs_all_deficit_improvement_db",
        "speech_minus_all_response_magnitude_db",
        "elapsed_frames_from_target",
    ))
    all_errors=[finite(r["all_alignment_abs_error_db"]) for r in rows]
    speech_errors=[finite(r["speech_alignment_abs_error_db"]) for r in rows]
    improvements=[
        finite(r["speech_vs_all_alignment_improvement_db"]) for r in rows
    ]
    out.update({
        "p90_all_alignment_abs_error_db":
            percentile_nearest_rank(all_errors,0.90),
        "p90_speech_alignment_abs_error_db":
            percentile_nearest_rank(speech_errors,0.90),
        "speech_alignment_better_fraction":
            sum(1 for v in improvements if v>0.0)/len(improvements),
        "speech_alignment_worse_fraction":
            sum(1 for v in improvements if v<0.0)/len(improvements),
    })
    return out


def evaluate(
    probe: Path,
    corpora: list[Path],
    contract_path: Path,
    output: Path,
) -> dict[str,Any]:
    contract=load_json(contract_path)
    require(
        contract["investigation_id"]
        =="i036-ns-noise-estimate-aggregation-domain-decomposition-v1",
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

    partitions=contract["fixed_spectral_partitions"]
    require(partitions["nfft"]==512,"nfft drift")
    require(partitions["low_bins"]=={"first":0,"last":8,"count":9},
            "low partition drift")
    require(partitions["speech_bins"]=={"first":9,"last":223,"count":215},
            "speech partition drift")
    require(partitions["high_bins"]=={"first":224,"last":256,"count":33},
            "high partition drift")
    require(partitions["boundaries_are_fixed_not_searched"] is True,
            "spectral band search was enabled")

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
    max_reconstruction_gap=0.0
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
            max_reconstruction_gap=max(
                max_reconstruction_gap,
                finite(item["mirror"]["max_noise_rms_reconstruction_gap"]),
            )

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
            target_rows.append({
                "target_case_key":record["metadata"]["case_key"],
                "metadata":record["metadata"],
                **{field:finite(target[field]) for field in FRAME_FIELDS},
            })
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
    if max_reconstruction_gap>float(
        gates["max_noise_rms_reconstruction_gap_db"]
    ):
        invalid_reasons.append("noise_rms_reconstruction")

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
        "I036_INPUT_INVALID_REVIEW_REQUIRED"
        if invalid_reasons else
        "NS_NOISE_ESTIMATE_AGGREGATION_DOMAIN_DECOMPOSED_REVIEW_REQUIRED"
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
            "max_noise_rms_reconstruction_gap_db":max_reconstruction_gap,
        },
        "coverage":{
            "target_cases":len(records),
            "causal_target_cases":len(causal),
            "causal_anchor_cases":len(anchored),
            "causal_anchor_coverage":anchor_coverage,
            "fixed_horizon_coverage":horizon_coverage,
        },
        "aggregation_domain":{
            "target":median_fields(target_rows,(
                "low_noise_energy_share",
                "speech_noise_energy_share",
                "high_noise_energy_share",
                "low_update_abs_contribution_fraction",
                "speech_update_abs_contribution_fraction",
                "high_update_abs_contribution_fraction",
                "all_abs_update_fraction_of_previous_noise",
            )),
            "global_fixed_horizons":global_review,
            "by_noise_domain":by_domain,
            "interpretation_authority":
                "diagnostic-only fixed spectral aggregation decomposition; "
                "no band, normalization, estimator, alpha, threshold, horizon, "
                "lag, mapping or source candidate may be selected",
        },
        "receipts":receipts,
        "decision":decision,
        "invalid_reasons":sorted(set(invalid_reasons)),
        "interpretation_boundary":{
            "target_only_no_donor_selection":True,
            "same_i035_causal_target_anchor_semantics":True,
            "fixed_reference_horizons_1_2_4_8_only":True,
            "fixed_low_speech_high_partitions_only":True,
            "shipping_tracker_function_reused_in_mirror":True,
            "all_bin_noise_rms_reconstructed_from_mirror":True,
            "partition_estimate_and_update_accounting_mirror_only":True,
            "shipping_ns_vad_source_unchanged":True,
            "no_spectral_band_search":True,
            "no_estimator_selection":True,
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
    rows=[
        {
            "all_alignment_abs_error_db":5.0,
            "speech_alignment_abs_error_db":2.0,
            "speech_vs_all_alignment_improvement_db":3.0,
            "low_noise_energy_share":0.1,
            "speech_noise_energy_share":0.8,
            "high_noise_energy_share":0.1,
            "low_update_abs_contribution_fraction":0.1,
            "speech_update_abs_contribution_fraction":0.8,
            "high_update_abs_contribution_fraction":0.1,
            "all_abs_update_fraction_of_previous_noise":0.05,
            "local_response_delta_db":6.0,
            "all_response_delta_db":1.0,
            "low_response_delta_db":0.5,
            "speech_response_delta_db":4.0,
            "high_response_delta_db":0.2,
            "all_response_deficit_db":5.0,
            "speech_response_deficit_db":2.0,
            "speech_vs_all_deficit_improvement_db":3.0,
            "speech_minus_all_response_magnitude_db":3.0,
            "elapsed_frames_from_target":8.0,
        }
    ]
    summary=horizon_review(rows)
    assert summary["speech_alignment_better_fraction"]==1.0
    assert summary["median_speech_vs_all_alignment_improvement_db"]==3.0
    print("I036 aggregation-domain decomposition self-test: OK")


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
        "shipping_mirror":result["shipping_mirror"],
        "target_aggregation":result["aggregation_domain"]["target"],
        "fixed_horizons":result["aggregation_domain"]["global_fixed_horizons"],
    },sort_keys=True))
    return 0 if result["decision"]!="I036_INPUT_INVALID_REVIEW_REQUIRED" else 2


if __name__=="__main__":
    raise SystemExit(main())
