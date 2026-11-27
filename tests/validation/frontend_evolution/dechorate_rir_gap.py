#!/usr/bin/env python3
"""Fixed measured-RIR support diagnostic; no product DSP, tuning or promotion."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import platform
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLAN = ".github/research/frontend-evolution-v1/dechorate-rir-gap-v1.json"
SCRIPT = "tests/validation/frontend_evolution/dechorate_rir_gap.py"
TEST = "tests/validation/frontend_evolution/test_dechorate_rir_gap.py"
DOC = "docs/research/frontend-evolution-v1/DECHORATE_RIR_GAP_V1.zh-CN.md"
GATE = ".github/scripts/verify-docs-gate.sh"
EXPERIMENT = "FE-SIM-RIR-SUPPORT-GAP-V1"
DECISION = "DESCRIPTIVE_ONLY_NO_PROMOTION_NO_MODEL_FIT"
STATUS = "MEASURED_DESCRIPTIVE_RIR_SUPPORT_GAP"
FIXED_WINDOWS = [[0.0, 0.005], [0.005, 0.02], [0.02, 0.05],
                 [0.05, 0.1], [0.1, 0.2], [0.2, 1.0]]
ROOMS = ["000000", "000001", "000010", "000100", "001000", "010000",
         "011000", "011100", "011110", "011111", "020002"]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _pairs(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, "duplicate JSON key: " + key)
        obj[key] = value
    return obj


def read_json(path):
    def bad_constant(value):
        raise ValueError("non-finite JSON constant: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=_pairs, parse_constant=bad_constant)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True,
                                    ensure_ascii=False, allow_nan=False) + "\n",
                          encoding="utf-8")


def validate_plan(p):
    require(p["schema_version"] == 1 and p["experiment_id"] == EXPERIMENT, "experiment identity")
    require(p["data_role"] == "disclosed-development-diagnostic", "data role")
    require(p["candidate_budget"] == 0 and p["promotion_allowed"] is False and
            p["model_parameter_fit_allowed"] is False, "candidate/fit/promotion forbidden")
    m, d, b = p["model"], p["metadata"], p["budget"]
    require(m["speed_of_sound_m_s"] == 343.0 and m["source_rate_hz"] == 16000 and
            m["kernel_support_source_samples"] == 2 and m["all_six_walls_retained"] is True,
            "fixed motion-v2 model family")
    require(d["room_dimensions_m"] == [5.705, 5.965, 2.355] and
            d["sample_rate_hz"] == 48000 and d["ir_shape"] == [1, 5, 48000] and
            d["ir_dtype"] == "float64", "native geometry/IR contract")
    require(p["dependencies"]["wall_state_tokens"] == ROOMS and
            p["dependencies"]["physical_room_count"] == 1 and
            p["dependencies"]["scored_microphone_indices_zero_based"] == [0, 1],
            "fixed dependent strata/channel roles")
    require(p["measurement"]["fixed_record_windows_seconds"] == FIXED_WINDOWS and
            p["measurement"]["absolute_arrival_error_samples"] is None and
            p["measurement"]["noise_subtraction"] is False and
            p["measurement"]["roundoff_fraction_tolerance"] == 1e-10,
            "fixed measurement definitions")
    require(b == {"source_object_count": 12, "source_total_bytes": 19403164,
                  "source_ceiling_bytes": 67108864, "analysis_attempts": 1,
                  "automatic_retries": 0, "analysis_wall_seconds": 90,
                  "output_ceiling_bytes": 100000000, "candidate_executions": 0,
                  "parameter_searches": 0}, "fixed budget")
    require(p["acceptance"]["success_status"] == STATUS and
            p["acceptance"]["decision"] == DECISION, "fixed conclusion")


def contract(root=ROOT):
    p = read_json(root / PLAN)
    validate_plan(p)
    for rel, expected in p["source_pins"].items():
        require(digest(root / rel) == expected, "predecessor source drift: " + rel)
    q = read_json(root / p["source"]["qualification_path"])
    require(p["source"]["objects"] == q["inventory_protocol"]["expected_selected_objects"],
            "original twelve-object lock changed")
    require(p["source"]["sha256"] == digest(root / p["source"]["qualification_path"]),
            "qualification identity")
    return p


def support_length(p):
    """Conservative contiguous support, allowing every interior source/mic position.

    For any wall image s', |r-s'|-|r-s| <= |s'-s| <= 2*max(room).
    Add the full two-source-sample interpolation support and one endpoint bin.
    The oracle interval is a relaxation of the seven sparse taps, not their fit.
    """
    m, d = p["model"], p["metadata"]
    excess = 2.0 * max(d["room_dimensions_m"])
    seconds = excess / m["speed_of_sound_m_s"] + \
        m["kernel_support_source_samples"] / m["source_rate_hz"]
    return {"excess_distance_bound_m": excess, "model_speed_m_s": m["speed_of_sound_m_s"],
            "kernel_support_seconds": m["kernel_support_source_samples"] / m["source_rate_hz"],
            "support_seconds_before_endpoint_bin": seconds,
            "native_window_samples": int(math.ceil(seconds * d["sample_rate_hz"])) + 1,
            "sample_rate_hz": d["sample_rate_hz"],
            "scope": "declared c=343 model family; not a universal physical propagation bound"}


def energy_coverage(values, length, sample_rate, windows):
    """A declared oracle energy statistic, never an alignment for another score."""
    require(type(length) is int and length > 0 and len(values) >= length, "short IR/window")
    energy = []
    for value in values:
        value = float(value)
        require(math.isfinite(value), "non-finite IR")
        power = value * value
        require(math.isfinite(power), "IR energy overflow")
        energy.append(power)
    total = math.fsum(energy)
    require(math.isfinite(total) and total > 0.0, "zero/invalid total IR energy")
    current = math.fsum(energy[:length])
    maximum, start = current, 0
    # O(N), with predetermined rebasing to bound accumulated subtraction error.
    for index in range(1, len(energy) - length + 1):
        if index % 1024 == 0:
            current = math.fsum(energy[index:index + length])
        else:
            current += energy[index + length - 1] - energy[index - 1]
        if current > maximum:
            maximum, start = current, index
    # Recompute the selected interval without the sliding-sum roundoff.
    maximum = math.fsum(energy[start:start + length])
    ratio = maximum / total
    require(math.isfinite(ratio) and -1e-10 <= ratio <= 1.0 + 1e-10, "invalid energy ratio")
    ratio = min(1.0, max(0.0, ratio))
    parts = []
    for begin, end in windows:
        a, b = int(round(begin * sample_rate)), int(round(end * sample_rate))
        require(0 <= a < b <= len(energy), "fixed record window outside original IR")
        value = math.fsum(energy[a:b])
        parts.append({"start_sample": a, "end_sample_exclusive": b,
                      "energy": value, "fraction": value / total})
    return {"sample_count": len(energy), "total_energy": total, "window_samples": length,
            "oracle_window_start_sample": start, "oracle_window_end_sample_exclusive": start + length,
            "oracle_max_window_energy": maximum, "oracle_covered_energy_fraction": ratio,
            "uncovered_energy_fraction_lower_bound": max(0.0, 1.0 - ratio),
            "fixed_record_windows": parts, "absolute_arrival_error_samples": None}


def verify_inputs(directory, p):
    require(directory.is_dir() and not directory.is_symlink(), "input root must be an ordinary directory")
    objects = p["source"]["objects"]
    require({x.name for x in directory.iterdir()} == {o["name"] for o in objects},
            "exact twelve input objects required")
    for item in objects:
        path = directory / item["name"]
        require(path.is_file() and not path.is_symlink(), "non-regular/symlink input: " + path.name)
        require(path.stat().st_size == item["size_bytes"] and digest(path) == item["sha256"],
                "original object size/hash mismatch: " + path.name)
    require(sum(x["size_bytes"] for x in objects) == p["source"]["total_bytes"] == 19403164,
            "input byte budget")


def _plain(value):
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if hasattr(value, "tolist"):
        return _plain(value.tolist())
    if isinstance(value, (list, tuple)):
        return [_plain(x) for x in value]
    return value


def validate_header(shape, dtype, rate, delays):
    require(shape == [1, 5, 48000] and dtype == "float64", "native IR shape/dtype")
    require(rate == 48000.0 and delays == [0.0] * 5, "rate/delay metadata")


def metadata_only(directory, p):
    """Inspect structure and declared coordinates without reading Data.IR values."""
    import h5py
    import numpy as np
    expected = p["metadata"]
    with h5py.File(directory / "dEchorate_annotations.h5", "r") as h:
        global_receivers = np.asarray(h["microphones"])[..., :5].T
        global_source = np.asarray(h["sources_directional_position"])[..., 0]
        room = _plain(h["room_size"][()])
        require(room == expected["room_dimensions_m"], "annotation room dimensions")
    records = []
    for obj in p["source"]["objects"]:
        if not obj["name"].endswith(".sofa"):
            continue
        with h5py.File(directory / obj["name"], "r") as h:
            ir = h["Data.IR"]
            validate_header(list(ir.shape), str(ir.dtype), float(h["Data.SamplingRate"][0]),
                            _plain(h["Data.Delay"][0]))
            fields = {key: _plain(h[key][()]) for key in expected["geometry_invariant_fields"]}
            require(fields == expected["geometry_invariant_fields"], "fixed geometry metadata drift")
            require(np.array_equal(np.asarray(h["ReceiverPosition"])[:, :, 0], global_receivers) and
                    np.array_equal(np.asarray(h["SourcePosition"])[0], global_source),
                    "SOFA global-coordinate/export identity")
            for key in ("SourcePosition", "ReceiverPosition", "ListenerPosition"):
                require(_plain(h[key].attrs["Type"]) == "cartesian" and
                        _plain(h[key].attrs["Units"]) == "metre", "coordinate type/units")
            for key, value in (("SOFAConventions", "SingleRoomSRIR"), ("SOFAConventionsVersion", "1.0"),
                               ("SourceShortName", "loudspeaker_id:1"), ("ListenerShortName", "array_id:0")):
                require(_plain(h.attrs[key]) == value, "SOFA identity: " + key)
            require(_plain(h.attrs["Title"]) == obj["name"][:-5], "filename/Title identity")
            records.append({"name": obj["name"], "ir_shape": list(ir.shape), "ir_dtype": str(ir.dtype),
                            "geometry": fields, "room_description": _plain(h.attrs["RoomDescription"]),
                            "room_temperature_placeholder": _plain(h["RoomTemperature"][()]),
                            "room_volume_placeholder": _plain(h["RoomVolume"][()]),
                            "embedded_license_sha256": hashlib.sha256(h.attrs["License"]).hexdigest()})
    return records


def _import_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def measure(directory, p, root=ROOT):
    verify_inputs(directory, p)
    metadata = metadata_only(directory, p)
    sys.path.insert(0, str(root / "validation/tools"))
    loader = _import_file("_rir_gap_canonical_loader", root / "validation/tools/build_dechorate_artifact_exclusion_corpus.py")
    require(Path(sys.modules["build_validation_corpus"].__file__).resolve() ==
            (root / "validation/tools/build_validation_corpus.py").resolve(), "loader dependency origin")
    rooms = loader.load_frozen_rirs(directory, read_json(root / p["source"]["qualification_path"]))
    bound = support_length(p)
    rows = []
    for room in ROOMS:
        for mic in (0, 1):
            values = rooms[room][mic]
            row = energy_coverage(values, bound["native_window_samples"], 48000, FIXED_WINDOWS)
            raw = values.astype("<f8", copy=False).tobytes()
            row.update({"room_state": room, "mic_index_zero_based": mic,
                        "original_file": "dEchorate_room%s_src1_arr1_mics1-5.sofa" % room,
                        "decoded_float64_le_sha256": hashlib.sha256(raw).hexdigest()})
            rows.append(row)
    missing = [r["uncovered_energy_fraction_lower_bound"] for r in rows]
    return {"experiment_id": EXPERIMENT, "decision": DECISION, "data_role": p["data_role"],
            "promotion_allowed": False, "model_parameter_fit_performed": False,
            "physical_room_count": 1, "dependent_room_state_count": 11,
            "native_ir_materialized_count": 55, "scored_ir_count": 22,
            "product_dsp_executions": 0, "support_bound": bound, "metadata": metadata,
            "cases": rows, "descriptive_uncovered_fraction":
            {"minimum": min(missing), "median": statistics.median(missing), "maximum": max(missing)}}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8").strip()


def source_files(p):
    return sorted(set(p["source_pins"]) | {PLAN, SCRIPT, TEST, DOC, GATE})


def source_record(p, revision, require_head):
    require(re.fullmatch("[0-9a-f]{40}", revision) is not None, "full execution source SHA required")
    if require_head:
        require(git("rev-parse", "HEAD") == revision and
                not git("status", "--porcelain", "--untracked-files=no"), "clean exact execution source required")
    files = {}
    for rel in source_files(p):
        data = (ROOT / rel).read_bytes()
        frozen = subprocess.check_output(["git", "show", revision + ":" + rel], cwd=ROOT)
        require(data == frozen, "checkout differs from execution source: " + rel)
        files[rel] = hashlib.sha256(data).hexdigest()
    return {"code_revision": revision, "files": files}


def runtime_identity():
    import h5py
    import numpy
    native = {}
    for name, module in sorted(sys.modules.items()):
        path = getattr(module, "__file__", None)
        if name.startswith(("h5py.", "numpy.")) and path and path.endswith(".so"):
            native[name] = {"path": path, "sha256": digest(path)}
    return {"python": sys.version, "system": platform.system(), "machine": platform.machine(),
            "release": platform.release(), "numpy": numpy.__version__, "h5py": h5py.__version__,
            "hdf5": h5py.version.hdf5_version,
            "numpy_module_sha256": digest(numpy.__file__), "h5py_module_sha256": digest(h5py.__file__),
            "loaded_native_modules": native}


def exact_manifest(directory):
    files = {}
    total = 0
    for path in sorted(directory.rglob("*")):
        require(not path.is_symlink(), "symlink in evidence")
        if path.is_file() and path != directory / "manifest.json":
            rel = str(path.relative_to(directory))
            total += path.stat().st_size
            require(total <= 100000000 and len(files) < 100, "bounded evidence file set")
            files[rel] = digest(path)
    return {"schema_version": 1, "experiment_id": EXPERIMENT, "files": files, "total_bytes": total}


def reject_failed_output(output):
    require(not (output / "failure.json").exists(), "failed execution cannot verify")


def validate_result(result, expected, p):
    require(result["status"] == STATUS and result["experiment_id"] == EXPERIMENT, "execution status")
    require(result["analysis_attempts"] == 1 and result["automatic_retries"] == 0, "attempt budget")
    elapsed = result["elapsed_seconds"]
    require(type(elapsed) in (int, float) and math.isfinite(elapsed) and
            0.0 <= elapsed <= p["budget"]["analysis_wall_seconds"], "actual elapsed budget")
    require(result["measurement"] == expected, "independent metric/role/count/conclusion recomputation differs")


def run(input_dir, output, revision):
    require(not output.exists() and not output.is_symlink(), "output must be new")
    resolved = output.resolve()
    require(input_dir.resolve() not in (resolved, *resolved.parents), "output must not be within input")
    require(ROOT.resolve() not in (resolved, *resolved.parents), "output must be outside checkout")
    started = time.monotonic()
    output.mkdir(parents=True, exist_ok=False)
    try:
        p = contract()
        source = source_record(p, revision, True)
        verify_inputs(input_dir, p)
        shutil.copytree(input_dir, output / "source")
        for rel in source["files"]:
            destination = output / "code" / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, destination)
        measured = measure(output / "source", p)
        verify_inputs(input_dir, p)
        require(source_record(p, revision, True) == source, "source changed during execution")
        runtime = runtime_identity()
        elapsed = time.monotonic() - started
        require(elapsed <= p["budget"]["analysis_wall_seconds"], "analysis wall budget exceeded")
        result = {"schema_version": 1, "experiment_id": EXPERIMENT, "status": STATUS,
                  "analysis_attempts": 1, "automatic_retries": 0, "elapsed_seconds": elapsed,
                  "source": source, "runtime": runtime, "measurement": measured,
                  "command": [sys.executable, *sys.argv]}
        write_json(output / "result.json", result)
        manifest = exact_manifest(output)
        require(manifest["total_bytes"] <= p["budget"]["output_ceiling_bytes"], "output byte budget")
        require(time.monotonic() - started <= p["budget"]["analysis_wall_seconds"], "final wall budget exceeded")
        write_json(output / "manifest.json", manifest)
        print(json.dumps({"status": STATUS, "decision": DECISION, "scored_ir_count": 22,
                          "promotion_allowed": False}, sort_keys=True))
        return result
    except Exception as exc:
        write_json(output / "failure.json", {"experiment_id": EXPERIMENT, "status": "FAIL",
                   "error_type": type(exc).__name__, "error": str(exc),
                   "elapsed_seconds": time.monotonic() - started, "promotion_allowed": False})
        raise


def verify(output):
    reject_failed_output(output)
    p = contract()
    manifest = read_json(output / "manifest.json")
    require(manifest == exact_manifest(output), "complete evidence manifest mismatch")
    require(manifest["total_bytes"] <= p["budget"]["output_ceiling_bytes"], "output budget")
    result = read_json(output / "result.json")
    source = source_record(p, result["source"]["code_revision"], False)
    require(source == result["source"], "source identity mismatch")
    for rel, expected in source["files"].items():
        require(digest(output / "code" / rel) == expected, "archived source mismatch: " + rel)
    expected = measure(output / "source", p)
    validate_result(result, expected, p)
    summary = {"status": "VERIFIED_DESCRIPTIVE_RIR_SUPPORT_GAP", "experiment_id": EXPERIMENT,
               "decision": DECISION, "scored_ir_count": 22, "physical_room_count": 1,
               "promotion_allowed": False, "new_product_dsp_executions": 0}
    print(json.dumps(summary, sort_keys=True))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    task = sub.add_parser("run")
    task.add_argument("--input-dir", type=Path, required=True)
    task.add_argument("--output", type=Path, required=True)
    task.add_argument("--execution-source", required=True)
    check = sub.add_parser("verify")
    check.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    def expired(_signum, _frame):
        raise TimeoutError("fixed 90-second wall budget exceeded")
    try:
        require(hasattr(signal, "setitimer"), "this bounded CLI requires a Unix wall timer")
        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, 90.0)
        if args.command == "run":
            run(args.input_dir.absolute(), args.output.absolute(), args.execution_source)
        else:
            verify(args.output.resolve())
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        return 1
    finally:
        if hasattr(signal, "setitimer"):
            signal.setitimer(signal.ITIMER_REAL, 0.0)


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
