#!/usr/bin/env python3
"""Temporary exact patcher for lifecycle framework rollout.

This file is intentionally deleted by the finalize workflow before the final
framework commit. Keeping GitHub Actions expressions here prevents the finalize
workflow itself from pre-parsing expressions intended for target workflows.
"""
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one anchor, found {count}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_once(path: str, marker: str, addition: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if marker in text:
        return
    if not text.endswith("\n"):
        text += "\n"
    p.write_text(text + "\n" + addition.strip() + "\n", encoding="utf-8")


# scripts/ci_impact.py: release-neutral lifecycle tooling + VERSION_ONLY semantics.
replace_once(
    "scripts/ci_impact.py",
    '    "scripts/ci_impact.py", "scripts/docs_consistency.py",\n',
    '    "scripts/ci_impact.py", "scripts/docs_consistency.py",\n'
    '    "scripts/research_registry.py", "scripts/prepare_release.py",\n'
    '    "scripts/release_manifest.py", "scripts/post_release_status.py",\n',
)
replace_once(
    "scripts/ci_impact.py",
    'VERSION_RE = re.compile(r"project\\s*\\([^)]*?VERSION\\s+([0-9]+\\.[0-9]+\\.[0-9]+)", re.S)\n',
    'VERSION_RE = re.compile(r"project\\s*\\([^)]*?VERSION\\s+([0-9]+\\.[0-9]+\\.[0-9]+)", re.S)\n'
    'VERSION_TOKEN_RE = re.compile(\n'
    '    r"(project\\s*\\([^)]*?\\bVERSION\\s+)([0-9]+\\.[0-9]+\\.[0-9]+)", re.S\n'
    ')\n',
)
replace_once(
    "scripts/ci_impact.py",
    "\n\ndef enforce_release_version(base: str, head: str, paths: list[str]) -> None:\n",
    "\n\ndef normalized_cmake_version(text: str) -> str:\n"
    "    normalized, count = VERSION_TOKEN_RE.subn(\n"
    "        lambda match: match.group(1) + '<VERSION>', text, count=1\n"
    "    )\n"
    "    if count != 1:\n"
    "        raise ValueError('CMake project VERSION token missing')\n"
    "    return normalized\n\n"
    "\ndef cmake_version_only(base: str, head: str) -> bool:\n"
    "    before = git_text(base, 'CMakeLists.txt')\n"
    "    after = git_text(head, 'CMakeLists.txt')\n"
    "    return (\n"
    "        before != after\n"
    "        and project_version(base) != project_version(head)\n"
    "        and normalized_cmake_version(before) == normalized_cmake_version(after)\n"
    "    )\n\n"
    "\ndef enforce_release_version(base: str, head: str, paths: list[str]) -> None:\n",
)
replace_once(
    "scripts/ci_impact.py",
    "def analyze(paths: list[str], force_full: bool = False) -> dict:\n",
    "def analyze(paths: list[str], force_full: bool = False, "
    "cmake_version_only_change: bool = False) -> dict:\n",
)
replace_once(
    "scripts/ci_impact.py",
    "    if not force_full and all(is_docs(p) for p in paths):\n        return {\n",
    "    effective_paths = [\n"
    "        path for path in paths\n"
    "        if not (cmake_version_only_change and path == 'CMakeLists.txt')\n"
    "    ]\n"
    "    if not force_full and all(is_docs(p) for p in effective_paths):\n"
    "        reason = (\n"
    "            'version-only release metadata'\n"
    "            if cmake_version_only_change and not effective_paths\n"
    "            else 'documentation-only change'\n"
    "        )\n"
    "        return {\n",
)
replace_once(
    "scripts/ci_impact.py",
    '            "reason": "documentation-only change",\n',
    '            "reason": reason,\n',
)
replace_once(
    "scripts/ci_impact.py",
    "    for p in paths:\n",
    "    for p in effective_paths:\n",
)
replace_once(
    "scripts/ci_impact.py",
    '    val = analyze(["validation/tools/run_validation.py"])\n'
    '    assert val["run_audio"] and not val["run_ci"] and val["arm"] == [] and not val["run_lab"]\n',
    '    val = analyze(["validation/tools/run_validation.py"])\n'
    '    assert val["run_audio"] and not val["run_ci"] and val["arm"] == [] and not val["run_lab"]\n'
    '    versioned_val = analyze(\n'
    '        ["CMakeLists.txt", "validation/tools/run_validation.py"],\n'
    '        cmake_version_only_change=True,\n'
    '    )\n'
    '    assert versioned_val["run_audio"] and not versioned_val["full"]\n'
    '    version_only = analyze(["CMakeLists.txt"], cmake_version_only_change=True)\n'
    '    assert version_only["docs_only"] and not version_only["full"]\n',
)
replace_once(
    "scripts/ci_impact.py",
    "    if args.base and args.head:\n"
    "        enforce_release_version(args.base, args.head, paths)\n"
    "    emit(analyze(paths, args.force_full), args.github_output)\n",
    "    if args.base and args.head:\n"
    "        enforce_release_version(args.base, args.head, paths)\n"
    "    cmake_only = bool(\n"
    "        args.base and args.head and 'CMakeLists.txt' in paths\n"
    "        and cmake_version_only(args.base, args.head)\n"
    "    )\n"
    "    emit(analyze(paths, args.force_full, cmake_only), args.github_output)\n",
)

# Verify: lifecycle tools are part of fast assurance.
replace_once(
    ".github/workflows/verify.yml",
    "          python3 scripts/docs_consistency.py --self-test\n"
    "          python3 scripts/docs_consistency.py\n",
    "          python3 scripts/docs_consistency.py --self-test\n"
    "          python3 scripts/research_registry.py --self-test\n"
    "          python3 scripts/prepare_release.py --self-test\n"
    "          python3 scripts/release_manifest.py --self-test\n"
    "          python3 scripts/post_release_status.py --self-test\n"
    "          python3 -m json.tool .github/research/evidence-index.json >/dev/null\n"
    "          python3 -m json.tool .github/research/qualification-policy.json >/dev/null\n"
    "          python3 scripts/docs_consistency.py\n",
)

# Hosted Real AEC: reusable exact-SHA one-way qualification without Draft PRs.
replace_once(
    ".github/workflows/hosted-aec-real-validation.yml",
    "  workflow_dispatch:\n\npermissions:\n",
    """  workflow_dispatch:
    inputs:
      source_sha:
        description: 'Optional exact 40-hex source SHA; defaults to event SHA'
        required: false
        default: ''
        type: string
      qualification_mode:
        description: 'normal or one-way'
        required: false
        default: normal
        type: choice
        options: [normal, one-way]
  workflow_call:
    inputs:
      source_sha:
        required: false
        default: ''
        type: string
      qualification_mode:
        required: false
        default: normal
        type: string

permissions:
""",
)
replace_once(
    ".github/workflows/hosted-aec-real-validation.yml",
    "  group: hosted-real-aec-${{ github.ref }}\n",
    "  group: hosted-real-aec-${{ inputs.source_sha || github.ref }}\n",
)
replace_once(
    ".github/workflows/hosted-aec-real-validation.yml",
    "    env:\n      AEC_REVISION: 6c633d0a9d2a143a0e364899b91b06f127315b18\n",
    "    env:\n"
    "      AEC_REVISION: 6c633d0a9d2a143a0e364899b91b06f127315b18\n"
    "      SOURCE_REVISION: ${{ inputs.source_sha || github.sha }}\n"
    "      QUALIFICATION_MODE: ${{ inputs.qualification_mode || 'normal' }}\n",
)
replace_once(
    ".github/workflows/hosted-aec-real-validation.yml",
    "      - uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5\n"
    "      - uses: ./.github/actions/setup-ccache\n",
    """      - uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5
        with:
          ref: ${{ inputs.source_sha || github.sha }}
          fetch-depth: 0
      - name: Enforce exact qualification source when supplied
        if: inputs.source_sha != ''
        run: |
          set -euo pipefail
          [[ "$SOURCE_REVISION" =~ ^[0-9a-f]{40}$ ]] || { echo 'source_sha must be exact 40-hex' >&2; exit 1; }
          test "$(git rev-parse HEAD)" = "$SOURCE_REVISION"
      - uses: ./.github/actions/setup-ccache
""",
)
replace_once(
    ".github/workflows/hosted-aec-real-validation.yml",
    "            --source-revision '${{ github.sha }}' \\\n",
    '            --source-revision "$SOURCE_REVISION" \\\n',
)
p = Path(".github/workflows/hosted-aec-real-validation.yml")
text = p.read_text(encoding="utf-8")
if text.count("          import json, statistics\n") != 2:
    raise SystemExit("hosted AEC expected two json/statistics anchors")
text = text.replace("          import json, statistics\n", "          import json, os, statistics\n")
p.write_text(text, encoding="utf-8")
replace_once(
    ".github/workflows/hosted-aec-real-validation.yml",
    "          assert report['summary']['median_output_render_corr_reduction'] is not None\n"
    "          groups = defaultdict(list)\n",
    "          assert report['summary']['median_output_render_corr_reduction'] is not None\n"
    "          if os.environ.get('QUALIFICATION_MODE') == 'one-way':\n"
    "              print(json.dumps({\n"
    "                  'result': report['validation_result'],\n"
    "                  'cases': report['summary']['cases'],\n"
    "                  'median_output_render_corr_reduction': report['summary']['median_output_render_corr_reduction'],\n"
    "                  'details': 'redacted-one-way',\n"
    "              }, sort_keys=True))\n"
    "              raise SystemExit(0)\n"
    "          groups = defaultdict(list)\n",
)
replace_once(
    ".github/workflows/hosted-aec-real-validation.yml",
    "          report = json.loads(Path('hosted-aec-out/report.json').read_text())\n"
    "          print('## Hosted real AEC validation')\n"
    "          print('- Source: `microsoft/AEC-Challenge` ICASSP 2022 real test set, exact commit + Git LFS SHA-256')\n",
    "          report = json.loads(Path('hosted-aec-out/report.json').read_text())\n"
    "          print('## Hosted real AEC validation')\n"
    "          print('- Source: `microsoft/AEC-Challenge` ICASSP 2022 real test set, exact commit + Git LFS SHA-256')\n"
    "          if os.environ.get('QUALIFICATION_MODE') == 'one-way':\n"
    "              print(f\"- Result: `{report['validation_result']}`\")\n"
    "              print(f\"- Cases: `{report['summary']['cases']}` (details redacted for one-way qualification)\")\n"
    "              print(f\"- Overall median render-correlation reduction: `{report['summary']['median_output_render_corr_reduction']:.6f}`\")\n"
    "              print('- Authority: one-way real AEC qualification; do not tune from this result.')\n"
    "              raise SystemExit(0)\n",
)

# Release: add machine-readable lineage/evidence manifest to immutable asset set.
replace_once(
    ".github/workflows/release.yml",
    """      - name: Package reproducible SDK/source and checksums
        if: steps.existing.outputs.release != 'true'
        env:
          TAG: ${{ steps.version.outputs.tag }}
          VERIFIED_SHA: ${{ github.event.workflow_run.head_sha }}
          SOURCE_DATE_EPOCH: ${{ steps.version.outputs.epoch }}
        run: |
""",
    """      - name: Package reproducible SDK/source and checksums
        if: steps.existing.outputs.release != 'true'
        env:
          VERSION: ${{ steps.version.outputs.version }}
          TAG: ${{ steps.version.outputs.tag }}
          VERIFIED_SHA: ${{ github.event.workflow_run.head_sha }}
          VERIFY_RUN_ID: ${{ github.event.workflow_run.id }}
          SOURCE_DATE_EPOCH: ${{ steps.version.outputs.epoch }}
          HIL_ENABLED: ${{ vars.HIL_ENABLED }}
          EXTENDED_REAL_ENABLED: ${{ vars.EXTENDED_REAL_ENABLED }}
        run: |
""",
)
replace_once(
    ".github/workflows/release.yml",
    "          cmp \"audio-pipeline-${TAG}-source.tar.gz\" /tmp/source-repeat.tar.gz\n"
    "          sha256sum \\\n"
    "            \"audio-pipeline-${TAG}-sdk.tar.gz\" \\\n"
    "            \"audio-pipeline-${TAG}-source.tar.gz\" \\\n"
    "            \"audio-pipeline-${TAG}.spdx.json\" \\\n"
    "            \"audio-pipeline-${TAG}-validation-smoke-corpus.json\" \\\n"
    "            \"audio-pipeline-${TAG}-validation-smoke.json\" \\\n"
    "            \"audio-pipeline-${TAG}-validation-smoke-evidence.json\" > SHA256SUMS\n",
    "          cmp \"audio-pipeline-${TAG}-source.tar.gz\" /tmp/source-repeat.tar.gz\n"
    "          python3 scripts/release_manifest.py --self-test\n"
    "          python3 scripts/release_manifest.py \\\n"
    "            --version \"$VERSION\" --tag \"$TAG\" \\\n"
    "            --source-sha \"$VERIFIED_SHA\" --verify-run-id \"$VERIFY_RUN_ID\" \\\n"
    "            --prs-json /tmp/release-prs.json \\\n"
    "            --hil-enabled \"$HIL_ENABLED\" --extended-real-enabled \"$EXTENDED_REAL_ENABLED\" \\\n"
    "            --asset \"audio-pipeline-${TAG}-sdk.tar.gz\" \\\n"
    "            --asset \"audio-pipeline-${TAG}-source.tar.gz\" \\\n"
    "            --asset \"audio-pipeline-${TAG}.spdx.json\" \\\n"
    "            --asset \"audio-pipeline-${TAG}-validation-smoke-corpus.json\" \\\n"
    "            --asset \"audio-pipeline-${TAG}-validation-smoke.json\" \\\n"
    "            --asset \"audio-pipeline-${TAG}-validation-smoke-evidence.json\" \\\n"
    "            --output \"audio-pipeline-${TAG}-release-manifest.json\"\n"
    "          sha256sum \\\n"
    "            \"audio-pipeline-${TAG}-sdk.tar.gz\" \\\n"
    "            \"audio-pipeline-${TAG}-source.tar.gz\" \\\n"
    "            \"audio-pipeline-${TAG}.spdx.json\" \\\n"
    "            \"audio-pipeline-${TAG}-validation-smoke-corpus.json\" \\\n"
    "            \"audio-pipeline-${TAG}-validation-smoke.json\" \\\n"
    "            \"audio-pipeline-${TAG}-validation-smoke-evidence.json\" \\\n"
    "            \"audio-pipeline-${TAG}-release-manifest.json\" > SHA256SUMS\n",
)
replace_once(
    ".github/workflows/release.yml",
    "            audio-pipeline-${{ steps.version.outputs.tag }}-validation-smoke-evidence.json\n"
    "            SHA256SUMS\n",
    "            audio-pipeline-${{ steps.version.outputs.tag }}-validation-smoke-evidence.json\n"
    "            audio-pipeline-${{ steps.version.outputs.tag }}-release-manifest.json\n"
    "            SHA256SUMS\n",
)
replace_once(
    ".github/workflows/release.yml",
    "            \"audio-pipeline-${TAG}-validation-smoke-evidence.json\" \\\n"
    "            SHA256SUMS\n",
    "            \"audio-pipeline-${TAG}-validation-smoke-evidence.json\" \\\n"
    "            \"audio-pipeline-${TAG}-release-manifest.json\" \\\n"
    "            SHA256SUMS\n",
)

# Documentation consistency: lifecycle assets are part of the canonical framework.
replace_once(
    "scripts/docs_consistency.py",
    '    ".github/workflows/acoustic-tuning-iteration.yml",\n)\n\n\ndef read(root: Path, rel: str) -> str:\n',
    '    ".github/workflows/acoustic-tuning-iteration.yml",\n)\n\n'
    'LIFECYCLE_REQUIRED = (\n'
    '    "scripts/research_registry.py",\n'
    '    "scripts/prepare_release.py",\n'
    '    "scripts/release_manifest.py",\n'
    '    "scripts/post_release_status.py",\n'
    '    ".github/research/evidence-index.json",\n'
    '    ".github/research/qualification-policy.json",\n'
    '    ".github/workflows/research-branch-gc.yml",\n'
    '    ".github/workflows/validation-authority-qualification.yml",\n'
    '    ".github/workflows/post-release-qualification-summary.yml",\n'
    '    "docs/REPOSITORY_LIFECYCLE.md",\n'
    '    "docs/REPOSITORY_LIFECYCLE.zh-CN.md",\n'
    ')\n\n\ndef read(root: Path, rel: str) -> str:\n',
)
replace_once(
    "scripts/docs_consistency.py",
    "def validate(root: Path, *, require_lab: bool = True,\n",
    "def validate_lifecycle(root: Path, errors: list[str]) -> None:\n"
    "    for rel in LIFECYCLE_REQUIRED:\n"
    "        if not (root / rel).is_file():\n"
    "            errors.append(f'missing lifecycle framework asset: {rel}')\n"
    "    if any(item.startswith('missing lifecycle') for item in errors):\n"
    "        return\n"
    "    registry = read(root, '.github/research/evidence-index.json')\n"
    "    qualification = read(root, '.github/research/qualification-policy.json')\n"
    "    gc = read(root, '.github/workflows/research-branch-gc.yml')\n"
    "    qualifier = read(root, '.github/workflows/validation-authority-qualification.yml')\n"
    "    post = read(root, '.github/workflows/post-release-qualification-summary.yml')\n"
    "    release = read(root, '.github/workflows/release.yml')\n"
    "    hosted_aec = read(root, '.github/workflows/hosted-aec-real-validation.yml')\n"
    "    for payload, name in ((registry, 'research registry'), (qualification, 'qualification policy')):\n"
    "        try:\n"
    "            json.loads(payload)\n"
    "        except json.JSONDecodeError as exc:\n"
    "            errors.append(f'invalid {name} JSON: {exc}')\n"
    "    for token in ('research_registry.py --self-test', 'DELETE_GC_ELIGIBLE_REFS'):\n"
    "        if token not in gc:\n"
    "            errors.append(f'research GC workflow missing token: {token}')\n"
    "    for token in ('workflow_call:', 'source_sha:', 'qualification_mode:', 'one-way'):\n"
    "        if token not in hosted_aec:\n"
    "            errors.append(f'Hosted Real AEC reusable qualification missing token: {token}')\n"
    "    if 'uses: ./.github/workflows/hosted-aec-real-validation.yml' not in qualifier:\n"
    "        errors.append('qualification workflow must reuse canonical Hosted Real AEC workflow')\n"
    "    if 'release-manifest.json' not in release:\n"
    "        errors.append('Release workflow must publish machine-readable release manifest')\n"
    "    for token in ('BLOCKED_RUNNER', 'BLOCKED_CONFIG'):\n"
    "        if token not in post:\n"
    "            errors.append(f'post-release summary missing explicit blocked state: {token}')\n"
    "    for tool in ('research_registry.py', 'prepare_release.py', 'release_manifest.py', 'post_release_status.py'):\n"
    "        completed = subprocess.run(\n"
    "            [sys.executable, str(root / 'scripts' / tool), '--self-test'],\n"
    "            cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,\n"
    "        )\n"
    "        if completed.returncode != 0:\n"
    "            errors.append(f'lifecycle {tool} self-test failed: ' + completed.stdout.strip())\n\n"
    "\ndef validate(root: Path, *, require_lab: bool = True,\n",
)
replace_once(
    "scripts/docs_consistency.py",
    "    if require_lab:\n        validate_lab(root, errors)\n    return errors\n",
    "    if require_lab:\n        validate_lab(root, errors)\n"
    "    validate_lifecycle(root, errors)\n"
    "    return errors\n",
)

# Current documentation links/contract, without touching historical CHANGELOG.
append_once(
    "docs/REPOSITORY_GOVERNANCE.md",
    "Repository lifecycle state machine",
    """## Repository lifecycle state machine

Research evidence, one-way validation qualification, immutable release lineage,
post-release laboratory states, and evidence-bound branch garbage collection are
specified in `docs/REPOSITORY_LIFECYCLE.md`. Research branches are not evidence
archives: terminal evidence must be sealed in the registry/artifacts before a
branch can become GC-eligible.
""",
)
append_once(
    "docs/TESTING.md",
    "Validation authority qualification",
    """## Validation authority qualification

Validation-authority candidates can run the canonical Hosted Real AEC holdout at
an exact 40-hex source SHA through `Validation Authority Qualification`. The
workflow reuses `hosted-aec-real-validation.yml` in one-way mode, so no
qualification-only Draft PR is required and holdout details are not optimizer
feedback. `main` push and ordinary PR Hosted Real AEC behavior remains unchanged.
""",
)
append_once(
    "docs/TESTING.zh-CN.md",
    "Validation authority qualification",
    """## Validation authority qualification

Validation authority 候选可通过 `Validation Authority Qualification` 对精确
40 位 source SHA 执行 canonical Hosted Real AEC one-way holdout。该入口复用
`hosted-aec-real-validation.yml`，不再需要 qualification-only Draft PR，且
holdout 细节不能作为优化反馈；普通 PR 与 main push 的 Hosted Real AEC 行为保持不变。
""",
)

print("framework lifecycle exact patch: OK")
