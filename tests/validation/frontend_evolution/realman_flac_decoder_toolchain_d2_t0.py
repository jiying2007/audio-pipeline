#!/usr/bin/env python3
"""FE03 D2-T0: preregistered native reference FLAC toolchain (no RealMAN audio).

Official source only: xiph/flac@28e4f0528c76b296c561e922ba67d43751990599.
Research-only compiler and synthetic exact-byte qualification.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
UPSTREAM = "https://github.com/xiph/flac.git"
TAG = "1.4.3"
COMMIT = "28e4f0528c76b296c561e922ba67d43751990599"
PASS = "REALMAN_D2_T0_XIPH_FLAC_1_4_3_NATIVE_CLI_TOOLCHAIN_QUALIFIED_SYNTHETIC_ONLY"
BLOCKED = "REALMAN_D2_T0_NATIVE_DECODER_NOT_QUALIFIED"
MAX_SOURCE_BYTES = 128*1024*1024
MAX_BINARY_BYTES = 64*1024*1024
BUILD_FLAGS = (
    "-DCMAKE_BUILD_TYPE=Release", "-DWITH_OGG=OFF",
    "-DBUILD_CXXLIBS=OFF", "-DBUILD_EXAMPLES=OFF",
    "-DBUILD_DOCS=OFF", "-DBUILD_TESTING=OFF",
    "-DBUILD_PROGRAMS=ON", "-DBUILD_SHARED_LIBS=OFF",
    "-DINSTALL_MANPAGES=OFF",
)


class Reject(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def require(test, code="T0_INVALID"):
    if not test:
        raise Reject(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def file_hash(p, limit=MAX_BINARY_BYTES):
    require(p.is_file() and p.stat().st_size <= limit, "T0_FILE_MISSING_OR_TOO_LARGE")
    h = hashlib.sha256()
    count = 0
    with p.open("rb") as src:
        while True:
            chunk = src.read(1<<20)
            if not chunk:
                break
            count += len(chunk)
            require(count <= limit, "T0_FILE_TOO_LARGE")
            h.update(chunk)
    return count, h.hexdigest()


def command(argv, *, cwd=None, timeout=30, code="T0_TOOL_FAILED", env=None):
    require(bool(argv) and all(isinstance(x, str) for x in argv), "T0_ARGUMENTS_INVALID")
    try:
        result = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                check=False, timeout=timeout, env=env)
    except (OSError, subprocess.SubprocessError):
        raise Reject(code) from None
    require(len(result.stdout) <= 2*1024*1024 and result.returncode == 0, code)
    return result.stdout.decode("utf-8", "replace").strip()


def program(name):
    found = shutil.which(name)
    require(found is not None, "T0_BUILD_TOOL_MISSING")
    p = Path(found).resolve()
    require(p.is_file() and
            str(p).startswith(("/usr/bin/", "/bin/", "/usr/local/bin/")),
            "T0_UNTRUSTED_BUILD_TOOL")
    _, checksum = file_hash(p)
    return str(p), checksum


def commit_sha():
    sha = command(["git", "rev-parse", "HEAD"], cwd=ROOT, timeout=5)
    require(sha == os.environ.get("GITHUB_SHA")
            and re.fullmatch(r"[a-f0-9]{40}", sha), "T0_EXECUTION_SHA_MISMATCH")
    return sha


def source_tree_bytes(path, cap=MAX_SOURCE_BYTES):
    count = 0
    for root, dirs, files in os.walk(path, followlinks=False):
        require(not any(Path(root, x).is_symlink() for x in dirs+files),
                "T0_SOURCE_SYMLINK_NOT_ADMITTED")
        for name in files:
            p = Path(root, name)
            count += p.stat().st_size
            require(count <= cap, "T0_SOURCE_SIZE_LIMIT")
    return count


def source_identity(work):
    source = work/"flac-source"
    require(source.is_dir(), "T0_SOURCE_NOT_AVAILABLE")
    sha = command(["git", "rev-parse", "HEAD"], cwd=source, timeout=5)
    require(sha == COMMIT, "T0_SOURCE_COMMIT_DRIFT")
    tree = command(["git", "rev-parse", "HEAD^{tree}"], cwd=source, timeout=5)
    require(bool(re.fullmatch(r"[0-9a-f]{40}", tree)), "T0_SOURCE_TREE_INVALID")
    require(command(["git", "status", "--porcelain", "--untracked-files=all"],
                    cwd=source, timeout=5) == "", "T0_UPSTREAM_SOURCE_DIRTY")
    return {"tag":TAG,"revision":sha,"tree":tree,
            "working_tree_bytes":source_tree_bytes(source)}


def toolchain_identity(work):
    build = work/"build"
    tool = build/"src"/"flac"/"flac"
    size, sha = file_hash(tool)
    version = command([str(tool), "--version"], timeout=5)
    require(version == "flac 1.4.3", "T0_WRONG_REFERENCE_CLI_VERSION")
    return str(tool), {"program":"flac", "native_version":version,
                        "binary_sha256":sha,"binary_bytes":size,
                        "build_target":"flacapp", "output_name":"flac",
                        "cmake_flags":list(BUILD_FLAGS)}


def synthetic_pcm():
    values = [(-32768 if i % 13 == 0 else
               32767 if i % 17 == 0 else
               ((i*7919 + 97) % 65536) - 32768)
              for i in range(257)]
    return struct.pack("<" + "h"*len(values), *values)


def decode_cmd(tool, path):
    return [tool, "--silent", "--decode", "--stdout",
            "--force-raw-format", "--endian=little", "--sign=signed", str(path)]


def synthetic_proof(work, tool, *, prefix):
    raw = synthetic_pcm()
    require(len(raw) == 514 and digest(raw) ==
            digest(synthetic_pcm()), "T0_SYNTHETIC_GENERATION_DRIFT")
    original = work/(prefix+".raw")
    encoded = work/(prefix+".flac")
    damaged = work/(prefix+"-damaged.flac")
    original.write_bytes(raw)
    # Force signed 16-bit little-endian/mono 48kHz input; no DSP.
    command([tool, "--silent", "--force", "--force-raw-format",
             "--endian=little", "--sign=signed", "--channels=1",
             "--bps=16", "--sample-rate=48000", "-o", str(encoded),
             str(original)], timeout=25, code="T0_SYNTHETIC_ENCODE_FAILED")
    require(encoded.stat().st_size < 1024*1024 and
            encoded.open("rb").read(4) == b"fLaC",
            "T0_SYNTHETIC_FORMAT_NOT_FLAC")
    try:
        result = subprocess.run(decode_cmd(tool, encoded),
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=25, check=False)
    except (OSError, subprocess.SubprocessError):
        raise Reject("T0_NATIVE_DECODE_FAILED") from None
    require(result.returncode == 0 and len(result.stdout) == len(raw),
            "T0_SYNTHETIC_RAW_LENGTH_MISMATCH")
    decoded = result.stdout
    require(digest(decoded) == digest(raw)
            and hashlib.md5(decoded).digest() == hashlib.md5(raw).digest()
            and decoded == raw, "T0_SYNTHETIC_PCM_NOT_BIT_EXACT")
    # A damaged original must not be able to masquerade as a complete
    # admitted PCM stream even if a decoder emits partial bytes.
    compressed = encoded.read_bytes()
    require(len(compressed) >= 80, "T0_FLAC_TOO_SHORT_FOR_NEGATIVE")
    damaged.write_bytes(compressed[:len(compressed)//2])
    try:
        neg = subprocess.run(decode_cmd(tool, damaged),
                             stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=25, check=False)
    except (OSError, subprocess.SubprocessError):
        raise Reject("T0_NEGATIVE_TEST_TOOL_ERROR") from None
    require(neg.returncode != 0 or
            len(neg.stdout) != len(raw) or digest(neg.stdout) != digest(raw),
            "T0_TRUNCATED_FLAC_FALSE_ADMISSION")
    # Remove even synthetic audio before returning metadata.
    for p in (original, encoded, damaged):
        p.unlink()
    return {"sample_rate_hz":48000,"channels":1,"bits_per_sample":16,
            "samples":257,"raw_bytes":514,"synthetic_raw_sha256":digest(raw),
            "synthetic_raw_md5":hashlib.md5(raw).hexdigest(),
            "decoded_raw_sha256":digest(decoded),
            "decoded_raw_md5":hashlib.md5(decoded).hexdigest(),
            "raw_bitwise_match":True,"damaged_input_blocked":True,
            "realman_recordings_used":False}


def identity(sha):
    return {
        "schema_version":1,
        "experiment_id":"FE03-A2-D2-T0-XIPH-REFERENCE-FLAC-SYNTHETIC",
        "preregistration":"https://github.com/jiying2007/audio-pipeline/issues/709",
        "source_commit":sha,
        "t0_script_sha256":file_hash(Path(__file__),limit=4*1024*1024)[1],
        "upstream_repository":UPSTREAM,"upstream_tag":TAG,
        "upstream_expected_commit":COMMIT,
        "build_policy":"CMAKE_OFFLINE_NO_INSTALL_NO_PACKAGE_MANAGER",
        "testing_role":"synthetic-only-toolchain-feasibility",
        "original_realman_data_used":False,"original_d1_csv_source_admitted":False,
        "original_d2_s3_preinstalled_only_protocol_passed":False,
        "realman_pcm_md5_verified":False,"doa_accuracy_measured":False,
        "shipping_authority":False,"research_rights":"GPL_REFERENCE_CLI_BUILD_NONCOMMERCIAL_RESEARCH_ONLY",
    }


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False,sort_keys=True,
                              separators=(",",":"),allow_nan=False)+"\n",
                   encoding="utf-8")
    tmp.replace(path)


def load(path):
    def hook(pairs):
        out = {}
        for k,v in pairs:
            require(k not in out,"T0_DUPLICATE_RECEIPT_KEY")
            out[k]=v
        return out
    require(path.is_file() and path.stat().st_size<32768,"T0_RECEIPT_MISSING")
    return json.loads(path.read_text(encoding="utf-8"),
                      object_pairs_hook=hook)


def collect(work, receipt):
    out = identity(commit_sha())
    out["captured_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        require(not work.exists(), "T0_WORKSPACE_ALREADY_EXISTS")
        work.mkdir(parents=True)
        git, git_sha = program("git")
        cmake, cmake_sha = program("cmake")
        c_compiler, cc_sha = program("cc")
        out["build_tool_preflight"] = {
            "git_binary_sha256":git_sha,"cmake_binary_sha256":cmake_sha,
            "cc_binary_sha256":cc_sha,
            "git_version":command([git, "--version"],timeout=5),
            "cmake_version":command([cmake,"--version"],timeout=5).splitlines()[0],
            "cc_version":command([c_compiler,"--version"],timeout=5).splitlines()[0],
        }
        # One pinned public official GitHub source clone; no package install.
        env=dict(os.environ,GIT_TERMINAL_PROMPT="0",GIT_CONFIG_NOSYSTEM="1")
        command([git,"clone","--depth","1","--branch",TAG,"--single-branch",
                 UPSTREAM,str(work/"flac-source")],
                cwd=work,timeout=120,code="T0_OFFICIAL_SOURCE_FETCH_FAILED",env=env)
        upstream=source_identity(work)
        out["upstream"]=upstream
        start=time.monotonic()
        command([cmake,"-S",str(work/"flac-source"),"-B",str(work/"build"),
                 *BUILD_FLAGS],timeout=120,code="T0_NATIVE_CMAKE_CONFIG_FAILED")
        remain=max(1,480-int(time.monotonic()-start))
        command([cmake,"--build",str(work/"build"),"--target","flacapp",
                 "--parallel","2"],timeout=remain,
                code="T0_REFERENCE_CLI_BUILD_FAILED")
        require(time.monotonic()-start <= 480, "T0_BUILD_TIME_EXCEEDED")
        tool,tool_meta=toolchain_identity(work)
        proof=synthetic_proof(work,tool,prefix="collect-fixture")
        require(source_identity(work)==upstream, "T0_SOURCE_CHANGED_AFTER_BUILD")
        out.update({"native_decoder":tool_meta,"synthetic_proof":proof,"decision":PASS})
        status=0
    except (Reject, OSError, subprocess.SubprocessError) as err:
        # Source/build partial measurements are NOT a proof of qualification.
        for key in ("build_tool_preflight","upstream","native_decoder","synthetic_proof"):
            out.pop(key,None)
        out["decision"]=BLOCKED
        out["failure_code"]=getattr(err,"code","T0_BUILD_OR_STORAGE_ERROR")
        status=1
    save(receipt,out)
    print("decision="+out["decision"]+" failure="+out.get("failure_code","NONE"),
          flush=True)
    return status


def verify(work, path):
    actual=load(path)
    expected=identity(commit_sha())
    require(isinstance(actual,dict),"T0_RECEIPT_TAMPER")
    for k,v in expected.items():
        require(actual.get(k)==v,"T0_RECEIPT_TAMPER")
    require(isinstance(actual.get("captured_at_utc"),str) and
            bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                              actual["captured_at_utc"])),"T0_RECEIPT_TAMPER")
    if actual.get("decision")==PASS:
        require(set(actual)==set(expected) |
                {"captured_at_utc","build_tool_preflight","upstream",
                 "native_decoder","synthetic_proof","decision"},
                "T0_RECEIPT_TAMPER")
        require(actual["upstream"]==source_identity(work),"T0_SOURCE_READBACK_MISMATCH")
        tool,tool_meta=toolchain_identity(work)
        require(tool_meta==actual["native_decoder"],"T0_BINARY_READBACK_MISMATCH")
        proof=synthetic_proof(work,tool,prefix="verify-fixture")
        require(proof==actual["synthetic_proof"],"T0_SYNTHETIC_READBACK_MISMATCH")
    else:
        require(actual.get("decision")==BLOCKED
                and isinstance(actual.get("failure_code"),str)
                and actual["failure_code"].startswith("T0_")
                and set(actual)==set(expected) | {"captured_at_utc","decision",
                                                   "failure_code"},
                "T0_RECEIPT_TAMPER")
    print("T0_INDEPENDENT_READBACK_CONSISTENT="+actual["decision"])


def self_test():
    x=synthetic_pcm()
    assert len(x)==514 and x[:2]==struct.pack("<h",-32768)
    assert len(set(x))>2
    assert COMMIT=="28e4f0528c76b296c561e922ba67d43751990599"
    assert len(BUILD_FLAGS)==9 and "-DWITH_OGG=OFF" in BUILD_FLAGS
    with tempfile.TemporaryDirectory(prefix="t0-fixture-") as td:
        p=Path(td)/"receipt.json"
        baseline=identity("0"*40)
        blocked=dict(baseline,captured_at_utc="2026-10-10T00:00:00Z",
                     decision=BLOCKED,failure_code="T0_BUILD_TOOL_MISSING")
        save(p,blocked)
        assert load(p)==blocked
        assert digest(x)==digest(synthetic_pcm())
        assert not blocked["original_realman_data_used"]
        assert not blocked["realman_pcm_md5_verified"]
    print("REALMAN_D2_T0_OFFLINE_SELF_TEST_PASS; no original audio or source built")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("self-test","collect","verify"))
    p.add_argument("--workspace")
    p.add_argument("--receipt")
    a=p.parse_args()
    if a.action=="self-test":
        self_test()
        return 0
    require(a.workspace and a.receipt,"T0_ARGUMENTS_MISSING")
    work=Path(a.workspace).resolve()
    require(work!=ROOT and ROOT not in work.parents,
            "T0_WORKSPACE_UNSAFE")
    if a.action=="collect":
        return collect(work,Path(a.receipt).resolve())
    verify(work,Path(a.receipt).resolve())
    return 0

if __name__=="__main__":
    raise SystemExit(main())
