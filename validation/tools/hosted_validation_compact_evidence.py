#!/usr/bin/env python3
"""Compact reproducible hosted validation artifacts after validation completes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def payload_stats(path: Path) -> tuple[int, int]:
    files = [item for item in path.rglob("*") if item.is_file()]
    return len(files), sum(item.stat().st_size for item in files)


def compact(
    root: Path,
    builder: Path,
    dataset_lock: Path,
    repository_revision: str,
) -> dict:
    if SHA_RE.fullmatch(repository_revision) is None:
        raise ValueError("repository revision must be exact lowercase 40-hex")
    root = root.resolve()
    corpus_dir = root / "corpus"
    corpus = corpus_dir / "corpus.json"
    source_manifest = corpus_dir / "source-manifest.json"
    materialized = corpus_dir / "cases"
    for path in (corpus, source_manifest, builder, dataset_lock):
        if not path.is_file():
            raise ValueError(f"required compact-evidence input missing: {path}")
    if not materialized.is_dir():
        raise ValueError(f"materialized corpus payload missing: {materialized}")

    source = json.loads(source_manifest.read_text(encoding="utf-8"))
    source_repository = source.get("source_repository")
    source_revision = source.get("source_revision")
    if not isinstance(source_repository, str) or not source_repository:
        raise ValueError("source manifest repository identity missing")
    if not isinstance(source_revision, str) or SHA_RE.fullmatch(source_revision) is None:
        raise ValueError("source manifest revision must be exact lowercase 40-hex")

    removed_files, removed_bytes = payload_stats(materialized)
    if removed_files <= 0 or removed_bytes <= 0:
        raise ValueError("materialized corpus payload must be non-empty before compaction")

    builder_digest = sha256_file(builder)
    policy = {
        "schema_version": 1,
        "artifact_scope": "hash-bound-manifest-only",
        "materialized_audio_retained": False,
        "reason": (
            "materialized validation audio is reproducible from the retained "
            "exact-source manifest, hashes, builder and dataset lock"
        ),
        "repository_revision": repository_revision,
        "source_repository": source_repository,
        "source_revision": source_revision,
        "corpus_sha256": sha256_file(corpus),
        "source_manifest_sha256": sha256_file(source_manifest),
        "builder_sha256": builder_digest,
        "dataset_lock_sha256": sha256_file(dataset_lock),
        "removed_materialized_payload": {
            "path": str(materialized.relative_to(root)),
            "files": removed_files,
            "bytes": removed_bytes,
        },
        "rebuild": {
            "builder": str(builder),
            "dataset_lock": str(dataset_lock),
            "requires_exact_external_source_revision": True,
        },
    }
    (root / "corpus-builder.sha256").write_text(
        f"{builder_digest}  {builder}\n", encoding="utf-8"
    )
    (root / "artifact-policy.json").write_text(
        json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    shutil.rmtree(materialized)
    if materialized.exists():
        raise AssertionError("materialized payload remained after compaction")
    return policy


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        root = base / "out"
        cases = root / "corpus" / "cases" / "case-a"
        cases.mkdir(parents=True)
        (cases / "mic.pcm").write_bytes(b"abc" * 1024)
        (root / "corpus" / "corpus.json").write_text(
            json.dumps({"schema_version": 1, "cases": [{"case_id": "a"}]}) + "\n",
            encoding="utf-8",
        )
        (root / "corpus" / "source-manifest.json").write_text(
            json.dumps({
                "schema_version": 1,
                "source_repository": "example/public-corpus",
                "source_revision": "2" * 40,
            }) + "\n",
            encoding="utf-8",
        )
        builder = base / "builder.py"
        builder.write_text("print('builder')\n", encoding="utf-8")
        lock = base / "lock.json"
        lock.write_text('{"schema_version":1}\n', encoding="utf-8")

        policy = compact(root, builder, lock, "1" * 40)
        assert policy["artifact_scope"] == "hash-bound-manifest-only"
        assert policy["materialized_audio_retained"] is False
        assert policy["removed_materialized_payload"]["files"] == 1
        assert policy["removed_materialized_payload"]["bytes"] == 3 * 1024
        assert not (root / "corpus" / "cases").exists()
        assert (root / "artifact-policy.json").is_file()
        assert (root / "corpus-builder.sha256").is_file()
    print("reproducible corpus evidence compactor self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--builder", type=Path)
    parser.add_argument("--dataset-lock", type=Path)
    parser.add_argument(
        "--repository-revision",
        default=os.environ.get("GITHUB_SHA", ""),
    )
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    for name in ("root", "builder", "dataset_lock"):
        if getattr(args, name) is None:
            parser.error(f"--{name.replace('_', '-')} is required")
    policy = compact(
        args.root,
        args.builder,
        args.dataset_lock,
        args.repository_revision,
    )
    print(json.dumps({
        "result": "COMPACTED_REPRODUCIBLE_EVIDENCE",
        "removed_files": policy["removed_materialized_payload"]["files"],
        "removed_bytes": policy["removed_materialized_payload"]["bytes"],
        "source_revision": policy["source_revision"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
