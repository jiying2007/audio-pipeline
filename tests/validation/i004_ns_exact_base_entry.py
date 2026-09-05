#!/usr/bin/env python3
"""Run the I004 diagnostic against the exact verified baseline source tree.

The research branch may evolve measurement tooling and its frozen contract, but the
processor under test is always built from contract.base_sha in a detached worktree.
Any unexpected branch file change is fail-closed before execution. Dynamic-noise
failures are authoritative only after clean-speech VAD/NS preconditions pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IMPLEMENTATION = ROOT / "tests/validation/i004_ns_nonstationary_diagnostic.py"
ALLOWED_RESEARCH_FILES = {
    ".github/workflows/i004-ns-baseline-diagnostic.yml",
    "docs/program/iterations/I004.json",
    "tests/validation/i004_ns_exact_base_entry.py",
    "tests/validation/i004_ns_nonstationary_diagnostic.py",
}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def run(argv: list[str], cwd: Path | None = None, capture: bool = False) -> str:
    result = subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    return result.stdout.strip() if capture else ""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_research_scope(base_sha: str) -> tuple[str, list[str]]:
    require(re.fullmatch(r"[0-9a-f]{40}", base_sha) is not None, "invalid exact base SHA")
    head = run(["git", "rev-parse", "HEAD"], ROOT, True)
    merge_base = run(["git", "merge-base", "HEAD", base_sha], ROOT, True)
    require(merge_base == base_sha, f"research branch is not based on exact baseline: {merge_base}")
    changed = [line for line in run(["git", "diff", "--name-only", f"{base_sha}...HEAD"], ROOT, True).splitlines() if line]
    unexpected = sorted(set(changed) - ALLOWED_RESEARCH_FILES)
    require(not unexpected, "unexpected I004 research scope: " + ", ".join(unexpected))
    require(all(not path.startswith(("src/", "include/", "cmake/", "certification/")) for path in changed),
            "shipping DSP/API/build/certification scope must remain untouched")
    require("CMakeLists.txt" not in changed and "CHANGELOG.md" not in changed,
            "shipping build/version scope must remain untouched")
    return head, sorted(changed)


def load_labels(path: Path) -> list[int]:
    value = json.loads(path.read_text(encoding="utf-8"))
    labels = value.get("labels")
    require(isinstance(labels, list) and labels, "clean-anchor labels")
    return [int(item) for item in labels]


def clean_anchor(processor: Path, pcm: Path, labels_path: Path, profile: str, work: Path) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    out = work / "out.pcm"
    metrics_path = work / "metrics.jsonl"
    run([
        str(processor),
        "--sample-rate", "16000",
        "--mic-channels", "1",
        "--capture-only",
        "--capture-profile", profile,
        "--metrics-jsonl", str(metrics_path),
        str(pcm), str(out),
    ])
    metrics = [json.loads(line) for line in metrics_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    require(metrics, f"missing clean-anchor metrics: {profile}")
    labels = load_labels(labels_path)
    latency_frames = int(metrics[0].get("algorithmic_latency_ms", 0)) // 10
    warmup = 40
    tp = fn = fp = tn = 0
    probabilities: list[float] = []
    for row in metrics[warmup:]:
        frame = int(row["frame"])
        source = frame - latency_frames
        if source < 0 or source >= len(labels):
            continue
        actual = labels[source] != 0
        predicted = int(row["vad_active"]) != 0
        probabilities.append(float(row.get("vad_probability", 0.0)))
        tp += int(actual and predicted)
        fn += int(actual and not predicted)
        fp += int((not actual) and predicted)
        tn += int((not actual) and not predicted)
    return {
        "profile": profile,
        "algorithmic_latency_ms": int(metrics[0].get("algorithmic_latency_ms", 0)),
        "vad_recall": tp / max(1, tp + fn),
        "vad_false_positive_rate": fp / max(1, fp + tn),
        "vad_probability_mean": sum(probabilities) / max(1, len(probabilities)),
        "frames_scored": tp + fn + fp + tn,
    }


def apply_clean_preconditions(output: Path, processor: Path, contract: dict) -> dict:
    thresholds = contract.get("diagnostic_preconditions", {})
    min_vad = float(thresholds["min_clean_vad_isolated_recall"])
    min_ns = float(thresholds["min_clean_ns_isolated_recall"])
    anchors = []
    for seed in contract["seeds"]:
        source = output / "corpus" / f"seed-{seed}" / "ns-motor-ramp-speech"
        pcm = source / "clean.pcm"
        labels = source / "labels.json"
        for profile in ("vad-isolated", "ns-isolated"):
            result = clean_anchor(processor, pcm, labels, profile, output / "clean-anchors" / f"seed-{seed}" / profile)
            threshold = min_vad if profile == "vad-isolated" else min_ns
            result["minimum_recall"] = threshold
            result["passed"] = result["vad_recall"] >= threshold
            result["seed"] = seed
            anchors.append(result)
    failures = [
        {"seed": item["seed"], "profile": item["profile"], "vad_recall": item["vad_recall"],
         "minimum_recall": item["minimum_recall"]}
        for item in anchors if not item["passed"]
    ]
    value = {
        "schema_version": 1,
        "authority": "diagnostic-input-precondition-only",
        "thresholds": thresholds,
        "anchors": anchors,
        "failures": failures,
        "passed": not failures,
    }
    write_json(output / "diagnostic-preconditions.json", value)
    report_path = output / "baseline-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["diagnostic_preconditions"] = value
    if failures:
        report["decision"] = "DIAGNOSTIC_INPUT_INVALID_REVIEW_REQUIRED"
        report["next_step"] = "repair or replace diagnostic speech input before authorizing any NS candidate"
    write_json(report_path, report)
    return value


def refresh_manifest(output: Path, binding: dict) -> None:
    build = output / "build"
    processor = build / "ap_process_pcm"
    probe = build / "ns_probability_probe"
    if processor.is_file():
        binding["processor_sha256"] = sha256(processor)
    if probe.is_file():
        binding["ns_probability_probe_sha256"] = sha256(probe)
    if build.exists():
        shutil.rmtree(build)
    binding_path = output / "execution-binding.json"
    write_json(binding_path, binding)
    files = {
        str(path.relative_to(output)): sha256(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name not in {"SHA256SUMS", "evidence-manifest.json"}
    }
    write_json(output / "evidence-manifest.json", {
        "schema_version": 1,
        "baseline_source_sha": binding["baseline_source_sha"],
        "research_head_sha": binding["research_head_sha"],
        "files": files,
    })
    with (output / "SHA256SUMS").open("w", encoding="utf-8") as handle:
        for rel, digest in sorted(files.items()):
            handle.write(f"{digest}  {rel}\n")


def self_test() -> None:
    require(all(not path.startswith(("src/", "include/", "cmake/", "certification/"))
                for path in ALLOWED_RESEARCH_FILES), "allowed scope contains shipping path")
    require("CMakeLists.txt" not in ALLOWED_RESEARCH_FILES, "allowed scope contains CMakeLists")
    require(IMPLEMENTATION.name == "i004_ns_nonstationary_diagnostic.py", "implementation binding")
    synthetic = [{"frame": 0, "algorithmic_latency_ms": 0, "vad_probability": 1.0, "vad_active": 1}]
    require(math.isfinite(float(synthetic[0]["vad_probability"])), "anchor metric sanity")
    print(json.dumps({"result": "PASS", "authority": "exact-base-entry-and-input-preconditions-only"}, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    require(args.contract is not None and args.output is not None, "contract/output required")
    contract_path = args.contract.resolve()
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    require(contract.get("schema_version") == 1 and contract.get("iteration_id") == "I004",
            "I004 contract identity")
    base_sha = contract.get("base_sha")
    research_head, changed_files = validate_research_scope(base_sha)
    output = args.output.resolve()
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be empty")

    preconditions = None
    with tempfile.TemporaryDirectory(prefix="ap-i004-base-") as temporary:
        base_root = Path(temporary) / "repo"
        run(["git", "worktree", "add", "--detach", str(base_root), base_sha], ROOT)
        try:
            actual_base = run(["git", "rev-parse", "HEAD"], base_root, True)
            require(actual_base == base_sha, "detached worktree exact-base mismatch")
            implementation_copy = base_root / "tests/validation/i004_ns_nonstationary_diagnostic.py"
            implementation_copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(IMPLEMENTATION, implementation_copy)
            code = subprocess.run([
                sys.executable,
                str(implementation_copy),
                "--contract", str(contract_path),
                "--output", str(output),
            ], cwd=base_root).returncode
            require(code == 0, f"I004 diagnostic failed with return code {code}")
            processor = output / "build" / "ap_process_pcm"
            require(processor.is_file(), "missing exact-base processor for clean anchors")
            preconditions = apply_clean_preconditions(output, processor, contract)
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(base_root)], cwd=ROOT, check=False)

    binding = {
        "schema_version": 1,
        "authority": "research-tooling-over-exact-baseline",
        "research_head_sha": research_head,
        "baseline_source_sha": base_sha,
        "merge_base_sha": base_sha,
        "research_changed_files": changed_files,
        "shipping_diff_zero": True,
        "candidate_limit": 0,
        "confirmation_limit": 0,
        "diagnostic_implementation_sha256": sha256(IMPLEMENTATION),
        "clean_preconditions_passed": bool(preconditions and preconditions["passed"]),
    }
    refresh_manifest(output, binding)
    report = json.loads((output / "baseline-report.json").read_text(encoding="utf-8"))
    print(json.dumps({
        "decision": report["decision"],
        "failed_cases": len(report["failed_flags"]),
        "clean_preconditions_passed": binding["clean_preconditions_passed"],
        "baseline_source_sha": base_sha,
        "research_head_sha": research_head,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise SystemExit(f"I004 exact-base entry error: {exc}")
