#!/usr/bin/env python3
"""FE06 fixed synthetic hard-signature engineering lane; NOT acoustic qualification."""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
import re
import shutil
import tempfile

from contracts import ROOT, hex_digest, load_json, require, sha256, verified_file
from libfvad_reference import run_logged, seal_output, write_json

HERE = Path(__file__).resolve().parent
PLAN = ROOT / ".github/research/frontend-evolution-v1/mic-fault-control-d0.json"
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
           check_negatives: bool = True) -> dict:
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
    for name in SOURCES:
        require((root / "source" / name).read_bytes() == (HERE / name).read_bytes(),
                "FE06 source bytes drift: " + name)
    report = load_json(root / "result.json")
    require(set(report) == {"schema_version", "experiment_id", "execution_source_revision",
                            "decision", "shipping_authority", "dataset_role", "arm_qualified",
                            "executables", "runs", "repeated_native"},
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
    require(set(report["runs"]) == set(targets) and set(report["executables"]) == set(targets),
            "FE06 target coverage incomplete")
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
    repeat_path = verified_file(root, "run-native-repeat.json")
    require(sha256(repeat_path.read_bytes()) == report["repeated_native"],
            "FE06 repeated execution receipt mismatch")
    inspect(load_json(repeat_path))
    require(load_json(repeat_path) == load_json(root / "run-native.json"),
            "FE06 repeat changed input/processing/masks")
    if check_negatives:
        negatives = load_json(root / "negative-evidence.json")
        require(set(negatives) == {"status", "kinds"} and negatives["status"] == "PASS"
                and negatives["kinds"] == ["promotion", "decision", "source", "missing-case",
                                           "latency", "mask", "binary", "output-fingerprint"],
                "FE06 resealed semantic negatives absent")
    return {"status": "MIC_FAULT_HARD_SIGNATURE_D0_ENGINEERING_PASS",
            "cases_per_target": 22, "targets": targets,
            "shipping_authority": False, "decision": DECISION}


def resealed_negatives(root: Path, revision: str) -> list[str]:
    kinds = ("promotion", "decision", "source", "missing-case", "latency", "mask",
             "binary", "output-fingerprint")
    for kind in kinds:
        with tempfile.TemporaryDirectory(prefix="fe06-negative-") as name:
            scratch = Path(name) / "evidence"
            shutil.copytree(root, scratch)
            report = load_json(scratch / "result.json")
            run = load_json(scratch / "run-native.json")
            if kind == "promotion": report["shipping_authority"] = True
            elif kind == "decision": report["decision"] = "PROMOTE_SHIPPING"
            elif kind == "source": report["execution_source_revision"] = "a"*40
            elif kind == "missing-case": run["cases"].pop()
            elif kind == "latency": run["cases"][6]["first_frame"] = 400
            elif kind == "mask": run["cases"][6]["final_mask"] = 15
            elif kind == "binary":
                binary = scratch / "bin/native"
                data = binary.read_bytes()
                binary.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
            elif kind == "output-fingerprint": run["cases"][6]["output_fnv64"] = "f"*16
            if kind in {"missing-case", "latency", "mask", "output-fingerprint"}:
                write_json(scratch / "run-native.json", run)
                report["runs"]["native"] = sha256((scratch / "run-native.json").read_bytes())
            write_json(scratch / "result.json", report)
            seal_output(scratch, report)  # integrity alone must NOT approve changed semantics
            try:
                verify(scratch, revision, check_negatives=False)
            except (ValueError, KeyError, AssertionError) as exc:
                require(str(exc), "FE06 negative rejection lacked cause")
            else:
                raise ValueError("resealed FE06 negative accepted: " + kind)
    return list(kinds)


def qualify(root: Path, revision: str, require_arm: bool) -> dict:
    require(hex_digest(revision, 40) and not root.exists(), "FE06 exact head/new output required")
    root.mkdir(parents=True)
    shutil.copyfile(PLAN, root / "experiment.json")
    (root / "source").mkdir()
    (root / "bin").mkdir()
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
        run_logged([root / "bin" / target], root / ("run-" + target + ".json"), timeout=360)
        inspect(load_json(root / ("run-" + target + ".json")))
    run_logged([root / "bin/native"], root / "run-native-repeat.json", timeout=360)
    require(load_json(root / "run-native-repeat.json") == load_json(root / "run-native.json"),
            "nondeterministic FE06 native run")
    has_arm = shutil.which("arm-linux-gnueabihf-gcc") and shutil.which("qemu-arm")
    require(bool(has_arm) or not require_arm, "FE06 Arm/QEMU required but unavailable")
    if has_arm:
        command = ["arm-linux-gnueabihf-gcc", *FLAGS, "-mcpu=cortex-a32",
                   "-mfpu=neon-fp-armv8", "-mfloat-abi=hard",
                   *native, "-lm", "-o", str(root / "bin/arm")]
        commands.append(command)
        run_logged(command, root / "build-arm.log")
        run_logged(["qemu-arm", "-cpu", "max", "-L", "/usr/arm-linux-gnueabihf",
                    root / "bin/arm"], root / "run-arm.json", timeout=360)
        inspect(load_json(root / "run-arm.json"))
    write_json(root / "build-commands.json", {"commands": commands})
    targets = ["native", "sanitized"] + (["arm"] if has_arm else [])
    report = {
        "schema_version": 1, "experiment_id": policy()["experiment_id"],
        "execution_source_revision": revision, "decision": DECISION,
        "shipping_authority": False, "dataset_role": "regression",
        "arm_qualified": bool(has_arm),
        "executables": {x: sha256((root / "bin" / x).read_bytes()) for x in targets},
        "runs": {x: sha256((root / ("run-" + x + ".json")).read_bytes()) for x in targets},
        "repeated_native": sha256((root / "run-native-repeat.json").read_bytes()),
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
    args = parser.parse_args()
    if args.self_test:
        p = policy()
        require(len(expected_ids()) == p["matrix_cases"], "FE06 matrix not fixed")
        print("FE06 fixed synthetic contract: PASS")
        return 0
    require(args.output is not None, "--output required")
    if args.verify:
        result = verify(args.output, args.execution_source, args.require_arm)
    else:
        require(args.execution_source is not None, "execution source required")
        result = qualify(args.output, args.execution_source, args.require_arm)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
