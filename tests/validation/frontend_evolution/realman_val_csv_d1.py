#!/usr/bin/env python3
"""FE03 A2 D1: bounded RealMAN val CSV source vetting; no audio or DOA scores."""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import realman_source_metadata_d0 as d0

ROOT = Path(__file__).resolve().parents[3]
REV = "fea47505cae8041f4b652b0954ba61c77d2b6df1"
SOURCES = (("static", "val/val_static_source_location.csv"),
           ("moving", "val/val_moving_source_location.csv"))
CAP = 16 * 1024 * 1024
PASS = "REALMAN_VAL_CSV_BYTES_VERIFIED_METADATA_ONLY"
BLOCKED = "REALMAN_VAL_CSV_SOURCE_ADMISSION_BLOCKED"
BLOCKERS = {"REMOTE_METADATA_INACCESSIBLE", "SOURCE_BYTES_TOO_LARGE",
            "SOURCE_REDIRECT_NOT_ADMITTED", "SOURCE_TRANSFER_INCOMPLETE",
            "SOURCE_CONTENT_NOT_CSV", "CSV_SCHEMA_MISMATCH",
            "TIMESTAMP_REPRESENTATION_UNRESOLVED", "D1_INTERNAL_ERROR"}

class AdmissionError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code

def require(condition, code="D1_INTERNAL_ERROR"):
    if not condition:
        raise AdmissionError(code)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def url_for(path):
    require(path in [x[1] for x in SOURCES], "SOURCE_REDIRECT_NOT_ADMITTED")
    return "https://huggingface.co/datasets/AISHELL/RealMAN/resolve/" + REV + "/" + path

def trusted(url):
    try:
        p = urlsplit(url)
        host = (p.hostname or "").lower()
        return (p.scheme == "https" and p.username is None and p.password is None
                and p.port in (None, 443) and bool(p.path)
                and (host == "huggingface.co" or host.endswith(".huggingface.co")
                     or host == "hf.co" or host.endswith(".hf.co")))
    except ValueError:
        return False

class LockedRedirects(HTTPRedirectHandler):
    max_redirections = 5
    max_repeats = 2
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urljoin(req.full_url, newurl)
        require(trusted(target), "SOURCE_REDIRECT_NOT_ADMITTED")
        return super().redirect_request(req, fp, code, msg, headers, target)

def bounded_read(response):
    length = response.headers.get("Content-Length")
    if length is not None:
        require(length.isdecimal(), "SOURCE_TRANSFER_INCOMPLETE")
        require(int(length) <= CAP, "SOURCE_BYTES_TOO_LARGE")
    ctype = response.headers.get("Content-Type", "").split(";")[0].lower().strip()
    require(ctype not in ("text/html", "application/json", "text/xml"),
            "SOURCE_CONTENT_NOT_CSV")
    require(response.headers.get("Content-Encoding", "identity").lower()
            in ("", "identity"), "SOURCE_TRANSFER_INCOMPLETE")
    start, raw = time.monotonic(), bytearray()
    while True:
        require(time.monotonic() - start <= 90, "REMOTE_METADATA_INACCESSIBLE")
        chunk = response.read(min(65536, CAP + 1 - len(raw)))
        if not chunk:
            break
        raw.extend(chunk)
        require(len(raw) <= CAP, "SOURCE_BYTES_TOO_LARGE")
    payload = bytes(raw)
    require(bool(payload), "SOURCE_TRANSFER_INCOMPLETE")
    if length is not None:
        require(len(payload) == int(length), "SOURCE_TRANSFER_INCOMPLETE")
    require(not payload[:256].lstrip().lower().startswith(
        (b"<html", b"<!doctype html", b"<?xml")), "SOURCE_CONTENT_NOT_CSV")
    return payload

def download(path):
    url = url_for(path)
    require(trusted(url), "SOURCE_REDIRECT_NOT_ADMITTED")
    req = Request(url, headers={"Accept": "text/csv,text/plain,application/octet-stream",
                                "Accept-Encoding": "identity",
                                "User-Agent": "audio-pipeline-realman-val-d1/1"})
    try:
        with build_opener(LockedRedirects()).open(req, timeout=20) as response:
            require(trusted(response.geturl()), "SOURCE_REDIRECT_NOT_ADMITTED")
            return bounded_read(response)
    except AdmissionError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError):
        # Never print signed redirect query strings or external response bodies.
        raise AdmissionError("REMOTE_METADATA_INACCESSIBLE") from None

def exact_source():
    checked = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                      cwd=ROOT, text=True).strip()
    expected = os.environ.get("GITHUB_SHA", "")
    require(bool(re.fullmatch(r"[0-9a-f]{40}", expected)) and expected == checked)
    return checked

def authority(commit):
    p = d0.authoritative_contract()
    require(p["dataset_repo"] == "AISHELL/RealMAN" and p["dataset_revision"] == REV
            and p["static_label_path"] == SOURCES[0][1]
            and p["moving_label_path"] == SOURCES[1][1]
            and p["physical_slot_map"] == [1, 3, 5, 7])
    return {
        "schema_version": 1,
        "experiment_id": "FE03-A2-REALMAN-VAL-CSV-D1",
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/697",
        "provider": "AISHELL/RealMAN", "dataset_revision": REV,
        "source_role": "val-disclosed-development",
        "research_purpose": "NONCOMMERCIAL_RESEARCH_ONLY",
        "effective_data_notice": "CC-BY-NC-4.0-NONCOMMERCIAL-RESEARCH",
        "execution_sha": commit,
        "d0_parser_sha256": sha(Path(d0.__file__).read_bytes()),
        "d0_contract_sha256": sha(d0.CONTRACT.read_bytes()),
        "d1_script_sha256": sha(Path(__file__).read_bytes()),
        "c2_physical": [1, 5], "c4_physical": [1, 3, 5, 7],
        "per_csv_hard_cap_bytes": CAP,
        "audio_bytes_admitted": False, "archive_members_verified": False,
        "timebase_calibrated": False, "doa_scores_reported": False,
        "shipping_authority": False, "product_qualification": False,
        "files": [],
    }

def inspect(raw, family):
    records = d0.parse_labels(raw, family, d0.authoritative_contract())
    headers = next(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
    names = sorted(x["filename"] for x in records)
    scenes = {x["scene"] for x in records}
    semantic = "".join(x["filename"] + "\t" + x["row_sha256"] + "\n"
                       for x in sorted(records, key=lambda r: r["filename"]))
    return {
        "headers": headers, "row_count": len(records),
        "unique_scene_count": len(scenes),
        "first_lexical_filename": names[0], "last_lexical_filename": names[-1],
        "semantic_records_sha256": sha(semantic.encode("utf-8")),
    }, scenes

def classify(err):
    if isinstance(err, AdmissionError):
        return err.code
    if isinstance(err, (ValueError, csv.Error, UnicodeError)):
        return ("TIMESTAMP_REPRESENTATION_UNRESOLVED"
                if "timestamp" in str(err).lower() or "interval" in str(err).lower()
                else "CSV_SCHEMA_MISMATCH")
    return "D1_INTERNAL_ERROR"

def workspace_path(path):
    work = Path(path).resolve()
    require(work != ROOT and ROOT not in work.parents)
    return work

def record(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"), allow_nan=False) + "\n",
                    encoding="utf-8")
    temp.replace(path)

def admit(work, output):
    result = authority(exact_source())
    scenes = {}
    try:
        work.mkdir(parents=True, exist_ok=True)
        for family, filename in SOURCES:
            raw = download(filename)
            (work / (family + ".csv")).write_bytes(raw)
            entry = {"family": family, "path": filename,
                     "bytes": len(raw), "sha256": sha(raw)}
            result["files"].append(entry)
            values, scene_names = inspect(raw, family)
            entry.update(values)
            scenes[family] = scene_names
            print("source=" + family + " bytes=" + str(len(raw))
                  + " sha256=" + entry["sha256"], flush=True)
        common = sorted(scenes["static"] & scenes["moving"])
        result["common_label_scenes"] = common
        result["common_label_scene_count"] = len(common)
        result["decision"] = PASS
        result["csv_bytes_verified"] = True
        code = 0
    except Exception as err:
        result["decision"] = BLOCKED
        result["csv_bytes_verified"] = False
        result["failure_code"] = classify(err)
        code = 1
    record(output, result)
    print("decision=" + result["decision"]
          + " failure_code=" + result.get("failure_code", "NONE"), flush=True)
    return code

def verify(work, path):
    receipt = d0.read_json(path)
    expected = authority(exact_source())
    for key, value in expected.items():
        if key != "files":
            require(receipt.get(key) == value)
    files = receipt.get("files")
    require(isinstance(files, list) and len(files) <= 2)
    seen = {}
    for n, item in enumerate(files):
        family, filename = SOURCES[n]
        require(item.get("family") == family and item.get("path") == filename)
        raw = (work / (family + ".csv")).read_bytes()
        require(0 < len(raw) <= CAP and item.get("bytes") == len(raw)
                and item.get("sha256") == sha(raw))
        if receipt.get("decision") == PASS:
            values, scene_names = inspect(raw, family)
            require(item == dict({"family": family, "path": filename,
                                  "bytes": len(raw), "sha256": sha(raw)}, **values))
            seen[family] = scene_names
    if receipt.get("decision") == PASS:
        require(len(files) == 2 and receipt.get("csv_bytes_verified") is True
                and "failure_code" not in receipt)
        common = sorted(seen["static"] & seen["moving"])
        require(receipt.get("common_label_scenes") == common
                and receipt.get("common_label_scene_count") == len(common))
    else:
        require(receipt.get("decision") == BLOCKED
                and receipt.get("csv_bytes_verified") is False
                and receipt.get("failure_code") in BLOCKERS
                and "common_label_scenes" not in receipt)
    print("receipt_consistent=true decision=" + receipt["decision"])

def self_test():
    p = d0.authoritative_contract()
    def example(moving):
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(d0.REQUIRED_CSV))
        writer.writeheader()
        part = "moving" if moving else "static"
        prefix = "VAL_M_" if moving else "VAL_S_"
        writer.writerow({
            "filename": "val/ma_noisy_speech/Gym/" + part + "/P0001/"
                        + prefix + "GYM_P0001_0001.flac",
            "real_st": "4800", "real_ed": "9600",
            "video_st": "5000", "video_ed": "10000",
            "angle(°)": "30,35" if moving else "30",
            "distance": "1.3,1.4" if moving else "1.3",
            "ele": "0,0" if moving else "0",
        })
        return buf.getvalue().encode()
    a, scenes_a = inspect(example(False), "static")
    b, scenes_b = inspect(example(True), "moving")
    assert a["row_count"] == b["row_count"] == 1 and scenes_a == scenes_b == {"Gym"}
    assert trusted(url_for(SOURCES[0][1]))
    assert trusted("https://cas-bridge.xethub.hf.co/blob")
    assert not trusted("https://huggingface.co.evil.net/a")
    assert not trusted("http://huggingface.co/a")
    for invalid in ("val/no.csv", "../val/val_static_source_location.csv"):
        try:
            url_for(invalid)
        except AdmissionError:
            pass
        else:
            raise AssertionError("unfrozen source URL accepted")
    for bad in (example(False).replace(b"4800", b"abc"),
                example(False).replace(b"angle(", b"wrong(")):
        try:
            inspect(bad, "static")
        except (ValueError, csv.Error):
            pass
        else:
            raise AssertionError("invalid source CSV accepted")
    class Oversized:
        headers = {"Content-Length": str(CAP + 1)}
    try:
        bounded_read(Oversized())
    except AdmissionError as e:
        assert e.code == "SOURCE_BYTES_TOO_LARGE"
    else:
        raise AssertionError("oversized CSV accepted")
    print("REALMAN_VAL_CSV_D1_OFFLINE_SELF_TEST_PASS; no external data")

def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=("self-test", "admit", "verify"))
    cli.add_argument("--workspace")
    cli.add_argument("--receipt")
    args = cli.parse_args()
    if args.action == "self-test":
        self_test()
        return 0
    require(bool(args.workspace and args.receipt))
    work, output = workspace_path(args.workspace), Path(args.receipt).resolve()
    if args.action == "admit":
        return admit(work, output)
    verify(work, output)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
