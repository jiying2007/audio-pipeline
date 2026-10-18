#!/usr/bin/env python3
"""#792: restore byte-exact, previously protected original speech selection.

This is an ORIGINAL DATA transport change only, never source substitution,
an acoustic result, a threshold waiver, a synthetic corpus or hardware proof.
The fixed predecessor ZIP digest and the already admitted source-check contract
are independent fail-closed authority; this script copies no old scores.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import zipfile

import speech_source
from speech_spatial import source_check
from contracts import ROOT

ORIGIN_REPO = "jiying2007/audio-pipeline"
ORIGIN_MAIN = "e85a14540f2c49456508387fe3f815a90308c1ba"
ORIGIN_VERIFY_RUN = 39052067322
ORIGIN_RELEASE_RUN = 39054626943
ORIGIN_ARTIFACT = 12107574410
ORIGIN_ARTIFACT_NAME = "frontend-speech-39052067322"
ORIGIN_ZIP_BYTES = 204415056
ORIGIN_ZIP_SHA256 = "1dffd4fc4968a0a214658627f1faf8bf54268f119fda86600a48511f897f30d4"
ORIGIN_ARCHIVE_SHA256 = "76f87d090650617fca0cac8f88b9416e0ebf80350acb97b343a85fa903728ab3"
ADMITTED_SOURCE_SHA256 = "7c4d711d4cb69121ccbbcb9a596d7ea26ca141a325add2dc8f5ff7421b9154c1"
PREFIX = "effects/data/"
DECISION = "FE03_EXACT_PREVIOUSLY_ADMITTED_SOURCE_BYTES_REVALIDATED_NEW_SCIENCE_REQUIRED"
FAILURE = "FE03_PINNED_OFFICIAL_SPEECH_SOURCE_NOT_ADMITTED"
MAX_MEMBERS = 24000
MAX_SOURCE_MEMBERS = 128
MAX_ZIP_MEMBER_BYTES = 65_000_000
MAX_SOURCE_BYTES = 80_000_000
ALLOWED_ORIGIN_SIZE = 204415056


class AdmissionError(ValueError):
    pass


def need(ok: bool, reason: str) -> None:
    if not ok:
        raise AdmissionError(reason)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def strict_source_commit(source_commit: str) -> None:
    need(re.fullmatch("[0-9a-f]{40}", source_commit) is not None,
         "EXECUTION_SOURCE_NOT_EXACT_SHA")
    actual = subprocess.check_output(
        ["git", "-c", "safe.directory=" + str(ROOT),
         "rev-parse", "HEAD"], cwd=ROOT, timeout=20).decode("ascii").strip()
    need(actual == source_commit, "CHECKED_OUT_SHA_NOT_EXECUTION_SOURCE")


def original_source_policy() -> dict:
    path = ROOT / ".github/research/frontend-evolution-v1/speech-admission-v1.json"
    policy = json.loads(path.read_text("utf-8"))
    need(type(policy) is dict and
         policy.get("decision") == "ADMITTED_RECORDED_SPEECH_FIXED_DIAGNOSTICS" and
         policy.get("shipping_authority") is False and
         policy.get("source_id") == "librispeech-dev-clean-fe03" and
         policy.get("archive_bytes") == 337926286 and
         policy.get("archive_sha256") == ORIGIN_ARCHIVE_SHA256 and
         policy.get("archive_md5") == speech_source.MD5 and
         policy.get("bound_source_sha256") == ADMITTED_SOURCE_SHA256 and
         speech_source.MD5 == "42e2234ba48799c1f50f24a7926300a1" and
         speech_source.URL == "https://www.openslr.org/resources/12/dev-clean.tar.gz",
         "INDEPENDENTLY_ADMITTED_ORIGINAL_SOURCE_POLICY_DRIFT")
    return policy


def _safe_member(member: zipfile.ZipInfo) -> None:
    name = member.filename
    need(type(name) is str and name and
         not name.startswith("/") and not name.startswith("\\") and
         "\\" not in name and ":" not in name and
         all(part not in ("", ".", "..") for part in
             name.rstrip("/").split("/")) and
         not PurePosixPath(name).is_absolute(),
         "UNSAFE_ZIP_MEMBER_PATH")
    mode = member.external_attr >> 16
    ftype = stat.S_IFMT(mode)
    need(ftype in (0, stat.S_IFDIR if member.is_dir() else stat.S_IFREG),
         "LINK_OR_NONREGULAR_ZIP_MEMBER_FORBIDDEN")
    need(0 <= member.file_size <= MAX_ZIP_MEMBER_BYTES and
         0 <= member.compress_size <= ORIGIN_ZIP_BYTES,
         "UNBOUNDED_ZIP_MEMBER")


def scan_zip(z: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    infos = z.infolist()
    need(0 < len(infos) <= MAX_MEMBERS, "MISSING_OR_UNBOUNDED_ORIGINAL_MEMBERS")
    seen: set[str] = set()
    selected = []
    source_bytes = 0
    total_bytes = 0
    for info in infos:
        _safe_member(info)
        need(info.filename not in seen, "DUPLICATE_ZIP_MEMBER")
        seen.add(info.filename)
        total_bytes += info.file_size
        need(total_bytes <= 2_000_000_000, "ZIP_UNCOMPRESSED_TOTAL_UNBOUNDED")
        if info.filename.startswith(PREFIX) and not info.is_dir():
            rel = info.filename[len(PREFIX):]
            need(rel and "/" not in rel or rel.startswith("flac/"),
                 "SOURCE_TREE_DEPTH_DRIFT")
            need(rel != "." and not rel.startswith(".") and
                 len(rel.split("/")) <= 2,
                 "UNEXPECTED_SELECTED_SOURCE_MEMBER")
            source_bytes += info.file_size
            need(source_bytes <= MAX_SOURCE_BYTES,
                 "SELECTED_OFFICIAL_DATA_SET_TOO_LARGE")
            selected.append(info)
    need(12 <= len(selected) <= MAX_SOURCE_MEMBERS and
         PREFIX+"source-receipt.json" in seen and
         PREFIX+"ATTRIBUTION.txt" in seen and
         PREFIX+"LICENSE.TXT" in seen and
         PREFIX+"README.TXT" in seen and
         PREFIX+"SPEAKERS.TXT" in seen,
         "ORIGINAL_SOURCE_SELECTION_OR_NOTICES_MISSING")
    return selected


def restore(archive: Path, output: Path, transfer: Path, commit: str) -> dict:
    strict_source_commit(commit)
    original_source_policy()
    need(output.parent.is_dir() and not output.parent.is_symlink() and
         not output.exists() and not output.is_symlink() and
         not transfer.exists() and not transfer.is_symlink() and
         transfer.parent.resolve() == output.parent.resolve() and
         archive.is_file() and not archive.is_symlink() and
         archive.resolve() != output.resolve() and
         archive.stat().st_size == ALLOWED_ORIGIN_SIZE,
         "SOURCE_OR_TRANSFER_DESTINATION_NOT_FRESH_OR_ARTIFACT_SIZE_WRONG")
    zip_digest = sha256_file(archive)
    need(zip_digest == ORIGIN_ZIP_SHA256,
         "ORIGINAL_GITHUB_ARTIFACT_ZIP_SHA256_CHANGED")
    with tempfile.TemporaryDirectory(prefix=".verified-speech-", dir=output.parent) as temp:
        scratch = Path(temp) / "source"
        scratch.mkdir()
        with zipfile.ZipFile(archive, "r") as z:
            selected = scan_zip(z)
            for info in selected:
                relative = info.filename[len(PREFIX):]
                item = scratch / relative
                need(item.resolve().is_relative_to(scratch.resolve()),
                     "SOURCE_MEMBER_ESCAPED_VERIFIED_DIRECTORY")
                item.parent.mkdir(parents=True, exist_ok=True)
                need(not item.exists(), "SOURCE_MEMBER_OVERWRITE_REFUSED")
                with z.open(info, "r") as src, item.open("xb") as dst:
                    count = 0
                    while True:
                        block = src.read(1024*1024)
                        if not block:
                            break
                        count += len(block)
                        need(count <= info.file_size, "SOURCE_ZIP_DECOMPRESS_OVERFLOW")
                        dst.write(block)
                need(count == info.file_size, "SHORT_OR_CORRUPTED_SOURCE_MEMBER")
        # Critically, this ORIGINAL first-party contract independently
        # rechecks all selected FLAC, notice, source/plan/roles and PCM hashes.
        source = source_check(scratch)
        need(type(source) is dict and
             source.get("archive_sha256") == ORIGIN_ARCHIVE_SHA256 and
             source.get("archive_md5") == speech_source.MD5 and
             source.get("archive_bytes") == 337926286 and
             source.get("url") == speech_source.URL and
             source.get("source_id") == "librispeech-dev-clean-fe03" and
             source.get("shipping_authority") is False,
             "FIRST_PARTY_ADMITTED_ARCHIVE_SOURCE_IDENTITY_DRIFT")
        source_receipt_sha = sha256_file(scratch / "source-receipt.json")
        hashes = {
            p.relative_to(scratch).as_posix(): sha256_file(p)
            for p in sorted(scratch.rglob("*")) if p.is_file()
        }
        need(all(source["files_sha256"].get(p) == h for p,h in hashes.items()
                 if p != "source-receipt.json") and
             set(hashes) == set(source["files_sha256"]) | {"source-receipt.json"},
             "ORIGINAL_FILE_BYTE_HASHES_INCOMPLETE")
        record = {
            "schema_version": 1, "decision": DECISION, "source_role":
                "original-LibriSpeech-fixed-recorded-speech-revalidated",
            "source_commit": commit,
            "protected_source_main": ORIGIN_MAIN,
            "protected_source_verify_run_id": ORIGIN_VERIFY_RUN,
            "protected_source_release_run_id": ORIGIN_RELEASE_RUN,
            "original_source_artifact_id": ORIGIN_ARTIFACT,
            "original_source_artifact_name": ORIGIN_ARTIFACT_NAME,
            "original_source_artifact_zip_sha256": zip_digest,
            "independently_admitted_selected_sha256": ADMITTED_SOURCE_SHA256,
            "original_archive_sha256_prior_verified": ORIGIN_ARCHIVE_SHA256,
            "source_receipt_sha256": source_receipt_sha,
            "original_restored_files_sha256": hashes,
            "verified_selected_source_member_count": len(hashes),
            "previous_scientific_score_reused": False,
            "current_acoustic_evaluation_completed": False,
            "original_full_archive_redownloaded": False,
            "source_substitution": False,
            "public_product_or_device_qualification": False,
            "verification_authority": "source-bytes-only-fresh-science-required"
        }
        receipt_tmp = Path(temp) / "source-transfer.json"
        receipt_tmp.write_text(json.dumps(record, sort_keys=True,
            separators=(",", ":"), allow_nan=False)+"\n", encoding="utf-8")
        need(receipt_tmp.stat().st_size <= 32*1024,
             "TRANSFER_RECEIPT_UNBOUNDED")
        scratch.rename(output)
        receipt_tmp.rename(transfer)
        return record


def preserve_failure(output: Path, error: Exception, commit: str) -> bool:
    if output.exists() or output.is_symlink():
        return False
    try:
        output.mkdir(parents=True, exist_ok=False)
        report = {
            "schema_version": 1,
            "status": "DATA_OR_INFRASTRUCTURE_FAILURE",
            "reason_code": "PINNED_ORIGINAL_SOURCE_ARTIFACT_TRANSFER_REJECTED",
            "reason_detail": str(error)[:180],
            "source_commit": commit,
            "original_source_artifact_id": ORIGIN_ARTIFACT,
            "original_source_zip_sha256_expected": ORIGIN_ZIP_SHA256,
            "source_substitution": False,
            "shipping_authority": False,
            "acoustic_validation_qualified": False
        }
        (output / "source-failure.json").write_text(json.dumps(
            report, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n",
            encoding="utf-8")
        return True
    except (OSError, ValueError):
        return False


def self_test() -> None:
    original_source_policy()
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)/"test.zip"
        def make(members: list[tuple[str, bytes]]) -> None:
            with zipfile.ZipFile(p, "w", compression=zipfile.ZIP_DEFLATED) as z:
                for name, data in members:
                    z.writestr(name, data)
        base = [(PREFIX+n, b"old-source-policy-test-data") for n in
                ("source-receipt.json", "ATTRIBUTION.txt", "LICENSE.TXT",
                 "README.TXT", "SPEAKERS.TXT")]
        base += [(PREFIX+f"flac/{n}.flac", bytes([n])) for n in range(10)]
        def accepted_format_only() -> None:
            with zipfile.ZipFile(p) as z:
                need(len(scan_zip(z)) == 15,
                     "OFFLINE_ZIP_FORMAT_SELFTEST_MISSING")
        make(base)
        accepted_format_only()  # ZIP parser only, never source admission.
        negatives = [
            (base[:2], "SOURCE_MISSING"),
            (base+[(PREFIX+"source-receipt.json",b"duplicate")], "DUPLICATE"),
            (base+[("../escape",b"evil")], "PATH_TRAVERSAL"),
            (base+[(PREFIX+"../../escape",b"evil")], "SOURCE_PATH_ESCAPE"),
            (base+[(PREFIX+".secret",b"evil")], "HIDDEN_SOURCE_MEMBER"),
            (base+[(PREFIX+"deep/extra/a",b"evil")], "SOURCE_TREE_DEPTH"),
            (base+[("root\\evil",b"evil")], "BACKSLASH"),
        ]
        failures = 0
        for members, reason in negatives:
            make(members)
            try:
                with zipfile.ZipFile(p) as z:
                    scan_zip(z)
            except AdmissionError:
                failures += 1
            else:
                raise AdmissionError("OFFLINE_SELFTEST_FALSE_ACCEPT_" + reason)
        need(failures == len(negatives), "NEGATIVE_ZIP_POLICY_NOT_EXECUTED")
        make(base)
        need(sha256_file(p) != ORIGIN_ZIP_SHA256,
             "FAKE_OFFLINE_TEST_MUST_NEVER_MATCH_PINNED_ORIGINAL_ZIP")
        need(not (Path(tmp)/"source").exists(),
             "OFFLINE_SELFTEST_FABRICATED_ADMITTED_SOURCE")
    print("FE03_ORIGINAL_SOURCE_SNAPSHOT_POLICY_SELFTEST_PASS",
          failures, "no_data_promotion")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--restore", action="store_true")
    mode.add_argument("--mark-download-failure", action="store_true")
    p.add_argument("--zip", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--transfer", type=Path)
    p.add_argument("--execution-source", default="")
    args = p.parse_args()
    try:
        if args.self_test:
            self_test()
            return
        need(args.output is not None and
             re.fullmatch("[0-9a-f]{40}", args.execution_source) is not None,
             "MISSING_EXECUTION_SHA_OR_OUTPUT")
        if args.mark_download_failure:
            need(not args.output.exists(), "FAILURE_OUTPUT_MUST_BE_FRESH")
            raise AdmissionError("PINNED_GITHUB_ARTIFACT_DOWNLOAD_FAILED")
        need(args.zip is not None and args.transfer is not None,
             "SOURCE_ZIP_OR_TRANSFER_RECEIPT_MISSING")
        result=restore(args.zip, args.output, args.transfer,
                       args.execution_source)
        print("FE03_PINNED_ORIGINAL_SOURCE_REVALIDATED",
              result["source_commit"],
              result["verified_selected_source_member_count"])
    except Exception as exc:
        if args.output is not None:
            preserve_failure(args.output, exc, args.execution_source)
        raise SystemExit(FAILURE+": "+str(exc)[:200]) from None

if __name__ == "__main__":
    main()
