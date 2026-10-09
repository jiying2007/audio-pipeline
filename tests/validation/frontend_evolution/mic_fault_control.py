#!/usr/bin/env python3
"""FE06 fixed synthetic hard-signature engineering lane; NOT acoustic qualification."""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile

from contracts import ROOT, hex_digest, load_json, require, sha256, verified_file
from libfvad_reference import run_logged, seal_output, write_json

HERE = Path(__file__).resolve().parent
PLAN = ROOT / ".github/research/frontend-evolution-v1/mic-fault-control-d0.json"
EVIDENCE_PLAN = ROOT / ".github/research/frontend-evolution-v1/mic-fault-evidence-v2.json"
SOURCES = (
    "array_native.c", "array_native.h",
    "mic_fault_control.c", "mic_fault_control.h", "mic_fault_control_test.c",
    "mic_fault_control.py", "contracts.py", "libfvad_reference.py"
)
FLAGS = ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
         "-Wconversion", "-Wshadow", "-pedantic", "-ffp-contract=off"]
NEGATIVE = ("quiet", "coherent", "weak-side", "diffuse", "motor-tone", "clipped")
POSITIVE = ("hard-zero", "rail-plus", "rail-minus", "sequential", "recovery")
DECISION = "MIC_FAULT_HARD_SIGNATURE_D0_NO_PROMOTION"
FNV = re.compile(r"^[0-9a-f]{16}$")
PART_SUFFIX = {"input": "input.f32le", "output": "output.f32le", "mask": "mask.u32le"}
POST_D0_NEGATIVES = (
    "promotion", "decision", "source", "missing-case", "latency", "mask",
    "binary", "output-fingerprint", "output-samples", "future-prefix",
    "mask-trace", "trace-receipt"
)


def evidence_policy() -> dict:
    p = load_json(EVIDENCE_PLAN)
    require(p["schema_version"] == 1 and
            p["study"] == "FE06-MIC-FAULT-CONTROL-D0-EVIDENCE-HARDENING" and
            p["authority"] == "POST_INITIAL_D0_EVIDENCE_EXTENSION_NOT_INDEPENDENT_CONFIRMATION" and
            p["future_first_changed_frame"] == 1200 and p["frame_samples"] == 160 and
            p["frame_count"] == 1600 and p["microphone_channels"] == 4 and
            p["complete_digest_targets"] == ["native", "sanitized", "arm", "future-native"] and
            p["captured_variants"] == ["native", "future-native"] and
            p["selected_raw_capture_cases"] ==
            ["ULA4-coherent", "ULA4-hard-zero", "UCA4-diffuse", "UCA4-sequential"] and
            p["replay_all_cases"] is True and p["no_shipment"] is True and
            p["no_data_selection"] is True, "post-D0 evidence authority drift")
    return p


def fnv64(data: bytes) -> str:
    state = 14695981039346656037
    for value in data:
        state = ((state ^ value) * 1099511628211) & ((1 << 64) - 1)
    return f"{state:016x}"


def part_path(directory: Path, case_id: str, kind: str) -> Path:
    return directory / f"{case_id}.{PART_SUFFIX[kind]}"


def trace_row(directory: Path, case_id: str) -> dict:
    expected = {
        "input": 1600 * 160 * 4 * 4,
        "output": 1600 * 160 * 4,
        "mask": 1600 * 4,
    }
    result = {}
    for kind, length in expected.items():
        path = part_path(directory, case_id, kind)
        require(path.is_file() and not path.is_symlink(), "FE06 missing trace: " + str(path))
        require(path.stat().st_size == length, "FE06 lost/extra raw stream samples")
        result[kind] = {"sha256": sha256(path.read_bytes()), "bytes": length}
    return result


def build_trace_receipt(root: Path, targets: list[str]) -> dict:
    p = evidence_policy()
    trace_root = root / "traces"
    variant_names = [*targets, "future-native"]
    runs = {}
    all_ids = expected_ids()
    for variant in variant_names:
        directory = trace_root / variant
        require(directory.is_dir(), "missing FE06 trace variant " + variant)
        expected = {f"{case}.{suffix}" for case in all_ids for suffix in PART_SUFFIX.values()}
        require({v.name for v in directory.iterdir()} == expected, "FE06 extra/missing trace files")
        runs[variant] = {case: trace_row(directory, case) for case in all_ids}
    first = 1200
    prefix_bytes = {"input": first * 160 * 4 * 4, "output": first * 160 * 4, "mask": first * 4}
    causality = {}
    for case in all_ids:
        record = {}
        for kind in PART_SUFFIX:
            baseline = part_path(trace_root / "native", case, kind).read_bytes()
            future = part_path(trace_root / "future-native", case, kind).read_bytes()
            size = prefix_bytes[kind]
            require(baseline[:size] == future[:size],
                    "FE06 future leaked into unchanged prefix: " + case + " " + kind)
            if kind == "mask":
                require(baseline == future, "FE06 future changed fault/mask decisions")
            else:
                require(baseline[size:] != future[size:],
                        "FE06 future perturbation did not change stream: " + case)
            record[kind + "_prefix_sha256"] = sha256(baseline[:size])
        causality[case] = record
        for target in targets:
            if target == "native": continue
            require(runs[target][case]["input"] == runs["native"][case]["input"],
                    "FE06 cross-target raw input changed")
            require(runs[target][case]["mask"] == runs["native"][case]["mask"],
                    "FE06 cross-target detector/mask decisions changed")
    captures = []
    for variant in p["captured_variants"]:
        for case in p["selected_raw_capture_cases"]:
            destination = root / "captures" / variant
            destination.mkdir(parents=True, exist_ok=True)
            for kind in PART_SUFFIX:
                source = part_path(trace_root / variant, case, kind)
                dst = part_path(destination, case, kind)
                require(not dst.exists(), "FE06 overwrite of captured sample")
                shutil.copyfile(source, dst)
                captures.append(f"{variant}/{dst.name}")
    return {
        "schema_version": 1,
        "experiment_id": policy()["experiment_id"],
        "evidence_study": p["study"],
        "evidence_authority": p["authority"],
        "future_first_changed_frame": first,
        "runs": runs,
        "causality": causality,
        "captures": sorted(captures),
        "all_target_inputs_identical": True,
        "all_target_masks_identical": True,
        "future_changes_after_prefix_only": True,
        "shipping_authority": False,
    }


def verify_trace_receipt(root: Path, receipt: dict, targets: list[str]) -> None:
    p = evidence_policy()
    ids = expected_ids()
    require(set(receipt) == {
        "schema_version", "experiment_id", "evidence_study", "evidence_authority",
        "future_first_changed_frame", "runs", "causality", "captures",
        "all_target_inputs_identical", "all_target_masks_identical",
        "future_changes_after_prefix_only", "shipping_authority"
    }, "FE06 raw digest receipt schema drift")
    require(receipt["schema_version"] == 1 and
            receipt["experiment_id"] == policy()["experiment_id"] and
            receipt["evidence_study"] == p["study"] and
            receipt["evidence_authority"] == p["authority"] and
            receipt["future_first_changed_frame"] == 1200 and
            receipt["shipping_authority"] is False and
            receipt["all_target_inputs_identical"] is True and
            receipt["all_target_masks_identical"] is True and
            receipt["future_changes_after_prefix_only"] is True,
            "FE06 raw digest receipt authority drift")
    variants = [*targets, "future-native"]
    require(set(receipt["runs"]) == set(variants) and
            set(receipt["causality"]) == set(ids),
            "FE06 missing raw streams or causality cases")
    expected_bytes = {"input": 4096000, "output": 1024000, "mask": 6400}
    for variant in variants:
        cases = receipt["runs"][variant]
        require(set(cases) == set(ids), "FE06 missing per-target digest cases")
        for case in ids:
            require(set(cases[case]) == set(PART_SUFFIX), "FE06 incomplete raw stream kinds")
            for kind in PART_SUFFIX:
                value = cases[case][kind]
                require(set(value) == {"sha256", "bytes"} and
                        hex_digest(value["sha256"]) and
                        type(value["bytes"]) is int and
                        value["bytes"] == expected_bytes[kind],
                        "FE06 incomplete or invalid stream digest")
    for case in ids:
        proofs = receipt["causality"][case]
        require(set(proofs) == {kind + "_prefix_sha256" for kind in PART_SUFFIX} and
                all(hex_digest(value) for value in proofs.values()),
                "FE06 unbound causality prefix receipt")
        for target in targets:
            require(receipt["runs"][target][case]["input"] == receipt["runs"]["native"][case]["input"]
                    and receipt["runs"][target][case]["mask"] == receipt["runs"]["native"][case]["mask"],
                    "FE06 cross-target inputs/masks do not match")
    expected_capture_names = sorted(
        f"{variant}/{case}.{suffix}"
        for variant in p["captured_variants"]
        for case in p["selected_raw_capture_cases"]
        for suffix in PART_SUFFIX.values()
    )
    require(receipt["captures"] == expected_capture_names, "FE06 partial/duplicate raw captures")
    saved_root = root / "captures"
    actual_names = sorted(f.relative_to(saved_root).as_posix() for f in saved_root.rglob("*") if f.is_file())
    require(actual_names == expected_capture_names, "FE06 unexpected/missing retained capture")
    for variant in p["captured_variants"]:
        run = load_json(root / ("run-" + variant + ".json"))
        case_records = {c["case_id"]: c for c in run["cases"]}
        for case in p["selected_raw_capture_cases"]:
            for kind in PART_SUFFIX:
                path = part_path(saved_root / variant, case, kind)
                data = path.read_bytes()
                require(len(data) == receipt["runs"][variant][case][kind]["bytes"],
                        "FE06 captured stream length mismatch")
                require(sha256(data) == receipt["runs"][variant][case][kind]["sha256"],
                        "FE06 captured raw stream SHA drift")
                require(fnv64(data) == case_records[case][kind + "_fnv64"],
                        "FE06 captured stream does not match C measurement")
            if variant == "native":
                # Bind the captured same-prefix samples to the per-case causal receipt.
                for kind in PART_SUFFIX:
                    data = part_path(saved_root / variant, case, kind).read_bytes()
                    span = (1200 * 160 * 4 * 4 if kind == "input" else
                            1200 * 160 * 4 if kind == "output" else 1200 * 4)
                    require(sha256(data[:span]) == receipt["causality"][case][kind + "_prefix_sha256"],
                            "FE06 stable-prefix capture mismatch")
            else:
                for kind in PART_SUFFIX:
                    base = part_path(saved_root / "native", case, kind).read_bytes()
                    future = part_path(saved_root / "future-native", case, kind).read_bytes()
                    span = (1200 * 160 * 4 * 4 if kind == "input" else
                            1200 * 160 * 4 if kind == "output" else 1200 * 4)
                    require(base[:span] == future[:span], "FE06 captured causality boundary leaked")
                    if kind == "mask":
                        require(base == future, "FE06 captured future changed mask")
                    else:
                        require(base[span:] != future[span:],
                                "FE06 future capture lacks independent perturbation")


def replay_exact_streams(root: Path, receipt: dict, targets: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="fe06-replay-", dir=root.parent) as temp_name:
        scratch = Path(temp_name)
        (scratch / "traces").mkdir()
        for variant in [*targets, "future-native"]:
            trace_dir = scratch / "traces" / variant
            trace_dir.mkdir()
            target = "native" if variant == "future-native" else variant
            binary = verified_file(root, "bin/" + target)
            prefix = (["qemu-arm", "-cpu", "max", "-L", "/usr/arm-linux-gnueabihf"]
                      if target == "arm" else [])
            out = scratch / f"run-{variant}.json"
            command = [*prefix, binary, trace_dir,
                       "future" if variant == "future-native" else "base"]
            if variant not in ("native", "future-native"):
                command.append(scratch / "traces" / "native")
            run_logged(command, out, timeout=360)
            require(load_json(out) == load_json(root / f"run-{variant}.json"),
                    "FE06 independent replay changed C outcome")
        computed = build_trace_receipt(scratch, targets)
        require(computed == receipt, "FE06 independent complete raw-stream replay mismatch")



def policy() -> dict:
    p = load_json(PLAN)
    require(p["schema_version"] == 1 and p["experiment_id"] == "FE06-MIC-FAULT-CONTROL-D0"
            and p["decision"] == DECISION and p["shipping_authority"] is False
            and p["auto_promote"] is False and p["dataset_role"] == "regression"
            and p["sample_rate_hz"] == 16000 and p["outer_frame_samples"] == 160
            and p["frames_per_case"] == 1600 and p["matrix_cases"] == 22,
            "FE06 fixed policy mismatch")
    require(p["geometry"] == ["ULA4", "UCA4"] and p["negative_scenes"] == list(NEGATIVE)
            and p["positive_scenes"] == list(POSITIVE)
            and p["hard_signatures"]["complete_consecutive_frames"] == 3
            and p["hard_signatures"]["other_channels_required"] == 2
            and p["hard_signatures"]["zero_requires_other_rms_at_least"] == 0.01
            and p["hard_signatures"]["suggested_mask_only"] is True
            and p["hard_signatures"]["automatic_muting"] is False
            and p["expected"] == {
                "initial_active_mask": 15,
                "first_fault_start_frame": 400, "first_suggestion_frame": 402,
                "first_proposed_mask": 14,
                "second_fault_start_frame": 800, "second_suggestion_frame": 802,
                "second_proposed_mask": 10,
                "recovery_end_frame_exclusive": 1000, "explicit_reenable_frame": 1020,
            }, "FE06 preregistration drift")
    return p


def expected_ids() -> list[str]:
    return [f"{geo}-{scene}" for geo in ("ULA4", "UCA4") for scene in (*NEGATIVE, *POSITIVE)]


def inspect(raw: dict) -> None:
    p = policy()
    require(set(raw) == {"schema_version", "experiment_id", "shipping_authority",
                         "decision", "cases", "case_count", "assertions"},
            "FE06 raw report schema drift")
    require(raw["schema_version"] == 1 and raw["experiment_id"] == p["experiment_id"]
            and raw["shipping_authority"] is False and raw["decision"] == DECISION
            and type(raw["case_count"]) is int and raw["case_count"] == p["matrix_cases"]
            and type(raw["assertions"]) is int and raw["assertions"] >= 5000000,
            "FE06 executable coverage/authority invalid")
    cases = raw["cases"]
    require(isinstance(cases, list) and len(cases) == p["matrix_cases"]
            and [r["case_id"] for r in cases] == expected_ids(), "FE06 incomplete/duplicate matrix")
    fields = {"case_id", "geometry", "scene", "frames", "suggestions", "first_frame",
              "second_frame", "final_mask", "explicit_reenables", "input_fnv64",
              "output_fnv64", "mask_fnv64", "delta_rms", "max_discontinuity"}
    for case in cases:
        require(set(case) == fields and
                case["case_id"] == case["geometry"] + "-" + case["scene"]
                and case["frames"] == p["frames_per_case"], "FE06 case schema/count drift")
        scene = case["scene"]
        count = 0 if scene in NEGATIVE else 2 if scene == "sequential" else 1
        final_mask = 15 if scene in NEGATIVE or scene == "recovery" else 10 if scene == "sequential" else 14
        require(type(case["suggestions"]) is int and case["suggestions"] == count
                and type(case["first_frame"]) is int
                and case["first_frame"] == (4294967295 if count == 0 else 402)
                and type(case["second_frame"]) is int
                and case["second_frame"] == (802 if count == 2 else 4294967295)
                and type(case["final_mask"]) is int and case["final_mask"] == final_mask
                and type(case["explicit_reenables"]) is int
                and case["explicit_reenables"] == (1 if scene == "recovery" else 0),
                "FE06 hard signature latency, false-positive or fallback failure")
        require(all(isinstance(case[k], str) and FNV.fullmatch(case[k]) for k in
                    ("input_fnv64", "output_fnv64", "mask_fnv64")),
                "missing complete-stream fingerprint")
        for key in ("delta_rms", "max_discontinuity"):
            require(type(case[key]) in (float, int) and math.isfinite(case[key])
                    and case[key] >= 0.0, "invalid output/transient telemetry")
        if scene in POSITIVE:
            require(case["delta_rms"] > 0.0, "fault did not affect BF output")
    # These are fixed engineering controls, not real mic health or acoustic FAR/FRR.


def verify(root: Path, revision: str | None = None, require_arm: bool = False,
           check_negatives: bool = True, replay: bool = False) -> dict:
    require(not (root / "failure.json").exists(), "failed engineering execution")
    require(all(not p.is_symlink() for p in root.rglob("*")), "symlink evidence")
    manifest = load_json(root / "manifest.json")
    actual = {p.relative_to(root).as_posix(): sha256(verified_file(root, p.relative_to(root).as_posix()).read_bytes())
              for p in root.rglob("*") if p.is_file() and p.name not in ("manifest.json", "SHA256SUMS")}
    require(manifest["files"] == actual and manifest["shipping_authority"] is False,
            "FE06 evidence file/hash drift")
    sums = {}
    for line in (root / "SHA256SUMS").read_text().splitlines():
        digest, path = line.split("  ", 1)
        require(path not in sums, "duplicate FE06 digest")
        sums[path] = digest
    require(sums == {**actual, "manifest.json": sha256((root / "manifest.json").read_bytes())},
            "FE06 digest set drift")
    require((root / "experiment.json").read_bytes() == PLAN.read_bytes(),
            "changed FE06 experiment")
    require((root / "evidence-contract.json").read_bytes() == EVIDENCE_PLAN.read_bytes(),
            "changed FE06 evidence extension")
    require(not (root / "traces").exists(), "unbounded scratch traces retained")
    for name in SOURCES:
        require((root / "source" / name).read_bytes() == (HERE / name).read_bytes(),
                "FE06 source bytes drift: " + name)
    report = load_json(root / "result.json")
    require(set(report) == {"schema_version", "experiment_id", "execution_source_revision",
                            "decision", "shipping_authority", "dataset_role", "arm_qualified",
                            "executables", "runs", "repeated_native", "trace_receipt_sha256"},
            "FE06 result schema drift")
    require(report["schema_version"] == 1 and report["experiment_id"] == policy()["experiment_id"]
            and report["decision"] == DECISION and report["shipping_authority"] is False
            and report["dataset_role"] == "regression"
            and type(report["arm_qualified"]) is bool
            and (not require_arm or report["arm_qualified"]),
            "FE06 claim/policy drift")
    require(hex_digest(report["execution_source_revision"], 40)
            and (revision is None or report["execution_source_revision"] == revision),
            "FE06 execution source mismatch")
    targets = ["native", "sanitized"] + (["arm"] if report["arm_qualified"] else [])
    require(set(report["runs"]) == set([*targets, "future-native"]) and
            set(report["executables"]) == set(targets),
            "FE06 target coverage incomplete")
    trace_path = verified_file(root, "trace-receipt.json")
    require(sha256(trace_path.read_bytes()) == report["trace_receipt_sha256"],
            "FE06 digest receipt identity mismatch")
    receipt = load_json(trace_path)
    verify_trace_receipt(root, receipt, targets)
    for target in targets:
        binary = verified_file(root, "bin/" + target)
        require(sha256(binary.read_bytes()) == report["executables"][target]
                and binary.read_bytes()[:4] == b"\x7fELF", "FE06 binary mismatch")
        if target == "arm":
            require(binary.read_bytes()[4:6] == b"\x01\x01" and
                    int.from_bytes(binary.read_bytes()[18:20], "little") == 40,
                    "FE06 missing actual AArch32 executable")
        raw_path = verified_file(root, "run-" + target + ".json")
        require(sha256(raw_path.read_bytes()) == report["runs"][target],
                "FE06 execution receipt mismatch")
        inspect(load_json(raw_path))
    future_path = verified_file(root, "run-future-native.json")
    require(sha256(future_path.read_bytes()) == report["runs"]["future-native"],
            "FE06 future execution receipt mismatch")
    inspect(load_json(future_path))
    repeat_path = verified_file(root, "run-native-repeat.json")
    require(sha256(repeat_path.read_bytes()) == report["repeated_native"],
            "FE06 repeated execution receipt mismatch")
    inspect(load_json(repeat_path))
    require(load_json(repeat_path) == load_json(root / "run-native.json"),
            "FE06 repeat changed input/processing/masks")
    if check_negatives:
        negatives = load_json(root / "negative-evidence.json")
        require(set(negatives) == {"status", "kinds"} and negatives["status"] == "PASS"
                and negatives["kinds"] == list(POST_D0_NEGATIVES),
                "FE06 resealed semantic negatives absent")
    if replay:
        replay_exact_streams(root, receipt, targets)
    return {"status": "MIC_FAULT_HARD_SIGNATURE_D0_ENGINEERING_PASS",
            "cases_per_target": 22, "targets": targets,
            "shipping_authority": False, "decision": DECISION}


def resealed_negatives(root: Path, revision: str) -> list[str]:
    # Hardlinks avoid copying retained raw waveforms a dozen times. Every
    # mutation first unlinks its target, so the source artifact is untouched.
    # Scratch directories are siblings on the same filesystem.
    expected_messages = {
        "promotion": "FE06 claim/policy drift",
        "decision": "FE06 claim/policy drift",
        "source": "FE06 execution source mismatch",
        "missing-case": "FE06 incomplete/duplicate matrix",
        "latency": "FE06 hard signature latency",
        "mask": "FE06 hard signature latency",
        "binary": "FE06 binary mismatch",
        "output-fingerprint": "FE06 captured stream does not match C measurement",
        "output-samples": "FE06 captured raw stream SHA drift",
        "future-prefix": "FE06 captured causality boundary leaked",
        "mask-trace": "FE06 captured raw stream SHA drift",
        "trace-receipt": "FE06 stable-prefix capture mismatch",
    }

    def replace_file(path: Path, data: bytes) -> None:
        path.unlink()  # break the hardlink BEFORE writing mutated content
        path.write_bytes(data)

    def replace_json(path: Path, payload: dict) -> None:
        path.unlink()
        write_json(path, payload)

    for kind in POST_D0_NEGATIVES:
        with tempfile.TemporaryDirectory(prefix="fe06-negative-", dir=root.parent) as name:
            scratch = Path(name) / "evidence"
            shutil.copytree(root, scratch, copy_function=os.link)
            report = load_json(scratch / "result.json")
            run = load_json(scratch / "run-native.json")
            receipt = load_json(scratch / "trace-receipt.json")
            if kind == "promotion":
                report["shipping_authority"] = True
            elif kind == "decision":
                report["decision"] = "PROMOTE_SHIPPING"
            elif kind == "source":
                report["execution_source_revision"] = "a"*40
            elif kind == "missing-case":
                run["cases"].pop()
            elif kind == "latency":
                run["cases"][6]["first_frame"] = 400
            elif kind == "mask":
                run["cases"][6]["final_mask"] = 15
            elif kind == "binary":
                path = scratch / "bin/native"
                data = path.read_bytes()
                replace_file(path, data[:-1] + bytes([data[-1] ^ 1]))
            elif kind == "output-fingerprint":
                run["cases"][6]["output_fnv64"] = "f"*16
            elif kind in ("output-samples", "future-prefix", "mask-trace"):
                if kind == "output-samples":
                    path = scratch / "captures/native/ULA4-hard-zero.output.f32le"
                elif kind == "future-prefix":
                    path = scratch / "captures/future-native/ULA4-coherent.input.f32le"
                else:
                    path = scratch / "captures/native/ULA4-hard-zero.mask.u32le"
                data = bytearray(path.read_bytes())
                data[0 if kind == "future-prefix" else -1] ^= 1
                replace_file(path, bytes(data))
                if kind == "future-prefix":
                    # Keep the independently resealed stream digest and
                    # C raw-input fingerprint consistent; causality still
                    # rejects the changed *common* input prefix.
                    future = load_json(scratch / "run-future-native.json")
                    case = next(row for row in future["cases"] if row["case_id"] == "ULA4-coherent")
                    case["input_fnv64"] = fnv64(bytes(data))
                    replace_json(scratch / "run-future-native.json", future)
                    report["runs"]["future-native"] = sha256(
                        (scratch / "run-future-native.json").read_bytes())
                    receipt["runs"]["future-native"]["ULA4-coherent"]["input"]["sha256"] = sha256(bytes(data))
                    replace_json(scratch / "trace-receipt.json", receipt)
                    report["trace_receipt_sha256"] = sha256(
                        (scratch / "trace-receipt.json").read_bytes())
            elif kind == "trace-receipt":
                receipt["causality"]["ULA4-coherent"]["output_prefix_sha256"] = "e"*64
                replace_json(scratch / "trace-receipt.json", receipt)
                report["trace_receipt_sha256"] = sha256(
                    (scratch / "trace-receipt.json").read_bytes())
            else:
                raise AssertionError("unsupported FE06 negative " + kind)

            if kind in {"missing-case", "latency", "mask", "output-fingerprint"}:
                replace_json(scratch / "run-native.json", run)
                report["runs"]["native"] = sha256((scratch / "run-native.json").read_bytes())
            replace_json(scratch / "result.json", report)
            (scratch / "manifest.json").unlink()
            (scratch / "SHA256SUMS").unlink()
            seal_output(scratch, report)  # checksum reseal is intentionally insufficient
            try:
                verify(scratch, revision, check_negatives=False, replay=False)
            except (ValueError, KeyError, AssertionError) as exc:
                require(expected_messages[kind] in str(exc),
                        f"FE06 negative {kind} rejected for the wrong reason: {exc}")
            else:
                raise ValueError("resealed FE06 negative accepted: " + kind)
    return list(POST_D0_NEGATIVES)


def qualify(root: Path, revision: str, require_arm: bool) -> dict:
    require(hex_digest(revision, 40) and not root.exists(), "FE06 exact head/new output required")
    root.mkdir(parents=True)
    shutil.copyfile(PLAN, root / "experiment.json")
    shutil.copyfile(EVIDENCE_PLAN, root / "evidence-contract.json")
    (root / "source").mkdir()
    (root / "bin").mkdir()
    (root / "traces").mkdir()
    for name in SOURCES:
        shutil.copyfile(HERE / name, root / "source" / name)
    native = [str(HERE / x) for x in ("array_native.c", "mic_fault_control.c",
                                      "mic_fault_control_test.c")]
    commands = []
    for target, prefix in [
        ("native", ["cc", *FLAGS]),
        ("sanitized", ["cc", *FLAGS, "-O1", "-g", "-fsanitize=address,undefined",
                       "-fno-omit-frame-pointer", "-fno-pie", "-no-pie"]),
    ]:
        command = [*prefix, *native, "-lm", "-o", str(root / "bin" / target)]
        commands.append(command)
        run_logged(command, root / ("build-" + target + ".log"))
        directory = root / "traces" / target
        directory.mkdir()
        execution = [root / "bin" / target, directory, "base"]
        if target != "native":
            execution.append(root / "traces" / "native")
        run_logged(execution, root / ("run-" + target + ".json"), timeout=360)
        inspect(load_json(root / ("run-" + target + ".json")))
    (root / "traces" / "native-repeat").mkdir()
    run_logged([root / "bin/native", root / "traces" / "native-repeat", "base"],
               root / "run-native-repeat.json", timeout=360)
    require(load_json(root / "run-native-repeat.json") == load_json(root / "run-native.json"),
            "nondeterministic FE06 native run")
    for case in expected_ids():
        require(trace_row(root / "traces" / "native-repeat", case) ==
                trace_row(root / "traces" / "native", case),
                "FE06 repeated complete PCM/output/mask bytes differ")
    shutil.rmtree(root / "traces" / "native-repeat")
    has_arm = shutil.which("arm-linux-gnueabihf-gcc") and shutil.which("qemu-arm")
    require(bool(has_arm) or not require_arm, "FE06 Arm/QEMU required but unavailable")
    if has_arm:
        command = ["arm-linux-gnueabihf-gcc", *FLAGS, "-mcpu=cortex-a32",
                   "-mfpu=neon-fp-armv8", "-mfloat-abi=hard",
                   *native, "-lm", "-o", str(root / "bin/arm")]
        commands.append(command)
        run_logged(command, root / "build-arm.log")
        (root / "traces" / "arm").mkdir()
        run_logged(["qemu-arm", "-cpu", "max", "-L", "/usr/arm-linux-gnueabihf",
                    root / "bin/arm", root / "traces" / "arm", "base",
                    root / "traces" / "native"], root / "run-arm.json", timeout=360)
        inspect(load_json(root / "run-arm.json"))
    (root / "traces" / "future-native").mkdir()
    run_logged([root / "bin" / "native", root / "traces" / "future-native", "future"],
               root / "run-future-native.json", timeout=360)
    inspect(load_json(root / "run-future-native.json"))
    write_json(root / "build-commands.json", {"commands": commands})
    targets = ["native", "sanitized"] + (["arm"] if has_arm else [])
    trace_receipt = build_trace_receipt(root, targets)
    write_json(root / "trace-receipt.json", trace_receipt)
    # Avoid duplicating hundreds of MB in retained artifacts. Exact per-case
    # SHA-256 remains independently reproducible from retained ELF + inputs.
    shutil.rmtree(root / "traces")
    report = {
        "schema_version": 1, "experiment_id": policy()["experiment_id"],
        "execution_source_revision": revision, "decision": DECISION,
        "shipping_authority": False, "dataset_role": "regression",
        "arm_qualified": bool(has_arm),
        "executables": {x: sha256((root / "bin" / x).read_bytes()) for x in targets},
        "runs": {x: sha256((root / ("run-" + x + ".json")).read_bytes())
                 for x in [*targets, "future-native"]},
        "repeated_native": sha256((root / "run-native-repeat.json").read_bytes()),
        "trace_receipt_sha256": sha256((root / "trace-receipt.json").read_bytes()),
    }
    write_json(root / "result.json", report)
    seal_output(root, report)
    kinds = resealed_negatives(root, revision)
    write_json(root / "negative-evidence.json", {"status": "PASS", "kinds": kinds})
    seal_output(root, report)
    return verify(root, revision, require_arm)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execution-source")
    parser.add_argument("--require-arm", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        p = policy()
        evidence_policy()
        require(len(expected_ids()) == p["matrix_cases"], "FE06 matrix not fixed")
        print("FE06 fixed synthetic contract: PASS")
        return 0
    require(args.output is not None, "--output required")
    if args.verify:
        result = verify(args.output, args.execution_source, args.require_arm,
                        replay=args.replay)
    else:
        require(args.execution_source is not None, "execution source required")
        result = qualify(args.output, args.execution_source, args.require_arm)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
