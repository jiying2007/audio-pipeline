#!/usr/bin/env python3
"""FE08 component-only resource measurement. Never a DUT timing/acoustic gate."""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import tempfile
from pathlib import Path

from contracts import ROOT, hex_digest, load_json, require, sha256, verified_file
from libfvad_reference import run_logged, seal_output, write_json

HERE = Path(__file__).resolve().parent
PLAN = ROOT / ".github/research/frontend-evolution-v1/array-resource-profile-v1.json"
SOURCES = ("array_native.h", "array_native.c", "array_resource_probe.c",
           "array_resource_qualification.py", "contracts.py", "libfvad_reference.py")
DECISION = "FE08_ARRAY_RESOURCE_CHARACTERIZATION_NO_PROMOTION"
PROFILES = [
    ("C1_LINEAR", 1, 0), ("C2_LINEAR", 2, 0), ("C2_FIR33", 2, 3),
    ("C4_FIR33", 4, 3), ("C4_SPATIAL33", 4, 4),
]
FLAGS = ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-Wconversion",
         "-Wshadow", "-pedantic", "-ffp-contract=off", "-fstack-usage"]
FORBIDDEN = {"malloc", "calloc", "realloc", "free", "fopen", "fprintf",
             "printf", "pthread_mutex_lock", "pthread_mutex_unlock"}
NEGATIVES = ["promotion", "decision", "missing-profile", "state-bound",
             "timing-order", "missing-arm", "binary"]


def check_plan() -> dict:
    p = load_json(PLAN)
    require(p.get("schema_version") == 1 and
            p.get("experiment_id") == "FE08-ARRAY-RESOURCE-CHARACTERIZATION-V1"
            and p.get("decision") == DECISION and p.get("shipping_authority") is False
            and p.get("component_only") is True and p.get("product_qualification") is False
            and p.get("dataset_role") == "regression"
            and p.get("component_arena_safety_bound_bytes") == 16384
            and p.get("sample_rate_hz") == 16000 and p.get("frame_samples") == 160
            and p.get("frames_per_profile") == 2000 and p.get("native_repeats") == 3
            and p.get("timing_clock") == "CLOCK_THREAD_CPUTIME_ID"
            and p.get("timing_gate") == "descriptive-no-hosted-threshold"
            and p.get("arm_aarch32_functional_required") is True
            and p.get("sanitizer_functional_required") is True
            and p.get("no_new_public_api") is True and p.get("no_software_release") is True,
            "FE08 preregistration authority drift")
    require([(c["name"], c["mic_count"], c["mode"]) for c in p["profiles"]] == PROFILES,
            "FE08 frozen profile set changed")
    return p


def parse_size(output: str) -> dict:
    sections = {".text": 0, ".rodata": 0}
    for line in output.splitlines():
        pieces = line.split()
        if len(pieces) < 3:
            continue
        for key in sections:
            if pieces[0] == key or pieces[0].startswith(key + "."):
                require(pieces[1].isdigit(), "FE08 unsupported ELF size output")
                sections[key] += int(pieces[1])
    require(sections[".text"] > 0 and sections[".rodata"] > 0,
            "FE08 missing ELF code or constants accounting")
    return {"text_bytes": sections[".text"], "rodata_bytes": sections[".rodata"]}


def read_size_receipt(root: Path, target: str) -> dict:
    """Resolve the sealed ELF receipt under the evidence root, not Path + str."""
    require(target in ("native", "sanitized", "arm"), "FE08 unexpected binary target")
    return parse_size((root / f"size-{target}.txt").read_text())


def parse_stack(path: Path) -> dict:
    """Keep frame-processing stack static; permit ONLY known bounded init wrappers."""
    entries, seen = [], set()
    init_wrappers = {"fe_array_init", "fe_array_init_spatial33"}
    for line in path.read_text().splitlines():
        parts = line.split("\t")
        require(len(parts) == 3 and parts[1].isdigit(), "FE08 malformed stack usage")
        function, size, kind = parts[0].rsplit(":", 1)[-1], int(parts[1]), parts[2]
        require(function not in seen, "FE08 duplicate stack function: " + function)
        seen.add(function)
        if kind != "static":
            require(function in init_wrappers and kind == "dynamic,bounded" and size <= 64,
                    f"FE08 unbounded/unapproved stack: {function} size={size} kind={kind}")
        require(size <= 16 * 1024, "FE08 unreasonable compiler stack bound")
        entries.append({"function": function, "bytes": size, "kind": kind})
    require("fe_array_process" in seen and
            next(x for x in entries if x["function"] == "fe_array_process")["kind"] == "static",
            "FE08 frame DSP must have compiler-static stack")
    require(init_wrappers.issubset(seen), "FE08 missing init wrappers")
    return {"max_single_function_bytes": max(x["bytes"] for x in entries),
            "functions": entries}

def profile_record(run: dict, timed: bool) -> list[dict]:
    p = check_plan()
    require(set(run) == {"schema_version", "scope", "shipping_authority",
                         "profiles", "profile_count", "timing_is_hosted_only"} and
            run["schema_version"] == 1 and run["scope"] == "FE08_ARRAY_COMPONENT_ONLY"
            and run["shipping_authority"] is False and
            run["profile_count"] == len(PROFILES) and
            run["timing_is_hosted_only"] is timed,
            "FE08 probe authority/schema mismatch")
    rows = run["profiles"]
    require(isinstance(rows, list) and len(rows) == len(PROFILES), "FE08 partial probe")
    expected_keys = {"name", "mic_count", "mode", "state_bytes", "frames",
                     "input_fnv64", "output_fnv64", "output_energy", "peak_abs", "timing"}
    for row, (name, microphones, mode) in zip(rows, PROFILES):
        require(set(row) == expected_keys and
                row["name"] == name and row["mic_count"] == microphones and
                row["mode"] == mode and row["frames"] == p["frames_per_profile"] and
                type(row["state_bytes"]) is int and
                0 < row["state_bytes"] <= p["component_arena_safety_bound_bytes"],
                "FE08 profile mismatch/oversized state")
        for field in ("input_fnv64", "output_fnv64"):
            require(isinstance(row[field], str) and
                    re.fullmatch(r"[0-9a-f]{16}", row[field]) is not None,
                    "FE08 invalid complete PCM fingerprint")
        for field in ("output_energy", "peak_abs"):
            require(type(row[field]) in (int, float) and math.isfinite(row[field]) and
                    row[field] > 0, "FE08 invalid functional output")
        if timed:
            t = row["timing"]
            require(isinstance(t, dict) and set(t) ==
                    {"clock", "cpu_ms_per_audio_second", "frame_p50_ns",
                     "frame_p95_ns", "frame_p99_ns", "frame_max_ns"} and
                    t["clock"] == "CLOCK_THREAD_CPUTIME_ID" and
                    type(t["cpu_ms_per_audio_second"]) in (float, int) and
                    math.isfinite(t["cpu_ms_per_audio_second"]) and
                    t["cpu_ms_per_audio_second"] > 0,
                    "FE08 invalid hosted measurement")
            ordered = [t[k] for k in ("frame_p50_ns", "frame_p95_ns",
                                       "frame_p99_ns", "frame_max_ns")]
            require(all(type(x) is int and x >= 0 for x in ordered) and
                    ordered == sorted(ordered), "FE08 invalid CPU time distribution")
        else:
            require(row["timing"] is None, "FE08 Arm/sanitizer timing not admissible")
    by_name = {v["name"]: v for v in rows}
    require(by_name["C1_LINEAR"]["state_bytes"] < by_name["C2_LINEAR"]["state_bytes"] <
            by_name["C4_FIR33"]["state_bytes"] and
            by_name["C2_FIR33"]["state_bytes"] < by_name["C4_FIR33"]["state_bytes"] and
            by_name["C4_FIR33"]["state_bytes"] == by_name["C4_SPATIAL33"]["state_bytes"],
            "FE08 state scaling or mode distinction lost")
    return rows


def inspect_report(report: dict) -> None:
    require(set(report) == {"schema_version", "experiment_id", "execution_source_revision",
                            "decision", "shipping_authority", "source_role", "dataset_role",
                            "component_only", "targets", "runs", "executables",
                            "elf_sections", "data_plane_stack", "negative_kinds"},
            "FE08 report schema drift")
    require(report["schema_version"] == 1 and
            report["experiment_id"] == check_plan()["experiment_id"] and
            report["decision"] == DECISION and report["shipping_authority"] is False
            and report["source_role"] == "first-party-research"
            and report["dataset_role"] == "regression" and
            report["component_only"] is True and hex_digest(report["execution_source_revision"],40),
            "FE08 report authority drift")
    require(report["targets"] == ["native", "sanitized", "arm"] and
            set(report["runs"]) == {"native-0", "native-1", "native-2", "sanitized", "arm"} and
            set(report["executables"]) == set(report["targets"]) and
            set(report["elf_sections"]) == set(report["targets"]) and
            set(report["data_plane_stack"]) == set(report["targets"]) and
            report["negative_kinds"] == NEGATIVES,
            "FE08 missing target/negative coverage")
    for target in report["targets"]:
        fields = report["elf_sections"][target]
        require(set(fields) == {"text_bytes", "rodata_bytes"} and
                all(type(v) is int and v > 0 for v in fields.values()),
                "FE08 invalid binary sizes")
        stack = report["data_plane_stack"][target]
        require(set(stack) == {"max_single_function_bytes", "functions"} and
                type(stack["max_single_function_bytes"]) is int and
                bool(stack["functions"]), "FE08 invalid static stack report")


def same_functional(a: list[dict], b: list[dict], *, exact: bool) -> None:
    for x, y in zip(a, b):
        require(x["name"] == y["name"] and x["mic_count"] == y["mic_count"] and
                x["mode"] == y["mode"] and x["frames"] == y["frames"] and
                x["input_fnv64"] == y["input_fnv64"] and
                (not exact or x["state_bytes"] == y["state_bytes"]),
                "FE08 source, geometry, or state drift across targets")
        if exact:
            require(x["output_fnv64"] == y["output_fnv64"] and
                    x["output_energy"] == y["output_energy"] and
                    x["peak_abs"] == y["peak_abs"],
                    "FE08 same-native functional repeat mismatch")
        else:
            for key in ("output_energy", "peak_abs"):
                require(abs(x[key]-y[key]) <= max(0.001, 1e-4 * abs(x[key])),
                        "FE08 cross-architecture functional mismatch")


def verify(root: Path, revision: str | None = None, negatives: bool = True) -> dict:
    require(not (root/"failure.json").exists(), "FE08 failed result")
    require(all(not p.is_symlink() for p in root.rglob("*")), "FE08 symlink in evidence")
    manifest = load_json(root/"manifest.json")
    actual = {p.relative_to(root).as_posix():sha256(verified_file(root,p.relative_to(root).as_posix()).read_bytes())
              for p in root.rglob("*") if p.is_file() and p.name not in ("manifest.json","SHA256SUMS")}
    require(manifest["files"] == actual and manifest["shipping_authority"] is False,
            "FE08 file digest mismatch")
    observed = {}
    for line in (root/"SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        require(name not in observed, "FE08 duplicate evidence digest")
        observed[name] = digest
    require(observed == {**actual, "manifest.json":sha256((root/"manifest.json").read_bytes())},
            "FE08 SHA256SUMS mismatch")
    require((root/"experiment.json").read_bytes() == PLAN.read_bytes(),
            "FE08 experiment changed")
    for name in SOURCES:
        require((root/"source"/name).read_bytes() == (HERE/name).read_bytes(),
                "FE08 source snapshot mismatch")
    report = load_json(root/"result.json")
    inspect_report(report)
    require(revision is None or report["execution_source_revision"] == revision,
            "FE08 stale execution SHA")
    for target in report["targets"]:
        binary = verified_file(root,"bin/"+target)
        require(binary.read_bytes()[:4] == b"\x7fELF" and
                report["executables"][target] == sha256(binary.read_bytes()),
                "FE08 stale/wrong executable")
        if target == "arm":
            require(binary.read_bytes()[4:6] == b"\x01\x01" and
                    int.from_bytes(binary.read_bytes()[18:20],"little") == 40,
                    "FE08 target is not AArch32 ELF")
        stack = parse_stack(root/"obj"/target/"array_native.su")
        require(stack == report["data_plane_stack"][target],
                "FE08 altered data-plane stack evidence")
        require(read_size_receipt(root, target) == report["elf_sections"][target],
                "FE08 changed ELF section evidence")
    rows = {}
    for name in report["runs"]:
        path = verified_file(root,"run-"+name+".json")
        require(report["runs"][name] == sha256(path.read_bytes()),
                "FE08 stale execution receipt: "+name)
        rows[name] = profile_record(load_json(path), name.startswith("native-"))
    same_functional(rows["native-0"],rows["native-1"],exact=True)
    same_functional(rows["native-0"],rows["native-2"],exact=True)
    same_functional(rows["native-0"],rows["sanitized"],exact=False)
    same_functional(rows["native-0"],rows["arm"],exact=False)
    if negatives:
        proof = load_json(root/"negative-evidence.json")
        require(proof == {"status":"PASS","kinds":NEGATIVES},
                "FE08 missing negative-evidence contract")
    return {"status":"FE08_ARRAY_RESOURCE_ENGINEERING_PASS",
            "profiles":len(PROFILES),"native_repeats":3,
            "arm_functional":True,"component_only":True,
            "decision":DECISION,"shipping_authority":False}


def create_and_check_negatives(root: Path, revision: str) -> list[str]:
    for kind in NEGATIVES:
        with tempfile.TemporaryDirectory(prefix="fe08-neg-") as directory:
            scratch = Path(directory)/"evidence"
            shutil.copytree(root,scratch)
            report = load_json(scratch/"result.json")
            if kind == "promotion": report["shipping_authority"] = True
            elif kind == "decision": report["decision"] = "PROMOTED"
            elif kind == "missing-profile":
                data = load_json(scratch/"run-native-0.json")
                data["profiles"].pop()
                write_json(scratch/"run-native-0.json",data)
                report["runs"]["native-0"] = sha256((scratch/"run-native-0.json").read_bytes())
            elif kind == "state-bound":
                data = load_json(scratch/"run-native-0.json")
                data["profiles"][3]["state_bytes"] = 20000
                write_json(scratch/"run-native-0.json",data)
                report["runs"]["native-0"] = sha256((scratch/"run-native-0.json").read_bytes())
            elif kind == "timing-order":
                data = load_json(scratch/"run-native-0.json")
                data["profiles"][0]["timing"]["frame_p99_ns"] = -1
                write_json(scratch/"run-native-0.json",data)
                report["runs"]["native-0"] = sha256((scratch/"run-native-0.json").read_bytes())
            elif kind == "missing-arm": report["targets"].remove("arm")
            elif kind == "binary":
                path = scratch/"bin/native"
                data = path.read_bytes()
                path.write_bytes(data[:-1]+bytes([data[-1]^1]))
            write_json(scratch/"result.json",report)
            (scratch/"manifest.json").unlink()
            (scratch/"SHA256SUMS").unlink()
            seal_output(scratch,report)
            try:
                verify(scratch,revision,negatives=False)
            except (ValueError,KeyError,AssertionError):
                pass
            else:
                raise ValueError("FE08 resealed negative erroneously admitted: "+kind)
    return NEGATIVES


def run(root: Path, revision: str) -> dict:
    require(hex_digest(revision,40) and not root.exists(), "FE08 new exact-SHA evidence required")
    root.mkdir(parents=True)
    (root/"source").mkdir();(root/"bin").mkdir();(root/"obj").mkdir()
    shutil.copyfile(PLAN,root/"experiment.json")
    for name in SOURCES:shutil.copyfile(HERE/name,root/"source"/name)
    require(shutil.which("arm-linux-gnueabihf-gcc") and shutil.which("qemu-arm"),
            "FE08 pinned Arm/QEMU toolchain unavailable")
    instructions = []
    compiler_specs = [
        ("native", "cc", FLAGS, "cc", [], []),
        ("sanitized", "cc", [*FLAGS, "-O1","-g","-fsanitize=address,undefined",
                            "-fno-omit-frame-pointer","-fno-pie"],
         "cc", ["-fsanitize=address,undefined","-no-pie"], ["--functional"]),
        ("arm", "arm-linux-gnueabihf-gcc",
         [*FLAGS,"-mcpu=cortex-a32","-mfpu=neon-fp-armv8","-mfloat-abi=hard"],
         "arm-linux-gnueabihf-gcc",[], ["--functional"]),
    ]
    for target, compiler, flags, linker, linkflags, _args in compiler_specs:
        obj = root/"obj"/target;obj.mkdir()
        for short in ("array_native","array_resource_probe"):
            command = [compiler,*flags,"-c",str(HERE/(short+".c")),
                       "-o",str(obj/(short+".o"))]
            instructions.append(command)
            run_logged(command,root/("build-"+target+"-"+short+".log"))
        command = [linker,*linkflags,str(obj/"array_native.o"),
                   str(obj/"array_resource_probe.o"),"-lm","-o",str(root/"bin"/target)]
        instructions.append(command)
        run_logged(command,root/("link-"+target+".log"))
        size_command = ["arm-linux-gnueabihf-size" if target=="arm" else "size",
                        "-A",str(root/"bin"/target)]
        run_logged(size_command,root/("size-"+target+".txt"))
        if target == "native":
            # Test core only. The resource probe itself is allowed to sort and print.
            run_logged(["nm","-u",obj/"array_native.o"],root/"undefined-core.txt")
            entries = (root/"undefined-core.txt").read_text().split()
            require(not FORBIDDEN.intersection(entries),
                    "FE08 tested data plane unexpectedly imports heap or I/O")
    for i in range(3):
        run_logged([root/"bin/native"],root/f"run-native-{i}.json",timeout=180)
        profile_record(load_json(root/f"run-native-{i}.json"),True)
    run_logged([root/"bin/sanitized","--functional"],root/"run-sanitized.json",timeout=180)
    run_logged(["qemu-arm","-cpu","max","-L","/usr/arm-linux-gnueabihf",
                root/"bin/arm","--functional"],root/"run-arm.json",timeout=180)
    profile_record(load_json(root/"run-sanitized.json"),False)
    profile_record(load_json(root/"run-arm.json"),False)
    write_json(root/"build-commands.json",{"commands":instructions})
    report = {
        "schema_version":1,"experiment_id":check_plan()["experiment_id"],
        "execution_source_revision":revision,
        "decision":DECISION,"shipping_authority":False,
        "source_role":"first-party-research","dataset_role":"regression",
        "component_only":True,"targets":["native","sanitized","arm"],
        "runs":{name:sha256((root/("run-"+name+".json")).read_bytes())
                for name in ("native-0","native-1","native-2","sanitized","arm")},
        "executables":{t:sha256((root/"bin"/t).read_bytes()) for t in ("native","sanitized","arm")},
        "elf_sections":{t:read_size_receipt(root, t)
                        for t in ("native","sanitized","arm")},
        "data_plane_stack":{t:parse_stack(root/"obj"/t/"array_native.su")
                            for t in ("native","sanitized","arm")},
        "negative_kinds":NEGATIVES,
    }
    write_json(root/"result.json",report)
    seal_output(root,report)
    create_and_check_negatives(root,revision)
    write_json(root/"negative-evidence.json",{"status":"PASS","kinds":NEGATIVES})
    seal_output(root,report)
    return verify(root,revision)


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--output",type=Path)
    parser.add_argument("--execution-source")
    parser.add_argument("--verify",action="store_true")
    a=parser.parse_args()
    if a.self_test:
        check_plan()
        require(parse_size(".text 100 0\n.rodata 16 0\n") ==
                {"text_bytes":100,"rodata_bytes":16}, "FE08 size parser test")
        with tempfile.TemporaryDirectory(prefix="fe08-size-test-") as tmp:
            root = Path(tmp)
            (root / "size-native.txt").write_text(".text 100 0\n.rodata 16 0\n")
            require(read_size_receipt(root, "native") ==
                    {"text_bytes":100,"rodata_bytes":16},
                    "FE08 exact-root size receipt self-test")
        with tempfile.TemporaryDirectory(prefix="fe08-stack-test-") as tmp:
            path = Path(tmp) / "core.su"
            baseline = ("unit.c:1:1:fe_array_process\t88\tstatic\n"
                        "unit.c:2:1:fe_array_init\t32\tdynamic,bounded\n"
                        "unit.c:3:1:fe_array_init_spatial33\t32\tstatic\n")
            path.write_text(baseline)
            require(len(parse_stack(path)["functions"]) == 3,
                    "FE08 allowed bounded initialization classification broken")
            for old, new in (
                ("fe_array_process\t88\tstatic", "fe_array_process\t88\tdynamic,bounded"),
                ("fe_array_init\t32\tdynamic,bounded", "fe_array_init\t32\tdynamic"),
                ("fe_array_init\t32\tdynamic,bounded", "fe_array_init\t65\tdynamic,bounded"),
            ):
                path.write_text(baseline.replace(old, new))
                try:
                    parse_stack(path)
                except ValueError as exc:
                    require("unbounded/unapproved stack" in str(exc),
                            "FE08 stack negative rejected for wrong reason")
                else:
                    raise AssertionError("unapproved dynamic/stack-bound negative passed")
        print("FE08 fixed resource contract: PASS")
        return 0
    require(a.output is not None,"--output required")
    if a.verify:
        result=verify(a.output,a.execution_source)
    else:
        require(a.execution_source is not None,"--execution-source required")
        result=run(a.output,a.execution_source)
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
