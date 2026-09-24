#!/usr/bin/env python3
"""Conservative change-aware CI selection for audio-pipeline.

Unknown paths always expand to the full matrix. The selector is an optimization
layer only; main pushes force the full verification graph. Product/runtime,
validation authority, certification, lab behavior and other release-bearing
changes must advance SemVer. Repository maintenance that cannot change the
shipped SDK or evidence authority may land between immutable releases.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAINTENANCE_WORKFLOW_CONTRACT = ROOT / ".github/program/maintenance_workflow_contract.py"
DIFF_FILTER = "ACDMRTUXB"

FULL_COMPOSITIONS = [
    "composition-low", "composition-tiny", "composition-voice-frontend",
    "composition-raw", "composition-aec-only", "composition-ns-only",
    "composition-activity-only", "composition-fast-resampler",
]
FULL_ARM = [
    "armv7a-scalar", "cortex-a7-scalar", "cortex-a7-neon",
    "cortex-a32-neon", "aarch64-neon",
]
DSP_ARM = ["cortex-a7-neon", "cortex-a32-neon", "aarch64-neon"]

DOC_PREFIXES = ("docs/",)
DOC_FILES = {"README.md", "README.zh-CN.md", "CHANGELOG.md", "THIRD_PARTY.md", "LICENSE", "SECURITY.md"}
RESEARCH_REGISTRY_METADATA_FILES = {".github/research/evidence-index.json"}
PROGRAM_ARCHIVE_GOVERNANCE_FILES = {
    ".github/program/maintenance_workflow_contract.py",
    ".github/program/terminal_workflow_retirement.py",
    ".github/workflows/program-iteration.yml",
    "docs/program/terminal-workflow-retirement.json",
}
TUNING_SEARCH_WORKFLOW_FILES = {
    ".github/workflows/audio-quality-gates.yml",
    ".github/workflows/verify.yml",
    ".github/workflows/acoustic-tuning-iteration.yml",
    "scripts/ci_impact.py",
}
RELEASE_NEUTRAL_PREFIXES = (".github/", "ci/", "tests/", "fuzz/")
RELEASE_NEUTRAL_FILES = {
    ".gitignore", ".gitattributes",
    "scripts/ci_impact.py", "scripts/docs_consistency.py",
    "scripts/public_surface_contract.py", "scripts/check-abi-contract.sh",
    "scripts/research_registry.py", "scripts/prepare_release.py",
    "scripts/release_manifest.py", "scripts/post_release_status.py",
    "scripts/qualification_fingerprint.py", "scripts/program.py",
    "scripts/test_history.py",
}
RELEASE_NEUTRAL_VALIDATION_PATTERNS = (
    re.compile(r"validation/tools/build_[A-Za-z0-9_]+_tuning_corpus\.py"),
    re.compile(r"validation/policies/validation-[A-Za-z0-9-]+-stage-tuning\.json"),
    re.compile(r"validation/tuning/search-spaces/[A-Za-z0-9._-]+\.json"),
    # Run receipts are archived observations, not executable validators, input
    # corpora or shipping policy. Keep the data-member allowlist narrow; this
    # affects versioning only, never the conservative CI matrix or hash gates.
    re.compile(
        r"validation/research/evidence/[A-Za-z0-9][A-Za-z0-9_-]*/"
        r"(?:SHA256SUMS|(?:build-info|compiler|corpora|diagnostic-infra-revision|"
        r"source-base-revision)\.txt|(?:contract|result|summary)\.json|probe\.sha256)"
    ),
)
VERSION_RE = re.compile(r"project\s*\([^)]*?VERSION\s+([0-9]+\.[0-9]+\.[0-9]+)", re.S)
VERSION_TOKEN_RE = re.compile(
    r"(project\s*\([^)]*?\bVERSION\s+)([0-9]+\.[0-9]+\.[0-9]+)", re.S
)
CHANGELOG_RE = re.compile(r"^#\s+([0-9]+\.[0-9]+\.[0-9]+)\s*$", re.M)


def validate_maintenance_workflow_contract() -> None:
    completed = subprocess.run(
        ["python3", str(MAINTENANCE_WORKFLOW_CONTRACT), "--self-test", "--check"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(
            "maintenance workflow contract failed:\n" + completed.stdout.strip()
        )


def changed_files(base: str, head: str) -> list[str]:
    out = subprocess.check_output(
        ["git", "diff", "--name-only", f"--diff-filter={DIFF_FILTER}", f"{base}...{head}"],
        text=True,
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def is_docs(path: str) -> bool:
    # Executable program contracts are governance, not documentation-only.
    if path.startswith("docs/program/") and not path.endswith(".md"):
        return False
    return path in DOC_FILES or path.startswith(DOC_PREFIXES) or path.endswith(".md")


def is_release_neutral(path: str) -> bool:
    return (
        is_docs(path)
        or path in RELEASE_NEUTRAL_FILES
        or path.startswith("docs/program/")
        or path.startswith(RELEASE_NEUTRAL_PREFIXES)
        or any(pattern.fullmatch(path) for pattern in RELEASE_NEUTRAL_VALIDATION_PATTERNS)
    )


def requires_tuning_search(paths: list[str]) -> bool:
    return any(
        path == "CMakeLists.txt"
        or path.startswith("cmake/")
        or path.startswith("src/")
        or path.startswith("include/")
        or path == "examples/process_pcm.c"
        or path.startswith("validation/")
        or path in TUNING_SEARCH_WORKFLOW_FILES
        for path in paths
    )


def parse_semver(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"([0-9]+)\.([0-9]+)\.([0-9]+)", value)
    if not match:
        raise ValueError(f"invalid project SemVer: {value}")
    return tuple(int(item) for item in match.groups())


def git_text(ref: str, path: str) -> str:
    return subprocess.check_output(["git", "show", f"{ref}:{path}"], text=True)


def project_version(ref: str) -> str:
    match = VERSION_RE.search(git_text(ref, "CMakeLists.txt"))
    if not match:
        raise ValueError(f"project VERSION missing at {ref}")
    return match.group(1)


def changelog_version(ref: str) -> str:
    match = CHANGELOG_RE.search(git_text(ref, "CHANGELOG.md"))
    if not match:
        raise ValueError(f"top CHANGELOG version missing at {ref}")
    return match.group(1)


def normalized_cmake_version(text: str) -> str:
    normalized, count = VERSION_TOKEN_RE.subn(
        lambda match: match.group(1) + '<VERSION>', text, count=1
    )
    if count != 1:
        raise ValueError('CMake project VERSION token missing')
    return normalized


def cmake_version_only(base: str, head: str) -> bool:
    before = git_text(base, 'CMakeLists.txt')
    after = git_text(head, 'CMakeLists.txt')
    return (
        before != after
        and project_version(base) != project_version(head)
        and normalized_cmake_version(before) == normalized_cmake_version(after)
    )


def enforce_release_version(base: str, head: str, paths: list[str]) -> None:
    release_paths = [path for path in paths if not is_release_neutral(path)]
    if not release_paths:
        return
    base_version = project_version(base)
    head_version = project_version(head)
    if parse_semver(head_version) <= parse_semver(base_version):
        raise ValueError(
            "release-bearing change must advance SemVer: "
            f"base={base_version} head={head_version} paths={release_paths[:8]}"
        )
    change_version = changelog_version(head)
    if change_version != head_version:
        raise ValueError(
            f"release version drift: CMake={head_version} CHANGELOG={change_version}"
        )


def analyze(paths: list[str], force_full: bool = False, cmake_version_only_change: bool = False) -> dict:
    if force_full:
        paths = paths or ["<forced-main-full>"]
    if not paths:
        return _full("empty diff conservatively expands to full", [])
    effective_paths = [
        path for path in paths
        if not (cmake_version_only_change and path == 'CMakeLists.txt')
    ]
    if (
        not force_full
        and effective_paths
        and all(p in RESEARCH_REGISTRY_METADATA_FILES for p in effective_paths)
    ):
        return _fast_only("research registry metadata-only change", paths)
    if (
        not force_full
        and effective_paths
        and all(p in PROGRAM_ARCHIVE_GOVERNANCE_FILES for p in effective_paths)
    ):
        return _governance_only("program archive governance-only change", paths)
    if not force_full and all(is_docs(p) for p in effective_paths):
        reason = (
            'version-only release metadata'
            if cmake_version_only_change and not effective_paths
            else 'documentation-only change'
        )
        return _fast_only(reason, paths)
    if force_full:
        return _full("main push / explicit full verification", paths)

    flags = {
        "aec": False, "ns": False, "resampler": False, "activity": False,
        "runtime": False, "validation": False, "certification": False,
        "bench": False, "alsa": False, "public": False, "unknown": False,
    }
    for p in effective_paths:
        if p.startswith(".github/") or p == "CMakeLists.txt" or p.startswith("cmake/"):
            flags["unknown"] = True
        elif p.startswith("include/"):
            flags["public"] = True
        elif p.startswith("tests/") or p.startswith("fuzz/"):
            flags["unknown"] = True
        elif p.startswith("src/platform/") or p.startswith("include/audio_pipeline/audio_runtime"):
            flags["runtime"] = True
        elif "aec" in p and (p.startswith("src/") or p.startswith("include/")):
            flags["aec"] = True
        elif ("ns" in p or "noise" in p) and (p.startswith("src/") or p.startswith("include/")):
            flags["ns"] = True
        elif "resampl" in p and (p.startswith("src/") or p.startswith("include/")):
            flags["resampler"] = True
        elif ("vad" in p or "activity" in p) and (p.startswith("src/") or p.startswith("include/")):
            flags["activity"] = True
        elif p.startswith("src/"):
            flags["unknown"] = True
        elif p.startswith("validation/") or p.startswith("eval/"):
            flags["validation"] = True
        elif p.startswith("certification/") or p in {"tools/ap_certify.py", "tools/target_evidence.py"}:
            flags["certification"] = True
        elif p.startswith("bench/") or p.startswith("scripts/compare-"):
            flags["bench"] = True
        elif p.startswith("examples/alsa"):
            flags["alsa"] = True
        elif p.startswith("examples/") or p.startswith("tools/"):
            flags["bench"] = True
        elif p.startswith("scripts/") or p.startswith("ci/") or p.startswith("hil/"):
            flags["unknown"] = True
        elif not is_docs(p):
            flags["unknown"] = True

    if flags["unknown"] or flags["public"]:
        return _full(
            "core/public/build/unknown change",
            paths,
            run_tuning=requires_tuning_search(paths),
        )

    dsp = flags["aec"] or flags["ns"] or flags["resampler"] or flags["activity"]
    code = dsp or flags["runtime"] or flags["bench"] or flags["alsa"]
    python_only = (flags["validation"] or flags["certification"]) and not code
    comps = {"composition-full", "composition-low", "composition-tiny"}
    if flags["aec"]:
        comps.add("composition-aec-only")
    if flags["ns"]:
        comps.add("composition-ns-only")
    if flags["resampler"]:
        comps.add("composition-fast-resampler")
    if flags["activity"]:
        comps.add("composition-activity-only")
    compositions = sorted(c for c in comps if c != "composition-full") if dsp else []
    return {
        "docs_only": False,
        "full": False,
        "run_ci": code,
        "run_quality": dsp or flags["runtime"],
        "run_audio": dsp or flags["validation"] or flags["certification"],
        "run_tuning": requires_tuning_search(paths),
        "run_resource": dsp or flags["runtime"],
        "run_codeql": code,
        "run_perf": dsp or flags["bench"],
        "run_alsa": flags["alsa"] or flags["runtime"],
        "run_aec_backend": flags["aec"],
        "run_ns_backend": flags["ns"],
        "run_extended": dsp or flags["runtime"],
        "run_abi": flags["runtime"],
        "run_lab": False,
        "compositions": compositions,
        "arm": DSP_ARM if dsp or flags["runtime"] else [],
        "reason": "validation/certification-only" if python_only else "targeted component change",
        "paths": paths,
    }


def _governance_only(reason: str, paths: list[str]) -> dict:
    return {
        "docs_only": False,
        "full": False,
        "run_ci": False,
        "run_quality": False,
        "run_audio": False,
        "run_tuning": False,
        "run_resource": False,
        "run_codeql": False,
        "run_perf": False,
        "run_alsa": False,
        "run_aec_backend": False,
        "run_ns_backend": False,
        "run_extended": False,
        "run_abi": False,
        "run_lab": False,
        "compositions": [],
        "arm": [],
        "reason": reason,
        "paths": paths,
    }


def _fast_only(reason: str, paths: list[str]) -> dict:
    return {
        "docs_only": True,
        "full": False,
        "run_ci": False,
        "run_quality": False,
        "run_audio": False,
        "run_tuning": False,
        "run_resource": False,
        "run_codeql": False,
        "run_perf": False,
        "run_alsa": False,
        "run_aec_backend": False,
        "run_ns_backend": False,
        "run_extended": False,
        "run_abi": False,
        "run_lab": False,
        "compositions": [],
        "arm": [],
        "reason": reason,
        "paths": paths,
    }


def _full(reason: str, paths: list[str], *, run_tuning: bool = True) -> dict:
    return {
        "docs_only": False,
        "full": True,
        "run_ci": True,
        "run_quality": True,
        "run_audio": True,
        "run_tuning": run_tuning,
        "run_resource": True,
        "run_codeql": True,
        "run_perf": True,
        "run_alsa": True,
        "run_aec_backend": True,
        "run_ns_backend": True,
        "run_extended": True,
        "run_abi": True,
        "run_lab": True,
        "compositions": FULL_COMPOSITIONS,
        "arm": FULL_ARM,
        "reason": reason,
        "paths": paths,
    }


def emit(result: dict, github_output: Path | None) -> None:
    print(json.dumps(result, sort_keys=True))
    if github_output:
        scalar = {k: v for k, v in result.items() if k not in {"paths", "compositions", "arm"}}
        with github_output.open("a", encoding="utf-8") as handle:
            for key, value in scalar.items():
                if isinstance(value, bool):
                    value = str(value).lower()
                handle.write(f"{key}={value}\n")
            handle.write("composition_matrix=" + json.dumps(result["compositions"], separators=(",", ":")) + "\n")
            handle.write("arm_matrix=" + json.dumps(result["arm"], separators=(",", ":")) + "\n")


def self_test() -> None:
    assert "D" in DIFF_FILTER, "deleted paths must participate in CI impact analysis"
    assert analyze(["README.md"])["docs_only"]
    assert is_release_neutral(".github/workflows/verify.yml")
    assert is_release_neutral("ci/Dockerfile")
    assert is_release_neutral("tests/test_pipeline.c")
    assert is_release_neutral("fuzz/fuzz_pipeline.c")
    assert is_release_neutral("scripts/ci_impact.py")
    assert is_release_neutral("scripts/docs_consistency.py")
    assert is_release_neutral("scripts/public_surface_contract.py")
    assert is_release_neutral("scripts/check-abi-contract.sh")
    assert is_release_neutral("scripts/program.py")
    assert is_release_neutral("scripts/test_history.py")
    assert is_release_neutral("docs/program/plan.json")
    assert is_release_neutral("docs/program/iterations/I001.json")
    assert not is_release_neutral("scripts/unregistered-program.py")
    assert not is_release_neutral("validation/tools/build_aec_motion_corpus.py")
    for path in [
        "scripts/program.py", "scripts/public_surface_contract.py",
        "scripts/check-abi-contract.sh", "docs/program/plan.json",
        "docs/program/iterations/I001.json",
    ]:
        program = analyze([path])
        assert program["full"] and program["run_lab"] and not program["docs_only"]
    assert is_release_neutral("validation/tools/build_agc_tuning_corpus.py")
    assert is_release_neutral("validation/tools/build_ns_tuning_corpus.py")
    assert is_release_neutral("validation/policies/validation-agc-stage-tuning.json")
    assert is_release_neutral("validation/policies/validation-ns-stage-tuning.json")
    assert is_release_neutral("validation/tuning/search-spaces/agc-stage-v1.json")
    archive_root = "validation/research/evidence/i015-35994848668/"
    archive_paths = [archive_root + name for name in (
        "SHA256SUMS", "build-info.txt", "compiler.txt", "contract.json",
        "corpora.txt", "diagnostic-infra-revision.txt", "probe.sha256",
        "result.json", "source-base-revision.txt", "summary.json",
    )]
    assert all(is_release_neutral(path) for path in archive_paths)
    for path in (
        archive_root + "validator.py", archive_root + "run.sh",
        archive_root + "probe.c", archive_root + "probe",
        archive_root + "policy.json", archive_root + "corpus.json",
        archive_root + "nested/result.json", archive_root + "../result.json",
        "validation/research/evidence-other/i015/result.json",
        "validation/research/evidence/.hidden/result.json",
        "validation/research/result.json",
    ):
        assert not is_release_neutral(path), path
    archive = analyze(archive_paths)
    assert archive["run_audio"] and archive["run_tuning"] and not archive["docs_only"]
    assert analyze(archive_paths, True)["full"]
    archive_pr_paths = archive_paths + [
        ".github/research/continuous-optimization/development-v4/"
        "i015-vad-upstream-consumption-decomposition-v1-result.json",
        "docs/program/I015-FINALIZATION.md",
    ]
    assert analyze(archive_pr_paths)["full"]
    # Exercise the version gate itself at unchanged SemVer, not just path flags.
    from unittest.mock import patch
    with patch(__name__ + ".project_version", return_value="2.3.49") as version:
        enforce_release_version("base", "head", archive_pr_paths)
        version.assert_not_called()
        for product_path in (
            "src/core/ap_pipeline.c", "validation/authority.json",
            "validation/policies/validation-smoke.json",
            "validation/tools/run_validation.py", archive_root + "validator.py",
        ):
            try:
                enforce_release_version("base", "head", archive_pr_paths + [product_path])
            except ValueError as error:
                assert "must advance SemVer" in str(error)
            else:
                raise AssertionError("release-bearing mixed diff passed: " + product_path)
    assert not is_release_neutral("validation/authority.json")
    assert not is_release_neutral("validation/tools/run_validation.py")
    assert not is_release_neutral("validation/policies/validation-smoke.json")
    assert not is_release_neutral("lab/requirements-ansible.txt")
    assert not is_release_neutral("src/core/ap_pipeline.c")
    assert parse_semver("2.3.1") > parse_semver("2.3.0")
    ns = analyze(["src/modules/ap_ns_module.c"])
    assert ns["run_ns_backend"] and ns["run_tuning"] and not ns["full"] and "composition-ns-only" in ns["compositions"]
    aec = analyze(["src/modules/ap_aec_module.c"])
    assert aec["run_aec_backend"] and aec["run_tuning"] and "composition-aec-only" in aec["compositions"]
    val = analyze(["validation/tools/run_validation.py"])
    assert val["run_audio"] and val["run_tuning"] and not val["run_ci"] and val["arm"] == [] and not val["run_lab"]
    tuning_val = analyze([
        "validation/tools/build_agc_tuning_corpus.py",
        "validation/policies/validation-agc-stage-tuning.json",
        "validation/tuning/search-spaces/agc-stage-v1.json",
    ])
    assert tuning_val["run_audio"] and tuning_val["run_tuning"] and not tuning_val["run_ci"] and not tuning_val["full"]
    versioned_val = analyze(
        ["CMakeLists.txt", "validation/tools/run_validation.py"],
        cmake_version_only_change=True,
    )
    assert versioned_val["run_audio"] and not versioned_val["full"]
    version_only = analyze(["CMakeLists.txt"], cmake_version_only_change=True)
    assert version_only["docs_only"] and not version_only["full"]
    registry_only = analyze([".github/research/evidence-index.json"])
    assert registry_only["docs_only"] and not registry_only["full"]
    assert registry_only["reason"] == "research registry metadata-only change"
    registry_mixed = analyze([
        ".github/research/evidence-index.json",
        "validation/tools/run_validation.py",
    ])
    assert registry_mixed["full"] and registry_mixed["run_lab"]
    registry_main = analyze([".github/research/evidence-index.json"], True)
    assert registry_main["full"] and registry_main["run_lab"]
    governance = analyze(sorted(PROGRAM_ARCHIVE_GOVERNANCE_FILES))
    assert not governance["docs_only"] and not governance["full"]
    assert governance["reason"] == "program archive governance-only change"
    for key in (
        "run_ci", "run_quality", "run_audio", "run_tuning", "run_resource", "run_codeql",
        "run_perf", "run_alsa", "run_aec_backend", "run_ns_backend",
        "run_extended", "run_abi", "run_lab",
    ):
        assert governance[key] is False, (key, governance[key])
    assert governance["compositions"] == [] and governance["arm"] == []
    governance_main = analyze(sorted(PROGRAM_ARCHIVE_GOVERNANCE_FILES), True)
    assert governance_main["full"] and governance_main["run_lab"]
    governance_mixed = analyze([
        ".github/program/terminal_workflow_retirement.py",
        "src/core/ap_pipeline.c",
    ])
    assert governance_mixed["full"] and governance_mixed["run_lab"]
    governance_with_deleted_workflow = analyze([
        ".github/program/terminal_workflow_retirement.py",
        ".github/workflows/research-stage-lane-optimization.yml",
    ])
    assert governance_with_deleted_workflow["full"] and governance_with_deleted_workflow["run_lab"]
    promotion_governance = analyze([".github/program/promotion_governance.py"])
    assert promotion_governance["full"] and promotion_governance["run_lab"]
    assert not promotion_governance["run_tuning"]
    unknown = analyze(["scripts/new-thing.sh"])
    assert unknown["full"] and unknown["run_lab"] and not unknown["run_tuning"]
    assert len(unknown["arm"]) == len(FULL_ARM)
    lab = analyze(["lab/ansible/site.yml"])
    assert lab["full"] and lab["run_lab"] and not lab["run_tuning"]
    lab_workflow = analyze([".github/workflows/lab-user-mode.yml"])
    assert lab_workflow["full"] and lab_workflow["run_lab"] and not lab_workflow["run_tuning"]
    hil = analyze(["hil/board.schema.json"])
    assert hil["full"] and hil["run_lab"] and not hil["run_tuning"]
    certification = analyze(["certification/record.schema.json"])
    assert certification["run_audio"] and not certification["run_tuning"]
    audio_workflow = analyze([".github/workflows/audio-quality-gates.yml"])
    assert audio_workflow["full"] and audio_workflow["run_tuning"]
    verify_workflow = analyze([".github/workflows/verify.yml"])
    assert verify_workflow["full"] and verify_workflow["run_tuning"]
    impact_self = analyze(["scripts/ci_impact.py"])
    assert impact_self["full"] and impact_self["run_tuning"]
    forced = analyze([], True)
    assert forced["full"] and forced["run_lab"] and forced["run_tuning"]
    print("ci impact analyzer self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base")
    parser.add_argument("--head")
    parser.add_argument("--force-full", action="store_true")
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    validate_maintenance_workflow_contract()
    if args.self_test:
        self_test()
        return 0
    paths = args.paths
    if not paths:
        if not args.base or not args.head:
            parser.error("provide paths or --base/--head")
        paths = changed_files(args.base, args.head)
    if args.base and args.head:
        enforce_release_version(args.base, args.head, paths)
    cmake_only = bool(
        args.base and args.head and 'CMakeLists.txt' in paths
        and cmake_version_only(args.base, args.head)
    )
    emit(analyze(paths, args.force_full, cmake_only), args.github_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
