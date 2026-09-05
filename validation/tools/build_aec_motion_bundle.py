#!/usr/bin/env python3
"""Build deterministic multi-seed bundles from the canonical AEC motion model.

Bundles preserve generator semantics and remain regression/development assets.
The role is orchestration metadata, not independent-confirmation authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import tempfile
from pathlib import Path

import build_aec_motion_corpus as motion


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prefix_path(seed: int, raw: str | None) -> str | None:
    return None if raw is None else f"seed-{seed}/{raw}"


def build(output: Path, seeds: list[int], seconds: float, role: str) -> dict:
    require(role in {"development", "validation", "shadow"}, "role")
    require(len(seeds) >= 2 and len(set(seeds)) == len(seeds), "distinct seeds")
    require(all(type(seed) is int and 0 <= seed < 2 ** 32 for seed in seeds), "seed range")
    require(isinstance(seconds, (int, float)) and math.isfinite(seconds) and 4.0 <= seconds <= 60.0,
            "seconds")
    require(not output.is_symlink() and (not output.exists() or (output.is_dir() and not any(output.iterdir()))),
            "output must be absent or empty")
    output.mkdir(parents=True, exist_ok=True)
    cases: list[dict] = []
    source_files: dict[str, str] = {}

    for seed in seeds:
        seed_root = output / f"seed-{seed}"
        corpus = motion.build(seed_root, seed, seconds)
        for case in corpus["cases"]:
            copied = json.loads(json.dumps(case))
            original_id = str(copied["case_id"])
            copied["case_id"] = f"seed-{seed}-{original_id}"
            for key in ("mic_audio", "render_audio", "clean_near_audio", "echo_audio", "vad_labels"):
                copied[key] = prefix_path(seed, copied.get(key))
            copied["source"]["ground_truth"] = prefix_path(seed, copied["source"]["ground_truth"])
            copied["source"]["source_id"] = copied["case_id"]
            copied["source"]["bundle_seed"] = seed
            copied["source"]["bundle_role"] = role
            cases.append(copied)
        for path in sorted(item for item in seed_root.rglob("*") if item.is_file()):
            source_files[str(path.relative_to(output))] = sha256_file(path)

    corpus = {
        "schema_version": 1,
        "corpus_id": f"aec-motion-geometry-bundle-v{motion.GENERATOR_VERSION}-{role}-" +
                     "-".join(str(seed) for seed in seeds),
        "tier": "regression",
        "generator": {
            "name": Path(__file__).name,
            "version": 2,
            "canonical_generator": "build_aec_motion_corpus.py",
            "canonical_generator_version": motion.GENERATOR_VERSION,
            "canonical_model_sha256": motion.json_sha256(motion.MODEL),
            "seeds": seeds,
            "seconds": math.ceil(seconds * 100.0) / 100.0,
            "role": role,
            "continuous_motion": True,
            "explicit_path_change_notifications": False,
        },
        "sources": [motion.DATASET_ID],
        "sealed_data": False,
        "cases": cases,
    }
    corpus_path = output / "corpus.json"
    motion.write_json(corpus_path, corpus)
    manifest = {
        "schema_version": 1,
        "authority": "development-only-non-shipping",
        "role": role,
        "seeds": seeds,
        "cases": len(cases),
        "dataset_id": motion.DATASET_ID,
        "canonical_generator_sha256": sha256_file(Path(motion.__file__)),
        "canonical_model_sha256": motion.json_sha256(motion.MODEL),
        "corpus_sha256": sha256_file(corpus_path),
        "files": source_files,
    }
    motion.write_json(output / "source-manifest.json", manifest)
    return corpus


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def self_test() -> None:
    original_build = motion.build

    def fake_build(root: Path, seed: int, seconds: float) -> dict:
        root.mkdir(parents=True, exist_ok=True)
        folder = root / "cases" / "case"
        folder.mkdir(parents=True)
        for name in ("mic.pcm", "render.pcm", "echo.pcm"):
            (folder / name).write_bytes(seed.to_bytes(4, "little") + name.encode())
        motion.write_json(folder / "ground-truth.json", {"seed": seed})
        return {"cases": [{
            "case_id": "case", "split": "dev", "scenario": "aec-continuous-motion",
            "sample_rate_hz": motion.RATE, "mic_channels": 1,
            "mic_audio": "cases/case/mic.pcm", "render_audio": "cases/case/render.pcm",
            "clean_near_audio": None, "echo_audio": "cases/case/echo.pcm", "vad_labels": None,
            "control": {}, "processor_profile": "default", "expected": {},
            "source": {"dataset_id": motion.DATASET_ID, "source_id": "case",
                       "generator_seed": seed, "ground_truth": "cases/case/ground-truth.json",
                       "model_sha256": motion.json_sha256(motion.MODEL)}
        }]}

    motion.build = fake_build
    try:
        with tempfile.TemporaryDirectory(prefix="ap-aec-motion-bundle-v2-") as raw:
            root = Path(raw)
            a, b, c = root / "a", root / "b", root / "c"
            ca = build(a, [4107, 4207], 4.0, "development")
            cb = build(b, [4107, 4207], 4.0, "development")
            cc = build(c, [5107, 5207], 4.0, "validation")
            assert len(ca["cases"]) == 2 and len({item["case_id"] for item in ca["cases"]}) == 2
            assert ca["sources"] == [motion.DATASET_ID]
            assert all(item["split"] == "dev" and item["source"]["ground_truth"].startswith("seed-")
                       for item in ca["cases"])
            assert tree_digest(a) == tree_digest(b) and tree_digest(a) != tree_digest(c)
            try:
                build(root / "bad", [1, 1], 4.0, "shadow")
            except ValueError:
                pass
            else:
                raise AssertionError("duplicate seeds accepted")
            shutil.rmtree(root / "bad", ignore_errors=True)
            try:
                build(a, [1, 2], 4.0, "development")
            except ValueError:
                pass
            else:
                raise AssertionError("stale bundle output accepted")
    finally:
        motion.build = original_build
    print("AEC motion geometry bundle v2 self-test: orchestration/path binding controls OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, action="append", dest="seeds")
    parser.add_argument("--seconds", type=float, default=8.0)
    parser.add_argument("--role", choices=("development", "validation", "shadow"), default="development")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.output is None or not args.seeds:
        parser.error("--output and at least two --seed values are required")
    try:
        corpus = build(args.output, args.seeds, args.seconds, args.role)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps({"corpus": str(args.output / "corpus.json"), "corpus_id": corpus["corpus_id"],
                      "cases": len(corpus["cases"]), "seeds": args.seeds, "role": args.role}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
