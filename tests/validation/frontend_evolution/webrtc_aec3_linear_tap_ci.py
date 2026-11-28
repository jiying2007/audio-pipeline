#!/usr/bin/env python3
"""F07's explicit, bounded wrapper around the unchanged AEC3 builder.

The reference sub-bundle retains the original compatibility engineering.  The
second engineering stage observes the same binary's explicitly requested linear
tap.  This module never invokes the six disclosed speech cases.
"""
from __future__ import annotations

import argparse
import importlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import webrtc_aec3_ci as previous
import webrtc_aec3_reference as reference
from contracts import ROOT, hex_digest, require, sha256

BASE = "a70f94489423c54edbcbc11acaab47ee4485b6b9"
BASE_WORKFLOW_SHA256 = "29dc1c973b9e1d61ad277dc953e9b81df16ca12a8c9578b0445b323d696d1784"
REL = "tests/validation/frontend_evolution/"
MODULE = REL + "webrtc_aec3_linear_tap_ci.py"
TEST = REL + "test_webrtc_aec3_linear_tap_ci.py"
FIXTURE = REL + "test_webrtc_aec3_linear_tap_adapter.py"
HARNESS = REL + "webrtc_aec3_linear_tap.py"
HARNESS_TEST = REL + "test_webrtc_aec3_linear_tap.py"
PLAN = ".github/research/frontend-evolution-v1/webrtc-aec3-linear-tap-v1.json"
DOCUMENT = "docs/research/frontend-evolution-v1/WEBRTC_AEC3_LINEAR_TAP_V1.zh-CN.md"
WORKFLOW = previous.WORKFLOW
AP_MODULE = REL + "ap_current_ci.py"
AP_TEST = REL + "test_ap_current_ci.py"
NAVIGATION = "docs/research/frontend-evolution-v1/README.md"
RESULT_DIRECTORY = "docs/research/frontend-evolution-v1/WEBRTC_AEC3_LINEAR_TAP_20261128"
RESULT_PATHS = tuple(RESULT_DIRECTORY + "/" + name for name in
                     ("README.zh-CN.md", "result.json", "independent-readback.json"))
EXPERIMENT = "webrtc-aec3-linear-tap"
KIND = "webrtc-aec3-linear-tap-engineering-v1"
CI_SECONDS = 1200
JOB_MARKER = "\n  webrtc-aec3-linear-tap:\n"
SCOPE_BLOCK = """          # F07_LINEAR_TAP_OUTER_SELECTOR_BEGIN
          import sys
          sys.path.insert(0, 'tests/validation/frontend_evolution')
          from webrtc_aec3_linear_tap_ci import select_workflow as select_f07_workflow
          if select_f07_workflow():
              raise SystemExit(0)
          # F07_LINEAR_TAP_OUTER_SELECTOR_END
"""
OUTPUT_LINE = "      f07_linear: ${{ steps.select.outputs.f07_linear }}\n"
OPTION = ", webrtc-aec3-linear-tap]"
TINY_STEP = """      - name: Validate the selected F07 method without compiling or executing DSP
        if: steps.select.outputs.f07_linear == 'true'
        shell: bash
        run: |
          set -euo pipefail
          timeout 60s python3 -B tests/validation/frontend_evolution/test_webrtc_aec3_linear_tap_ci.py
          timeout 60s python3 -B tests/validation/frontend_evolution/test_webrtc_aec3_linear_tap.py

"""
AP_ANCHOR = ('def predecessor_workflow(text: str) -> str:\n'
             '    """Restore only the declared AP wiring, then prove the entire predecessor."""\n')
AP_ADAPTER = ("    from webrtc_aec3_linear_tap_ci import strip_workflow as strip_f07_workflow\n"
              "    text = strip_f07_workflow(text)\n")
AP_NAV_ANCHOR = "    elif path == NAVIGATION:\n"
AP_NAV_ADAPTER = ("        from webrtc_aec3_linear_tap_ci import strip_navigation as strip_f07_navigation\n"
                  "        after = strip_f07_navigation(after)\n"
                  "        if before is not None:\n"
                  "            before = strip_f07_navigation(before)\n")
AP_TEST_ANCHOR = "        current = (ap.ROOT / ap.NAVIGATION).read_bytes()\n"
AP_TEST_ADAPTER = ("        from webrtc_aec3_linear_tap_ci import strip_navigation\n"
                   "        current = strip_navigation(current)\n")
NAVIGATION_APPEND = """
## F07 AEC3 线性输出观测

[冻结合同](WEBRTC_AEC3_LINEAR_TAP_V1.zh-CN.md)在[#975](https://github.com/jiying2007/audio-pipeline/issues/975)追踪，
固定线性与最终输出的单位、64/128点时序、三路工程等价和六例披露开发输入。
主条件只有一个独特窗口；全部次要观察和不可识别值均保留，不产生晋级。
登记、实际结果与保护主线验收分别留存，状态以任务及对应结果回执为准。
"""
REGISTRY = ".github/research/evidence-index.json"
REGISTRY_SHA256 = "448a95784c02739c7663988293afdbc705277ff85b112c4ba773b0cfe7a64b5b"
RETAINED_SOURCE = {"branch": "research/f07-aec3-linear-tap-20261128", "head_sha": None, "status": "ACTIVE",
                   "evidence": ["issue:975", "parent-issue:657:active", "implementation-base:" + BASE,
                       "contract:" + PLAN,
                       "decision:retain-moving-F07-source-and-frozen-execution-ancestors;null-head-is-moving-custody;no-gc-or-acoustic-promotion"],
                   "gc_eligible": False, "auto_gc": False}
CORE_PATHS = (MODULE, TEST, FIXTURE, HARNESS, HARNESS_TEST, PLAN,
              REL + "webrtc_aec3_runner.cc")
CONTROL_FILES = CORE_PATHS + (WORKFLOW, AP_MODULE, AP_TEST, REL + "webrtc_aec3_ci.py",
                            REL + "test_webrtc_aec3_adapter.py", REL + "webrtc_aec3_reference.py")
PATHS = {"reference": "reference", "runner": "reference/bin/webrtc-aec3-runner",
         "prepared": "reference/prepared", "build_receipt": "reference/build/build-receipt.json",
         "adapter_build": "reference/build/runner-build.json",
         "reference_ci_receipt": "reference-ci-receipt.json",
         "engineering": "linear-engineering/engineering.json"}
ENGINEERING_BUDGETS = {"compatibility_calls": 62, "compatibility_requested_audio_seconds": 6.95,
                      "linear_valid_calls": 13, "linear_invalid_calls": 12, "linear_process_calls": 25,
                      "linear_accepted_audio_seconds": 8.3, "linear_requested_audio_seconds": 8.4199375,
                      "combined_process_calls": 87, "combined_requested_audio_seconds": 15.3699375,
                      "each_stage_wall_seconds": 120, "each_stage_max_requested_audio_seconds": 10,
                      "separate_stage_budgets": True}


def git_bytes(revision: str, path: str = None) -> bytes:
    require(hex_digest(revision, 40), "F07 exact Git revision required")
    args = ["git", "-C", str(ROOT), "-c", "core.fsmonitor=false", "-c", "safe.directory=" + str(ROOT.resolve())]
    args += ["show", revision + ":" + path] if path is not None else ["rev-parse", revision + "^{commit}"]
    result = subprocess.run(args, env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    require(result.returncode == 0, "F07 missing exact Git object: " + revision + (":" + path if path else ""))
    return result.stdout


def job_text() -> str:
    return """
  webrtc-aec3-linear-tap:
    name: F07 linear tap engineering (one build, two explicit synthetic stages)
    needs: scope
    if: needs.scope.outputs.f07_linear == 'true'
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
      - name: Build once and preserve both compatibility and linear observation engineering
        shell: bash
        run: |
          set -euo pipefail
          timeout --signal=KILL 1260s python3 -B \\
            tests/validation/frontend_evolution/webrtc_aec3_linear_tap_ci.py run \\
            --expected-head "$EXECUTION_SHA" --output "$RUNNER_TEMP/ap-webrtc-aec3-linear-tap"
      - name: Preserve the F07 bundle or actual failed prefix
        if: always()
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        with:
          name: frontend-research-webrtc-aec3-linear-tap-${{ github.run_id }}-attempt-${{ github.run_attempt }}
          path: |
            ${{ runner.temp }}/ap-webrtc-aec3-linear-tap/webrtc-aec3-linear-tap*.tar.gz
            ${{ runner.temp }}/ap-webrtc-aec3-linear-tap/ci-receipt*.json
            ${{ runner.temp }}/ap-webrtc-aec3-linear-tap/logs/
            ${{ runner.temp }}/ap-webrtc-aec3-linear-tap/reference-build/webrtc-aec3-engineering-bundle.tar.gz
            ${{ runner.temp }}/ap-webrtc-aec3-linear-tap/reference-build/ci-receipt.json
            ${{ runner.temp }}/ap-webrtc-aec3-linear-tap/reference-build/logs/
            ${{ runner.temp }}/ap-webrtc-aec3-linear-tap/reference-build/failed-build-evidence/
            ${{ runner.temp }}/ap-webrtc-aec3-linear-tap/reference-build/bundle/
            ${{ runner.temp }}/ap-webrtc-aec3-linear-tap/bundle/
          include-hidden-files: true
          retention-days: 90
          if-no-files-found: error
"""


def strip_workflow(text: str) -> str:
    """Strip only exact F07 wiring; existing readers still validate old bytes."""
    markers = (JOB_MARKER, SCOPE_BLOCK, OUTPUT_LINE, OPTION, TINY_STEP)
    if not any(marker in text for marker in markers):
        return text
    require(all(text.count(marker) == 1 for marker in markers), "F07 missing or duplicate workflow wiring")
    require(text.endswith(job_text()), "F07 job differs from its exact declared body")
    text = text[:-len(job_text())]
    for old, new in ((SCOPE_BLOCK, ""), (OUTPUT_LINE, ""), (OPTION, "]"), (TINY_STEP, "")):
        text = text.replace(old, new, 1)
    return text


def validate_workflow(text: str) -> None:
    require(JOB_MARKER in text, "F07 explicit job missing")
    frozen = git_bytes(BASE, WORKFLOW)
    require(sha256(frozen) == BASE_WORKFLOW_SHA256 and strip_workflow(text).encode() == frozen,
            "F07 predecessor workflow or historical jobs changed")


def validate_ap_adapter(before: bytes, after: bytes) -> None:
    frozen = git_bytes(BASE, AP_MODULE)
    require(frozen.count(AP_ANCHOR.encode()) == 1 and AP_ADAPTER.encode() not in frozen,
            "F07 AP predecessor identity/anchor changed")
    expected = frozen.replace(AP_ANCHOR.encode(), (AP_ANCHOR + AP_ADAPTER).encode(), 1)
    require(expected.count(AP_NAV_ANCHOR.encode()) == 1, "F07 AP navigation anchor")
    expected = expected.replace(AP_NAV_ANCHOR.encode(), (AP_NAV_ANCHOR + AP_NAV_ADAPTER).encode(), 1)
    require(before == frozen and after == expected, "F07 only the exact AP predecessor-view adapter is admitted")


def validate_ap_test_view(before: bytes, after: bytes) -> None:
    frozen = git_bytes(BASE, AP_TEST)
    require(frozen.count(AP_TEST_ANCHOR.encode()) == 1, "F07 AP fixture anchor")
    expected = frozen.replace(AP_TEST_ANCHOR.encode(), (AP_TEST_ANCHOR + AP_TEST_ADAPTER).encode(), 1)
    require(before == frozen and after == expected, "F07 only the exact AP historical-fixture view is admitted")


def strip_navigation(data: bytes) -> bytes:
    appendix = NAVIGATION_APPEND.encode()
    if appendix not in data:
        return data
    require(data.count(appendix) == 1 and data.endswith(appendix), "F07 navigation must be one exact terminal append")
    restored = data[:-len(appendix)]
    require(restored == git_bytes(BASE, NAVIGATION), "F07 predecessor navigation body changed")
    return restored


def navigation_transition(before: bytes, after: bytes) -> None:
    require(NAVIGATION_APPEND and before is not None and after is not None,
            "F07 navigation append has not been declared")
    appendix = NAVIGATION_APPEND.encode()
    require(before.count(appendix) <= 1 and after.count(appendix) == 1
            and after.endswith(appendix) and before.replace(appendix, b"") == after[:-len(appendix)],
            "F07 unrelated, duplicate or removed navigation change")
    require(strip_navigation(after) == git_bytes(BASE, NAVIGATION), "F07 complete predecessor navigation identity")


def registry_transition(before: bytes, after: bytes) -> None:
    require(before == git_bytes(BASE, REGISTRY) and sha256(after) == REGISTRY_SHA256,
            "F07 exact retained-source registry transition required")
    old, new = json.loads(before), json.loads(after)
    require(len(old["records"]) == 86 and len(new["records"]) == 87
            and new["records"][-1] == RETAINED_SOURCE, "F07 retained source custody record")
    new["records"] = new["records"][:-1]
    require(new == old, "F07 old registry records or policy changed")


def select(event: str, selected: str, changes: dict, current: str):
    validate_workflow(current)
    false = dict({name: "false" for name in previous.HISTORICAL_FLAGS}, ap="false", webrtc="false", f07_linear="false")
    if event == "workflow_dispatch":
        return dict(false, f07_linear="true") if selected == EXPERIMENT else None
    require(event in ("pull_request", "push"), "F07 unsupported event")
    known = set(CORE_PATHS) | {DOCUMENT, NAVIGATION, REGISTRY, AP_MODULE, AP_TEST, WORKFLOW} | set(RESULT_PATHS)
    relevant = set(CORE_PATHS) | {DOCUMENT, NAVIGATION, REGISTRY} | set(RESULT_PATHS)
    wanted = any(path in relevant or path.startswith(RESULT_DIRECTORY + "/") for path in changes)
    if WORKFLOW in changes and current.encode() != changes[WORKFLOW][0]:
        wanted = True
    if not wanted:
        return None
    require(all(path in known for path in changes), "F07 mixed or unregistered research change")
    engineering = False
    for path, (before, after) in changes.items():
        require(after is not None, "F07 deletion is not admitted: " + path)
        if path in CORE_PATHS:
            engineering = True
        elif path == WORKFLOW:
            require(after == current.encode() and before is not None, "F07 actual workflow diff mismatch")
            require(before == git_bytes(BASE, WORKFLOW) or strip_workflow(before.decode()).encode() == git_bytes(BASE, WORKFLOW),
                    "F07 workflow predecessor is not registered")
            engineering = True
        elif path == AP_MODULE:
            validate_ap_adapter(before, after)
        elif path == AP_TEST:
            validate_ap_test_view(before, after)
        elif path == NAVIGATION:
            navigation_transition(before, after)
        elif path == REGISTRY:
            registry_transition(before, after)
        elif path in RESULT_PATHS:
            require(before is None, "F07 published result rewrite/rollback forbidden")
    return dict(false, f07_linear=str(engineering).lower())


def select_workflow() -> bool:
    event = os.environ["EVENT_NAME"]
    changes = {}
    if event != "workflow_dispatch":
        base = os.environ["BASE_SHA"]
        require(hex_digest(base, 40) and base != "0" * 40, "F07 exact base required")
        args = ["git", "-C", str(ROOT), "-c", "core.fsmonitor=false", "-c", "safe.directory=" + str(ROOT.resolve())]
        head = subprocess.check_output(args + ["rev-parse", "HEAD"], timeout=10).decode().strip()
        names = subprocess.check_output(args + ["diff", "--name-only", base, head], timeout=30).decode().splitlines()
        for path in names:
            values = []
            for revision in (base, head):
                result = subprocess.run(args + ["show", revision + ":" + path], stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, timeout=15)
                if result.returncode:
                    git_bytes(revision)
                values.append(result.stdout if result.returncode == 0 else None)
            changes[path] = tuple(values)
    result = select(event, os.environ.get("SELECTED_EXPERIMENT", ""), changes, (ROOT / WORKFLOW).read_text())
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        for name, value in (result or {"f07_linear": "false"}).items():
            output.write(name + "=" + value + "\n")
    return result is not None


def committed_controls(expected: str) -> dict:
    require(hex_digest(expected, 40), "F07 exact execution source required")
    args = ["git", "-C", str(ROOT), "-c", "core.fsmonitor=false", "-c", "safe.directory=" + str(ROOT.resolve())]
    require(subprocess.check_output(args + ["rev-parse", "HEAD"], timeout=10).decode().strip() == expected,
            "F07 actual checkout differs from explicit execution source")
    result = {}
    for name in CONTROL_FILES:
        data = git_bytes(expected, name)
        require((ROOT / name).read_bytes() == data, "F07 uncommitted executable/control input: " + name)
        if name in (REL + "webrtc_aec3_ci.py", REL + "test_webrtc_aec3_adapter.py", REL + "webrtc_aec3_reference.py"):
            require(data == git_bytes(BASE, name), "F07 original builder/compatibility reader changed")
        result[name] = sha256(data)
    return result


def fixture_module():
    return importlib.import_module("test_webrtc_aec3_linear_tap_adapter")


def execution_environment(root: Path) -> dict:
    return {"PATH": os.defpath, "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1",
            "LD_LIBRARY_PATH": str(root / "reference/bin/lib")}


def engineering_record(path: Path, revision: str, binary_sha: str, build_sha: str) -> dict:
    record = fixture_module().verify_engineering(path, binary_sha, build_sha, revision)
    require(record["fixture_source_sha256"] == sha256(git_bytes(revision, FIXTURE)), "F07 fixture source binding")
    require(record["runtime_identity_source_sha256"] == sha256(git_bytes(revision, REL + "webrtc_aec3_ci.py")),
            "F07 unchanged runtime observer binding")
    require(record["base_fixture_source_sha256"] == sha256(git_bytes(revision, REL + "test_webrtc_aec3_adapter.py")),
            "F07 original synthetic generator source binding")
    require(record["requested_capture_audio_seconds"] == 8.4199375
            and type(record["wall_seconds"]) in (int, float) and math.isfinite(record["wall_seconds"])
            and 0 < record["wall_seconds"] <= 120, "F07 linear engineering budget")
    return record


def verify_bundle(root: Path) -> dict:
    """Byte/Git readback: synthetic inputs are rebuilt; no SDK/build/ldd/speech."""
    root = previous.source.safe_path(root)
    manifest = reference.read_json(root / "bundle.json")
    require(manifest["schema_version"] == 1 and manifest["kind"] == KIND
            and manifest["status"] == "PASS_ENGINEERING_ONLY" and manifest["paths"] == PATHS,
            "F07 bundle kind/status/paths")
    require(reference.file_set(root, ("bundle.json",)) == manifest["files"], "F07 bundle file/hash set")
    revision = manifest["code_revision"]
    require(hex_digest(revision, 40) and set(manifest["controls_sha256"]) == set(CONTROL_FILES), "F07 control closure")
    for name, digest in manifest["controls_sha256"].items():
        require(sha256(git_bytes(revision, name)) == digest, "F07 committed control identity: " + name)
        if name not in (WORKFLOW, AP_MODULE, PLAN):
            require(sha256((ROOT / name).read_bytes()) == digest, "F07 use exact recorded implementation: " + name)
    original = reference.verify_bundle(root / PATHS["reference"])
    old_manifest, build, adapter, old_engineering = original
    require(old_manifest["code_revision"] == revision, "F07 reference source differs")
    require(len(old_engineering["calls"]) == 62 and old_engineering["requested_capture_audio_seconds"] == 6.95,
            "F07 original compatibility engineering must execute completely")
    original_ci = reference.read_json(root / PATHS["reference_ci_receipt"])
    require(original_ci["status"] == "PASS_ENGINEERING_ONLY" and original_ci["code_revision"] == revision
            and type(original_ci["elapsed_seconds"]) in (int, float) and math.isfinite(original_ci["elapsed_seconds"])
            and 0 < original_ci["elapsed_seconds"] <= previous.CI_SECONDS,
            "F07 original build/compatibility CI status and wall budget")
    original_controls = {name: manifest["controls_sha256"][name] for name in
                         (REL + "webrtc_aec3_ci.py", REL + "webrtc_aec3_runner.cc", REL + "test_webrtc_aec3_adapter.py")}
    require(original_ci["input_files_sha256"] == original_controls, "F07 original CI source closure")
    report = engineering_record(root / PATHS["engineering"], revision,
                                adapter["binary_sha256"], adapter["build_receipt_sha256"])
    original_output = Path(report["execution_output"])
    require(original_output.name == "linear-engineering"
            and report["binary"] == str(original_output.parent / PATHS["runner"]),
            "F07 engineering command must use its original bundle binary")
    require(reference.normalized_runtime(report["runtime_identity"]) == reference.normalized_runtime(adapter["runtime_identity"]),
            "F07 original linear engineering host/runtime differs from build")
    reference.research_runtime_binding(report["runtime_identity"], adapter)
    require(manifest["engineering_budgets"] == ENGINEERING_BUDGETS, "F07 stages/budgets changed")
    return {"manifest": manifest, "reference": original, "engineering": report,
            "paths": {name: root / value for name, value in PATHS.items()}}


def verify_engineering(root: Path, receipt: Path) -> dict:
    verified = verify_bundle(root)
    adapter = verified["reference"][2]
    report = engineering_record(receipt, verified["manifest"]["code_revision"],
                                adapter["binary_sha256"], adapter["build_receipt_sha256"])
    reference.research_runtime_binding(report["runtime_identity"], adapter)
    if previous.source.safe_path(receipt) != previous.source.safe_path(verified["paths"]["engineering"]):
        wrapper = reference.read_json(receipt.parent.parent / "host-engineering.json")
        require(wrapper["schema_version"] == 1 and wrapper["status"] == "PASS_ENGINEERING_ONLY"
                and wrapper["code_revision"] == verified["manifest"]["code_revision"]
                and wrapper["bundle_manifest_sha256"] == sha256((root / "bundle.json").read_bytes())
                and wrapper["receipt"] == "engineering/engineering.json"
                and wrapper["receipt_sha256"] == sha256(receipt.read_bytes())
                and wrapper["binary_sha256"] == adapter["binary_sha256"], "F07 host wrapper/bundle/source binding")
        for key in ("bundle_directory", "execution_output"):
            old = Path(wrapper[key])
            require(old.is_absolute() and ".." not in old.parts and str(old) == wrapper[key],
                    "F07 host wrapper canonical original path")
        require(report["execution_output"] == str(Path(wrapper["execution_output"]) / "engineering")
                and report["binary"] == str(Path(wrapper["bundle_directory"]) / PATHS["runner"]),
                "F07 host commands must use the recorded original bundle")
        require(type(wrapper["elapsed_seconds"]) in (int, float) and math.isfinite(wrapper["elapsed_seconds"])
                and 0 < wrapper["elapsed_seconds"] <= 120
                and all(type(wrapper[key]) is int and wrapper[key] == 0 for key in ("science_calls", "compile_calls"))
                and wrapper["compatibility_reexecution"] is False, "F07 host wrapper scope/budget")
    return report


def require_host_engineering(root: Path, receipt: Path = None) -> dict:
    verified = verify_bundle(root)
    receipt = receipt or verified["paths"]["engineering"]
    report = verify_engineering(root, receipt)
    observed = previous.runtime_identity(verified["paths"]["runner"], execution_environment(root))
    require(reference.normalized_runtime(observed) == reference.normalized_runtime(report["runtime_identity"]),
            "F07 this host needs its own successful linear engineering receipt")
    reference.research_runtime_binding(observed, verified["reference"][2], root / "reference")
    return report


def invalidate_success(output: Path) -> None:
    archive = output / "webrtc-aec3-linear-tap-bundle.tar.gz"
    if archive.exists():
        archive.rename(output / "webrtc-aec3-linear-tap-failed-prefix.tar.gz")
    path = output / "bundle/bundle.json"
    if path.exists():
        value = reference.read_json(path)
        path.rename(path.with_name("manifest-before-failure.json"))
        value["status"] = "FAIL_F07_BUNDLE_NOT_COMMITTED"
        previous.source.write_json(path, value)


def run(expected: str, output: Path) -> dict:
    started = time.monotonic()
    deadline = started + CI_SECONDS
    output = previous.source.safe_path(output)
    require(not output.exists() and previous.source.separate(ROOT, output), "F07 fresh output outside checkout required")
    output.mkdir(parents=True)
    logs = output / "logs"
    logs.mkdir()
    result = {"schema_version": 1, "status": "FAIL", "kind": KIND, "code_revision": expected,
              "stages": [], "science_calls": 0, "acoustic_acceptance": False, "promotion_authority": False}
    try:
        result["host"] = previous.assert_actions_host()
        result["controls_sha256"] = committed_controls(expected)
        validate_workflow((ROOT / WORKFLOW).read_text())
        legacy = output / "reference-build"
        previous.command([sys.executable, "-B", str(ROOT / (REL + "webrtc_aec3_ci.py")), "run",
                          "--expected-head", expected, "--output", str(legacy)],
                         logs / "reference-build-and-compatibility.log", dict(os.environ), deadline, 1055)
        original = reference.verify_bundle(legacy / "bundle")
        require(original[0]["code_revision"] == expected and len(original[3]["calls"]) == 62,
                "F07 exact source and complete compatibility receipt required")
        result["stages"].append("one-original-build-and-complete-original-compatibility-engineering")
        bundle = output / "bundle"
        bundle.mkdir()
        (legacy / "bundle").rename(bundle / "reference")
        shutil.copyfile(legacy / "ci-receipt.json", bundle / PATHS["reference_ci_receipt"])
        binary, build_receipt = bundle / PATHS["runner"], bundle / PATHS["build_receipt"]
        engineering = bundle / "linear-engineering"
        previous.command([sys.executable, "-B", str(ROOT / FIXTURE), "--binary", str(binary),
                          "--output", str(engineering), "--build-receipt", str(build_receipt), "--code-revision", expected],
                         logs / "linear-engineering.log", execution_environment(bundle), deadline, 125)
        report = engineering_record(engineering / "engineering.json", expected,
                                    original[2]["binary_sha256"], original[2]["build_receipt_sha256"])
        require(reference.normalized_runtime(report["runtime_identity"]) == reference.normalized_runtime(original[2]["runtime_identity"]),
                "F07 portable linear engineering uses a different host/library identity")
        reference.research_runtime_binding(report["runtime_identity"], original[2], bundle / "reference")
        require(committed_controls(expected) == result["controls_sha256"], "F07 controls changed during engineering")
        reference.verify_bundle(bundle / "reference")
        previous.remaining(deadline, 1)
        manifest = {"schema_version": 1, "kind": KIND, "status": "PASS_ENGINEERING_ONLY", "code_revision": expected,
                    "controls_sha256": result["controls_sha256"], "paths": PATHS,
                    "engineering_budgets": ENGINEERING_BUDGETS,
                    "files": previous.manifest_files(bundle)}
        previous.source.write_json(bundle / "bundle.json", manifest)
        verify_bundle(bundle)
        archive = output / "webrtc-aec3-linear-tap-bundle.tar.gz"
        result["bundle_archive"] = {"path": archive.name, "sha256": previous.pack_bundle(bundle, archive), "size": archive.stat().st_size}
        previous.remaining(deadline, 1)
        result["stages"].append("same-binary-explicit-linear-engineering-and-pure-bundle-readback")
        result["status"] = "PASS_ENGINEERING_ONLY"
        result["elapsed_seconds"] = time.monotonic() - started
        previous.source.write_json(output / "ci-receipt.json", result)
        previous.remaining(deadline, 1)
        return result
    except Exception as error:
        result["status"], result["error"] = "FAIL", str(error)
        result["elapsed_seconds"] = time.monotonic() - started
        invalidate_success(output)
        path = output / "ci-receipt.json"
        if path.exists():
            path.rename(output / "ci-receipt-before-failure.json")
        previous.source.write_json(path, result)
        raise


def engineering(root: Path, output: Path) -> dict:
    """The new host runs only the 13 frozen linear fixtures, never speech."""
    started = time.monotonic()
    deadline = started + 120
    root, output = previous.source.safe_path(root), previous.source.safe_path(output)
    require(not output.exists() and previous.source.separate(root, output), "F07 fresh host output outside bundle required")
    verified = verify_bundle(root)
    output.mkdir(parents=True)
    receipt = output / "engineering/engineering.json"
    result = {"schema_version": 1, "status": "FAIL", "code_revision": verified["manifest"]["code_revision"],
              "science_calls": 0, "compile_calls": 0, "compatibility_reexecution": False,
              "bundle_directory": str(root), "execution_output": str(output),
              "bundle_manifest_sha256": sha256((root / "bundle.json").read_bytes())}
    try:
        paths = verified["paths"]
        previous.command([sys.executable, "-B", str(ROOT / FIXTURE), "--binary", str(paths["runner"]),
                          "--output", str(receipt.parent), "--build-receipt", str(paths["build_receipt"]),
                          "--code-revision", result["code_revision"]],
                         output / "engineering.log", execution_environment(root), deadline, 120)
        adapter = verified["reference"][2]
        report = engineering_record(receipt, result["code_revision"], adapter["binary_sha256"], adapter["build_receipt_sha256"])
        observed = previous.runtime_identity(paths["runner"], execution_environment(root))
        require(reference.normalized_runtime(observed) == reference.normalized_runtime(report["runtime_identity"]),
                "F07 host runtime changed after its engineering fixtures")
        reference.research_runtime_binding(observed, adapter, root / "reference")
        verify_bundle(root)
        previous.remaining(deadline, 1)
        result.update(status="PASS_ENGINEERING_ONLY", receipt="engineering/engineering.json",
                      receipt_sha256=sha256(receipt.read_bytes()), binary_sha256=report["binary_sha256"],
                      elapsed_seconds=time.monotonic() - started)
        previous.source.write_json(output / "host-engineering.json", result)
        previous.remaining(deadline, 1)
        return result
    except Exception as error:
        result.update(status="FAIL", error=str(error), elapsed_seconds=time.monotonic() - started)
        prior = output / "host-engineering.json"
        if prior.exists():
            prior.rename(output / "host-engineering-before-failure.json")
        previous.source.write_json(output / "host-engineering.json", result)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("select")
    command = commands.add_parser("run")
    command.add_argument("--expected-head", required=True)
    command.add_argument("--output", type=Path, required=True)
    command = commands.add_parser("verify")
    command.add_argument("--bundle", type=Path, required=True)
    command = commands.add_parser("engineering")
    command.add_argument("--bundle", type=Path, required=True)
    command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "select":
            select_workflow()
        elif args.command == "run":
            print(json.dumps(run(args.expected_head, args.output), sort_keys=True))
        elif args.command == "engineering":
            print(json.dumps(engineering(args.bundle, args.output), sort_keys=True))
        else:
            verified = verify_bundle(args.bundle)
            print(json.dumps({"status": "PASS_ENGINEERING_BUNDLE_READBACK", "code_revision": verified["manifest"]["code_revision"],
                              "sdk_calls": 0, "compile_calls": 0, "speech_calls": 0}, sort_keys=True))
        return 0
    except (ValueError, RuntimeError, OSError, KeyError, subprocess.SubprocessError) as error:
        print("webrtc-aec3-linear-tap-ci: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
