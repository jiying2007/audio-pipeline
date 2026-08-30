#!/usr/bin/env python3
"""Fail closed on current-documentation and laboratory-assurance drift.

Historical CHANGELOG entries are intentionally excluded: released historical facts must not be
rewritten just because current product policy changes.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CURRENT_DOCS = (
    "README.md",
    "README.zh-CN.md",
    "docs/DEVELOPMENT.md",
    "docs/PERFORMANCE.md",
    "docs/PLATFORM_SUPPORT.md",
    "docs/PRODUCT_ASSURANCE.md",
    "docs/REPOSITORY_GOVERNANCE.md",
    "docs/TESTING.md",
    "docs/TESTING.zh-CN.md",
    "docs/TRUSTED_RUNNERS.md",
    "hil/README.md",
    "certification/README.md",
    "certification/policies/README.md",
)

RESOURCE_LITERALS = (
    "78,096 B", "78,096", "78096",
    "46,928 B", "46,928", "46928",
    "25,408 B", "25,408", "25408",
    "1,064 B", "1,064", "1064",
    "32,752 B", "32,752", "32752",
    "5,168 B", "5,168", "5168",
    "32,632 B", "32,632", "32632",
    "5,080 B", "5,080", "5080",
)

STALE_PHRASES = (
    "pre-1.0",
    "repository is pre-1.0",
    "passing >=8 h soak",
    ">=8 h soak",
    "at least 8 h soak",
    "intentionally skipped",
    "Until then scheduled/post-release HIL jobs are intentionally skipped",
    "未设置或为 false 时自动 skip",
    "只有仓库变量 `HIL_ENABLED=true` 后才启用定时和 Release 后 HIL",
)

LAB_REQUIRED = (
    "lab/README.md",
    "lab/data-sources.lock.json",
    "lab/requirements-validation.txt",
    "lab/requirements-ansible.txt",
    "lab/scripts/labctl.py",
    "lab/ansible/ansible.cfg",
    "lab/ansible/inventory.example.yml",
    "lab/ansible/site.yml",
    "lab/ansible/roles/common/tasks/main.yml",
    "lab/ansible/roles/github_runner/tasks/main.yml",
    "lab/ansible/roles/audio_validation/tasks/main.yml",
    "lab/ansible/roles/audio_target/tasks/main.yml",
    "lab/examples/board.ssc305.example.json",
)


def read(root: Path, rel: str) -> str:
    path = root / rel
    if not path.is_file():
        raise AssertionError(f"missing current document: {rel}")
    return path.read_text(encoding="utf-8")


def project_version(root: Path) -> str:
    text = read(root, "CMakeLists.txt")
    match = re.search(r"project\s*\([^)]*?VERSION\s+([0-9]+\.[0-9]+\.[0-9]+)", text, re.S)
    if not match:
        raise AssertionError("CMake project VERSION not found")
    return match.group(1)


def changelog_version(root: Path) -> str:
    text = read(root, "CHANGELOG.md")
    match = re.search(r"^#\s+([0-9]+\.[0-9]+\.[0-9]+)\s*$", text, re.M)
    if not match:
        raise AssertionError("top CHANGELOG version not found")
    return match.group(1)


def validate_lab(root: Path, errors: list[str]) -> None:
    for rel in LAB_REQUIRED:
        if not (root / rel).is_file():
            errors.append(f"missing laboratory infrastructure asset: {rel}")
    if errors and any(item.startswith("missing laboratory") for item in errors):
        return
    try:
        source = read(root, "lab/scripts/labctl.py")
        compile(source, "lab/scripts/labctl.py", "exec")
    except (AssertionError, SyntaxError) as exc:
        errors.append(f"labctl is not valid Python: {exc}")
        return
    try:
        catalog = json.loads(read(root, "lab/data-sources.lock.json"))
        by_id = {item["id"]: item for item in catalog["datasets"]}
        core = set(catalog["profiles"]["commercial-core"])
        expected_core = {"realman", "but-reverbdb", "musan", "openslr-slr31"}
        if core != expected_core:
            errors.append(f"lab commercial-core drift: {sorted(core)}")
        bad = [item for item in core if by_id[item].get("usage_class") != "commercial-validation"]
        if bad:
            errors.append(f"lab commercial-core contains non-commercial data: {bad}")
        if not re.fullmatch(r"[0-9a-f]{40}", by_id["realman"].get("revision", "")):
            errors.append("lab RealMAN source is not pinned to an exact revision")
        if by_id["musan"].get("integrity", {}).get("value") != "0c472d4fc0c5141eca47ad1ffeb2a7df":
            errors.append("lab MUSAN official checksum drift")
        if by_id["openslr-slr31"].get("integrity", {}).get("value") != "6d7ab67ac6a1d2c993d050e16d61080d":
            errors.append("lab SLR31 official checksum drift")
    except (AssertionError, KeyError, TypeError, json.JSONDecodeError) as exc:
        errors.append(f"invalid laboratory data catalog: {exc}")
    inventory = read(root, "lab/ansible/inventory.example.yml")
    runner = read(root, "lab/ansible/roles/github_runner/tasks/main.yml")
    site = read(root, "lab/ansible/site.yml")
    if "04cf0be1aff4c3ec3554466c39124ca250e3effd8873bb7e8d68535aa9505d5d" not in inventory:
        errors.append("lab GitHub Actions runner x64 SHA-256 pin drift")
    for token in ("github_runner_registration_token", "no_log: true", "--unattended", "--replace"):
        if token not in runner:
            errors.append(f"lab runner role missing security/idempotence token: {token}")
    for token in ("hosts: audio_validation", "hosts: audio_target", "github_runner"):
        if token not in site:
            errors.append(f"lab Ansible site missing role/host contract: {token}")
    if read(root, "lab/requirements-validation.txt").strip() != "huggingface_hub==1.29.0":
        errors.append("lab validation Python dependency pin drift")
    if read(root, "lab/requirements-ansible.txt").strip() != "ansible-core==2.19.12":
        errors.append("lab Ansible dependency pin drift")
    try:
        completed = subprocess.run(
            [sys.executable, str(root / "lab/scripts/labctl.py"), "self-test"],
            cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        if completed.returncode != 0:
            errors.append("labctl self-test failed: " + completed.stdout.strip())
    except OSError as exc:
        errors.append(f"unable to execute labctl self-test: {exc}")


def validate(root: Path, *, require_lab: bool = True) -> list[str]:
    errors: list[str] = []
    try:
        cmake_version = project_version(root)
        change_version = changelog_version(root)
        if cmake_version != change_version:
            errors.append(f"version drift: CMake={cmake_version} CHANGELOG={change_version}")
    except AssertionError as exc:
        errors.append(str(exc))

    docs: dict[str, str] = {}
    for rel in CURRENT_DOCS:
        try:
            docs[rel] = read(root, rel)
        except AssertionError as exc:
            errors.append(str(exc))

    for rel, text in docs.items():
        for phrase in STALE_PHRASES:
            if phrase in text:
                errors.append(f"{rel}: stale phrase present: {phrase!r}")
        for literal in RESOURCE_LITERALS:
            if literal in text:
                errors.append(
                    f"{rel}: resource literal {literal!r} must live only in ci/resource-baseline.json "
                    "and docs/generated/RESOURCE_BASELINE.md"
                )

    for rel in ("README.md", "README.zh-CN.md"):
        text = docs.get(rel, "")
        for required in ("ci/resource-baseline.json", "docs/generated/RESOURCE_BASELINE.md"):
            if required not in text:
                errors.append(f"{rel}: missing resource SSoT link {required}")
        if "72" not in text or "product-lifecycle" not in text:
            errors.append(f"{rel}: must describe 72 h shipping certification and lifecycle archive")
        if require_lab and "lab/README.md" not in text:
            errors.append(f"{rel}: missing laboratory deployment link lab/README.md")

    hil_docs = ("README.md", "README.zh-CN.md", "docs/TESTING.md", "docs/TESTING.zh-CN.md", "hil/README.md")
    for rel in hil_docs:
        text = docs.get(rel, "")
        if "HIL_ENABLED" not in text:
            errors.append(f"{rel}: missing HIL_ENABLED policy")
        if "fail-visible" not in text and "fails visibly" not in text:
            errors.append(f"{rel}: missing fail-visible HIL policy")

    certification_docs = ("README.md", "README.zh-CN.md", "docs/PRODUCT_ASSURANCE.md", "docs/TESTING.md", "docs/TESTING.zh-CN.md", "certification/README.md")
    for rel in certification_docs:
        text = docs.get(rel, "")
        if "72" not in text:
            errors.append(f"{rel}: missing 72 h shipping-certification policy")

    if require_lab:
        validate_lab(root, errors)
    return errors


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel in CURRENT_DOCS:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "current HIL_ENABLED fail-visible 72 product-lifecycle "
                "ci/resource-baseline.json docs/generated/RESOURCE_BASELINE.md\n",
                encoding="utf-8",
            )
        (root / "CMakeLists.txt").write_text("project(audio_pipeline VERSION 1.6.0 LANGUAGES C)\n", encoding="utf-8")
        (root / "CHANGELOG.md").write_text("# 1.6.0\n\n- current\n\n# 1.5.0\n- historical 32,632 B\n", encoding="utf-8")
        assert validate(root, require_lab=False) == []
        with (root / "README.md").open("a", encoding="utf-8") as handle:
            handle.write("Runtime full 32,632 B\n")
        errors = validate(root, require_lab=False)
        assert any("resource literal" in item for item in errors)
    print("documentation consistency self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    errors = validate(args.root.resolve())
    if errors:
        for error in errors:
            print(f"DOC_CONSISTENCY_ERROR: {error}")
        return 1
    print("documentation consistency: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
