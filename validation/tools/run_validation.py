#!/usr/bin/env python3
"""Run canonical acoustic validation and emit hash-bound evidence."""

from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import os
import statistics
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Sequence

SUPPORTED_RATES = {8000, 16000, 24000, 32000, 48000}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_raw(path: Path) -> list[int]:
    data = path.read_bytes()
    if len(data) % 2:
        raise ValueError(f"odd S16LE byte count: {path}")
    values = array.array("h")
    values.frombytes(data)
    if os.sys.byteorder != "little":
        values.byteswap()
    return list(values)


def read_audio(path: Path, expected_rate: int, expected_channels: int) -> tuple[list[int], bytes]:
    if path.suffix.lower() != ".wav":
        raw = path.read_bytes()
        return read_raw(path), raw
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        rate = handle.getframerate()
        width = handle.getsampwidth()
        compression = handle.getcomptype()
        if channels != expected_channels:
            raise ValueError(f"WAV channel mismatch {path}: {channels} != {expected_channels}")
        if rate != expected_rate:
            raise ValueError(f"WAV rate mismatch {path}: {rate} != {expected_rate}")
        if width != 2 or compression != "NONE":
            raise ValueError(f"only uncompressed PCM16 WAV is supported: {path}")
        raw = handle.readframes(handle.getnframes())
    values = array.array("h")
    values.frombytes(raw)
    if os.sys.byteorder != "little":
        values.byteswap()
    return list(values), raw


def resolve(corpus_path: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else corpus_path.parent / path


def mono(interleaved: Sequence[int], channels: int, channel: int = 0) -> list[int]:
    if channels < 1 or channel >= channels or len(interleaved) % channels:
        raise ValueError("invalid interleaved geometry")
    return list(interleaved[channel::channels])


def rms_dbfs(samples: Sequence[int]) -> float:
    if not samples:
        return -120.0
    energy = sum(float(x) * float(x) for x in samples) / len(samples)
    if energy <= 1.0e-18:
        return -120.0
    return 10.0 * math.log10(energy / (32768.0 * 32768.0))


def si_sdr_db(reference: Sequence[int], estimate: Sequence[int]) -> float | None:
    count = min(len(reference), len(estimate))
    if count < 16:
        return None
    ref = [float(x) for x in reference[:count]]
    est = [float(x) for x in estimate[:count]]
    ref_energy = sum(x * x for x in ref)
    if ref_energy <= 1.0e-12:
        return None
    scale = sum(r * e for r, e in zip(ref, est)) / ref_energy
    target_energy = sum((scale * r) ** 2 for r in ref)
    noise_energy = sum((e - scale * r) ** 2 for r, e in zip(ref, est))
    return 10.0 * math.log10((target_energy + 1.0e-12) / (noise_energy + 1.0e-12))


def normalized_corr(a: Sequence[int], b: Sequence[int], lag: int, stride: int = 4) -> float:
    if lag >= 0:
        count = min(len(a) - lag, len(b))
        ai = lag
        bi = 0
    else:
        count = min(len(a), len(b) + lag)
        ai = 0
        bi = -lag
    if count < 64:
        return 0.0
    xy = xx = yy = 0.0
    for offset in range(0, count, stride):
        x = float(a[ai + offset])
        y = float(b[bi + offset])
        xy += x * y
        xx += x * x
        yy += y * y
    if xx <= 1.0e-12 or yy <= 1.0e-12:
        return 0.0
    return abs(xy / math.sqrt(xx * yy))


def max_abs_corr(a: Sequence[int], b: Sequence[int], sample_rate: int) -> float:
    max_lag = max(1, sample_rate // 10)
    step = max(1, max_lag // 60)
    lags = list(range(-max_lag, max_lag + 1, step))
    if 0 not in lags:
        lags.append(0)
    return max((normalized_corr(a, b, lag) for lag in lags), default=0.0)


def aligned_si_sdr(reference: Sequence[int], estimate: Sequence[int],
                   sample_rate: int, expected_delay_samples: int) -> tuple[float | None, int]:
    """Calculate SI-SDR after bounded sample-exact latency refinement.

    The search is anchored to the pipeline-declared algorithmic latency. Input
    references use an expected delay of zero. A narrow +/-3 ms refinement
    absorbs integer-ms latency reporting and filter rounding without turning
    the evaluator into an unconstrained synchronizer that can search for a
    favorable score.
    """
    radius = max(2, sample_rate * 3 // 1000)
    center = -int(expected_delay_samples)
    best_lag = center
    best_corr = -1.0
    for lag in range(center - radius, center + radius + 1):
        corr = normalized_corr(reference, estimate, lag, stride=4)
        if corr > best_corr:
            best_corr = corr
            best_lag = lag
    if best_lag >= 0:
        ref = reference[best_lag:]
        est = estimate
    else:
        ref = reference
        est = estimate[-best_lag:]
    count = min(len(ref), len(est))
    if count < 16:
        return None, -best_lag
    return si_sdr_db(ref[:count], est[:count]), -best_lag


def erle_db(echo: Sequence[int], output: Sequence[int]) -> float | None:
    count = min(len(echo), len(output))
    if count < 160:
        return None
    start = count // 2
    ein = sum(float(x) * float(x) for x in echo[start:count])
    eout = sum(float(x) * float(x) for x in output[start:count])
    if ein <= 1.0e-12:
        return None
    return 10.0 * math.log10((ein + 1.0e-12) / (eout + 1.0e-12))


def vad_f1(labels: list[int], trace: list[dict]) -> float | None:
    predicted = [1 if int(row.get("vad_active", 0)) else 0 for row in trace]
    count = min(len(labels), len(predicted))
    if count == 0:
        return None
    tp = sum(1 for i in range(count) if labels[i] and predicted[i])
    fp = sum(1 for i in range(count) if not labels[i] and predicted[i])
    fn = sum(1 for i in range(count) if labels[i] and not predicted[i])
    if tp == 0:
        return 0.0
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    return 2.0 * precision * recall / (precision + recall)


def load_labels(path: Path) -> list[int]:
    labels = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = int(line.strip())
            if value not in (0, 1):
                raise ValueError(f"invalid VAD label: {value}")
            labels.append(value)
    return labels


def stage_audio(path: Path, rate: int, channels: int, directory: Path, name: str) -> tuple[list[int], Path]:
    values, raw = read_audio(path, rate, channels)
    staged = directory / name
    staged.write_bytes(raw)
    return values, staged


def invoke(processor: Path, case: dict, corpus_path: Path, work: Path) -> tuple[list[int], list[dict], dict]:
    rate = int(case["sample_rate_hz"])
    channels = int(case["mic_channels"])
    mic_path = resolve(corpus_path, case["mic_audio"])
    render_path = resolve(corpus_path, case.get("render_audio"))
    if mic_path is None:
        raise ValueError("mic_audio is required")
    mic, mic_raw = stage_audio(mic_path, rate, channels, work, "mic.pcm")
    render = None
    render_raw = None
    if render_path is not None:
        render, render_raw = stage_audio(render_path, rate, 1, work, "render.pcm")
    output_path = work / "out.pcm"
    metrics_path = work / "metrics.jsonl"
    command = [str(processor), "--sample-rate", str(rate), "--mic-channels", str(channels),
               "--metrics-jsonl", str(metrics_path)]
    control = case.get("control", {})
    if "echo_path_change_frame" in control:
        command += ["--echo-path-change-frame", str(int(control["echo_path_change_frame"]))]
    if "discontinuity_frame" in control:
        command += ["--discontinuity-frame", str(int(control["discontinuity_frame"])),
                    "--discontinuity-flags", str(int(control.get("discontinuity_flags", 1))),
                    "--discontinuity-lost-frames", str(int(control.get("discontinuity_lost_frames", 1)))]
    if render_raw is None:
        command += ["--capture-only", str(mic_raw), str(output_path)]
    else:
        command += [str(mic_raw), str(render_raw), str(output_path)]
    subprocess.run(command, check=True)
    output = read_raw(output_path)
    trace = []
    if metrics_path.exists():
        for line in metrics_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                trace.append(json.loads(line))
    return output, trace, {"mic": mic, "render": render}


def threshold_violations(metrics: dict, expected: dict) -> list[dict]:
    violations = []
    mapping = {
        "min_near_si_sdr_db": ("near_si_sdr_db", "min"),
        "min_near_si_sdr_improvement_db": ("near_si_sdr_improvement_db", "min"),
        "min_output_rms_dbfs": ("output_rms_dbfs", "min"),
        "max_output_rms_dbfs": ("output_rms_dbfs", "max"),
        "max_output_render_corr_ratio": ("output_render_corr_ratio", "max"),
        "min_output_render_corr_reduction": ("output_render_corr_reduction", "min"),
        "min_erle_db": ("erle_db", "min"),
        "min_vad_f1": ("vad_f1", "min"),
    }
    unknown = set(expected) - set(mapping)
    if unknown:
        raise ValueError(f"unknown expected thresholds: {sorted(unknown)}")
    for gate, limit in expected.items():
        metric, direction = mapping[gate]
        value = metrics.get(metric)
        fail = value is None or (direction == "min" and float(value) < float(limit)) or (direction == "max" and float(value) > float(limit))
        if fail:
            violations.append({"gate": gate, "metric": metric, "actual": value,
                               "expected_min" if direction == "min" else "expected_max": float(limit)})
    return violations


def evaluate_case(processor: Path, corpus_path: Path, case: dict) -> dict:
    rate = int(case["sample_rate_hz"])
    channels = int(case["mic_channels"])
    if rate not in SUPPORTED_RATES or channels not in (1, 2):
        raise ValueError(f"unsupported geometry in {case['case_id']}")
    with tempfile.TemporaryDirectory(prefix="ap-validation-") as temporary:
        work = Path(temporary)
        output, trace, inputs = invoke(processor, case, corpus_path, work)
    mic0 = mono(inputs["mic"], channels)
    metrics: dict[str, float | int | None] = {
        "input_rms_dbfs": rms_dbfs(mic0),
        "output_rms_dbfs": rms_dbfs(output),
        "frames": min(len(mic0), len(output)),
    }
    render = inputs["render"]
    if render is not None:
        input_corr = max_abs_corr(mic0, render, rate)
        output_corr = max_abs_corr(output, render, rate)
        metrics.update({
            "input_render_max_abs_corr": input_corr,
            "output_render_max_abs_corr": output_corr,
            "output_render_corr_ratio": output_corr / max(input_corr, 1.0e-9),
            "output_render_corr_reduction": input_corr - output_corr,
        })
    clean_path = resolve(corpus_path, case.get("clean_near_audio"))
    if clean_path is not None:
        clean, _ = read_audio(clean_path, rate, 1)
        declared_latency_ms = int(trace[0].get("algorithmic_latency_ms", 0)) if trace else 0
        expected_output_delay = declared_latency_ms * rate // 1000
        input_sdr, input_alignment = aligned_si_sdr(clean, mic0, rate, 0)
        output_sdr, output_alignment = aligned_si_sdr(clean, output, rate, expected_output_delay)
        metrics["input_near_si_sdr_db"] = input_sdr
        metrics["near_si_sdr_db"] = output_sdr
        metrics["declared_algorithmic_latency_ms"] = declared_latency_ms
        metrics["input_alignment_samples"] = input_alignment
        metrics["output_alignment_samples"] = output_alignment
        metrics["near_si_sdr_improvement_db"] = None if input_sdr is None or output_sdr is None else output_sdr - input_sdr
    echo_path = resolve(corpus_path, case.get("echo_audio"))
    if echo_path is not None:
        echo, _ = read_audio(echo_path, rate, 1)
        metrics["erle_db"] = erle_db(echo, output)
    labels_path = resolve(corpus_path, case.get("vad_labels"))
    if labels_path is not None:
        metrics["vad_f1"] = vad_f1(load_labels(labels_path), trace)
    violations = threshold_violations(metrics, case.get("expected", {}))
    return {
        "case_id": case["case_id"], "split": case["split"], "scenario": case["scenario"],
        "source": case.get("source", {}), "metrics": metrics,
        "violations": violations, "passed": not violations,
    }


def median_metric(cases: list[dict], name: str) -> float | None:
    values = [float(case["metrics"][name]) for case in cases if case["metrics"].get(name) is not None]
    return statistics.median(values) if values else None


def load_revision(explicit: str | None) -> str:
    if explicit:
        return explicit
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown-source-revision"


def policy_violations(policy: dict, corpus: dict, cases: list[dict]) -> tuple[dict, list[dict]]:
    violations = []
    tier = corpus["tier"]
    if tier not in policy.get("allowed_tiers", []):
        violations.append({"gate": "allowed_tiers", "actual": tier})
    minimum_cases = int(policy.get("minimum_cases", 1))
    if len(cases) < minimum_cases:
        violations.append({"gate": "minimum_cases", "actual": len(cases), "expected_min": minimum_cases})
    required_sources = set(policy.get("required_public_sources", []))
    actual_sources = set(corpus.get("sources", []))
    if not required_sources.issubset(actual_sources):
        violations.append({"gate": "required_public_sources", "missing": sorted(required_sources - actual_sources)})
    if tier != "regression":
        if not corpus.get("sealed_data"):
            violations.append({"gate": "sealed_data", "actual": False})
        if any(case.get("split") == "dev" for case in corpus["cases"]):
            violations.append({"gate": "no_dev_cases_in_validation_grade"})
    if tier == "validation-grade-blind" and not corpus.get("blind_key_fingerprint"):
        violations.append({"gate": "blind_key_fingerprint"})
    pass_rate = sum(1 for case in cases if case["passed"]) / max(1, len(cases))
    summary = {
        "cases": len(cases),
        "passed_cases": sum(1 for case in cases if case["passed"]),
        "pass_rate": pass_rate,
        "median_near_si_sdr_improvement_db": median_metric(cases, "near_si_sdr_improvement_db"),
        "median_erle_db": median_metric(cases, "erle_db"),
        "median_output_render_corr_reduction": median_metric(cases, "output_render_corr_reduction"),
        "min_vad_f1": min((float(case["metrics"]["vad_f1"]) for case in cases if case["metrics"].get("vad_f1") is not None), default=None),
    }
    aggregate = policy.get("aggregate", {})
    checks = {
        "min_pass_rate": ("pass_rate", "min"),
        "min_median_near_si_sdr_improvement_db": ("median_near_si_sdr_improvement_db", "min"),
        "min_median_erle_db": ("median_erle_db", "min"),
        "min_median_output_render_corr_reduction": ("median_output_render_corr_reduction", "min"),
        "min_vad_f1": ("min_vad_f1", "min"),
    }
    for gate, limit in aggregate.items():
        if gate not in checks:
            raise ValueError(f"unknown aggregate gate: {gate}")
        metric, _ = checks[gate]
        value = summary.get(metric)
        if value is None or float(value) < float(limit):
            violations.append({"gate": gate, "metric": metric, "actual": value, "expected_min": float(limit)})
    return summary, violations


def validate_corpus_shape(corpus: dict) -> None:
    if corpus.get("schema_version") != 1:
        raise ValueError("corpus schema_version must be 1")
    if corpus.get("tier") not in {"regression", "validation-grade", "validation-grade-blind"}:
        raise ValueError("invalid corpus tier")
    ids = [case.get("case_id") for case in corpus.get("cases", [])]
    if not ids or len(set(ids)) != len(ids) or any(not item for item in ids):
        raise ValueError("case_id values must be non-empty and unique")


def write_evidence(path: Path, report_path: Path, corpus_path: Path, policy_path: Path,
                   dataset_lock_path: Path) -> None:
    artifacts = []
    for artifact_type, artifact in [
        ("validation-report", report_path), ("validation-corpus", corpus_path),
        ("validation-policy", policy_path), ("dataset-lock", dataset_lock_path),
    ]:
        artifacts.append({"type": artifact_type, "path": str(artifact),
                          "size": artifact.stat().st_size, "sha256": sha256_file(artifact)})
    manifest = {"schema_version": 1, "evidence_type": "validation", "artifacts": artifacts}
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def self_test() -> None:
    rate = 16000
    ref = [int(10000 * math.sin(math.tau * 440.0 * n / rate)) for n in range(rate)]
    assert (si_sdr_db(ref, ref) or 0) > 100
    assert max_abs_corr(ref, ref, rate) > 0.99
    state = 1
    broadband = []
    for _ in range(rate):
        state = (1664525 * state + 1013904223) & 0xffffffff
        broadband.append(((state >> 16) & 0xffff) - 32768)
    delayed = [0] * 137 + broadband[:-137]
    delayed_sdr, alignment = aligned_si_sdr(broadband, delayed, rate, 137)
    assert alignment == 137
    assert delayed_sdr is not None and delayed_sdr > 100
    assert vad_f1([0, 1, 1, 0], [{"vad_active": 0}, {"vad_active": 1}, {"vad_active": 1}, {"vad_active": 0}]) == 1.0
    assert rms_dbfs([0] * 10) <= -119.0
    print("validation evaluator self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--policy", type=Path)
    parser.add_argument("--dataset-lock", type=Path, default=Path("validation/datasets.lock.json"))
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--evidence-manifest", type=Path)
    parser.add_argument("--source-revision")
    parser.add_argument("--blind-summary-only", action="store_true")
    parser.add_argument("--enforce", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    for name in ("corpus", "policy", "processor", "output"):
        if getattr(args, name) is None:
            parser.error(f"--{name.replace('_', '-')} is required")
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    validate_corpus_shape(corpus)
    cases = [evaluate_case(args.processor, args.corpus, case) for case in corpus["cases"]]
    summary, aggregate_violations = policy_violations(policy, corpus, cases)
    case_violations = [{"case_id": case["case_id"], "violations": case["violations"]}
                       for case in cases if case["violations"]]
    violations = case_violations + aggregate_violations
    report_cases = cases
    if args.blind_summary_only and corpus["tier"] == "validation-grade-blind":
        report_cases = [{"case_id": case["case_id"], "passed": case["passed"]} for case in cases]
    report = {
        "schema_version": 1,
        "validation_result": "PASS" if not violations else "FAIL",
        "tier": corpus["tier"],
        "corpus_id": corpus["corpus_id"],
        "policy_id": policy.get("policy_id"),
        "source_revision": load_revision(args.source_revision),
        "bindings": {
            "dataset_lock_sha256": sha256_file(args.dataset_lock),
            "corpus_sha256": sha256_file(args.corpus),
            "policy_sha256": sha256_file(args.policy),
        },
        "summary": summary,
        "cases": report_cases,
        "violations": violations,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.evidence_manifest:
        write_evidence(args.evidence_manifest, args.output, args.corpus, args.policy, args.dataset_lock)
    print(json.dumps({"result": report["validation_result"], "tier": report["tier"], **summary}, sort_keys=True))
    return 1 if args.enforce and violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
