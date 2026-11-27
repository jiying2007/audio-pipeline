#!/usr/bin/env python3
"""Package failed validation cases with canonical PCM and invocation semantics."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "validation" / "tools"
sys.path.insert(0, str(TOOLS))
import run_validation_engine as engine
import stage_profile_support

INPUT_KEYS = ("mic_audio", "render_audio", "clean_near_audio", "echo_audio", "vad_labels")
INVOCATION_SOURCES = ("run_validation_engine.py", "stage_profile_support.py")

# Keep the original canonical implementations in the artifact: replay must not
# depend on a future checkout or a second, hand-maintained processor command.
REPLAY_PY = '''#!/usr/bin/env python3
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
root = Path(__file__).resolve().parent
if len(sys.argv) != 2:
    raise SystemExit("usage: reproduce.py PROCESSOR")
manifest = json.loads((root / "input-manifest.json").read_text(encoding="utf-8"))
for name, digest in manifest["files"].items():
    actual = hashlib.sha256()
    with (root / name).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            actual.update(chunk)
    if actual.hexdigest() != digest:
        raise SystemExit("replay file hash mismatch: " + name)
sys.path.insert(0, str(root / "canonical"))
import run_validation_engine as engine
import stage_profile_support
case_path = root / "case.json"
case = json.loads(case_path.read_text(encoding="utf-8"))
try:
    stage_profile_support.build_invoke(engine)(
        Path(sys.argv[1]).resolve(), case, case_path, root)
except subprocess.CalledProcessError as exc:
    raise SystemExit(exc.returncode)
'''
REPLAY_SH = '''#!/bin/sh
set -eu
exec "${PYTHON:-python3}" "$(dirname "$0")/reproduce.py" "${PROCESSOR:-./ap_process_pcm}"
'''


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def failed_cases(corpus: dict, report: dict) -> list[tuple[dict, dict]]:
    cases = {}
    for case in corpus["cases"]:
        identity = case["case_id"]
        if not isinstance(identity, str) or not identity or identity in cases:
            raise ValueError("corpus case_id values must be non-empty and unique")
        cases[identity] = case
    failed = []
    seen = set()
    for result in report["cases"]:
        identity = result["case_id"]
        if identity not in cases or identity in seen:
            raise ValueError(f"unknown or duplicate report case_id: {identity}")
        seen.add(identity)
        if not isinstance(result.get("passed"), bool):
            raise ValueError(f"report passed must be boolean: {identity}")
        if not result["passed"]:
            if identity in {".", ".."} or Path(identity).name != identity or "\\" in identity:
                raise ValueError(f"unsafe replay case_id: {identity}")
            failed.append((cases[identity], result))
    return failed


def stage_inputs(corpus_path: Path, source_case: dict, root: Path) -> tuple[dict, dict]:
    """Keep role-separated originals and stage processor PCM with the evaluator."""
    local_case = json.loads(json.dumps(source_case))
    rate = source_case["sample_rate_hz"]
    channels = source_case["mic_channels"]
    if (type(rate) is not int or rate not in engine.SUPPORTED_RATES
            or type(channels) is not int or channels not in (1, 2)):
        raise ValueError(f"unsupported geometry in {source_case['case_id']}")
    profile = source_case.get("processor_profile", "default")
    if profile not in stage_profile_support.SUPPORTED_CAPTURE_PROFILES:
        raise ValueError("unsupported processor_profile")
    control = source_case.get("control", {})
    if not isinstance(control, dict):
        raise ValueError("control must be an object")
    for name in ("echo_path_change_frame", "discontinuity_frame",
                 "discontinuity_flags", "discontinuity_lost_frames"):
        if name in control:
            int(control[name])
    if not source_case.get("mic_audio"):
        raise ValueError("mic_audio is required")
    (root / "pcm").mkdir()
    inputs = {}
    for key in INPUT_KEYS:
        value = source_case.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not value:
            raise ValueError(f"invalid input path: {key}")
        # Keep the declared suffix, including when the source is a symlink:
        # canonical decoding uses that path's suffix, not the target's name.
        source = engine.resolve(corpus_path, value)
        original = root / "original" / key / source.name
        original.parent.mkdir(parents=True)
        original_sha = engine.sha256_file(source)
        shutil.copy2(source, original)
        if engine.sha256_file(original) != original_sha:
            raise ValueError(f"input changed while copying: {source}")
        binding = {"source_path": value, "original_path": original.relative_to(root).as_posix(),
                   "original_sha256": original_sha}
        if key == "vad_labels":
            engine.load_labels(original)
            local_case[key] = binding["original_path"]
        else:
            count = channels if key == "mic_audio" else 1
            samples, pcm = engine.stage_audio(original, rate, count, root / "pcm", key + ".pcm")
            if not samples or len(samples) % count:
                raise ValueError(f"empty or incomplete PCM channel frame: {key}")
            if original.suffix.lower() == ".wav":
                with wave.open(str(original), "rb") as handle:
                    if len(samples) != handle.getnframes() * count:
                        raise ValueError(f"truncated WAV payload: {key}")
            local_case[key] = pcm.relative_to(root).as_posix()
            binding.update({"pcm_path": local_case[key], "pcm_sha256": engine.sha256_file(pcm),
                            "sample_rate_hz": rate, "channels": count,
                            "sample_frames": len(samples) // count})
        inputs[key] = binding
    return local_case, inputs


def package(corpus_path: Path, report_path: Path, destination: Path,
            processor: Path | None) -> int:
    corpus_path = corpus_path.resolve()
    report_path = report_path.resolve()
    destination = destination.resolve()
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    failed = failed_cases(corpus, report)
    bindings = {"corpus_sha256": engine.sha256_file(corpus_path),
                "report_sha256": engine.sha256_file(report_path)}
    report_bindings = report.get("bindings", {})
    if not isinstance(report_bindings, dict):
        raise ValueError("report bindings must be an object")
    report_corpus_sha = report_bindings.get("corpus_sha256")
    if report_corpus_sha is not None and report_corpus_sha != bindings["corpus_sha256"]:
        raise ValueError("report corpus_sha256 does not match the supplied corpus")
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise ValueError("reproducer destination must be empty; refusing to overwrite evidence")
    shutil.copy2(report_path, destination / "report.json")
    shutil.copy2(corpus_path, destination / "source-corpus.json")
    replay_failures = 0
    for source_case, result in failed:
        root = destination / result["case_id"]
        root.mkdir()
        local_case, inputs = stage_inputs(corpus_path, source_case, root)
        write_json(root / "case.json", local_case)
        write_json(root / "source-case.json", source_case)
        write_json(root / "failure.json", result)
        (root / "canonical").mkdir()
        for name in INVOCATION_SOURCES:
            shutil.copy2(TOOLS / name, root / "canonical" / name)
        (root / "reproduce.py").write_text(REPLAY_PY, encoding="utf-8")
        (root / "reproduce.sh").write_text(REPLAY_SH, encoding="utf-8")
        (root / "reproduce.sh").chmod(0o755)
        write_json(root / "input-manifest.json", {
            "schema_version": 1, "case_id": result["case_id"], "bindings": bindings,
            "inputs": inputs,
            "invocation": "stage_profile_support.build_invoke(run_validation_engine)",
            "files": {path.relative_to(root).as_posix(): engine.sha256_file(path)
                      for path in sorted(root.rglob("*")) if path.is_file()},
        })
        if processor:
            proc = subprocess.run([sys.executable, str(root / "reproduce.py"), str(processor.resolve())],
                                  text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            (root / "replay.log").write_text(proc.stdout or "", encoding="utf-8")
            (root / "replay-returncode.txt").write_text(str(proc.returncode) + "\n", encoding="utf-8")
            replay_failures += int(proc.returncode != 0)
    print(json.dumps({"failed_cases": len(failed), "destination": str(destination),
                      "replay_failures": replay_failures}, sort_keys=True))
    return 1 if replay_failures else 0


def self_test() -> None:
    subprocess.run([sys.executable, str(ROOT / "tests/validation/test_validation_reproducer.py")],
                   check=True)
    print("validation reproducer self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--processor", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.corpus or not args.report or not args.destination:
        parser.error("--corpus, --report and --destination are required")
    try:
        return package(args.corpus, args.report, args.destination, args.processor)
    except (OSError, ValueError, KeyError, TypeError, wave.Error, EOFError) as exc:
        parser.exit(1, f"validation reproducer: {str(exc) or type(exc).__name__}\n")


if __name__ == "__main__":
    raise SystemExit(main())
