#!/usr/bin/env python3
"""I034 candidate-zero NS/VAD noise-state temporal-response decomposition."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tests"/"validation"))
import i033_ns_vad_causal_noise_delta_alignment as base  # type: ignore

HORIZONS=(1,2,4,8)
NOISE_DOMAINS=base.NOISE_DOMAINS


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


def horizon_summary(rows: list[dict[str,Any]]) -> dict[str,Any]:
    if not rows:
        return {"cases":0}
    ns_abs=[abs(float(r["ns_response_delta_db"])) for r in rows]
    local_abs=[abs(float(r["local_response_delta_db"])) for r in rows]
    errors=[float(r["alignment_abs_error_db"]) for r in rows]
    signed=[float(r["alignment_signed_error_db"]) for r in rows]
    elapsed=[float(r["elapsed_frames_from_target"]) for r in rows]
    median_ns=statistics.median(ns_abs)
    median_local=statistics.median(local_abs)
    return {
        "cases":len(rows),
        "median_elapsed_frames_from_target":statistics.median(elapsed),
        "median_absolute_ns_response_db":median_ns,
        "median_absolute_local_response_db":median_local,
        "median_absolute_alignment_error_db":statistics.median(errors),
        "p90_absolute_alignment_error_db":
            percentile_nearest_rank(errors,0.90),
        "maximum_absolute_alignment_error_db":max(errors),
        "median_signed_alignment_error_db":statistics.median(signed),
        "median_abs_response_ratio_ns_over_local":
            median_ns/median_local if median_local>1.0e-12 else None,
    }


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
    ns_value=statistics.median(
        float(frame["ns_noise_rms_dbfs"]) for frame in prefix
    )
    local_value=statistics.median(
        float(frame["post_ns_rms_dbfs"]) for frame in prefix
    )
    ns_delta=ns_value-float(anchor["ns_noise_rms_dbfs"])
    local_delta=local_value-float(anchor["post_ns_rms_dbfs"])
    return {
        "target_case_key":meta["case_key"],
        "metadata":meta,
        "horizon_reference_count":horizon,
        "elapsed_frames_from_target":
            int(prefix[-1]["local_frame_index"])
            - int(target["local_frame_index"]),
        "anchor_absolute_frame_index":
            int(anchor["absolute_frame_index"]),
        "target_absolute_frame_index":
            int(target["absolute_frame_index"]),
        "horizon_absolute_frame_index":
            int(prefix[-1]["absolute_frame_index"]),
        "anchor_ns_noise_rms_dbfs":
            float(anchor["ns_noise_rms_dbfs"]),
        "anchor_post_ns_rms_dbfs":
            float(anchor["post_ns_rms_dbfs"]),
        "cumulative_ns_noise_rms_dbfs":ns_value,
        "cumulative_post_ns_rms_dbfs":local_value,
        "ns_response_delta_db":ns_delta,
        "local_response_delta_db":local_delta,
        "alignment_signed_error_db":ns_delta-local_delta,
        "alignment_abs_error_db":abs(ns_delta-local_delta),
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
        =="i034-ns-vad-noise-state-temporal-response-decomposition-v1",
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

    horizons=tuple(
        int(v) for v in
        contract["fixed_temporal_response_semantics"]["reference_horizons"]
    )
    require(horizons==HORIZONS,"fixed horizon grid drift")
    require(
        contract["fixed_temporal_response_semantics"]
        ["cumulative_median_through_horizon"] is True,
        "cumulative horizon statistic drift",
    )
    require(
        contract["fixed_temporal_response_semantics"]
        ["best_horizon_selection_allowed"] is False,
        "best-horizon selection was enabled",
    )

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
            item=base.analyze_case(
                probe,path,case,upstream_guard,seed
            )
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
    minimum_horizon_coverage=float(
        gates["minimum_fixed_horizon_coverage"]
    )
    for horizon in HORIZONS:
        coverage=(
            len(rows_by_horizon[horizon])/len(anchored)
            if anchored else 0.0
        )
        horizon_coverage[str(horizon)]=coverage
        if coverage<minimum_horizon_coverage:
            invalid_reasons.append(
                f"horizon_{horizon}_coverage"
            )

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

    global_response={
        str(h):horizon_summary(rows_by_horizon[h])
        for h in HORIZONS
    }
    per_domain={}
    for domain in NOISE_DOMAINS:
        per_domain[domain]={
            str(h):horizon_summary([
                row for row in rows_by_horizon[h]
                if row["metadata"]["noise_domain"]==domain
            ])
            for h in HORIZONS
        }

    per_domain_coverage={}
    for domain in NOISE_DOMAINS:
        domain_anchored=[
            r for r in anchored
            if r["metadata"]["noise_domain"]==domain
        ]
        per_domain_coverage[domain]={
            "causal_target_cases":sum(
                1 for r in causal
                if r["metadata"]["noise_domain"]==domain
            ),
            "causal_anchor_cases":len(domain_anchored),
            "horizon_coverage":{
                str(h):(
                    sum(
                        1 for row in rows_by_horizon[h]
                        if row["metadata"]["noise_domain"]==domain
                    )/len(domain_anchored)
                    if domain_anchored else None
                )
                for h in HORIZONS
            },
        }

    progression={
        "reference_horizons":list(HORIZONS),
        "median_absolute_ns_response_db":[
            global_response[str(h)].get(
                "median_absolute_ns_response_db"
            ) for h in HORIZONS
        ],
        "median_absolute_local_response_db":[
            global_response[str(h)].get(
                "median_absolute_local_response_db"
            ) for h in HORIZONS
        ],
        "median_absolute_alignment_error_db":[
            global_response[str(h)].get(
                "median_absolute_alignment_error_db"
            ) for h in HORIZONS
        ],
        "median_elapsed_frames_from_target":[
            global_response[str(h)].get(
                "median_elapsed_frames_from_target"
            ) for h in HORIZONS
        ],
        "authority":
            "descriptive fixed-horizon decomposition only; "
            "cannot select a best horizon, lag, alpha, mapping or candidate",
    }

    decision=(
        "I034_INPUT_INVALID_REVIEW_REQUIRED"
        if invalid_reasons else
        "NS_VAD_NOISE_STATE_TEMPORAL_RESPONSE_DECOMPOSED_REVIEW_REQUIRED"
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
            "per_domain":per_domain_coverage,
        },
        "temporal_response":{
            "global":global_response,
            "by_noise_domain":per_domain,
            "progression":progression,
        },
        "receipts":receipts,
        "decision":decision,
        "invalid_reasons":sorted(set(invalid_reasons)),
        "interpretation_boundary":{
            "target_only_no_donor_selection":True,
            "causal_anchor_is_last_prior_ordinary_noise_reference":True,
            "target_is_first_pre_ready_speech_disagreement":True,
            "anchor_and_target_are_causal":True,
            "post_target_references_are_retrospective_only":True,
            "fixed_reference_horizons_only":True,
            "cumulative_median_through_each_horizon":True,
            "elapsed_frames_are_reported_not_selected":True,
            "shipping_ns_vad_source_unchanged":True,
            "no_best_horizon_or_lag_selection":True,
            "no_tracker_alpha_search":True,
            "no_absolute_or_relative_normalization_mapping":True,
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
    rows=[
        {
            "ns_response_delta_db":1.0,
            "local_response_delta_db":2.0,
            "alignment_abs_error_db":1.0,
            "alignment_signed_error_db":-1.0,
            "elapsed_frames_from_target":4,
        },
        {
            "ns_response_delta_db":2.0,
            "local_response_delta_db":4.0,
            "alignment_abs_error_db":2.0,
            "alignment_signed_error_db":-2.0,
            "elapsed_frames_from_target":8,
        },
    ]
    summary=horizon_summary(rows)
    assert HORIZONS==(1,2,4,8)
    assert summary["cases"]==2
    assert summary["median_absolute_ns_response_db"]==1.5
    assert summary["median_absolute_local_response_db"]==3.0
    assert summary["median_abs_response_ratio_ns_over_local"]==0.5
    assert summary["p90_absolute_alignment_error_db"]==2.0
    print("I034 temporal-response decomposition self-test: OK")


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
    result=evaluate(
        args.probe,args.target_corpus,args.contract,args.output
    )
    print(json.dumps({
        "decision":result["decision"],
        "invalid_reasons":result["invalid_reasons"],
        "coverage":result["coverage"],
        "temporal_response":result["temporal_response"]["global"],
    },sort_keys=True))
    return 0 if result["decision"]!="I034_INPUT_INVALID_REVIEW_REQUIRED" else 2


if __name__=="__main__":
    raise SystemExit(main())
