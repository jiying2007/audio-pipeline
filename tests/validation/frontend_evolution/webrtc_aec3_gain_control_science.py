#!/usr/bin/env python3
"""Single bounded LT2 continuation; reuse sealed predecessor scoring and native runner.

No acquisition, compilation, tuning, new corpus or F05 access. The engineering
plan remains non-authorizing; this separately frozen admission permits only
one neutral and at most one support-local unity call, with no retry.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
import signal
import stat
import subprocess
import sys
import tarfile
import time
import zipfile

sys.dont_write_bytecode = True
EXPERIMENT = "F07-LT2-AEC3-JOINT-GAIN-CONTROLLED-SYNTHESIS-V1"
HEAD = "dd7d5d8892ebe6ad767aaa1d6112638df5474207"
ZIP_SHA = "1a3ea980cbba85ac4a926b4286bba51c959b901feb011001ee5b217d8ac9edbb"
OLD_SHA = "311c4c452b90ea51734ac4e17ede0f56d95422baf63836d0564373a74076ad4d"
HOST_SHA = "9c5d86020d7903917e6e3fe3c12885ed10d835482f41b821066ed1aeabd67408"
HOST_RECEIPT_SHA = "f3d5369c3a83e5af8313f03a6d9e9b35fb324886e914072e6eabf139c43a832a"
ENGINEERING_READER_SHA = "e504534cc25386c2b5294335e9fe858499b76ad6dfa47198f307b3b06b510d59"
SCORE_READER_SHA = "f4869b6994511709a4e568b6c672801cbdb52fafa57e55ef9ce1e7cc29aee13e"
OLD_RESULT_SHA = "d099931f9c526db499912a62e14237602d598f74377b8c4dad8efb9751e0827d"
OLD_MANIFEST_SHA = "9ca7385bd0374f4feb80bc100b67f42b17be11527afbd298bcb0b9e0dc82fee5"
BINARY_SHA = "da0b8d18cbb52fe569e077b2c096918fd10c68a2d67d71e626309ccf0ea7b8b2"
LIB_SHA = "34ec6f84a33e7e6f315a262246c11163dd659946868a14428f9440d14b3d040f"
OLD_ROOT = "aec3-synthesis-selection-science-20261128/selection_evidence/measurement-dd2a416a/"
OLD_PREFIX = "aec3-synthesis-selection-science-20261128/"
INPUTS = ("mic.pcm", "render.pcm", "target.s16", "echo.s16")
OLD_FILES = ("output.pcm", "linear.f32", "stderr.log", "metadata.json", "frames.jsonl")
SAMPLES = 256000
SUPPORT = (1525, 1976)
MODES = ("gain-observe", "gain-unity")
ROLE = "DISCLOSED_DEVELOPMENT_DIAGNOSTIC_NOT_HOLDOUT"


def check(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def raw(path):
    path = Path(path)
    check(not any(p.is_symlink() for p in (path, *path.parents)), "symlink path")
    info = path.stat()
    check(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 128 * 1024 * 1024,
          "bounded ordinary file required")
    return path.read_bytes()


def unique(items):
    out = {}
    for key, value in items:
        check(key not in out, "duplicate JSON key")
        out[key] = value
    return out


def reject_constant(value):
    raise ValueError("nonfinite JSON constant: " + value)


def doc(data):
    return json.loads(data, object_pairs_hook=unique, parse_constant=reject_constant)


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as f:
        f.write(data)


def record(path, value):
    write(path, (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode())


def exact(data, sha):
    check(digest(data) == sha, "frozen byte identity mismatch: " + sha)
    return data


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def member(archive, name):
    matches = [m for m in archive.getmembers() if m.name == name]
    check(len(matches) == 1 and matches[0].isfile() and matches[0].size <= 64 * 1024 * 1024,
          "archive member missing, duplicate or nonregular: " + name)
    return archive.extractfile(matches[0]).read()


def prepare(root, old_path, zip_path, host_path):
    root.mkdir(parents=True, exist_ok=False)
    exact(raw(old_path), OLD_SHA)
    exact(raw(zip_path), ZIP_SHA)
    exact(raw(host_path), HOST_SHA)
    with tarfile.open(old_path) as t:
        old = doc(exact(member(t, OLD_ROOT + "result.json"), OLD_RESULT_SHA))
        manifest = doc(exact(member(t, OLD_ROOT + "manifest.json"), OLD_MANIFEST_SHA))["files"]
        check(old["data_role"] == ROLE and old["promotion_allowed"] is False, "old data role")
        for name in ["result.json", "manifest.json", "experiment.json"] + ["inputs/" + n for n in INPUTS] + ["observe/" + n for n in OLD_FILES]:
            data = member(t, OLD_ROOT + name)
            if name not in ("manifest.json", "result.json"):
                exact(data, manifest[name])
            write(root / "predecessor" / name, data)
        for name, sha in old["code_identity"]["files_sha256"].items():
            check(not Path(name).is_absolute() and ".." not in Path(name).parts, "unsafe source name")
            write(root / "canonical" / name, exact(member(t, OLD_ROOT + "measurement-source/" + name), sha))
        write(root / "readers/old_score.py", exact(member(t, OLD_PREFIX + "method_independent/read_selection_science_independently.py"), SCORE_READER_SHA))
    with tarfile.open(host_path) as t:
        host = exact(member(t, "host/host-engineering.json"), HOST_RECEIPT_SHA)
        write(root / "host-engineering.json", host)
        write(root / "readers/engineering.py", exact(member(t, "independent/lt2-independent-engineering.py"), ENGINEERING_READER_SHA))
    with zipfile.ZipFile(zip_path) as z:
        ci = doc(z.read("ci-receipt.json")); manifest = doc(z.read("bundle/bundle.json"))
        check(ci["status"] == manifest["status"] == "PASS_GAIN_CONTROL_ENGINEERING_ONLY" and
              ci["code_revision"] == manifest["code_revision"] == HEAD and
              ci["acoustic_measurement"] == "NOT_RUN", "engineering receipt identity")
        for name, sha in (("bin/webrtc-aec3-selection-runner", BINARY_SHA),
                          ("bin/lib/libwebrtc-audio-processing-2.so.1", LIB_SHA)):
            check(manifest["files"][name] == sha, "engineering manifest identity")
            write(root / name, exact(z.read("bundle/" + name), sha))
        (root / "bin/webrtc-aec3-selection-runner").chmod(0o755)
        for name in ("bundle/bundle.json", "bundle/build/runner-build.json", "bundle/source-change/source-transform.json", "bundle/engineering/engineering.json", "ci-receipt.json"):
            write(root / "ci" / name, z.read(name))
    check_inputs(root)
    record(root / "prepared.json", {"experiment_id": EXPERIMENT, "engineering_source": HEAD,
           "archives": [OLD_SHA, ZIP_SHA, HOST_SHA], "speech_calls": 0, "promotion_allowed": False})


def check_inputs(root):
    old = doc(exact(raw(root / "predecessor/result.json"), OLD_RESULT_SHA))
    manifest = doc(exact(raw(root / "predecessor/manifest.json"), OLD_MANIFEST_SHA))["files"]
    check(old["data_role"] == ROLE and old["promotion_allowed"] is False, "role drift")
    for name in ["experiment.json"] + ["inputs/" + n for n in INPUTS] + ["observe/" + n for n in OLD_FILES]:
        data = exact(raw(root / "predecessor" / name), manifest[name])
        if name.startswith("inputs/"):
            check(len(data) == SAMPLES * 2, "partial input")
    for name, sha in old["code_identity"]["files_sha256"].items():
        exact(raw(root / "canonical" / name), sha)
    exact(raw(root / "readers/old_score.py"), SCORE_READER_SHA)
    exact(raw(root / "readers/engineering.py"), ENGINEERING_READER_SHA)
    exact(raw(root / "bin/webrtc-aec3-selection-runner"), BINARY_SHA)
    exact(raw(root / "bin/lib/libwebrtc-audio-processing-2.so.1"), LIB_SHA)
    host = doc(exact(raw(root / "host-engineering.json"), HOST_RECEIPT_SHA))
    check(host["status"] == "PASS_INDEPENDENT_SAME_HOST_GAIN_CONTROL_ENGINEERING_ONLY" and
          host["binary_sha256"] == BINARY_SHA and host["head"] == HEAD and host["speech_calls"] == 0 and
          host["runtime_before"] == host["runtime_after"] and host["scientific_execution_authorized"] is False,
          "same-host engineering receipt missing")
    return old, host


def environment(root):
    return {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LD_LIBRARY_PATH": str(root / "bin/lib")}


def runtime(root, host):
    binary = root / "bin/webrtc-aec3-selection-runner"
    output = subprocess.check_output(["/usr/bin/ldd", str(binary)], env=environment(root), text=True, timeout=10)
    check("not found" not in output, "missing runtime library")
    libs = {}
    for path in re.findall(r"(?<!\S)(/[^\s]+)", output):
        p = Path(path).resolve()
        libs[str(p)] = digest(raw(p))
    expected = host["runtime_before"]
    relocated = {str(root / "bin/lib" / Path(k).name) if k.endswith("libwebrtc-audio-processing-2.so.1") else k: v
                 for k, v in expected["libraries"].items()}
    result = {"machine": platform.machine(), "release": platform.release(),
              "os_release_sha256": digest(Path("/etc/os-release").read_bytes()), "libraries": libs}
    check(libs == relocated and all(result[k] == expected[k] for k in ("machine", "release", "os_release_sha256")),
          "runtime differs from qualified host; stop before speech")
    return result


def read_arm(root, mode, reader):
    folder = root / mode
    data = raw(folder / "output.pcm"); linear = raw(folder / "linear.f32")
    check(len(data) == 2 * SAMPLES and len(linear) == 4 * SAMPLES, "output sample count")
    meta = doc(raw(folder / "metadata.json")); old = doc(raw(root / "predecessor/observe/metadata.json"))
    for key in ("requested_config", "applied_config", "mode", "sample_format", "sample_rate_hz", "frame_samples",
                "mic_channels", "render_channels", "output_channels", "channel_map", "stream_delay_ms",
                "adapter_lookahead_frames", "padded_samples", "tail_flush_samples", "latency_components_samples",
                "call_order", "aec3_includes_internal_residual_suppression", "pure_linear_aec", "adapter_normalization",
                "actual_processing_channels", "actual_processing_sample_rate_hz"):
        check(meta[key] == old[key], "processing contract changed: " + key)
    check(meta["status"] == "OK" and meta["completed_frames"] == meta["input_frames"] == 1600 and
          meta["output_sample_frames"] == SAMPLES and meta["algorithmic_latency_samples"] == 128 and
          meta["reset_before_frame"] is None and meta["aec3_synthesis_selection"]["mode"] == mode and
          meta["aec3_joint_gain_control"] == {"mode": mode, "support_blocks": [1525, 1976], "block_samples": 64,
          "cng_imaginary_endpoint_policy": reader.ENDPOINT_POLICY, "gain_controlled_cng_and_ola_may_change": True,
          "promotion_allowed": False}, "new adapter metadata mismatch")
    frames = [doc(line) for line in raw(folder / "frames.jsonl").splitlines()]
    check(len(frames) == 1600 and all(f["frame_index"] == i and f["input_sample_frames_available"] ==
          f["output_sample_frames_emitted"] == f["linear_output_sample_frames_emitted"] == (i+1)*160 and
          f["reset_before_frame"] is False and f["algorithmic_latency_samples"] == 128 and
          f["linear_signal_delay_samples"] == 64 for i, f in enumerate(frames)), "frame/reset/timing drift")
    parsed = reader.traces(raw(folder / "stderr.log"), 4000, mode)
    return data, linear, parsed


def baseline(root, observed, reader):
    folder = root / "predecessor/observe"
    check(observed[0] == raw(folder / "output.pcm") and observed[1] == raw(folder / "linear.f32"),
          "BASELINE_REPRODUCTION_FAILED: full final or linear bytes differ")
    old = reader.traces(raw(folder / "stderr.log"), 4000, "observe")
    check(observed[2][0] == old[0] and observed[2][2] == old[2],
          "BASELINE_REPRODUCTION_FAILED: original selector rows/bytes differ")


def evaluate(root, arms):
    source = root / "canonical/tests/validation/frontend_evolution"
    sys.path.insert(0, str(source))
    import webrtc_aec3_selection as canonical
    return {mode: canonical.score_observation(root / "predecessor/inputs", {"final": value[0], "linear": value[1]})
            for mode, value in arms.items()}


def decide(scores):
    a, b = (scores[m]["final"] for m in MODES)
    x, y = (v["near"]["double-before"] for v in (a, b))
    values = [v[k] for v in (x, y) for k in ("si_sdr_db", "normalized_mse")]
    if not all(v["projection_identifiable"] for v in (x,y)) or not all(v is not None and math.isfinite(v) for v in values):
        return {"decision": "NOT_IDENTIFIABLE", "promotion_allowed": False}
    improve = y["si_sdr_db"] > x["si_sdr_db"] and y["normalized_mse"] < x["normalized_mse"]
    nonimprove = y["si_sdr_db"] <= x["si_sdr_db"] and y["normalized_mse"] >= x["normalized_mse"]
    far = [(a["far"]["aggregate_ratio_db"], b["far"]["aggregate_ratio_db"])] + [(l["echo_to_output_ratio_db"], r["echo_to_output_ratio_db"]) for l,r in zip(a["far"]["blocks"], b["far"]["blocks"])]
    check(len(far) == 20, "far block count")
    adverse = [f"far_ratio_{i}" for i,(l,r) in enumerate(far) if l is not None and r is not None and r < l]
    unavailable = [f"far_ratio_{i}" for i,(l,r) in enumerate(far) if l is None or r is None]
    amplitude = {k: b["raw_amplitude"][k] - a["raw_amplitude"][k] for k in ("peak", "rms", "negative_endpoint_count", "positive_endpoint_count")}
    adverse += [k + "_increase" for k,v in amplitude.items() if v > 0]
    outcome = ("JOINT_GAIN_CONTROLLED_SYNTHESIS_HYPOTHESIS_NOT_SUPPORTED" if nonimprove else
               "INCONCLUSIVE_MIXED_INDICATORS" if not improve else
               "NEAR_END_GAIN_TRADEOFF_OBSERVED_NO_PROMOTION" if adverse else
               "INCONCLUSIVE_FAR_NOT_IDENTIFIABLE" if unavailable else
               "JOINT_GAIN_CONTROLLED_SYNTHESIS_EFFECT_SUPPORTED_IN_ONE_DISCLOSED_WINDOW")
    return {"decision": outcome, "si_sdr_delta_db": y["si_sdr_db"]-x["si_sdr_db"],
            "nmse_delta": y["normalized_mse"]-x["normalized_mse"], "adverse_directions": adverse,
            "unavailable_far_directions": unavailable, "amplitude_deltas": amplitude,
            "amplitude_increase_is_conservative_tradeoff_not_proven_quality_loss": True, "promotion_allowed": False}


def invoke(root, mode, deadline):
    folder = root / mode; folder.mkdir(exist_ok=False)
    inputs = root / "predecessor/inputs"
    cmd = [str(root / "bin/webrtc-aec3-selection-runner"), "--mode", "aec3", "--mic-channels", "1", "--channel-map", "0",
           "--mic", str(inputs / "mic.pcm"), "--render", str(inputs / "render.pcm"), "--output", str(folder / "output.pcm"),
           "--metadata", str(folder / "metadata.json"), "--frame-times", str(folder / "frames.jsonl"), "--aec3-export-mode", "factory-on",
           "--linear-output", str(folder / "linear.f32"), "--aec3-synthesis-selection", mode]
    start = time.monotonic_ns(); witness = {"command": cmd, "environment": environment(root), "started_monotonic_ns": start,
                                            "requested_samples": SAMPLES, "retry_index": 0}
    record(folder / "invocation-start.json", witness)
    timeout = min(30, deadline-time.monotonic()); check(timeout > 0, "science wall budget exhausted")
    with (folder / "stdout.log").open("xb") as out, (folder / "stderr.log").open("xb") as err:
        proc = subprocess.Popen(cmd, env=environment(root), stdout=out, stderr=err, start_new_session=True)
        try:
            rc = proc.wait(timeout=timeout)
        except BaseException:
            os.killpg(proc.pid, signal.SIGKILL); proc.wait(); raise
    end = time.monotonic_ns()
    record(folder / "command.json", dict(witness, pid=proc.pid, exit_code=rc, finished_monotonic_ns=end))
    check(rc == 0, "native science call failed; no retry")


def admission(root, public_revision, plan_sha):
    check(re.fullmatch(r"[0-9a-f]{40}", public_revision) and public_revision != "0"*40, "public freeze revision")
    plan = doc(exact(raw(root / "admission.json"), plan_sha))
    check(plan["experiment_id"] == EXPERIMENT and plan["engineering_revision"] == HEAD and
          plan["execution_root"] == str(root) and plan["speech_execution_authorized"] is True and
          plan["promotion_allowed"] is False and plan["data_role"] == ROLE and
          plan["max_calls"] == 2 and plan["max_capture_seconds"] == 32 and plan["retries"] == 0 and
          plan["primary_samples"] == [97600,126400] and plan["support_blocks"] == list(SUPPORT) and
          plan["archive_sha256"] == {"predecessor": OLD_SHA, "engineering": ZIP_SHA, "host": HOST_SHA} and
          plan["binary_sha256"] == BINARY_SHA and plan["host_receipt_sha256"] == HOST_RECEIPT_SHA,
          "frozen scientific admission does not match executor contract")
    source_sha = plan["executor_sha256"]
    exact(raw(Path(__file__).resolve()), source_sha)
    return source_sha


def run(root, public_revision, plan_sha):
    source_sha = admission(root, public_revision, plan_sha)
    check(not (root / "attempt-start.json").exists(), "once-only science identity already attempted")
    old, host = check_inputs(root)
    before = runtime(root, host)
    reader = module(root / "readers/engineering.py", "lt2_engineering_reader")
    started = time.monotonic(); deadline = started + 300
    record(root / "attempt-start.json", {"experiment_id": EXPERIMENT, "public_revision": public_revision,
           "executor_sha256": source_sha, "admission_sha256": plan_sha, "engineering_source": HEAD, "max_calls": 2, "max_seconds": 32,
           "retries": 0, "runtime_before": before, "data_role": ROLE, "promotion_allowed": False})
    try:
        invoke(root, MODES[0], deadline)
        neutral = read_arm(root, MODES[0], reader); baseline(root, neutral, reader)
        record(root / "neutral-gate.json", {"baseline_final_linear_selector_bytes_equal": True,
               "decided_monotonic_ns": time.monotonic_ns(), "second_call_permitted": True})
        invoke(root, MODES[1], deadline)
        unity = read_arm(root, MODES[1], reader)
        check(neutral[1] == unity[1] and neutral[0][:1526*64*2] == unity[0][:1526*64*2], "upstream linear or causal prefix differs")
        paired = reader.compare(neutral[2], unity[2])
        scores = evaluate(root, dict(zip(MODES, (neutral, unity))))
        check(scores[MODES[0]] == old["measurements"]["scores"]["observe"], "canonical neutral score reproduction failed")
        after = runtime(root, host); check(before == after, "runtime identity changed")
        check_inputs(root); check(time.monotonic() < deadline, "science wall budget exceeded")
        result = {"experiment_id": EXPERIMENT, "status": "EXECUTED_BOUNDED_GAIN_CONTROL_DIAGNOSTIC", "data_role": ROLE,
                  "promotion_allowed": False, "independent_confirmation": False, "public_revision": public_revision,
                  "engineering_source": HEAD, "executor_sha256": source_sha, "admission_sha256": plan_sha, "comparison": paired,
                  "scores": scores, "decision": decide(scores), "speech_calls": 2, "capture_seconds": 32,
                  "acoustic_retries": 0, "training_runs": 0, "local_compiler_calls": 0, "runtime_after": after,
                  "wall_seconds": time.monotonic()-started}
        record(root / "result.json", result)
    except BaseException as exc:
        record(root / "failure.json", {"error": repr(exc), "speech_call_starts": sum((root/m/"invocation-start.json").exists() for m in MODES), "retry_permitted": False, "promotion_allowed": False})
        raise


def verify(root):
    old, _ = check_inputs(root)
    check(not (root / "failure.json").exists(), "failed attempt cannot qualify")
    result = doc(raw(root / "result.json")); start = doc(raw(root / "attempt-start.json"))
    check(admission(root, start["public_revision"], start["admission_sha256"]) == result["executor_sha256"] and
          result["admission_sha256"] == start["admission_sha256"] and result["public_revision"] == start["public_revision"] and
          result["engineering_source"] == HEAD and result["data_role"] == ROLE and result["promotion_allowed"] is False and
          result["speech_calls"] == 2 and result["capture_seconds"] == 32 and result["acoustic_retries"] == 0 and
          result["local_compiler_calls"] == result["training_runs"] == 0 and 0 < result["wall_seconds"] <= 300,
          "frozen result authority/budget mismatch")
    reader = module(root / "readers/engineering.py", "lt2_engineering_reader")
    arms = {mode: read_arm(root, mode, reader) for mode in MODES}
    a,b = (arms[m] for m in MODES); baseline(root, a, reader)
    check(a[1] == b[1] and a[0][:1526*64*2] == b[0][:1526*64*2], "linear or causal prefix mismatch")
    check(reader.compare(a[2], b[2]) == result["comparison"], "paired trace result mismatch")
    calls = [doc(raw(root / m / "command.json")) for m in MODES]
    gate = doc(raw(root / "neutral-gate.json"))
    check(calls[0]["finished_monotonic_ns"] <= gate["decided_monotonic_ns"] < calls[1]["started_monotonic_ns"] and
          all(c["exit_code"] == c["retry_index"] == 0 and c["requested_samples"] == SAMPLES for c in calls), "call chronology/budget")
    canonical = evaluate(root, arms)
    check(canonical == result["scores"] and canonical[MODES[0]] == old["measurements"]["scores"]["observe"], "canonical readback mismatch")
    independent = module(root / "readers/old_score.py", "lt2_independent_scorer")
    plan = doc(raw(root / "canonical/.github/research/frontend-evolution-v1/webrtc-aec3-linear-tap-v1.json"))
    _, target = independent.pcm(root / "predecessor/inputs/target.s16", "s16")
    _, echo = independent.pcm(root / "predecessor/inputs/echo.s16", "s16")
    for mode in MODES:
        _, final = independent.pcm(root / mode / "output.pcm", "s16")
        _, linear = independent.pcm(root / mode / "linear.f32", "f32")
        independently_scored = independent.scoring(target, echo, {"final": final, "linear": linear}, plan["metrics"]["near_phase_samples"])
        check(independently_scored == canonical[mode], "independent numerical readback differs")
    check(decide(canonical) == result["decision"] and start["runtime_before"] == result["runtime_after"], "decision/runtime drift")
    record(root / "independent-readback.json", {"status": "PASS_RAW_GAIN_CONTROL_SCIENCE_READBACK", "result_sha256": digest(raw(root / "result.json")),
           "speech_calls": 2, "new_native_calls": 0, "numeric_tolerance": 0, "decision": result["decision"], "promotion_allowed": False})


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("command", choices=("prepare", "run", "verify")); p.add_argument("--root", type=Path, required=True)
    p.add_argument("--old", type=Path); p.add_argument("--zip", type=Path); p.add_argument("--host", type=Path)
    p.add_argument("--public-revision"); p.add_argument("--plan-sha")
    args = p.parse_args(); root = args.root.resolve()
    if args.command == "prepare": prepare(root, args.old, args.zip, args.host)
    elif args.command == "run": run(root, args.public_revision, args.plan_sha)
    else: verify(root)


if __name__ == "__main__":
    main()
