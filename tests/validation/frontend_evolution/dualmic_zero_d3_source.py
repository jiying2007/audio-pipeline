#!/usr/bin/env python3
"""D3 original-input admission only: no new DSP/model execution."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import dualmic_stages_source as source
import dualmic_gain_d2 as d2

ROOT = Path(__file__).resolve().parents[3]
FREEZE = "bfc066da9e95035530bace2468e5d31bdabb1a5a"
LOCK_PATH = "docs/research/frontend-evolution-v1/dualmic-zero-d3-input-lock.json"
PLAN_PATH = "docs/research/frontend-evolution-v1/DUALMIC_ZERO_D3_PLAN.zh-CN.md"
need = source.need


def frozen_lock():
    pinned = {LOCK_PATH: "d973fcd88a52787b6026ddb8add815c5f4475e54",
              PLAN_PATH: "070545d075cc32ccdf33cd532d450170419be986"}
    for name, expected in pinned.items():
        raw = (ROOT / name).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        need(blob == expected, "D3_FROZEN_CONTRACT_CHANGED")
    lock = json.loads((ROOT / LOCK_PATH).read_bytes())
    for name, expected in lock["helper_git_blobs"].items():
        raw = (ROOT / name).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        need(blob == expected, "D3_ORIGINAL_READER_CHANGED")
    return lock


def metadata(run, listing, lock):
    need(type(run) is dict and run.get("id") == lock["run_id"] and
         run.get("head_sha") == lock["source_revision"] and
         type(run.get("run_attempt")) is int and run["run_attempt"] == lock["run_attempt"] and
         run.get("status") == "completed" and run.get("conclusion") == "success",
         "D3_ORIGINAL_RUN_MISMATCH")
    need(type(listing) is dict and type(listing.get("total_count")) is int and
         0 <= listing["total_count"] <= 100 and type(listing.get("artifacts")) is list and
         len(listing["artifacts"]) == listing["total_count"], "D3_ARTIFACT_LIST_INCOMPLETE")
    spec = lock["artifact"]
    matches = [x for x in listing["artifacts"] if x.get("id") == spec["artifact_id"] or x.get("name") == spec["name"]]
    need(len(matches) == 1, "D3_ORIGINAL_ARTIFACT_ABSENT_OR_AMBIGUOUS")
    item = matches[0]
    need(item.get("id") == spec["artifact_id"] and item.get("name") == spec["name"] and
         item.get("size_in_bytes") == spec["zip_bytes"] and item.get("digest") == "sha256:" + spec["sha256"] and
         item.get("expired") is False and item.get("workflow_run", {}).get("id") == lock["run_id"] and
         item["workflow_run"].get("head_sha") == lock["source_revision"], "D3_ORIGINAL_ARTIFACT_MISMATCH")


def acquire(output):
    start = time.monotonic()
    need(not output.exists() and not output.is_symlink(), "D3_NEW_OUTPUT_REQUIRED")
    output.mkdir(parents=True)
    receipt = {"experiment": "FE-DUALMIC-ZERO-D3-INPUT", "status": "FAIL",
               "DSP_executed": False, "models_executed": False, "promotion_allowed": False}
    try:
        lock = frozen_lock()
        budget = lock["budget_seconds"]
        token = os.environ.get("GH_TOKEN", "")
        need(bool(token), "D3_GITHUB_READ_TOKEN_REQUIRED")
        api = "https://api.github.com/repos/" + lock["repository"]
        run = source.api_json(api + "/actions/runs/" + str(lock["run_id"]), token, start, budget)
        listing = source.api_json(api + "/actions/runs/" + str(lock["run_id"]) + "/artifacts?per_page=100",
                                  token, start, budget)
        metadata(run, listing, lock)
        archive = output / "original.zip"
        spec = lock["artifact"]
        source.fetch_zip(spec["artifact_id"], archive, spec["zip_bytes"], token, start, budget)
        checked = source.validate_extract(archive, output / "original", spec, lock, start, budget)
        need(checked["uncompressed_bytes"] == lock["max_uncompressed_bytes"], "D3_ORIGINAL_TOTAL_BYTES")
        source.dump(output / "member-hashes.json", checked)
        parent, prior = output / "original/result", output / "original/gain-d2"
        need(source.digest(prior / "report.json") == lock["report_sha256"] and
             source.digest(prior / "artifact-manifest.json") == lock["manifest_sha256"],
             "D3_ORIGINAL_REPORT_IDENTITY")
        manifest = d2.read_json(prior / "artifact-manifest.json")
        need(manifest["files"] == d2.payload_inventory(prior), "D3_ORIGINAL_D2_PAYLOAD_CHANGED")
        # The original reader remains byte-frozen and only reads retained evidence.
        recomputed = d2.analysis_payload(prior, parent, start)
        need(recomputed == d2.read_json(prior / "report.json"), "D3_ORIGINAL_D2_READBACK_DIFFERS")
        need(recomputed["source_revision"] == lock["source_revision"] and
             recomputed["case_count"] == 60 and recomputed["frames"] == 35916 and
             recomputed["samples"] == 5746560, "D3_ORIGINAL_SOURCE_OR_MATRIX")
        (output / "original-input-lock.json").write_bytes((prior / "input-lock.json").read_bytes())
        (output / "original-report.json").write_bytes((prior / "report.json").read_bytes())
        (output / "original-source-identity.json").write_bytes((prior / "source/identity.json").read_bytes())
        receipt.update(status="INPUT_ADMITTED_NO_DSP_EXECUTION", freeze=FREEZE,
                       source_revision=lock["source_revision"], artifact=spec,
                       member_count=checked["members"], uncompressed_bytes=checked["uncompressed_bytes"],
                       original_D2_readback_exact=True, case_count=60, frames=35916, samples=5746560)
        source.remaining(start, budget)
    except Exception as error:
        receipt.update(status="FAIL", failure_type=type(error).__name__,
                       failure_reason=str(error) if isinstance(error, ValueError) else "input admission failed; no fallback")
        raise
    finally:
        receipt.update(elapsed_seconds=time.monotonic() - start, budget_seconds=300,
                       elapsed_scope="through first receipt write; final write deadline checked")
        source.dump(output / "admission.json", receipt)
        if time.monotonic() - start > 300:
            receipt.update(status="FAIL", failure_reason="D3_FINAL_WRITE_BUDGET_EXCEEDED",
                           elapsed_seconds=time.monotonic() - start)
            source.dump(output / "admission.json", receipt)
            raise ValueError("D3_FINAL_WRITE_BUDGET_EXCEEDED")
    print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        acquire(args.output.resolve())
    except Exception as error:
        # Never emit signed artifact storage URLs or authentication material.
        print("D3_INPUT_ADMISSION_FAILED: " + type(error).__name__)
        raise SystemExit(1)
