#!/usr/bin/env python3
"""Repository-internal APD triage harness.

This intentionally remains under tests/: it improves engineering/CI diagnosis without
changing the released tools/* surface or the APD v1 format. If this functionality is
promoted into tools/ later, that is a release-bearing change and requires SemVer.
"""

from __future__ import annotations

import argparse
import csv
import json
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import apdump  # noqa: E402

METRICS = struct.Struct("<7fi6I6Q6B2xii")
METRICS_SIZE_V1 = METRICS.size
METRIC_FIELDS = (
    "input_rms_dbfs", "output_rms_dbfs", "noise_rms_dbfs", "erle_db",
    "residual_echo_gain", "vad_probability", "estimated_drift_ppm",
    "delay_error_samples", "estimated_delay_ms", "active_aec_taps",
    "active_aec_adapt_stride", "active_aec_partitions", "aec_block_samples",
    "aec_convergence_frames", "processed_frames", "render_underruns",
    "aec_resets", "delay_jumps", "reference_sample_slips",
    "timestamp_observations", "vad_active", "far_end_active",
    "double_talk_active", "frequency_res_active", "erle_valid",
    "aec_converged", "quality", "aec_backend",
)
QUALITY_NAMES = {0: "SAFE", 1: "LITE", 2: "FULL"}
AEC_BACKEND_NAMES = {0: "MDF", 1: "NLMS"}
METADATA_FLAGS = {
    1 << 0: "capture_timestamp_valid",
    1 << 1: "render_timestamp_valid",
    1 << 2: "capture_discontinuity",
    1 << 3: "render_discontinuity",
    1 << 4: "clock_reset",
    1 << 5: "xrun",
    1 << 6: "codec_reopen",
}
STATEFUL_METADATA_FLAGS = {
    "capture_discontinuity",
    "render_discontinuity",
    "clock_reset",
    "xrun",
    "codec_reopen",
}


def decode_metrics(raw: bytes) -> dict:
    if len(raw) != METRICS_SIZE_V1:
        raise ValueError(
            f"unexpected APD v1 metrics block size {len(raw)}, expected {METRICS_SIZE_V1}"
        )
    metrics = dict(zip(METRIC_FIELDS, METRICS.unpack(raw)))
    metrics["quality_name"] = QUALITY_NAMES.get(
        metrics["quality"], f"UNKNOWN({metrics['quality']})"
    )
    metrics["aec_backend_name"] = AEC_BACKEND_NAMES.get(
        metrics["aec_backend"], f"UNKNOWN({metrics['aec_backend']})"
    )
    return metrics


def metadata_flag_names(flags: int) -> list[str]:
    return [name for bit, name in METADATA_FLAGS.items() if flags & bit]


def decoded_records(header, data: bytes) -> list[dict]:
    records = []
    for record in apdump.iter_records(header, data):
        item = dict(record)
        raw_metrics = item.get("metrics")
        item["metrics"] = decode_metrics(raw_metrics) if raw_metrics is not None else None
        records.append(item)
    return records


def analyze(records: list[dict]) -> dict:
    anomalies: list[dict] = []
    previous = None
    max_abs_delay_error = 0
    max_abs_drift_ppm = 0.0
    quality_transitions = 0
    vad_transitions = 0
    far_end_frames = 0
    double_talk_frames = 0
    converged_frames = 0
    counter_fields = (
        ("render_underruns", "render_underrun"),
        ("aec_resets", "aec_reset"),
        ("delay_jumps", "delay_jump"),
        ("reference_sample_slips", "reference_sample_slip"),
    )

    for record in records:
        flags = metadata_flag_names(int(record["metadata_flags"]))
        noteworthy_flags = [
            flag for flag in flags
            if flag not in ("capture_timestamp_valid", "render_timestamp_valid")
        ]
        if noteworthy_flags:
            anomalies.append({
                "frame": record["index"], "kind": "metadata", "flags": noteworthy_flags
            })
        if record["trigger_event"]:
            anomalies.append({
                "frame": record["index"], "kind": "trigger_event",
                "event": record["trigger_event"],
            })

        metrics = record["metrics"]
        if metrics is None:
            continue
        max_abs_delay_error = max(
            max_abs_delay_error, abs(int(metrics["delay_error_samples"]))
        )
        max_abs_drift_ppm = max(
            max_abs_drift_ppm, abs(float(metrics["estimated_drift_ppm"]))
        )
        far_end_frames += int(bool(metrics["far_end_active"]))
        double_talk_frames += int(bool(metrics["double_talk_active"]))
        converged_frames += int(bool(metrics["aec_converged"]))

        if previous is not None:
            if metrics["quality"] != previous["quality"]:
                quality_transitions += 1
                anomalies.append({
                    "frame": record["index"], "kind": "quality_transition",
                    "from": previous["quality_name"], "to": metrics["quality_name"],
                })
            if metrics["vad_active"] != previous["vad_active"]:
                vad_transitions += 1
            for field, kind in counter_fields:
                delta = int(metrics[field]) - int(previous[field])
                if delta > 0:
                    anomalies.append({
                        "frame": record["index"], "kind": kind, "delta": delta
                    })
            if previous["aec_converged"] and not metrics["aec_converged"]:
                anomalies.append({
                    "frame": record["index"], "kind": "aec_convergence_lost"
                })
        previous = metrics

    metrics_frames = sum(1 for record in records if record["metrics"] is not None)
    return {
        "summary": {
            "frames": len(records),
            "duration_ms": len(records) * 10,
            "metrics_frames": metrics_frames,
            "anomaly_count": len(anomalies),
            "quality_transitions": quality_transitions,
            "vad_transitions": vad_transitions,
            "far_end_active_frames": far_end_frames,
            "double_talk_active_frames": double_talk_frames,
            "aec_converged_frames": converged_frames,
            "max_abs_delay_error_samples": max_abs_delay_error,
            "max_abs_estimated_drift_ppm": max_abs_drift_ppm,
            "final_metrics": previous,
        },
        "anomalies": anomalies,
    }


def replay_comparison(replay: dict) -> dict | None:
    """Read comparison JSON without changing the raw replay wrapper/return code."""
    if not isinstance(replay, dict):
        return None
    comparison = replay.get("comparison")
    if isinstance(comparison, dict):
        return comparison
    output = replay.get("output")
    if not isinstance(output, str) or not output.strip():
        return None
    try:
        decoded = json.loads(output)
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, dict):
        return None
    comparison = decoded.get("comparison")
    return comparison if isinstance(comparison, dict) else None


def replay_authority(analysis: dict, replay: dict) -> dict:
    """Describe what the existing PCM-only replay result can and cannot prove."""
    stateful_flags = sorted({
        str(flag)
        for item in analysis.get("anomalies") or []
        if item.get("kind") == "metadata"
        for flag in (item.get("flags") or [])
        if flag in STATEFUL_METADATA_FLAGS
    })
    comparison = replay_comparison(replay)
    bit_exact = None
    if isinstance(comparison, dict) and isinstance(comparison.get("bit_exact"), bool):
        bit_exact = comparison["bit_exact"]
    stateful = bool(stateful_flags)
    return {
        "authority": "repository-internal-replay-interpretation-only",
        "mode": "pcm-only",
        "state_replay": False,
        "runtime_metadata_state_present": stateful,
        "runtime_metadata_flags": stateful_flags,
        "comparison_present": isinstance(comparison, dict),
        "bit_exact": bit_exact,
        "classification": (
            "stateful-runtime-context-not-replayed"
            if stateful
            else "pcm-only-replay-check"
        ),
        "bit_exact_claim_scope": (
            "recorded PCM output comparison only; runtime metadata/state is present in the APD evidence but is not re-injected by the current replay path"
            if stateful
            else "recorded PCM output comparison only; does not prove whole runtime-execution equivalence"
        ),
        "whole_incident_equivalence_authoritative": False,
    }


def write_metrics(records: list[dict], directory: Path) -> dict:
    rows = [
        {"frame": r["index"], "sequence": r["sequence"], **r["metrics"]}
        for r in records if r["metrics"] is not None
    ]
    if not rows:
        return {}
    jsonl = directory / "metrics.jsonl"
    jsonl.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    csv_path = directory / "metrics.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return {"metrics_jsonl": str(jsonl), "metrics_csv": str(csv_path)}


def run(command: list[str]) -> dict:
    completed = subprocess.run(
        command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "output": completed.stdout or "",
    }


def write_summary(path: Path, result: dict) -> None:
    summary = result["analysis"]["summary"]
    comparison = replay_comparison(result.get("replay") or {}) or {}
    authority = result.get("replay_authority") or {}
    lines = [
        "# Audio dump triage",
        "",
        f"- dump: `{result['dump']}`",
        f"- APD build version: `{result['header']['build']['version']}`",
        f"- frames: `{summary['frames']}` / duration `{summary['duration_ms']} ms`",
        f"- decoded metrics frames: `{summary['metrics_frames']}`",
        f"- anomalies: `{summary['anomaly_count']}`",
        f"- max |delay error|: `{summary['max_abs_delay_error_samples']}` samples",
        f"- max |drift|: `{summary['max_abs_estimated_drift_ppm']}` ppm",
        f"- quality transitions: `{summary['quality_transitions']}`",
        f"- AEC converged frames: `{summary['aec_converged_frames']}`",
    ]
    if comparison:
        lines.extend([
            f"- bit-exact replay: `{comparison.get('bit_exact')}`",
            f"- replay MAE: `{comparison.get('mae_lsb')}` LSB",
            f"- replay max abs: `{comparison.get('max_abs_lsb')}` LSB",
        ])
    if authority:
        lines.extend([
            f"- replay mode: `{authority.get('mode')}`",
            f"- replay authority classification: `{authority.get('classification')}`",
            f"- runtime metadata/state present: `{authority.get('runtime_metadata_state_present')}`",
            f"- whole-incident equivalence authoritative: `{authority.get('whole_incident_equivalence_authoritative')}`",
        ])
    anomalies = result["analysis"]["anomalies"]
    if anomalies:
        lines.extend(["", "## Anomaly timeline", ""])
        for item in anomalies:
            details = ", ".join(
                f"{k}={v}" for k, v in item.items() if k not in ("frame", "kind")
            )
            lines.append(
                f"- frame `{item['frame']}`: `{item['kind']}`"
                + (f" — {details}" if details else "")
            )
    lines.extend([
        "", "## Evidence boundary", "",
        "This repository-internal harness does not change APD v1 or the released tools/* surface.",
        "Stage counterfactuals reprocess recorded microphone PCM through isolated profiles; they are not live intermediate taps from the original execution.",
        "The current replay path is PCM-only and does not prove whole runtime-execution equivalence.",
        "When stateful runtime metadata is present, a replay mismatch cannot by itself distinguish a DSP regression from runtime-state that was not re-injected.",
        "Bit-exact PCM comparison additionally requires a processor matching the APD build fingerprint.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def triage(
    dump: Path, processor: Path, output_dir: Path,
    stage_counterfactuals: bool, require_bit_exact: bool,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted_dir = output_dir / "extracted"
    manifest = apdump.extract(dump, extracted_dir)
    header, data = apdump.read_dump(dump)
    records = decoded_records(header, data)
    metric_paths = write_metrics(records, extracted_dir)
    analysis = analyze(records)
    analysis_path = output_dir / "analysis.json"
    analysis_path.write_text(
        json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    replay_command = [
        sys.executable, str(TOOLS / "apreplay.py"), str(dump),
        "--processor", str(processor),
        "--output-pcm", str(output_dir / "replay-output.pcm"),
    ]
    if require_bit_exact:
        replay_command.append("--require-bit-exact")
    replay_process = run(replay_command)
    (output_dir / "replay.log").write_text(replay_process["output"], encoding="utf-8")
    replay = replay_process
    if replay_process["returncode"] == 0:
        try:
            replay = json.loads(replay_process["output"])
        except json.JSONDecodeError:
            pass
    authority = replay_authority(analysis, replay)

    stages: dict[str, dict] = {}
    if stage_counterfactuals:
        mic_value = manifest.get("streams", {}).get("mic")
        mic_path = Path(mic_value) if mic_value else None
        if mic_path and mic_path.exists():
            profiles = ["ns-isolated", "vad-isolated", "agc-isolated"]
            if header.mic_channels == 2:
                profiles.insert(0, "bf-isolated")
            for profile in profiles:
                stage_output = output_dir / f"{profile}.pcm"
                stage_metrics = output_dir / f"{profile}-metrics.jsonl"
                stages[profile] = run([
                    str(processor),
                    "--sample-rate", str(header.sample_rate_hz),
                    "--mic-channels", str(header.mic_channels),
                    "--capture-profile", profile,
                    "--capture-only",
                    "--metrics-jsonl", str(stage_metrics),
                    str(mic_path), str(stage_output),
                ])
        else:
            stages["status"] = {"skipped": "APD has no microphone PCM"}

    replay_failed = isinstance(replay, dict) and replay.get("returncode", 0) != 0
    stage_failed = any(
        isinstance(value, dict) and int(value.get("returncode", 0)) != 0
        for value in stages.values()
    )
    result = {
        "schema_version": 1,
        "authority": "repository-internal-diagnostic-only",
        "dump": str(dump),
        "processor": str(processor),
        "header": apdump.header_json(header),
        "analysis": analysis,
        "metrics": metric_paths,
        "replay": replay,
        "replay_authority": authority,
        "stage_counterfactuals": stages,
        "status": "FAIL" if replay_failed or stage_failed else "PASS",
        "notes": [
            "does not alter the released APD v1 format or tools/* surface",
            "stage counterfactuals are isolated reprocessing, not captured live intermediate taps",
            "replay_authority is interpretation metadata only and does not change raw replay comparison or PASS/FAIL",
            "the current replay path is PCM-only and does not prove whole runtime-execution equivalence",
        ],
    }
    (output_dir / "triage.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_summary(output_dir / "summary.md", result)
    return result


def self_test() -> None:
    assert METRICS_SIZE_V1 == 120
    values = (
        [-20.0, -21.0, -40.0, 12.0, 0.5, 0.8, -3.25]
        + [-2]
        + [40, 1024, 2, 32, 32, 100]
        + [10, 1, 2, 3, 4, 5]
        + [1, 1, 0, 1, 1, 1]
        + [2, 0]
    )
    decoded = decode_metrics(METRICS.pack(*values))
    assert decoded["quality_name"] == "FULL"
    assert decoded["aec_backend_name"] == "MDF"
    assert decoded["delay_error_samples"] == -2
    assert metadata_flag_names((1 << 2) | (1 << 5)) == ["capture_discontinuity", "xrun"]

    replay = {"comparison": {"bit_exact": True}}
    ordinary = replay_authority({"anomalies": []}, replay)
    assert ordinary["classification"] == "pcm-only-replay-check"
    assert ordinary["runtime_metadata_state_present"] is False
    assert ordinary["bit_exact"] is True
    assert ordinary["whole_incident_equivalence_authoritative"] is False

    failed_wrapper = {
        "returncode": 1,
        "output": json.dumps({"comparison": {"bit_exact": False}}),
    }
    failed = replay_authority({"anomalies": []}, failed_wrapper)
    assert failed["classification"] == "pcm-only-replay-check"
    assert failed["comparison_present"] is True
    assert failed["bit_exact"] is False
    assert failed_wrapper["returncode"] == 1

    stateful = replay_authority(
        {
            "anomalies": [
                {"frame": 2, "kind": "metadata", "flags": ["clock_reset", "xrun"]}
            ]
        },
        {"comparison": {"bit_exact": False}},
    )
    assert stateful["classification"] == "stateful-runtime-context-not-replayed"
    assert stateful["runtime_metadata_state_present"] is True
    assert stateful["runtime_metadata_flags"] == ["clock_reset", "xrun"]
    assert stateful["bit_exact"] is False
    assert stateful["state_replay"] is False
    assert stateful["whole_incident_equivalence_authoritative"] is False
    print("repository diagnostic triage self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dump", nargs="?", type=Path)
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--stage-counterfactuals", action="store_true")
    parser.add_argument("--require-bit-exact", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.dump or not args.processor or not args.output_dir:
        parser.error("dump, --processor and --output-dir are required")
    try:
        result = triage(
            args.dump, args.processor, args.output_dir,
            args.stage_counterfactuals, args.require_bit_exact,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"aptriage: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "status": result["status"],
        "anomalies": result["analysis"]["summary"]["anomaly_count"],
        "output_dir": str(args.output_dir),
    }, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
