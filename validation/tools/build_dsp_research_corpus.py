#!/usr/bin/env python3
"""Build a non-shipping DSP research corpus from a sealed research manifest."""
from __future__ import annotations

import argparse
import array
import hashlib
import json
import os
import subprocess
from pathlib import Path

RATE = 16000
MAX_SECONDS = 8
SAFETY = {
    "max_output_clip_fraction": 0.02,
    "max_output_dc_offset_dbfs": -20.0,
    "min_output_rms_delta_db": -35.0,
    "max_output_rms_delta_db": 15.0,
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def decode(path: Path, channels: int) -> list[int]:
    raw = subprocess.check_output([
        "ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
        "-ac", str(channels), "-ar", str(RATE), "-f", "s16le", "-acodec", "pcm_s16le", "pipe:1",
    ])
    values = array.array("h"); values.frombytes(raw)
    if os.sys.byteorder != "little": values.byteswap()
    return list(values[:RATE * MAX_SECONDS * channels])


def write_pcm(path: Path, samples: list[int]) -> None:
    values = array.array("h", samples)
    if os.sys.byteorder != "little": values.byteswap()
    path.write_bytes(values.tobytes())


def verify_record(root: Path, record: dict) -> Path:
    path = root / record["relative_path"]
    if not path.is_file(): raise FileNotFoundError(path)
    if path.stat().st_size != int(record["size"]): raise ValueError(f"size mismatch: {path}")
    if sha256(path) != record["sha256"]: raise ValueError(f"SHA mismatch: {path}")
    return path


def build(manifest_path: Path, catalog_path: Path, data_root: Path, output: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    if manifest.get("profile") != "dsp-research" or manifest.get("authority") != "research-validation-only":
        raise ValueError("research manifest authority mismatch")
    by_id = {item["id"]: item for item in catalog["datasets"]}
    output.mkdir(parents=True, exist_ok=True); (output / "cases").mkdir(exist_ok=True)
    cases = []
    for dataset in manifest["datasets"]:
        dataset_id = dataset["id"]
        if dataset_id not in {"locata", "mimii", "mimii-due"}: raise ValueError("unexpected research dataset")
        if dataset["usage_class"] not in {"conditional", "research-only"}: raise ValueError("commercial source entered research-only builder")
        root = data_root / by_id[dataset_id]["local_path"]
        for index, entry in enumerate(dataset["entries"]):
            source = verify_record(root, entry["files"][0])
            is_locata = dataset_id == "locata"
            channels = 2 if is_locata else 1
            samples = decode(source, channels)
            if len(samples) < RATE * channels: continue
            cid = f"{dataset_id}-{index:03d}"
            case_dir = output / "cases" / cid; case_dir.mkdir(exist_ok=True)
            mic = case_dir / "mic.pcm"; write_pcm(mic, samples)
            expected = dict(SAFETY)
            labels = None
            profile = "default" if is_locata else "ns-isolated"
            scenario = "locata-bf-motion" if is_locata else "mechanical-hard-negative"
            if not is_locata:
                frame_count = max(1, (len(samples) + RATE // 100 - 1) // (RATE // 100))
                label_path = case_dir / "vad.labels"
                label_path.write_text("0\n" * frame_count, encoding="utf-8")
                labels = str(label_path.relative_to(output))
                expected.update({"max_vad_false_positive_rate": 0.50, "min_noise_only_attenuation_db": -1.0})
            cases.append({
                "case_id": cid,
                "split": "development",
                "scenario": scenario,
                "sample_rate_hz": RATE,
                "mic_channels": channels,
                "mic_audio": str(mic.relative_to(output)),
                "render_audio": None,
                "clean_near_audio": None,
                "echo_audio": None,
                "vad_labels": labels,
                "processor_profile": profile,
                "control": {},
                "expected": expected,
                "dimensions": dict(entry.get("dimensions", {})),
                "source": {
                    "dataset_id": dataset_id,
                    "source_id": entry["source_id"],
                    "usage_class": dataset["usage_class"],
                    "license": dataset["license"],
                    "source_sha256": entry["files"][0]["sha256"],
                },
            })
    if not cases: raise ValueError("research corpus has no cases")
    corpus = {
        "schema_version": 1,
        "corpus_id": "dsp-research-public-v1",
        "tier": "research-validation",
        "generator": {"name": "build_dsp_research_corpus.py", "version": 1},
        "sources": sorted({case["source"]["dataset_id"] for case in cases}),
        "sealed_data": True,
        "research_only": True,
        "source_manifest_sha256": sha256(manifest_path),
        "cases": cases,
    }
    corpus_path = output / "corpus.json"
    corpus_path.write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"corpus": str(corpus_path), "cases": len(cases), "sources": corpus["sources"]}


def self_test() -> None:
    assert SAFETY["max_output_clip_fraction"] == 0.02
    assert "min_near_si_sdr_improvement_db" not in SAFETY
    print("DSP research corpus builder self-test: OK")


def main() -> int:
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test")
    b = sub.add_parser("build")
    b.add_argument("--manifest", type=Path, required=True); b.add_argument("--catalog", type=Path, default=Path("validation/extended.datasets.lock.json"))
    b.add_argument("--data-root", type=Path, required=True); b.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.command == "self-test": self_test(); return 0
    print(json.dumps(build(args.manifest, args.catalog, args.data_root, args.output), sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
