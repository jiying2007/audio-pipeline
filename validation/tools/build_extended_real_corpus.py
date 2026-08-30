#!/usr/bin/env python3
"""Build extended-real validation cases from a verified normalized source manifest."""

from __future__ import annotations

import argparse
import array
import json
import math
import os
import subprocess
from pathlib import Path

from build_public_corpus import clamp16, convolve_short, frame_labels, interleave, write_pcm
from extended_dataset_lock import catalog_items, load_json, sha256_file, validate_catalog, validate_manifest
from prepare_extended_validation import verify_manifest_files

RATE = 16000
MAX_SECONDS = 8
SAFETY_EXPECTED = {
    "max_output_clip_fraction": 0.02,
    "max_output_dc_offset_dbfs": -28.0,
    "min_output_rms_delta_db": -35.0,
    "max_output_rms_delta_db": 15.0,
}


def decode_audio(path: Path, channels: int = 1, max_seconds: int = MAX_SECONDS) -> list[int]:
    command = [
        "ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
        "-ac", str(channels), "-ar", str(RATE), "-f", "s16le", "-acodec", "pcm_s16le", "pipe:1",
    ]
    raw = subprocess.check_output(command)
    values = array.array("h")
    values.frombytes(raw)
    if os.sys.byteorder != "little":
        values.byteswap()
    limit = RATE * max_seconds * channels
    return list(values[:limit])


def root_for(catalog: dict, data_root: Path, dataset_id: str) -> Path:
    return data_root / catalog_items(catalog)[dataset_id]["local_path"]


def file_by_role(entry: dict, role: str) -> dict | None:
    return next((item for item in entry["files"] if item.get("role") == role), None)


def source_path(root: Path, file_entry: dict) -> Path:
    return root / file_entry["relative_path"]


def trim_pair(a: list[int], b: list[int], minimum_seconds: int = 2) -> tuple[list[int], list[int]]:
    count = min(len(a), len(b))
    if count < RATE * minimum_seconds:
        raise ValueError("extended validation source is shorter than minimum duration")
    count = min(count, RATE * MAX_SECONDS)
    return a[:count], b[:count]


def mix_noise(clean: list[int], noise: list[int], gain_index: int) -> tuple[list[int], float]:
    if not clean or not noise:
        raise ValueError("cannot mix empty clean/noise")
    repeated = [noise[i % len(noise)] for i in range(len(clean))]
    peak_clean = max(1, max(abs(value) for value in clean))
    peak_noise = max(1, max(abs(value) for value in repeated))
    linear = [0.10, 0.18, 0.28, 0.42, 0.65][gain_index % 5] * peak_clean / peak_noise
    return [clamp16(clean[i] + linear * repeated[i]) for i in range(len(clean))], linear


def case_dir(output: Path, case_id: str) -> Path:
    path = output / "cases" / case_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def source_provenance(dataset: dict, entry: dict) -> dict:
    return {
        "dataset_id": dataset["id"],
        "source_id": entry["source_id"],
        "usage_class": dataset["usage_class"],
        "license": dataset["license"],
        "files": [
            {
                "role": item.get("role"),
                "relative_path": item["relative_path"],
                "sha256": item["sha256"],
            }
            for item in entry["files"]
        ],
    }


def add_realman_cases(output: Path, catalog: dict, data_root: Path, dataset: dict,
                      limit: int, cases: list[dict]) -> None:
    root = root_for(catalog, data_root, dataset["id"])
    entries = [item for item in dataset["entries"] if item["kind"] == "enhancement-pair"][:limit]
    for index, entry in enumerate(entries):
        mic0 = file_by_role(entry, "mic0")
        clean_file = file_by_role(entry, "clean")
        if mic0 is None or clean_file is None:
            continue
        left = decode_audio(source_path(root, mic0), 1)
        clean = decode_audio(source_path(root, clean_file), 1)
        left, clean = trim_pair(left, clean)
        mic1 = file_by_role(entry, "mic1")
        channels = 1
        mic_samples = left
        if mic1 is not None:
            right = decode_audio(source_path(root, mic1), 1)
            count = min(len(left), len(right), len(clean))
            if count >= RATE * 2:
                left = left[:count]
                right = right[:count]
                clean = clean[:count]
                mic_samples = interleave(left, right)
                channels = 2
        labels = frame_labels(clean, RATE)
        cid = f"realman-{index:03d}"
        directory = case_dir(output, cid)
        write_pcm(directory / "mic.pcm", mic_samples)
        write_pcm(directory / "clean.pcm", clean)
        (directory / "vad.labels").write_text("".join(f"{value}\n" for value in labels), encoding="utf-8")
        expected = dict(SAFETY_EXPECTED)
        expected["min_near_si_sdr_improvement_db"] = -1.5
        cases.append({
            "case_id": cid,
            "split": "validation",
            "scenario": "realman-farfield",
            "sample_rate_hz": RATE,
            "mic_channels": channels,
            "mic_audio": str((directory / "mic.pcm").relative_to(output)),
            "render_audio": None,
            "clean_near_audio": str((directory / "clean.pcm").relative_to(output)),
            "echo_audio": None,
            "vad_labels": str((directory / "vad.labels").relative_to(output)),
            "processor_profile": "default",
            "control": {},
            "expected": expected,
            "dimensions": dict(entry.get("dimensions", {})),
            "source": source_provenance(dataset, entry),
        })


def decode_entry(root: Path, entry: dict) -> list[int]:
    return decode_audio(source_path(root, entry["files"][0]), 1)


def add_measured_room_cases(output: Path, catalog: dict, data_root: Path,
                            datasets: dict[str, dict], limit: int, cases: list[dict]) -> None:
    but = datasets["but-reverbdb"]
    clean_ds = datasets["openslr-slr31"]
    musan = datasets["musan"]
    but_root = root_for(catalog, data_root, "but-reverbdb")
    clean_root = root_for(catalog, data_root, "openslr-slr31")
    musan_root = root_for(catalog, data_root, "musan")
    rirs = [e for e in but["entries"] if e["kind"] == "rir"]
    room_noises = [e for e in but["entries"] if e["kind"] == "noise"]
    cleans = [e for e in clean_ds["entries"] if e["kind"] == "clean"]
    musan_noises = [e for e in musan["entries"] if e["kind"] in {"noise", "music"}]
    noises = room_noises + musan_noises
    if min(len(rirs), len(cleans), len(noises)) < 2:
        raise ValueError("measured-room extended validation needs >=2 RIRs, clean files and noises")
    decoded_rirs = [decode_entry(but_root, entry) for entry in rirs[:min(len(rirs), max(4, limit))]]
    for index in range(limit):
        clean_entry = cleans[index % len(cleans)]
        clean = decode_entry(clean_root, clean_entry)
        if len(clean) < RATE * 2:
            continue
        clean = clean[:RATE * MAX_SECONDS]
        rir_entry = rirs[index % len(decoded_rirs)]
        rir = decoded_rirs[index % len(decoded_rirs)]
        target = convolve_short(clean, rir)
        noise_entry = noises[(index * 7 + 3) % len(noises)]
        noise_root = but_root if noise_entry in room_noises else musan_root
        noise = decode_entry(noise_root, noise_entry)
        noisy, mix_gain = mix_noise(target, noise, index)
        labels = frame_labels(target, RATE)
        provenance = {
            "dataset_id": "openslr-slr31+but-reverbdb+musan",
            "source_id": f"measured-room-{index:03d}",
            "usage_class": "commercial-validation",
            "license": "CC-BY-4.0",
            "clean": source_provenance(clean_ds, clean_entry),
            "rir": source_provenance(but, rir_entry),
            "noise": source_provenance(but if noise_entry in room_noises else musan, noise_entry),
            "mix_noise_gain": mix_gain,
        }
        ns_id = f"measured-rir-ns-{index:03d}"
        ns_dir = case_dir(output, ns_id)
        write_pcm(ns_dir / "mic.pcm", noisy)
        write_pcm(ns_dir / "clean.pcm", target)
        (ns_dir / "vad.labels").write_text("".join(f"{value}\n" for value in labels), encoding="utf-8")
        ns_expected = dict(SAFETY_EXPECTED)
        ns_expected.update({
            "min_near_si_sdr_improvement_db": -0.5,
            "max_speech_active_attenuation_db": 12.0,
        })
        cases.append({
            "case_id": ns_id, "split": "validation", "scenario": "measured-rir-ns",
            "sample_rate_hz": RATE, "mic_channels": 1,
            "mic_audio": str((ns_dir / "mic.pcm").relative_to(output)),
            "render_audio": None,
            "clean_near_audio": str((ns_dir / "clean.pcm").relative_to(output)),
            "echo_audio": None,
            "vad_labels": str((ns_dir / "vad.labels").relative_to(output)),
            "processor_profile": "ns-isolated", "control": {}, "expected": ns_expected,
            "dimensions": {"rir_index": index % len(decoded_rirs), "noise_family": noise_entry["kind"]},
            "source": provenance,
        })

        second_rir = decoded_rirs[(index + 1) % len(decoded_rirs)]
        right_target = convolve_short(clean, second_rir)
        right_noise, _ = mix_noise(right_target, noise, index + 2)
        count = min(len(noisy), len(right_noise), len(target))
        bf_id = f"measured-rir-bf-{index:03d}"
        bf_dir = case_dir(output, bf_id)
        write_pcm(bf_dir / "mic.pcm", interleave(noisy[:count], right_noise[:count]))
        write_pcm(bf_dir / "clean.pcm", target[:count])
        bf_labels = frame_labels(target[:count], RATE)
        (bf_dir / "vad.labels").write_text("".join(f"{value}\n" for value in bf_labels), encoding="utf-8")
        bf_expected = dict(SAFETY_EXPECTED)
        bf_expected.update({
            "min_near_si_sdr_improvement_db": -1.0,
            "max_speech_active_attenuation_db": 14.0,
        })
        cases.append({
            "case_id": bf_id, "split": "validation", "scenario": "measured-rir-bf",
            "sample_rate_hz": RATE, "mic_channels": 2,
            "mic_audio": str((bf_dir / "mic.pcm").relative_to(output)),
            "render_audio": None,
            "clean_near_audio": str((bf_dir / "clean.pcm").relative_to(output)),
            "echo_audio": None,
            "vad_labels": str((bf_dir / "vad.labels").relative_to(output)),
            "processor_profile": "default", "control": {}, "expected": bf_expected,
            "dimensions": {"rir_pair": f"{index % len(decoded_rirs)}:{(index + 1) % len(decoded_rirs)}"},
            "source": provenance,
        })


def add_negative_cases(output: Path, catalog: dict, data_root: Path, dataset: dict,
                       limit: int, scenario_prefix: str, cases: list[dict]) -> None:
    root = root_for(catalog, data_root, dataset["id"])
    entries = [e for e in dataset["entries"] if e["kind"] in {"noise", "music", "negative"}][:limit]
    for index, entry in enumerate(entries):
        samples = decode_entry(root, entry)
        if len(samples) < RATE:
            continue
        samples = samples[:RATE * MAX_SECONDS]
        labels = [0] * max(1, math.ceil(len(samples) / (RATE // 100)))
        cid = f"{scenario_prefix}-{index:03d}"
        directory = case_dir(output, cid)
        write_pcm(directory / "mic.pcm", samples)
        (directory / "vad.labels").write_text("".join("0\n" for _ in labels), encoding="utf-8")
        expected = dict(SAFETY_EXPECTED)
        expected["max_vad_false_positive_rate"] = 0.35 if dataset["usage_class"] == "commercial-validation" else 0.50
        expected["min_noise_only_attenuation_db"] = -1.0
        cases.append({
            "case_id": cid, "split": "validation", "scenario": scenario_prefix,
            "sample_rate_hz": RATE, "mic_channels": 1,
            "mic_audio": str((directory / "mic.pcm").relative_to(output)),
            "render_audio": None, "clean_near_audio": None, "echo_audio": None,
            "vad_labels": str((directory / "vad.labels").relative_to(output)),
            "processor_profile": "ns-isolated", "control": {}, "expected": expected,
            "dimensions": dict(entry.get("dimensions", {})),
            "source": source_provenance(dataset, entry),
        })


def add_stress_cases(output: Path, catalog: dict, data_root: Path, dataset: dict,
                     limit: int, scenario: str, cases: list[dict]) -> None:
    root = root_for(catalog, data_root, dataset["id"])
    entries = [e for e in dataset["entries"] if e["kind"] in {"farfield", "meeting"}][:limit]
    for index, entry in enumerate(entries):
        samples = decode_entry(root, entry)
        if len(samples) < RATE:
            continue
        samples = samples[:RATE * MAX_SECONDS]
        cid = f"{scenario}-{index:03d}"
        directory = case_dir(output, cid)
        write_pcm(directory / "mic.pcm", samples)
        cases.append({
            "case_id": cid, "split": "validation", "scenario": scenario,
            "sample_rate_hz": RATE, "mic_channels": 1,
            "mic_audio": str((directory / "mic.pcm").relative_to(output)),
            "render_audio": None, "clean_near_audio": None, "echo_audio": None,
            "vad_labels": None, "processor_profile": "default", "control": {},
            "expected": dict(SAFETY_EXPECTED),
            "dimensions": dict(entry.get("dimensions", {})),
            "source": source_provenance(dataset, entry),
        })


def write_attribution(output: Path, catalog: dict, used_sources: list[str]) -> None:
    by_id = catalog_items(catalog)
    lines = ["# Extended-real dataset attribution", ""]
    for dataset_id in used_sources:
        item = by_id[dataset_id]
        lines.extend([
            f"## {dataset_id}",
            "",
            f"- License: `{item['license']}`",
            f"- Usage class: `{item['usage_class']}`",
            f"- Source: {item['source']}",
            f"- Attribution: {item['attribution']}",
            "",
        ])
    (output / "DATASET_ATTRIBUTION.md").write_text("\n".join(lines), encoding="utf-8")


def self_test() -> None:
    clean = [1000, -1000] * 16000
    noise = [200, -300, 400, -500]
    mixed, gain = mix_noise(clean, noise, 0)
    assert len(mixed) == len(clean)
    assert gain > 0
    assert SAFETY_EXPECTED["max_output_clip_fraction"] < 0.1
    print("extended-real corpus builder self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--catalog", type=Path, default=Path("validation/extended.datasets.lock.json"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--direct-limit", type=int, default=24)
    parser.add_argument("--derived-limit", type=int, default=16)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.manifest is None or args.data_root is None or args.output is None:
        parser.error("--manifest, --data-root and --output are required unless --self-test is used")
    if args.direct_limit < 2 or args.derived_limit < 2:
        parser.error("direct-limit and derived-limit must be >=2")
    catalog = load_json(args.catalog)
    validate_catalog(catalog)
    manifest = load_json(args.manifest)
    validate_manifest(manifest, catalog, args.catalog)
    verify_manifest_files(manifest, catalog, args.data_root)
    datasets = {item["id"]: item for item in manifest["datasets"]}
    args.output.mkdir(parents=True, exist_ok=True)
    cases: list[dict] = []
    add_realman_cases(args.output, catalog, args.data_root, datasets["realman"], args.direct_limit, cases)
    add_measured_room_cases(args.output, catalog, args.data_root, datasets, args.derived_limit, cases)
    add_negative_cases(args.output, catalog, args.data_root, datasets["musan"],
                       max(4, args.direct_limit // 2), "musan-negative", cases)
    if "voices" in datasets:
        add_stress_cases(args.output, catalog, args.data_root, datasets["voices"],
                         args.direct_limit, "voices-farfield-stress", cases)
        add_negative_cases(args.output, catalog, args.data_root, datasets["voices"],
                           max(2, args.direct_limit // 4), "voices-distractor-negative", cases)
    if "ami" in datasets:
        add_stress_cases(args.output, catalog, args.data_root, datasets["ami"],
                         args.direct_limit, "ami-meeting-stress", cases)
    if "icsi" in datasets:
        add_stress_cases(args.output, catalog, args.data_root, datasets["icsi"],
                         args.direct_limit, "icsi-meeting-stress", cases)
    if "aishell4" in datasets:
        add_stress_cases(args.output, catalog, args.data_root, datasets["aishell4"],
                         args.direct_limit, "aishell4-meeting-research", cases)
    if "fsd50k" in datasets:
        add_negative_cases(args.output, catalog, args.data_root, datasets["fsd50k"],
                           args.direct_limit, "fsd50k-permissive-negative-research", cases)
    if "wham" in datasets:
        add_negative_cases(args.output, catalog, args.data_root, datasets["wham"],
                           args.direct_limit, "wham-negative-research", cases)
    if len(cases) < 16:
        raise ValueError(f"extended-real corpus is unexpectedly small: {len(cases)}")
    used_sources = [item["id"] for item in manifest["datasets"]]
    tier = "research-validation" if manifest["profile"] == "research" else "validation-grade"
    corpus = {
        "schema_version": 1,
        "corpus_id": f"extended-real-{manifest['profile']}-v1",
        "tier": tier,
        "generator": {"name": "build_extended_real_corpus.py", "version": 1},
        "sources": used_sources,
        "sealed_data": True,
        "dataset_lock_sha256": sha256_file(args.catalog),
        "source_manifest_sha256": sha256_file(args.manifest),
        "license_profile": manifest["profile"],
        "cases": cases,
    }
    corpus_path = args.output / "corpus.json"
    corpus_path.write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_attribution(args.output, catalog, used_sources)
    scenarios: dict[str, int] = {}
    for case in cases:
        scenarios[case["scenario"]] = scenarios.get(case["scenario"], 0) + 1
    print(json.dumps({
        "corpus": str(corpus_path),
        "cases": len(cases),
        "profile": manifest["profile"],
        "scenarios": scenarios,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
