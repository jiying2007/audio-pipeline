#!/usr/bin/env python3
"""Provisioning-side controller for audio-pipeline laboratory data and readiness.

The tool deliberately keeps GitHub runner credentials, large corpora and generated
source manifests outside Git. Repository locks describe acquisition intent; the
canonical validation scanner remains the authority for per-file SHA-256 evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCK = REPO_ROOT / "lab" / "data-sources.lock.json"
EXTENDED_CATALOG = REPO_ROOT / "validation" / "extended.datasets.lock.json"
def resolve_user_paths(env: dict[str, str] | None = None, user_home: Path | None = None) -> tuple[Path, Path, Path, Path, Path, Path, Path, Path, Path]:
    values = os.environ if env is None else env
    home = (Path.home() if user_home is None else user_home).expanduser()
    xdg_data = Path(values.get("XDG_DATA_HOME", str(home / ".local/share"))).expanduser()
    xdg_cache = Path(values.get("XDG_CACHE_HOME", str(home / ".cache"))).expanduser()
    xdg_state = Path(values.get("XDG_STATE_HOME", str(home / ".local/state"))).expanduser()
    xdg_config = Path(values.get("XDG_CONFIG_HOME", str(home / ".config"))).expanduser()
    data_root = Path(values.get("AUDIO_PIPELINE_LAB_DATA_ROOT", str(home / "audio-validation-extended"))).expanduser()
    cache_root = Path(values.get("AUDIO_PIPELINE_LAB_CACHE_ROOT", str(xdg_cache / "audio-pipeline-lab/datasets"))).expanduser()
    state_root = Path(values.get("AUDIO_PIPELINE_LAB_STATE_ROOT", str(xdg_state / "audio-pipeline-lab"))).expanduser()
    board = Path(values.get("AUDIO_PIPELINE_LAB_BOARD", str(xdg_config / "audio-pipeline/board.json"))).expanduser()
    return home, xdg_data, xdg_cache, xdg_state, xdg_config, data_root, cache_root, state_root, board


(USER_HOME, XDG_DATA_HOME, XDG_CACHE_HOME, XDG_STATE_HOME, XDG_CONFIG_HOME,
 DEFAULT_DATA_ROOT, DEFAULT_CACHE_ROOT, DEFAULT_STATE_ROOT, DEFAULT_BOARD) = resolve_user_paths()
SUPPORTED_PROVIDERS = {"huggingface_snapshot", "http_archive", "operator_import"}
COMMERCIAL_PROFILES = {"commercial-core", "commercial-plus"}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def digest(path: Path, algorithm: str) -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print("+ " + " ".join(argv), flush=True)
    subprocess.run(argv, cwd=cwd, env=env, check=True)


def require_command(command: str) -> str:
    found = shutil.which(command)
    if not found:
        raise SystemExit(f"required command not found in PATH: {command}")
    return found


def validate_catalog(catalog: dict) -> None:
    if catalog.get("schema_version") != 1:
        raise ValueError("lab data catalog schema_version must be 1")
    datasets = catalog.get("datasets")
    profiles = catalog.get("profiles")
    if not isinstance(datasets, list) or not isinstance(profiles, dict):
        raise ValueError("lab data catalog requires datasets[] and profiles{}")
    by_id: dict[str, dict] = {}
    for item in datasets:
        dataset_id = item.get("id")
        if not isinstance(dataset_id, str) or not dataset_id or dataset_id in by_id:
            raise ValueError(f"invalid/duplicate dataset id: {dataset_id!r}")
        if item.get("provider") not in SUPPORTED_PROVIDERS:
            raise ValueError(f"unsupported provider for {dataset_id}: {item.get('provider')}")
        if not item.get("local_path") or Path(item["local_path"]).is_absolute() or ".." in Path(item["local_path"]).parts:
            raise ValueError(f"invalid local_path for {dataset_id}")
        if item.get("provider") == "huggingface_snapshot":
            if not re.fullmatch(r"[0-9a-f]{40}", str(item.get("revision", ""))):
                raise ValueError(f"Hugging Face source must use exact 40-hex revision: {dataset_id}")
            if not item.get("allow_patterns"):
                raise ValueError(f"Hugging Face source needs allow_patterns: {dataset_id}")
        if item.get("provider") == "http_archive":
            integrity = item.get("integrity", {})
            mode = integrity.get("mode")
            if mode not in {"md5", "sha256", "record-first-sha256"}:
                raise ValueError(f"invalid integrity mode for {dataset_id}: {mode}")
            if mode in {"md5", "sha256"}:
                expected = str(integrity.get("value", ""))
                width = 32 if mode == "md5" else 64
                if not re.fullmatch(rf"[0-9a-f]{{{width}}}", expected):
                    raise ValueError(f"invalid {mode} digest for {dataset_id}")
        by_id[dataset_id] = item
    for profile, ids in profiles.items():
        if not isinstance(ids, list) or not ids:
            raise ValueError(f"profile must contain dataset ids: {profile}")
        missing = set(ids) - set(by_id)
        if missing:
            raise ValueError(f"profile {profile} references missing datasets: {sorted(missing)}")
        if profile in COMMERCIAL_PROFILES:
            bad = [item for item in ids if by_id[item].get("usage_class") != "commercial-validation"]
            if bad:
                raise ValueError(f"commercial profile {profile} contains non-commercial sources: {bad}")
    expected_core = {"realman", "but-reverbdb", "musan", "openslr-slr31"}
    if set(profiles.get("commercial-core", [])) != expected_core:
        raise ValueError("commercial-core materialization set drifted")


def catalog_index(catalog: dict) -> dict[str, dict]:
    return {item["id"]: item for item in catalog["datasets"]}


def safe_extract_tar(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with tarfile.open(archive, "r:*") as handle:
        members = handle.getmembers()
        for member in members:
            if member.issym() or member.islnk():
                raise ValueError(f"archive links are not accepted: {member.name}")
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise ValueError(f"archive path traversal rejected: {member.name}")
        handle.extractall(destination, members=members)


def acquisition_path(state_root: Path, dataset_id: str) -> Path:
    return state_root / "acquisition" / f"{dataset_id}.json"


def record_or_verify_acquisition(item: dict, archive: Path, state_root: Path) -> dict:
    sha256 = digest(archive, "sha256")
    record = {
        "schema_version": 1,
        "dataset_id": item["id"],
        "source": item.get("url"),
        "archive_name": archive.name,
        "size": archive.stat().st_size,
        "sha256": sha256,
        "integrity_mode": item["integrity"]["mode"],
    }
    path = acquisition_path(state_root, item["id"])
    if path.exists():
        existing = load_json(path)
        comparable = {key: existing.get(key) for key in record}
        if comparable != record:
            raise ValueError(f"acquisition seal mismatch for {item['id']}: {path}")
    else:
        write_json(path, record)
        path.chmod(0o640)
    return record


def download_archive(item: dict, cache_root: Path, state_root: Path) -> tuple[Path, dict]:
    downloader = "aria2c" if shutil.which("aria2c") else require_command("curl")
    directory = cache_root / item["id"]
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / item["archive_name"]
    if not archive.exists():
        if downloader == "aria2c":
            run([
                "aria2c", "--continue=true", "--max-connection-per-server=4", "--split=4",
                "--min-split-size=16M", "--file-allocation=none", "--dir", str(directory),
                "--out", archive.name, item["url"],
            ])
        else:
            run(["curl", "--fail", "--location", "--retry", "5", "--continue-at", "-",
                 "--output", str(archive), item["url"]])
    integrity = item["integrity"]
    mode = integrity["mode"]
    if mode in {"md5", "sha256"}:
        actual = digest(archive, mode)
        if actual != integrity["value"]:
            raise ValueError(f"{item['id']} {mode} mismatch: {actual} != {integrity['value']}")
    record = record_or_verify_acquisition(item, archive, state_root)
    return archive, record


def materialize_http(item: dict, data_root: Path, cache_root: Path, state_root: Path, force: bool) -> None:
    archive, record = download_archive(item, cache_root, state_root)
    destination = data_root / item["local_path"]
    marker = destination / ".audio-pipeline-materialized.json"
    if marker.exists() and not force:
        current = load_json(marker)
        if current.get("archive_sha256") == record["sha256"]:
            print(f"{item['id']}: already materialized and acquisition-bound")
            return
        raise ValueError(f"materialization marker disagrees with acquisition seal: {item['id']}")
    if force and destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    safe_extract_tar(archive, destination)
    write_json(marker, {
        "schema_version": 1,
        "dataset_id": item["id"],
        "archive_sha256": record["sha256"],
        "source": item["url"],
    })


def copy_metadata_tree(snapshot: Path, destination: Path) -> None:
    for source in snapshot.rglob("*"):
        if not source.is_file() or source.suffix.lower() == ".rar":
            continue
        relative = source.relative_to(snapshot)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def materialize_huggingface(item: dict, data_root: Path, cache_root: Path, state_root: Path, force: bool) -> None:
    require_command("7z")
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise SystemExit("huggingface_hub is required; use the Ansible-created user venv or install lab/requirements-validation.txt") from exc
    snapshot = cache_root / item["id"] / "snapshot"
    snapshot.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=item["repo_id"], repo_type=item.get("repo_type", "dataset"),
        revision=item["revision"], allow_patterns=item["allow_patterns"],
        local_dir=str(snapshot),
    )
    destination = data_root / item["local_path"]
    marker = destination / ".audio-pipeline-materialized.json"
    if marker.exists() and not force:
        current = load_json(marker)
        if current.get("upstream_revision") == item["revision"]:
            print(f"{item['id']}: already materialized at exact revision {item['revision']}")
            return
        raise ValueError(f"materialization revision mismatch for {item['id']}")
    if force and destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    copy_metadata_tree(snapshot, destination)
    archives = sorted(snapshot.rglob("*.rar"))
    if not archives:
        raise ValueError("RealMAN snapshot contained no RAR archives under selected val/test patterns")
    archive_records = []
    for archive in archives:
        relative = archive.relative_to(snapshot)
        target = destination / relative.parent / archive.stem
        target.mkdir(parents=True, exist_ok=True)
        run(["7z", "x", "-y", "-bso0", "-bsp0", f"-o{target}", str(archive)])
        archive_records.append({
            "path": relative.as_posix(), "size": archive.stat().st_size, "sha256": digest(archive, "sha256")
        })
    record = {
        "schema_version": 1,
        "dataset_id": item["id"],
        "repo_id": item["repo_id"],
        "upstream_revision": item["revision"],
        "archives": archive_records,
    }
    path = acquisition_path(state_root, item["id"])
    if path.exists() and load_json(path) != record:
        raise ValueError(f"Hugging Face acquisition seal drifted: {path}")
    write_json(path, record)
    path.chmod(0o640)
    write_json(marker, {
        "schema_version": 1, "dataset_id": item["id"], "upstream_revision": item["revision"],
        "archive_count": len(archive_records),
    })


def materialize_profile(catalog: dict, profile: str, data_root: Path, cache_root: Path,
                        state_root: Path, force: bool, skip_operator: bool) -> None:
    if profile not in catalog["profiles"]:
        raise ValueError(f"unknown profile: {profile}")
    by_id = catalog_index(catalog)
    data_root.mkdir(parents=True, exist_ok=True)
    for dataset_id in catalog["profiles"][profile]:
        item = by_id[dataset_id]
        print(f"== materialize {dataset_id} ({item['provider']}) ==", flush=True)
        if item["provider"] == "http_archive":
            materialize_http(item, data_root, cache_root, state_root, force)
        elif item["provider"] == "huggingface_snapshot":
            materialize_huggingface(item, data_root, cache_root, state_root, force)
        elif skip_operator:
            print(f"{dataset_id}: operator import required ({item.get('required_hint', 'see catalog')})")
        else:
            raise SystemExit(
                f"{dataset_id} requires reviewed operator import. Use `labctl.py adopt --dataset {dataset_id} --source PATH` first, or --skip-operator."
            )


def adopt_dataset(catalog: dict, dataset_id: str, source: Path, data_root: Path, delete: bool) -> None:
    by_id = catalog_index(catalog)
    item = by_id.get(dataset_id)
    if not item or item.get("provider") != "operator_import":
        raise ValueError(f"dataset is not an operator-import source: {dataset_id}")
    if not source.is_dir():
        raise ValueError(f"operator source directory does not exist: {source}")
    require_command("rsync")
    target = data_root / item["local_path"]
    target.mkdir(parents=True, exist_ok=True)
    args = ["rsync", "-a", "--human-readable"]
    if delete:
        args.append("--delete")
    args += [str(source.resolve()) + "/", str(target.resolve()) + "/"]
    run(args)
    write_json(target / ".audio-pipeline-materialized.json", {
        "schema_version": 1, "dataset_id": dataset_id, "provider": "operator_import",
        "source_path": str(source.resolve()),
    })


def verify_profile(profile: str, data_root: Path, state_root: Path, limit: int,
                   source_revision: str | None) -> dict:
    if profile not in COMMERCIAL_PROFILES:
        raise ValueError("lab activation currently accepts commercial-core or commercial-plus")
    evidence = state_root / "readiness" / profile
    evidence.mkdir(parents=True, exist_ok=True)
    manifest = evidence / "source-manifest.json"
    scan = [
        sys.executable, str(REPO_ROOT / "validation/tools/prepare_extended_validation.py"), "scan",
        "--catalog", str(EXTENDED_CATALOG), "--data-root", str(data_root),
        "--profile", profile, "--limit-per-dataset", str(limit), "--output", str(manifest),
    ]
    run(scan, cwd=REPO_ROOT)
    run([
        sys.executable, str(REPO_ROOT / "validation/tools/prepare_extended_validation.py"), "verify",
        "--catalog", str(EXTENDED_CATALOG), "--data-root", str(data_root), "--manifest", str(manifest),
    ], cwd=REPO_ROOT)
    result = {"profile": profile, "source_manifest": str(manifest), "source_revision": source_revision}
    if source_revision is not None:
        if not re.fullmatch(r"[0-9a-fA-F]{40}", source_revision):
            raise ValueError("source_revision must be exact 40-hex commit SHA")
        readiness = evidence / "runner-readiness.json"
        run([
            sys.executable, str(REPO_ROOT / "tools/runner_preflight.py"),
            "--role", "audio-validation", "--source-revision", source_revision,
            "--data-root", str(data_root), "--extended-catalog", str(EXTENDED_CATALOG),
            "--require-command", "ffmpeg", "--writable-path", str(REPO_ROOT),
            "--output", str(readiness),
        ], cwd=REPO_ROOT)
        result["runner_readiness"] = str(readiness)
    return result


def target_readiness(source_revision: str, board: Path, power_input: str | None, output: Path) -> None:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", source_revision):
        raise ValueError("source_revision must be exact 40-hex commit SHA")
    run([
        sys.executable, str(REPO_ROOT / "tools/hil_board.py"), "preflight",
        "--board", str(board), "--output", str(output.with_name("board-preflight.json")),
    ], cwd=REPO_ROOT)
    args = [
        sys.executable, str(REPO_ROOT / "tools/runner_preflight.py"),
        "--role", "audio-target", "--source-revision", source_revision,
        "--board-manifest", str(board), "--require-command", "cmake", "--require-command", "cc",
        "--writable-path", "/tmp", "--output", str(output),
    ]
    if power_input:
        args += ["--power-input", power_input]
    run(args, cwd=REPO_ROOT)


def dispatch_validation(source_revision: str, profile: str, data_root: Path | None, repo: str) -> None:
    require_command("gh")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", source_revision):
        raise ValueError("source_revision must be exact 40-hex commit SHA")
    run([
        "gh", "workflow", "run", "validation-extended-real.yml", "--repo", repo, "--ref", "main",
        "-f", f"source_sha={source_revision.lower()}", "-f", f"profile={profile}",
        "-f", f"data_root={data_root if data_root is not None else ''}", "-f", "limit_per_dataset=48",
        "-f", "direct_limit=24", "-f", "derived_limit=16", "-f", "holdout_percent=20",
    ])


def dispatch_hil(source_revision: str, repo: str, board: Path | None, capture: str, playback: str,
                 farend: str, power: str, tier: str) -> None:
    require_command("gh")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", source_revision):
        raise ValueError("source_revision must be exact 40-hex commit SHA")
    run([
        "gh", "workflow", "run", "hil-soak.yml", "--repo", repo, "--ref", "main",
        "-f", f"source_sha={source_revision.lower()}", "-f", f"tier={tier}",
        "-f", f"board_manifest={board if board is not None else ''}", "-f", f"capture_device={capture}",
        "-f", f"playback_device={playback}", "-f", f"farend_file={farend}",
        "-f", "sample_rate=16000", "-f", "mic_channels=2", "-f", "dsp_cpu=1",
        "-f", f"power_input={power}", "-f", "power_scale=1000000",
    ])


def self_test() -> None:
    catalog = load_json(DEFAULT_LOCK)
    validate_catalog(catalog)
    by_id = catalog_index(catalog)
    assert by_id["realman"]["revision"] == "12b6f7979e4e5efad4e1004280cf7419201ce209"
    assert by_id["musan"]["integrity"]["value"] == "0c472d4fc0c5141eca47ad1ffeb2a7df"
    assert by_id["openslr-slr31"]["integrity"]["value"] == "6d7ab67ac6a1d2c993d050e16d61080d"
    assert {by_id[item]["provider"] for item in catalog["profiles"]["commercial-core"]} <= {"http_archive", "huggingface_snapshot"}
    fake_home = Path("/tmp/audio-pipeline-selftest-home")
    resolved = resolve_user_paths({}, fake_home)
    assert resolved[5] == fake_home / "audio-validation-extended"
    assert resolved[6] == fake_home / ".cache/audio-pipeline-lab/datasets"
    assert resolved[7] == fake_home / ".local/state/audio-pipeline-lab"
    assert resolved[8] == fake_home / ".config/audio-pipeline/board.json"
    xdg = resolve_user_paths({
        "XDG_DATA_HOME": "/mnt/ap-xdg-data",
        "XDG_CACHE_HOME": "/mnt/ap-xdg-cache",
        "XDG_STATE_HOME": "/mnt/ap-xdg-state",
        "XDG_CONFIG_HOME": "/mnt/ap-xdg-config",
    }, fake_home)
    assert xdg[1] == Path("/mnt/ap-xdg-data")
    assert xdg[6] == Path("/mnt/ap-xdg-cache/audio-pipeline-lab/datasets")
    assert xdg[7] == Path("/mnt/ap-xdg-state/audio-pipeline-lab")
    assert xdg[8] == Path("/mnt/ap-xdg-config/audio-pipeline/board.json")
    explicit = resolve_user_paths({
        "AUDIO_PIPELINE_LAB_DATA_ROOT": "/data/ap-real",
        "AUDIO_PIPELINE_LAB_CACHE_ROOT": "/data/ap-cache",
        "AUDIO_PIPELINE_LAB_STATE_ROOT": "/data/ap-state",
        "AUDIO_PIPELINE_LAB_BOARD": "/data/ap-config/board.json",
    }, fake_home)
    assert explicit[5:] == (Path("/data/ap-real"), Path("/data/ap-cache"), Path("/data/ap-state"), Path("/data/ap-config/board.json"))
    for current in (DEFAULT_DATA_ROOT, DEFAULT_CACHE_ROOT, DEFAULT_STATE_ROOT, DEFAULT_BOARD):
        assert current.is_absolute()
    dispatch_validation_args = parser().parse_args(["dispatch-validation", "--source-revision", "0" * 40])
    assert dispatch_validation_args.data_root is None
    dispatch_hil_args = parser().parse_args(["dispatch-hil", "--source-revision", "0" * 40, "--capture", "hw:0,0"])
    assert dispatch_hil_args.board is None
    site = (REPO_ROOT / "lab/ansible/site.yml").read_text(encoding="utf-8")
    inventory = (REPO_ROOT / "lab/ansible/inventory.example.yml").read_text(encoding="utf-8")
    runner_role = (REPO_ROOT / "lab/ansible/roles/github_runner/tasks/main.yml").read_text(encoding="utf-8")
    assert "lab_system_mode: false" in inventory
    assert "become: true\n  roles:" not in site
    assert "systemctl --user" in runner_role and "loginctl enable-linger" in runner_role
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        archive = root / "ok.tar"
        source = root / "source"
        source.mkdir()
        (source / "fixture.txt").write_text("fixture\n", encoding="utf-8")
        with tarfile.open(archive, "w") as handle:
            handle.add(source / "fixture.txt", arcname="fixture.txt")
        out = root / "out"
        safe_extract_tar(archive, out)
        assert (out / "fixture.txt").read_text(encoding="utf-8") == "fixture\n"
    print("audio laboratory controller self-test: OK")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="labctl.py")
    p.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test")
    sub.add_parser("validate-catalog")
    plan = sub.add_parser("plan")
    plan.add_argument("--profile", choices=sorted(COMMERCIAL_PROFILES), required=True)
    mat = sub.add_parser("materialize")
    mat.add_argument("--profile", choices=sorted(COMMERCIAL_PROFILES), required=True)
    mat.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    mat.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    mat.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    mat.add_argument("--force", action="store_true")
    mat.add_argument("--skip-operator", action="store_true")
    adopt = sub.add_parser("adopt")
    adopt.add_argument("--dataset", required=True)
    adopt.add_argument("--source", type=Path, required=True)
    adopt.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    adopt.add_argument("--delete", action="store_true")
    verify = sub.add_parser("verify-profile")
    verify.add_argument("--profile", choices=sorted(COMMERCIAL_PROFILES), required=True)
    verify.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    verify.add_argument("--state-root", type=Path, default=DEFAULT_STATE_ROOT)
    verify.add_argument("--limit-per-dataset", type=int, default=48)
    verify.add_argument("--source-revision")
    target = sub.add_parser("target-readiness")
    target.add_argument("--source-revision", required=True)
    target.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    target.add_argument("--power-input")
    target.add_argument("--output", type=Path, default=DEFAULT_STATE_ROOT / "readiness/audio-target/runner-readiness.json")
    dv = sub.add_parser("dispatch-validation")
    dv.add_argument("--source-revision", required=True)
    dv.add_argument("--profile", choices=sorted(COMMERCIAL_PROFILES), default="commercial-core")
    dv.add_argument("--data-root", type=Path)
    dv.add_argument("--repo", default="jiying2007/audio-pipeline")
    dh = sub.add_parser("dispatch-hil")
    dh.add_argument("--source-revision", required=True)
    dh.add_argument("--repo", default="jiying2007/audio-pipeline")
    dh.add_argument("--board", type=Path)
    dh.add_argument("--capture", required=True)
    dh.add_argument("--playback", default="none")
    dh.add_argument("--farend", default="")
    dh.add_argument("--power", default="")
    dh.add_argument("--tier", choices=["accelerated-pr", "nightly-1h", "release-8h", "weekly-24h", "certification-72h"], default="accelerated-pr")
    return p


def main() -> int:
    args = parser().parse_args()
    if args.command == "self-test":
        self_test()
        return 0
    catalog = load_json(args.lock)
    validate_catalog(catalog)
    if args.command == "validate-catalog":
        print(json.dumps({"catalog_id": catalog["catalog_id"], "datasets": len(catalog["datasets"]), "profiles": catalog["profiles"]}, sort_keys=True))
    elif args.command == "plan":
        by_id = catalog_index(catalog)
        plan = [{"id": item, "provider": by_id[item]["provider"], "local_path": by_id[item]["local_path"], "license": by_id[item]["license"]} for item in catalog["profiles"][args.profile]]
        print(json.dumps({"profile": args.profile, "datasets": plan}, indent=2, sort_keys=True))
    elif args.command == "materialize":
        materialize_profile(catalog, args.profile, args.data_root, args.cache_root, args.state_root, args.force, args.skip_operator)
    elif args.command == "adopt":
        adopt_dataset(catalog, args.dataset, args.source, args.data_root, args.delete)
    elif args.command == "verify-profile":
        print(json.dumps(verify_profile(args.profile, args.data_root, args.state_root, args.limit_per_dataset, args.source_revision), indent=2, sort_keys=True))
    elif args.command == "target-readiness":
        target_readiness(args.source_revision, args.board, args.power_input, args.output)
    elif args.command == "dispatch-validation":
        dispatch_validation(args.source_revision, args.profile, args.data_root, args.repo)
    elif args.command == "dispatch-hil":
        dispatch_hil(args.source_revision, args.repo, args.board, args.capture, args.playback, args.farend, args.power, args.tier)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
