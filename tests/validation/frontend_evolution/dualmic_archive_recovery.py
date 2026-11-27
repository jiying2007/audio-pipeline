#!/usr/bin/env python3
"""Recover the fixed D1/D2 original ZIP offline, then run frozen read-only checks.

The repository's immutable D3 input lock is the metadata authority.  This
entrypoint does not query Actions, assert that an artifact is still active, or
write the old live-acquisition receipt.  It never executes DSP or models.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import zipfile

import dualmic_zero_d3_source as original

source = original.source
need = source.need
READER_SHA256 = "e92c81188a3a30e2c335f5b3c7c6841167cd74b22cb01a9f7072dfcebd2e965f"
SUCCESS = "RECOVERED_ORIGINAL_EVIDENCE_NO_NEW_EXPERIMENT"


def no_symlinks(path):
    """Do not resolve a link before checking it, including parent directories."""
    path = Path(path).absolute()
    need(not any(p.is_symlink() for p in (path, *path.parents)),
         "ARCHIVE_RECOVERY_SYMLINK_PATH")
    return path


def contract():
    need(source.digest(Path(original.__file__)) == READER_SHA256,
         "ARCHIVE_RECOVERY_FROZEN_READER_CHANGED")
    lock = original.frozen_lock()
    # This checks the full D1 source closure, not just the two helper blobs in
    # the D3 lock.  A later source migration must not silently bypass it.
    original.d2.input_lock()
    return lock


def read_original(extracted, lock, started):
    """Reuse the same byte seals and read-only analysis as the frozen reader."""
    parent, prior = extracted / "result", extracted / "gain-d2"
    need(source.digest(prior / "report.json") == lock["report_sha256"] and
         source.digest(prior / "artifact-manifest.json") == lock["manifest_sha256"],
         "D3_ORIGINAL_REPORT_IDENTITY")
    manifest = original.d2.read_json(prior / "artifact-manifest.json")
    need(manifest["files"] == original.d2.payload_inventory(prior),
         "D3_ORIGINAL_D2_PAYLOAD_CHANGED")
    recomputed = original.d2.analysis_payload(prior, parent, started)
    need(recomputed == original.d2.read_json(prior / "report.json"),
         "D3_ORIGINAL_D2_READBACK_DIFFERS")
    need(recomputed["source_revision"] == lock["source_revision"] and
         recomputed["case_count"] == 60 and recomputed["frames"] == 35916 and
         recomputed["samples"] == 5746560, "D3_ORIGINAL_SOURCE_OR_MATRIX")
    return {"original_D2_readback_exact": True,
            "original_report": original.d2.descriptor(prior / "report.json"),
            "original_manifest": original.d2.descriptor(prior / "artifact-manifest.json"),
            "case_count": 60, "frames": 35916, "samples": 5746560}


def recover(archive, output):
    started = time.monotonic()
    lock = contract()
    archive, output = no_symlinks(archive), no_symlinks(output)
    need(not output.exists(), "ARCHIVE_RECOVERY_NEW_OUTPUT_REQUIRED")
    need(output not in archive.parents and archive != output,
         "ARCHIVE_RECOVERY_OVERLAPPING_PATHS")
    need(archive.is_file(), "ARCHIVE_RECOVERY_REGULAR_ZIP_REQUIRED")
    spec, budget = lock["artifact"], lock["budget_seconds"]
    need(archive.stat().st_size == spec["zip_bytes"] and
         source.digest(archive) == spec["sha256"], "original ZIP hash/size mismatch")
    source.remaining(started, budget)

    # Invalid input must fail before creating output; failures after creation
    # retain a separate FAIL receipt and never overwrite the caller's archive.
    output.mkdir(parents=True)
    receipt = {
        "schema_version": 1, "operation": "dualmic-original-archive-recovery",
        "status": "FAIL", "metadata_authority": "repository-frozen-input-lock",
        "original_experiment": lock["experiment"], "freeze": original.FREEZE,
        "repository": lock["repository"], "run_id": lock["run_id"],
        "run_attempt": lock["run_attempt"], "source_revision": lock["source_revision"],
        "original_artifact": spec,
        "frozen_lock": {"path": original.LOCK_PATH,
                        "sha256": source.digest(original.ROOT / original.LOCK_PATH)},
        "live_actions_metadata_queried": False, "artifact_expiration_checked": False,
        "original_metadata_rewritten": False, "DSP_executed": False,
        "models_executed": False, "new_acoustic_experiment": False,
        "promotion_allowed": False, "budget_seconds": budget,
    }
    try:
        (output / "frozen-input-lock.json").write_bytes(
            (original.ROOT / original.LOCK_PATH).read_bytes())
        retained = output / "original.zip"
        # Retain the exact ZIP, not a repacked set of extracted files.  The
        # existing extractor rechecks the copied bytes before opening members.
        copied = 0
        with archive.open("rb") as src, retained.open("xb") as dst:
            while True:
                source.remaining(started, budget)
                block = src.read(1024 * 1024)
                if not block:
                    break
                copied += len(block)
                need(copied <= spec["zip_bytes"], "ARCHIVE_RECOVERY_COPY_SIZE_CHANGED")
                dst.write(block)
        need(copied == spec["zip_bytes"], "ARCHIVE_RECOVERY_COPY_SIZE_CHANGED")
        source.remaining(started, budget)
        checked = source.validate_extract(retained, output / "original", spec,
                                          lock, started, budget)
        need(checked["uncompressed_bytes"] == lock["max_uncompressed_bytes"],
             "D3_ORIGINAL_TOTAL_BYTES")
        source.dump(output / "member-hashes.json", checked)
        receipt.update(read_original(output / "original", lock, started))
        source.remaining(started, budget)
        receipt.update(status=SUCCESS, member_count=checked["members"],
                       uncompressed_bytes=checked["uncompressed_bytes"],
                       elapsed_seconds=time.monotonic() - started)
        source.dump(output / "recovery.json", receipt)
        source.remaining(started, budget)
    except Exception as error:
        receipt.update(status="FAIL", failure_type=type(error).__name__,
                       failure_reason=str(error) if isinstance(error, ValueError)
                       else "original archive recovery failed; no fallback",
                       elapsed_seconds=time.monotonic() - started)
        source.dump(output / "recovery.json", receipt)
        raise
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True,
                        help="the exact archived ZIP named by the frozen D3 input lock")
    parser.add_argument("--output", type=Path, required=True,
                        help="a new directory; existing data is never replaced")
    args = parser.parse_args(argv)
    try:
        result = recover(args.archive, args.output)
    except (OSError, ValueError, KeyError, TypeError, TimeoutError, zipfile.BadZipFile) as error:
        reason = str(error) if isinstance(error, ValueError) else type(error).__name__
        print("ARCHIVE_RECOVERY_FAILED: " + reason, file=sys.stderr)
        return 1
    print(json.dumps({key: result[key] for key in
                      ("status", "run_id", "run_attempt", "source_revision")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
