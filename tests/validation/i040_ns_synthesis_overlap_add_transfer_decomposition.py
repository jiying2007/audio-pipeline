#!/usr/bin/env python3
"""I040 candidate-zero NS synthesis/overlap-add transfer decomposition."""

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
DOMAINS=("all","low","speech","high")
TRACKER_FIELDS={
    "all":"all_noise_rms_dbfs",
    "low":"low_mean_noise_dbfs",
    "speech":"speech_mean_noise_dbfs",
    "high":"high_mean_noise_dbfs",
}
PRE_NS_FIELDS={
    "all":"pre_ns_all_mean_power_dbfs",
    "low":"pre_ns_low_mean_power_dbfs",
    "speech":"pre_ns_speech_mean_power_dbfs",
    "high":"pre_ns_high_mean_power_dbfs",
}
PREDICTED_FIELDS={
    "all":"predicted_suppressed_all_mean_power_dbfs",
    "low":"predicted_suppressed_low_mean_power_dbfs",
    "speech":"predicted_suppressed_speech_mean_power_dbfs",
    "high":"predicted_suppressed_high_mean_power_dbfs",
}
POST_NS_FIELDS={
    "all":"post_ns_all_mean_power_dbfs",
    "low":"post_ns_low_mean_power_dbfs",
    "speech":"post_ns_speech_mean_power_dbfs",
    "high":"post_ns_high_mean_power_dbfs",
}
PREDICTED_POST_FIELDS={
    "all":"predicted_post_ns_all_mean_power_dbfs",
    "low":"predicted_post_ns_low_mean_power_dbfs",
    "speech":"predicted_post_ns_speech_mean_power_dbfs",
    "high":"predicted_post_ns_high_mean_power_dbfs",
}
ATTENUATION_FIELDS={
    d:f"suppression_{d}_attenuation_db" for d in DOMAINS
}
MEAN_GAIN_FIELDS={
    d:f"suppression_{d}_mean_gain" for d in DOMAINS
}
FLOOR_FIELDS={
    d:f"suppression_{d}_floor_fraction" for d in DOMAINS
}
BASE_FRAME_FIELDS=(
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
    "all_abs_update_fraction_of_previous_noise",
    "post_ns_all_mean_power_dbfs",
    "post_ns_low_mean_power_dbfs",
    "post_ns_speech_mean_power_dbfs",
    "post_ns_high_mean_power_dbfs",
    "post_ns_low_energy_share",
    "post_ns_speech_energy_share",
    "post_ns_high_energy_share",
    "predicted_post_ns_all_mean_power_dbfs",
    "predicted_post_ns_low_mean_power_dbfs",
    "predicted_post_ns_speech_mean_power_dbfs",
    "predicted_post_ns_high_mean_power_dbfs",
    "predicted_post_ns_low_energy_share",
    "predicted_post_ns_speech_energy_share",
    "predicted_post_ns_high_energy_share",
    "synthesis_max_abs_sample_delta",
    "synthesis_output_rmse",
)
TRANSFER_FRAME_FIELDS=tuple(
    field
    for domain in DOMAINS
    for field in (
        PRE_NS_FIELDS[domain],
        PREDICTED_FIELDS[domain],
        ATTENUATION_FIELDS[domain],
        MEAN_GAIN_FIELDS[domain],
        FLOOR_FIELDS[domain],
    )
)
FRAME_FIELDS=BASE_FRAME_FIELDS+TRANSFER_FRAME_FIELDS


def require(condition: bool,message: str) -> None:
    if not condition:
        raise ValueError(message)


def load_json(path: Path) -> dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value,dict),f"JSON object required: {path}")
    return value


def finite(value: Any) -> float:
    x=float(value)
    require(math.isfinite(x),"non-finite suppression-transfer metric")
    return x


def transfer_frame(row: dict[str,Any],local_index: int) -> dict[str,Any]:
    item={
        "local_frame_index":local_index,
        "absolute_frame_index":int(row["frame"]),
        "ns_noise_rms_dbfs":finite(row["ns_noise_rms_dbfs"]),
        "post_ns_rms_dbfs":finite(row["post_ns_rms_dbfs"]),
        "mirror_gap":finite(row["mirror_gap"]),
        "noise_rms_reconstruction_gap":
            finite(row["noise_rms_reconstruction_gap"]),
        "all_noise_rms_bits":int(row["all_noise_rms_bits"]),
        "ns_noise_rms_bits":int(row["ns_noise_rms_bits"]),
        "noise_rms_bitwise_match":int(row["noise_rms_bitwise_match"]),
    }
    for field in FRAME_FIELDS:
        item[field]=finite(row[field])

    require(item["noise_rms_bitwise_match"] in (0,1),
            "invalid bitwise-match marker")
    require(
        (item["all_noise_rms_bits"]==item["ns_noise_rms_bits"])
        ==bool(item["noise_rms_bitwise_match"]),
        "noise-rms bitwise marker drift",
    )
    for prefix in ("","post_ns_"):
        require(int(row[prefix+"low_bins"])==9,
                f"{prefix}low partition bin-count drift")
        require(int(row[prefix+"speech_bins"])==215,
                f"{prefix}speech partition bin-count drift")
        require(int(row[prefix+"high_bins"])==33,
                f"{prefix}high partition bin-count drift")
    require(int(row["suppression_all_bins"])==257,
            "suppression all-bin count drift")
    require(int(row["suppression_low_bins"])==9,
            "suppression low-bin count drift")
    require(int(row["suppression_speech_bins"])==215,
            "suppression speech-bin count drift")
    require(int(row["suppression_high_bins"])==33,
            "suppression high-bin count drift")
    require(int(row["predicted_post_ns_low_bins"])==9,
            "predicted post-NS low-bin count drift")
    require(int(row["predicted_post_ns_speech_bins"])==215,
            "predicted post-NS speech-bin count drift")
    require(int(row["predicted_post_ns_high_bins"])==33,
            "predicted post-NS high-bin count drift")

    tracker_share_sum=(
        item["low_noise_energy_share"]
        +item["speech_noise_energy_share"]
        +item["high_noise_energy_share"]
    )
    require(abs(tracker_share_sum-1.0)<=2.0e-5,
            "tracker partition estimate-energy accounting drift")
    update_sum=(
        item["low_update_abs_contribution_fraction"]
        +item["speech_update_abs_contribution_fraction"]
        +item["high_update_abs_contribution_fraction"]
    )
    if item["all_abs_update_fraction_of_previous_noise"]>1.0e-15:
        require(abs(update_sum-1.0)<=2.0e-5,
                "tracker partition update accounting drift")
    post_share_sum=(
        item["post_ns_low_energy_share"]
        +item["post_ns_speech_energy_share"]
        +item["post_ns_high_energy_share"]
    )
    item["post_ns_partition_share_gap"]=abs(post_share_sum-1.0)
    predicted_post_share_sum=(
        item["predicted_post_ns_low_energy_share"]
        +item["predicted_post_ns_speech_energy_share"]
        +item["predicted_post_ns_high_energy_share"]
    )
    item["predicted_post_ns_partition_share_gap"]=abs(
        predicted_post_share_sum-1.0
    )
    require(item["synthesis_max_abs_sample_delta"]>=0.0,
            "negative synthesis sample delta")
    require(item["synthesis_output_rmse"]>=0.0,
            "negative synthesis output rmse")

    attenuation_gaps=[]
    power_excess=[]
    for domain in DOMAINS:
        pre=item[PRE_NS_FIELDS[domain]]
        predicted=item[PREDICTED_FIELDS[domain]]
        attenuation=item[ATTENUATION_FIELDS[domain]]
        gain=item[MEAN_GAIN_FIELDS[domain]]
        floor_fraction=item[FLOOR_FIELDS[domain]]
        attenuation_gaps.append(abs((predicted-pre)-attenuation))
        power_excess.append(max(0.0,predicted-pre))
        require(0.0<=gain<=1.0+1.0e-6,
                f"{domain} mean suppression gain outside [0,1]")
        require(0.0<=floor_fraction<=1.0,
                f"{domain} floor fraction outside [0,1]")
    item["max_suppression_attenuation_identity_gap_db"]=max(attenuation_gaps)
    item["max_predicted_suppressed_power_excess_db"]=max(power_excess)
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
    with tempfile.TemporaryDirectory(prefix="ap-i039-") as tmp:
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
    noise_rms_bitwise_mismatch_frames=0
    max_post_ns_partition_share_gap=0.0
    max_predicted_post_ns_partition_share_gap=0.0
    max_suppression_attenuation_identity_gap=0.0
    max_predicted_suppressed_power_excess=0.0
    max_synthesis_abs_sample_delta=0.0
    max_synthesis_output_rmse=0.0

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

        frame=transfer_frame(row,local_index)
        max_reconstruction_gap=max(
            max_reconstruction_gap,
            abs(frame["noise_rms_reconstruction_gap"]),
        )
        noise_rms_bitwise_mismatch_frames+=int(
            frame["noise_rms_bitwise_match"]!=1
        )
        max_post_ns_partition_share_gap=max(
            max_post_ns_partition_share_gap,
            finite(frame["post_ns_partition_share_gap"]),
        )
        max_predicted_post_ns_partition_share_gap=max(
            max_predicted_post_ns_partition_share_gap,
            finite(frame["predicted_post_ns_partition_share_gap"]),
        )
        max_synthesis_abs_sample_delta=max(
            max_synthesis_abs_sample_delta,
            finite(frame["synthesis_max_abs_sample_delta"]),
        )
        max_synthesis_output_rmse=max(
            max_synthesis_output_rmse,
            finite(frame["synthesis_output_rmse"]),
        )
        max_suppression_attenuation_identity_gap=max(
            max_suppression_attenuation_identity_gap,
            finite(frame["max_suppression_attenuation_identity_gap_db"]),
        )
        max_predicted_suppressed_power_excess=max(
            max_predicted_suppressed_power_excess,
            finite(frame["max_predicted_suppressed_power_excess_db"]),
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
            "noise_rms_bitwise_mismatch_frames":
                noise_rms_bitwise_mismatch_frames,
        },
        "transfer_invariants":{
            "max_post_ns_partition_share_gap":
                max_post_ns_partition_share_gap,
            "max_predicted_post_ns_partition_share_gap":
                max_predicted_post_ns_partition_share_gap,
            "max_suppression_attenuation_identity_gap_db":
                max_suppression_attenuation_identity_gap,
            "max_predicted_suppressed_power_excess_db":
                max_predicted_suppressed_power_excess,
            "max_synthesis_abs_sample_delta":
                max_synthesis_abs_sample_delta,
            "max_synthesis_output_rmse":
                max_synthesis_output_rmse,
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

    for domain in DOMAINS:
        pre_field=PRE_NS_FIELDS[domain]
        tracker_field=TRACKER_FIELDS[domain]
        predicted_field=PREDICTED_FIELDS[domain]
        synthesized_field=PREDICTED_POST_FIELDS[domain]
        post_field=POST_NS_FIELDS[domain]
        attenuation_field=ATTENUATION_FIELDS[domain]
        pre_delta=finite(row[pre_field])-finite(anchor[pre_field])
        tracker_delta=finite(row[tracker_field])-finite(anchor[tracker_field])
        predicted_delta=(
            finite(row[predicted_field])-finite(anchor[predicted_field])
        )
        synthesized_delta=(
            finite(row[synthesized_field])-finite(anchor[synthesized_field])
        )
        post_delta=finite(row[post_field])-finite(anchor[post_field])
        attenuation_delta=(
            finite(row[attenuation_field])-finite(anchor[attenuation_field])
        )
        row[f"{domain}_pre_ns_response_delta_db"]=pre_delta
        row[f"{domain}_tracker_response_delta_db"]=tracker_delta
        row[f"{domain}_predicted_suppressed_response_delta_db"]=predicted_delta
        row[f"{domain}_predicted_synthesized_response_delta_db"]=synthesized_delta
        row[f"{domain}_post_ns_response_delta_db"]=post_delta
        row[f"{domain}_suppression_attenuation_response_delta_db"]=(
            attenuation_delta
        )
        row[f"{domain}_tracker_vs_pre_alignment_abs_error_db"]=abs(
            tracker_delta-pre_delta
        )
        row[f"{domain}_predicted_vs_post_alignment_abs_error_db"]=abs(
            predicted_delta-post_delta
        )
        row[f"{domain}_synthesized_vs_post_alignment_abs_error_db"]=abs(
            synthesized_delta-post_delta
        )
        row[f"{domain}_synthesis_alignment_improvement_db"]=(
            abs(predicted_delta-post_delta)-abs(synthesized_delta-post_delta)
        )
        row[f"{domain}_tracker_vs_post_alignment_abs_error_db"]=abs(
            tracker_delta-post_delta
        )
        row[f"{domain}_tracker_response_deficit_vs_pre_db"]=(
            abs(pre_delta)-abs(tracker_delta)
        )
        row[f"{domain}_predicted_response_deficit_vs_post_db"]=(
            abs(post_delta)-abs(predicted_delta)
        )
        row[f"{domain}_pre_to_predicted_response_transfer_db"]=(
            predicted_delta-pre_delta
        )
        row[f"{domain}_predicted_to_post_response_residual_db"]=(
            post_delta-predicted_delta
        )
        row[f"{domain}_suppressed_to_synthesized_response_transfer_db"]=(
            synthesized_delta-predicted_delta
        )
        row[f"{domain}_synthesized_to_post_response_residual_db"]=(
            post_delta-synthesized_delta
        )
        row[f"{domain}_tracker_to_pre_magnitude_ratio"]=(
            abs(tracker_delta)/(abs(pre_delta)+1.0e-9)
        )
        row[f"{domain}_predicted_to_post_magnitude_ratio"]=(
            abs(predicted_delta)/(abs(post_delta)+1.0e-9)
        )
        row[f"{domain}_synthesized_to_post_magnitude_ratio"]=(
            abs(synthesized_delta)/(abs(post_delta)+1.0e-9)
        )
        row[f"{domain}_tracker_pre_direction_agree"]=int(
            tracker_delta==0.0 or pre_delta==0.0
            or (tracker_delta>0.0)==(pre_delta>0.0)
        )
        row[f"{domain}_predicted_post_direction_agree"]=int(
            predicted_delta==0.0 or post_delta==0.0
            or (predicted_delta>0.0)==(post_delta>0.0)
        )
        row[f"{domain}_synthesized_post_direction_agree"]=int(
            synthesized_delta==0.0 or post_delta==0.0
            or (synthesized_delta>0.0)==(post_delta>0.0)
        )
    return row


def horizon_review(rows: list[dict[str,Any]]) -> dict[str,Any]:
    if not rows:
        return {"cases":0}
    fields=[
        "low_noise_energy_share",
        "speech_noise_energy_share",
        "high_noise_energy_share",
        "low_update_abs_contribution_fraction",
        "speech_update_abs_contribution_fraction",
        "high_update_abs_contribution_fraction",
        "post_ns_low_energy_share",
        "post_ns_speech_energy_share",
        "post_ns_high_energy_share",
        "elapsed_frames_from_target",
    ]
    for domain in DOMAINS:
        fields.extend((
            MEAN_GAIN_FIELDS[domain],
            FLOOR_FIELDS[domain],
            f"{domain}_pre_ns_response_delta_db",
            f"{domain}_tracker_response_delta_db",
            f"{domain}_predicted_suppressed_response_delta_db",
            f"{domain}_predicted_synthesized_response_delta_db",
            f"{domain}_post_ns_response_delta_db",
            f"{domain}_suppression_attenuation_response_delta_db",
            f"{domain}_tracker_vs_pre_alignment_abs_error_db",
            f"{domain}_predicted_vs_post_alignment_abs_error_db",
            f"{domain}_synthesized_vs_post_alignment_abs_error_db",
            f"{domain}_synthesis_alignment_improvement_db",
            f"{domain}_tracker_vs_post_alignment_abs_error_db",
            f"{domain}_tracker_response_deficit_vs_pre_db",
            f"{domain}_predicted_response_deficit_vs_post_db",
            f"{domain}_pre_to_predicted_response_transfer_db",
            f"{domain}_predicted_to_post_response_residual_db",
            f"{domain}_suppressed_to_synthesized_response_transfer_db",
            f"{domain}_synthesized_to_post_response_residual_db",
            f"{domain}_tracker_to_pre_magnitude_ratio",
            f"{domain}_predicted_to_post_magnitude_ratio",
            f"{domain}_synthesized_to_post_magnitude_ratio",
        ))
    out=median_fields(rows,tuple(fields))
    for domain in DOMAINS:
        predicted_errors=[
            finite(r[f"{domain}_predicted_vs_post_alignment_abs_error_db"])
            for r in rows
        ]
        synthesized_errors=[
            finite(r[f"{domain}_synthesized_vs_post_alignment_abs_error_db"])
            for r in rows
        ]
        tracker_errors=[
            finite(r[f"{domain}_tracker_vs_post_alignment_abs_error_db"])
            for r in rows
        ]
        out[f"p90_{domain}_predicted_vs_post_alignment_abs_error_db"]=(
            percentile_nearest_rank(predicted_errors,0.90)
        )
        out[f"p90_{domain}_synthesized_vs_post_alignment_abs_error_db"]=(
            percentile_nearest_rank(synthesized_errors,0.90)
        )
        out[f"p90_{domain}_tracker_vs_post_alignment_abs_error_db"]=(
            percentile_nearest_rank(tracker_errors,0.90)
        )
        out[f"{domain}_tracker_pre_direction_agreement_fraction"]=(
            sum(int(r[f"{domain}_tracker_pre_direction_agree"]) for r in rows)
            /len(rows)
        )
        out[f"{domain}_predicted_post_direction_agreement_fraction"]=(
            sum(int(r[f"{domain}_predicted_post_direction_agree"]) for r in rows)
            /len(rows)
        )
        out[f"{domain}_synthesized_post_direction_agreement_fraction"]=(
            sum(int(r[f"{domain}_synthesized_post_direction_agree"]) for r in rows)
            /len(rows)
        )
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
        =="i040-ns-synthesis-overlap-add-transfer-decomposition-v1",
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

    transfer=contract["synthesis_overlap_add_observation"]
    require(transfer["selection_or_tuning_allowed"] is False,
            "synthesis overlap-add transfer became selectable")
    require(transfer["domains"]==list(DOMAINS),"domain set drift")
    require(float(transfer["fixed_ns_floor"])==0.12,"NS floor drift")

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
    noise_rms_bitwise_mismatch_frames=0
    max_post_ns_partition_share_gap=0.0
    max_predicted_post_ns_partition_share_gap=0.0
    max_attenuation_identity_gap=0.0
    max_predicted_power_excess=0.0
    max_synthesis_abs_sample_delta=0.0
    max_synthesis_output_rmse=0.0
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
            mirror=item["mirror"]
            inv=item["transfer_invariants"]
            max_ns_delta=max(max_ns_delta,finite(mirror["max_ns_upstream_gap_delta"]))
            max_vad_delta=max(max_vad_delta,finite(mirror["max_vad_probability_delta"]))
            active_mismatch+=int(mirror["vad_active_mismatch_frames"])
            max_reconstruction_gap=max(
                max_reconstruction_gap,
                finite(mirror["max_noise_rms_reconstruction_gap"]),
            )
            noise_rms_bitwise_mismatch_frames+=int(
                mirror["noise_rms_bitwise_mismatch_frames"]
            )
            max_post_ns_partition_share_gap=max(
                max_post_ns_partition_share_gap,
                finite(inv["max_post_ns_partition_share_gap"]),
            )
            max_predicted_post_ns_partition_share_gap=max(
                max_predicted_post_ns_partition_share_gap,
                finite(inv["max_predicted_post_ns_partition_share_gap"]),
            )
            max_synthesis_abs_sample_delta=max(
                max_synthesis_abs_sample_delta,
                finite(inv["max_synthesis_abs_sample_delta"]),
            )
            max_synthesis_output_rmse=max(
                max_synthesis_output_rmse,
                finite(inv["max_synthesis_output_rmse"]),
            )
            max_attenuation_identity_gap=max(
                max_attenuation_identity_gap,
                finite(inv["max_suppression_attenuation_identity_gap_db"]),
            )
            max_predicted_power_excess=max(
                max_predicted_power_excess,
                finite(inv["max_predicted_suppressed_power_excess_db"]),
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
    if max_vad_delta>float(gates["max_vad_shipping_mirror_probability_delta"]):
        invalid_reasons.append("vad_probability_mirror")
    if active_mismatch!=int(gates["vad_shipping_mirror_active_mismatch_frames"]):
        invalid_reasons.append("vad_active_mirror")
    if noise_rms_bitwise_mismatch_frames!=int(
        gates["noise_rms_bitwise_mismatch_frames"]
    ):
        invalid_reasons.append("noise_rms_bitwise_reconstruction")
    if noise_rms_bitwise_mismatch_frames==0 and max_reconstruction_gap!=0.0:
        invalid_reasons.append("noise_rms_numeric_gap_despite_bitwise_match")
    if max_post_ns_partition_share_gap>float(
        gates["max_post_ns_partition_energy_share_gap"]
    ):
        invalid_reasons.append("post_ns_partition_accounting")
    if max_attenuation_identity_gap>float(
        gates["max_suppression_attenuation_identity_gap_db"]
    ):
        invalid_reasons.append("suppression_attenuation_identity")
    if max_predicted_power_excess>float(
        gates["max_predicted_suppressed_power_excess_db"]
    ):
        invalid_reasons.append("predicted_suppressed_power_excess")
    if max_predicted_post_ns_partition_share_gap>float(
        gates["max_predicted_post_ns_partition_energy_share_gap"]
    ):
        invalid_reasons.append("predicted_post_ns_partition_accounting")
    if max_synthesis_abs_sample_delta>float(
        gates["max_synthesis_output_abs_sample_delta"]
    ):
        invalid_reasons.append("synthesis_output_sample_mirror")
    if max_synthesis_output_rmse>float(
        gates["max_synthesis_output_rmse"]
    ):
        invalid_reasons.append("synthesis_output_rmse_mirror")

    global_review={
        str(h):horizon_review(rows_by_horizon[h])
        for h in HORIZONS
    }
    by_noise_domain={
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
        "I040_INPUT_INVALID_REVIEW_REQUIRED"
        if invalid_reasons else
        "NS_SYNTHESIS_OVERLAP_ADD_TRANSFER_DECOMPOSED_REVIEW_REQUIRED"
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
            "noise_rms_bitwise_mismatch_frames":
                noise_rms_bitwise_mismatch_frames,
        },
        "transfer_invariants":{
            "max_post_ns_partition_energy_share_gap":
                max_post_ns_partition_share_gap,
            "max_predicted_post_ns_partition_energy_share_gap":
                max_predicted_post_ns_partition_share_gap,
            "max_suppression_attenuation_identity_gap_db":
                max_attenuation_identity_gap,
            "max_predicted_suppressed_power_excess_db":
                max_predicted_power_excess,
            "max_synthesis_output_abs_sample_delta":
                max_synthesis_abs_sample_delta,
            "max_synthesis_output_rmse":
                max_synthesis_output_rmse,
        },
        "coverage":{
            "target_cases":len(records),
            "causal_target_cases":len(causal),
            "causal_anchor_cases":len(anchored),
            "causal_anchor_coverage":anchor_coverage,
            "fixed_horizon_coverage":horizon_coverage,
        },
        "synthesis_overlap_add_transfer":{
            "target":median_fields(target_rows,tuple(
                field for domain in DOMAINS for field in (
                    MEAN_GAIN_FIELDS[domain],
                    FLOOR_FIELDS[domain],
                    ATTENUATION_FIELDS[domain],
                )
            )),
            "global_fixed_horizons":global_review,
            "by_noise_domain":by_noise_domain,
            "interpretation_authority":
                "diagnostic-only fixed-domain decomposition of the mirrored "
                "suppressed complex spectrum through inverse FFT, frozen "
                "synthesis windows and overlap-add state into predicted "
                "synthesized output, compared with actual post-NS output; "
                "no domain, window, overlap rule, estimator, normalization, "
                "floor, gain, alpha, threshold, horizon, lag, mapping or "
                "source candidate may be selected",
        },
        "receipts":receipts,
        "decision":decision,
        "invalid_reasons":sorted(set(invalid_reasons)),
        "interpretation_boundary":{
            "target_only_no_donor_selection":True,
            "same_i038_causal_target_anchor_semantics":True,
            "fixed_reference_horizons_1_2_4_8_only":True,
            "fixed_low_speech_high_partitions_only":True,
            "shipping_tracker_function_reused_in_mirror":True,
            "exact_shipping_order_all_bin_accumulation":True,
            "bitwise_noise_rms_reconstruction_required":True,
            "pre_ns_power_uses_existing_analysis_spectrum":True,
            "suppression_gain_formula_mirrors_shipping_full_mode":True,
            "fixed_ns_floor_unchanged":True,
            "predicted_suppressed_power_is_observation_only":True,
            "inverse_fft_operation_order_mirrors_shipping":True,
            "synthesis_window_operation_order_mirrors_shipping":True,
            "overlap_add_state_is_diagnostic_only_and_mirrors_shipping":True,
            "predicted_synthesized_output_reanalysis_uses_same_fixed_domains":True,
            "post_ns_reanalysis_uses_same_fixed_spectral_partitions":True,
            "shipping_ns_vad_source_unchanged":True,
            "no_domain_or_spectral_band_selection":True,
            "no_window_or_overlap_add_selection":True,
            "no_estimator_selection":True,
            "no_tracker_alpha_search":True,
            "no_tracker_threshold_search":True,
            "no_ns_floor_or_suppression_gain_tuning":True,
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
    row={
        "low_noise_energy_share":0.2,
        "speech_noise_energy_share":0.7,
        "high_noise_energy_share":0.1,
        "low_update_abs_contribution_fraction":0.2,
        "speech_update_abs_contribution_fraction":0.7,
        "high_update_abs_contribution_fraction":0.1,
        "post_ns_low_energy_share":0.3,
        "post_ns_speech_energy_share":0.6,
        "post_ns_high_energy_share":0.1,
        "elapsed_frames_from_target":8.0,
    }
    for i,domain in enumerate(DOMAINS,1):
        row[MEAN_GAIN_FIELDS[domain]]=0.5
        row[FLOOR_FIELDS[domain]]=0.25
        row[f"{domain}_pre_ns_response_delta_db"]=float(i+3)
        row[f"{domain}_tracker_response_delta_db"]=float(i)
        row[f"{domain}_predicted_suppressed_response_delta_db"]=float(i+2)
        row[f"{domain}_predicted_synthesized_response_delta_db"]=float(i+2.4)
        row[f"{domain}_post_ns_response_delta_db"]=float(i+2.5)
        row[f"{domain}_suppression_attenuation_response_delta_db"]=-1.0
        row[f"{domain}_tracker_vs_pre_alignment_abs_error_db"]=3.0
        row[f"{domain}_predicted_vs_post_alignment_abs_error_db"]=0.5
        row[f"{domain}_synthesized_vs_post_alignment_abs_error_db"]=0.1
        row[f"{domain}_synthesis_alignment_improvement_db"]=0.4
        row[f"{domain}_tracker_vs_post_alignment_abs_error_db"]=2.5
        row[f"{domain}_tracker_response_deficit_vs_pre_db"]=3.0
        row[f"{domain}_predicted_response_deficit_vs_post_db"]=0.5
        row[f"{domain}_pre_to_predicted_response_transfer_db"]=-1.0
        row[f"{domain}_predicted_to_post_response_residual_db"]=0.5
        row[f"{domain}_suppressed_to_synthesized_response_transfer_db"]=0.4
        row[f"{domain}_synthesized_to_post_response_residual_db"]=0.1
        row[f"{domain}_tracker_to_pre_magnitude_ratio"]=0.25
        row[f"{domain}_predicted_to_post_magnitude_ratio"]=0.8
        row[f"{domain}_synthesized_to_post_magnitude_ratio"]=0.96
        row[f"{domain}_tracker_pre_direction_agree"]=1
        row[f"{domain}_predicted_post_direction_agree"]=1
        row[f"{domain}_synthesized_post_direction_agree"]=1
    summary=horizon_review([row])
    assert summary["median_speech_synthesized_vs_post_alignment_abs_error_db"]==0.1
    assert summary["speech_synthesized_post_direction_agreement_fraction"]==1.0
    print("I040 synthesis-overlap-add transfer self-test: OK")


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
        "transfer_invariants":result["transfer_invariants"],
        "target_transfer":result["synthesis_overlap_add_transfer"]["target"],
        "fixed_horizons":
            result["synthesis_overlap_add_transfer"]["global_fixed_horizons"],
    },sort_keys=True))
    return 0 if result["decision"]!="I040_INPUT_INVALID_REVIEW_REQUIRED" else 2


if __name__=="__main__":
    raise SystemExit(main())
