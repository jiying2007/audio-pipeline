#!/usr/bin/env python3
"""Validate audio-pipeline SKU certification evidence without third-party deps."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


PRODUCT_PERF_REQUIRED = {
    "active_cpu_percent", "p95_us", "p99_us", "deadline_misses", "rss_kib",
    "xruns", "overruns", "input_full_events", "output_drop_events",
}
PRODUCT_ACOUSTIC_REQUIRED = {
    "corpus_revision", "cases_total", "cases_passed", "far_end_erle_db",
    "aec_convergence_ms", "double_talk_near_si_sdr_db",
    "noise_si_sdr_improvement_db", "vad_f1", "threshold_report",
}


def require_keys(obj: dict, keys: set[str], where: str, errors: list[str]) -> None:
    missing = sorted(key for key in keys if key not in obj)
    if missing:
        errors.append(f"{where}: missing {', '.join(missing)}")


def validate(record: dict) -> list[str]:
    errors: list[str] = []
    require_keys(record,
                 {"sku", "status", "build", "platform", "audio_route",
                  "performance", "acoustic", "soak", "artifacts"},
                 "record", errors)
    if errors:
        return errors

    status = record["status"]
    if status not in {"pending", "board-validated", "product-certified", "failed"}:
        errors.append(f"status: unsupported value {status!r}")

    require_keys(record["build"],
                 {"commit", "version", "fingerprint", "compiler", "abi"},
                 "build", errors)
    require_keys(record["platform"],
                 {"soc", "kernel", "governor", "cpuset"},
                 "platform", errors)
    require_keys(record["audio_route"],
                 {"capture_device", "playback_device", "sample_rate_hz", "mic_channels"},
                 "audio_route", errors)
    require_keys(record["soak"], {"hours", "passed"}, "soak", errors)

    if record["audio_route"].get("sample_rate_hz") not in {8000, 16000, 24000, 32000, 48000}:
        errors.append("audio_route.sample_rate_hz: unsupported rate")
    if record["audio_route"].get("mic_channels") not in {1, 2}:
        errors.append("audio_route.mic_channels: must be 1 or 2")

    if status == "product-certified":
        perf = record["performance"]
        acoustic = record["acoustic"]
        soak = record["soak"]
        artifacts = record["artifacts"]
        require_keys(perf, PRODUCT_PERF_REQUIRED, "performance", errors)
        require_keys(acoustic, PRODUCT_ACOUSTIC_REQUIRED, "acoustic", errors)
        require_keys(soak,
                     {"hours", "passed", "xruns", "deadline_misses", "output_drop_events"},
                     "soak", errors)
        require_keys(artifacts,
                     {"result_json", "benchmark_json", "sha256"},
                     "artifacts", errors)

        if float(soak.get("hours", 0)) < 8.0:
            errors.append("soak.hours: product-certified requires >= 8 hours")
        if soak.get("passed") is not True:
            errors.append("soak.passed: product-certified requires true")
        for where, obj, keys in (
            ("performance", perf,
             {"deadline_misses", "xruns", "overruns", "input_full_events", "output_drop_events"}),
            ("soak", soak, {"xruns", "deadline_misses", "output_drop_events"}),
        ):
            for key in keys:
                if key in obj and int(obj[key]) != 0:
                    errors.append(f"{where}.{key}: product-certified nominal gate requires 0")
        if "p99_us" in perf and float(perf["p99_us"]) >= 10000.0:
            errors.append("performance.p99_us: must be < 10000 us")
        if "p95_us" in perf and float(perf["p95_us"]) >= 7000.0:
            errors.append("performance.p95_us: must be < 7000 us")
        if ("cases_total" in acoustic and "cases_passed" in acoustic and
                int(acoustic["cases_passed"]) != int(acoustic["cases_total"])):
            errors.append("acoustic: every certification corpus case must pass")
        if "vad_f1" in acoustic and not 0.0 <= float(acoustic["vad_f1"]) <= 1.0:
            errors.append("acoustic.vad_f1: must be within [0, 1]")
        sha256 = str(artifacts.get("sha256", ""))
        if sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}", sha256):
            errors.append("artifacts.sha256: must be exactly 64 hexadecimal characters")

    return errors


def self_test() -> None:
    base = {
        "sku": "test",
        "status": "product-certified",
        "build": {"commit": "abcdef0", "version": "2.0.0", "fingerprint": "x",
                  "compiler": "gcc", "abi": "armv7"},
        "platform": {"soc": "test", "kernel": "6.6", "governor": "performance",
                     "cpuset": "1"},
        "audio_route": {"capture_device": "hw:0,0", "playback_device": "hw:0,0",
                        "sample_rate_hz": 16000, "mic_channels": 2},
        "performance": {"active_cpu_percent": 20, "p95_us": 3000, "p99_us": 5000,
                        "deadline_misses": 0, "rss_kib": 512, "xruns": 0,
                        "overruns": 0, "input_full_events": 0, "output_drop_events": 0},
        "acoustic": {"corpus_revision": "r1", "cases_total": 10, "cases_passed": 10,
                     "far_end_erle_db": 20, "aec_convergence_ms": 500,
                     "double_talk_near_si_sdr_db": 8,
                     "noise_si_sdr_improvement_db": 4, "vad_f1": 0.9,
                     "threshold_report": "result.json"},
        "soak": {"hours": 8, "passed": True, "xruns": 0,
                 "deadline_misses": 0, "output_drop_events": 0},
        "artifacts": {"result_json": "result.json", "benchmark_json": "bench.json",
                      "sha256": "0" * 64},
    }
    assert validate(base) == []
    bad = json.loads(json.dumps(base))
    bad["soak"]["hours"] = 2
    bad["performance"]["p99_us"] = 12000
    assert len(validate(bad)) >= 2
    print("audio-pipeline certification validator self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("record", type=Path, nargs="?")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.record is None:
        parser.error("record is required unless --self-test is used")
    errors = validate(json.loads(args.record.read_text(encoding="utf-8")))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"certification record OK: {args.record}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
