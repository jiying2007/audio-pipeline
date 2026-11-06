#!/usr/bin/env python3
"""Bounded Mandarin reference asset acquisition; never performs model inference.

The source lock is reviewed separately before execution. Large assets stay out
of Git. No unpinned pip resolution, upstream scripts, or bundled test WAVs run.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import sys
import tarfile
import time
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "docs/research/frontend-evolution-v1/mandarin-downstream-v1-source-lock.json"
WENET = "be6ad97fdb512589df113042f7ff3a29d392fb38"
BUDGET = 300.0
KWS_PREFIX = "sherpa-onnx-kws-zipformer-zh-en-3M-2025-12-20"
VOSK_PREFIX = "vosk-model-small-cn-0.22"
KWS_MEMBERS = (
    "encoder-epoch-13-avg-2-chunk-8-left-64.int8.onnx",
    "decoder-epoch-13-avg-2-chunk-8-left-64.onnx",
    "joiner-epoch-13-avg-2-chunk-8-left-64.int8.onnx",
    "tokens.txt",
)

# Exact wheel hashes were read from the publisher's version-specific PyPI
# metadata before acquisition. The Vosk Python package itself is not imported.
WHEELS = [
    {
        "id": "sherpa-onnx", "version": "1.13.4",
        "filename": "sherpa_onnx-1.13.4-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
        "url": "https://files.pythonhosted.org/packages/cc/b1/8dfe5d1d72c92ea1c95db999a95b61bfbb9769f1c569f06e572eda095c52/sherpa_onnx-1.13.4-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
        "bytes": 4358555,
        "sha256": "5f0158f3513d3adab1ebba0c26f0c815e53ba13b96846d92ef095ae25d648860",
    },
    {
        "id": "sherpa-onnx-core", "version": "1.13.4",
        "filename": "sherpa_onnx_core-1.13.4-py3-none-manylinux2014_x86_64.whl",
        "url": "https://files.pythonhosted.org/packages/41/be/38c57721d71ee74d984b1ca21720a8ca8477d6d341026af24ff658866ef9/sherpa_onnx_core-1.13.4-py3-none-manylinux2014_x86_64.whl",
        "bytes": 10338839,
        "sha256": "367aa06cee90b3fd7959d4e071d6fc821710b859af399b4987e5c3119ee6ae2a",
    },
    {
        "id": "numpy", "version": "2.3.3",
        "filename": "numpy-2.3.3-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl",
        "url": "https://files.pythonhosted.org/packages/51/64/7de3c91e821a2debf77c92962ea3fe6ac2bc45d0778c1cbe15d4fce2fd94/numpy-2.3.3-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl",
        "bytes": 16641643,
        "sha256": "d9192da52b9745f7f0766531dcfa978b7763916f158bb63bdb8a1eca0068ab20",
    },
    {
        "id": "vosk", "version": "0.3.45",
        "filename": "vosk-0.3.45-py3-none-manylinux_2_12_x86_64.manylinux2010_x86_64.whl",
        "url": "https://files.pythonhosted.org/packages/fc/ca/83398cfcd557360a3d7b2d732aee1c5f6999f68618d1645f38d53e14c9ff/vosk-0.3.45-py3-none-manylinux_2_12_x86_64.manylinux2010_x86_64.whl",
        "bytes": 7173758,
        "sha256": "25e025093c4399d7278f543568ed8cc5460ac3a4bf48c23673ace1e25d26619f",
    },
]

ASSETS = [
    {"id": "vosk-model", "filename": VOSK_PREFIX + ".zip",
     "url": "https://alphacephei.com/vosk/models/" + VOSK_PREFIX + ".zip",
     "bytes": 43898754},
    {"id": "kws-model", "filename": KWS_PREFIX + ".tar.bz2",
     "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/" + KWS_PREFIX + ".tar.bz2",
     "bytes": 32885699,
     "sha256": "68447f4fbc67e70eee3a93961f36e81e98f47aef73ce7e7ca00885c6cd3616a6"},
    {"id": "aishell-wav", "filename": "aishell-BAC009S0724W0121.wav",
     "url": "https://raw.githubusercontent.com/wenet-e2e/wenet/" + WENET + "/test/resources/aishell-BAC009S0724W0121.wav",
     "bytes": 137036, "git_blob_sha1": "0f1d46b3ed59c86f6a77dbeaecbb4c8ffa147b83"},
    {"id": "transcript", "filename": "wenet-transcript.txt",
     "url": "https://raw.githubusercontent.com/wenet-e2e/wenet/" + WENET + "/test/resources/dataset/text",
     "bytes": 279, "git_blob_sha1": "1b791e967e38202b77e9429977d29ce976a8719e"},
    {"id": "wenet-license", "filename": "wenet-LICENSE.txt",
     "url": "https://raw.githubusercontent.com/wenet-e2e/wenet/" + WENET + "/LICENSE",
     "max_bytes": 30000},
    {"id": "vosk-model-license-page", "filename": "vosk-models.html",
     "url": "https://alphacephei.com/vosk/models", "max_bytes": 2000000},
    {"id": "kws-license-comments", "filename": "sherpa-3802-comments.json",
     "url": "https://api.github.com/repos/k2-fsa/sherpa-onnx/issues/3802/comments?per_page=100",
     "max_bytes": 2000000},
    {"id": "aishell-license-page", "filename": "openslr33.html",
     "url": "https://www.openslr.org/33/", "max_bytes": 1000000},
    {"id": "vosk-code-license", "filename": "vosk-COPYING.txt",
     "url": "https://raw.githubusercontent.com/alphacep/vosk-api/cf2560c9f8a49d3d366b433fdabd78c518231bec/COPYING",
     "max_bytes": 30000},
    {"id": "vosk-c-api-header", "filename": "vosk_api.h",
     "url": "https://raw.githubusercontent.com/alphacep/vosk-api/cf2560c9f8a49d3d366b433fdabd78c518231bec/src/vosk_api.h",
     "max_bytes": 100000},
]


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                   indent=2, allow_nan=False) + "\n", encoding="utf-8")


def safe_member(name):
    p = PurePosixPath(name)
    require(not p.is_absolute() and ".." not in p.parts and "\\" not in name
            and p.parts and not any(":" in part for part in p.parts), "unsafe archive member")
    return p


def download(asset, folder, expected=None):
    """One bounded attempt at one fixed URL; no silently re-used partial body."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / asset["filename"]
    require(not path.exists(), "acquisition output already exists: " + str(path))
    started, start_time = time.monotonic(), utc()
    receipt = {"asset": asset["id"], "url": asset["url"], "started_at": start_time,
               "budget_seconds": BUDGET, "attempt": 1}
    maximum = asset.get("bytes", asset.get("max_bytes", 100000000))
    try:
        request = urllib.request.Request(asset["url"], headers={"User-Agent": "audio-pipeline-mandarin-source-v1"})
        with urllib.request.urlopen(request, timeout=30) as response, path.open("xb") as out:
            require(response.status == 200, "asset HTTP status")
            receipt["response_host"] = urllib.parse.urlparse(response.url).hostname
            count = 0
            while True:
                block = response.read(1 << 20)
                if not block:
                    break
                out.write(block)
                count += len(block)
                require(count <= maximum, "asset exceeds fixed size bound")
                require(time.monotonic() - started < BUDGET, "asset acquisition budget exceeded")
        if "bytes" in asset:
            require(path.stat().st_size == asset["bytes"], "asset byte count mismatch")
        actual = digest(path)
        if "sha256" in asset:
            require(actual == asset["sha256"], "publisher asset digest mismatch")
        if expected is not None:
            require(actual == expected["sha256"] and path.stat().st_size == expected["bytes"], "frozen asset drift")
        if "git_blob_sha1" in asset:
            content = path.read_bytes()
            git_sha = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
            require(git_sha == asset["git_blob_sha1"], "fixed Git blob mismatch")
            receipt["git_blob_sha1"] = git_sha
        receipt.update({"status": "PASS", "exit_code": 0, "bytes": path.stat().st_size, "sha256": actual})
    except Exception as exc:
        receipt.update({"status": "FAIL", "exit_code": 1,
                        "error": type(exc).__name__ + ": " + str(exc),
                        "partial_bytes": path.stat().st_size if path.exists() else 0})
        raise
    finally:
        receipt.update({"ended_at": utc(), "elapsed_seconds": time.monotonic() - started})
        write_json(folder / (asset["filename"] + ".acquisition.json"), receipt)
    require(receipt["elapsed_seconds"] <= BUDGET, "asset acquisition final budget exceeded")
    return receipt


def write_member(root, name, content):
    p = safe_member(name)
    path = root.joinpath(*p.parts)
    if path.exists():
        require(path.is_file() and path.read_bytes() == content, "conflicting wheel member")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def extract_zip(path, destination, limit):
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        require(len(infos) <= 10000 and len({m.filename for m in infos}) == len(infos), "duplicate/excess zip members")
        require(sum(m.file_size for m in infos) <= limit, "zip expansion bound")
        for member in infos:
            safe_member(member.filename)
            mode = member.external_attr >> 16
            require(not stat.S_ISLNK(mode), "zip symlink not permitted")
            require(not member.flag_bits & 1, "encrypted zip not permitted")
            if not member.is_dir():
                require(not member.filename.endswith(".pth"), "automatic Python startup hook not permitted")
                write_member(destination, member.filename, z.read(member))


def file_inventory(root):
    members = sorted(root.rglob("*"))
    require(all(not p.is_symlink() for p in members), "materialized source symlink")
    return {p.relative_to(root).as_posix(): {"sha256": digest(p), "bytes": p.stat().st_size}
            for p in members if p.is_file()}


def materialize(root):
    """Unpack reviewed files without importing a third-party Python module."""
    started, start_time = time.monotonic(), utc()
    receipt = {"started_at": start_time, "budget_seconds": BUDGET, "inference_performed": False}
    try:
        models = root / "models"
        runtime = root / "runtime"
        require(not models.exists() and not runtime.exists(), "materialization output must be fresh")
        models.mkdir()
        runtime.mkdir()
        extract_zip(root / "assets" / (VOSK_PREFIX + ".zip"), models, 200000000)
        require((models / VOSK_PREFIX / "am/final.mdl").is_file(), "missing Vosk acoustic model")
        with tarfile.open(root / "assets" / (KWS_PREFIX + ".tar.bz2"), "r:bz2") as archive:
            members = archive.getmembers()
            require(len(members) <= 10000 and len({m.name for m in members}) == len(members), "duplicate/excess tar members")
            by_name = {m.name: m for m in members}
            for member in members:
                safe_member(member.name)
                require(member.isdir() or member.isreg(), "tar special/link member")
            for name in KWS_MEMBERS:
                member = by_name[KWS_PREFIX + "/" + name]
                require(member.isreg() and 0 < member.size < 20000000, "KWS model member bound")
                write_member(models, member.name, archive.extractfile(member).read())
        for wheel in WHEELS:
            path = root / "wheels" / wheel["filename"]
            require(digest(path) == wheel["sha256"], "wheel hash changed before install")
            extract_zip(path, runtime, 300000000)
            require(time.monotonic() - started < BUDGET, "runtime installation budget exceeded")
        # A wheel-only prefix needs no resolver or executable setup.py. Its
        # top-level packages and bundled .libs directories retain their layout.
        require((runtime / "vosk/libvosk.so").is_file(), "Vosk C API library absent")
        require((runtime / "sherpa_onnx").is_dir() and (runtime / "numpy").is_dir(), "runtime packages absent")
        tokens = {line.split()[0] for line in (models / KWS_PREFIX / "tokens.txt").read_text().splitlines() if line.split()}
        require(set(("g", "uǎng", "zh", "ōu", "sh", "ì")).issubset(tokens), "frozen keyword phones missing")
        receipt.update({"status": "PASS", "exit_code": 0,
                        "model_files": file_inventory(models), "runtime_files": file_inventory(runtime)})
    except Exception as exc:
        receipt.update({"status": "FAIL", "exit_code": 1, "error": type(exc).__name__ + ": " + str(exc)})
        raise
    finally:
        receipt.update({"ended_at": utc(), "elapsed_seconds": time.monotonic() - started})
        write_json(root / "materialization.json", receipt)
    require(receipt["elapsed_seconds"] <= BUDGET, "runtime installation final budget exceeded")
    return receipt


def acquire(root, lock_path=None):
    require(sys.version_info[:2] == (3, 12) and platform.machine() == "x86_64" and sys.platform == "linux",
            "frozen runtime requires CPython 3.12 Linux x86_64")
    require(not root.exists(), "source root must be fresh")
    root.mkdir(parents=True)
    lock = json.loads(lock_path.read_text()) if lock_path else None
    frozen = {x["id"]: x for x in lock["assets"]} if lock else {}
    rows = []
    for asset in ASSETS + WHEELS:
        # Mutable rights snapshots are retained from the reviewed lock, never
        # used to silently grant changed rights during a replay.
        if lock and asset["id"].endswith(("-page", "-comments")):
            continue
        receipt = download(asset, root / ("wheels" if asset in WHEELS else "assets"), frozen.get(asset["id"]))
        rows.append({**asset, "sha256": receipt["sha256"], "bytes": receipt["bytes"]})
    transcript = (root / "assets/wenet-transcript.txt").read_text(encoding="utf-8")
    wanted = "test/resources/dataset/aishell-BAC009S0724W0121 广州市房地产中介协会分析"
    require(wanted in transcript.splitlines(), "external fixed Mandarin transcript changed")
    result = materialize(root)
    candidate = {"schema_version": 1, "experiment": "FE-C2-MANDARIN-DOWNSTREAM-V1",
                 "status": "SOURCE_ONLY_NOT_INFERENCE", "wenet_revision": WENET,
                 "assets": rows, "model_files": result["model_files"],
                 "runtime_files": result["runtime_files"], "runtime_python": "3.12",
                 "reference_text": "广州市房地产中介协会分析", "source_role": "disclosed-integration-smoke"}
    if lock:
        require(candidate["model_files"] == lock["model_files"], "frozen model extraction changed")
        require(candidate["runtime_files"] == lock["runtime_files"], "frozen runtime extraction changed")
    write_json(root / "source-candidate.json", candidate)
    return candidate


def verify(root, lock_path=LOCK):
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    require(lock["status"] == "ADMITTED_HOST_REFERENCE_SOURCE_ONLY", "source not admitted")
    for asset in lock["assets"]:
        if asset["id"].endswith(("-page", "-comments")) and not (root / "assets" / asset["filename"]).exists():
            continue  # replay uses the hash-bound reviewed rights in the lock
        path = root / ("wheels" if asset["id"] in {w["id"] for w in WHEELS} else "assets") / asset["filename"]
        require(path.is_file() and not path.is_symlink() and path.stat().st_size == asset["bytes"]
                and digest(path) == asset["sha256"], "asset mismatch: " + asset["id"])
    require(file_inventory(root / "models") == lock["model_files"], "model membership or bytes changed")
    require(file_inventory(root / "runtime") == lock["runtime_files"], "runtime membership or bytes changed")
    return lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    value = verify(args.root, args.lock or LOCK) if args.verify else acquire(args.root, args.lock)
    print(json.dumps({"status": value["status"], "model_files": len(value["model_files"]),
                      "runtime_files": len(value["runtime_files"]), "inference_performed": False}, sort_keys=True))


if __name__ == "__main__":
    main()
