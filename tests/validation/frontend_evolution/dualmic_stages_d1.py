#!/usr/bin/env python3
"""D1: sealed A/C replay, neutral stage observation, and read-only verification.

Only ``run`` executes the two PCM CLIs. ``verify`` reads the retained bytes and
recomputes the diagnostic report without executing DSP, build tools, or models.
Neither command changes the historical canonical or downstream scores.
"""
from __future__ import annotations

import argparse
from array import array
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "validation/tools"))
from tools.codex_assets.device_stages import energy as d19_energy
from run_validation_engine import si_sdr_span

EXPERIMENT = "FE-DUALMIC-STAGES-D1"
BASE_SHA = "4daa7e239eebda11f6c7066df2e851269021112f"
BUDGET = 300.0
RATE, HOP = 16000, 160
LOCK = ROOT / "docs/research/frontend-evolution-v1/dualmic-stages-d1-source-lock.json"
SCENES = ("near-only", "silent-render", "far-only", "doubletalk-nominal",
          "doubletalk-weak", "path-change", "render-gap")
PROFILES = ("call", "assistant")
C_CASES = ("call", "assistant", "call_duplex", "assistant_duplex")
LANES = {"aec_input": 0, "reference": 0, "echo": 0, "aec_residual": 0,
         "ns_input": 0, "ns_output": HOP, "agc_output": HOP}
AEC_LANES = frozenset(("aec_input", "reference", "echo", "aec_residual"))
NEAR_LANES = frozenset(("aec_input", "aec_residual", "ns_input", "ns_output", "agc_output"))
CONTROL_FIELDS = (
    "frame,mic_energy,reference_energy,smoothed_mic_before,smoothed_reference_before,"
    "smoothed_mic_after,smoothed_reference_after,far_threshold,double_talk_ratio,"
    "hangover_frames,far_hangover_before,far_hangover_after,dt_hangover_before,"
    "dt_hangover_after,far,dt,aec_present,aec_enabled,aec_mu,gate_eligible,"
    "aec_identity_max_abs_error,ns_mode,ns_floor,frequency_enabled,frequency_active,"
    "res_gain,noise_rms_dbfs,speech_probability,agc_allow,gain_before,gain_after"
).split(",")
CONTROL_FLAGS = ("far", "dt", "aec_present", "gate_eligible", "frequency_enabled",
                 "frequency_active", "agc_allow")
STATE_FIELDS = (*CONTROL_FLAGS, "aec_enabled", "ns_mode")
METRIC_STATE_FIELDS = ("estimated_delay_ms", "delay_error_samples", "aec_converged",
                       "erle_valid", "vad_active")
TOTALS = {"frames": 35916, "samples": 5746560, "capture_only_frames": 5858,
          "activity": 35916, "aec": 30058, "ns": 35916, "agc": 35916, "res": 0}
SOURCE_FILES = (
    "tests/validation/frontend_evolution/dualmic_stages_d1.py",
    "tests/validation/frontend_evolution/dualmic_stages_d1.c",
    "tests/validation/frontend_evolution/dualmic_stages_source.py",
    "tools/codex_assets/dualmic_stages_build.py",
    "docs/research/frontend-evolution-v1/DUALMIC_STAGES_D1_PLAN.zh-CN.md",
    "docs/research/frontend-evolution-v1/dualmic-stages-d1-source-lock.json",
    "validation/tools/run_validation_engine.py",
    "tools/codex_assets/device_stages.py",
    "tools/codex_assets/device_capture.py",
    "tools/codex_assets/device_exact_reference.py",
    "tools/codex_assets/device_replay.py",
)
VERIFY_FILES = frozenset(("verify.log", "verify-phase.json", "readback.json", "verify-error.json"))
A_METADATA = ("result/artifact-manifest.json", "result/report.json", "result/input/corpus.json",
              "result/input/source-manifest.json", "build-identity.txt", "checkout-sha.txt",
              "result/bin/ap_process_pcm", "result/bin/ap_build_info_dump")
C_METADATA = ("prepared/preparation.json", "prepared/manifest.json", "prepared/clean_mono.pcm",
              "prepared/duplex_mono.pcm", "source-receipts/source-lock.json")
ORIGINAL_CASE_FILES = ("command.json", "continuity.json", "execution.json", "out.pcm",
                       "metrics.jsonl", "stdout.txt", "stderr.txt")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def descriptor(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "regular file required: " + str(path))
    return {"bytes": path.stat().st_size, "sha256": digest(path)}


def safe(root, relative):
    require(isinstance(relative, str) and relative and "\\" not in relative,
            "invalid artifact path")
    parts = PurePosixPath(relative)
    require(not parts.is_absolute() and all(p not in (".", "..") for p in parts.parts),
            "non-relative artifact path: " + relative)
    path = Path(root)
    require(not path.is_symlink(), "symlink root")
    for part in parts.parts:
        path /= part
        require(not path.is_symlink(), "symlink artifact path: " + relative)
    return path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON: " + value)))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True,
                               allow_nan=False) + "\n", encoding="utf-8")


def remaining(started, reserve=0.0):
    value = BUDGET - (time.monotonic() - started) - reserve
    if value <= 0:
        raise TimeoutError("frozen 300 second phase budget exceeded")
    return value


def copy_exact(source, destination):
    expected = descriptor(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        require(descriptor(destination) == expected, "conflicting retained file: " + str(destination))
    else:
        shutil.copy2(source, destination)
    require(descriptor(destination) == expected, "copy drift: " + str(source))
    return expected


def process_environment(tap_dir=None):
    # Do not pass Actions credentials or other ambient service variables to DSP.
    environment = {key: os.environ[key] for key in ("PATH", "HOME", "TMPDIR", "LANG") if key in os.environ}
    environment["LC_ALL"] = "C"
    if tap_dir is not None:
        environment["AP_D1_STAGE_DIR"] = str(tap_dir)
    return environment


def archive_index(path, entry, lock):
    require(descriptor(path) == {"bytes": entry["zip_bytes"], "sha256": entry["sha256"]},
            "sealed archive identity changed: " + entry["key"])
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        require(len(infos) == entry["members"] <= lock["max_members"], "ZIP member count drift")
        require(len({i.filename for i in infos}) == len(infos), "duplicate ZIP member")
        require(sum(i.file_size for i in infos) <= lock["max_uncompressed_bytes"], "ZIP size limit")
        files = {}
        for info in infos:
            safe(Path("/unused-d1-root"), info.filename)
            require(((info.external_attr >> 16) & 0o170000) != 0o120000, "ZIP symlink")
            require(not (info.flag_bits & 1), "encrypted ZIP member")
            if not info.is_dir():
                files[info.filename] = info.file_size
        return files


def original_member(output, originals, archives, group, name):
    source = safe(originals[group], name)
    with zipfile.ZipFile(archives[group]) as archive:
        info = archive.getinfo(name)
        require(not info.is_dir() and info.file_size <= 64 * 1024 * 1024, "invalid selected member")
        raw = archive.read(name)
    require(source.read_bytes() == raw, "extracted original differs from locked ZIP: " + group + "/" + name)
    destination = safe(output / "originals" / group, name)
    return copy_exact(source, destination)


def catalog(a_root, c_root):
    """Construct the exact 60-case catalog from the original artifacts only."""
    corpus = read_json(a_root / "result/input/corpus.json")
    old_a = read_json(a_root / "result/report.json")
    prep = read_json(c_root / "prepared/preparation.json")
    old_c = read_json(c_root / "result/report.json")
    require(old_a["source_revision"] == prep["source_revision"] == old_c["source_revision"] == BASE_SHA,
            "original source revision drift")
    expected_a = {f"pair-{pair}-{scene}-{profile}" for pair in range(4)
                  for scene in SCENES for profile in PROFILES}
    actual_a = [c["case_id"] for c in corpus["cases"]]
    require(len(actual_a) == 56 and set(actual_a) == expected_a, "A case matrix drift")
    require([c["case_id"] for c in old_a["cases"]] == actual_a, "A report/corpus order drift")
    require(set(prep["views"]) == {*C_CASES, "raw", "raw_duplex"}, "C view matrix drift")
    specs = []
    for group, cases in (("A", corpus["cases"]), ("C", C_CASES)):
        for raw in cases:
            if group == "A":
                case = raw
                name, profile, scene = case["case_id"], case["pipeline_profile"], case["scenario"]
                require(case["sample_rate_hz"] == RATE and case["mic_channels"] == 2,
                        "A PCM geometry changed")
                require(case["dimensions"]["frames"] == 600 and
                        case["dimensions"]["data_role"] == "regression", "A data role/length drift")
                require(case["processor_profile"] == "default", "A capture profile drift")
                inputs = {"mic": "result/input/" + case["mic_audio"],
                          "render": "result/input/" + case["render_audio"] if case["render_audio"] else None,
                          "clean_near": "result/input/" + case["clean_near_audio"] if case["clean_near_audio"] else None}
                aux = ["result/input/" + case[key] for key in ("echo_audio", "interference_audio") if case.get(key)]
                control, dimensions, frames = case["control"], case["dimensions"], 600
                old_dir = "result/replay/" + name
                old_prefix = "/tmp/ap-dualmic-recorded-stage/"
                original_root = a_root
            else:
                name = raw
                profile = name.split("_")[0]
                duplex = name.endswith("_duplex")
                scene = "mandarin-duplex" if duplex else "mandarin-clean"
                inputs = {"mic": "prepared/" + ("duplex_capture.pcm" if duplex else "clean_capture.pcm"),
                          "render": "prepared/duplex_render.pcm" if duplex else None, "clean_near": None}
                aux, control = [], {}
                dimensions = {"human_vad_labels": False, "independent_original_utterances": 1,
                              "real_array_recording": False, "real_farend_speech": False}
                frames = 629 if duplex else 529
                old_dir = "prepared/processed/" + name
                old_prefix = "/tmp/ap-mandarin-stage/"
                original_root = c_root
            require(profile in PROFILES and re.fullmatch(r"[a-z0-9_-]+", name), "invalid case identity")
            require(set(control) <= {"echo_path_change_frame", "discontinuity_frame", "discontinuity_flags",
                                     "discontinuity_lost_frames"}, "unfrozen control option")
            argv = read_json(original_root / old_dir / "command.json")
            require(isinstance(argv, list) and all(isinstance(v, str) for v in argv), "original argv schema")
            expected = argv[:1] + ["--profile", profile, "--sample-rate", "16000", "--mic-channels", "2",
                                  "--strict-capture-frames", "--metrics-jsonl", old_prefix + old_dir + "/metrics.jsonl"]
            events = []
            if "echo_path_change_frame" in control:
                require(control["echo_path_change_frame"] == 300, "path-change frame drift")
                expected += ["--echo-path-change-frame", "300"]
                events.append({"frame": 300, "sample": 48000, "kind": "cli_echo_path_change"})
            if "discontinuity_frame" in control:
                require(control == {"discontinuity_frame": 300, "discontinuity_flags": 2,
                                    "discontinuity_lost_frames": 4}, "render-gap control drift")
                expected += ["--discontinuity-frame", "300", "--discontinuity-flags", "2",
                             "--discontinuity-lost-frames", "4"]
                events.append({"frame": 300, "sample": 48000, "kind": "cli_discontinuity",
                               "flags": 2, "lost_frames": 4})
            if inputs["render"] is None:
                expected += ["--capture-profile", "default", "--capture-only", old_prefix + inputs["mic"],
                             old_prefix + old_dir + "/out.pcm"]
            else:
                expected += [old_prefix + inputs["mic"], old_prefix + inputs["render"],
                             old_prefix + old_dir + "/out.pcm"]
            require(argv == expected and Path(argv[0]).name == "ap_process_pcm", "original argv drift: " + name)
            specs.append({"group": group, "case_id": name, "key": group + "/" + name,
                          "profile": profile, "scenario": scene, "frames": frames, "samples": frames * HOP,
                          "capture_only": inputs["render"] is None, "inputs": inputs, "auxiliary_inputs": aux,
                          "original_dir": old_dir, "original_prefix": old_prefix, "original_argv": argv,
                          "input_events": events, "dimensions": dimensions, "data_role": "disclosed-regression"})
    require(len(specs) == 60 and sum(c["frames"] for c in specs) == TOTALS["frames"], "total matrix drift")
    return specs


def snapshot_originals(args, output, started):
    originals = {"A": Path(args.original_a).resolve(), "C": Path(args.original_c).resolve()}
    require(originals["A"].parent == originals["C"].parent, "A/C acquisition roots must be siblings")
    acquired = originals["A"].parent
    lock = read_json(LOCK)
    require((acquired / "source-lock.json").read_bytes() == LOCK.read_bytes(), "acquired source lock drift")
    receipt = read_json(acquired / "acquisition.json")
    require(receipt["status"] == "PASS" and receipt["experiment"] == EXPERIMENT and
            receipt["base_sha"] == BASE_SHA and receipt["lock_sha256"] == digest(LOCK), "acquisition not qualified")
    require(receipt["run_id"] == lock["run_id"] and receipt["run_attempt"] == lock["run_attempt"] and
            0 <= receipt["elapsed_seconds"] <= BUDGET and receipt["budget_seconds"] == BUDGET,
            "acquisition identity/budget drift")
    copy_exact(LOCK, output / "origins/source-lock.json")
    copy_exact(acquired / "acquisition.json", output / "origins/acquisition.json")
    archives, selected = {}, {"A": {}, "C": {}}
    for entry in lock["artifacts"]:
        remaining(started)
        group = entry["key"]
        archive = acquired / (group + ".zip")
        archive_index(archive, entry, lock)
        archives[group] = output / "original-archives" / (group + ".zip")
        copy_exact(archive, archives[group])
    for group, names in (("A", A_METADATA), ("C", C_METADATA)):
        for name in names:
            selected[group][name] = original_member(output, originals, archives, group, name)
    for path in sorted((originals["C"] / "result").iterdir()):
        require(path.is_file(), "unexpected C report directory")
        name = "result/" + path.name
        selected["C"][name] = original_member(output, originals, archives, "C", name)
    specs = catalog(originals["A"], originals["C"])
    require({p.name for p in (originals["A"] / "result/replay").iterdir()} ==
            {c["case_id"] for c in specs if c["group"] == "A"}, "extra/missing A replay case")
    require({p.name for p in (originals["C"] / "prepared/processed").iterdir()} == set(C_CASES),
            "extra/missing C processed view")
    for case in specs:
        remaining(started)
        names = [n for n in case["inputs"].values() if n] + case["auxiliary_inputs"]
        names += [case["original_dir"] + "/" + n for n in ORIGINAL_CASE_FILES]
        for name in names:
            if name not in selected[case["group"]]:
                selected[case["group"]][name] = original_member(output, originals, archives, case["group"], name)
    write_json(output / "origins/selected-members.json", selected)
    require(catalog(output / "originals/A", output / "originals/C") == specs, "retained catalog drift")
    return specs


def snapshot_build(build_dir, output, started):
    build_dir = Path(build_dir).resolve()
    manifest = read_json(build_dir / "build-manifest.json")
    require(manifest["status"] == "BUILT" and manifest["experiment"] == EXPERIMENT and
            manifest["base_sha"] == BASE_SHA and manifest["production_source_unchanged"] is True,
            "unqualified D1 build")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                                       timeout=min(30, remaining(started))).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True,
                                   timeout=min(30, remaining(started))).strip()
    require(re.fullmatch(r"[0-9a-f]{40}", revision) and manifest["source_revision"] == revision and
            manifest["source_tree"] == tree, "build is not the exact current source")
    subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "src", "include", "examples/process_pcm.c",
                    *SOURCE_FILES], cwd=ROOT, check=True, timeout=min(30, remaining(started)))
    copied = {"build-manifest.json": copy_exact(build_dir / "build-manifest.json", output / "build/build-manifest.json")}
    for spec in manifest["programs"].values():
        path = safe(build_dir, spec["path"])
        require(descriptor(path) == {k: spec[k] for k in ("bytes", "sha256")}, "program hash drift")
        copied[spec["path"]] = copy_exact(path, safe(output / "build", spec["path"]))
    require(set(manifest["programs"]) == {"plain_cli", "plain_build_info", "observer_cli"}, "program inventory drift")
    for name in ("plain", "observer"):
        build = manifest["builds"][name]
        expected = revision if name == "plain" else revision + "-D1-observer"
        require(build["source_revision"] == expected and 0 <= build["elapsed_seconds"] <= BUDGET and
                build["budget_seconds"] == BUDGET, "build source/budget drift")
        for key in ("library", "generated_header", "flags_make"):
            spec = build[key]
            path = safe(build_dir, spec["path"])
            require(descriptor(path) == {k: spec[k] for k in ("bytes", "sha256")}, "build evidence drift")
            copied[spec["path"]] = copy_exact(path, safe(output / "build", spec["path"]))
    for name, spec in manifest["proof_files"].items():
        require(name == spec["path"], "build proof path mismatch")
        path = safe(build_dir, name)
        require(descriptor(path) == {k: spec[k] for k in ("bytes", "sha256")}, "build proof drift")
        copied[name] = copy_exact(path, safe(output / "build", name))
    sources = {}
    for name in SOURCE_FILES:
        path = ROOT / name
        committed = subprocess.check_output(["git", "show", revision + ":" + name], cwd=ROOT,
                                            timeout=min(30, remaining(started)))
        require(path.read_bytes() == committed, "uncommitted measurement source: " + name)
        sources[name] = copy_exact(path, safe(output / "source", name))
    identity = {"source_revision": revision, "source_tree": tree, "files": sources, "build_files": copied,
                "python": sys.version, "platform": platform.platform(),
                "measurement_metric": "run_validation_engine.si_sdr_span; track_identity=False",
                "energy_metric": "tools.codex_assets.device_stages.energy"}
    write_json(output / "source/identity.json", identity)
    return manifest, identity


def mapped_argv(case, executable, case_dir, original_root):
    old_dir, prefix = case["original_dir"], case["original_prefix"]
    replacements = {prefix + old_dir + "/out.pcm": str(case_dir / "out.pcm"),
                    prefix + old_dir + "/metrics.jsonl": str(case_dir / "metrics.jsonl")}
    for name in ("mic", "render"):
        relative = case["inputs"][name]
        if relative:
            replacements[prefix + relative] = str(safe(original_root, relative))
    original = case["original_argv"]
    require(all(original.count(k) == 1 for k in replacements), "ambiguous argv path mapping")
    return [str(executable)] + [replacements.get(value, value) for value in original[1:]]


def execute(command, directory, started, tap_dir=None):
    directory.mkdir(parents=True, exist_ok=False)
    environment = process_environment(tap_dir)
    if tap_dir is not None:
        tap_dir.mkdir(parents=True, exist_ok=False)
    write_json(directory / "command.json", command)
    begin = time.monotonic()
    timeout = min(BUDGET, remaining(started, 2.0))
    result = {"timeout_seconds": timeout, "process_budget_seconds": BUDGET,
              "environment": {"keys": sorted(environment), "LC_ALL": "C",
                              "AP_D1_STAGE_DIR": str(tap_dir) if tap_dir is not None else None}}
    try:
        with (directory / "stdout.txt").open("wb") as stdout, (directory / "stderr.txt").open("wb") as stderr:
            completed = subprocess.run(command, cwd=directory, env=environment, stdout=stdout,
                                       stderr=stderr, timeout=timeout, check=False)
        result.update(returncode=completed.returncode, status="COMPLETE" if completed.returncode == 0 else "FAILED")
    except subprocess.TimeoutExpired:
        result.update(returncode=None, status="TIMEOUT")
        raise
    finally:
        result["elapsed_seconds"] = time.monotonic() - begin
        write_json(directory / "execution.json", result)
    require(result["status"] == "COMPLETE" and result["elapsed_seconds"] <= timeout, "PCM process failed or timed out")


def compare_case(output, case):
    original = output / "originals" / case["group"] / case["original_dir"]
    directory = output / "cases" / case["key"]
    evidence = {}
    for name in ("out.pcm", "metrics.jsonl"):
        paths = {"original": original / name, "plain": directory / "plain" / name,
                 "observed": directory / "observed" / name}
        descriptions = {kind: descriptor(path) for kind, path in paths.items()}
        old = paths["original"].read_bytes()
        plain, observed = paths["plain"].read_bytes(), paths["observed"].read_bytes()
        evidence[name] = {"files": descriptions, "plain_equals_original": plain == old,
                          "observed_equals_plain": observed == plain, "observed_equals_original": observed == old}
    write_json(directory / "neutrality.json", evidence)
    require(all(v["plain_equals_original"] and v["observed_equals_plain"] and v["observed_equals_original"]
                for v in evidence.values()), "MEASUREMENT_INVALID byte mismatch: " + case["key"])
    require(evidence["out.pcm"]["files"]["plain"]["bytes"] == case["samples"] * 2, "output PCM size drift")
    return evidence


def worker_run(args):
    started, output = time.monotonic(), Path(args.output).resolve()
    specs = snapshot_originals(args, output, started)
    manifest, identity = snapshot_build(args.build_dir, output, started)
    index = {"schema_version": 1, "experiment": EXPERIMENT, "status": "RUNNING", "cases": specs,
             "source_revision": identity["source_revision"], "source_tree": identity["source_tree"],
             "data_role": "disclosed-regression", "original_source_revision": BASE_SHA,
             "originals_retained": True, "models_executed": False, "completed_cases": []}
    write_json(output / "run-index.json", index)
    for case in specs:
        remaining(started)
        directory = output / "cases" / case["key"]
        original_root = output / "originals" / case["group"]
        for kind, program in (("plain", "plain_cli"), ("observed", "observer_cli")):
            executable = safe(output / "build", manifest["programs"][program]["path"])
            command = mapped_argv(case, executable, directory / kind, original_root)
            execute(command, directory / kind, started, directory / "taps" if kind == "observed" else None)
        compare_case(output, case)
        index["completed_cases"].append(case["key"])
        write_json(output / "run-index.json", index)
    index["status"] = "RUN_COMPLETE_BYTES_IDENTICAL"
    write_json(output / "run-index.json", index)
    remaining(started)


def samples(path, kind, count):
    raw = path.read_bytes()
    width = 4 if kind == "f" else 2
    require(len(raw) == count * width, "signal byte count mismatch: " + str(path))
    values = array(kind)
    values.frombytes(raw)
    if sys.byteorder != "little":
        values.byteswap()
    require(all(math.isfinite(v) for v in values), "nonfinite signal: " + str(path))
    return values


def metric_rows(path, frames):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    require(len(rows) == frames, "metrics frame count drift")
    for i, row in enumerate(rows):
        require(type(row.get("frame")) is int and row["frame"] == i and row["algorithmic_latency_ms"] == 10,
                "metrics frame/delay contract")
        require(all(not isinstance(v, float) or math.isfinite(v) for v in row.values()), "nonfinite metrics")
    return rows


def controls(path, case, metrics):
    reader = csv.DictReader(io.StringIO(path.read_text(encoding="ascii")))
    require(reader.fieldnames == CONTROL_FIELDS, "control schema drift")
    rows = list(reader)
    require(len(rows) == case["frames"], "control frame count drift")
    counts = {name: 0 for name in (*CONTROL_FLAGS, "aec_enabled")}
    events = list(case["input_events"])
    previous, prior_metrics = {}, {}
    for i, row in enumerate(rows):
        require(row["frame"] == str(i) and set(row) == set(CONTROL_FIELDS), "control sequence/schema")
        nullable = {"aec_enabled", "aec_mu", "aec_identity_max_abs_error"} if case["capture_only"] else set()
        for key, value in row.items():
            require(value == "" if key in nullable else value not in (None, "") and math.isfinite(float(value)),
                    "missing/nonfinite control value: " + key)
        for key in CONTROL_FLAGS:
            require(row[key] in ("0", "1"), "invalid control flag")
            counts[key] += int(row[key])
        require(row["aec_present"] == str(int(not case["capture_only"])), "AEC presence drift")
        require(int(row["far"]) == metrics[i]["far_end_active"] and
                int(row["dt"]) == metrics[i]["double_talk_active"], "control/public metric mismatch")
        eligible = int(row["far"]) and not int(row["dt"])
        require(int(row["gate_eligible"]) == int(eligible) and int(row["agc_allow"]) == int(not eligible),
                "control policy mismatch")
        enabled = not case["capture_only"]
        require(int(row["frequency_enabled"]) == int(enabled) and
                int(row["frequency_active"]) == int(enabled and eligible and int(row["ns_mode"]) != 0),
                "frequency RES route mismatch")
        if not case["capture_only"]:
            require(row["aec_enabled"] in ("0", "1") and
                    0 <= float(row["aec_identity_max_abs_error"]) <= 1e-6, "AEC observer identity failure")
            counts["aec_enabled"] += int(row["aec_enabled"])
        state = {key: row[key] for key in STATE_FIELDS}
        changed = {key: {"before": previous.get(key), "after": value}
                   for key, value in state.items() if previous.get(key) != value}
        if changed:
            events.append({"frame": i, "sample": i * HOP, "kind": "observed_control_transition", "changes": changed})
        previous = state
        m_state = {key: metrics[i][key] for key in METRIC_STATE_FIELDS}
        changed = {key: {"before": prior_metrics.get(key), "after": value}
                   for key, value in m_state.items() if prior_metrics.get(key) != value}
        if changed:
            events.append({"frame": i, "sample": i * HOP, "kind": "public_metric_transition", "changes": changed})
        prior_metrics = m_state
    return counts, events


def measure_lane(signal, offset, n, reference, reference_reason, near_lane):
    def one(first, last):
        measured = d19_energy(signal, first + offset, last + offset)
        score = None
        reason = reference_reason
        if reference is not None and near_lane:
            score = si_sdr_span(reference, signal, first, first + offset, last - first)
            reason = "zero_energy_reference_or_short_span" if score is None else None
        elif not near_lane:
            reason = "render_reference_or_estimated_echo_is_not_a_near_output"
        return {"physical_sample_range": [first, last], "signal_sample_range": [first + offset, last + offset],
                **measured, "near_si_sdr_db": score, "near_si_sdr_null_reason": reason}
    common_end = n - HOP
    return {"present": True, "offset_samples": offset, "common": one(0, common_end),
            "one_second_windows": [one(first, min(first + RATE, common_end))
                                   for first in range(0, common_end, RATE)],
            "native_whole_buffer_energy": d19_energy(signal, 0, n)}


def stage_delta(stages, before, after, label):
    if not stages[before]["present"] or not stages[after]["present"]:
        return {"label": label, "present": False}
    def one(left, right):
        require(left["physical_sample_range"] == right["physical_sample_range"], "stage comparison span drift")
        a, b = left["near_si_sdr_db"], right["near_si_sdr_db"]
        return {"physical_sample_range": left["physical_sample_range"],
                "rms_change_db": right["rms_dbfs"] - left["rms_dbfs"],
                "near_si_sdr_change_db": b - a if a is not None and b is not None else None}
    return {"label": label, "present": True, "common": one(stages[before]["common"], stages[after]["common"]),
            "one_second_windows": [one(a, b) for a, b in
                                   zip(stages[before]["one_second_windows"], stages[after]["one_second_windows"])]}


def inspect_case(output, case, revision):
    directory = output / "cases" / case["key"]
    original_root = output / "originals" / case["group"]
    old = original_root / case["original_dir"]
    # Check without rewriting neutrality.json; readback never repairs evidence.
    neutral = read_json(directory / "neutrality.json")
    for name in ("out.pcm", "metrics.jsonl"):
        paths = {"original": old / name, "plain": directory / "plain" / name,
                 "observed": directory / "observed" / name}
        require({kind: descriptor(path) for kind, path in paths.items()} == neutral[name]["files"], "neutrality hash drift")
        require(paths["original"].read_bytes() == paths["plain"].read_bytes() == paths["observed"].read_bytes(),
                "MEASUREMENT_INVALID PCM/metrics neutrality failure")
        require(all(neutral[name][k] is True for k in
                    ("plain_equals_original", "observed_equals_plain", "observed_equals_original")), "neutrality flag drift")
    n, frames = case["samples"], case["frames"]
    require(descriptor(original_root / case["inputs"]["mic"])["bytes"] == n * 4, "stereo input length")
    if case["inputs"]["render"]:
        require(descriptor(original_root / case["inputs"]["render"])["bytes"] == n * 2, "render input length")
    require(neutral["out.pcm"]["files"]["plain"]["bytes"] == n * 2, "mono output length")
    metrics = metric_rows(directory / "observed/metrics.jsonl", frames)
    taps = directory / "taps"
    observer = read_json(taps / "observer.json")
    require(observer["schema_version"] == 1 and observer["experiment"] == EXPERIMENT and
            observer["transformed_measurement_copy"] is True and observer["frame_samples"] == HOP and
            observer["sample_format"] == "float32le" and observer["gate_eligible_is_actual_adaptation_count"] is False,
            "observer format/semantics drift")
    require(observer["status"] == "OBSERVED" and observer["cli_exit_code"] == 0 and
            observer["observer_error_count"] == 0 and observer["frames"] == frames and
            observer["capture_only"] is case["capture_only"] and observer["first_error"] == "",
            "observer terminal status")
    require(observer["source_revision"] == revision + "-D1-observer", "observer build identity drift")
    expected_calls = {"activity": frames, "aec": 0 if case["capture_only"] else frames,
                      "ns": frames, "agc": frames, "res": 0}
    require(observer["calls"] == expected_calls and set(observer["lanes"]) == set(LANES), "observer call/lane count drift")
    values, stages, tap_hashes = {}, {}, {}
    reference = None
    reference_reason = "C_has_no_admitted_clean_near_reference" if case["group"] == "C" else "no_clean_near_reference"
    if case["group"] == "A" and case["inputs"]["clean_near"]:
        raw = samples(original_root / case["inputs"]["clean_near"], "h", n)
        reference = [float(v) / 32768.0 for v in raw]
    for lane, offset in LANES.items():
        info = observer["lanes"][lane]
        present = not (case["capture_only"] and lane in AEC_LANES)
        expected_size = n * 4 if present else 0
        require(info["file"] == lane + ".f32le" and info["present"] is present and
                info["frames"] == (frames if present else 0) and info["samples"] == (n if present else 0) and
                info["bytes"] == expected_size and info["offset_samples"] == offset, "lane contract: " + lane)
        path = taps / info["file"]
        tap_hashes[info["file"]] = descriptor(path)
        require(tap_hashes[info["file"]]["bytes"] == expected_size, "lane byte length")
        if present:
            values[lane] = samples(path, "f", n)
            stages[lane] = measure_lane(values[lane], offset, n, reference, reference_reason, lane in NEAR_LANES)
        else:
            stages[lane] = {"present": False, "offset_samples": offset, "reason": "capture_only_route_has_no_AEC_call"}
    arithmetic = None
    if not case["capture_only"]:
        require((taps / "ns_input.f32le").read_bytes() == (taps / "aec_residual.f32le").read_bytes(),
                "NS input is not the observed AEC residual")
        arithmetic = max(abs(a - (b + c)) for a, b, c in
                         zip(values["aec_input"], values["echo"], values["aec_residual"]))
        require(arithmetic <= 1e-6, "AEC arithmetic identity exceeded")
    counts, events = controls(taps / "control.csv", case, metrics)
    for name in ("control.csv", "observer.json"):
        tap_hashes[name] = descriptor(taps / name)
    require({p.name for p in taps.iterdir()} == set(tap_hashes), "unexpected tap member")
    return {"key": case["key"], "group": case["group"], "case_id": case["case_id"],
            "profile": case["profile"], "scenario": case["scenario"], "data_role": "disclosed-regression",
            "frames": frames, "samples": n, "capture_only": case["capture_only"],
            "calls": observer["calls"], "neutrality": neutral, "taps": tap_hashes,
            "source_placement_metadata": case["dimensions"], "human_vad_labels": False,
            "control_counts": counts, "events": events, "aec_arithmetic_max_abs_error": arithmetic,
            "stages": stages, "stage_changes": {
                "aec": stage_delta(stages, "aec_input", "aec_residual", "linear_AEC_stage"),
                "joint_ns_frequency_res": stage_delta(stages, "ns_input", "ns_output", "joint_NS_frequency_RES_stage"),
                "agc": stage_delta(stages, "ns_output", "agc_output", "AGC_stage")}}


def analysis_payload(output, *, origins_verified=False):
    started = time.monotonic()
    index = read_json(output / "run-index.json")
    require(index["status"] == "RUN_COMPLETE_BYTES_IDENTICAL" and index["experiment"] == EXPERIMENT,
            "execution did not qualify for stage analysis")
    if not origins_verified:
        verify_origins(output)
    specs = catalog(output / "originals/A", output / "originals/C")
    require(index["cases"] == specs and index["completed_cases"] == [c["key"] for c in specs], "incomplete/reordered matrix")
    identity = read_json(output / "source/identity.json")
    for name, expected in identity["files"].items():
        require(descriptor(ROOT / name) == expected and descriptor(output / "source" / name) == expected,
                "measurement implementation drift: " + name)
    manifest = read_json(output / "build/build-manifest.json")
    require(manifest["source_revision"] == index["source_revision"] == identity["source_revision"] and
            manifest["source_tree"] == index["source_tree"] == identity["source_tree"], "new source binding drift")
    for name, expected in identity["build_files"].items():
        require(descriptor(output / "build" / name) == expected, "retained build evidence drift")
    cases, totals = [], {name: 0 for name in TOTALS}
    for case in specs:
        remaining(started)
        directory = output / "cases" / case["key"]
        for kind, program in (("plain", "plain_cli"), ("observed", "observer_cli")):
            recorded = read_json(directory / kind / "command.json")
            # Retained commands contain the original execution location. Infer
            # that root only from the mapped output token, then reproduce every
            # token; the verifier never executes these historical paths.
            suffix = "/cases/" + case["key"] + "/" + kind + "/out.pcm"
            require(recorded[-1].endswith(suffix), "recorded output mapping drift")
            run_root = Path(recorded[-1][:-len(suffix)])
            expected = mapped_argv(case, run_root / "build" / manifest["programs"][program]["path"],
                                   run_root / "cases" / case["key"] / kind, run_root / "originals" / case["group"])
            require(recorded == expected, "unfrozen argv mutation")
            execution = read_json(directory / kind / "execution.json")
            require(execution["status"] == "COMPLETE" and execution["returncode"] == 0 and
                    0 <= execution["elapsed_seconds"] <= execution["timeout_seconds"] <= BUDGET and
                    execution["process_budget_seconds"] == BUDGET, "process execution/budget failure")
            env = execution["environment"]
            expected_tap = str(run_root / "cases" / case["key"] / "taps") if kind == "observed" else None
            expected_keys = {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL"}
            if kind == "observed":
                expected_keys.add("AP_D1_STAGE_DIR")
            require(set(env["keys"]) <= expected_keys and "LC_ALL" in env["keys"] and
                    ("AP_D1_STAGE_DIR" in env["keys"]) == (kind == "observed") and
                    env["LC_ALL"] == "C" and env["AP_D1_STAGE_DIR"] == expected_tap,
                    "observer environment mapping drift")
        result = inspect_case(output, case, index["source_revision"])
        cases.append(result)
        totals["frames"] += case["frames"]
        totals["samples"] += case["samples"]
        totals["capture_only_frames"] += case["frames"] if case["capture_only"] else 0
        for name, count in result["calls"].items():
            totals[name] += count
    require(totals == TOTALS, "aggregate stage count drift")
    aggregates = []
    for group in ("A", "C"):
        for profile in PROFILES:
            for scene in sorted({c["scenario"] for c in cases if c["group"] == group}):
                subset = [c for c in cases if c["group"] == group and c["profile"] == profile and c["scenario"] == scene]
                changes = {}
                for stage in ("aec", "joint_ns_frequency_res", "agc"):
                    vals = [c["stage_changes"][stage]["common"]["near_si_sdr_change_db"] for c in subset
                            if c["stage_changes"][stage]["present"] and
                            c["stage_changes"][stage]["common"]["near_si_sdr_change_db"] is not None]
                    changes[stage] = {"count": len(vals), "min": min(vals) if vals else None,
                                      "median": statistics.median(vals) if vals else None, "max": max(vals) if vals else None}
                aggregates.append({"group": group, "profile": profile, "scenario": scene, "cases": len(subset),
                                   "descriptive_common_span_si_sdr_changes_db": changes})
    prior = {"A/report.json": descriptor(output / "originals/A/result/report.json"),
             "C/report.json": descriptor(output / "originals/C/result/report.json"),
             "C/scores.json": descriptor(output / "originals/C/result/scores.json"),
             "C/predictions.json": descriptor(output / "originals/C/result/predictions.json")}
    result = {"schema_version": 1, "experiment": EXPERIMENT, "status": "MEASUREMENT_VALID",
              "measurement_valid": True, "data_role": "disclosed-regression", "promotion_allowed": False,
              "acoustic_thresholds_applied": False, "models_executed": False, "canonical_reports_recomputed": False,
              "original_source_revision": BASE_SHA, "source_revision": index["source_revision"],
              "source_tree": index["source_tree"], "build_identity": manifest,
              "prior_report_bindings": prior, "matrix_totals": totals, "case_count": len(cases),
              "measurement_contract": {"sample_rate_hz": RATE, "frame_samples": HOP,
                  "physical_common_span": "[0,N-160)", "lane_offsets_samples": LANES,
                  "windows": "every fixed 16000-sample physical window, final window clipped at N-160",
                  "normalization": "clean-near S16 / 32768 only; Float32 taps unchanged",
                  "near_si_sdr_function": "validation/tools/run_validation_engine.py::si_sdr_span",
                  "lag_search": False, "ns_res_separate_contributions": False,
                  "gate_count_means": "outer adaptation eligibility, not actual MDF updates",
                  "C_near_truth": "not scored; duplex_mono includes echo",
                  "phase_windows_are_human_vad": False,
                  "stage_scores_replace_historical_canonical_scores": False},
              "aggregates": aggregates, "cases": cases}
    remaining(started)
    return result


def verify_origins(output):
    lock = read_json(output / "origins/source-lock.json")
    require(lock == read_json(LOCK), "source lock differs from frozen implementation")
    receipt = read_json(output / "origins/acquisition.json")
    require(receipt["status"] == "PASS" and receipt["lock_sha256"] == digest(output / "origins/source-lock.json"),
            "retained source receipt invalid")
    selected = read_json(output / "origins/selected-members.json")
    specs = catalog(output / "originals/A", output / "originals/C")
    required = {"A": set(A_METADATA), "C": set(C_METADATA)}
    for case in specs:
        required[case["group"]].update(n for n in case["inputs"].values() if n)
        required[case["group"]].update(case["auxiliary_inputs"])
        required[case["group"]].update(case["original_dir"] + "/" + n for n in ORIGINAL_CASE_FILES)
    require(set(selected) == {"A", "C"}, "original group inventory drift")
    for entry in lock["artifacts"]:
        group = entry["key"]
        archive_path = output / "original-archives" / (group + ".zip")
        names = archive_index(archive_path, entry, lock)
        if group == "C":
            required[group].update(n for n in names if n.startswith("result/"))
        actual = set()
        for path in (output / "originals" / group).rglob("*"):
            require(not path.is_symlink(), "symlink retained original")
            if path.is_file():
                actual.add(path.relative_to(output / "originals" / group).as_posix())
        require(actual == set(selected[group]) == required[group], "retained original member closure drift: " + group)
        with zipfile.ZipFile(archive_path) as archive:
            for name, expected in selected[group].items():
                path = safe(output / "originals" / group, name)
                require(descriptor(path) == expected and path.read_bytes() == archive.read(name),
                        "retained original member drift: " + group + "/" + name)
    return {group: len(files) for group, files in selected.items()}


def payload_inventory(output):
    inventory = {}
    for path in sorted(output.rglob("*")):
        require(not path.is_symlink(), "symlink in D1 output")
        if path.is_file():
            name = path.relative_to(output).as_posix()
            if name != "artifact-manifest.json" and name not in VERIFY_FILES:
                inventory[name] = descriptor(path)
    return inventory


def worker_verify(args):
    started, output = time.monotonic(), Path(args.output).resolve()
    manifest = read_json(output / "artifact-manifest.json")
    require(manifest["experiment"] == EXPERIMENT and manifest["files"] == payload_inventory(output),
            "sealed D1 payload drift")
    for phase in ("run", "analysis"):
        record = read_json(output / (phase + "-phase.json"))
        require(record["status"] == "COMPLETE" and record["returncode"] == 0 and
                0 <= record["elapsed_seconds"] <= BUDGET and record["budget_seconds"] == BUDGET,
                "phase was incomplete or exceeded budget")
    counts = verify_origins(output)
    recomputed = analysis_payload(output, origins_verified=True)
    require(recomputed == read_json(output / "report.json"), "readback differs from stored stage report")
    remaining(started)
    write_json(output / "readback.json", {"schema_version": 1, "experiment": EXPERIMENT, "status": "PASS",
               "DSP_executed": False, "models_executed": False, "original_members_rechecked": counts,
               "case_count": 60, "matrix_totals": TOTALS, "report": descriptor(output / "report.json"),
               "manifest": descriptor(output / "artifact-manifest.json")})
    remaining(started)


def supervise(args, phase):
    output, started = Path(args.output).resolve(), time.monotonic()
    command = [sys.executable, str(Path(__file__).resolve()), "--worker-phase", phase, "--output", str(output)]
    if phase == "run":
        command += ["--original-a", str(Path(args.original_a).resolve()), "--original-c", str(Path(args.original_c).resolve()),
                    "--build-dir", str(Path(args.build_dir).resolve())]
    status, error, code = "FAILED", None, None
    with (output / (phase + ".log")).open("wb") as log:
        child = subprocess.Popen(command, cwd=ROOT, env=process_environment(), stdout=log,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = child.wait(timeout=remaining(started, 2.0))
            status = "COMPLETE" if code == 0 else "FAILED"
        except subprocess.TimeoutExpired:
            status, error = "TIMEOUT", "frozen phase wall budget reached"
            os.killpg(child.pid, signal.SIGKILL)
            code = child.wait(timeout=1)
    elapsed = time.monotonic() - started
    if elapsed > BUDGET:
        status, error = "TIMEOUT", "frozen phase budget exceeded during finalization"
    record = {"schema_version": 1, "experiment": EXPERIMENT, "phase": phase, "status": status,
              "command": command, "returncode": code, "error": error, "terminal": True,
              "elapsed_seconds": elapsed, "budget_seconds": BUDGET}
    write_json(output / (phase + "-phase.json"), record)
    record["elapsed_seconds"] = time.monotonic() - started
    record["elapsed_scope"] = "through initial phase write; final write also deadline checked"
    write_json(output / (phase + "-phase.json"), record)
    if time.monotonic() - started > BUDGET:
        status = record["status"] = "TIMEOUT"
        record["error"] = "phase final write exceeded frozen budget"
        record["elapsed_seconds"] = time.monotonic() - started
        write_json(output / (phase + "-phase.json"), record)
    return status == "COMPLETE", started


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("run", "verify"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--original-a", type=Path)
    parser.add_argument("--original-c", type=Path)
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--worker-phase", choices=("run", "analysis", "verify"), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if args.worker_phase:
        try:
            if args.worker_phase == "run":
                worker_run(args)
            elif args.worker_phase == "analysis":
                write_json(output / "report.json", analysis_payload(output))
            else:
                worker_verify(args)
            return 0
        except Exception as exc:
            write_json(output / (args.worker_phase + "-error.json"),
                       {"experiment": EXPERIMENT, "status": "MEASUREMENT_INVALID", "type": type(exc).__name__,
                        "error": str(exc), "promotion_allowed": False})
            if args.worker_phase == "verify":
                write_json(output / "readback.json", {"experiment": EXPERIMENT, "status": "FAIL",
                           "DSP_executed": False, "models_executed": False, "error": str(exc)})
            print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
            return 1
    if args.command == "run":
        if not all((args.original_a, args.original_c, args.build_dir)):
            parser.error("run requires --original-a, --original-c and --build-dir")
        require(not args.output.exists() and not args.output.is_symlink(), "new, absent output directory required")
        output.mkdir(parents=True, exist_ok=False)
        success, _ = supervise(args, "run")
        if success:
            success, analysis_started = supervise(args, "analysis")
            if success:
                write_json(output / "artifact-manifest.json", {"schema_version": 1, "experiment": EXPERIMENT,
                           "files": payload_inventory(output)})
                phase = read_json(output / "analysis-phase.json")
                phase["elapsed_seconds"] = time.monotonic() - analysis_started
                if phase["elapsed_seconds"] > BUDGET:
                    phase["status"], success = "TIMEOUT", False
                write_json(output / "analysis-phase.json", phase)
                manifest = read_json(output / "artifact-manifest.json")
                manifest["files"]["analysis-phase.json"] = descriptor(output / "analysis-phase.json")
                write_json(output / "artifact-manifest.json", manifest)
                if time.monotonic() - analysis_started > BUDGET:
                    success = False
                    phase["status"] = "TIMEOUT"
                    phase["error"] = "artifact sealing exceeded frozen analysis budget"
                    phase["elapsed_seconds"] = time.monotonic() - analysis_started
                    write_json(output / "analysis-phase.json", phase)
                    manifest["files"]["analysis-phase.json"] = descriptor(output / "analysis-phase.json")
                    write_json(output / "artifact-manifest.json", manifest)
        if not success:
            write_json(output / "measurement-invalid.json", {"experiment": EXPERIMENT,
                       "status": "MEASUREMENT_INVALID", "promotion_allowed": False,
                       "reason": "See preserved phase/error files; no acoustic interpretation is admitted."})
        print(json.dumps({"experiment": EXPERIMENT, "status": "MEASUREMENT_VALID" if success else "MEASUREMENT_INVALID",
                          "output": str(output), "verify_required": success}, sort_keys=True))
        return 0 if success else 1
    if args.command == "verify":
        require(output.is_dir() and not args.output.is_symlink(), "existing D1 output required")
        success, _ = supervise(args, "verify")
        print(json.dumps({"experiment": EXPERIMENT, "status": "PASS" if success else "FAIL", "DSP_executed": False}, sort_keys=True))
        return 0 if success else 1
    parser.error("choose run or verify")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as exc:
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        raise SystemExit(2)
