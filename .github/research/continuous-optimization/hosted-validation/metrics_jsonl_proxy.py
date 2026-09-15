#!/usr/bin/env python3
"""Proxy one frozen processor while canonicalizing C non-finite JSON metrics.

Audio arguments and output are passed through unchanged. Only `--metrics-jsonl`
is redirected to a temporary file so the two diagnostic floating-point fields
written by examples/process_pcm.c (`vad_probability`, `erle_db`) can map C
`nan`/`inf` spellings to JSON `null`. Every resulting line is then parsed with
strict JSON semantics. Any other malformed token fails closed.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

_FIELDS = ("vad_probability", "erle_db")
_NONFINITE = re.compile(
    r'("(?:vad_probability|erle_db)"\s*:\s*)[+-]?(?:nan|inf(?:inity)?)(?=\s*[,}])',
    re.IGNORECASE,
)


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant remained after canonicalization: {value}")


def canonicalize_line(line: str) -> tuple[str, int]:
    replaced, count = _NONFINITE.subn(r"\1null", line)
    payload = json.loads(replaced, parse_constant=_reject_constant)
    if not isinstance(payload, dict):
        raise ValueError("metrics JSONL row must be an object")
    return replaced, count


def canonicalize_file(source: Path, output: Path, audit: Path | None = None) -> int:
    replacements = 0
    rows = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    with source.open("r", encoding="utf-8") as src, output.open("w", encoding="utf-8") as dst:
        for number, raw in enumerate(src, 1):
            if not raw.strip():
                continue
            try:
                line, count = canonicalize_line(raw.rstrip("\n"))
            except Exception as exc:
                raise ValueError(f"invalid metrics JSONL row {number}: {exc}") from exc
            dst.write(line + "\n")
            rows += 1
            replacements += count
    if audit is not None:
        audit.parent.mkdir(parents=True, exist_ok=True)
        with audit.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "schema_version": 1,
                "rows": rows,
                "canonicalized_nonfinite_values": replacements,
                "allowed_fields": list(_FIELDS),
                "audio_mutation": False,
            }, sort_keys=True) + "\n")
    return replacements


def proxy(processor: Path, args: list[str], audit: Path | None) -> int:
    try:
        index = args.index("--metrics-jsonl")
    except ValueError:
        return subprocess.run([str(processor), *args], check=False).returncode
    if index + 1 >= len(args):
        raise ValueError("--metrics-jsonl requires an output path")
    requested = Path(args[index + 1])
    with tempfile.TemporaryDirectory(prefix="ap-metrics-proxy-") as tmp:
        raw = Path(tmp) / "metrics.raw.jsonl"
        forwarded = list(args)
        forwarded[index + 1] = str(raw)
        rc = subprocess.run([str(processor), *forwarded], check=False).returncode
        if rc != 0:
            return rc
        if not raw.exists():
            raise ValueError("processor did not create requested metrics JSONL")
        canonicalize_file(raw, requested, audit)
    return 0


def self_test() -> None:
    samples = [
        ('{"frame":0,"vad_probability":nan,"erle_db":-inf,"vad_active":1}', 2),
        ('{"frame":1,"vad_probability":0.5,"erle_db":12.0,"vad_active":0}', 0),
    ]
    for raw, expected in samples:
        fixed, count = canonicalize_line(raw)
        assert count == expected
        payload = json.loads(fixed, parse_constant=_reject_constant)
        if expected:
            assert payload["vad_probability"] is None and payload["erle_db"] is None
    for invalid in ('{"frame":0,"other":NaN}', '{"frame":0,"other":nan}'):
        try:
            canonicalize_line(invalid)
        except Exception:
            pass
        else:
            raise AssertionError("unknown non-finite field did not fail closed")
    print("metrics JSONL proxy self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--processor", type=Path)
    parser.add_argument("--audit", type=Path)
    parser.add_argument("args", nargs=argparse.REMAINDER)
    ns = parser.parse_args()
    if ns.self_test:
        self_test()
        return 0
    if ns.processor is None:
        parser.error("--processor is required")
    forwarded = ns.args[1:] if ns.args and ns.args[0] == "--" else ns.args
    return proxy(ns.processor.resolve(), forwarded, ns.audit)


if __name__ == "__main__":
    raise SystemExit(main())
