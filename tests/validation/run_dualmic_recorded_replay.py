#!/usr/bin/env python3
"""Execute and read back 56 recorded-speech C2 cases through canonical metrics.

Actual PCM and anonymous WAV options are retained. Completion is measurement
integrity, never an acoustic winner, human rating, real-room or silicon claim.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import wave

import build_dualmic_recorded_corpus as builder
import dualmic_profile_support as support
import run_dualmic_profile_replay as existing
from authority import load_authority
from contracts import load_json, require
import run_validation
import run_validation_engine as engine

ROOT = builder.ROOT
BUDGET = 300
BOUND_SOURCES = tuple(dict.fromkeys((*existing.BOUND_SOURCES,
    "tests/validation/build_dualmic_recorded_corpus.py",
    "tests/validation/run_dualmic_recorded_replay.py",
    "tests/validation/test_dualmic_recorded_replay.py",
    "tests/validation/frontend_evolution/speech_spatial.py",
    "tests/validation/frontend_evolution/speech_source.py",
    "tests/validation/frontend_evolution/contracts.py",
    ".github/research/frontend-evolution-v1/speech-spatial-v1.json",
    builder.ADMISSION, builder.PLAN)))
NOT_RUN = ["Chinese_KWS_FAR_FRR", "ASR", "human_listening", "real_dualmic_room",
           "physical_SSC305", "real_network_end_to_end"]
write_json = builder.write_json


def verify_revision(revision: str) -> None:
    require(re.fullmatch(r"[0-9a-f]{40}", revision) is not None, "exact source SHA required")
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                     text=True, timeout=10).strip()
    require(actual == revision, "checked-out and execution source differ")
    for name in BOUND_SOURCES:
        subprocess.run(["git", "cat-file", "-e", f"{revision}:{name}"], cwd=ROOT,
                       check=True, capture_output=True, timeout=10)
    subprocess.run(["git", "diff", "--quiet", revision, "--", "src", "include", *BOUND_SOURCES],
                   cwd=ROOT, check=True, capture_output=True, timeout=10)


def bindings(processor: Path, corpus_path: Path) -> dict:
    return {"processor_sha256": engine.sha256_file(processor),
            "build_info_sha256": engine.sha256_file(processor.with_name("ap_build_info_dump")),
            "corpus_sha256": engine.sha256_file(corpus_path),
            "source_manifest_sha256": engine.sha256_file(corpus_path.parent / "source-manifest.json"),
            "source_files": {name: engine.sha256_file(ROOT / name) for name in BOUND_SOURCES}}


def finite(value: object) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(finite(item) for item in value.values())
    if isinstance(value, list):
        return all(finite(item) for item in value)
    return True


def summaries(corpus: dict, results: list[dict]) -> tuple[dict, dict, list]:
    semantics = support.validation_semantics()
    policy = {"allowed_tiers": ["regression"], "minimum_cases": 56,
              "required_scenarios": list(builder.SCENARIOS)}
    summary, violations = run_validation.policy_violations(
        policy, corpus, results, load_authority(),
        engine_policy_violations=semantics.engine_policy_violations)
    profiles = {}
    for profile in builder.PROFILES:
        selected = [row for row in results if row["dimensions"]["pipeline_profile"] == profile]
        profiles[profile], _ = semantics.engine_policy_violations(
            {"allowed_tiers": ["regression"]}, corpus, selected)
    return summary, profiles, violations


def listening_layout(corpus: dict) -> list[dict]:
    stems = {row["case_id"].rsplit("-", 1)[0] for row in corpus["cases"]}
    digest = lambda name: hashlib.sha256((builder.EXPERIMENT + ":" + name).encode()).hexdigest()
    layout = []
    for index, stem in enumerate(sorted(stems, key=lambda x: digest("trial:" + x)), 1):
        labels = sorted(("raw-mic0", "call", "assistant"),
                        key=lambda x: digest("option:" + stem + ":" + x))
        layout.append({"trial": f"trial-{index:02d}", "stem": stem,
                       "options": [{"option": chr(65 + i), "identity": label,
                                    "wav": f"trial-{index:02d}-{chr(65 + i)}.wav"}
                                   for i, label in enumerate(labels)]})
    return layout


def listening_payload(root: Path, corpus: dict, stem: str, identity: str) -> bytes:
    if identity == "raw-mic0":
        row = next(r for r in corpus["cases"] if r["case_id"] == stem + "-call")
        return builder.pcm(builder.samples((root / "input" / row["mic_audio"]).read_bytes())[::2])
    return (root / "replay" / (stem + "-" + identity) / "out.pcm").read_bytes()


def export_listening(root: Path, corpus: dict) -> dict:
    directory = root / "listening"
    directory.mkdir()
    trials, keys = [], []
    for item in listening_layout(corpus):
        trial = {"trial": item["trial"], "options": []}
        for option in item["options"]:
            payload = listening_payload(root, corpus, item["stem"], option["identity"])
            require(len(payload) == builder.SAMPLES * 2, "listening PCM length mismatch")
            with wave.open(str(directory / option["wav"]), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(builder.RATE)
                output.writeframes(payload)
            trial["options"].append({"option": option["option"], "file": option["wav"]})
            keys.append({"trial": item["trial"], "stem": item["stem"], **option,
                         "pcm_sha256": hashlib.sha256(payload).hexdigest()})
        trials.append(trial)
    write_json(directory / "trials.json", {"human_listening": "NOT_RUN", "trials": trials,
        "fixed_playback_gain": 1.0, "output_normalization": False,
        "anonymous_options_only_not_a_completed_blind_study": True})
    write_json(root / "listening-key.json", {"experiment": builder.EXPERIMENT, "options": keys})
    for name in ("LICENSE.TXT", "ATTRIBUTION.txt", "README.TXT", "SPEAKERS.TXT"):
        shutil.copyfile(root / "input/source" / name, directory / name)
    (directory / "LISTENING_GUIDE.txt").write_text(
        "These 28 trials contain original mic0, CALL and ASSISTANT options in a fixed anonymous order.\n"
        "The WAV PCM is unchanged: no output loudness normalization or truncation. Keep player volume fixed.\n"
        "Do not open the separate listening-key.json while comparing anonymous options.\n"
        "No human ratings were collected: human_listening=NOT_RUN. No MOS or subjective improvement is claimed.\n"
        "Actual English LibriSpeech recordings, CC BY 4.0; original attribution and notices are included.\n"
        "Derivatives: fixed four-second excerpts, common pair gain, zero placement, simulated two-mic/echo, "
        "and full CALL/ASSISTANT frontend processing. Not actual room or hardware recordings.\n"
        "Waveform level and the listener's actual acoustic playback level are distinct.\n", encoding="utf-8")
    return {"trials": 28, "wav_options": len(keys), "human_listening": "NOT_RUN",
            "output_normalization": False}


def verify_listening(root: Path, corpus: dict) -> dict:
    expected_keys, expected_trials = [], []
    for item in listening_layout(corpus):
        trial = {"trial": item["trial"], "options": []}
        for option in item["options"]:
            payload = listening_payload(root, corpus, item["stem"], option["identity"])
            with wave.open(str(root / "listening" / option["wav"]), "rb") as stream:
                require((stream.getnchannels(), stream.getsampwidth(), stream.getframerate(),
                         stream.getnframes(), stream.getcomptype()) ==
                        (1, 2, builder.RATE, builder.SAMPLES, "NONE"), "WAV geometry changed")
                require(stream.readframes(builder.SAMPLES + 1) == payload, "WAV level or PCM changed")
            trial["options"].append({"option": option["option"], "file": option["wav"]})
            expected_keys.append({"trial": item["trial"], "stem": item["stem"], **option,
                                  "pcm_sha256": hashlib.sha256(payload).hexdigest()})
        expected_trials.append(trial)
    require(load_json(root / "listening-key.json") ==
            {"experiment": builder.EXPERIMENT, "options": expected_keys}, "listening identity/key drift")
    require(load_json(root / "listening/trials.json") ==
            {"human_listening": "NOT_RUN", "trials": expected_trials, "fixed_playback_gain": 1.0,
             "output_normalization": False, "anonymous_options_only_not_a_completed_blind_study": True},
            "listening claims or trial coverage changed")
    for name in ("LICENSE.TXT", "ATTRIBUTION.txt", "README.TXT", "SPEAKERS.TXT"):
        require((root / "listening" / name).read_bytes() ==
                (root / "input/source" / name).read_bytes(), "listening notice changed")
    return {"trials": 28, "wav_options": len(expected_keys), "human_listening": "NOT_RUN",
            "output_normalization": False}


def run(processor: Path, corpus_path: Path, output: Path, revision: str) -> dict:
    started = time.monotonic()
    verify_revision(revision)
    corpus = builder.verify(corpus_path)
    run_validation.validate_corpus_shape(corpus, load_authority())
    output.mkdir(parents=True, exist_ok=False)
    before = bindings(processor, corpus_path)
    identity = existing.build_identity(processor, revision)
    defaults = {profile: existing.preset_tuning(processor, profile)[0] for profile in builder.PROFILES}
    require(existing.preset_tuning(processor, None)[1] == existing.preset_tuning(processor, "call")[1],
            "implicit and explicit CALL defaults changed")
    shutil.copytree(corpus_path.parent, output / "input")
    (output / "bin").mkdir()
    for name, original in (("ap_process_pcm", processor),
                           ("ap_build_info_dump", processor.with_name("ap_build_info_dump"))):
        shutil.copy2(original, output / "bin" / name)
    for name in BOUND_SOURCES:
        target = output / "source-tree" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    semantics = support.validation_semantics(retain_root=output / "replay")
    results, failures = [], []
    for case in corpus["cases"]:
        try:
            require(time.monotonic() - started < BUDGET, "frozen matrix wall budget exceeded")
            result = semantics.evaluate_case(processor, output / "input/corpus.json", case, semantics.evaluation)
            result["output_contract"] = load_json(output / "replay" / case["case_id"] / "continuity.json")
            trace_path = output / "replay" / case["case_id"] / "metrics.jsonl"
            require(finite([json.loads(line) for line in trace_path.read_text().splitlines()]),
                    "non-finite retained telemetry")
            require(finite(result), "non-finite case metric")
            require(not any(key.startswith("vad_") for key in result["metrics"]),
                    "unlabelled recordings cannot produce VAD accuracy/timing metrics")
            results.append(result)
        except (OSError, ValueError, subprocess.SubprocessError, TimeoutError) as error:
            failures.append({"case_id": case["case_id"], "error": type(error).__name__ + ": " + str(error)})
        write_json(output / "progress.json", {"completed_cases": len(results), "failures": failures})
        print(json.dumps({"completed_cases": len(results), "failures": len(failures)}), flush=True)
    require(time.monotonic() - started <= BUDGET, "frozen matrix wall budget exceeded")
    require(bindings(processor, corpus_path) == before, "source/binary changed during execution")
    verify_revision(revision)
    builder.verify(output / "input/corpus.json")
    summary, profiles, violations = summaries(corpus, results)
    failures.extend(violations)
    if len(results) != 56:
        failures.append({"error": "incomplete 56-case matrix"})
    listening = export_listening(output, corpus) if not failures else None
    elapsed = time.monotonic() - started
    if elapsed > BUDGET:
        failures.append({"error": "complete replay/listening packaging wall budget exceeded"})
    report = {"schema_version": 1, "experiment": builder.EXPERIMENT, "source_revision": revision,
              "result": "FAIL" if failures else "RECORDED_SPEECH_REPLAY_COMPLETE",
              "quality_decision": "DESCRIPTIVE_ONLY", "data_role": "regression",
              "acoustic_thresholds_applied": False, "promotion_allowed": False,
              "real_array_recording": False, "human_listening": "NOT_RUN", "not_run": NOT_RUN,
              "elapsed_seconds": elapsed, "bindings": before, "build_identity": identity,
              "default_tuning_readback": defaults, "processor_original_path": str(processor),
              "execution_root": str(output), "canonical_summary": summary, "profile_summaries": profiles,
              "cases": results, "listening_pack": listening, "failures": failures}
    write_json(output / "report.json", report)
    return report


def expected_command(report: dict, case: dict) -> list[str]:
    root = Path(report["execution_root"])
    work = root / "replay" / case["case_id"]
    command = [report["processor_original_path"], "--profile", case["pipeline_profile"],
               "--sample-rate", "16000", "--mic-channels", "2", "--strict-capture-frames",
               "--metrics-jsonl", str(work / "metrics.jsonl")]
    control = case["control"]
    if "echo_path_change_frame" in control:
        command += ["--echo-path-change-frame", str(control["echo_path_change_frame"])]
    if "discontinuity_frame" in control:
        command += ["--discontinuity-frame", str(control["discontinuity_frame"]),
                    "--discontinuity-flags", str(control["discontinuity_flags"]),
                    "--discontinuity-lost-frames", str(control["discontinuity_lost_frames"])]
    mic = str(root / "input" / case["mic_audio"])
    if case["render_audio"] is None:
        command += ["--capture-profile", "default", "--capture-only", mic, str(work / "out.pcm")]
    else:
        command += [mic, str(root / "input" / case["render_audio"]), str(work / "out.pcm")]
    return command


def seal(root: Path) -> None:
    write_json(root / "artifact-manifest.json", {"schema_version": 1,
        "files": {p.relative_to(root).as_posix(): {"sha256": engine.sha256_file(p),
                  "size_bytes": p.stat().st_size} for p in sorted(root.rglob("*"))
                  if p.is_file() and p != root / "artifact-manifest.json"}})


def verify(root: Path) -> dict:
    started = time.monotonic()
    report, phase = load_json(root / "report.json"), load_json(root / "execution-phase.json")
    require(report["experiment"] == builder.EXPERIMENT and
            report["result"] == "RECORDED_SPEECH_REPLAY_COMPLETE" and not report["failures"] and
            report["quality_decision"] == "DESCRIPTIVE_ONLY" and report["data_role"] == "regression" and
            report["promotion_allowed"] is False and report["acoustic_thresholds_applied"] is False and
            report["real_array_recording"] is False and report["human_listening"] == "NOT_RUN" and
            report["not_run"] == NOT_RUN and finite(report), "report authority/completion drift")
    require(phase["status"] == "COMPLETE" and phase["returncode"] == 0 and
            0 <= phase["elapsed_seconds"] <= BUDGET and 0 <= report["elapsed_seconds"] <= BUDGET,
            "replay budget/process did not complete")
    manifest = load_json(root / "artifact-manifest.json")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    require(actual == set(manifest["files"]) | {"artifact-manifest.json"}, "artifact file set changed")
    require(all(not p.is_symlink() for p in root.rglob("*")), "artifact links forbidden")
    for name, binding in manifest["files"].items():
        path = root / name
        require(path.stat().st_size == binding["size_bytes"] and
                engine.sha256_file(path) == binding["sha256"], "artifact hash changed: " + name)
    verify_revision(report["source_revision"])
    require(report["bindings"]["source_files"] ==
            {name: engine.sha256_file(ROOT / name) for name in BOUND_SOURCES}, "execution source drift")
    for name, digest in report["bindings"]["source_files"].items():
        require(engine.sha256_file(root / "source-tree" / name) == digest, "source snapshot changed")
    require(engine.sha256_file(root / "bin/ap_process_pcm") == report["bindings"]["processor_sha256"] and
            engine.sha256_file(root / "bin/ap_build_info_dump") == report["bindings"]["build_info_sha256"],
            "retained producer binary mismatch")
    require(report["build_identity"]["values"]["source_revision"] == report["source_revision"] and
            report["build_identity"]["processor_sha256"] == report["bindings"]["processor_sha256"] and
            report["build_identity"]["dump_sha256"] == report["bindings"]["build_info_sha256"],
            "producer identity/binary binding changed")
    corpus = builder.verify(root / "input/corpus.json")
    require(engine.sha256_file(root / "input/corpus.json") == report["bindings"]["corpus_sha256"] and
            engine.sha256_file(root / "input/source-manifest.json") == report["bindings"]["source_manifest_sha256"],
            "retained corpus binding changed")
    semantics = support.validation_semantics()

    def retained_invoke(processor, case, corpus_path, unused_work):
        directory = root / "replay" / case["case_id"]
        require(json.loads((directory / "command.json").read_text()) == expected_command(report, case),
                "actual processor command differs from frozen profile/event/config")
        execution = load_json(directory / "execution.json")
        require(execution.get("returncode") == 0 and 0 <= execution["elapsed_seconds"] <= 30,
                "processor did not complete within per-case budget")
        output = engine.read_raw_array(directory / "out.pcm")
        trace = [json.loads(line) for line in (directory / "metrics.jsonl").read_text().splitlines()]
        require(finite(trace), "non-finite retained telemetry")
        inputs = {"mic": engine.read_raw_array(root / "input" / case["mic_audio"]),
                  "render": (engine.read_raw_array(root / "input" / case["render_audio"])
                             if case["render_audio"] is not None else None)}
        require(support.continuity(case, output, trace, inputs) == load_json(directory / "continuity.json"),
                "output continuity changed")
        return output, trace, inputs

    measured = []
    evaluation = replace(semantics.evaluation, invoke=retained_invoke)
    for case in corpus["cases"]:
        row = semantics.evaluate_case(Path("unused-no-DSP-reexecution"), root / "input/corpus.json", case, evaluation)
        row["output_contract"] = load_json(root / "replay" / case["case_id"] / "continuity.json")
        measured.append(row)
    require(measured == report["cases"], "canonical per-case metric recomputation changed")
    summary, profiles, violations = summaries(corpus, measured)
    require(not violations and summary == report["canonical_summary"] and
            profiles == report["profile_summaries"], "canonical summary recomputation changed")
    require(verify_listening(root, corpus) == report["listening_pack"], "listening summary changed")
    elapsed = time.monotonic() - started
    require(elapsed <= BUDGET, "readback budget exceeded")
    return {"result": "RECORDED_SPEECH_EVIDENCE_VERIFIED", "files": len(actual), "cases": len(measured),
            "wav_options": 84, "elapsed_seconds": elapsed, "quality_decision": "DESCRIPTIVE_ONLY",
            "human_listening": "NOT_RUN", "DSP_reexecuted": False}


def supervise(args) -> int:
    started = time.monotonic()
    output = args.output.resolve()
    require(not output.exists() and not output.is_symlink(), "replay output must be fresh")
    output.parent.mkdir(parents=True, exist_ok=True)
    log = output.parent / (output.name + ".worker.log")
    command = [sys.executable, str(Path(__file__).resolve()), "--worker", "--processor",
               str(args.processor.resolve()), "--corpus", str(args.corpus.resolve()),
               "--output", str(output), "--source-revision", args.source_revision]
    status, returncode, error = "FAIL", None, None
    with log.open("xb") as stream:
        process = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            returncode = process.wait(timeout=max(0.1, BUDGET - 3 - (time.monotonic() - started)))
            status = "COMPLETE" if returncode == 0 else "FAIL"
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            returncode = process.wait(timeout=2)
            status, error = "TIMEOUT", "300-second whole-stage budget; cleanup reserve included"
    output.mkdir(parents=True, exist_ok=True)
    log.rename(output / "execution.log")
    phase = {"status": status, "returncode": returncode, "error": error,
             "budget_seconds": BUDGET, "elapsed_seconds": time.monotonic() - started,
             "command": command, "child_pid": process.pid, "terminal": process.poll() is not None}
    if phase["elapsed_seconds"] > BUDGET:
        phase["status"] = "TIMEOUT"
    write_json(output / "execution-phase.json", phase)
    seal(output)
    # Include the expensive full-payload sealing in the observed phase time.
    # Only the two small final metadata writes follow this observation.
    phase["elapsed_seconds"] = time.monotonic() - started
    if phase["elapsed_seconds"] > BUDGET:
        phase["status"] = "TIMEOUT"
    write_json(output / "execution-phase.json", phase)
    manifest = load_json(output / "artifact-manifest.json")
    phase_path = output / "execution-phase.json"
    manifest["files"]["execution-phase.json"] = {"sha256": engine.sha256_file(phase_path),
                                                   "size_bytes": phase_path.stat().st_size}
    write_json(output / "artifact-manifest.json", manifest)
    print(json.dumps(phase, sort_keys=True))
    return 0 if phase["status"] == "COMPLETE" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-revision")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.verify:
        print(json.dumps(verify(args.output.resolve()), sort_keys=True))
        return 0
    if args.processor is None or args.corpus is None or args.source_revision is None:
        parser.error("--processor, --corpus and --source-revision are required for execution")
    if args.worker:
        report = run(args.processor.resolve(), args.corpus.resolve(), args.output.resolve(), args.source_revision)
        return 1 if report["failures"] else 0
    return supervise(args)


if __name__ == "__main__":
    raise SystemExit(main())
