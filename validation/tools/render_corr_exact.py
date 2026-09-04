#!/usr/bin/env python3
"""Exact all-integer-lag render correlation for canonical validation.

The C11 helper evaluates every integer lag in the existing +/-100 ms search
window and only selects the winning lag. The final metric value is always
recomputed by run_validation_engine.normalized_corr(..., stride=4), so this
module cannot redefine the metric or any acoustic acceptance threshold.

The helper is compiled into a process-local temporary directory. It is not a
CMake target, is not installed, and is never linked into the product runtime.
Missing or failed host compilation aborts validation rather than falling back to
the historical sparse lag grid.
"""

from __future__ import annotations

import array
import ctypes
import hashlib
import json
import math
import os
import random
import shlex
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Callable, Sequence

SEARCH_ID = "exact-all-integer-lags-stride4-v1"
SOURCE_PATH = Path(__file__).with_name("render_corr_exact.c")
LOADER_PATH = Path(__file__)
_NATIVE_LOCK = threading.Lock()
_NATIVE_STATE: dict | None = None
_NATIVE_TEMP: tempfile.TemporaryDirectory[str] | None = None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _compiler_command() -> list[str]:
    command = shlex.split(os.environ.get("CC", "cc"))
    if not command:
        raise RuntimeError("CC resolved to an empty compiler command")
    return command


def _compiler_identity(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command + ["--version"], check=False, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
    except OSError as exc:
        raise RuntimeError(f"cannot execute validation C compiler {command[0]!r}: {exc}") from exc
    first = completed.stdout.splitlines()[0].strip() if completed.stdout else "unknown"
    return first or "unknown"


def _load_native() -> dict:
    global _NATIVE_STATE, _NATIVE_TEMP
    if _NATIVE_STATE is not None:
        return _NATIVE_STATE
    with _NATIVE_LOCK:
        if _NATIVE_STATE is not None:
            return _NATIVE_STATE
        if not SOURCE_PATH.is_file():
            raise RuntimeError(f"render-correlation helper source is missing: {SOURCE_PATH}")
        if os.name == "nt":
            raise RuntimeError(
                "canonical validation exact render correlation requires a POSIX C11 host compiler"
            )

        compiler = _compiler_command()
        temporary = tempfile.TemporaryDirectory(prefix="ap-validation-corr-")
        suffix = ".dylib" if sys.platform == "darwin" else ".so"
        library_path = Path(temporary.name) / f"librender_corr_exact{suffix}"
        command = compiler + [
            "-O3", "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-fno-fast-math", "-ffp-contract=off", "-fPIC",
        ]
        command += ["-dynamiclib" if sys.platform == "darwin" else "-shared"]
        command += [str(SOURCE_PATH), "-lm", "-o", str(library_path)]
        try:
            completed = subprocess.run(
                command, check=False, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except OSError as exc:
            temporary.cleanup()
            raise RuntimeError(
                f"cannot execute validation C compiler {compiler[0]!r}: {exc}"
            ) from exc
        if completed.returncode != 0:
            temporary.cleanup()
            detail = (completed.stderr or completed.stdout or "compiler failed").strip()
            raise RuntimeError(
                "failed to build exact render-correlation validation helper: " + detail[-4000:]
            )

        library = ctypes.CDLL(str(library_path))
        function = library.ap_validation_max_abs_corr
        function.restype = ctypes.c_double
        function.argtypes = [
            ctypes.POINTER(ctypes.c_int16), ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_int16), ctypes.c_size_t,
            ctypes.c_int, ctypes.POINTER(ctypes.c_int),
        ]
        _NATIVE_TEMP = temporary
        _NATIVE_STATE = {
            "library": library,
            "function": function,
            "library_path": library_path,
            "binary_sha256": _sha256_file(library_path),
            "compiler": _compiler_identity(compiler),
        }
        return _NATIVE_STATE


def find_best_lag(a: Sequence[int], b: Sequence[int], sample_rate: int) -> tuple[int, float]:
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if not a or not b:
        return 0, 0.0
    native = _load_native()
    aa = array.array("h", (int(value) for value in a))
    bb = array.array("h", (int(value) for value in b))
    if aa.itemsize != 2 or bb.itemsize != 2:
        raise RuntimeError("host array('h') is not 16-bit")
    a_buffer = (ctypes.c_int16 * len(aa)).from_buffer(aa)
    b_buffer = (ctypes.c_int16 * len(bb)).from_buffer(bb)
    best_lag = ctypes.c_int(0)
    score = native["function"](
        a_buffer, len(aa), b_buffer, len(bb), int(sample_rate), ctypes.byref(best_lag)
    )
    if not math.isfinite(score) or score < 0.0 or score > 1.0000000001:
        raise RuntimeError(f"invalid native render-correlation score: {score}")
    return int(best_lag.value), float(score)


def exact_score(normalized_corr: Callable[..., float], a: Sequence[int], b: Sequence[int],
                sample_rate: int) -> float:
    if not a or not b:
        return 0.0
    lag, native_score = find_best_lag(a, b, sample_rate)
    canonical_score = float(normalized_corr(a, b, lag, stride=4))
    if abs(native_score - canonical_score) > 1.0e-10:
        raise RuntimeError(
            f"native/canonical render-correlation drift at lag {lag}: "
            f"{native_score} != {canonical_score}"
        )
    return canonical_score


def install(engine) -> None:
    """Install exact max-correlation search into the canonical engine module."""
    def max_abs_corr(a: Sequence[int], b: Sequence[int], sample_rate: int) -> float:
        return exact_score(engine.normalized_corr, a, b, sample_rate)

    max_abs_corr.__name__ = "max_abs_corr"
    max_abs_corr.__doc__ = (
        "Return canonical stride-4 max absolute correlation over every integer "
        "lag in the existing +/-100 ms window."
    )
    engine.max_abs_corr = max_abs_corr


def report_bindings(engine_path: Path) -> dict[str, str]:
    native = _load_native()
    return {
        "validation_evaluator_sha256": _sha256_file(engine_path),
        "render_corr_search": SEARCH_ID,
        "render_corr_loader_sha256": _sha256_file(LOADER_PATH),
        "render_corr_helper_source_sha256": _sha256_file(SOURCE_PATH),
        "render_corr_helper_binary_sha256": str(native["binary_sha256"]),
        "render_corr_compiler": str(native["compiler"]),
    }


def extend_evidence_manifest(path: Path, engine_path: Path) -> None:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    artifacts = manifest.setdefault("artifacts", [])
    existing = {(item.get("type"), item.get("path")) for item in artifacts}
    for artifact_type, artifact in (
        ("validation-evaluator-engine", engine_path),
        ("render-correlation-loader", LOADER_PATH),
        ("render-correlation-helper-source", SOURCE_PATH),
    ):
        key = (artifact_type, str(artifact))
        if key in existing:
            continue
        artifacts.append({
            "type": artifact_type,
            "path": str(artifact),
            "size": artifact.stat().st_size,
            "sha256": _sha256_file(artifact),
        })
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _brute_max(normalized_corr: Callable[..., float], a: list[int], b: list[int],
               sample_rate: int) -> float:
    max_lag = max(1, sample_rate // 10)
    return max(
        float(normalized_corr(a, b, lag, stride=4))
        for lag in range(-max_lag, max_lag + 1)
    )


def _legacy_sparse_max(normalized_corr: Callable[..., float], a: list[int], b: list[int],
                       sample_rate: int) -> float:
    max_lag = max(1, sample_rate // 10)
    step = max(1, max_lag // 60)
    lags = list(range(-max_lag, max_lag + 1, step))
    if 0 not in lags:
        lags.append(0)
    return max(float(normalized_corr(a, b, lag, stride=4)) for lag in lags)


def self_test(normalized_corr: Callable[..., float]) -> None:
    rng = random.Random(20260904)
    rate = 16000
    source = [rng.randint(-12000, 12000) for _ in range(8000)]
    colored: list[int] = []
    state = 0.0
    for sample in source:
        state = 0.82 * state + 0.18 * float(sample)
        colored.append(int(state))

    for signal, delay in (
        (source, 7), (source, 17), (source, 250),
        (source, 672), (colored, 829), (colored, 1316),
    ):
        shifted = [0] * delay + signal[:-delay]
        forward = exact_score(normalized_corr, shifted, signal, rate)
        reverse = exact_score(normalized_corr, signal, shifted, rate)
        assert forward > 0.999999999, (delay, forward)
        assert reverse > 0.999999999, (delay, reverse)

    shifted17 = [0] * 17 + source[:-17]
    sparse17 = _legacy_sparse_max(normalized_corr, shifted17, source, rate)
    exact17 = exact_score(normalized_corr, shifted17, source, rate)
    assert sparse17 < 0.50, sparse17
    assert exact17 > 0.999999999, exact17

    small_rate = 1000
    for index in range(5):
        a = [rng.randint(-16000, 16000) for _ in range(360 + index * 23)]
        b = [rng.randint(-16000, 16000) for _ in range(390 + index * 19)]
        brute = _brute_max(normalized_corr, a, b, small_rate)
        exact = exact_score(normalized_corr, a, b, small_rate)
        assert abs(exact - brute) <= 1.0e-12, (index, exact, brute)

    bindings = report_bindings(Path(__file__).with_name("run_validation_engine.py"))
    assert bindings["render_corr_search"] == SEARCH_ID
    assert len(bindings["render_corr_helper_source_sha256"]) == 64
    assert len(bindings["render_corr_helper_binary_sha256"]) == 64
    print("exact render-correlation validation self-test: OK")
