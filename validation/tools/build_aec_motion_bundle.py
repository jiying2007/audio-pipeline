#!/usr/bin/env python3
"""Build deterministic multi-seed AEC motion bundles for tuning roles.

This composes independent build_aec_motion_corpus.py outputs without changing
case semantics. Bundles stay tier=regression and are development/replay assets,
never blind, release, HIL, or shipping authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import build_aec_motion_corpus as motion


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prefix_path(seed: int, raw: str | None) -> str | None:
    return None if raw is None else f"seed-{seed}/{raw}"


def build(output: Path, seeds: list[int], seconds: float, role: str) -> dict:
    if role not in {"development", "validation", "shadow"}:
        raise ValueError("role must be development, validation, or shadow")
    if len(seeds) < 2 or len(set(seeds)) != len(seeds):
        raise ValueError("bundle requires at least two distinct seeds")
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
            copied["source"]["source_id"] = copied["case_id"]
            copied["source"]["bundle_seed"] = seed
            cases.append(copied)
        for path in sorted(seed_root.rglob("*.pcm")):
            source_files[str(path.relative_to(output))] = sha256_file(path)

    corpus = {
        "schema_version": 1,
        "corpus_id": "aec-motion-bundle-v1-" + role + "-" + "-".join(str(seed) for seed in seeds),
        "tier": "regression",
        "generator": {
            "name": "build_aec_motion_bundle.py",
            "version": 1,
            "seeds": seeds,
            "seconds": seconds,
            "role": role,
            "continuous_motion": True,
            "explicit_path_change_notifications": False,
        },
        "sources": ["deterministic-aec-motion-v1"],
        "sealed_data": False,
        "cases": cases,
    }
    corpus_path = output / "corpus.json"
    corpus_path.write_text(json.dumps(corpus, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "authority": "development-only-non-shipping",
        "role": role,
        "seeds": seeds,
        "cases": len(cases),
        "corpus_sha256": sha256_file(corpus_path),
        "files": source_files,
    }
    (output / "source-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return corpus


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="ap-aec-motion-bundle-") as raw:
        root = Path(raw)
        a, b, c = root / "a", root / "b", root / "c"
        ca = build(a, [4107, 4207], 4.0, "development")
        cb = build(b, [4107, 4207], 4.0, "development")
        cc = build(c, [5107, 5207], 4.0, "validation")
        assert len(ca["cases"]) == 24
        assert len({item["case_id"] for item in ca["cases"]}) == 24
        assert ca["tier"] == "regression"
        assert ca["generator"]["role"] == "development"
        assert all(item["split"] == "dev" for item in ca["cases"])
        assert tree_digest(a) == tree_digest(b)
        assert tree_digest(a) != tree_digest(c)
        try:
            build(root / "bad", [1, 1], 4.0, "shadow")
        except ValueError:
            pass
        else:
            raise AssertionError("duplicate seeds must fail closed")
        shutil.rmtree(root / "bad", ignore_errors=True)
    print("AEC motion bundle self-test: OK")


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
    if args.output is None or not args.seeds or len(args.seeds) < 2 or args.seconds < 4.0:
        parser.error("--output, at least two --seed values, and --seconds >= 4 are required")
    corpus = build(args.output, args.seeds, args.seconds, args.role)
    print(json.dumps({
        "corpus": str(args.output / "corpus.json"),
        "corpus_id": corpus["corpus_id"],
        "cases": len(corpus["cases"]),
        "seeds": args.seeds,
        "role": args.role,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
