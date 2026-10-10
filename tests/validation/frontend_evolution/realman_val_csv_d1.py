#!/usr/bin/env python3
"""FE03 A2 D1: bounded RealMAN val CSV source vetting; no audio or DOA scores."""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
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

def parser_reason(err):
    # Only fixed first-party D0 error labels are safe to publish; no CSV rows.
    message = str(err)
    prefix = "FE03 A2 metadata: "
    if message.startswith(prefix):
        return message[len(prefix):][:100]
    return type(err).__name__

def source_headers(raw):
    try:
        decoded = raw.decode("utf-8-sig")
        header = next(csv.reader(io.StringIO(decoded, newline="")))
        if len(header) <= 64 and all(len(x) <= 150 for x in header):
            return header
    except (UnicodeError, csv.Error, StopIteration):
        pass
    return []

def unadmitted_distance_diagnostics(raw):
    # Source-only structural evidence, never a valid-distance admission.
    try:
        stream = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
        counts = {"unadmitted_structural_rows": 0,
                  "nonpositive_distance_rows": 0,
                  "zero_distance_rows": 0,
                  "negative_distance_rows": 0,
                  "nonfinite_distance_rows": 0,
                  "nonnumeric_distance_rows": 0}
        modes, by_scene = Counter(), Counter()
        min_negative, max_negative = None, None
        for row in stream:
            counts["unadmitted_structural_rows"] += 1
            if counts["unadmitted_structural_rows"] > 100000:
                return {"diagnostic_error": "STRUCTURAL_ROW_BOUND_EXCEEDED"}
            raw_cell = row.get("distance")
            if not isinstance(raw_cell, str):
                counts["nonnumeric_distance_rows"] += 1
                continue
            try:
                values = [float(x.strip()) for x in raw_cell.split(",")]
            except ValueError:
                counts["nonnumeric_distance_rows"] += 1
                continue
            negative = [v for v in values if v < 0]
            counts["zero_distance_rows"] += int(any(x == 0 for x in values))
            counts["negative_distance_rows"] += int(bool(negative))
            counts["nonfinite_distance_rows"] += int(any(not math.isfinite(x) for x in values))
            counts["nonpositive_distance_rows"] += int(any(x <= 0 for x in values))
            if negative:
                name = row.get("filename", "")
                parts = name.split("/") if isinstance(name, str) else []
                scene = (parts[2] if len(parts) == 6 and
                         parts[:2] == ["val", "ma_noisy_speech"] and
                         re.fullmatch(r"[A-Za-z0-9_.-]{1,60}", parts[2]) else
                         "UNCLASSIFIED")
                by_scene[scene] += 1
                if len(by_scene) > 64:
                    return {"diagnostic_error": "TOO_MANY_SCENES"}
                for v in negative:
                    key = format(v, ".12g")
                    modes[key] += 1
                    min_negative = v if min_negative is None else min(v, min_negative)
                    max_negative = v if max_negative is None else max(v, max_negative)
        counts["negative_value_mode_top8"] = [
            {"value": value, "occurrences": n} for value, n in
            sorted(modes.items(), key=lambda item: (-item[1], item[0]))[:8]
        ]
        counts["negative_rows_by_scene"] = [
            {"scene": scene, "rows": n} for scene, n in sorted(by_scene.items())
        ]
        counts["negative_distance_min"] = min_negative
        counts["negative_distance_max"] = max_negative
        counts["distinct_negative_values"] = len(modes)
        return counts
    except (UnicodeError, csv.Error):
        return {"diagnostic_error": "UNPARSABLE_STRUCTURE"}

def admit(work, output):
    result = authority(exact_source())
    scenes, failures = {}, []
    try:
        work.mkdir(parents=True, exist_ok=True)
        # Independently collect both exact raw CSV identities, even when
        # one D0 semantic parser rejects the official source schema.
        for family, filename in SOURCES:
            try:
                raw = download(filename)
                (work / (family + ".csv")).write_bytes(raw)
                entry = {"family": family, "path": filename,
                         "bytes": len(raw), "sha256": sha(raw)}
                result["files"].append(entry)
                print("source=" + family + " bytes=" + str(len(raw))
                      + " sha256=" + entry["sha256"], flush=True)
            except Exception as err:
                failures.append({"family": family, "failure_code": classify(err)})
                continue
            try:
                values, scene_names = inspect(raw, family)
                entry.update(values)
                scenes[family] = scene_names
            except Exception as err:
                entry["unadmitted_raw_headers"] = source_headers(raw)
                entry["unadmitted_distance_diagnostics"] = unadmitted_distance_diagnostics(raw)
                entry["parse_failure_reason"] = parser_reason(err)
                failures.append({"family": family, "failure_code": classify(err),
                                 "parse_failure_reason": parser_reason(err)})
        if failures:
            result["decision"] = BLOCKED
            result["csv_bytes_verified"] = False
            result["failure_code"] = failures[0]["failure_code"]
            result["blocked_sources"] = failures
            code = 1
        else:
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

def verify_payload(work, receipt, expected):
    # Rehash real raw bytes and reconstruct every semantic receipt claim.
    for key, value in expected.items():
        if key != "files":
            require(receipt.get(key) == value)
    source_files = receipt.get("files")
    require(isinstance(source_files, list) and len(source_files) <= 2)
    source_index = {family: i for i, (family, _) in enumerate(SOURCES)}
    items = {}
    last_index = -1
    for item in source_files:
        require(isinstance(item, dict))
        family = item.get("family")
        require(family in source_index and source_index[family] > last_index)
        last_index = source_index[family]
        items[family] = item
    errors, scenes = [], {}
    for family, path in SOURCES:
        item = items.get(family)
        if item is None:
            blocked_sources = receipt.get("blocked_sources", [])
            matching = [entry for entry in blocked_sources
                        if isinstance(entry, dict) and entry.get("family") == family]
            require(len(matching) == 1 and
                    matching[0].get("failure_code") in
                    {"REMOTE_METADATA_INACCESSIBLE", "SOURCE_BYTES_TOO_LARGE",
                     "SOURCE_REDIRECT_NOT_ADMITTED", "SOURCE_TRANSFER_INCOMPLETE",
                     "SOURCE_CONTENT_NOT_CSV"})
            errors.append({"family": family,
                           "failure_code": matching[0]["failure_code"]})
            continue
        require(item.get("path") == path)
        data = (work / (family + ".csv")).read_bytes()
        core = {"family": family, "path": path,
                "bytes": len(data), "sha256": sha(data)}
        require(0 < len(data) <= CAP and
                item.get("bytes") == len(data) and
                item.get("sha256") == sha(data))
        try:
            metrics, member_scenes = inspect(data, family)
        except (ValueError, csv.Error, UnicodeError) as err:
            observed = {
                **core,
                "unadmitted_raw_headers": source_headers(data),
                "unadmitted_distance_diagnostics": unadmitted_distance_diagnostics(data),
                "parse_failure_reason": parser_reason(err),
            }
            require(item == observed)
            errors.append({
                "family": family, "failure_code": classify(err),
                "parse_failure_reason": parser_reason(err),
            })
        else:
            require(item == dict(core, **metrics))
            scenes[family] = member_scenes
    if errors:
        require(receipt.get("decision") == BLOCKED and
                receipt.get("csv_bytes_verified") is False and
                receipt.get("blocked_sources") == errors and
                receipt.get("failure_code") == errors[0]["failure_code"] and
                "common_label_scenes" not in receipt and
                "common_label_scene_count" not in receipt)
        require(set(receipt) == set(expected) |
                {"decision", "csv_bytes_verified", "failure_code", "blocked_sources"})
    else:
        require(receipt.get("decision") == PASS and
                receipt.get("csv_bytes_verified") is True and
                len(source_files) == 2 and "failure_code" not in receipt and
                "blocked_sources" not in receipt)
        common = sorted(scenes["static"] & scenes["moving"])
        require(receipt.get("common_label_scenes") == common and
                receipt.get("common_label_scene_count") == len(common))
        require(set(receipt) == set(expected) |
                {"decision", "csv_bytes_verified", "common_label_scenes",
                 "common_label_scene_count"})


def verify(work, path):
    receipt = d0.read_json(path)
    verify_payload(work, receipt, authority(exact_source()))
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
    diagnostic = unadmitted_distance_diagnostics(
        example(False).replace(b"1.3", b"0"))
    assert diagnostic["unadmitted_structural_rows"] == 1
    assert diagnostic["zero_distance_rows"] == 1
    assert diagnostic["nonpositive_distance_rows"] == 1
    diagnostic_negative = unadmitted_distance_diagnostics(
        example(False).replace(b"1.3", b"-1"))
    assert diagnostic_negative["negative_distance_rows"] == 1
    assert diagnostic_negative["distinct_negative_values"] == 1
    assert diagnostic_negative["negative_value_mode_top8"] == [
        {"value": "-1", "occurrences": 1}]
    assert diagnostic_negative["negative_rows_by_scene"] == [
        {"scene": "Gym", "rows": 1}]
    assert diagnostic_negative["negative_distance_min"] == -1
    assert diagnostic_negative["negative_distance_max"] == -1
    assert diagnostic_negative["nonpositive_distance_rows"] == 1
    with tempfile.TemporaryDirectory(prefix="realman-d1-receipt-") as workdir:
        work = Path(workdir)
        commit = "0" * 40
        receipt = authority(commit)
        bstatic = example(False).replace(b"1.3", b"-1")
        bmoving = example(True)
        (work / "static.csv").write_bytes(bstatic)
        (work / "moving.csv").write_bytes(bmoving)
        entry_static = {
            "family": "static", "path": SOURCES[0][1],
            "bytes": len(bstatic), "sha256": sha(bstatic),
            "unadmitted_raw_headers": source_headers(bstatic),
            "unadmitted_distance_diagnostics": unadmitted_distance_diagnostics(bstatic),
            "parse_failure_reason": "nonpositive source distance",
        }
        metrics_moving, _ = inspect(bmoving, "moving")
        entry_moving = {
            "family": "moving", "path": SOURCES[1][1],
            "bytes": len(bmoving), "sha256": sha(bmoving),
            **metrics_moving,
        }
        receipt.update({
            "files": [entry_static, entry_moving],
            "decision": BLOCKED,
            "csv_bytes_verified": False,
            "failure_code": "CSV_SCHEMA_MISMATCH",
            "blocked_sources": [
                {"family": "static", "failure_code": "CSV_SCHEMA_MISMATCH",
                 "parse_failure_reason": "nonpositive source distance"},
            ],
        })
        verify_payload(work, receipt, authority(commit))
        mutations = [
            lambda r: r["files"][0]["unadmitted_distance_diagnostics"].update(
                negative_distance_rows=0),
            lambda r: r["files"][0].update(sha256="0" * 64),
            lambda r: r["files"][0].update(parse_failure_reason="accepted"),
            lambda r: r["blocked_sources"][0].update(
                failure_code="REMOTE_METADATA_INACCESSIBLE"),
            lambda r: r.update(decision=PASS),
            lambda r: r.update(csv_bytes_verified=True),
            lambda r: r.update(common_label_scenes=["Gym"]),
        ]
        for mutate in mutations:
            changed = copy.deepcopy(receipt)
            mutate(changed)
            try:
                verify_payload(work, changed, authority(commit))
            except (ValueError, KeyError):
                pass
            else:
                raise AssertionError("mutated blocked D1 receipt accepted")
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
