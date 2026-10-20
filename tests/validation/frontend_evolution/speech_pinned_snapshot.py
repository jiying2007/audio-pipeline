#!/usr/bin/env python3
"""Restore or reacquire byte-exact, previously admitted original speech.

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
import time
import zipfile

import speech_source
import speech_source_stage_budget as stage_budget
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
CACHE_BUDGET_SECONDS = 600


class AdmissionError(ValueError):
    pass


class CacheFailure(AdmissionError):
    """A negative cache outcome, never an acoustic or source-admission result."""


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


def fresh_destinations(output: Path, transfer: Path) -> None:
    need(output.parent.is_dir() and not output.parent.is_symlink() and
         not output.exists() and not output.is_symlink() and
         not transfer.exists() and not transfer.is_symlink() and
         transfer.parent.resolve() == output.parent.resolve() and
         transfer.resolve() != output.resolve(),
         "SOURCE_OR_TRANSFER_DESTINATION_NOT_FRESH")


def publish_source(scratch: Path, output: Path, transfer: Path, commit: str,
                   *, zip_digest: str | None, original_downloaded: bool = False,
                   cache_failure: Path | None = None) -> dict:
    # The original independent contract, not transport success, admits bytes.
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
    need(all(source["files_sha256"].get(p) == h for p, h in hashes.items()
             if p != "source-receipt.json") and
         set(hashes) == set(source["files_sha256"]) | {"source-receipt.json"},
         "ORIGINAL_FILE_BYTE_HASHES_INCOMPLETE")
    need(len(hashes) <= MAX_SOURCE_MEMBERS and
         sum(p.stat().st_size for p in scratch.rglob("*") if p.is_file())
         <= MAX_SOURCE_BYTES, "SELECTED_OFFICIAL_DATA_SET_TOO_LARGE")
    record = {
        "schema_version": 2, "decision": DECISION,
        "source_role": "original-LibriSpeech-fixed-recorded-speech-revalidated",
        "source_commit": commit,
        "acquisition_path": ("protected-artifact-cache" if zip_digest else
                             "official-original-archive"),
        "protected_source_main": ORIGIN_MAIN,
        "protected_source_verify_run_id": ORIGIN_VERIFY_RUN,
        "protected_source_release_run_id": ORIGIN_RELEASE_RUN,
        "original_source_artifact_id": ORIGIN_ARTIFACT,
        "original_source_artifact_name": ORIGIN_ARTIFACT_NAME,
        "original_source_artifact_zip_sha256": zip_digest,
        "artifact_cache_identity_revalidated_this_run": zip_digest is not None,
        "independently_admitted_selected_sha256": ADMITTED_SOURCE_SHA256,
        "original_archive_sha256_prior_verified": ORIGIN_ARCHIVE_SHA256,
        "source_receipt_sha256": source_receipt_sha,
        "original_restored_files_sha256": hashes,
        "verified_selected_source_member_count": len(hashes),
        "previous_scientific_score_reused": False,
        "current_acoustic_evaluation_completed": False,
        "original_full_archive_redownloaded": original_downloaded,
        "original_full_archive_rehashed_this_run": zip_digest is None,
        "cache_failure_receipt_sha256": (sha256_file(cache_failure)
                                          if cache_failure else None),
        "source_substitution": False,
        "public_product_or_device_qualification": False,
        "verification_authority": "source-bytes-only-fresh-science-required"
    }
    receipt_tmp = scratch.parent / "source-transfer.json"
    receipt_tmp.write_text(json.dumps(record, sort_keys=True,
        separators=(",", ":"), allow_nan=False)+"\n", encoding="utf-8")
    need(receipt_tmp.stat().st_size <= 32*1024, "TRANSFER_RECEIPT_UNBOUNDED")
    fresh_destinations(output, transfer)
    scratch.rename(output)
    receipt_tmp.rename(transfer)
    return record


def restore(archive: Path, output: Path, transfer: Path, commit: str) -> dict:
    strict_source_commit(commit)
    original_source_policy()
    fresh_destinations(output, transfer)
    need(archive.is_file() and not archive.is_symlink() and
         archive.resolve() != output.resolve() and
         archive.stat().st_size == ALLOWED_ORIGIN_SIZE,
         "ARTIFACT_FILE_OR_SIZE_WRONG")
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
        return publish_source(scratch, output, transfer, commit,
                              zip_digest=zip_digest)


def reacquire_official(output: Path, transfer: Path, commit: str, *,
                      archive: Path | None = None,
                      cache_failure: Path | None = None) -> dict:
    """Recreate the frozen selection; no new URL, speaker or decoder fallback."""
    strict_source_commit(commit)
    policy = original_source_policy()
    fresh_destinations(output, transfer)
    if cache_failure is not None:
        need(cache_failure.is_file() and not cache_failure.is_symlink() and
             cache_failure.parent.resolve() == output.parent.resolve() and
             0 < cache_failure.stat().st_size <= 4096,
             "CACHE_FAILURE_RECEIPT_NOT_BOUNDED_OR_LOCAL")
    with tempfile.TemporaryDirectory(prefix=".official-speech-",
                                     dir=output.parent) as temp:
        scratch = Path(temp)
        original = archive if archive is not None else scratch / "dev-clean.tar.gz"
        if archive is None:
            speech_source.download(original)  # Original <=3-attempt policy.
        need(original.is_file() and not original.is_symlink() and
             original.stat().st_size == policy["archive_bytes"],
             "OFFICIAL_ORIGINAL_ARCHIVE_SIZE_OR_FILE_REJECTED")
        # Validate SHA256 before any external decoder receives archive members.
        need(sha256_file(original) == policy["archive_sha256"],
             "OFFICIAL_ORIGINAL_ARCHIVE_SHA256_REJECTED")
        data = scratch / "source"
        speech_source.acquire(original, data, offset=0)
        return publish_source(data, output, transfer, commit, zip_digest=None,
                              original_downloaded=archive is None,
                              cache_failure=cache_failure)


def cache_api(endpoint: str, deadline: float, kind: str, *, stream=None):
    """Read-only fixed GitHub endpoints; never retain stderr or signed URLs."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise CacheFailure("PINNED_CACHE_WALL_DEADLINE")
    try:
        response = subprocess.run(
            ["gh", "api", "repos/" + ORIGIN_REPO + endpoint],
            stdout=stream if stream is not None else subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=remaining if stream is not None else min(30, remaining),
            check=False)
    except subprocess.TimeoutExpired:
        raise CacheFailure("PINNED_CACHE_" + kind + "_TIMEOUT") from None
    except OSError:
        raise CacheFailure("PINNED_CACHE_" + kind + "_UNAVAILABLE") from None
    if response.returncode:
        raise CacheFailure("PINNED_CACHE_" + kind + "_UNAVAILABLE")
    if stream is not None:
        return None
    if not 0 < len(response.stdout) <= 1024*1024:
        raise CacheFailure("PINNED_CACHE_" + kind + "_METADATA_UNBOUNDED")
    try:
        value = json.loads(response.stdout)
    except (ValueError, UnicodeError):
        raise CacheFailure("PINNED_CACHE_" + kind + "_MALFORMED_JSON") from None
    if type(value) is not dict:
        raise CacheFailure("PINNED_CACHE_" + kind + "_MALFORMED_JSON")
    return value


def restore_cache(archive: Path, output: Path, transfer: Path,
                  commit: str) -> dict:
    deadline = time.monotonic() + CACHE_BUDGET_SECONDS
    run = cache_api("/actions/runs/" + str(ORIGIN_VERIFY_RUN),
                    deadline, "RUN")
    if (run.get("id") != ORIGIN_VERIFY_RUN or
        run.get("head_sha") != ORIGIN_MAIN or
        run.get("conclusion") != "success" or run.get("event") != "push"):
        raise CacheFailure("PINNED_CACHE_RUN_IDENTITY_REJECTED")
    artifact = cache_api("/actions/artifacts/" + str(ORIGIN_ARTIFACT),
                         deadline, "ARTIFACT")
    if artifact.get("expired") is True:
        raise CacheFailure("PINNED_CACHE_ARTIFACT_EXPIRED")
    origin = artifact.get("workflow_run")
    if (artifact.get("id") != ORIGIN_ARTIFACT or
        artifact.get("name") != ORIGIN_ARTIFACT_NAME or
        artifact.get("size_in_bytes") != ORIGIN_ZIP_BYTES or
        artifact.get("digest") != "sha256:" + ORIGIN_ZIP_SHA256 or
        artifact.get("expired") is not False or type(origin) is not dict or
        origin.get("id") != ORIGIN_VERIFY_RUN or
        origin.get("head_sha") != ORIGIN_MAIN):
        raise CacheFailure("PINNED_CACHE_ARTIFACT_IDENTITY_REJECTED")
    with archive.open("xb") as stream:
        cache_api("/actions/artifacts/" + str(ORIGIN_ARTIFACT) + "/zip",
                  deadline, "DOWNLOAD", stream=stream)
    return restore(archive, output, transfer, commit)


def preserve_cache_failure(path: Path, error: Exception, commit: str) -> None:
    # Known admission messages describe paths/identity only. Never serialize
    # subprocess stdout/stderr, request headers or a redirected download URL.
    record = {
        "schema_version": 1,
        "status": "CACHE_UNAVAILABLE_OR_REJECTED",
        "reason_code": (str(error) if isinstance(error, CacheFailure) else
                        "PINNED_CACHE_SOURCE_IDENTITY_REJECTED"),
        "reason_detail": (str(error)[:180] if isinstance(error, ValueError)
                          else type(error).__name__),
        "source_commit": commit,
        "original_source_artifact_id": ORIGIN_ARTIFACT,
        "original_source_zip_sha256_expected": ORIGIN_ZIP_SHA256,
        "cache_wall_seconds_ceiling": CACHE_BUDGET_SECONDS,
        "next_allowed_source": speech_source.URL,
        "next_allowed_archive_sha256": ORIGIN_ARCHIVE_SHA256,
        "original_source_reacquisition_completed": False,
        "source_substitution": False,
        "acoustic_validation_qualified": False,
        "shipping_authority": False,
    }
    with path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, sort_keys=True, separators=(",", ":"),
                  allow_nan=False)
        stream.write("\n")


def acquire_source(archive: Path, output: Path, transfer: Path,
                   cache_failure: Path, commit: str) -> dict:
    started = time.monotonic()
    strict_source_commit(commit)
    original_source_policy()
    fresh_destinations(output, transfer)
    for path in (archive, cache_failure):
        need(path.parent.resolve() == output.parent.resolve() and
             not path.exists() and not path.is_symlink(),
             "CACHE_DESTINATION_NOT_FRESH_OR_LOCAL")
    need(len({path.resolve() for path in
              (archive, output, transfer, cache_failure)}) == 4,
         "OVERLAPPING_SOURCE_TRANSPORT_DESTINATIONS")
    try:
        return restore_cache(archive, output, transfer, commit)
    except Exception as error:
        preserve_cache_failure(cache_failure, error, commit)
        # A partially published result must not be reused or overwritten.
        fresh_destinations(output, transfer)
    finally:
        archive.unlink(missing_ok=True)
    remaining = stage_budget.DEADLINE_SECONDS - (time.monotonic() - started)
    need(remaining > 0, "ORIGINAL_SOURCE_ACQUISITION_WALL_DEADLINE")
    environment = os.environ.copy()
    for key in ("GH_TOKEN", "GITHUB_TOKEN"):
        environment.pop(key, None)
    command = [sys.executable, str(Path(__file__).resolve()),
               "--reacquire-official", "--output", str(output.resolve()),
               "--transfer", str(transfer.resolve()),
               "--cache-failure", str(cache_failure.resolve()),
               "--execution-source", commit]
    succeeded = stage_budget.run_bounded(
        command, output, remaining, cwd=ROOT,
        env=environment)
    need(succeeded, "OFFICIAL_ORIGINAL_SOURCE_REACQUISITION_FAILED")
    # A successful process exit alone is not a source or receipt admission.
    source_check(output)
    need(transfer.is_file() and not transfer.is_symlink() and
         0 < transfer.stat().st_size <= 32*1024,
         "OFFICIAL_SOURCE_TRANSFER_RECEIPT_MISSING")
    record = json.loads(transfer.read_text("utf-8"))
    need(record.get("source_commit") == commit and
         record.get("decision") == DECISION and
         record.get("acquisition_path") == "official-original-archive" and
         record.get("cache_failure_receipt_sha256") == sha256_file(cache_failure),
         "OFFICIAL_SOURCE_TRANSFER_RECEIPT_IDENTITY_REJECTED")
    return record


def preserve_failure(output: Path, error: Exception, commit: str, *,
                     reason_code: str =
                     "PINNED_ORIGINAL_SOURCE_ARTIFACT_TRANSFER_REJECTED") -> bool:
    if output.is_symlink():
        return False
    try:
        output.mkdir(parents=True, exist_ok=True)
        marker = output / "source-failure.json"
        if marker.exists() or marker.is_symlink():
            return (marker.is_file() and not marker.is_symlink() and
                    0 < marker.stat().st_size <= 65536)
        report = {
            "schema_version": 1,
            "status": "DATA_OR_INFRASTRUCTURE_FAILURE",
            "reason_code": reason_code,
            "reason_detail": str(error)[:180],
            "source_commit": commit,
            "original_source_artifact_id": ORIGIN_ARTIFACT,
            "original_source_zip_sha256_expected": ORIGIN_ZIP_SHA256,
            "original_source_url": speech_source.URL,
            "original_archive_sha256_expected": ORIGIN_ARCHIVE_SHA256,
            "source_substitution": False,
            "shipping_authority": False,
            "acoustic_validation_qualified": False
        }
        with marker.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)
            stream.write("\n")
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
    mode.add_argument("--acquire", action="store_true")
    mode.add_argument("--reacquire-official", action="store_true")
    mode.add_argument("--mark-download-failure", action="store_true")
    p.add_argument("--zip", type=Path)
    p.add_argument("--original-archive", type=Path)
    p.add_argument("--cache-failure", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--transfer", type=Path)
    p.add_argument("--execution-source", default="")
    args = p.parse_args()
    preexisting_output = (args.output is not None and
                          (args.output.exists() or args.output.is_symlink()))
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
        need(args.transfer is not None, "SOURCE_TRANSFER_RECEIPT_MISSING")
        need(args.original_archive is None or args.reacquire_official,
             "LOCAL_ORIGINAL_ARCHIVE_ONLY_FOR_EXPLICIT_ORIGINAL_REPLAY")
        if args.reacquire_official:
            result = reacquire_official(
                args.output, args.transfer, args.execution_source,
                archive=args.original_archive, cache_failure=args.cache_failure)
        else:
            need(args.zip is not None, "SOURCE_ZIP_MISSING")
            if args.acquire:
                need(args.cache_failure is not None, "CACHE_FAILURE_RECEIPT_MISSING")
                result = acquire_source(args.zip, args.output, args.transfer,
                                        args.cache_failure, args.execution_source)
            else:
                result = restore(args.zip, args.output, args.transfer,
                                 args.execution_source)
        print("FE03_ORIGINAL_SOURCE_REVALIDATED",
              result["source_commit"], result["acquisition_path"],
              result["verified_selected_source_member_count"])
    except Exception as exc:
        if args.output is not None and not preexisting_output:
            reason = ("OFFICIAL_ORIGINAL_SOURCE_REACQUISITION_REJECTED"
                      if args.reacquire_official else
                      "PINNED_ORIGINAL_SOURCE_ACQUISITION_REJECTED"
                      if args.acquire else
                      "PINNED_ORIGINAL_SOURCE_ARTIFACT_TRANSFER_REJECTED")
            preserve_failure(args.output, exc, args.execution_source,
                             reason_code=reason)
        raise SystemExit(FAILURE+": "+str(exc)[:200]) from None


if __name__ == "__main__":
    main()
