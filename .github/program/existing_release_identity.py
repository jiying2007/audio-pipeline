#!/usr/bin/env python3
"""Validate an already-published release before release.yml short-circuits.

This validator is intentionally self-consistency based: a release-neutral main
commit may be newer than the immutable software release. The release source
must therefore be an ancestor of the current verified main SHA, while the tag,
manifest and asset identities must bind to the exact historical release source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:([0-9a-f]{64})$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_names(tag: str) -> tuple[set[str], set[str], set[str]]:
    payload = {
        f"audio-pipeline-{tag}-sdk.tar.gz",
        f"audio-pipeline-{tag}-source.tar.gz",
        f"audio-pipeline-{tag}.spdx.json",
        f"audio-pipeline-{tag}-validation-smoke-corpus.json",
        f"audio-pipeline-{tag}-validation-smoke.json",
        f"audio-pipeline-{tag}-validation-smoke-evidence.json",
    }
    manifest = f"audio-pipeline-{tag}-release-manifest.json"
    sums = "SHA256SUMS"
    return payload, payload | {manifest}, payload | {manifest, sums}


def asset_digests(release: dict) -> dict[str, str]:
    result: dict[str, str] = {}
    for asset in release.get("assets", []):
        name = asset.get("name")
        digest = asset.get("digest")
        if not isinstance(name, str) or not name or name in result:
            raise ValueError("release asset names must be unique non-empty strings")
        match = DIGEST_RE.fullmatch(str(digest))
        if not match:
            raise ValueError(f"release asset lacks sha256 digest: {name}")
        result[name] = match.group(1)
    return result


def checksum_records(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split(None, 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            raise ValueError("invalid SHA256SUMS row")
        name = parts[1].lstrip("*")
        if "/" in name or name in result:
            raise ValueError("SHA256SUMS must use unique release basenames")
        result[name] = parts[0]
    return result


def validate(*, release: dict, manifest: dict, sums_path: Path, manifest_path: Path,
             tag: str, version: str, tag_peel_sha: str, verified_sha: str,
             release_source_is_ancestor: bool) -> dict:
    if not SHA_RE.fullmatch(tag_peel_sha) or not SHA_RE.fullmatch(verified_sha):
        raise ValueError("tag/current source must be exact 40-hex SHA")
    if release.get("tag_name") != tag or release.get("draft") is not False or \
            release.get("prerelease") is not False or release.get("immutable") is not True:
        raise ValueError("existing release must be immutable, published and exact-tagged")

    payload_names, checksummed_names, all_names = expected_names(tag)
    assets = asset_digests(release)
    if set(assets) != all_names:
        raise ValueError(f"existing release asset contract mismatch: {sorted(assets)}")

    if manifest.get("schema_version") != 1:
        raise ValueError("release manifest schema mismatch")
    rel = manifest.get("release", {})
    source = manifest.get("source", {})
    if rel != {"immutable_required": True, "tag": tag, "version": version}:
        raise ValueError("release manifest identity mismatch")
    manifest_source = source.get("commit_sha")
    if not SHA_RE.fullmatch(str(manifest_source)):
        raise ValueError("manifest source SHA missing/invalid")
    if manifest_source != tag_peel_sha:
        raise ValueError("release tag peel and manifest source disagree")
    if not release_source_is_ancestor:
        raise ValueError("existing release source is not an ancestor of verified main")

    manifest_assets = manifest.get("assets")
    if not isinstance(manifest_assets, list):
        raise ValueError("release manifest assets missing")
    records = {}
    for item in manifest_assets:
        if not isinstance(item, dict) or set(item) != {"name", "sha256", "size"}:
            raise ValueError("release manifest asset record malformed")
        name, digest = item["name"], item["sha256"]
        if name in records or name not in payload_names or not re.fullmatch(r"[0-9a-f]{64}", str(digest)):
            raise ValueError("release manifest payload asset identity mismatch")
        records[name] = digest
    if set(records) != payload_names:
        raise ValueError("release manifest payload set mismatch")
    for name, digest in records.items():
        if assets[name] != digest:
            raise ValueError(f"release asset digest disagrees with manifest: {name}")

    manifest_name = f"audio-pipeline-{tag}-release-manifest.json"
    if sha256(manifest_path) != assets[manifest_name]:
        raise ValueError("release manifest file digest disagrees with GitHub asset metadata")
    if sha256(sums_path) != assets["SHA256SUMS"]:
        raise ValueError("SHA256SUMS file digest disagrees with GitHub asset metadata")
    sums = checksum_records(sums_path)
    if set(sums) != checksummed_names:
        raise ValueError("SHA256SUMS asset set mismatch")
    for name, digest in sums.items():
        if assets[name] != digest:
            raise ValueError(f"SHA256SUMS disagrees with GitHub asset digest: {name}")

    return {
        "schema_version": 1,
        "tag": tag,
        "version": version,
        "release_source_sha": manifest_source,
        "verified_main_sha": verified_sha,
        "release_source_is_ancestor": True,
        "immutable": True,
        "asset_count": len(assets),
        "checksummed_assets": len(sums),
        "manifest_payload_assets": len(records),
        "result": "EXISTING_RELEASE_IDENTITY_PASS",
    }


def self_test() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tag, version = "v9.8.7", "9.8.7"
        source, current = "a" * 40, "b" * 40
        payload, checksummed, all_names = expected_names(tag)
        payload_bytes = {name: ("bytes:" + name).encode() for name in payload}
        manifest = {
            "schema_version": 1,
            "release": {"version": version, "tag": tag, "immutable_required": True},
            "source": {"commit_sha": source, "tree_sha": "c" * 40},
            "lineage": {"merged_pr_numbers": [1], "main_verify_run_id": "2"},
            "validation_bindings": {},
            "assets": sorted([
                {"name": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                for name, data in payload_bytes.items()
            ], key=lambda item: item["name"]),
            "lab_qualification": {},
        }
        manifest_path = root / f"audio-pipeline-{tag}-release-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        digests = {name: hashlib.sha256(data).hexdigest() for name, data in payload_bytes.items()}
        digests[manifest_path.name] = sha256(manifest_path)
        sums_path = root / "SHA256SUMS"
        sums_path.write_text("".join(f"{digests[name]}  {name}\n" for name in sorted(checksummed)))
        digests["SHA256SUMS"] = sha256(sums_path)
        release = {
            "tag_name": tag, "draft": False, "prerelease": False, "immutable": True,
            "assets": [{"name": name, "digest": "sha256:" + digests[name]} for name in sorted(all_names)],
        }
        good = dict(release=release, manifest=manifest, sums_path=sums_path,
                    manifest_path=manifest_path, tag=tag, version=version,
                    tag_peel_sha=source, verified_sha=current, release_source_is_ancestor=True)
        assert validate(**good)["result"] == "EXISTING_RELEASE_IDENTITY_PASS"
        for mutate in (
            lambda x: x.update(tag_peel_sha="d" * 40),
            lambda x: x.update(release_source_is_ancestor=False),
            lambda x: x["release"]["assets"].pop(),
        ):
            bad = dict(good)
            bad["release"] = json.loads(json.dumps(release))
            mutate(bad)
            try:
                validate(**bad)
            except ValueError:
                pass
            else:
                raise AssertionError("invalid existing release identity accepted")
    print("existing release identity self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-json", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--sha256s", type=Path)
    parser.add_argument("--tag")
    parser.add_argument("--version")
    parser.add_argument("--tag-peel-sha")
    parser.add_argument("--verified-sha")
    parser.add_argument("--release-source-is-ancestor", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    for name in ("release_json", "manifest", "sha256s", "tag", "version", "tag_peel_sha", "verified_sha", "output"):
        if getattr(args, name) in (None, ""):
            parser.error(f"--{name.replace('_', '-')} is required")
    result = validate(
        release=json.loads(args.release_json.read_text()),
        manifest=json.loads(args.manifest.read_text()),
        sums_path=args.sha256s,
        manifest_path=args.manifest,
        tag=args.tag,
        version=args.version,
        tag_peel_sha=args.tag_peel_sha,
        verified_sha=args.verified_sha,
        release_source_is_ancestor=args.release_source_is_ancestor,
    )
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
