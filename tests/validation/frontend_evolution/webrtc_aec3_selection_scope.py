#!/usr/bin/env python3
"""Exact CI wiring for the bounded AEC3 synthesis-selection experiment.

This layer admits only its declared additions and restores byte-exact historical
views for earlier CI consumers. It never runs DSP or classifies acoustic results.
"""
from __future__ import annotations

import json
import os
import subprocess

import webrtc_aec3_ci as previous
from contracts import ROOT, hex_digest, require, sha256

BASE = "9d2cfef495ac8e34d03a55538777c16010ac3b14"
BASE_WORKFLOW_SHA256 = "b03e970bac3bb10a672ad34f232292cc8b6c0e4c48fe31f30fe5dd95a6e7dabb"
REL = "tests/validation/frontend_evolution/"
MODULE = REL + "webrtc_aec3_selection_scope.py"
TEST = REL + "test_webrtc_aec3_selection_scope.py"
PLAN = ".github/research/frontend-evolution-v1/webrtc-aec3-synthesis-selection-v1.json"
DOCUMENT = "docs/research/frontend-evolution-v1/WEBRTC_AEC3_SYNTHESIS_SELECTION_V1.zh-CN.md"
WORKFLOW = ".github/workflows/frontend-research.yml"
NAVIGATION = "docs/research/frontend-evolution-v1/README.md"
REGISTRY = ".github/research/evidence-index.json"
F07_MODULE = REL + "webrtc_aec3_linear_tap_ci.py"
F07_TEST = REL + "test_webrtc_aec3_linear_tap_ci.py"
EXPERIMENT = "webrtc-aec3-synthesis-selection"
RESULT_DIRECTORY = "docs/research/frontend-evolution-v1/WEBRTC_AEC3_SYNTHESIS_SELECTION_20261128"
RESULT_PATHS = tuple(RESULT_DIRECTORY + "/" + name for name in
                     ("README.zh-CN.md", "result.json", "independent-readback.json"))
CORE_PATHS = (MODULE, TEST, PLAN,
              REL + "webrtc_aec3_selection_source.py",
              REL + "webrtc_aec3_selection_ci.py",
              REL + "test_webrtc_aec3_selection_source.py",
              REL + "test_webrtc_aec3_selection_adapter.py",
              REL + "webrtc_aec3_selection.py",
              REL + "test_webrtc_aec3_selection.py",
              REL + "webrtc_aec3_gain_control_audit.py",
              REL + "test_webrtc_aec3_gain_control_audit.py",
              REL + "webrtc_aec3_gain_control_source.py",
              REL + "webrtc_aec3_gain_control_trace.py",
              REL + "test_webrtc_aec3_gain_control_adapter.py",
              REL + "webrtc_aec3_gain_control_science.py",
              ".github/research/frontend-evolution-v1/aec3-joint-gain-controlled-synthesis-science-v1.json",
              ".github/research/frontend-evolution-v1/aec3-joint-gain-controlled-synthesis-v1.json")
JOB_MARKER = "\n  webrtc-aec3-synthesis-selection:\n"
SCOPE_BLOCK = """          # F07_SYNTHESIS_SELECTION_OUTER_SELECTOR_BEGIN
          import sys
          sys.path.insert(0, 'tests/validation/frontend_evolution')
          from webrtc_aec3_selection_scope import select_workflow as select_synthesis_workflow
          if select_synthesis_workflow():
              raise SystemExit(0)
          # F07_SYNTHESIS_SELECTION_OUTER_SELECTOR_END
"""
OUTPUT_LINE = "      f07_selection: ${{ steps.select.outputs.f07_selection }}\n"
OPTION = ", webrtc-aec3-synthesis-selection]"
TINY_STEP_PREVIOUS = """      - name: Validate the selected synthesis-selection method without compiling or executing DSP
        if: steps.select.outputs.f07_selection == 'true'
        shell: bash
        run: |
          set -euo pipefail
          timeout 60s python3 -B tests/validation/frontend_evolution/test_webrtc_aec3_selection_scope.py
          timeout 60s python3 -B tests/validation/frontend_evolution/test_webrtc_aec3_selection_source.py
          timeout 60s python3 -B tests/validation/frontend_evolution/test_webrtc_aec3_selection.py

"""
TINY_STEP = """      - name: Validate the selected synthesis-selection method without compiling or executing DSP
        if: steps.select.outputs.f07_selection == 'true'
        shell: bash
        run: |
          set -euo pipefail
          timeout 60s python3 -B tests/validation/frontend_evolution/test_webrtc_aec3_selection_scope.py
          timeout 60s python3 -B tests/validation/frontend_evolution/test_webrtc_aec3_selection_source.py
          timeout 60s python3 -B tests/validation/frontend_evolution/test_webrtc_aec3_selection.py
          timeout 60s python3 -B tests/validation/frontend_evolution/test_webrtc_aec3_gain_control_audit.py

"""
NAVIGATION_APPEND = """
## F07 AEC3 合成入口受控选择

[冻结合同](WEBRTC_AEC3_SYNTHESIS_SELECTION_V1.zh-CN.md)在[#977](https://github.com/jiying2007/audio-pipeline/issues/977)追踪。
复用已披露 p1-none 输入，先记录一次16秒中性状态；主窗451个合成支持块全部选E时停止，
仅在存在Y暴露时运行一次局部force-E。G位模式及GetGain后nearend状态只读保留，
不改变主窗、门槛或分支；旧F07方法及结果保持原样，不产生晋级或实机资格。
"""
RETAINED_SOURCE = {
    "branch": "research/f07-controlled-path-20261128", "head_sha": None, "status": "ACTIVE",
    "evidence": ["issue:977", "parent-issue:657:active", "implementation-base:" + BASE,
                 "contract:" + PLAN,
                 "decision:retain-moving-synthesis-selection-source-and-execution-ancestors;null-head-is-moving-custody;no-gc-or-acoustic-promotion"],
    "gc_eligible": False, "auto_gc": False,
}
F07_WORKFLOW_ANCHOR = ('def strip_workflow(text: str) -> str:\n'
                       '    """Strip only exact F07 wiring; existing readers still validate old bytes."""\n')
F07_WORKFLOW_ADAPTER = ('    from webrtc_aec3_selection_scope import strip_workflow as strip_selection_workflow\n'
                        '    text = strip_selection_workflow(text)\n')
F07_NAV_ANCHOR = 'def strip_navigation(data: bytes) -> bytes:\n'
F07_NAV_ADAPTER = ('    from webrtc_aec3_selection_scope import strip_navigation as strip_selection_navigation\n'
                   '    data = strip_selection_navigation(data)\n')
F07_TEST_ADAPTERS = (
    ('        cls.current = (ci.ROOT / ci.WORKFLOW).read_text()\n',
     '        from webrtc_aec3_selection_scope import strip_workflow\n'
     '        cls.current = strip_workflow(cls.current)\n'),
    ('            changes[path] = (result.stdout if result.returncode == 0 else None, (ci.ROOT / path).read_bytes())\n',
     '        from webrtc_aec3_selection_scope import predecessor_test_changes\n'
     '        changes = predecessor_test_changes(changes)\n'),
    ('        after = (ci.ROOT / ci.NAVIGATION).read_bytes()\n',
     '        from webrtc_aec3_selection_scope import predecessor_test_view\n'
     '        after = predecessor_test_view(ci.NAVIGATION, after)\n'),
    ('        after = (ci.ROOT / ci.REGISTRY).read_bytes()\n',
     '        from webrtc_aec3_selection_scope import predecessor_test_view\n'
     '        after = predecessor_test_view(ci.REGISTRY, after)\n'),
)


def git_bytes(revision: str, path: str = None) -> bytes:
    require(hex_digest(revision, 40) and revision != "0" * 40,
            "SELECTION exact nonzero Git revision required")
    args = ["git", "-C", str(ROOT), "-c", "core.fsmonitor=false",
            "-c", "safe.directory=" + str(ROOT.resolve())]
    args += ["show", revision + ":" + path] if path is not None else ["rev-parse", revision + "^{commit}"]
    result = subprocess.run(args, env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    require(result.returncode == 0, "SELECTION missing exact Git object: " + revision)
    return result.stdout


def job_text() -> str:
    return """
  webrtc-aec3-synthesis-selection:
    name: AEC3 synthesis-selection engineering (synthetic only, no speech)
    needs: scope
    if: needs.scope.outputs.f07_selection == 'true'
    runs-on: ubuntu-24.04
    timeout-minutes: 22
    env:
      EXECUTION_SHA: ${{ github.event.pull_request.head.sha || github.sha }}
      PYTHONDONTWRITEBYTECODE: '1'
    steps:
      - uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5
        with:
          fetch-depth: 0
          persist-credentials: false
          ref: ${{ github.event.pull_request.head.sha || github.sha }}
      - name: Build the separately identified selector and run only its finite synthetic stage
        shell: bash
        run: |
          set -euo pipefail
          timeout --signal=KILL 1260s python3 -B \\
            tests/validation/frontend_evolution/webrtc_aec3_selection_ci.py run \\
            --expected-head "$EXECUTION_SHA" --output "$RUNNER_TEMP/ap-webrtc-aec3-selection"
      - name: Preserve the selector bundle or actual failed prefix
        if: always()
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        with:
          name: frontend-research-webrtc-aec3-synthesis-selection-${{ github.run_id }}-attempt-${{ github.run_attempt }}
          path: |
            ${{ runner.temp }}/ap-webrtc-aec3-selection/webrtc-aec3-selection-engineering-bundle.tar.gz
            ${{ runner.temp }}/ap-webrtc-aec3-selection/ci-receipt.json
            ${{ runner.temp }}/ap-webrtc-aec3-selection/logs/
            ${{ runner.temp }}/ap-webrtc-aec3-selection/failed-build-evidence/
            ${{ runner.temp }}/ap-webrtc-aec3-selection/bundle/
          include-hidden-files: true
          retention-days: 90
          if-no-files-found: error
"""


def strip_workflow(text: str) -> str:
    """Remove only this exact layer; all predecessor bytes remain mandatory."""
    tiny_step = TINY_STEP if TINY_STEP in text else TINY_STEP_PREVIOUS
    markers = (JOB_MARKER, SCOPE_BLOCK, OUTPUT_LINE, OPTION, tiny_step)
    if not any(marker in text for marker in markers):
        return text
    require(all(text.count(marker) == 1 for marker in markers),
            "SELECTION missing or duplicate workflow wiring")
    require(text.endswith(job_text()), "SELECTION job differs from exact declared body")
    restored = text[:-len(job_text())]
    for old, new in ((SCOPE_BLOCK, ""), (OUTPUT_LINE, ""), (OPTION, "]"), (tiny_step, "")):
        restored = restored.replace(old, new, 1)
    frozen = git_bytes(BASE, WORKFLOW)
    require(sha256(frozen) == BASE_WORKFLOW_SHA256 and restored.encode() == frozen,
            "SELECTION complete predecessor workflow changed")
    return restored


def validate_workflow(text: str) -> None:
    require(JOB_MARKER in text, "SELECTION explicit job missing")
    require(strip_workflow(text).encode() == git_bytes(BASE, WORKFLOW),
            "SELECTION workflow predecessor identity")


def strip_navigation(data: bytes) -> bytes:
    appendix = NAVIGATION_APPEND.encode()
    if appendix not in data:
        return data
    require(data.count(appendix) == 1 and data.endswith(appendix),
            "SELECTION navigation must be one exact terminal append")
    restored = data[:-len(appendix)]
    require(restored == git_bytes(BASE, NAVIGATION), "SELECTION predecessor navigation changed")
    return restored


def expected_registry() -> bytes:
    frozen = git_bytes(BASE, REGISTRY)
    data = json.loads(frozen)
    require(len(data["records"]) == 87
            and not any(row["branch"] == RETAINED_SOURCE["branch"] for row in data["records"]),
            "SELECTION registry predecessor identity")
    suffix = b"\n  ]\n}\n"
    require(frozen.endswith(suffix), "SELECTION registry terminal layout changed")
    record = "\n".join("    " + line for line in
                       json.dumps(RETAINED_SOURCE, indent=2, ensure_ascii=False).splitlines()).encode()
    expected = frozen[:-len(suffix)] + b",\n" + record + suffix
    data["records"].append(RETAINED_SOURCE)
    require(json.loads(expected) == data, "SELECTION registry append must preserve every old record")
    return expected


def strip_registry(data: bytes) -> bytes:
    if RETAINED_SOURCE["branch"].encode() not in data:
        return data
    require(data == expected_registry(), "SELECTION registry record, policy or bytes changed")
    return git_bytes(BASE, REGISTRY)


def expected_predecessor_adapter(path: str) -> bytes:
    frozen = git_bytes(BASE, path)
    if path == F07_MODULE:
        adapters = ((F07_WORKFLOW_ANCHOR, F07_WORKFLOW_ADAPTER),
                    (F07_NAV_ANCHOR, F07_NAV_ADAPTER))
    else:
        require(path == F07_TEST, "SELECTION unregistered predecessor adapter")
        adapters = F07_TEST_ADAPTERS
    for anchor, addition in adapters:
        require(frozen.count(anchor.encode()) == 1 and addition.encode() not in frozen,
                "SELECTION predecessor adapter anchor changed")
        frozen = frozen.replace(anchor.encode(), (anchor + addition).encode(), 1)
    return frozen


def predecessor_test_view(path: str, data: bytes) -> bytes:
    """Explicit historical fixture view, never a new scientific PASS."""
    if path == WORKFLOW:
        return strip_workflow(data.decode()).encode()
    if path == NAVIGATION:
        return strip_navigation(data)
    if path == REGISTRY:
        return strip_registry(data)
    if path in (F07_MODULE, F07_TEST):
        frozen = git_bytes(BASE, path)
        require(data in (frozen, expected_predecessor_adapter(path)),
                "SELECTION unregistered change to historical CI consumer")
        return frozen
    return data


def predecessor_test_changes(changes: dict) -> dict:
    """Restore the cumulative F07 fixture only after exact new-layer admission."""
    new_paths = set(CORE_PATHS) | {DOCUMENT} | set(RESULT_PATHS)
    result = {}
    for path, (before, after) in changes.items():
        if path in new_paths:
            require(before is None and after is not None,
                    "SELECTION historical fixture cannot hide rewrites or deletes")
            continue
        require(not path.startswith(RESULT_DIRECTORY + "/"),
                "SELECTION unknown result in historical fixture")
        if after is not None:
            after = predecessor_test_view(path, after)
        result[path] = (before, after)
    return result


def select(event: str, selected: str, changes: dict, current: str):
    validate_workflow(current)
    false = dict({name: "false" for name in previous.HISTORICAL_FLAGS},
                 ap="false", webrtc="false", f07_linear="false", f07_selection="false")
    if event == "workflow_dispatch":
        return dict(false, f07_selection="true") if selected == EXPERIMENT else None
    require(event in ("pull_request", "push"), "SELECTION unsupported event")
    known = set(CORE_PATHS) | {DOCUMENT, NAVIGATION, REGISTRY, F07_MODULE, F07_TEST, WORKFLOW} | set(RESULT_PATHS)
    relevant = set(CORE_PATHS) | {DOCUMENT, NAVIGATION, REGISTRY} | set(RESULT_PATHS)
    wanted = any(path in relevant or path.startswith(RESULT_DIRECTORY + "/") for path in changes)
    if WORKFLOW in changes:
        require(changes[WORKFLOW][1] == current.encode(),
                "SELECTION actual workflow diff mismatch")
        if current.encode() != changes[WORKFLOW][0]:
            wanted = True
    if not wanted:
        return None
    require(all(path in known for path in changes), "SELECTION mixed or unregistered research change")
    engineering = False
    for path, (before, after) in changes.items():
        require(after is not None, "SELECTION deletion is not admitted: " + path)
        if path in CORE_PATHS:
            engineering = True
        elif path == WORKFLOW:
            require(after == current.encode() and before is not None,
                    "SELECTION actual workflow diff mismatch")
            require(before == git_bytes(BASE, WORKFLOW)
                    or strip_workflow(before.decode()).encode() == git_bytes(BASE, WORKFLOW),
                    "SELECTION unregistered workflow predecessor")
            engineering = True
        elif path in (F07_MODULE, F07_TEST):
            require(before == git_bytes(BASE, path) and after == expected_predecessor_adapter(path),
                    "SELECTION only exact historical CI view adapters admitted")
        elif path == NAVIGATION:
            require(before == git_bytes(BASE, NAVIGATION)
                    and after == before + NAVIGATION_APPEND.encode()
                    and strip_navigation(after) == before,
                    "SELECTION only exact navigation append admitted")
        elif path == REGISTRY:
            require(before == git_bytes(BASE, REGISTRY) and after == expected_registry(),
                    "SELECTION only exact retained-source append admitted")
        elif path in RESULT_PATHS:
            require(before is None, "SELECTION published result rewrite or rollback forbidden")
    return dict(false, f07_selection=str(engineering).lower())


def select_workflow() -> bool:
    event = os.environ["EVENT_NAME"]
    changes = {}
    if event != "workflow_dispatch":
        base = os.environ["BASE_SHA"]
        git_bytes(base)
        args = ["git", "-C", str(ROOT), "-c", "core.fsmonitor=false",
                "-c", "safe.directory=" + str(ROOT.resolve())]
        environment = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
        head = subprocess.check_output(args + ["rev-parse", "HEAD"], env=environment, timeout=10).decode().strip()
        git_bytes(head)
        names = subprocess.check_output(args + ["diff", "--name-only", base, head],
                                        env=environment, timeout=30).decode().splitlines()
        for path in names:
            values = []
            for revision in (base, head):
                entry = subprocess.check_output(args + ["ls-tree", "--full-tree", revision, "--", path],
                                                env=environment, timeout=15)
                if not entry:
                    values.append(None)
                    continue
                require(entry.startswith(b"100644 blob ") and entry.count(b"\n") == 1,
                        "SELECTION nonregular or ambiguous changed Git member: " + path)
                values.append(git_bytes(revision, path))
            changes[path] = tuple(values)
    result = select(event, os.environ.get("SELECTED_EXPERIMENT", ""), changes,
                    (ROOT / WORKFLOW).read_text())
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        for name, value in (result or {"f07_selection": "false"}).items():
            output.write(name + "=" + value + "\n")
    return result is not None
