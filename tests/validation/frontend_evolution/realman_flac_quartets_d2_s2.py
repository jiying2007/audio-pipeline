#!/usr/bin/env python3
"""FE03 A2 D2-S2: 8 original Gym FLAC byte/STREAMINFO research-only study.

Frozen preregistration: github.com/jiying2007/audio-pipeline/issues/705.
No audio rendering/decoding, no DOA scoring, no source substitution.
"""
from __future__ import annotations
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import selectors
import shutil
import subprocess
import tempfile
import time

import realman_single_archive_d2_s1 as s1

ROOT = Path(__file__).resolve().parents[3]
CHS = (1, 3, 5, 7)
ROLES = ("static", "moving")
PER_FILE_LIMIT = 32 * 1024 * 1024
TOTAL_LIMIT = 128 * 1024 * 1024
LIST_OUTPUT_LIMIT = 4 * 1024 * 1024
LIST_TIMEOUT = 75
EXTRACT_TIMEOUT = 75
OVERALL_EXTRACT_TIMEOUT = 180
EXPECTED_7Z_SHA = "60fc00b4e1ed37668972c51f03426973d8006db3c7224075878f6d66196d7c27"
PASS = "REALMAN_D2_S2_GYM_8_FLAC_BYTES_AND_HEADERS_VERIFIED_RESEARCH_ONLY"
BLOCKED = "REALMAN_D2_S2_FLAC_SOURCE_BYTES_NOT_ADMITTED"
MAX_LISTED = 100000

class Reject(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code

def require(ok, code="S2_RESEARCH_INVALID"):
    if not ok:
        raise Reject(code)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def exact_tool():
    found = shutil.which("7z")
    require(found is not None, "S2_EXACT_LIST_TOOL_MISSING")
    path = Path(found).resolve()
    require(str(path).startswith(("/usr/bin/", "/bin/")),
            "S2_LIST_TOOL_NOT_SYSTEM")
    length, sha = s1.file_hash(path, cap=64 * 1024 * 1024)
    require(length > 0 and sha == EXPECTED_7Z_SHA,
            "S2_LIST_TOOL_IDENTITY_CHANGED")
    result = subprocess.run([str(path), "-h"], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            timeout=5, check=False)
    version = s1.first_lister_version(result.stdout)
    require(bool(version and version.startswith("7-Zip 23.01")),
            "S2_LIST_TOOL_VERSION_CHANGED")
    return str(path), {"binary_sha256": sha, "version": version}

def capture_process(command, cap, seconds, *, error_code):
    proc = None
    try:
        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
        data, start = bytearray(), time.monotonic()
        with selectors.DefaultSelector() as selector:
            fd = proc.stdout.fileno()
            os.set_blocking(fd, False)
            selector.register(fd, selectors.EVENT_READ)
            while selector.get_map():
                require(time.monotonic() - start < seconds, error_code)
                for key, _ in selector.select(timeout=1):
                    block = os.read(key.fd, 16384)
                    if not block:
                        selector.unregister(key.fd)
                    else:
                        require(len(data) + len(block) <= cap,
                                "S2_LIST_OUTPUT_TOO_LARGE")
                        data.extend(block)
        require(proc.wait(timeout=5) == 0, error_code)
        return bytes(data)
    except (OSError, subprocess.SubprocessError) as err:
        raise Reject(error_code) from None
    finally:
        if proc:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
            if proc.stdout:
                proc.stdout.close()

def parse_list(raw):
    """Strictly parse 7-Zip's -slt verbose list, no member extraction."""
    try:
        lines = raw.decode("utf-8", "strict").splitlines()
    except UnicodeError:
        raise Reject("S2_MEMBER_LIST_NOT_UTF8") from None
    require(any(line.startswith("----------") for line in lines),
            "S2_MEMBER_LIST_NOT_STRUCTURED")
    header_done, records, current = False, [], {}
    for line in lines:
        if not header_done:
            if line.startswith("----------"):
                header_done = True
            continue
        if not line.strip():
            if current:
                records.append(current)
                current = {}
            continue
        if " = " not in line:
            require(not current, "S2_MEMBER_LIST_MALFORMED")
            continue
        k, v = line.split(" = ", 1)
        require(k not in current and len(k) <= 64 and len(v) <= 1024,
                "S2_MEMBER_LIST_MALFORMED")
        current[k] = v
    if current:
        records.append(current)
    require(0 < len(records) <= MAX_LISTED, "S2_MEMBER_COUNT_INVALID")
    members = {}
    for record in records:
        name = record.get("Path", "")
        require(s1.safe_name(name) and name not in members,
                "S2_MEMBER_UNSAFE_OR_DUPLICATE")
        is_dir = record.get("Folder") == "+" or (
            name.endswith("/") or
            record.get("Attributes", "").startswith("D"))
        if is_dir:
            continue
        require(record.get("Encrypted", "-") == "-",
                "S2_ENCRYPTED_MEMBER_REJECTED")
        require(record.get("Size", "").isdecimal() and
                record.get("Packed Size", "").isdecimal(),
                "S2_MEMBER_SIZE_UNKNOWN")
        size, packed = int(record["Size"]), int(record["Packed Size"])
        require(0 <= size <= (1 << 40) and 0 <= packed <= s1.MAX_BYTES,
                "S2_MEMBER_SIZE_INVALID")
        require(not name.endswith("/"), "S2_MEMBER_UNSAFE_OR_DUPLICATE")
        members[name] = {"path": name, "size": size, "packed_size": packed}
    require(bool(members), "S2_NO_SAFE_ARCHIVE_MEMBERS")
    return members

def classify_member(name):
    require(s1.safe_name(name), "S2_MEMBER_UNSAFE_OR_DUPLICATE")
    parts = PurePosixPath(name).parts
    present = [role for role in ROLES if role in parts]
    if len(present) != 1:
        return None
    role = present[0]
    base = PurePosixPath(name).name
    m = re.fullmatch(r"(VAL_[MS]_[A-Za-z0-9_-]+)_CH([1357])\.flac",
                     base)
    if m is None:
        return None
    if (role == "static" and not base.startswith("VAL_S_")) or (
            role == "moving" and not base.startswith("VAL_M_")):
        return None
    ch = int(m.group(2))
    return role, name[:-(len("_CH" + str(ch) + ".flac"))], ch

def select_quartets(members):
    groups = {}
    for member in members.values():
        t = classify_member(member["path"])
        if t is None:
            continue
        role, stem, channel = t
        k = (role, stem)
        found = groups.setdefault(k, {})
        require(channel not in found, "S2_MEMBER_GROUP_DUPLICATE")
        found[channel] = member
    selected = []
    for role in ROLES:
        possible = sorted(
            ((stem, chans) for (r, stem), chans in groups.items()
             if r == role and set(chans) == set(CHS)),
            key=lambda item: item[0])
        require(bool(possible), "S2_NO_COMPLETE_" + role.upper() + "_QUARTET")
        stem, channels = possible[0]
        for channel in CHS:
            e = channels[channel]
            require(0 < e["size"] <= PER_FILE_LIMIT,
                    "S2_PRESELECTED_FLAC_TOO_LARGE")
            selected.append({"role": role, "channel": channel,
                             "name": e["path"], "size": e["size"],
                             "packed_size": e["packed_size"],
                             "stem_sha256": digest(stem.encode("utf-8")),
                             "member_path_sha256": digest(e["path"].encode("utf-8"))})
    require(len(selected) == 8 and
            sum(item["size"] for item in selected) <= TOTAL_LIMIT,
            "S2_PRESELECTED_TOTAL_BYTES_TOO_LARGE")
    return selected, {
        "metadata_member_count": len(members),
        "all_regular_name_sha256": digest(
            "\n".join(sorted(members)).encode("utf-8")),
        "complete_static_quartet_count": sum(
            1 for (r, _), c in groups.items() if r == "static" and set(c) == set(CHS)),
        "complete_moving_quartet_count": sum(
            1 for (r, _), c in groups.items() if r == "moving" and set(c) == set(CHS)),
        "selected_path_sha256": digest(
            "\n".join(q["name"] for q in selected).encode("utf-8")),
    }

def list_and_select(archive):
    tool, identity = exact_tool()
    raw = capture_process([tool, "l", "-slt", "-bd", str(archive)],
                          LIST_OUTPUT_LIMIT, LIST_TIMEOUT,
                          error_code="S2_LIST_TOOL_FAILED")
    members = parse_list(raw)
    selected, inventory = select_quartets(members)
    inventory["list_tool"] = identity
    return tool, selected, inventory

def extract_exact(tool, archive, name, target, size, deadline):
    require(s1.safe_name(name) and not any(ch in name for ch in ("*", "?", "[")),
            "S2_AMBIGUOUS_MEMBER_NAME")
    require(0 < size <= PER_FILE_LIMIT, "S2_EXTRACT_BUDGET_EXCEEDED")
    argv = [tool, "e", "-so", "-spd", "-y", str(archive), name]
    proc = None
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        count, start = 0, time.monotonic()
        hasher = hashlib.sha256()
        first = b""
        with target.open("xb") as output:
            with selectors.DefaultSelector() as selector:
                fd = proc.stdout.fileno()
                os.set_blocking(fd, False)
                selector.register(fd, selectors.EVENT_READ)
                while selector.get_map():
                    require(time.monotonic() < deadline and
                            time.monotonic() - start < EXTRACT_TIMEOUT,
                            "S2_EXTRACT_TIMEOUT")
                    for key, _ in selector.select(timeout=1):
                        data = os.read(key.fd, 65536)
                        if not data:
                            selector.unregister(key.fd)
                            continue
                        count += len(data)
                        require(count <= PER_FILE_LIMIT and count <= size,
                                "S2_EXTRACT_BUDGET_EXCEEDED")
                        if len(first) < 4:
                            first += data[:4 - len(first)]
                        output.write(data)
                        hasher.update(data)
        require(proc.wait(timeout=5) == 0 and count == size,
                "S2_EXACT_MEMBER_EXTRACTION_FAILED")
        require(first == b"fLaC", "S2_MEMBER_NOT_FLAC")
        return count, hasher.hexdigest()
    except (OSError, subprocess.SubprocessError):
        raise Reject("S2_EXTRACT_TOOL_FAILED") from None
    finally:
        if proc:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
            if proc.stdout:
                proc.stdout.close()

def flac_streaminfo(path):
    """Inspect FLAC magic / 34-byte STREAMINFO only; never decode PCM."""
    with path.open("rb") as stream:
        require(stream.read(4) == b"fLaC", "S2_FLAC_MAGIC_BAD")
        header = stream.read(4)
        require(len(header) == 4 and header[0] & 0x7f == 0 and
                int.from_bytes(header[1:4], "big") == 34,
                "S2_FLAC_STREAMINFO_INVALID")
        payload = stream.read(34)
        require(len(payload) == 34, "S2_FLAC_STREAMINFO_TRUNCATED")
    min_block = int.from_bytes(payload[:2], "big")
    max_block = int.from_bytes(payload[2:4], "big")
    sf = int.from_bytes(payload[10:18], "big")
    samplerate = (sf >> 44) & ((1 << 20) - 1)
    channels = ((sf >> 41) & 7) + 1
    bits = ((sf >> 36) & 31) + 1
    total_samples = sf & ((1 << 36) - 1)
    require(0 < min_block <= max_block and samplerate > 0 and
            channels == 1 and 4 <= bits <= 32 and total_samples > 0,
            "S2_FLAC_FORMAT_NOT_ADMITTED")
    pcm_md5 = payload[18:34]
    return {
        "native_sample_rate_hz": samplerate,
        "flac_encoded_channels": channels,
        "bits_per_sample": bits,
        "total_samples": total_samples,
        "min_block_size": min_block, "max_block_size": max_block,
        "streaminfo_pcm_md5_hex": pcm_md5.hex(),
        "streaminfo_pcm_md5_present": pcm_md5 != b"\x00" * 16,
        "decoded_pcm_verified": False,
    }

def format_group(records):
    for role in ROLES:
        rows = [x for x in records if x["role"] == role]
        require(len(rows) == 4 and [x["channel"] for x in rows] == list(CHS),
                "S2_ROLE_QUARTET_INCOMPLETE")
        metrics = {(x["streaminfo"]["native_sample_rate_hz"],
                    x["streaminfo"]["bits_per_sample"],
                    x["streaminfo"]["total_samples"]) for x in rows}
        require(len(metrics) == 1, "S2_CHANNEL_FORMAT_OR_LENGTH_MISMATCH")
    return {
        "native_48khz_all": all(
            row["streaminfo"]["native_sample_rate_hz"] == 48000 for row in records),
        "all_quartet_channels_mono": all(
            row["streaminfo"]["flac_encoded_channels"] == 1 for row in records),
        "physical_capture_sync_verified": False,
        "camera_audio_timebase_verified": False,
        "doa_study_scene_selected": False,
        "doa_scored": False,
    }

def exact_work(path):
    work = Path(path).resolve()
    require(work != ROOT and ROOT not in work.parents, "S2_WORKSPACE_UNSAFE")
    return work

def source_sha():
    raw = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                  cwd=ROOT, text=True).strip()
    require(bool(re.fullmatch(r"[0-9a-f]{40}", raw)) and
            raw == os.environ.get("GITHUB_SHA"), "S2_EXECUTION_SHA_MISMATCH")
    return raw

def identity(sha_commit):
    return {
        "schema_version": 1,
        "experiment_id": "FE03-A2-D2-S2-REALMAN-FLAC-8-BYTES",
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/705",
        "source_dataset_revision": s1.REV,
        "source_archive_path": s1.REL,
        "source_archive_expected_sha256": s1.EXPECTED_SHA,
        "source_archive_expected_bytes": s1.EXPECTED_BYTES,
        "max_flac_original_bytes_per_file": PER_FILE_LIMIT,
        "max_flac_original_total_bytes": TOTAL_LIMIT,
        "selection_policy": "LEX_FIRST_COMPLETE_STATIC_AND_MOVING_QUARTETS_BY_MEMBER_NAME",
        "source_role": "disclosed-development-only",
        "source_commit": sha_commit,
        "s2_script_sha256": s1.file_hash(Path(__file__), cap=4*1024*1024)[1],
        "s1_script_sha256": s1.file_hash(Path(s1.__file__), cap=4*1024*1024)[1],
        "original_d1_csv_source_admitted": False,
        "source_audio_channel_sync_qualified": False,
        "doa_accuracy_measured": False,
        "shipping_authority": False,
        "research_rights": "NONCOMMERCIAL_ATTRIBUTION_ONLY",
    }

def save(path, result):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(result, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"), allow_nan=False) + "\n",
                    encoding="utf-8")
    temp.replace(path)

def collect(work, path):
    result = identity(source_sha())
    result["retrieved_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        work.mkdir(parents=True, exist_ok=True)
        archive = work / "Gym.rar"
        upstream = s1.download(work)
        s1.verify_archive(archive, upstream, s1.EXPECTED_BYTES, s1.EXPECTED_SHA)
        result["archive"] = upstream
        tool, selected, inventory = list_and_select(archive)
        result["inventory"] = inventory
        result["preselected_member_path_sha256s"] = [
            x["member_path_sha256"] for x in selected
        ]
        results, total = [], 0
        deadline = time.monotonic() + OVERALL_EXTRACT_TIMEOUT
        for x in selected:
            flat = work / ("%s-ch%d.flac" % (x["role"], x["channel"]))
            size, checksum = extract_exact(tool, archive, x["name"], flat,
                                           x["size"], deadline)
            total += size
            require(total <= TOTAL_LIMIT, "S2_EXTRACT_BUDGET_EXCEEDED")
            actual_size, actual_sha = s1.file_hash(flat, cap=PER_FILE_LIMIT)
            require((actual_size, actual_sha) == (size, checksum),
                    "S2_FLAC_READBACK_MISMATCH")
            result_row = {
                "role": x["role"], "channel": x["channel"],
                "member_path_sha256": x["member_path_sha256"],
                "stem_sha256": x["stem_sha256"],
                "listed_uncompressed_bytes": x["size"],
                "listed_packed_bytes": x["packed_size"],
                "original_flac_bytes": size, "original_flac_sha256": checksum,
                "streaminfo": flac_streaminfo(flat),
            }
            results.append(result_row)
        result["members"] = results
        result["format_summary"] = format_group(results)
        result["decision"] = PASS
        code = 0
    except (Reject, OSError, subprocess.SubprocessError) as err:
        # Blocked provenance is a *minimal* failure receipt. Never publish
        # misleading partial success fields as an admitted FLAC study.
        for field in ("archive", "inventory", "preselected_member_path_sha256s",
                      "members", "format_summary"):
            result.pop(field, None)
        result["decision"] = BLOCKED
        result["failure_code"] = (
            err.code if isinstance(err, Reject) else "S2_TOOL_OR_STORAGE_ERROR")
        code = 1
    save(path, result)
    print("decision=" + result["decision"] + " failure=" +
          result.get("failure_code", "NONE"), flush=True)
    return code

def read_receipt(path):
    def no_duplicate(pairs):
        obj = {}
        for k, v in pairs:
            require(k not in obj, "S2_RECEIPT_TAMPER")
            obj[k] = v
        return obj
    def no_constant(_):
        raise Reject("S2_RECEIPT_TAMPER")
    try:
        value = json.loads(path.read_text(encoding="utf-8"),
                           object_pairs_hook=no_duplicate,
                           parse_constant=no_constant)
    except (UnicodeError, ValueError):
        raise Reject("S2_RECEIPT_TAMPER") from None
    require(isinstance(value, dict), "S2_RECEIPT_TAMPER")
    return value

def verify_receipt(work, receipt, expected):
    for k, v in expected.items():
        require(receipt.get(k) == v, "S2_RECEIPT_TAMPER")
    timestamp = receipt.get("retrieved_at_utc")
    require(isinstance(timestamp, str) and bool(re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", timestamp)),
        "S2_RECEIPT_TAMPER")
    if receipt.get("decision") == PASS:
        archive = work / "Gym.rar"
        upstream = receipt.get("archive", {})
        # S1's verify_archive independently re-reads and rehashes the entire
        # original RAR; do not cause a redundant, third full archive pass.
        s1.verify_archive(archive, upstream, s1.EXPECTED_BYTES, s1.EXPECTED_SHA)
        _, selected, inventory = list_and_select(archive)
        require(receipt.get("inventory") == inventory and
                receipt.get("preselected_member_path_sha256s") ==
                [x["member_path_sha256"] for x in selected],
                "S2_RECEIPT_TAMPER")
        recorded = receipt.get("members")
        require(isinstance(recorded, list) and len(recorded) == 8,
                "S2_RECEIPT_TAMPER")
        rebuilt = []
        for x in selected:
            flat = work / ("%s-ch%d.flac" % (x["role"], x["channel"]))
            size, checksum = s1.file_hash(flat, cap=PER_FILE_LIMIT)
            rebuilt.append({
                "role": x["role"], "channel": x["channel"],
                "member_path_sha256": x["member_path_sha256"],
                "stem_sha256": x["stem_sha256"],
                "listed_uncompressed_bytes": x["size"],
                "listed_packed_bytes": x["packed_size"],
                "original_flac_bytes": size, "original_flac_sha256": checksum,
                "streaminfo": flac_streaminfo(flat),
            })
            require(size == x["size"], "S2_READBACK_SIZE_MISMATCH")
        require(recorded == rebuilt and receipt.get("format_summary") ==
                format_group(rebuilt), "S2_RECEIPT_TAMPER")
        require(sum(x["original_flac_bytes"] for x in rebuilt) <= TOTAL_LIMIT,
                "S2_EXTRACT_BUDGET_EXCEEDED")
        require(set(receipt) == set(expected) |
                {"retrieved_at_utc", "archive", "inventory",
                 "preselected_member_path_sha256s", "members",
                 "format_summary", "decision"}, "S2_RECEIPT_TAMPER")
    else:
        code = receipt.get("failure_code")
        require(receipt.get("decision") == BLOCKED and
                isinstance(code, str) and
                (code.startswith("S2_") or code in (
                    "ARCHIVE_REMOTE_INACCESSIBLE",
                    "ARCHIVE_REDIRECT_NOT_TRUSTED", "ARCHIVE_MAGIC_REJECTED",
                    "ARCHIVE_SHA256_MISMATCH", "ARCHIVE_TIMEOUT",
                    "ARCHIVE_BYTES_TOO_LARGE", "ARCHIVE_TRANSFER_INCOMPLETE",
                    "ARCHIVE_CONTENT_LENGTH_MISMATCH",
                    "ARCHIVE_WRONG_CONTENT_TYPE",
                    "ARCHIVE_REMOTE_RESPONSE_REJECTED",
                    "ARCHIVE_RANGE_REJECTED",
                    "ARCHIVE_CONTENT_ENCODING_REJECTED")),
                "S2_RECEIPT_TAMPER")
        require(set(receipt) == set(expected) |
                {"retrieved_at_utc", "decision", "failure_code"},
                "S2_RECEIPT_TAMPER")
    print("S2_INDEPENDENT_READBACK_CONSISTENT=" + receipt["decision"])

def self_test():
    fixture = [
        {"path": "Gym/"+role+"/001/VAL_"+token+"_GYM_001_0001_CH"+str(ch)+".flac",
         "size": 64, "packed_size": 30}
        for role, token in (("static", "S"), ("moving", "M")) for ch in CHS
    ]
    mock = "\n".join(["7-Zip 23.01", "Listing archive: Gym.rar", "----------", ""] +
                     sum(([f"Path = {row['path']}",
                           f"Size = {row['size']}",
                           f"Packed Size = {row['packed_size']}",
                           "Encrypted = -", "Attributes = A", ""] for row in fixture), []))
    members = parse_list(mock.encode("utf-8"))
    selected, profile = select_quartets(members)
    assert len(selected) == 8 and profile["complete_static_quartet_count"] == 1
    assert profile["complete_moving_quartet_count"] == 1
    assert [r["channel"] for r in selected] == list(CHS) * 2
    for mutated in (
        mock + "\nPath = ../unsafe.flac\nSize = 1\nPacked Size = 1\n",
        mock + "\nPath = "+fixture[0]["path"]+"\nSize = 1\nPacked Size = 1\n",
        mock.replace("Size = 64", "Size = -1", 1),
        mock.replace("Encrypted = -", "Encrypted = +", 1),
    ):
        try:
            parse_list(mutated.encode("utf-8"))
        except Reject:
            pass
        else:
            raise AssertionError("invalid archive list passed")
    prefix = b"fLaC" + bytes([0]) + (34).to_bytes(3, "big")
    rate, chans, bits, nsample = 48000, 1, 16, 48000
    packed = (rate << 44) | ((chans - 1) << 41) | ((bits - 1) << 36) | nsample
    info = (256).to_bytes(2, "big") + (4096).to_bytes(2, "big") + (
        b"\x00" * 6) + packed.to_bytes(8, "big") + (b"\x01" * 16)
    assert len(info) == 34
    with tempfile.TemporaryDirectory(prefix="realman-s2-selftest-") as td:
        source = Path(td) / "test.flac"
        source.write_bytes(prefix + info)
        fields = flac_streaminfo(source)
        assert fields["native_sample_rate_hz"] == 48000
        assert fields["flac_encoded_channels"] == 1
        assert fields["total_samples"] == nsample
        for bad in (b"RIFF" + prefix[4:] + info, prefix + info[:10]):
            source.write_bytes(bad)
            try:
                flac_streaminfo(source)
            except Reject:
                pass
            else:
                raise AssertionError("invalid flac header passed")
        recs = [
            {"role": role, "channel": ch, "streaminfo": fields}
            for role in ROLES for ch in CHS
        ]
        assert format_group(recs)["native_48khz_all"]
        tamper = copy.deepcopy(recs)
        tamper[0]["streaminfo"]["total_samples"] = 100
        try:
            format_group(tamper)
        except Reject:
            pass
        else:
            raise AssertionError("misaligned header tuple accepted")
    assert not s1.safe_name("../invalid.flac")
    base = identity("0" * 40)
    blocked = dict(base, retrieved_at_utc="2026-10-10T00:00:00Z",
                   decision=BLOCKED,
                   failure_code="S2_NO_COMPLETE_MOVING_QUARTET")
    with tempfile.TemporaryDirectory(prefix="realman-s2-receipt-") as temp:
        verify_receipt(Path(temp), blocked, base)
        for change in (
            {"shipping_authority": True},
            {"decision": PASS},
            {"failure_code": "ARCHIVE_FAKE_ADMITTED"},
            {"members": []},
        ):
            bad = dict(blocked, **change)
            try:
                verify_receipt(Path(temp), bad, base)
            except Reject:
                pass
            else:
                raise AssertionError("blocked receipt forgery accepted")
    print("REALMAN_D2_S2_OFFLINE_SELF_TEST_PASS; no original audio bytes consumed")

def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=("self-test", "collect", "verify"))
    cli.add_argument("--workspace")
    cli.add_argument("--receipt")
    args = cli.parse_args()
    if args.action == "self-test":
        self_test()
        return 0
    require(bool(args.workspace and args.receipt), "S2_ARGUMENTS_MISSING")
    work = exact_work(args.workspace)
    path = Path(args.receipt).resolve()
    if args.action == "collect":
        return collect(work, path)
    verify_receipt(work, read_receipt(path), identity(source_sha()))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
