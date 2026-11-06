#!/usr/bin/env python3
"""Retain dual-use profile replay and canonical descriptive quality metrics.

No acoustic thresholds are introduced or relaxed. Optional legacy comparison
is a CLI-only byte-equivalence check against the frozen pre-change processor;
do not use that comparison to judge subsequent DSP algorithm changes.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT / "validation/tools", ROOT / "tests/validation"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import build_dualmic_profile_corpus as builder
import dualmic_profile_support as support
import render_corr_exact
import run_validation
import run_validation_engine as engine
from authority import load_authority

BASE_REVISION = "438fe09d79ff768306c00573849517bcd91cbc6e"
RUN_BUDGET_SECONDS = 300
BOUND_SOURCES = (
    "CMakeLists.txt",
    "examples/process_pcm.c", "tests/test_process_pcm_profiles.c",
    "tests/validation/dualmic_profile_support.py",
    "tests/validation/build_dualmic_profile_corpus.py",
    "tests/validation/run_dualmic_profile_replay.py",
    "tests/validation/quality_metric_support.py",
    "tests/validation/build_quality_validation_corpus.py",
    "validation/tools/build_validation_corpus.py",
    "validation/tools/run_validation.py", "validation/tools/run_validation_engine.py",
    "validation/tools/stage_profile_support.py", "validation/tools/render_corr_exact.py",
    "validation/research-authority.json",
    "docs/research/frontend-evolution-v1/DUALMIC_PROFILE_REPLAY_V1_IMPLEMENTATION_FREEZE.zh-CN.md",
)


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def source_bindings(processor: Path, corpus_path: Path) -> dict:
    return {
        "processor_sha256": engine.sha256_file(processor),
        "corpus_sha256": engine.sha256_file(corpus_path),
        "source_manifest_sha256": engine.sha256_file(corpus_path.parent / "source-manifest.json"),
        "source_files": {name: engine.sha256_file(ROOT / name) for name in BOUND_SOURCES},
    }


def verify_source_revision(revision: str) -> None:
    """Reject a configured Git label attached to different working source."""
    for name in BOUND_SOURCES:
        subprocess.run(["git", "cat-file", "-e", f"{revision}:{name}"], cwd=ROOT,
                       check=True, capture_output=True, timeout=30)
    subprocess.run(["git", "diff", "--quiet", revision, "--", "src", "include",
                    *BOUND_SOURCES], cwd=ROOT, check=True, capture_output=True, timeout=30)


def build_identity(processor: Path, revision: str) -> dict:
    # The existing linked build-info executable is built alongside the PCM
    # processor. Bind both actual binaries rather than inventing board identity.
    dump = processor.with_name("ap_build_info_dump")
    completed = subprocess.run([str(dump)], check=True, capture_output=True, text=True, timeout=30)
    identity = dict(line.split("=", 1) for line in completed.stdout.splitlines() if "=" in line)
    if identity.get("source_revision") != revision:
        raise ValueError("linked build source does not match --source-revision")
    return {"values": identity, "dump_sha256": engine.sha256_file(dump),
            "processor_sha256": engine.sha256_file(processor)}


def preset_tuning(processor: Path, profile: str | None) -> tuple[dict, str]:
    command = [str(processor)]
    if profile is not None:
        command += ["--profile", profile]
    command.append("--print-default-tuning")
    completed = subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)
    payload = json.loads(completed.stdout)
    if (set(payload) != {"aec_mu", "ns_floor", "agc_target_dbfs", "limiter_dbfs"}
            or any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in payload.values())):
        raise ValueError("processor default-tuning readback drifted")
    return payload, completed.stdout


def compare_artifacts(left: Path, right: Path) -> dict:
    result = {}
    for filename in ("out.pcm", "metrics.jsonl"):
        first, second = left / filename, right / filename
        first_hash, second_hash = engine.sha256_file(first), engine.sha256_file(second)
        result[filename] = {"left_sha256": first_hash, "right_sha256": second_hash,
                            "byte_identical": first.read_bytes() == second.read_bytes()}
    result["passed"] = all(result[name]["byte_identical"] for name in ("out.pcm", "metrics.jsonl"))
    return result


def run(processor: Path, corpus_path: Path, output: Path, revision: str,
        baseline: Path | None = None) -> dict:
    started = time.monotonic()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("--source-revision must be an exact lower-case 40-hex commit")
    verify_source_revision(revision)
    corpus = builder.verify(corpus_path)
    authority = load_authority()
    run_validation.validate_corpus_shape(corpus, authority)
    output.mkdir(parents=True, exist_ok=False)
    bindings = source_bindings(processor, corpus_path)
    identity = build_identity(processor, revision)
    defaults = {profile: preset_tuning(processor, profile)[0] for profile in builder.PROFILES}
    _, legacy_tuning = preset_tuning(processor, None)
    _, explicit_tuning = preset_tuning(processor, "call")
    if legacy_tuning != explicit_tuning:
        raise ValueError("default CALL tuning JSON is not byte-identical")
    write_json(output / "build-identity.json", identity)
    write_json(output / "default-tuning.json", defaults)
    write_json(output / "input-bindings.json", bindings)
    retained_input = output / "input"
    retained_input.mkdir()
    source_manifest = json.loads((corpus_path.parent / "source-manifest.json").read_text())
    for relative in ["corpus.json", "source-manifest.json", *source_manifest["files"]]:
        destination = retained_input / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(corpus_path.parent / relative, destination)
    replay_corpus_path = retained_input / "corpus.json"
    builder.verify(replay_corpus_path)
    if baseline is not None:
        write_json(output / "baseline-build-identity.json", build_identity(baseline, BASE_REVISION))
        _, baseline_tuning = preset_tuning(baseline, None)
        if baseline_tuning != legacy_tuning:
            raise ValueError("CLI-only baseline default-tuning JSON changed")

    replay_root = output / "replay"
    semantics = support.validation_semantics(retain_root=replay_root)
    original_invoke = run_validation.canonical_evaluation_semantics().invoke
    results, failures, comparisons = [], [], []

    def check_budget() -> None:
        if time.monotonic() - started >= RUN_BUDGET_SECONDS:
            raise TimeoutError("frozen replay budget exhausted")

    for case in corpus["cases"]:
        case_id = case["case_id"]
        try:
            check_budget()
            result = semantics.evaluate_case(processor, replay_corpus_path, case, semantics.evaluation)
            result["output_contract"] = json.loads((replay_root / case_id / "continuity.json").read_text())
            results.append(result)
            if baseline is not None and case["pipeline_profile"] == "call":
                legacy_case = copy.deepcopy(case)
                legacy_case.pop("pipeline_profile")
                legacy_work = support.case_directory(output / "candidate-legacy", case_id)
                base_work = support.case_directory(output / "baseline-legacy", case_id)
                check_budget()
                legacy_output, trace, inputs = original_invoke(processor, legacy_case, replay_corpus_path, legacy_work)
                support.continuity(legacy_case, legacy_output, trace, inputs)
                check_budget()
                base_output, trace, inputs = original_invoke(baseline, legacy_case, replay_corpus_path, base_work)
                support.continuity(legacy_case, base_output, trace, inputs)
                old_vs_new = compare_artifacts(base_work, legacy_work)
                default_vs_explicit = compare_artifacts(legacy_work, replay_root / case_id)
                comparisons.append({"case_id": case_id, "base_vs_candidate_default": old_vs_new,
                                    "candidate_default_vs_call": default_vs_explicit})
                if not old_vs_new["passed"] or not default_vs_explicit["passed"]:
                    failures.append({"case_id": case_id, "error": "CLI-only byte-equivalence failure"})
        except (ValueError, OSError, subprocess.SubprocessError, TimeoutError) as exc:
            failures.append({"case_id": case_id, "error": f"{type(exc).__name__}: {exc}"})
        # Retain partial results before another case can fail or the process is
        # interrupted; never overwrite a prior run directory.
        write_json(output / "progress.json", {"completed_cases": len(results),
                                              "failures": failures, "comparisons": comparisons})

    if len(results) != len(corpus["cases"]):
        failures.append({"error": "incomplete case coverage"})
    if baseline is not None and len(comparisons) != len(builder.SEEDS) * len(builder.SCENARIOS):
        failures.append({"error": "incomplete CLI-only baseline comparison"})
    if source_bindings(processor, corpus_path) != bindings:
        failures.append({"error": "source/processor identity changed during replay"})
    if time.monotonic() - started > RUN_BUDGET_SECONDS:
        failures.append({"error": "frozen replay budget exceeded"})
    try:
        builder.verify(corpus_path)
        builder.verify(replay_corpus_path)
    except (ValueError, OSError) as exc:
        failures.append({"error": f"post-replay source verification: {exc}"})

    # Reuse only existing metric aggregation. This local policy checks coverage,
    # not a new acoustic success threshold; old policies are separately intact.
    descriptive_policy = {"allowed_tiers": ["regression"], "minimum_cases": 42,
                          "required_scenarios": list(builder.SCENARIOS)}
    summary, coverage = run_validation.policy_violations(
        descriptive_policy, corpus, results, authority,
        engine_policy_violations=semantics.engine_policy_violations,
    )
    failures.extend(coverage)
    profile_summaries = {}
    for profile in builder.PROFILES:
        selected = [item for item in results if item["dimensions"]["pipeline_profile"] == profile]
        profile_summaries[profile], _ = semantics.engine_policy_violations(
            {"allowed_tiers": ["regression"]}, corpus, selected)
    report = {
        "schema_version": 1, "experiment": builder.EXPERIMENT,
        "source_revision": revision,
        "result": "FAIL" if failures else "REGRESSION_REPLAY_COMPLETE",
        "quality_decision": "DESCRIPTIVE_ONLY", "acoustic_thresholds_applied": False,
        "promotion_allowed": False, "data_role": "regression",
        "not_run": ["KWS_FAR_FRR", "ASR", "subjective_intercom_quality", "real_dualmic_room", "physical_SSC305"],
        "elapsed_seconds": time.monotonic() - started,
        "bindings": {**bindings, **render_corr_exact.report_bindings(Path(engine.__file__))},
        "build_identity": identity, "default_tuning_readback": defaults,
        "canonical_summary": summary, "profile_summaries": profile_summaries,
        "cases": results, "cli_only_baseline_comparisons": comparisons, "failures": failures,
    }
    write_json(output / "report.json", report)
    write_json(output / "artifact-manifest.json", {
        "schema_version": 1,
        "files": {str(path.relative_to(output)): {"sha256": engine.sha256_file(path),
                                                  "size_bytes": path.stat().st_size}
                  for path in sorted(output.rglob("*")) if path.is_file()},
    })
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processor", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--baseline-processor", type=Path,
                        help="Optional exact pre-change processor for CLI-only byte-equivalence")
    args = parser.parse_args()
    report = run(args.processor.resolve(), args.corpus.resolve(), args.output.resolve(),
                 args.source_revision, args.baseline_processor.resolve() if args.baseline_processor else None)
    print(json.dumps({"result": report["result"], "quality_decision": report["quality_decision"],
                      "cases": len(report["cases"]),
                      "baseline_pairs": len(report["cli_only_baseline_comparisons"]),
                      "failures": report["failures"], "report": str(args.output / "report.json")}, sort_keys=True))
    return 1 if report["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
