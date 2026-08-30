#!/usr/bin/env python3
"""One-time v2.1.0 extended-real evaluator migration. Removed before merge."""

from __future__ import annotations

from pathlib import Path


def replace_region(text: str, start: str, end: str, replacement: str) -> str:
    begin = text.index(start)
    finish = text.index(end, begin)
    return text[:begin] + replacement.rstrip() + "\n\n" + text[finish:]


path = Path("validation/tools/run_validation.py")
text = path.read_text(encoding="utf-8")

helpers = r'''
def peak_dbfs(samples: Sequence[int]) -> float:
    if not samples:
        return -120.0
    peak = max(abs(int(value)) for value in samples)
    if peak <= 0:
        return -120.0
    return 20.0 * math.log10(peak / 32768.0)


def clip_fraction(samples: Sequence[int], threshold: int = 32760) -> float:
    if not samples:
        return 0.0
    return sum(1 for value in samples if abs(int(value)) >= threshold) / len(samples)


def dc_offset_dbfs(samples: Sequence[int]) -> float:
    if not samples:
        return -120.0
    mean = abs(sum(float(value) for value in samples) / len(samples))
    if mean <= 1.0e-12:
        return -120.0
    return 20.0 * math.log10(mean / 32768.0)
'''
needle = "\ndef si_sdr_db(reference: Sequence[int], estimate: Sequence[int]) -> float | None:\n"
if helpers.strip() not in text:
    text = text.replace(needle, "\n" + helpers.strip() + "\n\n" + needle.lstrip("\n"), 1)

vad_block = r'''
def vad_stats(labels: list[int], trace: list[dict]) -> dict[str, float | None]:
    predicted = [1 if int(row.get("vad_active", 0)) else 0 for row in trace]
    count = min(len(labels), len(predicted))
    if count == 0:
        return {
            "f1": None, "precision": None, "recall": None,
            "false_positive_rate": None, "false_negative_rate": None,
        }
    tp = sum(1 for i in range(count) if labels[i] and predicted[i])
    fp = sum(1 for i in range(count) if not labels[i] and predicted[i])
    fn = sum(1 for i in range(count) if labels[i] and not predicted[i])
    tn = count - tp - fp - fn
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    fnr = fn / (fn + tp) if fn + tp else 0.0
    return {
        "f1": f1, "precision": precision, "recall": recall,
        "false_positive_rate": fpr, "false_negative_rate": fnr,
    }


def vad_f1(labels: list[int], trace: list[dict]) -> float | None:
    return vad_stats(labels, trace)["f1"]
'''
text = replace_region(text, "def vad_f1(", "def noise_only_attenuation_db(", vad_block)

speech_fn = r'''
def speech_active_attenuation_db(input_samples: Sequence[int], output: Sequence[int],
                                 labels: list[int], rate: int,
                                 output_delay_samples: int) -> tuple[float | None, int]:
    frame = rate // 100
    input_energy = 0.0
    output_energy = 0.0
    used_frames = 0
    sample_count = 0
    for frame_index in range(1, len(labels) - 1):
        if not (labels[frame_index - 1] and labels[frame_index] and labels[frame_index + 1]):
            continue
        input_start = frame_index * frame
        output_start = input_start + output_delay_samples
        if output_start < 0:
            continue
        count = min(frame, len(input_samples) - input_start, len(output) - output_start)
        if count <= 0:
            continue
        for offset in range(count):
            x = float(input_samples[input_start + offset])
            y = float(output[output_start + offset])
            input_energy += x * x
            output_energy += y * y
        used_frames += 1
        sample_count += count
    if sample_count < frame or input_energy <= 1.0e-12:
        return None, used_frames
    return 10.0 * math.log10((input_energy + 1.0e-12) / (output_energy + 1.0e-12)), used_frames
'''
needle = "\ndef load_labels(path: Path) -> list[int]:\n"
if speech_fn.strip() not in text:
    text = text.replace(needle, "\n" + speech_fn.strip() + "\n\n" + needle.lstrip("\n"), 1)

threshold_fn = r'''
def threshold_violations(metrics: dict, expected: dict) -> list[dict]:
    violations = []
    mapping = {
        "min_near_si_sdr_db": ("near_si_sdr_db", "min"),
        "min_near_si_sdr_improvement_db": ("near_si_sdr_improvement_db", "min"),
        "min_output_rms_dbfs": ("output_rms_dbfs", "min"),
        "max_output_rms_dbfs": ("output_rms_dbfs", "max"),
        "min_output_rms_delta_db": ("output_rms_delta_db", "min"),
        "max_output_rms_delta_db": ("output_rms_delta_db", "max"),
        "max_output_clip_fraction": ("output_clip_fraction", "max"),
        "max_output_dc_offset_dbfs": ("output_dc_offset_dbfs", "max"),
        "max_output_render_corr_ratio": ("output_render_corr_ratio", "max"),
        "min_output_render_corr_reduction": ("output_render_corr_reduction", "min"),
        "min_erle_db": ("erle_db", "min"),
        "min_vad_f1": ("vad_f1", "min"),
        "min_vad_precision": ("vad_precision", "min"),
        "min_vad_recall": ("vad_recall", "min"),
        "max_vad_false_positive_rate": ("vad_false_positive_rate", "max"),
        "max_vad_false_negative_rate": ("vad_false_negative_rate", "max"),
        "min_noise_only_attenuation_db": ("noise_only_attenuation_db", "min"),
        "max_speech_active_attenuation_db": ("speech_active_attenuation_db", "max"),
    }
    unknown = set(expected) - set(mapping)
    if unknown:
        raise ValueError(f"unknown expected thresholds: {sorted(unknown)}")
    for gate, limit in expected.items():
        metric, direction = mapping[gate]
        value = metrics.get(metric)
        fail = value is None or (direction == "min" and float(value) < float(limit)) or (direction == "max" and float(value) > float(limit))
        if fail:
            violations.append({
                "gate": gate, "metric": metric, "actual": value,
                "expected_min" if direction == "min" else "expected_max": float(limit),
            })
    return violations
'''
text = replace_region(text, "def threshold_violations(", "def evaluate_case(", threshold_fn)

evaluate_fn = r'''
def evaluate_case(processor: Path, corpus_path: Path, case: dict) -> dict:
    rate = int(case["sample_rate_hz"])
    channels = int(case["mic_channels"])
    if rate not in SUPPORTED_RATES or channels not in (1, 2):
        raise ValueError(f"unsupported geometry in {case['case_id']}")
    with tempfile.TemporaryDirectory(prefix="ap-validation-") as temporary:
        work = Path(temporary)
        output, trace, inputs = invoke(processor, case, corpus_path, work)
    mic0 = mono(inputs["mic"], channels)
    input_rms = rms_dbfs(mic0)
    output_rms = rms_dbfs(output)
    metrics: dict[str, float | int | None] = {
        "input_rms_dbfs": input_rms,
        "output_rms_dbfs": output_rms,
        "output_rms_delta_db": output_rms - input_rms,
        "input_peak_dbfs": peak_dbfs(mic0),
        "output_peak_dbfs": peak_dbfs(output),
        "input_clip_fraction": clip_fraction(mic0),
        "output_clip_fraction": clip_fraction(output),
        "input_dc_offset_dbfs": dc_offset_dbfs(mic0),
        "output_dc_offset_dbfs": dc_offset_dbfs(output),
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
        labels = load_labels(labels_path)
        vad = vad_stats(labels, trace)
        metrics.update({
            "vad_f1": vad["f1"],
            "vad_precision": vad["precision"],
            "vad_recall": vad["recall"],
            "vad_false_positive_rate": vad["false_positive_rate"],
            "vad_false_negative_rate": vad["false_negative_rate"],
        })
        declared_latency_ms = int(trace[0].get("algorithmic_latency_ms", 0)) if trace else 0
        output_delay = int(metrics.get("output_alignment_samples", declared_latency_ms * rate // 1000) or 0)
        attenuation, noise_frames = noise_only_attenuation_db(mic0, output, labels, rate, output_delay)
        speech_attenuation, speech_frames = speech_active_attenuation_db(mic0, output, labels, rate, output_delay)
        metrics["noise_only_attenuation_db"] = attenuation
        metrics["noise_only_frames"] = noise_frames
        metrics["speech_active_attenuation_db"] = speech_attenuation
        metrics["speech_active_frames"] = speech_frames
    violations = threshold_violations(metrics, case.get("expected", {}))
    return {
        "case_id": case["case_id"], "split": case["split"], "scenario": case["scenario"],
        "source": case.get("source", {}), "dimensions": case.get("dimensions", {}),
        "metrics": metrics, "violations": violations, "passed": not violations,
    }
'''
text = replace_region(text, "def evaluate_case(", "def median_metric(", evaluate_fn)

percentile_fn = r'''
def percentile_metric(cases: list[dict], name: str, quantile: float) -> float | None:
    values = sorted(float(case["metrics"][name]) for case in cases if case["metrics"].get(name) is not None)
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
'''
needle = "\ndef load_revision(explicit: str | None) -> str:\n"
if percentile_fn.strip() not in text:
    text = text.replace(needle, "\n" + percentile_fn.strip() + "\n\n" + needle.lstrip("\n"), 1)

policy_fn = r'''
def policy_violations(policy: dict, corpus: dict, cases: list[dict]) -> tuple[dict, list[dict]]:
    violations: list[dict] = []
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

    by_scenario: dict[str, list[dict]] = {}
    for case in cases:
        by_scenario.setdefault(case["scenario"], []).append(case)
    required_scenarios = set(policy.get("required_scenarios", []))
    if not required_scenarios.issubset(by_scenario):
        violations.append({"gate": "required_scenarios", "missing": sorted(required_scenarios - set(by_scenario))})
    minimum_by_scenario = policy.get("minimum_cases_by_scenario", {})
    for scenario, minimum in minimum_by_scenario.items():
        actual = len(by_scenario.get(scenario, []))
        if actual < int(minimum):
            violations.append({
                "gate": "minimum_cases_by_scenario", "scenario": scenario,
                "actual": actual, "expected_min": int(minimum),
            })
    scenario_pass_rate = {
        scenario: sum(1 for case in group if case["passed"]) / max(1, len(group))
        for scenario, group in sorted(by_scenario.items())
    }
    for scenario, minimum in policy.get("minimum_pass_rate_by_scenario", {}).items():
        actual = scenario_pass_rate.get(scenario)
        if actual is None or actual < float(minimum):
            violations.append({
                "gate": "minimum_pass_rate_by_scenario", "scenario": scenario,
                "actual": actual, "expected_min": float(minimum),
            })

    dimension_values: dict[str, list[object]] = {}
    for name, required_values in policy.get("required_dimension_values", {}).items():
        seen = sorted({
            case.get("dimensions", {}).get(name)
            for case in cases
            if case.get("dimensions", {}).get(name) is not None
        }, key=str)
        dimension_values[name] = seen
        missing = [value for value in required_values if value not in seen]
        if missing:
            violations.append({"gate": "required_dimension_values", "dimension": name, "missing": missing})

    pass_rate = sum(1 for case in cases if case["passed"]) / max(1, len(cases))
    summary = {
        "cases": len(cases),
        "passed_cases": sum(1 for case in cases if case["passed"]),
        "pass_rate": pass_rate,
        "scenario_pass_rate": scenario_pass_rate,
        "dimension_values": dimension_values,
        "median_near_si_sdr_improvement_db": median_metric(cases, "near_si_sdr_improvement_db"),
        "p10_near_si_sdr_improvement_db": percentile_metric(cases, "near_si_sdr_improvement_db", 0.10),
        "p10_noise_only_attenuation_db": percentile_metric(cases, "noise_only_attenuation_db", 0.10),
        "median_erle_db": median_metric(cases, "erle_db"),
        "median_output_render_corr_reduction": median_metric(cases, "output_render_corr_reduction"),
        "min_vad_f1": min((float(case["metrics"]["vad_f1"]) for case in cases if case["metrics"].get("vad_f1") is not None), default=None),
        "min_vad_recall": min((float(case["metrics"]["vad_recall"]) for case in cases if case["metrics"].get("vad_recall") is not None), default=None),
        "max_vad_false_positive_rate": max((float(case["metrics"]["vad_false_positive_rate"]) for case in cases if case["metrics"].get("vad_false_positive_rate") is not None), default=None),
        "max_output_clip_fraction": max((float(case["metrics"]["output_clip_fraction"]) for case in cases if case["metrics"].get("output_clip_fraction") is not None), default=None),
        "max_output_dc_offset_dbfs": max((float(case["metrics"]["output_dc_offset_dbfs"]) for case in cases if case["metrics"].get("output_dc_offset_dbfs") is not None), default=None),
    }
    checks = {
        "min_pass_rate": ("pass_rate", "min"),
        "min_median_near_si_sdr_improvement_db": ("median_near_si_sdr_improvement_db", "min"),
        "min_p10_near_si_sdr_improvement_db": ("p10_near_si_sdr_improvement_db", "min"),
        "min_p10_noise_only_attenuation_db": ("p10_noise_only_attenuation_db", "min"),
        "min_median_erle_db": ("median_erle_db", "min"),
        "min_median_output_render_corr_reduction": ("median_output_render_corr_reduction", "min"),
        "min_vad_f1": ("min_vad_f1", "min"),
        "min_vad_recall": ("min_vad_recall", "min"),
        "max_vad_false_positive_rate": ("max_vad_false_positive_rate", "max"),
        "max_output_clip_fraction": ("max_output_clip_fraction", "max"),
        "max_output_dc_offset_dbfs": ("max_output_dc_offset_dbfs", "max"),
    }
    for gate, limit in policy.get("aggregate", {}).items():
        if gate not in checks:
            raise ValueError(f"unknown aggregate gate: {gate}")
        metric, direction = checks[gate]
        value = summary.get(metric)
        fail = value is None or (direction == "min" and float(value) < float(limit)) or (direction == "max" and float(value) > float(limit))
        if fail:
            violations.append({
                "gate": gate, "metric": metric, "actual": value,
                "expected_min" if direction == "min" else "expected_max": float(limit),
            })
    return summary, violations
'''
text = replace_region(text, "def policy_violations(", "def validate_corpus_shape(", policy_fn)

shape_fn = r'''
def validate_corpus_shape(corpus: dict) -> None:
    if corpus.get("schema_version") != 1:
        raise ValueError("corpus schema_version must be 1")
    if corpus.get("tier") not in {"regression", "validation-grade", "validation-grade-blind", "research-validation"}:
        raise ValueError("invalid corpus tier")
    ids = [case.get("case_id") for case in corpus.get("cases", [])]
    if not ids or len(set(ids)) != len(ids) or any(not item for item in ids):
        raise ValueError("case_id values must be non-empty and unique")
    invalid_profiles = sorted({case.get("processor_profile", "default") for case in corpus.get("cases", [])} - {"default", "ns-isolated"})
    if invalid_profiles:
        raise ValueError(f"invalid processor_profile values: {invalid_profiles}")
    for case in corpus.get("cases", []):
        dimensions = case.get("dimensions", {})
        if not isinstance(dimensions, dict):
            raise ValueError(f"dimensions must be an object: {case.get('case_id')}")
        for name, value in dimensions.items():
            if not isinstance(name, str) or not isinstance(value, (str, int, float, bool)):
                raise ValueError(f"dimensions must contain scalar values: {case.get('case_id')}/{name}")
'''
text = replace_region(text, "def validate_corpus_shape(", "def write_evidence(", shape_fn)

write_fn = r'''
def write_evidence(path: Path, report_path: Path, corpus_path: Path, policy_path: Path,
                   dataset_lock_path: Path, source_manifest_path: Path | None = None) -> None:
    artifacts = []
    inputs = [
        ("validation-report", report_path), ("validation-corpus", corpus_path),
        ("validation-policy", policy_path), ("dataset-lock", dataset_lock_path),
    ]
    if source_manifest_path is not None:
        inputs.append(("source-manifest", source_manifest_path))
    for artifact_type, artifact in inputs:
        artifacts.append({"type": artifact_type, "path": str(artifact),
                          "size": artifact.stat().st_size, "sha256": sha256_file(artifact)})
    manifest = {"schema_version": 1, "evidence_type": "validation", "artifacts": artifacts}
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
'''
text = replace_region(text, "def write_evidence(", "def self_test(", write_fn)

self_test_fn = r'''
def self_test() -> None:
    rate = 16000
    ref = [int(10000 * math.sin(math.tau * 440.0 * n / rate)) for n in range(rate)]
    assert (si_sdr_db(ref, ref) or 0) > 100
    assert max_abs_corr(ref, ref, rate) > 0.99
    assert -11.0 < peak_dbfs([10000, -10000]) < -10.0
    assert clip_fraction([32767, -32768, 0, 1]) == 0.5
    assert dc_offset_dbfs([0, 0, 0]) <= -119.0
    state = 1
    broadband = []
    for _ in range(rate):
        state = (1664525 * state + 1013904223) & 0xffffffff
        broadband.append(((state >> 16) & 0xffff) - 32768)
    delayed = [0] * 137 + broadband[:-137]
    delayed_sdr, alignment = aligned_si_sdr(broadband, delayed, rate, 137)
    assert alignment == 137
    assert delayed_sdr is not None and delayed_sdr > 100
    trace = [{"vad_active": 0}, {"vad_active": 1}, {"vad_active": 1}, {"vad_active": 0}]
    stats = vad_stats([0, 1, 1, 0], trace)
    assert stats["f1"] == 1.0 and stats["recall"] == 1.0 and stats["false_positive_rate"] == 0.0
    negative_stats = vad_stats([0, 0, 0, 0], [{"vad_active": 1}] * 4)
    assert negative_stats["false_positive_rate"] == 1.0
    noise_in = [1000, -1000] * 320
    noise_out = [500, -500] * 320
    attenuation, used = noise_only_attenuation_db(noise_in, noise_out, [0, 0, 0, 0], rate, 0)
    assert used == 2 and attenuation is not None and 5.9 < attenuation < 6.2
    speech_attenuation, speech_used = speech_active_attenuation_db(noise_in, noise_out, [1, 1, 1, 1], rate, 0)
    assert speech_used == 2 and speech_attenuation is not None and 5.9 < speech_attenuation < 6.2
    assert rms_dbfs([0] * 10) <= -119.0
    synthetic_cases = [
        {"scenario": "a", "passed": True, "dimensions": {"motion": "static"}, "metrics": {"output_clip_fraction": 0.0, "output_dc_offset_dbfs": -100.0}},
        {"scenario": "a", "passed": False, "dimensions": {"motion": "moving"}, "metrics": {"output_clip_fraction": 0.01, "output_dc_offset_dbfs": -50.0}},
    ]
    policy = {"allowed_tiers": ["validation-grade"], "minimum_cases": 2, "required_scenarios": ["a"], "required_dimension_values": {"motion": ["static", "moving"]}, "aggregate": {"max_output_clip_fraction": 0.02}}
    summary, violations = policy_violations(policy, {"tier": "validation-grade", "sealed_data": True, "sources": [], "cases": [{"split": "validation"}, {"split": "validation"}]}, synthetic_cases)
    assert summary["scenario_pass_rate"]["a"] == 0.5 and not violations
    print("validation evaluator self-test: OK")
'''
text = replace_region(text, "def self_test(", "def main(", self_test_fn)

text = text.replace(
    '    parser.add_argument("--source-revision")\n',
    '    parser.add_argument("--source-revision")\n    parser.add_argument("--source-manifest", type=Path)\n',
    1,
)
text = text.replace(
    '    args.output.parent.mkdir(parents=True, exist_ok=True)\n',
    '    if args.source_manifest is not None:\n        report["bindings"]["source_manifest_sha256"] = sha256_file(args.source_manifest)\n    args.output.parent.mkdir(parents=True, exist_ok=True)\n',
    1,
)
text = text.replace(
    '        write_evidence(args.evidence_manifest, args.output, args.corpus, args.policy, args.dataset_lock)\n',
    '        write_evidence(args.evidence_manifest, args.output, args.corpus, args.policy, args.dataset_lock, args.source_manifest)\n',
    1,
)
path.write_text(text, encoding="utf-8")

split = Path("validation/tools/split_holdout.py")
source = split.read_text(encoding="utf-8")
partition_block = r'''
def stratification_value(case: dict, stratify: str | None) -> str:
    if stratify in (None, "none"):
        return "all"
    if stratify == "scenario":
        return str(case.get("scenario", "unknown"))
    if stratify == "dataset":
        source = case.get("source", {})
        return str(source.get("dataset_id", "unknown"))
    raise ValueError(f"unsupported stratification: {stratify}")


def partition_cases(cases: list[dict], key: bytes, holdout_percent: int,
                    stratify: str | None = None) -> tuple[list[dict], list[dict]]:
    validation_cases: list[dict] = []
    blind_cases: list[dict] = []
    groups: dict[str, list[tuple[int, dict]]] = {}
    for case in cases:
        identity = canonical_identity(case).encode("utf-8")
        digest = hmac.new(key, identity, hashlib.sha256).digest()
        bucket = int.from_bytes(digest[:4], "big") % 100
        groups.setdefault(stratification_value(case, stratify), []).append((bucket, case))
    for _group, rows in sorted(groups.items()):
        ordered = sorted(rows, key=lambda item: (item[0], canonical_identity(item[1])))
        group_validation: list[dict] = []
        group_blind: list[dict] = []
        for bucket, case in ordered:
            target = group_blind if bucket < holdout_percent else group_validation
            copied = dict(case)
            copied["split"] = "blind" if target is group_blind else "validation"
            target.append(copied)
        if stratify not in (None, "none") and len(ordered) >= 2:
            if not group_blind:
                moved = group_validation.pop(0)
                moved["split"] = "blind"
                group_blind.append(moved)
            if not group_validation:
                moved = group_blind.pop(-1)
                moved["split"] = "validation"
                group_validation.append(moved)
        validation_cases.extend(group_validation)
        blind_cases.extend(group_blind)
    validation_cases.sort(key=lambda case: case["case_id"])
    blind_cases.sort(key=lambda case: case["case_id"])
    return validation_cases, blind_cases
'''
source = replace_region(source, "def partition_cases(", "def self_test(", partition_block)
new_self = r'''
def self_test() -> None:
    key = b"audio-pipeline-holdout-self-test-key"
    cases = [
        {"case_id": f"case-{index:03d}", "scenario": f"s{index % 4}",
         "source": {"source_id": f"case-{index:03d}", "dataset_id": f"d{index % 3}"}}
        for index in range(160)
    ]
    expected_minima = {
        (100, 20): (60, 10),
        (100, 30): (60, 10),
        (160, 20): (100, 16),
        (160, 30): (100, 16),
    }
    for (count, percent), (min_validation, min_blind) in expected_minima.items():
        validation, blind = partition_cases(cases[:count], key, percent)
        assert len(validation) + len(blind) == count
        assert len(validation) >= min_validation, (count, percent, len(validation))
        assert len(blind) >= min_blind, (count, percent, len(blind))
        validation2, blind2 = partition_cases(cases[:count], key, percent)
        assert [item["case_id"] for item in validation] == [item["case_id"] for item in validation2]
        assert [item["case_id"] for item in blind] == [item["case_id"] for item in blind2]
    validation, blind = partition_cases(cases, key, 20, "scenario")
    for scenario in {case["scenario"] for case in cases}:
        assert any(case["scenario"] == scenario for case in validation)
        assert any(case["scenario"] == scenario for case in blind)
    dataset_validation, dataset_blind = partition_cases(cases, key, 20, "dataset")
    for dataset in {case["source"]["dataset_id"] for case in cases}:
        assert any(case["source"]["dataset_id"] == dataset for case in dataset_validation)
        assert any(case["source"]["dataset_id"] == dataset for case in dataset_blind)
    print("validation blind holdout self-test: OK")
'''
source = replace_region(source, "def self_test(", "def main(", new_self)
source = source.replace(
    '    parser.add_argument("--key-env", default="AP_VALIDATION_HOLDOUT_KEY")\n',
    '    parser.add_argument("--key-env", default="AP_VALIDATION_HOLDOUT_KEY")\n    parser.add_argument("--stratify", choices=("none", "scenario", "dataset"), default="none")\n',
    1,
)
source = source.replace(
    '    validation_cases, blind_cases = partition_cases(corpus["cases"], key, args.holdout_percent)\n',
    '    validation_cases, blind_cases = partition_cases(corpus["cases"], key, args.holdout_percent, args.stratify)\n',
    1,
)
source = source.replace(
    '                      "key_fingerprint": fingerprint}, sort_keys=True))\n',
    '                      "key_fingerprint": fingerprint, "stratify": args.stratify}, sort_keys=True))\n',
    1,
)
split.write_text(source, encoding="utf-8")

cmake = Path("CMakeLists.txt")
cmake_text = cmake.read_text(encoding="utf-8")
old_version = "project(audio_pipeline VERSION 2.0.1 LANGUAGES C)"
new_version = "project(audio_pipeline VERSION 2.1.0 LANGUAGES C)"
if old_version not in cmake_text:
    raise SystemExit("CMake v2.0.1 project declaration not found")
cmake.write_text(cmake_text.replace(old_version, new_version, 1), encoding="utf-8")

changelog = Path("CHANGELOG.md")
change = changelog.read_text(encoding="utf-8")
if not change.startswith("# 2.0.1\n"):
    raise SystemExit("unexpected CHANGELOG head")
entry = '''# 2.1.0

- Add a separate extended-real validation family without changing the established Compact100/Full160 public-validation baselines.
- Add a license-aware extended dataset catalog with commercial, conditional, research-only, and catalog-only usage classes; research/NC/share-alike data cannot satisfy commercial or shipping evidence gates.
- Hash-bind every selected real audio input through normalized source manifests and verify those SHA-256 bindings again before corpus construction.
- Add real far-field/moving-source RealMAN cases, measured-room BUT ReverbDB + Mini LibriSpeech + MUSAN NS/BF cases, environmental hard-negative cases, and optional VOiCES/AMI/ICSI meeting/far-field stress suites.
- Add research-only AISHELL-4, permissive-filtered FSD50K and WHAM stress paths while keeping CC-BY-ND ACE catalog-only and non-transforming.
- Extend validation metrics with clipping, DC offset, output level drift, VAD precision/recall/FPR/FNR, speech-active attenuation, tail percentiles, scenario pass rates and dimension-coverage gates.
- Stratify blind HMAC holdouts by scenario or dataset so required acoustic families cannot disappear from the hidden partition by chance.
- Keep extended-real validation non-authoritative for product shipping: real DUT HIL, product acoustic/thermal/power evidence and 72 h certification remain separate mandatory gates.

'''
changelog.write_text(entry + change, encoding="utf-8")

arch = Path("scripts/check-architecture.sh")
arch_text = arch.read_text(encoding="utf-8")
marker = "# extended-real-validation-contract-v1"
if marker not in arch_text:
    arch_text += r'''

# extended-real-validation-contract-v1
python3 validation/tools/extended_dataset_lock.py self-test
python3 validation/tools/prepare_extended_validation.py self-test
python3 validation/tools/build_extended_real_corpus.py --self-test
python3 validation/tools/extended_dataset_lock.py validate --catalog validation/extended.datasets.lock.json
python3 validation/tools/split_holdout.py --self-test
python3 - <<'PY'
import json
from pathlib import Path
catalog = json.loads(Path('validation/extended.datasets.lock.json').read_text())
by_id = {item['id']: item for item in catalog['datasets']}
for profile in ('commercial-core', 'commercial-plus'):
    assert all(by_id[item]['usage_class'] == 'commercial-validation' for item in catalog['profiles'][profile]), profile
assert by_id['wham']['usage_class'] == 'research-only'
assert by_id['aishell4']['usage_class'] == 'conditional'
assert by_id['ace-challenge']['transforms_allowed'] is False
for name in (
    'validation-extended-real-core.json',
    'validation-extended-real-core-blind.json',
    'validation-extended-real-plus.json',
    'validation-extended-real-plus-blind.json',
    'validation-extended-real-research.json',
):
    policy = json.loads((Path('validation/policies') / name).read_text())
    assert policy['schema_version'] == 1
    assert policy['minimum_cases'] > 0
print('extended-real validation contracts: OK')
PY
'''
    arch.write_text(arch_text, encoding="utf-8")

print("v2.1.0 extended-real evaluator migration applied")
