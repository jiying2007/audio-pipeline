#!/usr/bin/env python3
"""Confirm the BF wind candidate against an exact pre-candidate base.

Target wind cases retain absolute product-candidate requirements versus the
frontend-equivalent healthy microphone. Every non-wind case is an anti-
regression control and must remain byte-exact versus the pinned base output.
This avoids pretending that the base beamformer is always close to the healthy
single-microphone oracle for unrelated fault families.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

FAULT_START_FRAME = 200
FAULT_END_FRAME = 500
WIND_MIN_DELTA_DB = -1.0
WIND_MIN_IMPROVEMENT_OVER_BASE_DB = 10.0
WIND_MIN_HARD_ACTIVE_FRACTION = 0.85
MIN_HARD_RELIABLE_SELECTED_FRACTION = 0.99
MAX_NON_WIND_HARD_ACTIVE_FRACTION = 0.01
MAX_RECOVERY_FRAMES = 40
SOFT_CONTROL_TYPES = {"soft-global-gain", "soft-sensitivity-floor"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_trace(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def case_artifact(report_path: Path, case_id: str, name: str) -> Path:
    path = report_path.parent / "case-artifacts" / case_id / name
    if not path.exists():
        raise ValueError(f"missing case artifact: {path}")
    return path


def hard_stats(trace: list[dict], reliable_channel: int) -> tuple[float, float | None]:
    rows = trace[FAULT_START_FRAME:FAULT_END_FRAME]
    if len(rows) != FAULT_END_FRAME - FAULT_START_FRAME:
        raise ValueError(f"trace too short: {len(trace)}")
    hard_rows = [row for row in rows if int(row.get("fallback_hard_fault", 0))]
    hard_fraction = len(hard_rows) / len(rows)
    if not hard_rows:
        return hard_fraction, None
    selected = sum(
        1 for row in hard_rows
        if int(row.get("fallback_strong_channel", -1)) == reliable_channel
    )
    return hard_fraction, selected / len(hard_rows)


def load_report(path: Path) -> tuple[dict, dict[str, dict]]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("frontend") != "hpf-bf":
        raise ValueError(f"confirmation requires hpf-bf: {path}")
    cases = {str(case["case_id"]): case for case in report.get("cases", [])}
    if len(cases) != len(report.get("cases", [])):
        raise ValueError(f"duplicate case ids: {path}")
    return report, cases


def evaluate(candidate_paths: list[Path], base_paths: list[Path]) -> dict:
    if len(candidate_paths) != 3 or len(base_paths) != 3:
        raise ValueError("expected exactly three candidate and three base reports")

    violations: list[dict] = []
    rows: list[dict] = []
    for candidate_path, base_path in zip(candidate_paths, base_paths):
        candidate_report, candidate_cases = load_report(candidate_path)
        base_report, base_cases = load_report(base_path)
        candidate_id = str(candidate_report.get("corpus_id"))
        base_id = str(base_report.get("corpus_id"))
        if candidate_id != base_id:
            raise ValueError(f"corpus mismatch: {candidate_id} != {base_id}")
        if set(candidate_cases) != set(base_cases):
            raise ValueError(f"case-set mismatch: {candidate_path} / {base_path}")

        for case_id in sorted(candidate_cases):
            candidate = candidate_cases[case_id]
            base = base_cases[case_id]
            fault_type = str(candidate.get("fault_type"))
            reliable_channel = int(candidate.get("reliable_channel", 0))
            candidate_output = case_artifact(candidate_path, case_id, "out.pcm")
            base_output = case_artifact(base_path, case_id, "out.pcm")
            candidate_sha = sha256(candidate_output)
            base_sha = sha256(base_output)
            byte_exact = candidate_sha == base_sha

            trace = read_trace(case_artifact(candidate_path, case_id, "trace.jsonl"))
            hard_fraction, selected_fraction = hard_stats(trace, reliable_channel)
            candidate_delta_raw = candidate.get("quality", {}).get("fault_current_minus_reliable_db")
            base_delta_raw = base.get("quality", {}).get("fault_current_minus_reliable_db")
            candidate_delta = None if candidate_delta_raw is None else float(candidate_delta_raw)
            base_delta = None if base_delta_raw is None else float(base_delta_raw)
            improvement = None
            if candidate_delta is not None and base_delta is not None:
                improvement = candidate_delta - base_delta
            recovery_raw = candidate.get("dynamics", {}).get("stable_recovery_latency_frames")
            recovery = None if recovery_raw is None else int(recovery_raw)

            row = {
                "corpus_id": candidate_id,
                "case_id": case_id,
                "fault_type": fault_type,
                "candidate_output_sha256": candidate_sha,
                "base_output_sha256": base_sha,
                "byte_exact_vs_base": byte_exact,
                "candidate_delta_vs_reliable_db": candidate_delta,
                "base_delta_vs_reliable_db": base_delta,
                "candidate_improvement_over_base_db": improvement,
                "hard_active_fraction": hard_fraction,
                "hard_reliable_selected_fraction": selected_fraction,
                "stable_recovery_latency_frames": recovery,
            }
            rows.append(row)

            if fault_type == "wind-burst":
                if candidate_delta is None or candidate_delta < WIND_MIN_DELTA_DB:
                    violations.append({
                        "corpus_id": candidate_id, "case_id": case_id,
                        "gate": "wind_quality_vs_reliable_mic",
                        "actual_db": candidate_delta,
                        "expected_min_db": WIND_MIN_DELTA_DB,
                    })
                if improvement is None or improvement < WIND_MIN_IMPROVEMENT_OVER_BASE_DB:
                    violations.append({
                        "corpus_id": candidate_id, "case_id": case_id,
                        "gate": "wind_improvement_over_exact_base",
                        "actual_db": improvement,
                        "expected_min_db": WIND_MIN_IMPROVEMENT_OVER_BASE_DB,
                    })
                if hard_fraction < WIND_MIN_HARD_ACTIVE_FRACTION:
                    violations.append({
                        "corpus_id": candidate_id, "case_id": case_id,
                        "gate": "wind_hard_mode_coverage",
                        "actual": hard_fraction,
                        "expected_min": WIND_MIN_HARD_ACTIVE_FRACTION,
                    })
                if selected_fraction is None or selected_fraction < MIN_HARD_RELIABLE_SELECTED_FRACTION:
                    violations.append({
                        "corpus_id": candidate_id, "case_id": case_id,
                        "gate": "wind_healthy_channel_selection",
                        "actual": selected_fraction,
                        "expected_min": MIN_HARD_RELIABLE_SELECTED_FRACTION,
                    })
                if recovery is None or recovery > MAX_RECOVERY_FRAMES:
                    violations.append({
                        "corpus_id": candidate_id, "case_id": case_id,
                        "gate": "wind_bounded_recovery",
                        "actual_frames": recovery,
                        "expected_max_frames": MAX_RECOVERY_FRAMES,
                    })
            else:
                if not byte_exact:
                    violations.append({
                        "corpus_id": candidate_id, "case_id": case_id,
                        "gate": "non_wind_output_must_match_exact_base",
                        "candidate_sha256": candidate_sha,
                        "base_sha256": base_sha,
                    })
                if hard_fraction > MAX_NON_WIND_HARD_ACTIVE_FRACTION:
                    violations.append({
                        "corpus_id": candidate_id, "case_id": case_id,
                        "gate": "non_wind_false_hard_mode",
                        "actual": hard_fraction,
                        "expected_max": MAX_NON_WIND_HARD_ACTIVE_FRACTION,
                    })
                if fault_type in SOFT_CONTROL_TYPES and hard_fraction != 0.0:
                    violations.append({
                        "corpus_id": candidate_id, "case_id": case_id,
                        "gate": "soft_degradation_must_remain_soft",
                        "actual": hard_fraction,
                        "expected": 0.0,
                    })

    expected_rows = 3 * 15
    if len(rows) != expected_rows:
        raise ValueError(f"incomplete differential evidence: {len(rows)} != {expected_rows}")
    return {
        "schema_version": 1,
        "authority": "deterministic-differential-confirmation-only",
        "candidate_reports": [str(path) for path in candidate_paths],
        "base_reports": [str(path) for path in base_paths],
        "rows": rows,
        "violations": violations,
        "validation_result": "PASS" if not violations else "FAIL",
    }


def self_test() -> None:
    trace = [
        {"fallback_hard_fault": 1 if 220 <= frame < 490 else 0,
         "fallback_strong_channel": 1}
        for frame in range(800)
    ]
    fraction, selected = hard_stats(trace, 1)
    assert abs(fraction - 0.9) < 1.0e-12
    assert selected == 1.0
    print("BF hard-fault differential confirmation self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-report", action="append", type=Path, default=[])
    parser.add_argument("--base-report", action="append", type=Path, default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output is None:
        parser.error("--output is required")
    result = evaluate(args.candidate_report, args.base_report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for row in result["rows"]:
        print(
            f"{row['corpus_id']} {row['case_id']}: exact={row['byte_exact_vs_base']} "
            f"candidate={row['candidate_delta_vs_reliable_db']}dB "
            f"base={row['base_delta_vs_reliable_db']}dB "
            f"improvement={row['candidate_improvement_over_base_db']}dB "
            f"hard={row['hard_active_fraction']:.3f} "
            f"healthy={row['hard_reliable_selected_fraction']} "
            f"recovery={row['stable_recovery_latency_frames']}f"
        )
    for violation in result["violations"]:
        print("DIFFERENTIAL CONFIRMATION FAIL: " + json.dumps(violation, sort_keys=True))
    return 1 if result["violations"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
