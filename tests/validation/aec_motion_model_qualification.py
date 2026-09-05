#!/usr/bin/env python3
"""Qualify I002 migration of the canonical AEC motion measurement model.

This script is a measurement-authority gate, not an acoustic optimizer. It keeps
product DSP/evaluator/policy fixed, proves that the canonical generator matches
the I001 audited model, exercises known-answer/negative contracts, and runs the
unchanged canonical development policy on bounded development seeds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "validation" / "tools"))
import build_aec_motion_corpus as motion  # noqa: E402
import build_aec_motion_bundle as bundle  # noqa: E402

ALLOWED_PATHS = {
    "CMakeLists.txt",
    "CHANGELOG.md",
    "validation/tools/build_aec_motion_corpus.py",
    "validation/tools/build_aec_motion_bundle.py",
    "validation/AEC_MOTION_DEVELOPMENT.md",
    "tests/validation/aec_motion_model_qualification.py",
    "tests/validation/aec_motion_model_audit.py",
    "docs/program/iterations/I002.json",
    "docs/program/iterations/I002-result.json",
    "docs/program/plan.json",
    "scripts/program.py",
    ".github/workflows/program-iteration.yml",
    ".github/workflows/aec-motion-development.yml",
}
FORBIDDEN_PREFIXES = (
    "src/", "include/", "ci/resource-baseline.json", "validation/policies/",
    "validation/datasets.lock.json", "validation/hosted_", "certification/",
)
FORBIDDEN_EXACT = {
    "validation/tools/run_validation.py",
    "validation/tools/run_validation_engine.py",
}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def validate_contract(contract: dict) -> None:
    required = {"schema_version", "iteration_id", "root_cause_id", "phase", "base_sha", "seeds",
                "seconds", "candidate_limit", "confirmation_limit", "run_timeout_seconds", "data_role",
                "promotion_allowed", "canonical_generator", "generator_version", "hypothesis", "acceptance",
                "next_on_success", "next_on_failure"}
    require(set(contract) == required, "contract keys")
    require(contract["schema_version"] == 1 and contract["iteration_id"] == "I002", "contract identity")
    require(contract["root_cause_id"] == "aec-motion-measurement-model" and
            contract["phase"] == "measurement-migration", "contract phase")
    require(isinstance(contract["base_sha"], str) and len(contract["base_sha"]) == 40 and
            all(ch in "0123456789abcdef" for ch in contract["base_sha"]), "base SHA")
    require(len(contract["seeds"]) == 3 and len(set(contract["seeds"])) == 3 and
            all(type(seed) is int and 0 <= seed < 2 ** 32 for seed in contract["seeds"]), "seed budget")
    require(isinstance(contract["seconds"], (int, float)) and math.isfinite(contract["seconds"]) and
            4.0 <= contract["seconds"] <= 8.0, "duration budget")
    require(contract["candidate_limit"] == 0 and contract["confirmation_limit"] == 0 and
            contract["promotion_allowed"] is False and contract["data_role"] == "development",
            "measurement migration has no promotion authority")
    require(1 <= contract["run_timeout_seconds"] <= 900, "timeout budget")
    require(contract["canonical_generator"] == "validation/tools/build_aec_motion_corpus.py" and
            contract["generator_version"] == motion.GENERATOR_VERSION == 2, "generator identity")
    require(isinstance(contract["acceptance"], list) and len(contract["acceptance"]) >= 8, "acceptance contract")


def changed_paths(base_sha: str) -> list[str]:
    raw = subprocess.check_output(["git", "diff", "--name-only", f"{base_sha}..HEAD"], cwd=ROOT, text=True)
    return [line for line in raw.splitlines() if line]


def assert_scope(paths: list[str]) -> None:
    require(paths, "I002 must change measurement authority")
    unknown = sorted(set(paths) - ALLOWED_PATHS)
    require(not unknown, "unexpected I002 path(s): " + ", ".join(unknown))
    for path in paths:
        require(path not in FORBIDDEN_EXACT and not any(path == prefix or path.startswith(prefix) for prefix in FORBIDDEN_PREFIXES),
                f"product/evaluator/policy path changed: {path}")
    require("validation/tools/build_aec_motion_corpus.py" in paths, "canonical generator not migrated")
    require("tests/validation/aec_motion_model_audit.py" in paths, "I001 duplicate executable must be removed")
    require("CMakeLists.txt" in paths and "CHANGELOG.md" in paths, "release metadata required")


def command(argv: list[str], cwd: Path, log_path: Path, timeout: int = 240) -> None:
    with log_path.open("w", encoding="utf-8") as log:
        completed = subprocess.run(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                   timeout=timeout, check=False)
    require(completed.returncode == 0, f"command failed ({completed.returncode}): {' '.join(argv)}")


def report_summary(report: dict) -> dict:
    summary = report["summary"]
    return {
        "validation_result": report["validation_result"],
        "cases": summary["cases"],
        "pass_rate": summary["pass_rate"],
        "median_output_render_corr_reduction": summary["median_output_render_corr_reduction"],
        "median_erle_db": summary.get("median_erle_db"),
        "max_output_clip_fraction": summary["max_output_clip_fraction"],
    }


def self_test() -> None:
    contract = json.loads((ROOT / "docs/program/iterations/I002.json").read_text())
    validate_contract(contract)
    motion.validate_model(motion.MODEL)
    require(json.loads((ROOT / "docs/program/iterations/I001.json").read_text())["model"] == motion.MODEL,
            "canonical model drifted from I001 audit")
    assert_scope(["CMakeLists.txt", "CHANGELOG.md", "validation/tools/build_aec_motion_corpus.py",
                  "tests/validation/aec_motion_model_audit.py"])
    for bad in (["src/aec/ap_aec_mdf.c"], ["validation/tools/run_validation.py"], ["README.md"]):
        try:
            assert_scope(["CMakeLists.txt", "CHANGELOG.md", "validation/tools/build_aec_motion_corpus.py",
                          "tests/validation/aec_motion_model_audit.py", *bad])
        except ValueError:
            pass
        else:
            raise AssertionError("forbidden/unregistered scope accepted")
    periodic = [round(10000 * math.sin(math.tau * n / 80)) for n in range(16000)]
    require(motion.excitation_sidelobe(periodic)["peak"] > 0.999, "periodic negative control")
    print("I002 qualification self-test: contract/model/scope/negative controls OK")


def run(contract_path: Path, output: Path) -> int:
    contract = json.loads(contract_path.read_text())
    validate_contract(contract)
    require(not output.exists() or (output.is_dir() and not any(output.iterdir())), "output must be empty")
    output.mkdir(parents=True, exist_ok=True)
    base_sha = contract["base_sha"]
    head_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    require(subprocess.check_output(["git", "rev-parse", base_sha + "^{commit}"], cwd=ROOT, text=True).strip() == base_sha,
            "base SHA unavailable")
    paths = changed_paths(base_sha)
    assert_scope(paths)
    require(json.loads((ROOT / "docs/program/iterations/I001.json").read_text())["model"] == motion.MODEL,
            "canonical model must exactly match audited I001 model")
    require("project(audio_pipeline VERSION 2.3.12 LANGUAGES C)" in (ROOT / "CMakeLists.txt").read_text(),
            "I002 release version")
    require((ROOT / "CHANGELOG.md").read_text().startswith("# 2.3.12\n"), "I002 changelog version")

    result = {
        "schema_version": 1,
        "iteration_id": "I002",
        "execution_result": "FAILED",
        "decision": "MEASUREMENT_CHANGE_REVIEW_REQUIRED",
        "base_sha": base_sha,
        "head_sha": head_sha,
        "contract_sha256": digest(contract_path),
        "generator_sha256": digest(ROOT / contract["canonical_generator"]),
        "bundle_sha256": digest(ROOT / "validation/tools/build_aec_motion_bundle.py"),
        "model_sha256": motion.json_sha256(motion.MODEL),
        "changed_paths": paths,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "product_qualification": "DEFERRED_BY_SCOPE",
        "authority": "measurement-migration-only-not-acoustic-promotion",
        "seeds": [],
        "errors": [],
    }
    write_json(output / "qualification-result.json", result)
    try:
        command([sys.executable, str(ROOT / contract["canonical_generator"]), "--self-test"], ROOT,
                output / "generator-self-test.log", timeout=90)
        command([sys.executable, str(ROOT / "validation/tools/build_aec_motion_bundle.py"), "--self-test"], ROOT,
                output / "bundle-self-test.log", timeout=30)
        build = output / "build"
        command(["cmake", "-S", str(ROOT), "-B", str(build), "-DCMAKE_BUILD_TYPE=Release",
                 "-DAP_BUILD_BENCH=OFF", "-DAP_STRICT_WARNINGS=ON"], ROOT, output / "cmake-configure.log")
        command(["cmake", "--build", str(build), "--target", "ap_process_pcm", "ap_build_info_dump", "--parallel"],
                ROOT, output / "cmake-build.log")
        command([str(build / "ap_build_info_dump")], ROOT, output / "build-info.txt", timeout=30)
        for seed in contract["seeds"]:
            seed_root = output / f"seed-{seed}"
            corpus_root = seed_root / "corpus"
            seed_root.mkdir(parents=True)
            command([sys.executable, str(ROOT / contract["canonical_generator"]), "--output", str(corpus_root),
                     "--seed", str(seed), "--seconds", str(contract["seconds"])], ROOT,
                    seed_root / "generate.log", timeout=180)
            command([sys.executable, str(ROOT / "validation/tools/run_validation.py"),
                     "--source-revision", head_sha,
                     "--corpus", str(corpus_root / "corpus.json"),
                     "--policy", str(ROOT / "validation/policies/validation-aec-motion-development.json"),
                     "--dataset-lock", str(ROOT / "validation/datasets.lock.json"),
                     "--source-manifest", str(corpus_root / "source-manifest.json"),
                     "--processor", str(build / "ap_process_pcm"),
                     "--output", str(seed_root / "report.json"),
                     "--evidence-manifest", str(seed_root / "evidence-manifest.json"), "--enforce"],
                    ROOT, seed_root / "validation.log", timeout=240)
            corpus = json.loads((corpus_root / "corpus.json").read_text())
            require(corpus["generator"]["version"] == 2 and corpus["generator"]["model"] == motion.MODEL,
                    "generated corpus identity")
            require(len(corpus["cases"]) == 12, "generated case count")
            for case in corpus["cases"]:
                truth_path = corpus_root / case["source"]["ground_truth"]
                motion.validate_truth(json.loads(truth_path.read_text()), motion.MODEL)
            sidelobes = {}
            for index, kind in enumerate(motion.MODEL["excitation"]):
                signal = motion.excitation(math.ceil(contract["seconds"] * 100) * motion.FRAME,
                                           seed * 17 + 101 + index, kind)
                sidelobes[kind] = motion.excitation_sidelobe(signal)
                require(sidelobes[kind]["peak"] < 0.30, "excitation ambiguity regression")
            report = json.loads((seed_root / "report.json").read_text())
            summary = report_summary(report)
            require(summary["validation_result"] == "PASS" and summary["cases"] == 12 and
                    abs(summary["pass_rate"] - 1.0) < 1e-12, "canonical policy did not pass")
            result["seeds"].append({"seed": seed, "sidelobes": sidelobes, "report": summary,
                                    "corpus_sha256": digest(corpus_root / "corpus.json"),
                                    "source_manifest_sha256": digest(corpus_root / "source-manifest.json"),
                                    "report_sha256": digest(seed_root / "report.json"),
                                    "evidence_manifest_sha256": digest(seed_root / "evidence-manifest.json")})
        result["execution_result"] = "COMPLETE"
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        result["errors"].append(str(exc))
        write_json(output / "qualification-result.json", result)
        raise
    write_json(output / "qualification-result.json", result)
    print(json.dumps({"iteration_id": "I002", "result": result["execution_result"],
                      "decision": result["decision"], "seeds": len(result["seeds"])}, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.contract is None or args.output is None:
        parser.error("--contract and --output are required")
    try:
        return run(args.contract, args.output)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"I002 qualification: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
