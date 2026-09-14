#!/usr/bin/env python3
"""Select a post-freeze externally-nonced Microsoft AEC holdout.

The selector operates on Git LFS pointer metadata before the selected audio is
materialized. Selection is deterministic for a GitHub-assigned run id, excludes
all precommitted hosted-AEC cases, and has no tuning or promotion authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path

SOURCE_REPOSITORY = "microsoft/AEC-Challenge"
SOURCE_REVISION = "6c633d0a9d2a143a0e364899b91b06f127315b18"
PREFIX = Path("datasets/test_set_icassp2022/farend-singletalk")
USAGE_CLASS = "validation-only-composite-upstream-terms"
LICENSE = "Composite upstream dataset terms; see the pinned AEC-Challenge README Dataset licenses section."
LICENSE_EVIDENCE = (
    "https://github.com/microsoft/AEC-Challenge/blob/"
    + SOURCE_REVISION
    + "/README.md#dataset-licenses"
)
POINTER_VERSION = "version https://git-lfs.github.com/spec/v1"
CANDIDATE_RE = re.compile(r"^[0-9a-f]{12}$")
NONCE_RE = re.compile(r"^[1-9][0-9]*$")
OID_RE = re.compile(r"^oid sha256:([0-9a-f]{64})$")
SIZE_RE = re.compile(r"^size ([1-9][0-9]*)$")


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def parse_pointer(path: Path) -> tuple[str, int]:
    require(path.is_file(), f"missing Git LFS pointer: {path}")
    raw = path.read_bytes()
    require(len(raw) <= 1024, f"audio was materialized before selection: {path}")
    text = raw.decode("ascii")
    lines = text.splitlines()
    require(len(lines) >= 3 and lines[0] == POINTER_VERSION, f"not a Git LFS pointer: {path}")
    oid_match = OID_RE.fullmatch(lines[1])
    size_match = SIZE_RE.fullmatch(lines[2])
    require(oid_match is not None and size_match is not None, f"invalid Git LFS pointer: {path}")
    size = int(size_match.group(1))
    require(size >= 1024, f"invalid LFS object size: {path}")
    return oid_match.group(1), size


def excluded_paths(lock_path: Path) -> set[str]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    require(lock.get("source_repository") == SOURCE_REPOSITORY, "exclude lock repository drift")
    require(lock.get("source_revision") == SOURCE_REVISION, "exclude lock revision drift")
    excluded: set[str] = set()
    for case in lock.get("cases", []):
        for role in ("mic", "render"):
            value = str((case.get(role) or {}).get("path", ""))
            require(value, f"exclude lock missing {role} path")
            excluded.add(value)
    require(excluded, "exclude lock must contain precommitted cases")
    return excluded


def discover(source_root: Path, excluded: set[str]) -> list[dict]:
    root = source_root / PREFIX
    require(root.is_dir(), f"missing pinned AEC directory: {root}")
    discovered: list[dict] = []
    for mic in sorted(root.glob("*_mic.wav")):
        rel_mic = mic.relative_to(source_root).as_posix()
        render = mic.with_name(mic.name[:-8] + "_lpb.wav")
        if not render.is_file():
            raise ValueError(f"missing render pair for {rel_mic}")
        rel_render = render.relative_to(source_root).as_posix()
        if rel_mic in excluded or rel_render in excluded:
            continue
        mic_oid, mic_size = parse_pointer(mic)
        render_oid, render_size = parse_pointer(render)
        movement = "farend-singletalk-with-movement" in mic.name
        require(
            movement or "farend-singletalk_mic.wav" in mic.name,
            f"unsupported far-end scenario: {rel_mic}",
        )
        discovered.append({
            "movement": movement,
            "mic_path": rel_mic,
            "mic_sha256": mic_oid,
            "mic_size": mic_size,
            "render_path": rel_render,
            "render_sha256": render_oid,
            "render_size": render_size,
        })
    require(discovered, "no eligible AEC LFS pairs discovered")
    return discovered


def rank(item: dict, nonce: str, candidate_id: str) -> str:
    payload = f"{nonce}\0{candidate_id}\0{item['mic_path']}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def select_cases(items: list[dict], nonce: str, candidate_id: str, per_scenario: int) -> list[dict]:
    require(NONCE_RE.fullmatch(nonce) is not None, "nonce must be a positive decimal GitHub run id")
    require(CANDIDATE_RE.fullmatch(candidate_id) is not None, "candidate id must be 12 lowercase hex")
    require(2 <= per_scenario <= 16, "per_scenario must be in [2, 16]")
    selected: list[dict] = []
    for movement in (False, True):
        pool = [item for item in items if item["movement"] is movement]
        require(len(pool) >= per_scenario, f"insufficient {'movement' if movement else 'static'} cases")
        pool.sort(key=lambda item: (rank(item, nonce, candidate_id), item["mic_path"]))
        for item in pool[:per_scenario]:
            digest = hashlib.sha256(item["mic_path"].encode()).hexdigest()[:12]
            kind = "moving" if movement else "static"
            selected.append({
                "id": f"blind-{kind}-{digest}",
                "scenario": "aec-farend-singletalk-movement" if movement else "aec-farend-singletalk",
                "movement": movement,
                "mic": {
                    "path": item["mic_path"],
                    "sha256": item["mic_sha256"],
                    "size": item["mic_size"],
                },
                "render": {
                    "path": item["render_path"],
                    "sha256": item["render_sha256"],
                    "size": item["render_size"],
                },
            })
    return selected


def build_lock(source_root: Path, exclude_lock: Path, nonce: str, candidate_id: str, per_scenario: int) -> tuple[dict, dict]:
    excluded = excluded_paths(exclude_lock)
    items = discover(source_root, excluded)
    cases = select_cases(items, nonce, candidate_id, per_scenario)
    selected_paths = {case[role]["path"] for case in cases for role in ("mic", "render")}
    require(not selected_paths.intersection(excluded), "precommitted hosted-AEC case leaked into holdout")
    lock = {
        "schema_version": 1,
        "catalog_id": "audio-pipeline-hosted-blind-aec-v1",
        "source_repository": SOURCE_REPOSITORY,
        "source_revision": SOURCE_REVISION,
        "usage_class": USAGE_CLASS,
        "license": LICENSE,
        "license_evidence": LICENSE_EVIDENCE,
        "cases": cases,
    }
    selection = {
        "schema_version": 1,
        "authority": "post-freeze-externally-nonced-software-holdout",
        "nonce_source": "github.run_id",
        "nonce": nonce,
        "candidate_id": candidate_id,
        "source_repository": SOURCE_REPOSITORY,
        "source_revision": SOURCE_REVISION,
        "eligible_pairs_after_exclusion": len(items),
        "excluded_precommitted_paths": len(excluded),
        "selected_cases": len(cases),
        "selected_static": sum(not case["movement"] for case in cases),
        "selected_movement": sum(case["movement"] for case in cases),
        "selection_rule": "sha256(github_run_id NUL candidate_id NUL mic_path), lowest ranks per scenario",
        "rule": (
            "The nonce is externally assigned after candidate freeze but is not secret HMAC material. "
            "This is one-way software/public-data qualification only and grants no target, HIL, DUT, soak, "
            "Product Certification, or shipping authority."
        ),
    }
    return lock, selection


def pointer(oid_digit: str, size: int = 4096) -> str:
    return f"{POINTER_VERSION}\noid sha256:{oid_digit * 64}\nsize {size}\n"


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="ap-hosted-blind-") as temporary:
        root = Path(temporary)
        source = root / "source"
        data = source / PREFIX
        data.mkdir(parents=True)
        cases = []
        for movement in (False, True):
            for index in range(8):
                token = f"{'m' if movement else 's'}{index:02d}"
                stem = f"{token}_farend-singletalk{'-with-movement' if movement else ''}"
                mic = data / f"{stem}_mic.wav"
                render = data / f"{stem}_lpb.wav"
                mic.write_text(pointer("a" if not movement else "b"), encoding="ascii")
                render.write_text(pointer("c" if not movement else "d"), encoding="ascii")
                cases.append((mic, render, movement))
        exclude = root / "exclude.json"
        first_mic, first_render, _ = cases[0]
        exclude.write_text(json.dumps({
            "source_repository": SOURCE_REPOSITORY,
            "source_revision": SOURCE_REVISION,
            "cases": [{
                "mic": {"path": first_mic.relative_to(source).as_posix()},
                "render": {"path": first_render.relative_to(source).as_posix()},
            }],
        }), encoding="utf-8")
        lock1, meta1 = build_lock(source, exclude, "123456", "4a6a408bf0e3", 3)
        lock2, _ = build_lock(source, exclude, "123456", "4a6a408bf0e3", 3)
        lock3, _ = build_lock(source, exclude, "123457", "4a6a408bf0e3", 3)
        assert lock1 == lock2
        assert [c["id"] for c in lock1["cases"]] != [c["id"] for c in lock3["cases"]]
        assert len(lock1["cases"]) == 6 and meta1["selected_static"] == 3 and meta1["selected_movement"] == 3
        assert first_mic.relative_to(source).as_posix() not in {
            c[role]["path"] for c in lock1["cases"] for role in ("mic", "render")
        }
        materialized = root / "materialized.wav"
        materialized.write_bytes(b"RIFF" + b"x" * 2048)
        try:
            parse_pointer(materialized)
        except (ValueError, UnicodeDecodeError):
            pass
        else:
            raise AssertionError("materialized audio was accepted before selection")
        try:
            select_cases(discover(source, excluded_paths(exclude)), "0", "4a6a408bf0e3", 3)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid external nonce was accepted")
    print("acoustic candidate hosted blind selector self-test: OK")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--exclude-lock", type=Path)
    parser.add_argument("--nonce")
    parser.add_argument("--candidate-id")
    parser.add_argument("--per-scenario", type=int, default=6)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--metadata-output", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    required = ("source_root", "exclude_lock", "nonce", "candidate_id", "output", "metadata_output")
    missing = [name for name in required if getattr(args, name) is None]
    if missing:
        parser.error("missing required arguments: " + ", ".join(missing))
    lock, metadata = build_lock(
        args.source_root, args.exclude_lock, args.nonce, args.candidate_id, args.per_scenario
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.metadata_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.metadata_output.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metadata, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
