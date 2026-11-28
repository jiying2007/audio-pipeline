#!/usr/bin/env python3
"""Restore or reacquire byte-exact, previously admitted original speech.

This is an ORIGINAL DATA transport change only, never source substitution,
an acoustic result, a threshold waiver, a synthetic corpus or hardware proof.
The fixed predecessor and bounded successor ZIP identities prove transport;
the independent source-check contract admits original bytes, never old scores.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
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
import speech_source_cache_profiles as profiles
import speech_source_recent_cache as recent_cache
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
RECENT_UNAVAILABLE = {"PINNED_CACHE_RUN_UNAVAILABLE", "PINNED_CACHE_ARTIFACT_UNAVAILABLE",
                      "PINNED_CACHE_ARTIFACT_EXPIRED", "PINNED_CACHE_DOWNLOAD_UNAVAILABLE"}
RECENT_FAILURE_NAME = "source-recent-cache-failure.json"

def _settings(profile):
    if profile is not None:
        return profiles.require_profile(profile)
    # Preserve the original runtime lookup of default constants, including
    # existing offline test doubles. No profile mutates any of these globals.
    return profiles.SnapshotProfile(
        name='', offset=0, source_id='librispeech-dev-clean-fe03',
        source_role='original-LibriSpeech-fixed-recorded-speech-revalidated',
        origin_main=ORIGIN_MAIN, verify_run=ORIGIN_VERIFY_RUN,
        release_run=ORIGIN_RELEASE_RUN, artifact_id=ORIGIN_ARTIFACT,
        artifact_name=ORIGIN_ARTIFACT_NAME, zip_bytes=ORIGIN_ZIP_BYTES,
        zip_sha256=ORIGIN_ZIP_SHA256, admitted_source_sha256=ADMITTED_SOURCE_SHA256)


def _options(profile):
    _settings(profile)
    return {} if profile is None else {'profile': profile}


def check_source(path: Path, *, profile=None) -> dict:
    _settings(profile)
    if profile is None:
        return source_check(path)
    from speech_spatial_weights import source_check as spatial_source_check
    return spatial_source_check(path)


def check_profile_receipt(record: dict, profile) -> None:
    p = _settings(profile)
    if profile is not None:
        need(record.get('snapshot_profile') == p.name and
             record.get('source_speaker_offset') == p.offset and
             record.get('source_id') == p.source_id and
             record.get('source_admission_sha256') == p.admission_sha256 and
             record.get('source_plan_sha256') == p.plan_sha256,
             'SOURCE_TRANSFER_PROFILE_IDENTITY_REJECTED')


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


def original_source_policy(*, profile=None) -> dict:
    p = _settings(profile)
    if profile is not None:
        admission, plan = ROOT / p.admission_path, ROOT / p.plan_path
        need(sha256_file(admission) == p.admission_sha256 and
             sha256_file(plan) == p.plan_sha256,
             'SPATIAL_SOURCE_CONTRACT_BYTES_CHANGED')
        policy = json.loads(admission.read_text('utf-8'))
        plan_value = json.loads(plan.read_text('utf-8'))
        need(policy.get('decision') == 'ADMITTED_NEW_SPEAKERS_BEFORE_SCORING' and
             policy.get('shipping_authority') is False and
             policy.get('source_id') == p.source_id and
             policy.get('bound_source_sha256') == p.admitted_source_sha256 and
             policy.get('speakers') == list(p.speakers) and
             plan_value.get('archive_sha256') == ORIGIN_ARCHIVE_SHA256 and
             speech_source.MD5 == '42e2234ba48799c1f50f24a7926300a1' and
             speech_source.URL == 'https://www.openslr.org/resources/12/dev-clean.tar.gz',
             'INDEPENDENTLY_ADMITTED_SPATIAL_SOURCE_POLICY_DRIFT')
        return {**policy, 'archive_bytes':337926286,
                'archive_sha256':ORIGIN_ARCHIVE_SHA256, 'archive_md5':speech_source.MD5}
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
                   cache_failure: Path | None = None, profile=None,
                   recent_origin=None, recent_deadline=None) -> dict:
    p = _settings(profile)
    if recent_origin is not None:
        recent_cache.validate_origin(recent_origin)
        need(profile is None and zip_digest == recent_origin["zip_sha256"] and
             cache_failure is not None and cache_failure.is_file() and not cache_failure.is_symlink() and
             cache_failure.parent.resolve() == output.parent.resolve() and
             0 < cache_failure.stat().st_size <= 4096 and recent_deadline is not None,
             "RECENT_CACHE_PUBLICATION_IDENTITY_REJECTED")
    # The original independent contract, not transport success, admits bytes.
    source = check_source(scratch, **_options(profile))
    need(type(source) is dict and
         source.get("archive_sha256") == ORIGIN_ARCHIVE_SHA256 and
         source.get("archive_md5") == speech_source.MD5 and
         source.get("archive_bytes") == 337926286 and
         source.get("url") == speech_source.URL and
         source.get("source_id") == p.source_id and
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
        "source_role": p.source_role,
        "source_commit": commit,
        "acquisition_path": ("protected-artifact-cache" if zip_digest else
                             "official-original-archive"),
        "protected_source_main": p.origin_main,
        "protected_source_verify_run_id": p.verify_run,
        "protected_source_release_run_id": p.release_run,
        "original_source_artifact_id": p.artifact_id,
        "original_source_artifact_name": p.artifact_name,
        "original_source_artifact_zip_sha256": zip_digest,
        "artifact_cache_identity_revalidated_this_run": zip_digest is not None,
        "independently_admitted_selected_sha256": p.admitted_source_sha256,
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
    if recent_origin is not None:
        record.update({"acquisition_path": "protected-main-source-recovery",
                       "protected_source_main": recent_origin["main_sha"],
                       "protected_source_verify_run_id": recent_origin["run_id"],
                       "protected_source_release_run_id": None,
                       "original_source_artifact_id": recent_origin["artifact_id"],
                       "original_source_artifact_name": recent_origin["artifact_name"],
                       "recent_protected_main_cache": recent_origin,
                       "failed_original_pin_id": p.artifact_id})
        need(time.monotonic() < recent_deadline, "RECENT_CACHE_DEADLINE")
    if profile is not None:
        record.update({'snapshot_profile':p.name, 'source_speaker_offset':p.offset,
            'source_id':p.source_id, 'source_admission_sha256':p.admission_sha256,
            'source_plan_sha256':p.plan_sha256,
            'source_roles':[row['role'] for row in source['speaker_selection']],
            'source_cache_representation':'audio-pipeline-evidence-cas-v1' if zip_digest else None,
            'cache_inner_sha256':p.inner_sha256 if zip_digest else None,
            'cache_manifest_sha256':p.manifest_sha256 if zip_digest else None,
            'cache_transport_tool_sha256':p.transport_tool_sha256 if zip_digest else None})
    receipt_tmp = scratch.parent / "source-transfer.json"
    receipt_tmp.write_text(json.dumps(record, sort_keys=True,
        separators=(",", ":"), allow_nan=False)+"\n", encoding="utf-8")
    need(receipt_tmp.stat().st_size <= 32*1024, "TRANSFER_RECEIPT_UNBOUNDED")
    fresh_destinations(output, transfer)
    scratch.rename(output)
    receipt_tmp.rename(transfer)
    return record


def restore(archive: Path, output: Path, transfer: Path, commit: str, *, profile=None,
            recent_origin=None, cache_failure=None, recent_deadline=None) -> dict:
    p = _settings(profile)
    strict_source_commit(commit)
    original_source_policy(**_options(profile))
    fresh_destinations(output, transfer)
    if recent_origin is not None:
        recent_cache.validate_origin(recent_origin)
        need(profile is None and recent_origin["main_sha"] != commit and
             recent_origin["run_id"] != p.verify_run and cache_failure is not None and
             recent_deadline is not None and time.monotonic() < recent_deadline,
             "RECENT_CACHE_RESTORE_SCOPE_REJECTED")
    expected_size = (recent_origin["zip_bytes"] if recent_origin is not None else
                     ALLOWED_ORIGIN_SIZE if profile is None else p.zip_bytes)
    expected_digest = recent_origin["zip_sha256"] if recent_origin is not None else p.zip_sha256
    need(archive.is_file() and not archive.is_symlink() and
         archive.resolve() != output.resolve() and
         archive.stat().st_size == expected_size,
         "ARTIFACT_FILE_OR_SIZE_WRONG")
    zip_digest = sha256_file(archive)
    need(zip_digest == expected_digest,
         "ORIGINAL_GITHUB_ARTIFACT_ZIP_SHA256_CHANGED")
    with tempfile.TemporaryDirectory(prefix=".verified-speech-", dir=output.parent) as temp:
        scratch = Path(temp) / "source"
        scratch.mkdir()
        if profile is not None:
            from speech_source_cas import copy_source
            copy_source(archive, scratch, profile)
            return publish_source(scratch, output, transfer, commit,
                                  zip_digest=zip_digest, **_options(profile))
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
        if recent_origin is not None:
            return publish_source(scratch, output, transfer, commit, zip_digest=zip_digest,
                                  cache_failure=cache_failure, recent_origin=recent_origin,
                                  recent_deadline=recent_deadline)
        return publish_source(scratch, output, transfer, commit,
                              zip_digest=zip_digest)


def reacquire_official(output: Path, transfer: Path, commit: str, *,
                      archive: Path | None = None,
                      cache_failure: Path | None = None, profile=None) -> dict:
    """Recreate the frozen selection; no new URL, speaker or decoder fallback."""
    strict_source_commit(commit)
    p = _settings(profile)
    policy = original_source_policy(**_options(profile))
    fresh_destinations(output, transfer)
    if cache_failure is not None:
        need(cache_failure.is_file() and not cache_failure.is_symlink() and
             cache_failure.parent.resolve() == output.parent.resolve() and
             0 < cache_failure.stat().st_size <= 4096,
             "CACHE_FAILURE_RECEIPT_NOT_BOUNDED_OR_LOCAL")
    # Enforce this at the callable boundary too: explicit local archive replay
    # still starts FFmpeg, even though it does not perform a network download.
    with without_github_auth(), tempfile.TemporaryDirectory(
            prefix=".official-speech-", dir=output.parent) as temp:
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
        speech_source.acquire(original, data, offset=p.offset)
        return publish_source(data, output, transfer, commit, zip_digest=None,
                              original_downloaded=archive is None,
                              cache_failure=cache_failure, **_options(profile))


@contextmanager
def without_github_auth():
    """Remove GitHub credentials for public-source work and restore the caller."""
    removed = {key: os.environ.pop(key, None)
               for key in ("GH_TOKEN", "GITHUB_TOKEN")}
    try:
        yield
    finally:
        for key, value in removed.items():
            if value is not None:
                os.environ[key] = value


def replay_official_worker(archive: Path, output: Path, transfer: Path,
                           commit: str, *, cache_failure: Path | None = None,
                           profile=None) -> dict:
    """Local replay and independent readback, inside one supervised process."""
    result = reacquire_official(output, transfer, commit, archive=archive,
                                cache_failure=cache_failure, **_options(profile))
    check_source(output, **_options(profile))
    return result


def replay_official_archive(archive: Path, output: Path, transfer: Path,
                            commit: str, *, cache_failure: Path | None = None,
                            profile=None) -> dict:
    """Bound the public local-archive replay just like the acquisition stage."""
    started = time.monotonic()
    strict_source_commit(commit)
    original_source_policy(**_options(profile))
    fresh_destinations(output, transfer)
    need(archive.is_file() and not archive.is_symlink(),
         "OFFICIAL_ORIGINAL_ARCHIVE_SIZE_OR_FILE_REJECTED")
    if cache_failure is not None:
        need(cache_failure.is_file() and not cache_failure.is_symlink() and
             cache_failure.parent.resolve() == output.parent.resolve() and
             0 < cache_failure.stat().st_size <= 4096,
             "CACHE_FAILURE_RECEIPT_NOT_BOUNDED_OR_LOCAL")
    command = [sys.executable, str(Path(__file__).resolve()),
               "--replay-official-worker", "--original-archive", str(archive.resolve()),
               "--output", str(output.resolve()), "--transfer", str(transfer.resolve()),
               "--execution-source", commit]
    if profile is not None:
        command += ['--profile', _settings(profile).name]
    if cache_failure is not None:
        command += ["--cache-failure", str(cache_failure.resolve())]
    # The parent retains any cache authorization. No public-source subprocess,
    # including the explicitly requested local replay, inherits either token.
    environment = {key: value for key, value in os.environ.items()
                   if key not in ("GH_TOKEN", "GITHUB_TOKEN")}
    try:
        remaining = stage_budget.DEADLINE_SECONDS - (time.monotonic() - started)
        need(remaining > 0, "ORIGINAL_SOURCE_ACQUISITION_WALL_DEADLINE")
        need(stage_budget.run_bounded(command, output, remaining,
                                      cwd=ROOT, env=environment),
             "OFFICIAL_ORIGINAL_REPLAY_WORKER_FAILED")
        need(transfer.is_file() and not transfer.is_symlink() and
             0 < transfer.stat().st_size <= 32*1024,
             "OFFICIAL_SOURCE_TRANSFER_RECEIPT_MISSING")
        record = json.loads(transfer.read_text("utf-8"))
        check_profile_receipt(record, profile)
        need(type(record) is dict and record.get("source_commit") == commit and
             record.get("decision") == DECISION and
             record.get("acquisition_path") == "official-original-archive" and
             record.get("original_full_archive_redownloaded") is False and
             record.get("original_full_archive_rehashed_this_run") is True and
             record.get("cache_failure_receipt_sha256") ==
                 (sha256_file(cache_failure) if cache_failure else None),
             "OFFICIAL_SOURCE_TRANSFER_RECEIPT_IDENTITY_REJECTED")
        need(time.monotonic() - started <= stage_budget.DEADLINE_SECONDS,
             "ORIGINAL_SOURCE_ACQUISITION_WALL_DEADLINE")
        return record
    except Exception as error:
        preserve_failure(output, error, commit,
                         reason_code="OFFICIAL_ORIGINAL_SOURCE_REACQUISITION_REJECTED",
                         **_options(profile))
        raise


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
                  commit: str, *, profile=None) -> dict:
    p = _settings(profile)
    deadline = time.monotonic() + CACHE_BUDGET_SECONDS
    run = cache_api("/actions/runs/" + str(p.verify_run),
                    deadline, "RUN")
    if (run.get("id") != p.verify_run or
        run.get("head_sha") != p.origin_main or
        run.get("conclusion") != "success" or run.get("event") != "push" or
        (profile is not None and run.get('head_branch') != 'main')):
        raise CacheFailure("PINNED_CACHE_RUN_IDENTITY_REJECTED")
    artifact = cache_api("/actions/artifacts/" + str(p.artifact_id),
                         deadline, "ARTIFACT")
    if artifact.get("expired") is True:
        raise CacheFailure("PINNED_CACHE_ARTIFACT_EXPIRED")
    origin = artifact.get("workflow_run")
    if (artifact.get("id") != p.artifact_id or
        artifact.get("name") != p.artifact_name or
        artifact.get("size_in_bytes") != p.zip_bytes or
        artifact.get("digest") != "sha256:" + p.zip_sha256 or
        artifact.get("expired") is not False or type(origin) is not dict or
        origin.get("id") != p.verify_run or
        origin.get("head_sha") != p.origin_main):
        raise CacheFailure("PINNED_CACHE_ARTIFACT_IDENTITY_REJECTED")
    with archive.open("xb") as stream:
        cache_api("/actions/artifacts/" + str(p.artifact_id) + "/zip",
                  deadline, "DOWNLOAD", stream=stream)
    if profile is not None and time.monotonic() >= deadline:
        raise CacheFailure('PINNED_CACHE_WALL_DEADLINE')
    result = restore(archive, output, transfer, commit, **_options(profile))
    # Completion check, not a hard alarm during Python hashing/extraction.
    # The unchanged parent worker supplies the full-stage 1800 s hard ceiling.
    if profile is not None and time.monotonic() > deadline:
        raise CacheFailure('PINNED_CACHE_WALL_DEADLINE')
    return result


def preserve_cache_failure(path: Path, error: Exception, commit: str, *, profile=None) -> None:
    # Known admission messages describe paths/identity only. Never serialize
    # subprocess stdout/stderr, request headers or a redirected download URL.
    p = _settings(profile)
    record = {
        "schema_version": 1,
        "status": "CACHE_UNAVAILABLE_OR_REJECTED",
        "reason_code": (str(error) if isinstance(error, CacheFailure) else
                        "PINNED_CACHE_SOURCE_IDENTITY_REJECTED"),
        "reason_detail": (str(error)[:180] if isinstance(error, ValueError)
                          else type(error).__name__),
        "source_commit": commit,
        "original_source_artifact_id": p.artifact_id,
        "original_source_zip_sha256_expected": p.zip_sha256,
        "cache_wall_seconds_ceiling": CACHE_BUDGET_SECONDS,
        "next_allowed_source": speech_source.URL,
        "next_allowed_archive_sha256": ORIGIN_ARCHIVE_SHA256,
        "original_source_reacquisition_completed": False,
        "source_substitution": False,
        "acoustic_validation_qualified": False,
        "shipping_authority": False,
    }
    if profile is not None:
        record.update({'snapshot_profile':p.name, 'source_speaker_offset':p.offset,
                       'source_id':p.source_id})
    with path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, sort_keys=True, separators=(",", ":"),
                  allow_nan=False)
        stream.write("\n")


def fresh_transport_destinations(archive: Path, output: Path, transfer: Path,
                                 cache_failure: Path) -> None:
    fresh_destinations(output, transfer)
    for path in (archive, cache_failure):
        need(path.parent.resolve() == output.parent.resolve() and
             not path.exists() and not path.is_symlink(),
             "CACHE_DESTINATION_NOT_FRESH_OR_LOCAL")
    need(len({path.resolve() for path in
              (archive, output, transfer, cache_failure)}) == 4,
         "OVERLAPPING_SOURCE_TRANSPORT_DESTINATIONS")


def restore_recent_cache(archive: Path, output: Path, transfer: Path,
                         cache_failure: Path, commit: str, deadline: float) -> dict:
    """Reuse only the source members, never the previous acoustic results."""
    origin = recent_cache.discover(cache_api, deadline, commit, ORIGIN_VERIFY_RUN)
    with archive.open("xb") as stream:
        cache_api("/actions/artifacts/" + str(origin["artifact_id"]) + "/zip",
                  deadline, "RECENT_DOWNLOAD", stream=stream)
    return restore(archive, output, transfer, commit, recent_origin=origin,
                   cache_failure=cache_failure, recent_deadline=deadline)


def recent_failure_path(output):
    return output.parent / RECENT_FAILURE_NAME


def preserve_recent_failure(output, error, commit):
    reason = (str(error) if isinstance(error, (recent_cache.RecoveryError, CacheFailure)) and
              re.fullmatch("(?:RECENT|PINNED)_CACHE_[A-Z_]+", str(error)) else
              "RECENT_CACHE_SOURCE_OR_TRANSPORT_REJECTED")
    with recent_failure_path(output).open("x", encoding="utf-8") as stream:
        json.dump({"schema_version": 1, "status": "RECENT_CACHE_UNAVAILABLE_OR_REJECTED",
                   "reason_code": reason, "source_commit": commit,
                   "source_substitution": False, "shipping_authority": False,
                   "acoustic_validation_qualified": False}, stream,
                  sort_keys=True, separators=(",", ":"), allow_nan=False)
        stream.write("\n")


def verify_recent_receipt(record, cache_failure, commit):
    origin = recent_cache.validate_origin(record.get("recent_protected_main_cache"))
    need(origin["main_sha"] != commit and origin["run_id"] != ORIGIN_VERIFY_RUN and
         record.get("protected_source_main") == origin["main_sha"] and
         record.get("protected_source_verify_run_id") == origin["run_id"] and
         record.get("protected_source_release_run_id") is None and
         record.get("original_source_artifact_id") == origin["artifact_id"] and
         record.get("original_source_artifact_name") == origin["artifact_name"] and
         record.get("original_source_artifact_zip_sha256") == origin["zip_sha256"] and
         record.get("failed_original_pin_id") == ORIGIN_ARTIFACT and
         record.get("independently_admitted_selected_sha256") == ADMITTED_SOURCE_SHA256 and
         record.get("artifact_cache_identity_revalidated_this_run") is True and
         record.get("original_full_archive_rehashed_this_run") is False and
         record.get("previous_scientific_score_reused") is False and
         record.get("current_acoustic_evaluation_completed") is False and
         record.get("source_substitution") is False and
         record.get("public_product_or_device_qualification") is False and
         record.get("verification_authority") == "source-bytes-only-fresh-science-required" and
         cache_failure.is_file() and not cache_failure.is_symlink() and
         record.get("cache_failure_receipt_sha256") == sha256_file(cache_failure),
         "RECENT_CACHE_TRANSFER_RECEIPT_IDENTITY_REJECTED")
    return origin


def acquire_source_worker(archive: Path, output: Path, transfer: Path,
                          cache_failure: Path, commit: str, *, profile=None,
                          allow_recent_recovery=False) -> dict:
    """Entire expensive stage, supervised once by acquire_source's parent.

    No nested process-group supervisor: gh and FFmpeg remain in this worker's
    process group so the parent can terminate cache, decode and verification.
    """
    started = time.monotonic()
    strict_source_commit(commit)
    original_source_policy(**_options(profile))
    fresh_transport_destinations(archive, output, transfer, cache_failure)
    if allow_recent_recovery:
        need(profile is None and not recent_failure_path(output).exists() and
             not recent_failure_path(output).is_symlink() and
             recent_failure_path(output).resolve() not in
             {archive.resolve(), output.resolve(), transfer.resolve(), cache_failure.resolve()},
             "RECENT_CACHE_SCOPE_OR_DESTINATION_REJECTED")
    recent_eligible = False
    try:
        return restore_cache(archive, output, transfer, commit, **_options(profile))
    except Exception as error:
        recent_eligible = (allow_recent_recovery and isinstance(error, CacheFailure) and
                           str(error) in RECENT_UNAVAILABLE)
        preserve_cache_failure(cache_failure, error, commit, **_options(profile))
        # A partially published result must not be reused or overwritten.
        fresh_destinations(output, transfer)
    finally:
        archive.unlink(missing_ok=True)
    if recent_eligible:
        try:
            return restore_recent_cache(archive, output, transfer, cache_failure, commit,
                                        started + CACHE_BUDGET_SECONDS)
        except Exception as error:
            preserve_recent_failure(output, error, commit)
            fresh_destinations(output, transfer)
        finally:
            archive.unlink(missing_ok=True)
    need(time.monotonic() - started < stage_budget.DEADLINE_SECONDS,
         "ORIGINAL_SOURCE_ACQUISITION_WALL_DEADLINE")
    # Only this dedicated worker mutates its environment. Public-source
    # download and any external decoder must not receive GitHub credentials.
    with without_github_auth():
        reacquire_official(output, transfer, commit,
                           cache_failure=cache_failure, **_options(profile))
    # This independent readback is also inside the outer wall-clock deadline.
    check_source(output, **_options(profile))
    need(transfer.is_file() and not transfer.is_symlink() and
         0 < transfer.stat().st_size <= 32*1024,
         "OFFICIAL_SOURCE_TRANSFER_RECEIPT_MISSING")
    record = json.loads(transfer.read_text("utf-8"))
    check_profile_receipt(record, profile)
    need(record.get("source_commit") == commit and
         record.get("decision") == DECISION and
         record.get("acquisition_path") == "official-original-archive" and
         record.get("cache_failure_receipt_sha256") == sha256_file(cache_failure),
         "OFFICIAL_SOURCE_TRANSFER_RECEIPT_IDENTITY_REJECTED")
    return record


def acquire_source(archive: Path, output: Path, transfer: Path,
                   cache_failure: Path, commit: str, *, profile=None,
                   allow_recent_recovery=False) -> dict:
    """Supervise cache + hash/extraction/readback + official source as one stage."""
    started = time.monotonic()
    strict_source_commit(commit)
    p = _settings(profile)
    original_source_policy(**_options(profile))
    fresh_transport_destinations(archive, output, transfer, cache_failure)
    command = [sys.executable, str(Path(__file__).resolve()),
               "--acquire-worker", "--zip", str(archive.resolve()),
               "--output", str(output.resolve()),
               "--transfer", str(transfer.resolve()),
               "--cache-failure", str(cache_failure.resolve()),
               "--execution-source", commit]
    if profile is not None:
        command += ['--profile', p.name]
    if allow_recent_recovery:
        need(profile is None and not recent_failure_path(output).exists() and
             not recent_failure_path(output).is_symlink() and
             recent_failure_path(output).resolve() not in
             {archive.resolve(), output.resolve(), transfer.resolve(), cache_failure.resolve()},
             "RECENT_CACHE_SCOPE_OR_DESTINATION_REJECTED")
        command.append("--recover-recent-protected-main")
    try:
        remaining = stage_budget.DEADLINE_SECONDS - (time.monotonic() - started)
        need(remaining > 0, "ORIGINAL_SOURCE_ACQUISITION_WALL_DEADLINE")
        succeeded = stage_budget.run_bounded(
            command, output, remaining, cwd=ROOT, env=os.environ.copy())
        need(succeeded, "ORIGINAL_SOURCE_ACQUISITION_WORKER_FAILED")
        # Full independent source checking happened inside the supervised
        # worker. The parent only reads a bounded completion receipt.
        need(transfer.is_file() and not transfer.is_symlink() and
             0 < transfer.stat().st_size <= 32*1024,
             "SOURCE_TRANSFER_RECEIPT_MISSING")
        record = json.loads(transfer.read_text("utf-8"))
        check_profile_receipt(record, profile)
        need(type(record) is dict and record.get("source_commit") == commit and
             record.get("decision") == DECISION and
             record.get("acquisition_path") in
                 ("protected-artifact-cache", "official-original-archive", "protected-main-source-recovery"),
             "SOURCE_TRANSFER_RECEIPT_IDENTITY_REJECTED")
        if record["acquisition_path"] == "protected-artifact-cache":
            need(record.get("original_source_artifact_zip_sha256") ==
                 p.zip_sha256, "CACHE_TRANSFER_RECEIPT_IDENTITY_REJECTED")
        elif record["acquisition_path"] == "protected-main-source-recovery":
            need(allow_recent_recovery and profile is None, "RECENT_CACHE_NOT_AUTHORIZED")
            verify_recent_receipt(record, cache_failure, commit)
        else:
            need(cache_failure.is_file() and not cache_failure.is_symlink() and
                 record.get("cache_failure_receipt_sha256") ==
                 sha256_file(cache_failure),
                 "OFFICIAL_SOURCE_TRANSFER_RECEIPT_IDENTITY_REJECTED")
        need(time.monotonic() - started <= stage_budget.DEADLINE_SECONDS,
             "ORIGINAL_SOURCE_ACQUISITION_WALL_DEADLINE")
        return record
    except Exception as error:
        preserve_failure(output, error, commit,
                         reason_code="ORIGINAL_SOURCE_STAGE_REJECTED", **_options(profile))
        raise
    finally:
        archive.unlink(missing_ok=True)


def preserve_failure(output: Path, error: Exception, commit: str, *,
                     reason_code: str =
                     "PINNED_ORIGINAL_SOURCE_ARTIFACT_TRANSFER_REJECTED",
                     profile=None) -> bool:
    p = _settings(profile)
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
            "original_source_artifact_id": p.artifact_id,
            "original_source_zip_sha256_expected": p.zip_sha256,
            "original_source_url": speech_source.URL,
            "original_archive_sha256_expected": ORIGIN_ARCHIVE_SHA256,
            "source_substitution": False,
            "shipping_authority": False,
            "acoustic_validation_qualified": False
        }
        if profile is not None:
            report.update({'snapshot_profile':p.name, 'source_speaker_offset':p.offset,
                           'source_id':p.source_id})
        with marker.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)
            stream.write("\n")
        return True
    except (OSError, ValueError):
        return False


def self_test(*, profile=None) -> None:
    original_source_policy(**_options(profile))
    if profile is not None:
        from speech_source_cas import transport_reader
        transport_reader()
        print('FE03_SPATIAL_SOURCE_CACHE_PROFILE_POLICY_PASS',
              _settings(profile).name, 'no_data_promotion')
        return
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
    mode.add_argument("--acquire-worker", action="store_true", help=argparse.SUPPRESS)
    mode.add_argument("--reacquire-official", action="store_true")
    mode.add_argument("--replay-official-worker", action="store_true", help=argparse.SUPPRESS)
    mode.add_argument("--mark-download-failure", action="store_true")
    p.add_argument("--zip", type=Path)
    p.add_argument("--original-archive", type=Path)
    p.add_argument("--cache-failure", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--transfer", type=Path)
    p.add_argument("--execution-source", default="")
    p.add_argument("--recover-recent-protected-main", action="store_true",
                   help="Allow one byte-only successor transport after expired/unavailable offset-0 pin")
    p.add_argument('--profile', choices=profiles.CHOICES,
                   help='Explicit closed source identity; omitted retains original offset-0 behavior')
    args = p.parse_args()
    profile = profiles.select(args.profile)
    preexisting_output = (args.output is not None and
                          (args.output.exists() or args.output.is_symlink()))
    try:
        need(not args.recover_recent_protected_main or
             (profile is None and (args.acquire or args.acquire_worker)),
             "RECENT_CACHE_SCOPE_REJECTED")
        if args.self_test:
            self_test(**_options(profile))
            return
        need(args.output is not None and
             re.fullmatch("[0-9a-f]{40}", args.execution_source) is not None,
             "MISSING_EXECUTION_SHA_OR_OUTPUT")
        if args.mark_download_failure:
            need(not args.output.exists(), "FAILURE_OUTPUT_MUST_BE_FRESH")
            raise AdmissionError("PINNED_GITHUB_ARTIFACT_DOWNLOAD_FAILED")
        need(args.transfer is not None, "SOURCE_TRANSFER_RECEIPT_MISSING")
        replay = args.reacquire_official or args.replay_official_worker
        need(args.original_archive is None or replay,
             "LOCAL_ORIGINAL_ARCHIVE_ONLY_FOR_EXPLICIT_ORIGINAL_REPLAY")
        if replay:
            need(args.original_archive is not None,
                 "EXPLICIT_LOCAL_ORIGINAL_ARCHIVE_REQUIRED_USE_ACQUIRE_FOR_NETWORK")
            execute = (replay_official_worker if args.replay_official_worker else
                       replay_official_archive)
            result = execute(args.original_archive, args.output, args.transfer,
                             args.execution_source, cache_failure=args.cache_failure,
                             **_options(profile))
        else:
            need(args.zip is not None, "SOURCE_ZIP_MISSING")
            if args.acquire or args.acquire_worker:
                need(args.cache_failure is not None, "CACHE_FAILURE_RECEIPT_MISSING")
                acquire = (acquire_source_worker if args.acquire_worker else
                           acquire_source)
                options = _options(profile)
                if args.recover_recent_protected_main:
                    options["allow_recent_recovery"] = True
                result = acquire(args.zip, args.output, args.transfer,
                                 args.cache_failure, args.execution_source, **options)
            else:
                result = restore(args.zip, args.output, args.transfer,
                                 args.execution_source, **_options(profile))
        print("FE03_ORIGINAL_SOURCE_REVALIDATED",
              result["source_commit"], result["acquisition_path"],
              result["verified_selected_source_member_count"])
    except Exception as exc:
        if args.output is not None and not preexisting_output:
            reason = ("OFFICIAL_ORIGINAL_SOURCE_REACQUISITION_REJECTED"
                      if args.reacquire_official or args.replay_official_worker else
                      "PINNED_ORIGINAL_SOURCE_ACQUISITION_REJECTED"
                      if args.acquire or args.acquire_worker else
                      "PINNED_ORIGINAL_SOURCE_ARTIFACT_TRANSFER_REJECTED")
            preserve_failure(args.output, exc, args.execution_source,
                             reason_code=reason, **_options(profile))
        raise SystemExit(FAILURE+": "+str(exc)[:200]) from None


if __name__ == "__main__":
    main()
