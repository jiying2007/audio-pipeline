#!/usr/bin/env python3
"""Conservative change-aware CI selection for audio-pipeline.

Unknown paths always expand to the full matrix. The selector is an optimization
layer only; main pushes force the full verification graph.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

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
DOC_FILES = {"README.md", "README.zh-CN.md", "CHANGELOG.md", "THIRD_PARTY.md", "LICENSE"}


def changed_files(base: str, head: str) -> list[str]:
    out = subprocess.check_output(
        ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", f"{base}...{head}"],
        text=True,
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def is_docs(path: str) -> bool:
    return path in DOC_FILES or path.startswith(DOC_PREFIXES) or path.endswith(".md")


def analyze(paths: list[str], force_full: bool = False) -> dict:
    if force_full:
        paths = paths or ["<forced-main-full>"]
    if not paths:
        return _full("empty diff conservatively expands to full", [])
    if not force_full and all(is_docs(p) for p in paths):
        return {
            "docs_only": True,
            "full": False,
            "run_ci": False,
            "run_quality": False,
            "run_audio": False,
            "run_resource": False,
            "run_codeql": False,
            "run_perf": False,
            "run_alsa": False,
            "run_aec_backend": False,
            "run_ns_backend": False,
            "run_extended": False,
            "run_abi": False,
            "compositions": [],
            "arm": [],
            "reason": "documentation-only change",
            "paths": paths,
        }
    if force_full:
        return _full("main push / explicit full verification", paths)

    flags = {
        "aec": False, "ns": False, "resampler": False, "activity": False,
        "runtime": False, "validation": False, "certification": False,
        "bench": False, "alsa": False, "public": False, "unknown": False,
    }
    for p in paths:
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
        return _full("core/public/build/unknown change", paths)

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
        "run_resource": dsp or flags["runtime"],
        "run_codeql": code,
        "run_perf": dsp or flags["bench"],
        "run_alsa": flags["alsa"] or flags["runtime"],
        "run_aec_backend": flags["aec"],
        "run_ns_backend": flags["ns"],
        "run_extended": dsp or flags["runtime"],
        "run_abi": flags["runtime"],
        "compositions": compositions,
        "arm": DSP_ARM if dsp or flags["runtime"] else [],
        "reason": "validation/certification-only" if python_only else "targeted component change",
        "paths": paths,
    }


def _full(reason: str, paths: list[str]) -> dict:
    return {
        "docs_only": False,
        "full": True,
        "run_ci": True,
        "run_quality": True,
        "run_audio": True,
        "run_resource": True,
        "run_codeql": True,
        "run_perf": True,
        "run_alsa": True,
        "run_aec_backend": True,
        "run_ns_backend": True,
        "run_extended": True,
        "run_abi": True,
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
    assert analyze(["README.md"])["docs_only"]
    ns = analyze(["src/modules/ap_ns_module.c"])
    assert ns["run_ns_backend"] and not ns["full"] and "composition-ns-only" in ns["compositions"]
    aec = analyze(["src/modules/ap_aec_module.c"])
    assert aec["run_aec_backend"] and "composition-aec-only" in aec["compositions"]
    val = analyze(["validation/tools/run_validation.py"])
    assert val["run_audio"] and not val["run_ci"] and val["arm"] == []
    unknown = analyze(["scripts/new-thing.sh"])
    assert unknown["full"] and len(unknown["arm"]) == len(FULL_ARM)
    hil = analyze(["hil/board.schema.json"])
    assert hil["full"]
    assert analyze([], True)["full"]
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
    if args.self_test:
        self_test()
        return 0
    paths = args.paths
    if not paths:
        if not args.base or not args.head:
            parser.error("provide paths or --base/--head")
        paths = changed_files(args.base, args.head)
    emit(analyze(paths, args.force_full), args.github_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
