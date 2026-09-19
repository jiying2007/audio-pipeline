#!/usr/bin/env python3
"""Ground-truth quality extensions for the canonical acoustic evaluator.

The canonical engine remains the only source of the existing SI-SDR, ERLE,
render-correlation, VAD and safety metrics. This module adds missing
scale-sensitive and temporal measurements needed to decide whether an acoustic
candidate is actually better rather than merely different:

* near-end projection gain (detects RES/NS/BF over-suppression hidden by SI-SDR),
* known-interference projection attenuation (detects real echo/competitor level change),
* interference correlation reduction as a diagnostic only,
* AEC convergence and post-event recovery time from known echo truth,
* VAD onset/release delay from frame labels.

Only cases that opt in through ``quality`` or an explicit truth reference are
replayed a second time. Existing public/regression corpora keep their historical
metric behavior. No result from this module has shipping authority.
"""

from __future__ import annotations

import copy
import math
import statistics
import tempfile
from pathlib import Path
from typing import Any, Sequence

QUALITY_THRESHOLDS = {
    "min_near_projection_gain_db": ("near_projection_gain_db", "min"),
    "min_interference_projection_attenuation_db": ("interference_projection_attenuation_db", "min"),
    "min_interference_corr_reduction": ("interference_corr_reduction", "min"),
    "min_noise_ref_corr_reduction": ("noise_ref_corr_reduction", "min"),
    "max_erle_convergence_ms": ("erle_convergence_ms", "max"),
    "max_erle_recovery_ms": ("erle_recovery_ms", "max"),
    "max_vad_onset_delay_ms": ("vad_onset_delay_ms", "max"),
    "max_vad_release_delay_ms": ("vad_release_delay_ms", "max"),
}

QUALITY_AGGREGATES = {
    "min_p10_near_projection_gain_db": ("p10_near_projection_gain_db", "min"),
    "min_p10_interference_projection_attenuation_db": ("p10_interference_projection_attenuation_db", "min"),
    "min_p10_interference_corr_reduction": ("p10_interference_corr_reduction", "min"),
    "max_p90_erle_convergence_ms": ("p90_erle_convergence_ms", "max"),
    "max_p90_erle_recovery_ms": ("p90_erle_recovery_ms", "max"),
    "max_p90_vad_onset_delay_ms": ("p90_vad_onset_delay_ms", "max"),
    "max_p90_vad_release_delay_ms": ("p90_vad_release_delay_ms", "max"),
}


def _percentile(values: list[float], quantile: float) -> float | None:
    values = sorted(value for value in values if math.isfinite(value))
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    position = max(0.0, min(1.0, quantile)) * (len(values) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] * (1.0 - fraction) + values[upper] * fraction


def _align(reference: Sequence[int], estimate: Sequence[int], delay_samples: int) -> tuple[list[int], list[int]]:
    delay = int(delay_samples)
    if delay >= 0:
        ref = list(reference)
        est = list(estimate[delay:])
    else:
        ref = list(reference[-delay:])
        est = list(estimate)
    count = min(len(ref), len(est))
    return ref[:count], est[:count]


def projection_gain_db(reference: Sequence[int], estimate: Sequence[int], delay_samples: int) -> float | None:
    ref, est = _align(reference, estimate, delay_samples)
    if len(ref) < 160:
        return None
    energy = sum(float(value) * float(value) for value in ref)
    if energy <= 1.0e-12:
        return None
    scale = sum(float(r) * float(e) for r, e in zip(ref, est)) / energy
    magnitude = abs(scale)
    if magnitude <= 1.0e-12:
        return -120.0
    return 20.0 * math.log10(magnitude)


def _window_erle(echo: Sequence[int], output: Sequence[int], rate: int,
                 output_delay_samples: int) -> list[tuple[int, float]]:
    ref, est = _align(echo, output, output_delay_samples)
    window = max(160, rate // 10)  # 100 ms
    step = max(80, rate // 100)    # 10 ms
    curve: list[tuple[int, float]] = []
    for start in range(0, max(0, min(len(ref), len(est)) - window + 1), step):
        stop = start + window
        ein = sum(float(x) * float(x) for x in ref[start:stop])
        eout = sum(float(x) * float(x) for x in est[start:stop])
        if ein <= 1.0e-12:
            continue
        value = 10.0 * math.log10((ein + 1.0e-12) / (eout + 1.0e-12))
        curve.append((start, value))
    return curve


def _settling_ms(curve: list[tuple[int, float]], rate: int, start_sample: int = 0) -> float | None:
    eligible = [(sample, value) for sample, value in curve if sample >= max(0, start_sample)]
    if len(eligible) < 4:
        return None
    tail_count = max(3, len(eligible) // 4)
    final_level = statistics.median(value for _, value in eligible[-tail_count:])
    target = final_level - 3.0
    for index in range(0, len(eligible) - 2):
        window = eligible[index:index + 3]
        if all(value >= target for _, value in window):
            return 1000.0 * (window[0][0] - start_sample) / rate
    return None


def vad_transition_delays_ms(labels: list[int], trace: list[dict], frame_ms: float = 10.0) -> tuple[float | None, float | None]:
    predicted = [1 if int(row.get("vad_active", 0)) else 0 for row in trace]
    count = min(len(labels), len(predicted))
    if count < 2:
        return None, None
    onset: list[float] = []
    release: list[float] = []
    for index in range(1, count):
        if labels[index - 1] == 0 and labels[index] == 1:
            found = next((probe for probe in range(index, min(count, index + 50)) if predicted[probe]), None)
            if found is not None:
                onset.append((found - index) * frame_ms)
        if labels[index - 1] == 1 and labels[index] == 0:
            found = next((probe for probe in range(index, min(count, index + 100)) if not predicted[probe]), None)
            if found is not None:
                release.append((found - index) * frame_ms)
    return _percentile(onset, 0.90), _percentile(release, 0.90)


def _quality_threshold_violations(metrics: dict, expected: dict) -> list[dict]:
    violations = []
    for gate, limit in expected.items():
        metric, direction = QUALITY_THRESHOLDS[gate]
        value = metrics.get(metric)
        fail = value is None or (
            direction == "min" and float(value) < float(limit)
        ) or (
            direction == "max" and float(value) > float(limit)
        )
        if fail:
            violations.append({
                "gate": gate,
                "metric": metric,
                "actual": value,
                "expected_min" if direction == "min" else "expected_max": float(limit),
            })
    return violations


def _summary_value(cases: list[dict], metric: str, quantile: float) -> float | None:
    values = [
        float(case["metrics"][metric])
        for case in cases
        if case.get("metrics", {}).get(metric) is not None
    ]
    return _percentile(values, quantile)


def _split_expected(case: dict) -> tuple[dict, dict]:
    base_case = copy.deepcopy(case)
    expected = dict(base_case.get("expected", {}))
    quality = {key: expected.pop(key) for key in list(expected) if key in QUALITY_THRESHOLDS}
    base_case["expected"] = expected
    return base_case, quality


def _needs_quality(case: dict, quality_expected: dict) -> bool:
    return bool(
        case.get("quality")
        or case.get("interference_audio")
        or case.get("noise_audio")
        or quality_expected
    )


def install(engine: Any) -> None:
    if getattr(engine, "_quality_metric_support_installed", False):
        return
    original_evaluate_case = engine.evaluate_case
    original_policy_violations = engine.policy_violations

    def evaluate_case(processor: Path, corpus_path: Path, case: dict) -> dict:
        base_case, quality_expected = _split_expected(case)
        if not _needs_quality(case, quality_expected):
            return original_evaluate_case(processor, corpus_path, base_case)

        rate = int(case["sample_rate_hz"])
        channels = int(case["mic_channels"])
        with tempfile.TemporaryDirectory(prefix="ap-quality-") as temporary:
            output, trace, inputs = engine.invoke(
                processor, base_case, corpus_path, Path(temporary)
            )
        result = engine.evaluate_case_runtime(
            corpus_path, base_case, output, trace, inputs
        )
        mic0 = engine.mono_view(inputs["mic"], channels)
        declared_latency_ms = int(trace[0].get("algorithmic_latency_ms", 0)) if trace else 0
        declared_delay = declared_latency_ms * rate // 1000

        clean_path = engine.resolve(corpus_path, case.get("clean_near_audio"))
        if clean_path is not None:
            clean = engine.read_audio_samples(clean_path, rate, 1)
            _, output_alignment = engine.aligned_si_sdr(clean, output, rate, declared_delay)
            result["metrics"]["near_projection_gain_db"] = projection_gain_db(
                clean, output, output_alignment
            )

        interference_path = engine.resolve(corpus_path, case.get("interference_audio"))
        if interference_path is not None:
            interference = engine.read_audio_samples(interference_path, rate, 1)
            input_corr = engine.max_abs_corr(mic0, interference, rate)
            output_corr = engine.max_abs_corr(output, interference, rate)
            _, input_alignment = engine.aligned_si_sdr(interference, mic0, rate, 0)
            _, output_alignment = engine.aligned_si_sdr(interference, output, rate, declared_delay)
            input_projection = projection_gain_db(interference, mic0, input_alignment)
            output_projection = projection_gain_db(interference, output, output_alignment)
            attenuation = None
            if input_projection is not None and output_projection is not None:
                attenuation = input_projection - output_projection
            result["metrics"].update({
                "input_interference_max_abs_corr": input_corr,
                "output_interference_max_abs_corr": output_corr,
                "interference_corr_reduction": input_corr - output_corr,
                "input_interference_projection_gain_db": input_projection,
                "output_interference_projection_gain_db": output_projection,
                "interference_projection_attenuation_db": attenuation,
            })

        noise_path = engine.resolve(corpus_path, case.get("noise_audio"))
        if noise_path is not None:
            noise = engine.read_audio_samples(noise_path, rate, 1)
            input_corr = engine.max_abs_corr(mic0, noise, rate)
            output_corr = engine.max_abs_corr(output, noise, rate)
            result["metrics"].update({
                "input_noise_ref_max_abs_corr": input_corr,
                "output_noise_ref_max_abs_corr": output_corr,
                "noise_ref_corr_reduction": input_corr - output_corr,
            })

        echo_path = engine.resolve(corpus_path, case.get("echo_audio"))
        if echo_path is not None and case.get("clean_near_audio") is None:
            echo = engine.read_audio_samples(echo_path, rate, 1)
            curve = _window_erle(echo, output, rate, declared_delay)
            result["metrics"]["erle_convergence_ms"] = _settling_ms(curve, rate, 0)
            control = case.get("control", {})
            event_frame = control.get("echo_path_change_frame", control.get("discontinuity_frame"))
            if event_frame is not None:
                event_sample = int(event_frame) * max(1, rate // 100)
                result["metrics"]["erle_recovery_ms"] = _settling_ms(curve, rate, event_sample)

        labels_path = engine.resolve(corpus_path, case.get("vad_labels"))
        if labels_path is not None and trace:
            onset, release = vad_transition_delays_ms(engine.load_labels(labels_path), trace)
            result["metrics"]["vad_onset_delay_ms"] = onset
            result["metrics"]["vad_release_delay_ms"] = release

        quality_violations = _quality_threshold_violations(result["metrics"], quality_expected)
        result["violations"].extend(quality_violations)
        result["passed"] = not result["violations"]
        return result

    def policy_violations(policy: dict, corpus: dict, cases: list[dict]) -> tuple[dict, list[dict]]:
        base_policy = copy.deepcopy(policy)
        aggregate = dict(base_policy.get("aggregate", {}))
        quality_aggregate = {
            key: aggregate.pop(key) for key in list(aggregate) if key in QUALITY_AGGREGATES
        }
        base_policy["aggregate"] = aggregate
        summary, violations = original_policy_violations(base_policy, corpus, cases)
        summary.update({
            "p10_near_projection_gain_db": _summary_value(cases, "near_projection_gain_db", 0.10),
            "p10_interference_projection_attenuation_db": _summary_value(cases, "interference_projection_attenuation_db", 0.10),
            "p10_interference_corr_reduction": _summary_value(cases, "interference_corr_reduction", 0.10),
            "p90_erle_convergence_ms": _summary_value(cases, "erle_convergence_ms", 0.90),
            "p90_erle_recovery_ms": _summary_value(cases, "erle_recovery_ms", 0.90),
            "p90_vad_onset_delay_ms": _summary_value(cases, "vad_onset_delay_ms", 0.90),
            "p90_vad_release_delay_ms": _summary_value(cases, "vad_release_delay_ms", 0.90),
        })
        for gate, limit in quality_aggregate.items():
            metric, direction = QUALITY_AGGREGATES[gate]
            value = summary.get(metric)
            fail = value is None or (
                direction == "min" and float(value) < float(limit)
            ) or (
                direction == "max" and float(value) > float(limit)
            )
            if fail:
                violations.append({
                    "gate": gate,
                    "metric": metric,
                    "actual": value,
                    "expected_min" if direction == "min" else "expected_max": float(limit),
                })
        return summary, violations

    engine.evaluate_case = evaluate_case
    engine.policy_violations = policy_violations
    engine._quality_metric_support_installed = True


def self_test() -> None:
    ref = [1000, -1000] * 320
    est = [0] * 160 + [500, -500] * 240
    gain = projection_gain_db(ref, est, 160)
    assert gain is not None and -6.2 < gain < -5.8
    input_gain = projection_gain_db(ref, ref, 0)
    output_gain = projection_gain_db(ref, [value // 2 for value in ref], 0)
    assert input_gain is not None and output_gain is not None
    attenuation = input_gain - output_gain
    assert 5.9 < attenuation < 6.2
    labels = [0] * 10 + [1] * 20 + [0] * 20
    trace = [{"vad_active": 0}] * 12 + [{"vad_active": 1}] * 20 + [{"vad_active": 0}] * 18
    onset, release = vad_transition_delays_ms(labels, trace)
    assert onset == 20.0 and release == 20.0
    curve = [(index * 160, value) for index, value in enumerate([-10.0, -2.0, 1.0, 5.0, 6.0, 6.5, 6.2])]
    settled = _settling_ms(curve, 16000)
    assert settled is not None and settled >= 20.0

    class FakeEngine:
        def __init__(self) -> None:
            self.invoke_count = 0

        def evaluate_case(self, processor: Path, corpus_path: Path,
                          case: dict) -> dict:
            raise AssertionError("quality case must not invoke base evaluator")

        def evaluate_case_runtime(self, corpus_path: Path, case: dict,
                                  output: Sequence[int], trace: list[dict],
                                  inputs: dict) -> dict:
            return {
                "case_id": case["case_id"],
                "split": case["split"],
                "scenario": case["scenario"],
                "source": {},
                "dimensions": {},
                "metrics": {},
                "violations": [],
                "passed": True,
            }

        def invoke(self, processor: Path, case: dict, corpus_path: Path,
                   work: Path) -> tuple[list[int], list[dict], dict]:
            self.invoke_count += 1
            return [0] * 160, [{"algorithmic_latency_ms": 0}], {
                "mic": [0] * 160,
                "render": None,
            }

        @staticmethod
        def mono_view(samples: Sequence[int], channels: int) -> Sequence[int]:
            return samples

        @staticmethod
        def policy_violations(policy: dict, corpus: dict,
                              cases: list[dict]) -> tuple[dict, list[dict]]:
            return {}, []

    fake = FakeEngine()
    install(fake)
    probe_case = {
        "case_id": "quality-single-invoke",
        "split": "validation",
        "scenario": "self-test",
        "sample_rate_hz": 16000,
        "mic_channels": 1,
        "quality": {},
        "expected": {"min_near_projection_gain_db": -120.0},
    }
    fake.evaluate_case(Path("processor"), Path("corpus.json"), probe_case)
    assert fake.invoke_count == 1
    print("quality metric support self-test: OK")


if __name__ == "__main__":
    self_test()
