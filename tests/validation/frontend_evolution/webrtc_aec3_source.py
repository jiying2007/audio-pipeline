#!/usr/bin/env python3
"""Fixed freedesktop WebRTC source admission/build; no audio or training runs.

Archives are supplied locally. No fetch, install, patch search, or implicit wrap
download is performed. Source admission uses the existing research catalog.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import time
import zipfile

from contracts import ROOT, admit_execution, load_json, require, sha256

REGISTRY = ROOT / ".github/research/frontend-evolution-v1"
LOCK = REGISTRY / "webrtc-aec3-source-lock.json"
ADMISSION = REGISTRY / "webrtc-aec3-admission.json"
CATALOG = REGISTRY / "sources.json"
CONTRACTS = Path(__file__).resolve().with_name("contracts.py")
SCOPE = "fixed-freedesktop-2.1-build-bounded-synthetic-and-separately-preregistered-disclosed-reference-only"


def encoded(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def safe_path(path: Path) -> Path:
    path = Path(os.path.abspath(str(path)))
    require(all(not p.is_symlink() for p in (path,) + tuple(path.parents)), "symlink path forbidden")
    return path


def separate(a: Path, b: Path) -> bool:
    return a != b and a not in b.parents and b not in a.parents


def file_record(data: bytes, executable: bool) -> dict:
    return {"size": len(data), "sha256": sha256(data),
            "git_blob_sha1": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest(),
            "mode": "100755" if executable else "100644"}


def git_tree(manifest: dict) -> str:
    tree = {}
    for name, record in manifest.items():
        parts = name.split("/")
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        require(parts[-1] not in node, "file/directory collision")
        node[parts[-1]] = (record["mode"], record["git_blob_sha1"])

    def digest(node: dict) -> bytes:
        body = b""
        for name, item in sorted(node.items(), key=lambda kv: kv[0].encode() + (b"/" if isinstance(kv[1], dict) else b"")):
            mode, value = ("40000", digest(item)) if isinstance(item, dict) else (item[0], bytes.fromhex(item[1]))
            body += mode.encode() + b" " + name.encode() + b"\0" + value
        return hashlib.sha1(b"tree " + str(len(body)).encode() + b"\0" + body).digest()
    return digest(tree).hex()


def member_name(name: str, root: str, directory: bool) -> str:
    require(isinstance(name, str) and name and "\\" not in name and not any(ord(x) < 32 or ord(x) == 127 for x in name),
            "unsafe archive path")
    clean = name[:-1] if directory and name.endswith("/") else name
    parts = clean.split("/")
    require(parts[0] == root and all(p and p not in (".", "..") and ":" not in p for p in parts),
            "unsafe archive path or wrong root")
    require(directory or len(parts) > 1, "archive root must be a directory")
    return "/".join(parts[1:])


def read_archive(path: Path, spec: dict) -> dict:
    """Validate all members before writing any; fixed bounds include directories."""
    path = safe_path(path)
    require(path.is_file() and path.stat().st_size == spec["size"], "archive missing or size mismatch")
    data = path.read_bytes()
    require(sha256(data) == spec["sha256"], "archive SHA256 mismatch")
    entries = []
    if spec["format"] == "tar":
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
            for entry in archive:
                require(len(entries) < spec["members"], "archive member bound exceeded")
                require(entry.isdir() or entry.isfile(), "archive link/special member forbidden")
                require(not entry.mode & 0o7000, "archive special permission forbidden")
                name = member_name(entry.name, spec["root"], entry.isdir())
                require(entry.size <= spec["max_file_size"], "archive member size bound exceeded")
                require(not entry.isdir() or entry.size == 0, "directory payload forbidden")
                payload = b"" if entry.isdir() else archive.extractfile(entry).read(spec["max_file_size"] + 1)
                require(entry.isdir() or len(payload) == entry.size, "archive member size mismatch")
                entries.append((name, entry.isdir(), payload, bool(entry.mode & 0o111)))
    else:
        require(spec["format"] == "zip", "unsupported archive format")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            require(len(archive.infolist()) <= spec["members"], "archive member bound exceeded")
            for entry in archive.infolist():
                mode = entry.external_attr >> 16
                require(stat.S_IFMT(mode) in (0, stat.S_IFDIR, stat.S_IFREG), "archive link/special member forbidden")
                require(stat.S_IFMT(mode) == 0 or stat.S_ISDIR(mode) == entry.is_dir(), "archive member type mismatch")
                require(not mode & 0o7000 and not entry.flag_bits & 1, "archive permission/encryption forbidden")
                name = member_name(entry.filename, spec["root"], entry.is_dir())
                require(entry.file_size <= spec["max_file_size"], "archive member size bound exceeded")
                payload = b"" if entry.is_dir() else archive.read(entry)
                require(len(payload) == entry.file_size, "archive member size mismatch")
                entries.append((name, entry.is_dir(), payload, bool(mode & 0o111)))
    require(len(entries) == spec["members"], "archive member count mismatch")
    require(len({x[0] for x in entries}) == len(entries), "duplicate archive path")
    files = {name: (data, executable) for name, directory, data, executable in entries if not directory}
    for name, directory, _, _ in entries:
        require(not any("/".join(name.split("/")[:n]) in files for n in range(1, len(name.split("/")))),
                "archive file/directory collision")
    manifest = {name: file_record(data, executable) for name, (data, executable) in files.items()}
    require(len(files) == spec["files"] and sum(r["size"] for r in manifest.values()) == spec["unpacked_size"],
            "archive file count/size mismatch")
    require(sha256(encoded(manifest)) == spec["files_manifest_sha256"], "archive file manifest mismatch")
    require(git_tree(manifest) == spec["git_tree"], "archive Git tree mismatch")
    return files


def scan_source(source: Path, lock: dict) -> dict:
    require(safe_path(source).is_dir(), "missing source directory")
    manifest = {}
    limits = list(lock["archives"].values())
    max_files = sum(item["files"] for item in limits)
    max_bytes = sum(item["unpacked_size"] for item in limits)
    max_file_size = max(item["max_file_size"] for item in limits)
    max_directories = sum(item["members"] for item in limits)
    directories = set()
    total = 0
    for directory, dirs, files in os.walk(source, followlinks=False):
        for name in dirs:
            child = Path(directory) / name
            require(not child.is_symlink(), "source symlink forbidden")
            directories.add(child.relative_to(source).as_posix())
            require(len(directories) <= max_directories, "source directory bound exceeded")
        for name in files:
            path = Path(directory) / name
            info = path.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "source link/special file forbidden")
            total += info.st_size
            require(len(manifest) < max_files and total <= max_bytes and info.st_size <= max_file_size,
                    "source file/size bound exceeded")
            manifest[path.relative_to(source).as_posix()] = file_record(path.read_bytes(), bool(info.st_mode & 0o111))
    expected_dirs = {"/".join(name.split("/")[:n]) for name in manifest for n in range(1, len(name.split("/")))}
    require(directories == expected_dirs, "source directory set drift")
    return manifest


def receipt_for(lock: dict, manifest: dict) -> dict:
    return {"schema_version": 1, "source_id": "webrtc", "scope": SCOPE,
            "status": "SOURCE_BYTES_VERIFIED_NOT_BUILT", "shipping_authority": False,
            "acoustic_measurement": "NOT_RUN", "training": "NOT_RUN",
            "source_lock_sha256": sha256(LOCK.read_bytes()),
            "distribution_commit": lock["distribution_commit"], "distribution_tree": lock["distribution_tree"],
            "archives": {k: {f: v[f] for f in ("filename", "size", "sha256")} for k, v in lock["archives"].items()},
            "files": len(manifest), "unpacked_size": sum(v["size"] for v in manifest.values()),
            "materialized_source_sha256": sha256(encoded(manifest))}


def verify(prepared: Path) -> dict:
    prepared = safe_path(prepared)
    lock = load_json(LOCK)
    require(prepared.is_dir() and {p.name for p in prepared.iterdir()} == {"source", "files.json", "source-receipt.json"},
            "prepared root file set mismatch")
    for name in ("files.json", "source-receipt.json"):
        require(safe_path(prepared / name).is_file(), "missing source metadata")
        require((prepared / name).stat().st_nlink == 1 and (prepared / name).stat().st_size <=
                (sum(v["files"] for v in lock["archives"].values()) * 512 if name == "files.json" else 32768),
                "invalid source metadata size/link")
    manifest = scan_source(prepared / "source", lock)
    require(sha256(encoded(manifest)) == lock["materialized_source_sha256"], "prepared source byte/mode/file set drift")
    require(load_json(prepared / "files.json") == manifest, "source file manifest drift")
    receipt = receipt_for(lock, manifest)
    require(load_json(prepared / "source-receipt.json") == receipt, "source receipt drift")
    return receipt


def preflight(archives_dir: Path, output: Path) -> dict:
    archives_dir, output = safe_path(archives_dir), safe_path(output)
    require(not output.exists() and separate(output, archives_dir), "fresh disjoint output required")
    lock = load_json(LOCK)
    all_files = {}
    for name, spec in lock["archives"].items():
        files = read_archive(archives_dir / spec["filename"], spec)
        for relative, value in files.items():
            target = spec["destination"] + relative
            require(target not in all_files, "archive overlay would overwrite a file")
            all_files[target] = value
    manifest = {name: file_record(data, executable) for name, (data, executable) in all_files.items()}
    require(sha256(encoded(manifest)) == lock["materialized_source_sha256"], "prepared source manifest mismatch")
    output.mkdir(parents=True)
    for name, (data, executable) in all_files.items():
        target = output / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(data)
        target.chmod(0o755 if executable else 0o644)
    write_json(output / "files.json", manifest)
    write_json(output / "source-receipt.json", receipt_for(lock, manifest))
    return verify(output)


def admitted(prepared: Path) -> dict:
    receipt = verify(prepared)
    source = admit_execution(load_json(CATALOG), "webrtc")
    review = load_json(ADMISSION)
    require(source["scope"] == SCOPE and review["scope"] == SCOPE, "source scope drift")
    require(source["admission_receipt_path"] == ADMISSION.relative_to(ROOT).as_posix(), "wrong admission receipt")
    require(source["admission_receipt_sha256"] == sha256(ADMISSION.read_bytes()), "admission receipt hash mismatch")
    require(review["decision"] == "EXECUTION_ADMITTED_FIXED_REFERENCE_ONLY" and review["shipping_authority"] is False,
            "reference admission required")
    require(source["commit"] == review["distribution_commit"] == receipt["distribution_commit"], "admission commit mismatch")
    require(review["distribution_tree"] == receipt["distribution_tree"], "admission tree mismatch")
    require(review["source_lock_sha256"] == receipt["source_lock_sha256"], "admission source lock mismatch")
    require(source["materialized_source_sha256"] == review["materialized_source_sha256"] == receipt["materialized_source_sha256"],
            "admission materialized source mismatch")
    require(source["rights"] == review["rights"], "admission rights mismatch")
    return receipt


def build_plan(prepared: Path, build_dir: Path, meson: str) -> dict:
    receipt = admitted(prepared)
    prepared, build_dir = safe_path(prepared), safe_path(build_dir)
    require(not build_dir.exists() and separate(prepared, build_dir) and separate(ROOT, build_dir),
            "fresh build directory outside repository and prepared source required")
    contract = load_json(LOCK)["build_contract"]
    require(type(contract["wall_seconds"]) is int and 0 < contract["wall_seconds"] <= 600
            and contract["parallel_jobs"] == 2, "invalid build budget")
    require("--wrap-mode=nodownload" in contract["setup_arguments"]
            and "--force-fallback-for=abseil-cpp" in contract["setup_arguments"], "fixed offline dependency policy required")
    source, binary = prepared / "source", build_dir / "meson"
    return {"schema_version": 1, "status": "BUILD_PLAN_NOT_EXECUTED", "source_receipt": receipt,
            "source_root": str(source), "build_root": str(build_dir), "meson_build_dir": str(binary),
            "wall_seconds": contract["wall_seconds"], "parallel_jobs": contract["parallel_jobs"],
            "setup": [meson, "setup", str(binary), str(source)] + contract["setup_arguments"],
            "compile": [meson, "compile", "-C", str(binary), "--jobs", str(contract["parallel_jobs"]), contract["target"]]}


def committed_controls() -> dict:
    """Do not execute uncommitted admission/source controls, even locally."""
    def git(*args: str) -> bytes:
        return subprocess.check_output(["git", "-C", str(ROOT), *args], stderr=subprocess.PIPE, timeout=10)
    head = git("rev-parse", "HEAD").decode().strip()
    files = {}
    for path in (Path(__file__).resolve(), CONTRACTS, LOCK, ADMISSION, CATALOG):
        relative = path.relative_to(ROOT).as_posix()
        data = path.read_bytes()
        require(git("show", head + ":" + relative) == data, "source/build controls must be committed before build: " + relative)
        files[relative] = sha256(data)
    return {"commit": head, "tree": git("rev-parse", "HEAD^{tree}").decode().strip(), "files_sha256": files}


def run_logged(command: list, path: Path, env: dict, deadline: float) -> int:
    remaining = deadline - time.monotonic()
    require(remaining > 0, "build wall-time budget exhausted")
    with path.open("wb") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
        try:
            return process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise ValueError("build wall-time budget exhausted; process group terminated")


def built_shared_libraries(binary: Path) -> list:
    # Meson also creates libNAME.so.VERSION.p/ for objects; it is not a library.
    libraries = sorted(p for p in binary.rglob("libwebrtc-audio-processing-2.so*")
                       if not p.is_symlink() and p.is_file())
    require(libraries, "missing built WebRTC reference library")
    return libraries


def build(prepared: Path, build_dir: Path, meson: str, ninja: str) -> dict:
    started = time.monotonic()
    plan = build_plan(prepared, build_dir, meson)
    deadline = started + plan["wall_seconds"]
    controls = committed_controls()
    tools = {}
    for name, executable in (("meson", meson), ("ninja", ninja), ("cc", "cc"), ("cxx", "c++"), ("pkg_config", "pkg-config")):
        path = shutil.which(executable)
        require(path is not None, "missing build tool: " + name)
        require(deadline > time.monotonic(), "build wall-time budget exhausted")
        version = subprocess.check_output([path, "--version"], stderr=subprocess.STDOUT,
                                          timeout=min(10, deadline - time.monotonic())).decode().strip()
        tools[name] = {"path": path, "version": version, "sha256": sha256(Path(path).read_bytes())}
    expected = load_json(LOCK)["build_contract"]["tool_versions"]
    require(all(tools[name]["version"] == value for name, value in expected.items()), "build tool version mismatch")
    root = Path(plan["build_root"])
    root.mkdir(parents=True)
    env = {"PATH": os.pathsep.join(dict.fromkeys([str(Path(v["path"]).parent) for v in tools.values()] + [os.defpath])),
           "LC_ALL": "C", "CC": tools["cc"]["path"], "CXX": tools["cxx"]["path"],
           "NINJA": tools["ninja"]["path"], "PKG_CONFIG": tools["pkg_config"]["path"]}
    result = {**plan, "status": "BUILD_FAILED", "controls": controls, "tools": tools,
              "shipping_authority": False, "acoustic_measurement": "NOT_RUN", "training": "NOT_RUN", "steps": []}
    try:
        for phase in ("setup", "compile"):
            code = run_logged(plan[phase], root / (phase + ".log"), env, deadline)
            result["steps"].append({"phase": phase, "exit_code": code})
            require(code == 0, "build " + phase + " failed; inspect retained log")
        result["post_source_verification"] = verify(prepared)
        require(result["post_source_verification"] == plan["source_receipt"], "source changed during build")
        pc_dir = Path(plan["meson_build_dir"]) / "meson-uninstalled"
        pc_module = "webrtc-audio-processing-2-uninstalled"
        pc_env = dict(env, PKG_CONFIG_PATH=str(pc_dir))
        require(deadline > time.monotonic(), "build wall-time budget exhausted")
        cflags = subprocess.check_output([tools["pkg_config"]["path"], "--cflags", pc_module], env=pc_env,
                                        timeout=min(10, deadline - time.monotonic())).decode().strip()
        require(deadline > time.monotonic(), "build wall-time budget exhausted")
        libs = subprocess.check_output([tools["pkg_config"]["path"], "--libs", pc_module], env=pc_env,
                                      timeout=min(10, deadline - time.monotonic())).decode().strip()
        libraries = built_shared_libraries(Path(plan["meson_build_dir"]))
        result["link"] = {"pkgconfig_dir": str(pc_dir), "pkgconfig_module": pc_module,
                          "pkgconfig_sha256": sha256((pc_dir / (pc_module + ".pc")).read_bytes()),
                          "cflags": shlex.split(cflags), "libs": shlex.split(libs),
                          "source_include_dir": str(Path(plan["source_root"]) / "webrtc"),
                          "abseil_include_dir": str(Path(plan["source_root"]) / "subprojects/abseil-cpp-20240722.0"),
                          "runtime_library_dirs": sorted({str(p.parent) for p in libraries}),
                          "libraries": [{"path": str(p), "sha256": sha256(p.read_bytes()), "size": p.stat().st_size} for p in libraries]}
        require(deadline >= time.monotonic(), "build wall-time budget exhausted")
        result["status"] = "BUILT_FIXED_REFERENCE_NO_ACOUSTIC_MEASUREMENT"
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        result["error"] = str(error)
        if "post_source_verification" not in result:
            try:
                result["post_source_verification"] = verify(prepared)
            except (ValueError, OSError, KeyError) as source_error:
                result["post_source_verification_error"] = str(source_error)
        raise
    finally:
        result["elapsed_seconds"] = time.monotonic() - started
        result["logs"] = {p.name: sha256(p.read_bytes()) for p in root.glob("*.log")}
        write_json(root / "build-receipt.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    pre = sub.add_parser("preflight")
    pre.add_argument("--archives-dir", type=Path, required=True)
    pre.add_argument("--output", type=Path, required=True)
    ver = sub.add_parser("verify")
    ver.add_argument("--prepared", type=Path, required=True)
    for name in ("build-plan", "build"):
        item = sub.add_parser(name)
        item.add_argument("--prepared", type=Path, required=True)
        item.add_argument("--build-dir", type=Path, required=True)
        item.add_argument("--meson", default="meson")
        if name == "build":
            item.add_argument("--ninja", default="ninja")
    args = parser.parse_args()
    try:
        if args.command == "preflight":
            result = preflight(args.archives_dir, args.output)
        elif args.command == "verify":
            result = verify(args.prepared)
        elif args.command == "build-plan":
            result = build_plan(args.prepared, args.build_dir, args.meson)
        else:
            result = build(args.prepared, args.build_dir, args.meson, args.ninja)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, tarfile.TarError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        print("webrtc-aec3-source: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
