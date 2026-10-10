#!/usr/bin/env python3
"""FE03 A2 D2-S1: only one pinned RealMAN Gym.rar raw-byte feasibility pilot.

Preregistered at github.com/jiying2007/audio-pipeline/issues/703.
No paid services, archive redistribution, FLAC extraction, DOA or shipping authority.
"""
from __future__ import annotations
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import shutil
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[3]
REV = "fea47505cae8041f4b652b0954ba61c77d2b6df1"
REL = "val/ma_noisy_speech/Gym.rar"
URL = "https://huggingface.co/datasets/AISHELL/RealMAN/resolve/" + REV + "/" + REL
EXPECTED_BYTES = 447127176
EXPECTED_SHA = "8175dad412a752a34bdf2722f7e9b5ee671b62e67dfe5179f7a769d63912b2ea"
MAX_BYTES = 512 * 1024 * 1024
MAX_SECONDS = 13 * 60
CHUNK = 1024 * 1024
PASS = "REALMAN_D2_S1_ONE_ARCHIVE_HASH_VERIFIED_RESEARCH_ONLY"
BLOCKED = "REALMAN_D2_S1_SOURCE_FEASIBILITY_BLOCKED"
RAR4 = b"Rar!\x1a\x07\x00"
RAR5 = b"Rar!\x1a\x07\x01\x00"

class Reject(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code

def require(condition, code="D2_S1_INTEGRITY_REJECTED"):
    if not condition:
        raise Reject(code)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def file_hash(path, cap=MAX_BYTES):
    h, length = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(CHUNK)
            if not chunk:
                break
            length += len(chunk)
            require(length <= cap, "ARCHIVE_BYTES_TOO_LARGE")
            h.update(chunk)
    return length, h.hexdigest()

def approved_url(url):
    try:
        p = urlsplit(url)
        host = (p.hostname or "").lower()
        return (p.scheme == "https" and p.username is None and p.password is None
                and p.port in (None, 443) and not p.fragment and bool(p.path)
                and (host == "huggingface.co" or host.endswith(".huggingface.co")
                     or host == "hf.co" or host.endswith(".hf.co")))
    except ValueError:
        return False

class RestrictedRedirect(HTTPRedirectHandler):
    max_redirections = 5
    max_repeats = 2
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        dest = urljoin(req.full_url, newurl)
        require(approved_url(dest), "ARCHIVE_REDIRECT_NOT_TRUSTED")
        return super().redirect_request(req, fp, code, msg, headers, dest)

def rar_header_valid(prefix):
    return prefix.startswith(RAR4) or prefix.startswith(RAR5)

def stream_bounded(response, target, *, expected_length, expected_sha, cap, start=None):
    """Single bounded streaming pass; no provider dependencies, resume, or large RAM."""
    require(0 < expected_length <= cap <= MAX_BYTES, "ARCHIVE_SIZE_POLICY_DRIFT")
    length_header = response.headers.get("Content-Length")
    if length_header is not None:
        require(length_header.isdecimal(), "ARCHIVE_CONTENT_LENGTH_MALFORMED")
        require(int(length_header) <= cap, "ARCHIVE_BYTES_TOO_LARGE")
        require(int(length_header) == expected_length, "ARCHIVE_CONTENT_LENGTH_MISMATCH")
    require(response.headers.get("Content-Encoding", "identity").lower()
            in ("", "identity"), "ARCHIVE_CONTENT_ENCODING_REJECTED")
    require("Content-Range" not in response.headers, "ARCHIVE_RANGE_REJECTED")
    ctype = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
    require(ctype not in ("text/html", "text/plain", "application/json", "text/xml"),
            "ARCHIVE_WRONG_CONTENT_TYPE")
    if start is None:
        start = time.monotonic()
    h, count, first = hashlib.sha256(), 0, b""
    with target.open("wb") as output:
        while True:
            require(time.monotonic() - start <= MAX_SECONDS, "ARCHIVE_TIMEOUT")
            raw = response.read(min(CHUNK, cap + 1 - count))
            if not raw:
                break
            if len(first) < 8:
                first += raw[:8 - len(first)]
            if len(first) >= 8:
                require(rar_header_valid(first), "ARCHIVE_MAGIC_REJECTED")
            count += len(raw)
            require(count <= cap, "ARCHIVE_BYTES_TOO_LARGE")
            require(count <= expected_length, "ARCHIVE_LENGTH_MISMATCH")
            h.update(raw)
            output.write(raw)
    require(count == expected_length, "ARCHIVE_TRANSFER_INCOMPLETE")
    require(rar_header_valid(first), "ARCHIVE_MAGIC_REJECTED")
    require(h.hexdigest() == expected_sha, "ARCHIVE_SHA256_MISMATCH")
    return {"actual_bytes": count, "actual_sha256": h.hexdigest(),
            "archive_magic": "rar5" if first.startswith(RAR5) else "rar4"}

def download(work):
    require(approved_url(URL) and REV in URL and REL in URL,
            "ARCHIVE_URL_POLICY_DRIFT")
    request = Request(URL, headers={
        "Accept": "application/octet-stream,application/x-rar-compressed",
        "Accept-Encoding": "identity",
        "User-Agent": "audio-pipeline-realman-d2-s1/1",
    })
    try:
        start = time.monotonic()
        with build_opener(RestrictedRedirect()).open(request, timeout=30) as response:
            require(response.status == 200 and approved_url(response.geturl()),
                    "ARCHIVE_REMOTE_RESPONSE_REJECTED")
            record = stream_bounded(response, work / "Gym.rar",
                                    expected_length=EXPECTED_BYTES,
                                    expected_sha=EXPECTED_SHA, cap=MAX_BYTES,
                                    start=start)
            record["final_origin_host"] = urlsplit(response.geturl()).hostname
            return record
    except Reject:
        raise
    except (HTTPError, URLError, TimeoutError, OSError):
        # Never expose signed redirect URL, bearer token or upstream error body.
        raise Reject("ARCHIVE_REMOTE_INACCESSIBLE") from None

def safe_name(name):
    if not isinstance(name, str) or not 0 < len(name) <= 511:
        return False
    if name.startswith(("/", "\\")) or "\\" in name or "\x00" in name:
        return False
    name = name.rstrip("/")
    path = PurePosixPath(name)
    return (name == path.as_posix() and ".." not in path.parts
            and all(0 < len(part) < 130 for part in path.parts))

def first_lister_version(raw):
    lines = raw.decode("utf-8", "replace").splitlines()
    values = [re.sub(r"[^\x20-\x7E]", "", line).strip()[:180] for line in lines]
    return next((value for value in values if value), None)

def bounded_listing(path):
    """Attempt read-only preinstalled listers; no extraction or package install."""
    choices = (
        ("bsdtar", ("-tf",), ("--version",)),
        ("7z", ("l", "-slt", "-bd"), ("-h",)),
        ("unrar", ("lb",), ("-?",)),
    )
    for name, options, versionargs in choices:
        found = shutil.which(name)
        if not found:
            continue
        exe = str(Path(found).resolve())
        if not exe.startswith(("/usr/bin/", "/bin/")):
            continue
        try:
            binary_bytes, binary_sha = file_hash(Path(exe), cap=64 * 1024 * 1024)
            require(binary_bytes > 0, "LIST_TOOL_UNTRUSTED")
        except (OSError, Reject):
            continue
        process = None
        try:
            version = subprocess.run([exe, *versionargs], stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, timeout=5,
                                     check=False)
            ver = first_lister_version(version.stdout)
            if not ver:
                continue
            process = subprocess.Popen([exe, *options, str(path)],
                                       stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL)
            copied, budget, start = bytearray(), 4 * 1024 * 1024, time.monotonic()
            with selectors.DefaultSelector() as selector:
                fd = process.stdout.fileno()
                os.set_blocking(fd, False)
                selector.register(fd, selectors.EVENT_READ)
                while selector.get_map():
                    require(time.monotonic() - start < 75, "LIST_TOOL_TIMEOUT")
                    for key, _ in selector.select(timeout=1):
                        segment = os.read(key.fd, 8192)
                        if not segment:
                            selector.unregister(key.fd)
                        else:
                            copied.extend(segment)
                            require(len(copied) <= budget, "LIST_OUTPUT_TOO_LARGE")
            if process.wait(timeout=5) != 0:
                continue
            lines = copied.decode("utf-8", "strict").splitlines()
            if name == "7z":
                seen_heading = False
                names = []
                for line in lines:
                    if line.startswith("----------"):
                        seen_heading = True
                    elif seen_heading and line.startswith("Path = "):
                        names.append(line[7:])
            else:
                names = lines
            if not names or len(names) > 100000 or len(names) != len(set(names)):
                continue
            if not all(safe_name(x) for x in names):
                continue
            ordered = sorted(names)
            counts = {str(c): 0 for c in (1, 3, 5, 7)}
            families = {"static": 0, "moving": 0, "unclassified": 0}
            for member in ordered:
                key = ("static" if "/static/" in "/" + member else
                       "moving" if "/moving/" in "/" + member else "unclassified")
                families[key] += 1
                for channel in counts:
                    if member.endswith("_CH" + channel + ".flac"):
                        counts[channel] += 1
            return {"member_inventory_listed": True,
                    "lister": name, "lister_version": ver,
                    "lister_binary_sha256": binary_sha,
                    "member_count": len(ordered),
                    "member_name_list_sha256": sha("\n".join(ordered).encode("utf-8")),
                    "member_role_name_counts": families,
                    "candidate_channel_filename_counts": counts,
                    "flac_headers_verified": False,
                    "member_data_verified": False}
        except (OSError, Reject, UnicodeError, subprocess.SubprocessError):
            continue
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                if process.stdout is not None:
                    process.stdout.close()
    return {"member_inventory_listed": False,
            "reason": "NO_VERIFIED_LIST_ONLY_TOOL",
            "flac_headers_verified": False, "member_data_verified": False}

def execution_sha():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                   cwd=ROOT, text=True).strip()
    require(bool(re.fullmatch(r"[0-9a-f]{40}", head))
            and head == os.environ.get("GITHUB_SHA"), "EXECUTION_SHA_MISMATCH")
    return head

def identity(sha_commit):
    script = Path(__file__)
    d2 = ROOT / "tests/validation/frontend_evolution/realman_scene_tree_d2_s0.py"
    return {
        "schema_version": 1,
        "experiment_id": "REALMAN-FE03-A2-D2-S1-GYM-ARCHIVE-BYTES",
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/703",
        "dataset_revision": REV, "source_role": "val-noisy-disclosed-development",
        "archive_path": REL, "expected_bytes": EXPECTED_BYTES,
        "expected_sha256": EXPECTED_SHA, "max_bytes": MAX_BYTES,
        "execution_sha": sha_commit,
        "source_script_sha256": file_hash(script, cap=4*1024*1024)[1],
        "d2_s0_script_sha256": file_hash(d2, cap=4*1024*1024)[1],
        "research_rights": "NONCOMMERCIAL_ATTRIBUTION_ONLY",
        "original_d1_csv_admitted": False,
        "selected_as_doa_study_scene": False,
        "audio_channels_decoded": False,
        "timestamp_alignment_qualified": False,
        "doa_accuracy_measured": False,
        "shipping_authority": False,
    }

def record_receipt(path, receipt):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(receipt, sort_keys=True,
                               ensure_ascii=False, separators=(",", ":"),
                               allow_nan=False) + "\n", encoding="utf-8")
    temp.replace(path)

def collect(work, receipt_path):
    receipt = identity(execution_sha())
    receipt["retrieved_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        work.mkdir(parents=True, exist_ok=True)
        receipt["archive"] = download(work)
        receipt["members"] = bounded_listing(work / "Gym.rar")
        receipt["decision"] = PASS
        code = 0
    except (Reject, OSError) as err:
        receipt["decision"] = BLOCKED
        receipt["failure_code"] = (err.code if isinstance(err, Reject)
                                   else "ARCHIVE_LOCAL_STORAGE_FAILURE")
        temp = work / "Gym.rar"
        if temp.is_file():
            receipt["partial_bytes"], receipt["partial_sha256"] = file_hash(temp)
        code = 1
    record_receipt(receipt_path, receipt)
    print("decision=" + receipt["decision"] +
          " failure=" + receipt.get("failure_code", "NONE"), flush=True)
    return code

def verify_archive(path, record, expected_size, expected_digest):
    require(isinstance(record, dict), "RECEIPT_TAMPER")
    require(path.is_file(), "ARCHIVE_MISSING_FOR_READBACK")
    size, checksum = file_hash(path)
    require(size == expected_size and checksum == expected_digest,
            "ARCHIVE_READBACK_SHA_MISMATCH")
    with path.open("rb") as f:
        magic = f.read(8)
    require(rar_header_valid(magic), "ARCHIVE_READBACK_MAGIC_MISMATCH")
    origin = record.get("final_origin_host")
    require(isinstance(origin, str) and approved_url("https://" + origin + "/object"),
            "RECEIPT_TAMPER")
    require(record.get("actual_bytes") == size
            and record.get("actual_sha256") == checksum
            and record.get("archive_magic") ==
            ("rar5" if magic.startswith(RAR5) else "rar4"), "RECEIPT_TAMPER")

def verify(work, receipt, expected):
    for key, value in expected.items():
        require(receipt.get(key) == value, "RECEIPT_TAMPER")
    stamp = receipt.get("retrieved_at_utc")
    require(isinstance(stamp, str) and bool(re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", stamp)), "RECEIPT_TAMPER")
    target = work / "Gym.rar"
    if receipt.get("decision") == PASS:
        verify_archive(target, receipt.get("archive"), EXPECTED_BYTES, EXPECTED_SHA)
        require(receipt.get("members") == bounded_listing(target), "RECEIPT_TAMPER")
        require(set(receipt) == set(expected) |
                {"retrieved_at_utc", "archive", "members", "decision"},
                "RECEIPT_TAMPER")
    else:
        allowed = {
            "ARCHIVE_URL_POLICY_DRIFT", "ARCHIVE_REMOTE_INACCESSIBLE",
            "ARCHIVE_REMOTE_RESPONSE_REJECTED", "ARCHIVE_REDIRECT_NOT_TRUSTED",
            "ARCHIVE_SIZE_POLICY_DRIFT", "ARCHIVE_BYTES_TOO_LARGE",
            "ARCHIVE_TIMEOUT", "ARCHIVE_CONTENT_LENGTH_MALFORMED",
            "ARCHIVE_CONTENT_LENGTH_MISMATCH", "ARCHIVE_CONTENT_ENCODING_REJECTED",
            "ARCHIVE_RANGE_REJECTED", "ARCHIVE_WRONG_CONTENT_TYPE",
            "ARCHIVE_MAGIC_REJECTED", "ARCHIVE_LENGTH_MISMATCH",
            "ARCHIVE_TRANSFER_INCOMPLETE", "ARCHIVE_SHA256_MISMATCH",
            "ARCHIVE_LOCAL_STORAGE_FAILURE",
        }
        require(receipt.get("decision") == BLOCKED and
                receipt.get("failure_code") in allowed and
                "archive" not in receipt and "members" not in receipt,
                "RECEIPT_TAMPER")
        extra = set()
        if target.is_file():
            n, h = file_hash(target)
            require(receipt.get("partial_bytes") == n and
                    receipt.get("partial_sha256") == h, "RECEIPT_TAMPER")
            extra = {"partial_bytes", "partial_sha256"}
        require(set(receipt) == set(expected) |
                {"retrieved_at_utc", "decision", "failure_code"} | extra,
                "RECEIPT_TAMPER")
    print("independent_receipt_and_archive_readback=true decision=" +
          receipt["decision"], flush=True)

def self_test():
    assert first_lister_version(b"\n7-Zip 24.09 (x64)\n\nCopyright\n") == "7-Zip 24.09 (x64)"
    assert first_lister_version(b"\n\n") is None
    assert approved_url(URL)
    assert not approved_url("https://evil.example/Gym.rar")
    assert not approved_url(URL.replace("https:", "http:"))
    assert not approved_url(URL.replace("huggingface.co", "huggingface.co.evil.test"))
    assert URL != URL.replace(REV, "main")
    assert safe_name("Gym/static/P0001/VAL_S_GYM_P0001_0001_CH1.flac")
    for unsafe in ("../x.flac", "/absolute.flac", "C:\\tmp\\fake.flac"):
        assert not safe_name(unsafe)
    sample = RAR5 + b"REALMAN"
    class Fake:
        headers = {"Content-Length": str(len(sample)),
                   "Content-Type": "application/octet-stream"}
        def __init__(self, raw):
            self.stream = io.BytesIO(raw)
        def read(self, n):
            return self.stream.read(n)
    with tempfile.TemporaryDirectory(prefix="realman-d2-s1-test-") as td:
        work = Path(td)
        target = work / "Gym.rar"
        got = stream_bounded(Fake(sample), target, expected_length=len(sample),
                             expected_sha=sha(sample), cap=MAX_BYTES)
        assert got["actual_bytes"] == len(sample) and got["archive_magic"] == "rar5"
        for raw, checksum, reason in (
            (sample[:-1], sha(sample), "ARCHIVE_TRANSFER_INCOMPLETE"),
            (sample, "0"*64, "ARCHIVE_SHA256_MISMATCH"),
            (b"<html>abcdef", "0"*64, "ARCHIVE_MAGIC_REJECTED"),
        ):
            try:
                stream_bounded(Fake(raw), target, expected_length=len(sample),
                               expected_sha=checksum, cap=MAX_BYTES)
            except Reject as err:
                assert err.code == reason
            else:
                raise AssertionError("invalid archive accepted: " + reason)
        stream_bounded(Fake(sample), target, expected_length=len(sample),
                       expected_sha=sha(sample), cap=MAX_BYTES)
        record = {"actual_bytes": len(sample), "actual_sha256": sha(sample),
                  "archive_magic": "rar5",
                  "final_origin_host": "cas-bridge.xethub.hf.co"}
        verify_archive(target, record, len(sample), sha(sample))
        for change in (
            {"actual_bytes": len(sample)+1},
            {"actual_sha256": "0"*64},
            {"archive_magic": "rar4"},
            {"final_origin_host": "evil.example"},
        ):
            altered = dict(record, **change)
            try:
                verify_archive(target, altered, len(sample), sha(sample))
            except Reject:
                pass
            else:
                raise AssertionError("mutated archive readback accepted")
        fixture = identity("0"*40)
        fixture.update({"retrieved_at_utc": "2026-10-10T00:00:00Z",
                        "decision": BLOCKED, "failure_code": "ARCHIVE_REMOTE_INACCESSIBLE"})
        check_dir = work / "not-downloaded"
        check_dir.mkdir()
        verify(check_dir, fixture, identity("0"*40))
        modified = copy.deepcopy(fixture)
        modified["shipping_authority"] = True
        try:
            verify(check_dir, modified, identity("0"*40))
        except Reject:
            pass
        else:
            raise AssertionError("receipt promotion forgery accepted")
    print("REALMAN_D2_S1_OFFLINE_SELF_TEST_PASS; no remote archive downloaded")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("self-test", "collect", "verify"))
    ap.add_argument("--workspace")
    ap.add_argument("--receipt")
    args = ap.parse_args()
    if args.action == "self-test":
        self_test()
        return 0
    require(bool(args.workspace and args.receipt), "ARGUMENTS_REQUIRED")
    work, receipt = Path(args.workspace).resolve(), Path(args.receipt).resolve()
    require(work != ROOT and ROOT not in work.parents, "UNSAFE_WORKSPACE")
    if args.action == "collect":
        return collect(work, receipt)
    verify(work, json.loads(receipt.read_text(encoding="utf-8")),
           identity(execution_sha()))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
