#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import re
from pathlib import Path

import h5py
import numpy as np

ROOM_RE = re.compile(r"_room([0-9]{6})_")


def _dataset(f, *names):
    for name in names:
        if name in f:
            return np.asarray(f[name])
    raise KeyError(f"missing SOFA dataset; tried {names}; root keys={list(f.keys())}")


def _scalar_dataset(f, *names):
    x = _dataset(f, *names)
    vals = np.asarray(x).reshape(-1)
    if vals.size != 1:
        raise ValueError(f"expected scalar {names}, got shape={x.shape}")
    return float(vals[0])


def _tensor_fingerprint(x):
    a = np.ascontiguousarray(np.asarray(x))
    h = hashlib.sha256()
    h.update(str(a.dtype).encode())
    h.update(b"\0")
    h.update(json.dumps(list(a.shape)).encode())
    h.update(b"\0")
    h.update(a.tobytes())
    return h.hexdigest()


def _json_attr(v):
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, np.generic):
        return v.item()
    return v


def _optional_scalar(f, name):
    if name not in f:
        return None
    a = np.asarray(f[name]).reshape(-1)
    if a.size != 1:
        return None
    return float(a[0])


def _metric_db(value, reference, factor):
    if value <= 0.0 or reference <= 0.0:
        raise ValueError("non-positive value in dB comparison")
    return factor * math.log10(value / reference)


def _read_case(path):
    mm = ROOM_RE.search(path.name)
    if not mm:
        raise ValueError(f"missing room token: {path.name}")
    room = mm.group(1)
    with h5py.File(path, "r") as f:
        ir = _dataset(f, "Data.IR", "Data_IR")
        if ir.ndim == 3 and ir.shape[0] == 1:
            ir = ir[0]
        if ir.ndim != 2 or ir.shape[0] != 5:
            raise ValueError(f"expected five-receiver RIR tensor, got {ir.shape} in {path.name}")
        ir = np.asarray(ir, dtype=np.float64)
        if not np.isfinite(ir).all():
            raise ValueError(f"non-finite RIR samples in {path.name}")

        fs = _scalar_dataset(f, "Data.SamplingRate", "Data_SamplingRate")
        delay = _dataset(f, "Data.Delay", "Data_Delay")
        source = _dataset(f, "SourcePosition")
        receiver = _dataset(f, "ReceiverPosition")
        listener = _dataset(f, "ListenerPosition")

        energy = np.sum(ir * ir, axis=1)
        peak = np.max(np.abs(ir), axis=1)
        if np.any(energy <= 0.0) or np.any(peak <= 0.0):
            raise ValueError(f"non-positive RIR metric in {path.name}")

        room_vars = {}
        for name in [
            "RoomFloorIsRefective",
            "RoomCleilingIsRefective",
            "RoomWestIsRefective",
            "RoomSouthIsRefective",
            "RoomEastIsRefective",
            "RoomNorthIsRefective",
            "RoomHasFornitures",
        ]:
            room_vars[name] = _optional_scalar(f, name)

        return {
            "room": room,
            "filename": path.name,
            "sampling_rate_hz": fs,
            "data_ir_shape": list(ir.shape),
            "data_delay_shape": list(np.asarray(delay).shape),
            "data_delay_all_zero": bool(np.all(np.asarray(delay) == 0)),
            "source_position_shape": list(np.asarray(source).shape),
            "receiver_position_shape": list(np.asarray(receiver).shape),
            "listener_position_shape": list(np.asarray(listener).shape),
            "source_position_fingerprint": _tensor_fingerprint(source),
            "receiver_position_fingerprint": _tensor_fingerprint(receiver),
            "listener_position_fingerprint": _tensor_fingerprint(listener),
            "total_energy_per_mic": energy.tolist(),
            "peak_abs_per_mic": peak.tolist(),
            "room_metadata": room_vars,
            "root_keys": sorted(list(f.keys())),
            "global_attrs": {k: _json_attr(v) for k, v in f.attrs.items()},
        }


def analyze(input_dir, qualification_manifest):
    q = json.loads(Path(qualification_manifest).read_text())
    proto = q["inventory_protocol"]
    expected = [o for o in proto["expected_selected_objects"] if o["name"].endswith(".sofa")]
    if len(expected) != 11:
        raise ValueError(f"expected 11 frozen SOFA objects, got {len(expected)}")

    cases = []
    for obj in expected:
        path = Path(input_dir) / obj["name"]
        data = path.read_bytes()
        if len(data) != int(obj["size_bytes"]):
            raise ValueError(f"size drift: {path.name}")
        if hashlib.sha256(data).hexdigest() != obj["sha256"]:
            raise ValueError(f"sha256 drift: {path.name}")
        cases.append(_read_case(path))
    cases.sort(key=lambda c: c["room"])

    if len({c["room"] for c in cases}) != 11:
        raise ValueError("room coverage drift")
    if any(c["sampling_rate_hz"] != 48000.0 for c in cases):
        raise ValueError("sampling-rate drift")
    if not all(c["data_delay_all_zero"] for c in cases):
        raise ValueError("non-zero SOFA Data.Delay")

    source_fps = {c["source_position_fingerprint"] for c in cases}
    receiver_fps = {c["receiver_position_fingerprint"] for c in cases}
    listener_fps = {c["listener_position_fingerprint"] for c in cases}
    if len(source_fps) != 1:
        raise ValueError("SourcePosition varies across frozen room configurations")
    if len(receiver_fps) != 1:
        raise ValueError("ReceiverPosition varies across frozen room configurations")
    if len(listener_fps) != 1:
        raise ValueError("ListenerPosition varies across frozen room configurations")

    ref = next((c for c in cases if c["room"] == "000000"), None)
    if ref is None:
        raise ValueError("reference room000000 missing")
    ref_energy = np.asarray(ref["total_energy_per_mic"], dtype=np.float64)
    ref_peak = np.asarray(ref["peak_abs_per_mic"], dtype=np.float64)

    for c in cases:
        energy = np.asarray(c["total_energy_per_mic"], dtype=np.float64)
        peak = np.asarray(c["peak_abs_per_mic"], dtype=np.float64)
        c["total_energy_db_relative_room000000_per_mic"] = [
            _metric_db(float(v), float(r), 10.0) for v, r in zip(energy, ref_energy)
        ]
        c["peak_db_relative_room000000_per_mic"] = [
            _metric_db(float(v), float(r), 20.0) for v, r in zip(peak, ref_peak)
        ]
        c["median_total_energy_db_relative_room000000"] = float(
            np.median(c["total_energy_db_relative_room000000_per_mic"])
        )
        c["median_peak_db_relative_room000000"] = float(
            np.median(c["peak_db_relative_room000000_per_mic"])
        )

    energy_db = np.asarray(
        [c["total_energy_db_relative_room000000_per_mic"] for c in cases], dtype=np.float64
    )
    peak_db = np.asarray(
        [c["peak_db_relative_room000000_per_mic"] for c in cases], dtype=np.float64
    )
    room_energy_med = np.median(energy_db, axis=1)
    room_peak_med = np.median(peak_db, axis=1)

    aggregate = {
        "room_count": len(cases),
        "sampling_rate_hz": 48000,
        "reference_room": "000000",
        "geometry_invariant": True,
        "source_position_fingerprint": next(iter(source_fps)),
        "receiver_position_fingerprint": next(iter(receiver_fps)),
        "listener_position_fingerprint": next(iter(listener_fps)),
        "per_mic_total_energy_span_db": (np.max(energy_db, axis=0) - np.min(energy_db, axis=0)).tolist(),
        "median_per_mic_total_energy_span_db": float(np.median(np.max(energy_db, axis=0) - np.min(energy_db, axis=0))),
        "room_median_total_energy_relative_db_min": float(np.min(room_energy_med)),
        "room_median_total_energy_relative_db_max": float(np.max(room_energy_med)),
        "room_median_total_energy_relative_db_span": float(np.max(room_energy_med) - np.min(room_energy_med)),
        "per_mic_peak_span_db": (np.max(peak_db, axis=0) - np.min(peak_db, axis=0)).tolist(),
        "median_per_mic_peak_span_db": float(np.median(np.max(peak_db, axis=0) - np.min(peak_db, axis=0))),
        "room_median_peak_relative_db_min": float(np.min(room_peak_med)),
        "room_median_peak_relative_db_max": float(np.max(room_peak_med)),
        "room_median_peak_relative_db_span": float(np.max(room_peak_med) - np.min(room_peak_med)),
        "activity_or_dtd_executed": False,
        "audio_synthesized": False,
        "rir_normalized_or_modified": False,
        "absolute_spl_or_device_gain_claimed": False,
        "selection_threshold_derived": False,
        "candidate_authority": False,
    }

    return {
        "schema_version": 1,
        "investigation": "dechorate-ground-truth-diagnostic-v1",
        "interpretation_boundary": {
            "allowed": "relative measured acoustic-transfer magnitude across fixed source/array/microphone geometry and frozen room configurations",
            "prohibited": "absolute SPL calibration, device playback-to-microphone gain, or a detector boundary",
        },
        "first_sofa_schema": {
            "root_keys": cases[0]["root_keys"],
            "global_attrs": cases[0]["global_attrs"],
            "data_ir_shape": cases[0]["data_ir_shape"],
            "source_position_shape": cases[0]["source_position_shape"],
            "receiver_position_shape": cases[0]["receiver_position_shape"],
            "listener_position_shape": cases[0]["listener_position_shape"],
        },
        "cases": cases,
        "aggregate": aggregate,
    }


def self_test():
    e = [1.0, 4.0]
    assert abs(_metric_db(e[1], e[0], 10.0) - 6.020599913279624) < 1e-12
    assert abs(_metric_db(2.0, 1.0, 20.0) - 6.020599913279624) < 1e-12
    x = np.arange(6, dtype=np.float64).reshape(2, 3)
    assert _tensor_fingerprint(x) == _tensor_fingerprint(x.copy())
    print("self-test: PASS")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir")
    ap.add_argument("--qualification-manifest")
    ap.add_argument("--output")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.input_dir or not args.qualification_manifest or not args.output:
        ap.error("--input-dir, --qualification-manifest and --output are required")
    result = analyze(args.input_dir, args.qualification_manifest)
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result["aggregate"], sort_keys=True))


if __name__ == "__main__":
    main()
