#!/usr/bin/env python3
"""Fixed real-Mandarin host model integration; never a corpus-quality gate."""
from __future__ import annotations

import argparse
import array
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "validation/tools"))
sys.path.insert(0, str(ROOT / "tests/validation"))
import build_validation_corpus as generator
import downstream_metrics as metrics
import dualmic_profile_support as profile_support
import mandarin_downstream_source as source
import run_dualmic_profile_replay as profile_replay

RATE, HOP, FLUSH = 16000, 160, 5120
BUDGET = 300.0
SEAL_RESERVE = 3.0
CASES = ("raw", "call", "assistant", "raw_duplex", "call_duplex", "assistant_duplex")
INPUT_KEYS = ("clean_mono", "clean_capture", "duplex_mono", "duplex_capture", "duplex_render")
KEYWORDS = "g uǎng zh ōu sh ì @广州市\n"
ASR_SETTINGS = {"model": source.VOSK_PREFIX, "runtime": "vosk-0.3.45-C-API",
                "sample_rate_hz": RATE, "feed_samples": HOP, "grammar": None,
                "word_details": False, "finish": "FinalResult", "extra_flush_samples": 0}
KWS_SETTINGS = {"model": source.KWS_PREFIX, "runtime": "sherpa-onnx-1.13.4",
                "sample_rate_hz": RATE, "feature_dim": 80, "provider": "cpu", "num_threads": 1,
                "max_active_paths": 4, "num_trailing_blanks": 1, "keywords_score": 1.0,
                "keywords_threshold": 0.25, "keywords": KEYWORDS, "feed_samples": HOP,
                "extra_flush_samples": FLUSH, "chunk": 8,
                "encoder": source.KWS_MEMBERS[0], "decoder": source.KWS_MEMBERS[1],
                "joiner": source.KWS_MEMBERS[2], "tokens": source.KWS_MEMBERS[3]}
BOUND_SOURCES = (
    "tests/validation/mandarin_downstream.py", "tests/validation/mandarin_downstream_source.py",
    "validation/tools/downstream_metrics.py", "validation/tools/build_validation_corpus.py",
    "tests/validation/dualmic_profile_support.py", "tests/validation/run_dualmic_profile_replay.py",
    "tests/validation/quality_metric_support.py", "validation/tools/run_validation.py",
    "validation/tools/run_validation_engine.py", "validation/tools/stage_profile_support.py",
    "examples/process_pcm.c", "CMakeLists.txt",
    "docs/research/frontend-evolution-v1/MANDARIN_DOWNSTREAM_V1_CONTRACT.zh-CN.md",
    "docs/research/frontend-evolution-v1/MANDARIN_DOWNSTREAM_V1_DUPLEX_ADDENDUM.zh-CN.md",
    "docs/research/frontend-evolution-v1/mandarin-downstream-v1-source-lock.json",
)


def load_json(path):
    def pairs(rows):
        result = {}
        for key, value in rows:
            source.require(key not in result, "duplicate JSON key: " + key)
            result[key] = value
        return result
    def bad_constant(value):
        raise ValueError("nonfinite JSON: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs,
                      parse_constant=bad_constant)


def pcm_bytes(values):
    pcm = array.array("h", values)
    if sys.byteorder != "little":
        pcm.byteswap()
    return pcm.tobytes()


def samples(data):
    source.require(len(data) % 2 == 0, "partial S16 input")
    result = array.array("h")
    result.frombytes(data)
    if sys.byteorder != "little":
        result.byteswap()
    return list(result)


def remaining(started, reserve=0.0):
    value = BUDGET - reserve - (time.monotonic() - started)
    if value <= 0:
        raise TimeoutError("frozen 300 second stage budget exceeded")
    return value


def identity(revision):
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    source.require(revision == actual and len(revision) == 40, "exact current source revision required")
    subprocess.run(["git", "diff", "--exit-code", revision, "--", "src", "include", *BOUND_SOURCES],
                   cwd=ROOT, check=True, capture_output=True, timeout=30)
    for name in BOUND_SOURCES:
        committed = subprocess.check_output(["git", "show", revision + ":" + name], cwd=ROOT, timeout=30)
        source.require(hashlib.sha256(committed).hexdigest() == source.digest(ROOT / name), "source bytes not committed: " + name)
    return {name: source.digest(ROOT / name) for name in BOUND_SOURCES}


def model_bindings(lock):
    def one(kind, prefix, settings):
        return metrics.manifest_digest({"kind": kind, "settings": settings,
            "model_files": {k: v for k, v in lock["model_files"].items() if k.startswith(prefix + "/")},
            "runtime_inventory_digest": metrics.manifest_digest(lock["runtime_files"])})
    return {"asr": one("asr", source.VOSK_PREFIX, ASR_SETTINGS),
            "kws": one("kws", source.KWS_PREFIX, KWS_SETTINGS)}


def derive_inputs(source_root):
    with wave.open(str(source_root / "assets/aishell-BAC009S0724W0121.wav"), "rb") as wav:
        source.require((wav.getnchannels(), wav.getframerate(), wav.getsampwidth(), wav.getcomptype())
                       == (1, RATE, 2, "NONE"), "fixed WAV geometry changed")
        original = samples(wav.readframes(wav.getnframes()))
    source.require(len(original) == 68496, "fixed Mandarin source length changed")
    clean = [0] * 8000 + original + [0] * 8000
    clean_padding = (-len(clean)) % HOP
    clean += [0] * clean_padding
    near = [0] * RATE + [int(round(x * 0.5)) for x in original] + [0] * RATE
    duplex_padding = (-len(near)) % HOP
    near += [0] * duplex_padding
    render = generator.render_signal(64000, 20261106) + [0] * (len(near) - 64000)
    echoes = [generator.echo_from_render(render, [(800 + mic, 0.25), (1280 + mic, 0.10)]) for mic in (0, 1)]
    channels = [[a + b for a, b in zip(near, echo)] for echo in echoes]
    source.require(all(-32768 <= x <= 32767 for channel in channels for x in channel), "frozen duplex mixture clips")
    return {"clean_mono": clean, "clean_capture": [x for value in clean for x in (value, value)],
            "duplex_mono": channels[0], "duplex_capture": [x for pair in zip(*channels) for x in pair],
            "duplex_render": render,
            "derivation": {"original_samples": len(original), "clean_preroll_samples": 8000,
                           "clean_postroll_samples": 8000, "clean_alignment_padding_samples": clean_padding,
                           "duplex_preroll_samples": RATE, "duplex_postroll_samples": RATE,
                           "duplex_alignment_padding_samples": duplex_padding,
                           "duplex_near_gain": 0.5, "duplex_render_seed": 20261106,
                           "duplex_render_active_samples": 64000,
                           "echo_taps_mic0": [[800, 0.25], [1280, 0.10]],
                           "echo_taps_mic1": [[801, 0.25], [1281, 0.10]],
                           "real_array_recording": False, "real_farend_speech": False}}


def expected_manifest(lock, views):
    cases = []
    for case_id in CASES:
        cases.append({"case_id": case_id, "pcm_sha256": views[case_id]["sha256"], "sample_rate_hz": RATE,
                      "samples": views[case_id]["bytes"] // 2,
                      "max_emitted_samples": views[case_id]["bytes"] // 2 + FLUSH,
                      "reference_text": lock["reference_text"], "reference_words": None, "kws_annotation": None})
    return {"schema_version": 1, "normalization": metrics.NORMALIZATION,
            "model_bindings": model_bindings(lock), "cases": cases}


def expected_preparation_files():
    names = {key + ".pcm" for key in INPUT_KEYS} | {"manifest.json", "keywords.txt"}
    for case_id in CASES:
        if not case_id.startswith("raw"):
            names.update("processed/" + case_id + "/" + name for name in
                         ("command.json", "out.pcm", "metrics.jsonl", "stdout.txt", "stderr.txt", "execution.json", "continuity.json"))
    return names


def prepare(source_root, processor, output, revision):
    source.require(not output.exists(), "preparation output must be fresh")
    output.mkdir(parents=True)
    started = time.monotonic()
    receipt = {"started_at": source.utc(), "budget_seconds": BUDGET, "model_inference_performed": False}
    try:
        lock = source.verify(source_root)
        bound = identity(revision)
        build = profile_replay.build_identity(processor, revision)
        source.require(build["values"].get("version") == "2.3.63", "unexpected DSP source version")
        data = derive_inputs(source_root)
        for key in INPUT_KEYS:
            (output / (key + ".pcm")).write_bytes(pcm_bytes(data[key]))
        defaults = {p: profile_replay.preset_tuning(processor, p)[0] for p in ("call", "assistant")}
        semantics = profile_support.validation_semantics(retain_root=output / "processed")
        views = {}
        for case_id in CASES:
            remaining(started)
            duplex = case_id.endswith("_duplex")
            raw = case_id.startswith("raw")
            key = "duplex" if duplex else "clean"
            if raw:
                path = output / (key + "_mono.pcm")
                continuity = {"output_mono_samples": len(data[key + "_mono"]), "raw_microphone0": True}
                render_summary = None
            else:
                profile = case_id.split("_")[0]
                case = {"case_id": case_id, "pipeline_profile": profile, "sample_rate_hz": RATE,
                        "mic_channels": 2, "mic_audio": key + "_capture.pcm",
                        "render_audio": "duplex_render.pcm" if duplex else None}
                output_pcm, trace, inputs = semantics.evaluation.invoke(processor, case, output / "inputs.json", output)
                path = output / "processed" / case_id / "out.pcm"
                continuity = profile_support.continuity(case, output_pcm, trace, inputs)
                render_summary = {"render_input_nonzero_samples": sum(x != 0 for x in (inputs["render"] or [])),
                                  "render_input_samples": len(inputs["render"] or []),
                                  "observed_trace_fields": sorted(trace[0]) if trace else [],
                                  "far_end_active_frames": sum(row.get("far_end_active", False) is True or row.get("far_end_active") == 1 for row in trace),
                                  "far_end_active_field_present": any("far_end_active" in row for row in trace)}
                if duplex:
                    source.require(render_summary["render_input_nonzero_samples"] > 0, "duplex reference was empty")
            pcm = path.read_bytes()
            source.require(len(pcm) == len(data[key + "_mono"]) * 2 and len(pcm) % (HOP * 2) == 0,
                           "model view is not complete continuous frames")
            views[case_id] = {"path": path.relative_to(output).as_posix(), "bytes": len(pcm),
                              "sha256": source.digest(path), "continuity": continuity, "render_summary": render_summary}
        manifest = expected_manifest(lock, views)
        source.write_json(output / "manifest.json", manifest)
        (output / "keywords.txt").write_text(KEYWORDS, encoding="utf-8")
        receipt.update({"status": "PREPARED_NOT_INFERRED", "exit_code": 0, "source_revision": revision,
                        "source_files": bound, "source_lock_sha256": source.digest(source.LOCK), "build_identity": build,
                        "defaults": defaults, "views": views, "derivation": data["derivation"],
                        "asr_settings": ASR_SETTINGS, "kws_settings": KWS_SETTINGS,
                        "manifest_digest": metrics.manifest_digest(manifest),
                        "prepared_files": source.file_inventory(output), "independent_original_utterances": 1})
        source.require(identity(revision) == bound and source.verify(source_root) == lock, "source changed during preparation")
        remaining(started)
    except Exception as exc:
        receipt.update({"status": "FAIL", "exit_code": 1, "error": type(exc).__name__ + ": " + str(exc)})
        raise
    finally:
        receipt.update({"ended_at": source.utc(), "elapsed_seconds": time.monotonic() - started})
        source.write_json(output / "preparation.json", receipt)
    return receipt


def verify_prepared(source_root, prepared):
    lock = source.verify(source_root)
    meta = load_json(prepared / "preparation.json")
    source.require(meta["status"] == "PREPARED_NOT_INFERRED" and type(meta["exit_code"]) is int and meta["exit_code"] == 0,
                   "preparation did not succeed")
    source.require(meta["source_lock_sha256"] == source.digest(source.LOCK), "source admission changed")
    source.require(set(meta["source_files"]) == set(BOUND_SOURCES), "source binding membership changed")
    revision = meta["source_revision"]
    source.require(type(revision) is str and len(revision) == 40 and all(c in "0123456789abcdef" for c in revision),
                   "invalid preparation source revision")
    for name, expected in meta["source_files"].items():
        source.require(source.digest(ROOT / name) == expected, "runner source changed since preparation: " + name)
        for ref in (revision, "HEAD"):
            committed = subprocess.check_output(["git", "show", ref + ":" + name], cwd=ROOT, timeout=30)
            source.require(hashlib.sha256(committed).hexdigest() == expected, "uncommitted/substituted source identity: " + name)
    inventory = source.file_inventory(prepared)
    source.require(set(inventory) == expected_preparation_files() | {"preparation.json"}, "preparation file membership changed")
    inventory.pop("preparation.json")
    source.require(inventory == meta["prepared_files"], "preparation byte inventory changed")
    for name, expected in meta["prepared_files"].items():
        relative = source.safe_member(name)
        path = prepared.joinpath(*relative.parts)
        source.require(path.is_file() and not path.is_symlink() and path.stat().st_size == expected["bytes"]
                       and source.digest(path) == expected["sha256"], "prepared evidence changed: " + name)
    manifest = load_json(prepared / "manifest.json")
    source.require(metrics.manifest_digest(manifest) == meta["manifest_digest"], "prepared manifest changed")
    source.require(manifest["model_bindings"] == model_bindings(lock), "prepared models/settings changed")
    source.require(tuple(c["case_id"] for c in manifest["cases"]) == CASES and set(meta["views"]) == set(CASES),
                   "fixed six-view set changed")
    data = derive_inputs(source_root)
    source.require(meta["derivation"] == data["derivation"], "input derivation receipt changed")
    for name in INPUT_KEYS:
        source.require((prepared / (name + ".pcm")).read_bytes() == pcm_bytes(data[name]), "derived source audio changed: " + name)
    actual_views = {}
    for case_id in CASES:
        key = "duplex" if case_id.endswith("_duplex") else "clean"
        relative = key + "_mono.pcm" if case_id.startswith("raw") else "processed/" + case_id + "/out.pcm"
        path = prepared / relative
        source.require(meta["views"][case_id]["path"] == relative and path.stat().st_size == len(data[key + "_mono"]) * 2,
                       "model view path or samples changed")
        actual_views[case_id] = {"bytes": path.stat().st_size, "sha256": source.digest(path)}
        source.require(all(meta["views"][case_id][k] == v for k, v in actual_views[case_id].items()), "model view identity changed")
    source.require(manifest == expected_manifest(lock, actual_views), "labels/audio/model manifest no longer derives from frozen source")
    source.require((prepared / "keywords.txt").read_text() == KEYWORDS, "keyword changed")
    return lock, meta, manifest


def vosk_infer(source_root, pcm):
    library_path = source_root / "runtime/vosk/libvosk.so"
    lib = ctypes.CDLL(str(library_path))
    functions = {
        "vosk_model_new": ([ctypes.c_char_p], ctypes.c_void_p),
        "vosk_model_free": ([ctypes.c_void_p], None),
        "vosk_recognizer_new": ([ctypes.c_void_p, ctypes.c_float], ctypes.c_void_p),
        "vosk_recognizer_free": ([ctypes.c_void_p], None),
        "vosk_recognizer_accept_waveform": ([ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int], ctypes.c_int),
        "vosk_recognizer_result": ([ctypes.c_void_p], ctypes.c_char_p),
        "vosk_recognizer_final_result": ([ctypes.c_void_p], ctypes.c_char_p),
    }
    for name, (args, result) in functions.items():
        fn = getattr(lib, name); fn.argtypes, fn.restype = args, result
    model = lib.vosk_model_new(os.fsencode(source_root / "models" / source.VOSK_PREFIX))
    source.require(model, "Vosk model load failed")
    recognizer, results, calls = None, [], 0
    try:
        recognizer = lib.vosk_recognizer_new(model, RATE)
        source.require(recognizer, "Vosk recognizer creation failed")
        for offset in range(0, len(pcm), HOP * 2):
            chunk = pcm[offset:offset + HOP * 2]
            status = lib.vosk_recognizer_accept_waveform(recognizer, chunk, len(chunk))
            calls += 1
            source.require(status in (0, 1), "Vosk AcceptWaveform failed")
            if status:
                payload = json.loads(lib.vosk_recognizer_result(recognizer).decode("utf-8"))
                results.append({"kind": "endpoint", "consumed_samples": (offset + len(chunk)) // 2, "result": payload})
        payload = json.loads(lib.vosk_recognizer_final_result(recognizer).decode("utf-8"))
        results.append({"kind": "final", "consumed_samples": len(pcm) // 2, "result": payload})
    finally:
        if recognizer:
            lib.vosk_recognizer_free(recognizer)
        lib.vosk_model_free(model)
    source.require(all(type(row["result"].get("text")) is str for row in results), "missing Vosk text result")
    return {"status": "ok", "text": " ".join(row["result"]["text"] for row in results if row["result"]["text"]),
            "accept_waveform_calls": calls, "consumed_samples": len(pcm) // 2, "raw_results": results,
            "native_library_sha256": source.digest(library_path)}


def kws_infer(source_root, prepared, pcm):
    runtime = source_root / "runtime"
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(runtime))
    import numpy as np
    import sherpa_onnx
    source.require(np.__version__ == "2.3.3" and sherpa_onnx.__version__ == "1.13.4", "runtime version mismatch")
    for module in (np, sherpa_onnx):
        source.require(Path(module.__file__).resolve().is_relative_to(runtime.resolve()), "unexpected Python runtime package")
    models = source_root / "models" / source.KWS_PREFIX
    kws = sherpa_onnx.KeywordSpotter(tokens=str(models / KWS_SETTINGS["tokens"]),
        encoder=str(models / KWS_SETTINGS["encoder"]), decoder=str(models / KWS_SETTINGS["decoder"]),
        joiner=str(models / KWS_SETTINGS["joiner"]), keywords_file=str(prepared / "keywords.txt"),
        num_threads=1, sample_rate=RATE, feature_dim=80, max_active_paths=4,
        num_trailing_blanks=1, keywords_score=1.0, keywords_threshold=0.25, provider="cpu")
    stream = kws.create_stream()
    audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / np.float32(32768.0)
    audio = np.concatenate((audio, np.zeros(FLUSH, dtype=np.float32)))
    events, calls, consumed = [], 0, 0
    def decode_available():
        nonlocal calls
        while kws.is_ready(stream):
            kws.decode_stream(stream); calls += 1
            result = kws.keyword_spotter.get_result(stream)
            if result.keyword:
                event = {"event_id": "event-" + str(len(events)), "keyword": result.keyword.strip(),
                         "emitted_at_sample": consumed, "tokens": list(result.tokens),
                         "token_timestamps_seconds": [float(x) for x in result.timestamps]}
                source.require(all(math.isfinite(x) for x in event["token_timestamps_seconds"]), "nonfinite KWS token time")
                events.append(event)
                kws.reset_stream(stream)
    for offset in range(0, len(audio), HOP):
        chunk = audio[offset:offset + HOP]
        stream.accept_waveform(RATE, chunk)
        consumed += len(chunk)
        decode_available()
    stream.input_finished()
    decode_available()
    return {"status": "ok", "events": events, "decode_stream_calls": calls,
            "accept_waveform_calls": len(audio) // HOP, "input_samples": len(pcm) // 2,
            "explicit_flush_samples": FLUSH, "consumed_samples": consumed,
            "numpy_version": np.__version__, "sherpa_onnx_version": sherpa_onnx.__version__,
            "token_time_is_trigger_latency": False}


def loaded_native_inventory(source_root):
    paths = set()
    for line in Path("/proc/self/maps").read_text().splitlines():
        fields = line.split(None, 5)
        if len(fields) == 6 and fields[-1].startswith("/") and ".so" in fields[-1]:
            paths.add(Path(fields[-1]))
    result = {}
    for path in sorted(paths):
        source.require(path.is_file(), "loaded native path cannot be hashed")
        name = path.relative_to(source_root).as_posix() if path.is_relative_to(source_root) else str(path)
        result[name] = {"sha256": source.digest(path), "bytes": path.stat().st_size,
                        "source": "frozen-runtime" if path.is_relative_to(source_root / "runtime") else "host-system"}
    for required in ("runtime/vosk/libvosk.so", "runtime/sherpa_onnx/lib/libonnxruntime.so"):
        source.require(required in result, "required actual native library not loaded: " + required)
    return result


def infer_case(source_root, prepared, case_id, output):
    source.require(case_id in CASES and not output.exists(), "invalid/fresh model case output")
    lock, meta, manifest = verify_prepared(source_root, prepared)
    path = prepared / meta["views"][case_id]["path"]
    pcm = path.read_bytes()
    started = time.monotonic()
    record = {"case_id": case_id, "pcm_sha256": source.digest(path), "started_at": source.utc(),
              "manifest_digest": metrics.manifest_digest(manifest), "model_bindings": manifest["model_bindings"]}
    try:
        record["asr"] = vosk_infer(source_root, pcm)
        record["kws"] = kws_infer(source_root, prepared, pcm)
        record["loaded_native_files"] = loaded_native_inventory(source_root)
        record["python"] = {"version": sys.version, "executable_sha256": source.digest(Path(sys.executable).resolve()),
                            "platform": platform.platform()}
        source.require(source.verify(source_root) == lock, "runtime/model bytes changed during inference")
        record.update({"status": "MODEL_EXECUTION_COMPLETE", "exit_code": 0})
    except Exception as exc:
        record.update({"status": "FAIL", "exit_code": 1, "error": type(exc).__name__ + ": " + str(exc)})
        raise
    finally:
        record.update({"ended_at": source.utc(), "elapsed_seconds": time.monotonic() - started})
        source.write_json(output, record)
    return record


def model_environment():
    return {"PATH": os.defpath, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
            "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}


def model_child(command, timeout):
    return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          env=model_environment(), timeout=timeout)


def seal_report(output, report, started):
    def snapshot():
        source.write_json(output / "report.json", report)
        inventory = source.file_inventory(output)
        inventory.pop("artifact-manifest.json", None)
        source.write_json(output / "artifact-manifest.json", inventory)

    snapshot()
    # This checkpoint includes the first complete report + artifact seal. The
    # final timing-field refresh below is necessarily outside its own timestamp;
    # the command's outer stage receipt measures that refresh and process exit.
    elapsed = time.monotonic() - started
    report.update({"ended_at": source.utc(), "elapsed_seconds": elapsed,
                   "timing_scope": "through first complete artifact seal; excludes final timing metadata refresh and process exit",
                   "seal_reserve_seconds": SEAL_RESERVE})
    if elapsed > BUDGET:
        report.update({"status": "FAIL", "exit_code": 1, "budget_exceeded": True,
                       "error": report.get("error", "TimeoutError: frozen 300 second stage budget exceeded during sealing")})
    snapshot()
    # Check again after refreshing both final files: an over-budget success
    # must not survive merely because the earlier checkpoint was in budget.
    completed = time.monotonic() - started
    if completed > BUDGET:
        report.update({"status": "FAIL", "exit_code": 1, "budget_exceeded": True,
                       "elapsed_seconds": completed, "ended_at": source.utc(),
                       "error": report.get("error", "TimeoutError: frozen 300 second stage budget exceeded during final metadata write")})
        snapshot()
        raise TimeoutError("frozen 300 second stage budget exceeded during finalization")


def run(source_root, prepared, output):
    source.require(not output.exists(), "formal matrix output must be fresh")
    output.mkdir(parents=True)
    started = time.monotonic()
    report = {"started_at": source.utc(), "budget_seconds": BUDGET, "cases": [],
              "experiment": "FE-C2-MANDARIN-DOWNSTREAM-V1", "promotion_allowed": False}
    try:
        lock, meta, manifest = verify_prepared(source_root, prepared)
        predicted = []
        # Third-party inference receives only required host execution settings,
        # never the parent's Actions/GitHub/cloud credential environment.
        for case_id in CASES:
            command = [sys.executable, str(Path(__file__).resolve()), "infer-case", "--source-root", str(source_root),
                       "--prepared", str(prepared), "--case-id", case_id, "--output", str(output / (case_id + ".json"))]
            try:
                child = model_child(command, remaining(started, SEAL_RESERVE))
            except subprocess.TimeoutExpired as exc:
                partial = exc.stdout or b""
                if isinstance(partial, str): partial = partial.encode("utf-8")
                (output / (case_id + ".log")).write_bytes(partial)
                report["cases"].append({"case_id": case_id, "command": command, "exit_code": None,
                                        "status": "TIMEOUT", "budget_seconds": BUDGET})
                source.write_json(output / "progress.json", report)
                raise
            (output / (case_id + ".log")).write_bytes(child.stdout)
            report["cases"].append({"case_id": case_id, "command": command, "exit_code": child.returncode})
            source.write_json(output / "progress.json", report)
            child.check_returncode()
            actual = load_json(output / (case_id + ".json"))
            source.require(actual["status"] == "MODEL_EXECUTION_COMPLETE" and actual["case_id"] == case_id,
                           "model case execution incomplete")
            predicted.append({"case_id": case_id, "pcm_sha256": actual["pcm_sha256"],
                              "asr": actual["asr"], "kws": actual["kws"]})
        predictions = {"schema_version": 1, "manifest_digest": metrics.manifest_digest(manifest),
                       "model_bindings": manifest["model_bindings"], "cases": predicted}
        source.write_json(output / "predictions.json", predictions)
        scored = metrics.evaluate(manifest, predictions)
        source.write_json(output / "scores.json", scored)
        source.require(verify_prepared(source_root, prepared) == (lock, meta, manifest), "preparation changed during matrix")
        remaining(started)
        report.update({"status": "MANDARIN_MODEL_INTEGRATION_SMOKE_ONLY", "exit_code": 0,
                       "source_revision": meta["source_revision"], "source_lock_sha256": source.digest(source.LOCK),
                       "manifest_digest": metrics.manifest_digest(manifest), "scores_sha256": source.digest(output / "scores.json"),
                       "predictions_sha256": source.digest(output / "predictions.json"), "original_utterances": 1,
                       "quality_decision": "DESCRIPTIVE_ONLY", "real_array_recording": False,
                       "not_run": ["human_KWS_temporal_truth", "real_negative_exposure", "population_CER_WER",
                                   "human_listening", "real_playback_barge_in", "physical_SSC305"]})
    except Exception as exc:
        report.update({"status": "FAIL", "exit_code": 1, "error": type(exc).__name__ + ": " + str(exc)})
        raise
    finally:
        seal_report(output, report, started)
    return report


def verify(source_root, prepared, output):
    lock, meta, manifest = verify_prepared(source_root, prepared)
    report = load_json(output / "report.json")
    source.require(report["status"] == "MANDARIN_MODEL_INTEGRATION_SMOKE_ONLY" and report["exit_code"] == 0,
                   "formal matrix incomplete")
    source.require(report["elapsed_seconds"] <= BUDGET and report["source_revision"] == meta["source_revision"], "matrix source/budget mismatch")
    artifact = load_json(output / "artifact-manifest.json")
    expected_files = {case_id + suffix for case_id in CASES for suffix in (".json", ".log")} | {
        "progress.json", "predictions.json", "scores.json", "report.json"}
    inventory = source.file_inventory(output)
    source.require(set(inventory) == expected_files | {"artifact-manifest.json"} and set(artifact) == expected_files,
                   "result file membership changed")
    inventory.pop("artifact-manifest.json")
    source.require(inventory == artifact, "result byte inventory changed")
    for name, expected in artifact.items():
        path = output.joinpath(*source.safe_member(name).parts)
        source.require(path.is_file() and source.digest(path) == expected["sha256"] and path.stat().st_size == expected["bytes"],
                       "result artifact changed: " + name)
    predictions = load_json(output / "predictions.json")
    source.require(source.digest(output / "predictions.json") == report["predictions_sha256"] and
                   source.digest(output / "scores.json") == report["scores_sha256"], "result report digest mismatch")
    source.require(metrics.evaluate(manifest, predictions) == load_json(output / "scores.json"), "canonical scores do not recompute")
    source.require(tuple(row["case_id"] for row in predictions["cases"]) == CASES, "actual fixed view set changed")
    for row in predictions["cases"]:
        actual = load_json(output / (row["case_id"] + ".json"))
        label = next(case for case in manifest["cases"] if case["case_id"] == row["case_id"])
        source.require(actual["status"] == "MODEL_EXECUTION_COMPLETE" and type(actual["exit_code"]) is int and actual["exit_code"] == 0
                       and actual["case_id"] == row["case_id"] and actual["pcm_sha256"] == row["pcm_sha256"] == label["pcm_sha256"],
                       "actual model case identity/status mismatch")
        source.require(row["asr"] == actual["asr"] and row["kws"] == actual["kws"], "predictions differ from model records")
        recovered = " ".join(item["result"]["text"] for item in actual["asr"]["raw_results"] if item["result"]["text"])
        source.require(recovered == row["asr"]["text"], "Vosk raw result transcript mismatch")
        source.require(actual["manifest_digest"] == metrics.manifest_digest(manifest) and actual["model_bindings"] == manifest["model_bindings"],
                       "actual model record source mismatch")
        source.require(actual["asr"]["consumed_samples"] == label["samples"]
                       and actual["asr"]["accept_waveform_calls"] == label["samples"] // HOP
                       and actual["kws"]["input_samples"] == label["samples"]
                       and actual["kws"]["explicit_flush_samples"] == FLUSH
                       and actual["kws"]["consumed_samples"] == label["samples"] + FLUSH,
                       "actual model feed/flush counts changed")
        for name in ("vosk/libvosk.so", "sherpa_onnx/lib/libonnxruntime.so"):
            observed = actual["loaded_native_files"]["runtime/" + name]
            source.require(observed["sha256"] == lock["runtime_files"][name]["sha256"]
                           and observed["bytes"] == lock["runtime_files"][name]["bytes"], "actual loaded native library mismatch")
    return {"status": "EVIDENCE_READBACK_COMPLETE", "cases": len(CASES), "original_utterances": 1,
            "source_revision": meta["source_revision"], "promotion_allowed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run", "infer-case", "verify"))
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--source-revision")
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--case-id")
    args = parser.parse_args()
    source_root, output = args.source_root.resolve(), args.output.resolve()
    if args.mode == "prepare":
        source.require(args.processor is not None and args.source_revision is not None, "processor/source required")
        result = prepare(source_root, args.processor.resolve(), output, args.source_revision)
    else:
        source.require(args.prepared is not None, "prepared inputs required")
        prepared = args.prepared.resolve()
        if args.mode == "run": result = run(source_root, prepared, output)
        elif args.mode == "infer-case": result = infer_case(source_root, prepared, args.case_id, output)
        else: result = verify(source_root, prepared, output)
    print(json.dumps({k: result[k] for k in ("status", "exit_code", "elapsed_seconds", "original_utterances") if k in result},
                     ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
