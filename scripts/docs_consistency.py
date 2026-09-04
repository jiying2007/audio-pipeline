#!/usr/bin/env python3
"""Fail closed on current-documentation, validation-framework and lab-assurance drift.

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
    "docs/ARCHITECTURE.md",
    "docs/DEVELOPMENT.md",
    "docs/PERFORMANCE.md",
    "docs/PLATFORM_SUPPORT.md",
    "docs/PRODUCT_ASSURANCE.md",
    "docs/REPOSITORY_GOVERNANCE.md",
    "docs/TESTING.md",
    "docs/TESTING.zh-CN.md",
    "docs/TRUSTED_RUNNERS.md",
    "docs/TUNING.md",
    "validation/README.md",
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
    "lab/ansible/roles/audio_builder/tasks/main.yml",
    "lab/ansible/roles/certification_archive/tasks/main.yml",
    "lab/examples/board.ssc305.example.json",
    ".github/workflows/extended-real-automation.yml",
    ".github/workflows/validation-extended-real.yml",
    ".github/workflows/hil-soak.yml",
    ".github/workflows/product-certification.yml",
    ".github/workflows/lab-user-mode.yml",
)

VALIDATION_REQUIRED = (
    "validation/authority.json",
    "validation/corpus.schema.json",
    "validation/policy.schema.json",
    "validation/report.schema.json",
    "validation/tools/authority.py",
    "validation/tools/run_validation.py",
    "validation/tools/run_validation_engine.py",
    "validation/tools/tuning_iteration.py",
    "validation/tools/tuning_iteration_engine.py",
    "validation/tuning/search-spaces/call-pr-smoke-v1.json",
    "validation/tuning/search-spaces/call-v1.json",
    ".github/workflows/audio-quality-gates.yml",
    ".github/workflows/acoustic-tuning-iteration.yml",
)

LIFECYCLE_REQUIRED = (
    "scripts/research_registry.py",
    "scripts/prepare_release.py",
    "scripts/release_manifest.py",
    "scripts/post_release_status.py",
    "scripts/qualification_fingerprint.py",
    ".github/research/evidence-index.json",
    ".github/research/qualification-policy.json",
    ".github/workflows/research-branch-gc.yml",
    ".github/workflows/validation-authority-qualification.yml",
    ".github/workflows/post-release-qualification-summary.yml",
    "docs/REPOSITORY_LIFECYCLE.md",
    "docs/REPOSITORY_LIFECYCLE.zh-CN.md",
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


def validate_supply_chain(root: Path, errors: list[str]) -> None:
    dockerfile = read(root, "ci/Dockerfile")
    first = next((line.strip() for line in dockerfile.splitlines() if line.strip()), "")
    if not re.fullmatch(r"FROM\s+ubuntu:24\.04@sha256:[0-9a-f]{64}", first):
        errors.append("CI Dockerfile base image must be pinned by immutable Ubuntu 24.04 digest")

    dependabot = read(root, ".github/dependabot.yml")
    required_tokens = (
        "package-ecosystem: github-actions",
        "package-ecosystem: pip",
        "directory: /lab",
        "package-ecosystem: docker",
        "directory: /ci",
        "lab-python-patch:",
        "dependency-name: ubuntu",
    )
    for token in required_tokens:
        if token not in dependabot:
            errors.append(f"Dependabot supply-chain coverage missing token: {token}")
    if "lab-python-dependencies:" in dependabot:
        errors.append("lab dependency automation must not use the unrestricted legacy group")
    if dependabot.count("version-update:semver-major") < 3:
        errors.append("Dependabot must reject major updates for Actions, lab Python and CI Ubuntu")
    if dependabot.count("version-update:semver-minor") < 2:
        errors.append("Dependabot must reject minor updates for lab Python and CI Ubuntu")
    if dependabot.count("          - patch") < 2:
        errors.append("Dependabot must retain patch updates for Actions and lab Python")


def validate_validation_framework(root: Path, errors: list[str]) -> None:
    for rel in VALIDATION_REQUIRED:
        if not (root / rel).is_file():
            errors.append(f"missing canonical validation asset: {rel}")
    if (root / "eval").exists():
        errors.append("legacy eval/ framework must not coexist with canonical validation/")
    if errors and any(item.startswith("missing canonical validation") for item in errors):
        return

    authority_text = read(root, "validation/authority.json")
    corpus_schema = read(root, "validation/corpus.schema.json")
    validation_readme = read(root, "validation/README.md")
    architecture = read(root, "docs/ARCHITECTURE.md")
    tuning = read(root, "docs/TUNING.md")
    evaluator = read(root, "validation/tools/run_validation.py")
    evaluator_engine = read(root, "validation/tools/run_validation_engine.py")
    tuner = read(root, "validation/tools/tuning_iteration.py")
    tuner_engine = read(root, "validation/tools/tuning_iteration_engine.py")
    audio_quality = read(root, ".github/workflows/audio-quality-gates.yml")
    tuning_workflow = read(root, ".github/workflows/acoustic-tuning-iteration.yml")

    try:
        authority = json.loads(authority_text)
        tiers = authority["corpus_tiers"]
        expected = {
            "regression", "research-validation", "validation-grade", "validation-grade-blind"
        }
        if set(tiers) != expected:
            errors.append(f"validation authority tier set drift: {sorted(tiers)}")
        if tiers["validation-grade"]["optimizer_roles"] != ["validation", "shadow"]:
            errors.append("validation-grade optimizer role authority drift")
        if tiers["validation-grade-blind"]["optimizer_roles"] != []:
            errors.append("blind corpus must never become optimizer input")
        if tiers["research-validation"]["allows_dev_split"] is not True:
            errors.append("research-validation must retain explicit development semantics")
        if tiers["validation-grade"]["allows_dev_split"] is not False:
            errors.append("validation-grade must forbid development split")
        if tiers["validation-grade-blind"]["requires_blind_key"] is not True:
            errors.append("blind authority must require repository-external key identity")
        product = authority["terminal_authority"]["product-certified"]
        if product.get("system") != "certification" or product.get("record_schema_version") != 4:
            errors.append("product-certified terminal authority drift")
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        errors.append(f"invalid validation authority JSON: {exc}")

    if "research-validation" not in corpus_schema:
        errors.append("corpus schema is missing research-validation authority tier")
    if "validation/authority.json" not in validation_readme or "certification/" not in validation_readme:
        errors.append("validation README must document authority SSoT and certification boundary")
    if "there is no parallel `eval/` implementation" not in architecture:
        errors.append("architecture must forbid a parallel eval framework")
    if "canonical `validation/`" not in tuning:
        errors.append("tuning guide must use canonical validation framework")

    for token in ("from authority import", "authority_sha256", "tier_spec"):
        if token not in evaluator:
            errors.append(f"canonical evaluator is not authority guarded: missing {token}")
    for token in ("optimizer_role_allowed", "objective_metric_missing", "unknown objective metrics"):
        if token not in tuner:
            errors.append(f"canonical tuner is not fail-closed/authority guarded: missing {token}")
    if "from authority import" in evaluator_engine or "from authority import" in tuner_engine:
        errors.append("private validation engines must not own duplicated authority policy")

    workflow_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((root / ".github/workflows").glob("*.yml"))
    )
    for private_entry in ("run_validation_engine.py", "tuning_iteration_engine.py"):
        if private_entry in workflow_text:
            errors.append(f"workflow bypasses canonical validation CLI via {private_entry}")

    if re.search(r"(?m)^\s*pull_request\s*:", tuning_workflow):
        errors.append("standalone acoustic tuning search must not duplicate required PR tuning")
    for token in ("schedule:", "workflow_dispatch:", "call-v1.json", "validation/tools/authority.py"):
        if token not in tuning_workflow:
            errors.append(f"scheduled acoustic tuning workflow missing token: {token}")
    for token in (
        "validation/tools/authority.py --self-test",
        "call-pr-smoke-v1.json",
        "Enforce bounded acoustic tuning iteration",
    ):
        if token not in audio_quality:
            errors.append(f"required Audio Quality gate missing canonical tuning token: {token}")

    for tool in ("authority.py", "run_validation.py", "tuning_iteration.py"):
        try:
            completed = subprocess.run(
                [sys.executable, str(root / "validation/tools" / tool), "--self-test"],
                cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
            )
            if completed.returncode != 0:
                errors.append(f"validation {tool} self-test failed: " + completed.stdout.strip())
        except OSError as exc:
            errors.append(f"unable to execute validation {tool} self-test: {exc}")


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
    builder = read(root, "lab/ansible/roles/audio_builder/tasks/main.yml")
    archive = read(root, "lab/ansible/roles/certification_archive/tasks/main.yml")
    site = read(root, "lab/ansible/site.yml")
    if "04cf0be1aff4c3ec3554466c39124ca250e3effd8873bb7e8d68535aa9505d5d" not in inventory:
        errors.append("lab GitHub Actions runner x64 SHA-256 pin drift")
    for token in ("github_runner_registration_token", "no_log: true", "--unattended", "--replace"):
        if token not in runner:
            errors.append(f"lab runner role missing security/idempotence token: {token}")
    for token in (
        "audio_builder:",
        'github_runner_labels: "audio-builder"',
        "audio_builder_shipping_cc:",
        "audio_builder_shipping_sysroot:",
        "audio_builder_shipping_toolchain_root:",
        "certification_archive:",
        'github_runner_labels: "certification-archive"',
        'certification_archive_command: "/usr/local/bin/audio-pipeline-cert-archive"',
    ):
        if token not in inventory:
            errors.append(f"lab inventory missing certification topology contract: {token}")
    for token in (
        "audio_builder_shipping_cc",
        "audio_builder_shipping_sysroot",
        "audio_builder_shipping_toolchain_root",
        "--version",
    ):
        if token not in builder:
            errors.append(f"audio-builder role missing fail-closed toolchain token: {token}")
    for token in (
        "certification_archive_command",
        "certification_archive_command_stat.stat.isreg",
        "certification_archive_command_stat.stat.executable",
    ):
        if token not in archive:
            errors.append(f"certification-archive role missing fail-closed backend token: {token}")
    for token in (
        "hosts: audio_validation",
        "hosts: audio_target",
        "hosts: audio_builder",
        "hosts: certification_archive",
        "github_runner",
    ):
        if token not in site:
            errors.append(f"lab Ansible site missing role/host contract: {token}")
    if read(root, "lab/requirements-validation.txt").strip() != "huggingface_hub==1.29.0":
        errors.append("lab validation Python dependency pin drift")
    if read(root, "lab/requirements-ansible.txt").strip() != "ansible-core==2.19.12":
        errors.append("lab Ansible dependency pin drift")
    extended_auto = read(root, ".github/workflows/extended-real-automation.yml")
    extended = read(root, ".github/workflows/validation-extended-real.yml")
    hil = read(root, ".github/workflows/hil-soak.yml")
    if "/opt/audio-validation-extended" in extended_auto or "/opt/audio-validation-extended" in extended:
        errors.append("extended-real workflow reintroduced a system-mode /opt default")
    for token in ("AUDIO_PIPELINE_LAB_DATA_ROOT", "$HOME/audio-validation-extended"):
        if token not in extended:
            errors.append(f"extended-real workflow missing runner-local user-mode token: {token}")
    if "default: /etc/audio-pipeline/board.json" in hil:
        errors.append("HIL workflow reintroduced a system-mode /etc board default")
    for token in ("AUDIO_PIPELINE_LAB_BOARD", "XDG_CONFIG_HOME", "$HOME/.config"):
        if token not in hil:
            errors.append(f"HIL workflow missing runner-local user-mode token: {token}")
    readiness = read(root, ".github/workflows/trusted-runner-readiness.yml")
    certification = read(root, ".github/workflows/product-certification.yml")
    lab_user_mode = read(root, ".github/workflows/lab-user-mode.yml")
    for forbidden in ("default: /opt/audio-validation-data", "default: /etc/audio-pipeline/board.json"):
        if forbidden in readiness:
            errors.append(f"trusted runner readiness reintroduced stale system-mode default: {forbidden}")
    for token in ("$HOME/audio-validation-data", "datasets.seal.json", "AUDIO_PIPELINE_LAB_BOARD", "XDG_CONFIG_HOME", "$HOME/.config"):
        if token not in readiness:
            errors.append(f"trusted runner readiness missing runner-local user-mode token: {token}")
    if "default: /etc/audio-pipeline/board.json" in certification:
        errors.append("Product Certification reintroduced a system-mode /etc board default")
    for token in (
        "AUDIO_PIPELINE_LAB_BOARD",
        "XDG_CONFIG_HOME",
        "$HOME/.config",
        "/tmp/audio-target-board-path.txt",
        "runs-on: [self-hosted, linux, audio-builder]",
        "runs-on: [self-hosted, linux, certification-archive]",
        "/usr/local/bin/audio-pipeline-cert-archive",
    ):
        if token not in certification:
            errors.append(f"Product Certification missing runner-local/certification topology token: {token}")
    for token in (
        "audio_builder",
        "builderuser",
        "Execute audio-builder as an ordinary user",
        '"audio_builder":"PASS"',
        "certification_archive",
        "archiveuser",
        "Execute certification-archive as an ordinary user",
        '"certification_archive":"PASS"',
    ):
        if token not in lab_user_mode:
            errors.append(f"required lab user-mode gate missing certification topology token: {token}")
    try:
        completed = subprocess.run(
            [sys.executable, str(root / "lab/scripts/labctl.py"), "self-test"],
            cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        if completed.returncode != 0:
            errors.append("labctl self-test failed: " + completed.stdout.strip())
    except OSError as exc:
        errors.append(f"unable to execute labctl self-test: {exc}")


def validate_lifecycle(root: Path, errors: list[str]) -> None:
    for rel in LIFECYCLE_REQUIRED:
        if not (root / rel).is_file():
            errors.append(f'missing lifecycle framework asset: {rel}')
    if any(item.startswith('missing lifecycle') for item in errors):
        return
    registry = read(root, '.github/research/evidence-index.json')
    qualification = read(root, '.github/research/qualification-policy.json')
    gc = read(root, '.github/workflows/research-branch-gc.yml')
    qualifier = read(root, '.github/workflows/validation-authority-qualification.yml')
    post = read(root, '.github/workflows/post-release-qualification-summary.yml')
    release = read(root, '.github/workflows/release.yml')
    hosted_aec = read(root, '.github/workflows/hosted-aec-real-validation.yml')
    for payload, name in ((registry, 'research registry'), (qualification, 'qualification policy')):
        try:
            json.loads(payload)
        except json.JSONDecodeError as exc:
            errors.append(f'invalid {name} JSON: {exc}')
    for token in ('research_registry.py --self-test', 'DELETE_GC_ELIGIBLE_REFS'):
        if token not in gc:
            errors.append(f'research GC workflow missing token: {token}')
    for token in ('workflow_call:', 'source_sha:', 'qualification_mode:', 'one-way'):
        if token not in hosted_aec:
            errors.append(f'Hosted Real AEC reusable qualification missing token: {token}')
    if 'uses: ./.github/workflows/hosted-aec-real-validation.yml' not in qualifier:
        errors.append('qualification workflow must reuse canonical Hosted Real AEC workflow')
    if 'release-manifest.json' not in release:
        errors.append('Release workflow must publish machine-readable release manifest')
    for token in ('BLOCKED_RUNNER', 'BLOCKED_CONFIG'):
        if token not in post:
            errors.append(f'post-release summary missing explicit blocked state: {token}')
    for tool in ('research_registry.py', 'prepare_release.py', 'release_manifest.py', 'post_release_status.py', 'qualification_fingerprint.py'):
        completed = subprocess.run(
            [sys.executable, str(root / 'scripts' / tool), '--self-test'],
            cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        if completed.returncode != 0:
            errors.append(f'lifecycle {tool} self-test failed: ' + completed.stdout.strip())


def validate(root: Path, *, require_lab: bool = True,
             require_validation: bool = True,
             require_supply_chain: bool = True,
             require_lifecycle: bool = True) -> list[str]:
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
        for required in (
            "ci/resource-baseline.json", "docs/generated/RESOURCE_BASELINE.md",
            "validation/authority.json", "research-validation",
        ):
            if required not in text:
                errors.append(f"{rel}: missing current truth-source token {required}")
        if "72" not in text or "product-lifecycle" not in text:
            errors.append(f"{rel}: must describe 72 h shipping certification and lifecycle archive")
        if "product-certified" not in text or "certification/" not in text:
            errors.append(f"{rel}: must separate product-certified from validation corpus tiers")
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

    if require_validation:
        validate_validation_framework(root, errors)
    if require_supply_chain:
        validate_supply_chain(root, errors)
    if require_lab:
        validate_lab(root, errors)
    if require_lifecycle:
        validate_lifecycle(root, errors)
    return errors


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel in CURRENT_DOCS:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "current HIL_ENABLED fail-visible 72 product-lifecycle "
                "ci/resource-baseline.json docs/generated/RESOURCE_BASELINE.md "
                "validation/authority.json research-validation product-certified certification/\n",
                encoding="utf-8",
            )
        (root / "CMakeLists.txt").write_text("project(audio_pipeline VERSION 1.6.0 LANGUAGES C)\n", encoding="utf-8")
        (root / "CHANGELOG.md").write_text("# 1.6.0\n\n- current\n\n# 1.5.0\n- historical 32,632 B\n", encoding="utf-8")
        assert validate(
            root, require_lab=False, require_validation=False, require_supply_chain=False,
            require_lifecycle=False
        ) == []
        with (root / "README.md").open("a", encoding="utf-8") as handle:
            handle.write("Runtime full 32,632 B\n")
        errors = validate(
            root, require_lab=False, require_validation=False, require_supply_chain=False,
            require_lifecycle=False
        )
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
