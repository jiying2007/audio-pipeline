#!/usr/bin/env python3
"""FE03 A2 D2-S0: pinned RealMAN scene-RAR remote *metadata*, never audio bytes.

Research-only, preregistered at https://github.com/jiying2007/audio-pipeline/issues/701.
No third-party package; no archive resolve/download endpoint or corpus selection.
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
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[3]
REV = "fea47505cae8041f4b652b0954ba61c77d2b6df1"
TREE_PATH = "val/ma_noisy_speech"
API_PATH = "/api/datasets/AISHELL/RealMAN/tree/" + REV + "/" + TREE_PATH
FIRST_URL = "https://huggingface.co" + API_PATH + "?recursive=false&expand=false"
SCENES = (
    "Auditorium", "BadmintonCourt1", "BasketballCourt1", "BasketballCourt2",
    "Cafeteria3", "Gym", "LivingRoom6", "LivingRoom8", "Market",
    "OfficeLobby", "OfficeRoom1", "OfficeRoom3", "SunkenPlaza1",
)
MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_PAGES = 5
MAX_TOTAL_SECONDS = 90
MAX_FILE_BYTES = 1024 ** 4
PASSED = "REALMAN_D2_S0_ARCHIVE_METADATA_CATALOGUED_ONLY"
BLOCKED = "REALMAN_D2_S0_ARCHIVE_METADATA_NOT_ADMITTED"
PARSER = ROOT / "tests/validation/frontend_evolution/realman_val_csv_d1.py"
D0 = ROOT / ".github/research/frontend-evolution-v1/realman-source-metadata-d0.json"


class Reject(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def require(ok: bool, code: str) -> None:
    if not ok:
        raise Reject(code)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read_json(raw: bytes):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            require(k not in result, "MALFORMED_TREE_JSON")
            result[k] = v
        return result

    def bad_constant(_):
        raise Reject("MALFORMED_TREE_JSON")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                          parse_constant=bad_constant)
    except (UnicodeError, ValueError) as err:
        if isinstance(err, Reject):
            raise
        raise Reject("MALFORMED_TREE_JSON") from None


def valid_url(url: str, *, first: bool = False) -> bool:
    try:
        p = urlsplit(url)
        if not (p.scheme == "https" and p.hostname == "huggingface.co"
                and p.port in (None, 443) and p.username is None
                and p.password is None and p.path == API_PATH
                and not p.fragment):
            return False
        pairs = parse_qsl(p.query, keep_blank_values=True, strict_parsing=True)
        values = dict(pairs)
        if len(values) != len(pairs) or not set(values).issubset(
                {"recursive", "expand", "cursor", "limit"}):
            return False
        if values.get("recursive") != "false" or values.get("expand") != "false":
            return False
        if "limit" in values and (not values["limit"].isdecimal()
                                  or not 1 <= int(values["limit"]) <= 1000):
            return False
        if first and ("cursor" in values or "limit" in values):
            return False
        if "cursor" in values and not 0 < len(values["cursor"]) <= 2048:
            return False
        return True
    except (ValueError, UnicodeError):
        return False


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Reject("TREE_REDIRECT_NOT_ADMITTED")


def read_page(response, start):
    length = response.headers.get("Content-Length")
    if length is not None:
        require(length.isdecimal(), "INVALID_TREE_LENGTH")
        require(int(length) <= MAX_PAGE_BYTES, "TREE_PAGE_TOO_LARGE")
    ctype = response.headers.get("Content-Type", "").split(";")[0].lower().strip()
    require(ctype in ("application/json", "application/json+hf"),
            "TREE_NOT_JSON")
    require(response.headers.get("Content-Encoding", "identity").lower()
            in ("", "identity"), "TREE_ENCODING_NOT_ADMITTED")
    buf = bytearray()
    while True:
        require(time.monotonic() - start < MAX_TOTAL_SECONDS,
                "TREE_TIMEOUT")
        block = response.read(min(65536, MAX_PAGE_BYTES + 1 - len(buf)))
        if not block:
            break
        buf.extend(block)
        require(len(buf) <= MAX_PAGE_BYTES, "TREE_PAGE_TOO_LARGE")
    require(bool(buf) and (length is None or int(length) == len(buf)),
            "TREE_INCOMPLETE")
    read_json(bytes(buf))
    return bytes(buf)


def next_link(value):
    if not value:
        return None
    candidates = []
    for part in value.split(","):
        m = re.fullmatch(r'\s*<([^<>]+)>\s*;\s*rel="?([^";\s]+)"?\s*', part)
        require(m is not None, "TREE_PAGINATION_INVALID")
        if m.group(2) == "next":
            candidates.append(m.group(1))
    require(len(candidates) <= 1, "TREE_PAGINATION_INVALID")
    if candidates:
        require(valid_url(candidates[0]), "TREE_PAGINATION_UNTRUSTED")
        return candidates[0]
    return None


def fetch_pages(work, raw_pages):
    require(valid_url(FIRST_URL, first=True), "TREE_URL_POLICY_DRIFT")
    client = build_opener(NoRedirect())
    url = FIRST_URL
    visited = set()
    start = time.monotonic()
    while url is not None:
        require(url not in visited, "TREE_PAGINATION_CYCLE")
        require(len(raw_pages) < MAX_PAGES, "TREE_PAGE_LIMIT_EXCEEDED")
        require(time.monotonic() - start < MAX_TOTAL_SECONDS,
                "TREE_TIMEOUT")
        visited.add(url)
        req = Request(url, headers={
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": "audio-pipeline-realman-d2-s0/1",
        })
        try:
            with client.open(req, timeout=20) as response:
                require(valid_url(response.geturl()), "TREE_URL_POLICY_DRIFT")
                raw = read_page(response, start)
                nxt = next_link(response.headers.get("Link"))
        except Reject:
            raise
        except (HTTPError, URLError, TimeoutError, OSError):
            # Do not log signed/query URLs, credentials, or server response bodies.
            raise Reject("REMOTE_TREE_INACCESSIBLE") from None
        page_id = len(raw_pages)
        (work / ("page-%02d.json" % page_id)).write_bytes(raw)
        raw_pages.append(raw)
        url = nxt
    require(bool(raw_pages), "REMOTE_TREE_INACCESSIBLE")
    return raw_pages


def analyze(raw_pages):
    require(0 < len(raw_pages) <= MAX_PAGES, "TREE_PAGE_LIMIT_EXCEEDED")
    entries = {}
    for raw in raw_pages:
        require(0 < len(raw) <= MAX_PAGE_BYTES, "TREE_PAGE_TOO_LARGE")
        payload = read_json(raw)
        require(isinstance(payload, list) and len(payload) <= 1000,
                "TREE_JSON_SHAPE_INVALID")
        for item in payload:
            require(isinstance(item, dict), "TREE_JSON_SHAPE_INVALID")
            path = item.get("path")
            require(isinstance(path, str) and len(path) <= 512 and
                    path == PurePosixPath(path).as_posix() and
                    path.startswith(TREE_PATH + "/") and
                    len(PurePosixPath(path).parts) == 3 and
                    ".." not in PurePosixPath(path).parts and
                    path not in entries, "TREE_UNSAFE_OR_DUPLICATE_PATH")
            entries[path] = item
    files, extras = [], []
    for path, item in sorted(entries.items()):
        leaf = path[len(TREE_PATH) + 1:]
        target = leaf[:-4] if leaf.endswith(".rar") else None
        if target not in SCENES:
            extras.append({"path": path, "kind": item.get("type", "unknown")})
            continue
        require(item.get("type") == "file", "TREE_FILE_TYPE_MISMATCH")
        size = item.get("size")
        require(type(size) is int and 0 < size <= MAX_FILE_BYTES,
                "TREE_FILE_SIZE_INVALID")
        oid = item.get("oid")
        require(isinstance(oid, str) and re.fullmatch(r"[0-9a-f]{40}", oid),
                "TREE_GIT_OID_MISSING")
        lfs = item.get("lfs")
        require(isinstance(lfs, dict), "TREE_REMOTE_SHA256_MISSING")
        remote_hash = lfs.get("oid", lfs.get("sha256"))
        require(isinstance(remote_hash, str) and
                re.fullmatch(r"[0-9a-f]{64}", remote_hash),
                "TREE_REMOTE_SHA256_INVALID")
        require(type(lfs.get("size")) is int and lfs["size"] == size,
                "TREE_LFS_SIZE_MISMATCH")
        files.append({
            "scene": target, "path": path, "declared_bytes": size,
            "git_blob_oid": oid, "remote_lfs_sha256": remote_hash,
            "independently_hashed_archive_bytes": False,
            "member_inventory_verified": False,
        })
    observed = {x["scene"] for x in files}
    missing = sorted(set(SCENES) - observed)
    catalog = {
        "remote_entry_count": len(entries),
        "declared_file_count": len(files),
        "declared_total_bytes": sum(x["declared_bytes"] for x in files),
        "remote_files": sorted(files, key=lambda x: x["scene"]),
        "missing_preregistered_scenes": missing,
        "unexpected_entries": extras,
        "archive_bytes_verified": False,
        "flac_members_verified": False,
        "scene_selected_for_audio": False,
    }
    return catalog, ("TREE_PREREGISTERED_SCENES_MISSING" if missing else None)


def source_sha():
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                  cwd=ROOT, text=True).strip()
    require(bool(re.fullmatch(r"[0-9a-f]{40}", sha))
            and sha == os.environ.get("GITHUB_SHA", ""), "EXECUTION_SHA_MISMATCH")
    return sha


def identity(sha):
    return {
        "schema_version": 1,
        "experiment_id": "FE03-A2-D2-S0-REALMAN-SCENE-ARCHIVE-TREE",
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/701",
        "provider": "AISHELL/RealMAN",
        "dataset_revision": REV,
        "metadata_api_path": API_PATH,
        "source_role": "val-mixed-noisy-disclosed-development",
        "source_scene_count": len(SCENES),
        "candidate_scenes": list(SCENES),
        "excluded_scene": "Car-Electric",
        "source_csv_static_sha256": "1f0be80d4ab1cc023e7599bf7e564f84acaf36ccad73fd59c992cc9e853f1233",
        "source_csv_moving_sha256": "542f04d011c2b6fbdd49bfa51c423942fe854e7e0615fb1f67954c762ad20bf5",
        "execution_sha": sha,
        "d2_script_sha256": digest(Path(__file__).read_bytes()),
        "d1q_script_sha256": digest(PARSER.read_bytes()),
        "d0_contract_sha256": digest(D0.read_bytes()),
        "max_pages": MAX_PAGES,
        "max_page_bytes": MAX_PAGE_BYTES,
        "research_purpose": "NONCOMMERCIAL_RESEARCH_ONLY",
        "original_d1_source_admitted": False,
        "audio_archive_downloaded": False,
        "audio_bytes_admitted": False,
        "doa_accuracy_qualified": False,
        "shipping_authority": False,
    }


def write_receipt(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"), allow_nan=False) + "\n",
                    encoding="utf-8")
    temp.replace(path)


def safe_work(path):
    work = Path(path).resolve()
    require(work != ROOT and ROOT not in work.parents, "UNSAFE_WORKSPACE")
    return work


def collect(work, path):
    result = identity(source_sha())
    result["retrieved_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pages = []
    try:
        work.mkdir(parents=True, exist_ok=True)
        pages = fetch_pages(work, pages)
        result["response_pages"] = [
            {"index": i, "size": len(b), "sha256": digest(b)}
            for i, b in enumerate(pages)
        ]
        catalog, problem = analyze(pages)
        result["catalog"] = catalog
        if problem:
            raise Reject(problem)
        result["decision"] = PASSED
        code = 0
    except Exception as exc:
        result["decision"] = BLOCKED
        result["failure_code"] = exc.code if isinstance(exc, Reject) else "TREE_INTERNAL_ERROR"
        result.setdefault("response_pages", [
            {"index": i, "size": len(b), "sha256": digest(b)}
            for i, b in enumerate(pages)
        ])
        code = 1
    write_receipt(path, result)
    print("decision=" + result["decision"] + " pages=" + str(len(result["response_pages"])) +
          " failure=" + result.get("failure_code", "NONE"), flush=True)
    return code


def validate_receipt(work, receipt, expected):
    for key, value in expected.items():
        require(receipt.get(key) == value, "RECEIPT_TAMPER")
    assert_time = receipt.get("retrieved_at_utc")
    require(isinstance(assert_time, str) and bool(re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", assert_time)),
        "RECEIPT_TAMPER")
    now = datetime.now(timezone.utc)
    try:
        age = (now - datetime.fromisoformat(assert_time.replace("Z", "+00:00"))).total_seconds()
    except ValueError:
        raise Reject("RECEIPT_TAMPER") from None
    require(-300 <= age <= 3600, "RECEIPT_TAMPER")
    page_infos = receipt.get("response_pages")
    require(isinstance(page_infos, list) and len(page_infos) <= MAX_PAGES,
            "RECEIPT_TAMPER")
    pages = []
    for i, info in enumerate(page_infos):
        raw = (work / ("page-%02d.json" % i)).read_bytes()
        require(info == {"index": i, "size": len(raw), "sha256": digest(raw)},
                "RECEIPT_TAMPER")
        pages.append(raw)
    if receipt.get("decision") == PASSED:
        require("failure_code" not in receipt and len(pages) >= 1, "RECEIPT_TAMPER")
        catalog, err = analyze(pages)
        require(err is None and receipt.get("catalog") == catalog, "RECEIPT_TAMPER")
        require(set(receipt) == set(expected) |
                {"retrieved_at_utc", "response_pages", "catalog", "decision"},
                "RECEIPT_TAMPER")
    else:
        require(receipt.get("decision") == BLOCKED and
                isinstance(receipt.get("failure_code"), str) and
                receipt["failure_code"] != "" and
                "audio_bytes_admitted" in receipt and
                receipt["audio_bytes_admitted"] is False,
                "RECEIPT_TAMPER")
        if pages:
            try:
                catalog, err = analyze(pages)
                if err:
                    require(receipt["failure_code"] == err and
                            receipt.get("catalog") == catalog, "RECEIPT_TAMPER")
                else:
                    # The caller may have failed after downloading a page.
                    require(receipt["failure_code"] in
                            {"REMOTE_TREE_INACCESSIBLE", "TREE_TIMEOUT",
                             "TREE_PAGE_LIMIT_EXCEEDED",
                             "TREE_PAGINATION_INVALID", "TREE_PAGINATION_UNTRUSTED",
                             "TREE_PAGINATION_CYCLE"}, "RECEIPT_TAMPER")
            except Reject as ex:
                require(receipt["failure_code"] == ex.code or
                        ex.code == "RECEIPT_TAMPER", "RECEIPT_TAMPER")
        require(set(receipt) == set(expected) |
                {"retrieved_at_utc", "response_pages", "catalog", "decision",
                 "failure_code"} if "catalog" in receipt else
                set(receipt) == set(expected) |
                {"retrieved_at_utc", "response_pages", "decision", "failure_code"},
                "RECEIPT_TAMPER")


def verify(work, path):
    receipt = read_json(path.read_bytes())
    require(isinstance(receipt, dict), "RECEIPT_TAMPER")
    validate_receipt(work, receipt, identity(source_sha()))
    print("receipt_readback_consistent=true decision=" + receipt["decision"])


def self_test():
    good = [{"type": "file",
             "path": TREE_PATH + "/" + scene + ".rar",
             "size": 128, "oid": "a" * 40,
             "lfs": {"oid": "b" * 64, "size": 128, "pointerSize": 131}}
            for scene in SCENES]
    raw = json.dumps(good, separators=(",", ":")).encode("utf-8")
    catalog, problem = analyze([raw])
    assert problem is None and catalog["declared_file_count"] == 13
    assert catalog["declared_total_bytes"] == 1664
    assert catalog["missing_preregistered_scenes"] == []
    assert catalog["scene_selected_for_audio"] is False
    assert valid_url(FIRST_URL, first=True)
    assert not valid_url(FIRST_URL.replace(REV, "main"), first=True)
    assert not valid_url(FIRST_URL.replace("huggingface.co", "evil.example"),
                         first=True)
    assert not valid_url(FIRST_URL + "&token=sensitive")
    assert next_link(None) is None
    assert next_link('<' + FIRST_URL + '&cursor=abc>; rel="next"') is not None
    bad_cases = [
        (good[:-1], "TREE_PREREGISTERED_SCENES_MISSING"),
        (good + [good[0]], "TREE_UNSAFE_OR_DUPLICATE_PATH"),
        ([dict(good[0], size=0)] + good[1:], "TREE_FILE_SIZE_INVALID"),
        ([dict(good[0], lfs=None)] + good[1:], "TREE_REMOTE_SHA256_MISSING"),
        ([dict(good[0], path=TREE_PATH + "/../bad.rar")] + good[1:],
         "TREE_UNSAFE_OR_DUPLICATE_PATH"),
    ]
    for entries, code in bad_cases:
        try:
            _, outcome = analyze([json.dumps(entries).encode()])
            require(outcome != code, code)
        except Reject as err:
            assert err.code == code
        else:
            raise AssertionError("invalid tree was accepted: " + code)
    try:
        read_json(b'{"k":1,"k":2}')
    except Reject as err:
        assert err.code == "MALFORMED_TREE_JSON"
    else:
        raise AssertionError("duplicate source JSON field accepted")
    with tempfile.TemporaryDirectory(prefix="realman-d2-s0-selftest-") as td:
        work = Path(td)
        (work / "page-00.json").write_bytes(raw)
        checked = identity("0" * 40)
        receipt = dict(checked)
        receipt.update({
            "retrieved_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "response_pages": [{"index": 0, "size": len(raw), "sha256": digest(raw)}],
            "catalog": catalog,
            "decision": PASSED,
        })
        validate_receipt(work, receipt, checked)
        mutants = [
            lambda r: r["response_pages"][0].update(sha256="0" * 64),
            lambda r: r["catalog"].update(declared_file_count=12),
            lambda r: r["catalog"]["remote_files"][0].update(
                independently_hashed_archive_bytes=True),
            lambda r: r.update(original_d1_source_admitted=True),
            lambda r: r.update(decision=BLOCKED),
        ]
        for mutate in mutants:
            changed = copy.deepcopy(receipt)
            mutate(changed)
            try:
                validate_receipt(work, changed, checked)
            except Reject:
                pass
            else:
                raise AssertionError("tampered D2-S0 receipt accepted")
    print("REALMAN_D2_S0_OFFLINE_SELF_TEST_PASS; no remote bytes consumed")


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=("self-test", "collect", "verify"))
    cli.add_argument("--workspace")
    cli.add_argument("--receipt")
    args = cli.parse_args()
    if args.action == "self-test":
        self_test()
        return 0
    require(bool(args.workspace and args.receipt), "MISSING_ARGUMENTS")
    work, path = safe_work(args.workspace), Path(args.receipt).resolve()
    if args.action == "collect":
        return collect(work, path)
    verify(work, path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
