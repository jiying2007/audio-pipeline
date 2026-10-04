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
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MODES = {"external-source", "deterministic-generator"}


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
    *,
    mode: str = "external-source",
    source_repository: str | None = None,
) -> dict:
    if SHA_RE.fullmatch(repository_revision) is None:
        raise ValueError("repository revision must be exact lowercase 40-hex")
    if mode not in MODES:
        raise ValueError(f"unsupported compaction mode: {mode}")

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
    corpus_doc = json.loads(corpus.read_text(encoding="utf-8"))
    builder_digest = sha256_file(builder)
    corpus_digest = sha256_file(corpus)
    source_manifest_digest = sha256_file(source_manifest)

    removed_files, removed_bytes = payload_stats(materialized)
    if removed_files <= 0 or removed_bytes <= 0:
        raise ValueError("materialized corpus payload must be non-empty before compaction")

    policy = {
        "schema_version": 1,
        "artifact_scope": "hash-bound-manifest-only",
        "reproducibility_mode": mode,
        "materialized_audio_retained": False,
        "materialized_payload_retained": False,
        "repository_revision": repository_revision,
        "corpus_sha256": corpus_digest,
        "source_manifest_sha256": source_manifest_digest,
        "builder_sha256": builder_digest,
        "dataset_lock_sha256": sha256_file(dataset_lock),
        "removed_materialized_payload": {
            "path": str(materialized.relative_to(root)),
            "files": removed_files,
            "bytes": removed_bytes,
        },
    }

    if mode == "external-source":
        manifest_repository = source.get("source_repository")
        manifest_revision = source.get("source_revision")
        if not isinstance(manifest_repository, str) or not manifest_repository:
            raise ValueError("source manifest repository identity missing")
        if not isinstance(manifest_revision, str) or SHA_RE.fullmatch(manifest_revision) is None:
            raise ValueError("source manifest revision must be exact lowercase 40-hex")
        policy.update({
            "reason": (
                "materialized validation audio is reproducible from the retained "
                "exact-source manifest, hashes, builder and dataset lock"
            ),
            "source_repository": manifest_repository,
            "source_revision": manifest_revision,
            "rebuild": {
                "builder": str(builder),
                "dataset_lock": str(dataset_lock),
                "requires_exact_external_source_revision": True,
                "requires_exact_repository_revision": False,
            },
        })
    else:
        if not isinstance(source_repository, str) or not source_repository:
            raise ValueError("deterministic-generator mode requires source_repository")
        if source.get("authority") != "development-only-non-shipping":
            raise ValueError("deterministic generator authority drifted")
        seed = source.get("seed")
        generator_version = source.get("generator_version")
        generator_digest = source.get("generator_sha256")
        model_digest = source.get("model_sha256")
        manifest_corpus_digest = source.get("corpus_sha256")
        files = source.get("files")
        if type(seed) is not int or seed < 0:
            raise ValueError("deterministic generator seed missing")
        if type(generator_version) is not int or generator_version < 1:
            raise ValueError("deterministic generator version missing")
        if not isinstance(generator_digest, str) or SHA256_RE.fullmatch(generator_digest) is None:
            raise ValueError("deterministic generator SHA-256 missing")
        if generator_digest != builder_digest:
            raise ValueError("deterministic generator SHA-256 drifted")
        if not isinstance(model_digest, str) or SHA256_RE.fullmatch(model_digest) is None:
            raise ValueError("deterministic model SHA-256 missing")
        if manifest_corpus_digest != corpus_digest:
            raise ValueError("deterministic corpus SHA-256 drifted")
        if not isinstance(files, dict) or not files:
            raise ValueError("deterministic source manifest file hashes missing")
        if any(
            not isinstance(path, str)
            or not path
            or not isinstance(digest, str)
            or SHA256_RE.fullmatch(digest) is None
            for path, digest in files.items()
        ):
            raise ValueError("invalid deterministic source manifest file hash")

        generator = corpus_doc.get("generator")
        if not isinstance(generator, dict):
            raise ValueError("deterministic corpus generator identity missing")
        if generator.get("name") != builder.name:
            raise ValueError("deterministic corpus generator name drifted")
        if generator.get("version") != generator_version:
            raise ValueError("deterministic corpus generator version drifted")
        if generator.get("seed") != seed:
            raise ValueError("deterministic corpus seed drifted")
        seconds = generator.get("seconds")
        if not isinstance(seconds, (int, float)) or seconds <= 0:
            raise ValueError("deterministic corpus duration missing")

        policy.update({
            "reason": (
                "materialized synthetic regression payload is exactly reproducible "
                "from the retained repository revision, generator/model/file hashes, "
                "seed, duration and dataset lock"
            ),
            "source_repository": source_repository,
            "source_revision": repository_revision,
            "generator": {
                "seed": seed,
                "version": generator_version,
                "model_sha256": model_digest,
                "manifest_file_count": len(files),
            },
            "rebuild": {
                "builder": str(builder),
                "dataset_lock": str(dataset_lock),
                "requires_exact_external_source_revision": False,
                "requires_exact_repository_revision": True,
                "seed": seed,
                "seconds": seconds,
            },
        })

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
        builder = base / "builder.py"
        builder.write_text("print('builder')\n", encoding="utf-8")
        lock = base / "lock.json"
        lock.write_text('{"schema_version":1}\n', encoding="utf-8")

        external = base / "external"
        cases = external / "corpus" / "cases" / "case-a"
        cases.mkdir(parents=True)
        (cases / "mic.pcm").write_bytes(b"abc" * 1024)
        (external / "corpus" / "corpus.json").write_text(
            json.dumps({"schema_version": 1, "cases": [{"case_id": "a"}]}) + "\n",
            encoding="utf-8",
        )
        (external / "corpus" / "source-manifest.json").write_text(
            json.dumps({
                "schema_version": 1,
                "source_repository": "example/public-corpus",
                "source_revision": "2" * 40,
            }) + "\n",
            encoding="utf-8",
        )

        policy = compact(external, builder, lock, "1" * 40)
        assert policy["artifact_scope"] == "hash-bound-manifest-only"
        assert policy["reproducibility_mode"] == "external-source"
        assert policy["materialized_audio_retained"] is False
        assert policy["removed_materialized_payload"]["files"] == 1
        assert policy["removed_materialized_payload"]["bytes"] == 3 * 1024
        assert not (external / "corpus" / "cases").exists()
        assert (external / "artifact-policy.json").is_file()
        assert (external / "corpus-builder.sha256").is_file()

        generated = base / "generated"
        generated_cases = generated / "corpus" / "cases" / "case-a"
        generated_cases.mkdir(parents=True)
        generated_payload = b"deterministic" * 512
        (generated_cases / "mic.pcm").write_bytes(generated_payload)
        corpus_doc = {
            "schema_version": 1,
            "generator": {
                "name": builder.name,
                "version": 2,
                "seed": 4107,
                "seconds": 8.0,
            },
            "cases": [{"case_id": "a"}],
        }
        corpus_path = generated / "corpus" / "corpus.json"
        corpus_path.write_text(json.dumps(corpus_doc, sort_keys=True) + "\n", encoding="utf-8")
        payload_digest = hashlib.sha256(generated_payload).hexdigest()
        (generated / "corpus" / "source-manifest.json").write_text(
            json.dumps({
                "schema_version": 1,
                "authority": "development-only-non-shipping",
                "seed": 4107,
                "generator_version": 2,
                "generator_sha256": sha256_file(builder),
                "model_sha256": "3" * 64,
                "corpus_sha256": sha256_file(corpus_path),
                "files": {"cases/case-a/mic.pcm": payload_digest},
            }, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        generated_policy = compact(
            generated,
            builder,
            lock,
            "4" * 40,
            mode="deterministic-generator",
            source_repository="example/repository",
        )
        assert generated_policy["reproducibility_mode"] == "deterministic-generator"
        assert generated_policy["source_revision"] == "4" * 40
        assert generated_policy["generator"]["seed"] == 4107
        assert generated_policy["generator"]["manifest_file_count"] == 1
        assert generated_policy["rebuild"]["requires_exact_repository_revision"] is True
        assert not (generated / "corpus" / "cases").exists()
    print("reproducible corpus evidence compactor self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--builder", type=Path)
    parser.add_argument("--dataset-lock", type=Path)
    parser.add_argument("--mode", choices=sorted(MODES), default="external-source")
    parser.add_argument("--source-repository")
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
        mode=args.mode,
        source_repository=args.source_repository,
    )
    print(json.dumps({
        "result": "COMPACTED_REPRODUCIBLE_EVIDENCE",
        "mode": policy["reproducibility_mode"],
        "removed_files": policy["removed_materialized_payload"]["files"],
        "removed_bytes": policy["removed_materialized_payload"]["bytes"],
        "source_revision": policy["source_revision"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
