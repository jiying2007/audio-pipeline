#!/usr/bin/env python3
"""Fail-closed checks for the current public/documentation surface.

Historical release notes and archived iteration evidence are intentionally outside this
contract. This guard covers only current integration entry points, current public API
contracts, current CI labels, and the active ABI enforcement script.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]

CURRENT_SURFACE = (
    "README.md",
    "README.zh-CN.md",
    "CONTRIBUTING.md",
    "CONTRIBUTING.zh-CN.md",
    "docs/API_CONTRACT.md",
    "docs/API_CONTRACT.zh-CN.md",
    "docs/DEVELOPMENT.md",
    "docs/DEVELOPMENT.zh-CN.md",
    "docs/DIAGNOSTICS.md",
    "docs/QUICKSTART.zh-CN.md",
    ".github/workflows/verify.yml",
    ".github/workflows/quality.yml",
    "scripts/check-abi-contract.sh",
)

MIGRATION_PHRASES = (
    "v2 hard-cut",
    "v2 hard cut",
    "V2 hard-cut",
    "intentional hard cut",
    "Removed 1.x",
    "removed 1.x",
    "1.x alias",
    "1.x wrapper",
    "1.x generational",
    "no released v2 baseline yet",
    "legacy public token",
    "legacy exported symbol",
)

COMMAND_DOCS = (
    "README.md",
    "README.zh-CN.md",
    "docs/QUICKSTART.zh-CN.md",
)

QUICKSTART_RETIRED_SNIPPETS = (
    "ap_config_default();",
    "ap_state_size(",
    "ap_init(",
    "ap_process(",
)

QUICKSTART_REQUIRED_SNIPPETS = (
    "ap_config_default(AP_PROFILE_CALL)",
    "ap_pipeline_state_size()",
    "ap_pipeline_init(",
    "ap_pipeline_process_capture(",
)


def validate_texts(texts: Mapping[str, str]) -> list[str]:
    errors: list[str] = []
    for path in CURRENT_SURFACE:
        text = texts.get(path)
        if text is None:
            errors.append(f"missing current-surface file: {path}")
            continue
        for phrase in MIGRATION_PHRASES:
            if phrase in text:
                errors.append(f"{path}: migration-era phrase remains: {phrase!r}")

    for path in COMMAND_DOCS:
        text = texts.get(path, "")
        if "--out-dir" in text:
            errors.append(f"{path}: retired apdump option --out-dir remains")
        if "--work-dir" in text:
            errors.append(f"{path}: retired apreplay option --work-dir remains")
        if "--output-dir" not in text:
            errors.append(f"{path}: current apdump --output-dir example missing")
        if "--output-pcm" not in text:
            errors.append(f"{path}: current apreplay --output-pcm example missing")

    quickstart = texts.get("docs/QUICKSTART.zh-CN.md", "")
    for snippet in QUICKSTART_RETIRED_SNIPPETS:
        if snippet in quickstart:
            errors.append(f"docs/QUICKSTART.zh-CN.md: retired API snippet remains: {snippet}")
    for snippet in QUICKSTART_REQUIRED_SNIPPETS:
        if snippet not in quickstart:
            errors.append(f"docs/QUICKSTART.zh-CN.md: current API snippet missing: {snippet}")

    abi = texts.get("scripts/check-abi-contract.sh", "")
    required_abi = (
        "unable to fetch required baseline tag",
        "required baseline tag $BASE_REF does not resolve to a commit",
        "retired public token reintroduced",
        "retired exported symbol reintroduced",
        "public ABI regression",
        "public API/ABI contract OK against required baseline",
    )
    for snippet in required_abi:
        if snippet not in abi:
            errors.append(f"scripts/check-abi-contract.sh: terminal ABI guard missing: {snippet}")
    if 'git fetch origin "refs/tags/$BASE_REF:refs/tags/$BASE_REF" --force >/dev/null 2>&1 || true' in abi:
        errors.append("scripts/check-abi-contract.sh: required baseline fetch is fail-open")

    verify = texts.get(".github/workflows/verify.yml", "")
    quality = texts.get(".github/workflows/quality.yml", "")
    if "Public API/ABI contract gate when impacted" not in verify:
        errors.append("verify workflow: terminal public API/ABI gate label missing")
    if "Prove missing public ABI baseline fails closed" not in quality:
        errors.append("quality workflow: missing-baseline negative proof missing")
    if "Enforce public API/ABI contract" not in quality:
        errors.append("quality workflow: terminal public API/ABI gate label missing")

    return errors


def load_current_surface(root: Path) -> dict[str, str]:
    return {
        path: (root / path).read_text(encoding="utf-8")
        for path in CURRENT_SURFACE
    }


def self_test() -> None:
    base = {path: "terminal current surface\n" for path in CURRENT_SURFACE}
    for path in COMMAND_DOCS:
        base[path] += "apdump --output-dir extracted\napreplay --output-pcm replay.pcm\n"
    base["docs/QUICKSTART.zh-CN.md"] += (
        "ap_config_default(AP_PROFILE_CALL)\n"
        "ap_pipeline_state_size()\n"
        "ap_pipeline_init(\n"
        "ap_pipeline_process_capture(\n"
    )
    base["scripts/check-abi-contract.sh"] += (
        "unable to fetch required baseline tag\n"
        "required baseline tag $BASE_REF does not resolve to a commit\n"
        "retired public token reintroduced\n"
        "retired exported symbol reintroduced\n"
        "public ABI regression\n"
        "public API/ABI contract OK against required baseline\n"
    )
    base[".github/workflows/verify.yml"] += "Public API/ABI contract gate when impacted\n"
    base[".github/workflows/quality.yml"] += (
        "Prove missing public ABI baseline fails closed\n"
        "Enforce public API/ABI contract\n"
    )
    assert validate_texts(base) == []

    bad = dict(base)
    bad["README.md"] += "## v2 hard-cut API\n--out-dir\n"
    bad["docs/QUICKSTART.zh-CN.md"] += "ap_state_size(&cfg)\n"
    bad["scripts/check-abi-contract.sh"] += (
        'git fetch origin "refs/tags/$BASE_REF:refs/tags/$BASE_REF" --force >/dev/null 2>&1 || true\n'
    )
    errors = validate_texts(bad)
    assert any("migration-era phrase" in error for error in errors)
    assert any("--out-dir" in error for error in errors)
    assert any("retired API snippet" in error for error in errors)
    assert any("fail-open" in error for error in errors)
    print("public surface contract self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0

    try:
        texts = load_current_surface(ROOT)
    except OSError as exc:
        print(f"public surface contract: {exc}")
        return 2
    errors = validate_texts(texts)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("public surface contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
