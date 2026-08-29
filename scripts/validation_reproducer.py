#!/usr/bin/env python3
"""Package failed validation cases into self-contained replay artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

AUDIO_KEYS = ("mic_audio", "render_audio", "clean_near_audio", "echo_audio", "vad_labels")


def resolve(corpus: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else corpus.parent / path


def command_for(processor: str, case: dict, directory: Path) -> list[str]:
    cmd = [processor, "--sample-rate", str(case["sample_rate_hz"]),
           "--mic-channels", str(case["mic_channels"]),
           "--metrics-jsonl", str(directory / "metrics.jsonl")]
    control = case.get("control", {})
    if "echo_path_change_frame" in control:
        cmd += ["--echo-path-change-frame", str(control["echo_path_change_frame"])]
    if "discontinuity_frame" in control:
        cmd += ["--discontinuity-frame", str(control["discontinuity_frame"]),
                "--discontinuity-flags", str(control.get("discontinuity_flags", 1)),
                "--discontinuity-lost-frames", str(control.get("discontinuity_lost_frames", 1))]
    mic = directory / Path(case["mic_audio"]).name
    render_value = case.get("render_audio")
    if render_value:
        cmd += [str(mic), str(directory / Path(render_value).name), str(directory / "output.pcm")]
    else:
        cmd += ["--capture-profile", case.get("processor_profile", "default"),
                "--capture-only", str(mic), str(directory / "output.pcm")]
    return cmd


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def package(corpus_path: Path, report_path: Path, destination: Path,
            processor: Path | None) -> int:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    cases = {case["case_id"]: case for case in corpus["cases"]}
    failed = [case for case in report.get("cases", []) if not case.get("passed", False)]
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for result in failed:
        source_case = dict(cases[result["case_id"]])
        root = destination / result["case_id"]
        root.mkdir(parents=True, exist_ok=True)
        local_case = json.loads(json.dumps(source_case))
        for key in AUDIO_KEYS:
            value = source_case.get(key)
            if not value:
                continue
            src = resolve(corpus_path, value)
            dst = root / src.name
            shutil.copy2(src, dst)
            local_case[key] = dst.name
        (root / "case.json").write_text(json.dumps(local_case, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (root / "failure.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        replay = command_for("${PROCESSOR:-./ap_process_pcm}", local_case, Path("."))
        script = "#!/bin/sh\nset -eu\n" + " ".join(
            item if item.startswith("${PROCESSOR") else shell_quote(str(item)) for item in replay
        ) + "\n"
        (root / "reproduce.sh").write_text(script, encoding="utf-8")
        (root / "reproduce.sh").chmod(0o755)
        if processor:
            proc = subprocess.run(command_for(str(processor.resolve()), local_case, root),
                                  cwd=root, text=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT)
            (root / "replay.log").write_text(proc.stdout or "", encoding="utf-8")
            if proc.returncode != 0:
                (root / "replay-returncode.txt").write_text(str(proc.returncode) + "\n", encoding="utf-8")
    print(json.dumps({"failed_cases": len(failed), "destination": str(destination)}, sort_keys=True))
    return 0


def self_test() -> None:
    assert shell_quote("a'b") == "'a'\\''b'"
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
    return package(args.corpus, args.report, args.destination, args.processor)


if __name__ == "__main__":
    raise SystemExit(main())
