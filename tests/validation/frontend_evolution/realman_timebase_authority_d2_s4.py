#!/usr/bin/env python3
"""FE03 A2 D2-S4: bounded pinned official RealMAN source/timebase audit.

Only README + published code + sealed first-party metadata; absolutely no
original RAR, FLAC, PCM, CSV row transfer or acoustic/DOA/beamformer scoring.
PREREG: https://github.com/jiying2007/audio-pipeline/issues/713
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import realman_source_metadata_d0 as d0
import realman_flac_quartets_d2_s2 as s2

ROOT = Path(__file__).resolve().parents[3]
FROZEN = Path(__file__).with_name("realman_timebase_d2_s4_source_anchor.json")
UPSTREAM_REV = "9dc59f03a98149bc7fe5524d1363af83a5b399f7"
GITHUB_RAW = "https://raw.githubusercontent.com/Audio-WestlakeU/RealMAN/" + UPSTREAM_REV + "/"
PASS = "REALMAN_D2_S4_NATIVE_CAPTURE_TIMEBASE_DOCUMENTED_RESEARCH_ONLY"
UNKNOWN = "REALMAN_D2_S4_CAPTURE_TIMEBASE_UNRESOLVED"
BLOCKED = "REALMAN_D2_S4_SOURCE_METADATA_NOT_ADMITTED"
MAX_SOURCE_SIZE = 128 * 1024
REQUIRED = (
    "four_channel_common_capture_clock",
    "hardware_sample_zero_origin",
    "per_channel_capture_offset_and_drift",
    "physical_channel_order_and_polarity_calibration",
    "audio_to_fisheye_video_time_origin",
    "moving_source_label_to_pcm_sample_clock",
    "exact_frozen_stem_to_original_csv_row_identity",
)
SOURCE_HASHES = {
    "README.md": "a327db37ad48743725dc35cecfecfbca251e683b",
    "baselines/SSL/RecordData.py": "affc5d50ca22751a7cf836b58865986164a55cb6",
    "baselines/SSL/utils_.py": "0f7554bbfd65f2c52a917526e277a264b325d102",
}


class Reject(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def require(ok, code="S4_SOURCE_METADATA_INVALID"):
    if not ok:
        raise Reject(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(path, cap=65536):
    require(path.is_file() and 0 < path.stat().st_size <= cap, "S4_METADATA_MISSING")
    def no_duplicate(pairs):
        result = {}
        for k, v in pairs:
            require(k not in result, "S4_DUPLICATE_JSON_FIELD")
            result[k] = v
        return result
    def no_nonfinite(value):
        raise Reject("S4_NONFINITE_JSON_REJECTED")
    try:
        return json.loads(path.read_text(encoding="utf-8"),
                          object_pairs_hook=no_duplicate,
                          parse_constant=no_nonfinite)
    except (UnicodeError, OSError, ValueError):
        raise Reject("S4_METADATA_PARSE_REJECTED") from None


def git_blob_sha1(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def bounded_git_source_url(path):
    require(path in SOURCE_HASHES, "S4_UNAPPROVED_OFFICIAL_SOURCE")
    url = GITHUB_RAW + path
    p = urlsplit(url)
    require(p.scheme == "https" and p.hostname == "raw.githubusercontent.com"
            and p.username is None and p.password is None and p.port in (None, 443)
            and p.query == "" and p.fragment == "" and
            p.path.endswith("/" + path), "S4_SOURCE_URL_NOT_PINNED")
    return url


class NoCrossHostRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Reject("S4_SOURCE_REDIRECT_NOT_ADMITTED")


def read_official(path):
    """Only GitHub raw, exact immutable commit, one small source file."""
    url = bounded_git_source_url(path)
    req = Request(url, headers={
        "Accept-Encoding": "identity",
        "User-Agent": "audio-pipeline-realman-timebase-metadata-s4/1",
        "Accept": "text/plain,application/octet-stream",
    })
    try:
        with build_opener(NoCrossHostRedirect()).open(req, timeout=20) as response:
            require(response.geturl() == url, "S4_SOURCE_URL_CHANGED")
            require(response.headers.get("Content-Encoding", "identity").lower()
                    in ("", "identity"), "S4_SOURCE_ENCODING_UNSUPPORTED")
            n = response.headers.get("Content-Length")
            require(n is None or (n.isdecimal() and int(n) <= MAX_SOURCE_SIZE),
                    "S4_SOURCE_TOO_LARGE")
            raw = response.read(MAX_SOURCE_SIZE + 1)
            require(0 < len(raw) <= MAX_SOURCE_SIZE and
                    (n is None or len(raw) == int(n)), "S4_SOURCE_TOO_LARGE")
            require(git_blob_sha1(raw) == SOURCE_HASHES[path],
                    "S4_OFFICIAL_GIT_BLOB_HASH_MISMATCH")
            return raw
    except Reject:
        raise
    except (HTTPError, URLError, TimeoutError, OSError):
        raise Reject("S4_SOURCE_TRANSPORT_UNAVAILABLE") from None


def source_line(text, phrase):
    positions = [n for n, line in enumerate(text.splitlines(), 1) if phrase in line]
    require(len(positions) >= 1, "S4_OFFICIAL_SOURCE_CONVENTION_MISSING")
    return positions[0]


def inspect_three_sources(raw):
    texts = {}
    for path, code in raw.items():
        require(git_blob_sha1(code) == SOURCE_HASHES[path],
                "S4_SOURCE_BYTES_MISMATCH")
        try:
            texts[path] = code.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise Reject("S4_SOURCE_TEXT_INVALID") from None
    readme = texts["README.md"]
    loader = texts["baselines/SSL/RecordData.py"]
    geom = texts["baselines/SSL/utils_.py"]
    require("32-channel microphone array" in readme and
            "fisheye camera" in readme, "S4_32MIC_RECORDING_NOTICE_MISSING")
    require("def load_signals(self, sig_path, use_mic_id):" in loader
            and "np.stack(channels, axis=-1)" in loader
            and "self.resample" in loader,
            "S4_CHANNEL_LOADER_PROVENANCE_INVALID")
    require("def audiowu_high_array_geometry()" in geom
            and "pos_rcv[1:9, :]" in geom
            and "radius=R, mic_num=8" in geom,
            "S4_NATIVE_MIC_GEOMETRY_CONTRACT_DRIFT")
    return {
        "README.md": {
            "git_blob_sha1": SOURCE_HASHES["README.md"],
            "source_sha256": sha(raw["README.md"]),
            "array_statement_line": source_line(readme, "32-channel microphone array"),
            "fisheye_camera_annotation_line": source_line(readme, "fisheye camera"),
        },
        "baselines/SSL/RecordData.py": {
            "git_blob_sha1": SOURCE_HASHES["baselines/SSL/RecordData.py"],
            "source_sha256": sha(raw["baselines/SSL/RecordData.py"]),
            "channel_load_line": source_line(loader, "def load_signals(self, sig_path, use_mic_id):"),
            "filename_suffix_line": source_line(loader, "sig_path.replace('.flac',f'_CH{i}.flac')"),
            "stack_line": source_line(loader, "np.stack(channels, axis=-1)"),
            "resampling_line": source_line(loader, "def resample(self,mic_signal,fs,new_fs):"),
            "nominal_10hz_label_slice_line": source_line(loader, "self.target_fs / 10"),
        },
        "baselines/SSL/utils_.py": {
            "git_blob_sha1": SOURCE_HASHES["baselines/SSL/utils_.py"],
            "source_sha256": sha(raw["baselines/SSL/utils_.py"]),
            "geometry_definition_line": source_line(geom, "def audiowu_high_array_geometry()"),
            "central_radius_line": source_line(geom, "R = 0.03"),
            "inner_ring_line": source_line(geom, "pos_rcv[1:9, :]"),
        },
    }


def frozen_authority():
    a = strict_json(FROZEN, cap=16384)
    require(isinstance(a, dict)
            and a.get("schema_version") == 1
            and a.get("preregistration") ==
            "https://github.com/jiying2007/audio-pipeline/issues/713"
            and a.get("official_code_revision") == UPSTREAM_REV
            and a.get("s3r_main_sha") ==
            "1be9b89af778783bdbe695c72d048b3d77eee948"
            and a.get("s3r_codec_decision") ==
            "REALMAN_D2_S3R_GYM_8_PCM_MD5_VERIFIED_RESEARCH_ONLY"
            and a.get("s3r_source_run_id") == 38100098794
            and a.get("s3r_release_run_id") == 38101857116
            and a.get("s2_selected_name_list_sha256") ==
            "7b6458adc4d335c6c1897f98e51501f897585623359ef147494d7635d4d9be37"
            and a.get("s2_receipt_sha256") ==
            "16e690a4b32f0aeb9f011900af55f83f302a6f29662f2bb1601c058257ae3190"
            and a.get("archive_sha256") ==
            "8175dad412a752a34bdf2722f7e9b5ee671b62e67dfe5179f7a769d63912b2ea"
            and a.get("source_audio_download_authorized") is False
            and a.get("pcm_decode_authorized") is False
            and a.get("doa_or_bf_score_authorized") is False
            and a.get("shipping_authority") is False
            and a.get("commercial_authority") is False
            and a.get("expected_conservative_decision") == UNKNOWN,
            "S4_FROZEN_PROTOCOL_DRIFT")
    require(a.get("required_authorities") == list(REQUIRED)
            and a.get("allowed_decisions") == [PASS, UNKNOWN, BLOCKED]
            and a.get("frozen_original_channel_ids") == [1, 3, 5, 7]
            and a.get("native_sampling_hz") == 48000
            and a.get("native_bits_per_sample") == 16
            and a.get("frozen_original_member_count") == 8
            and a.get("static_samples_per_channel") == 238895
            and a.get("moving_samples_per_channel") == 237071,
            "S4_FROZEN_PCM_GEOMETRY_CHANGED")
    require([(x.get("path"), x.get("git_blob_sha1"))
             for x in a.get("source_files", [])
             if isinstance(x, dict)] == list(SOURCE_HASHES.items()),
            "S4_OFFICIAL_SOURCE_SHA_DRIFT")
    old = a.get("d1q_evidence")
    require(isinstance(old, dict)
            and old.get("artifact_id") == 11687810612
            and old.get("zip_sha256") ==
            "645f53f5c262bfff6c02c5b9febb8bf02acdd210592d3e3c5a6009c6084b26cb"
            and old.get("receipt_sha256") ==
            "6aed993d727b32f047d4857324cd5ff8f248bdbc85844ac194b4b93d6838468a"
            and old.get("original_static_csv_sha256") ==
            "1f0be80d4ab1cc023e7599bf7e564f84acaf36ccad73fd59c992cc9e853f1233"
            and old.get("original_moving_csv_sha256") ==
            "542f04d011c2b6fbdd49bfa51c423942fe854e7e0615fb1f67954c762ad20bf5"
            and old.get("invalid_car_electric_negative_distance_rows") == 544
            and old.get("original_full_csv_admitted") is False
            and old.get("retained_shared_scenes_include_gym") is True,
            "S4_HISTORICAL_CSV_STATUS_DRIFT")
    contract = d0.authoritative_contract()
    require(contract["dataset_revision"] == a["dataset_revision"]
            and contract["physical_slot_map"] == [1, 3, 5, 7]
            and contract["raw_capture_sample_rate_hz"] == 48000
            and contract["number_of_source_microphones"] == 32
            and contract["nominal_label_rate_hz"] == 10
            and contract["label_timebase_alignment"] ==
            "UNVERIFIED_NO_TIMESTAMP_TO_AUDIO_CONVERSION"
            and contract["csv_required_columns"] ==
            ["filename", "real_st", "real_ed", "video_st", "video_ed",
             "angle(°)", "distance", "ele"],
            "S4_EXISTING_D0_SOURCE_CONTRACT_DRIFT")
    anchor_path = ROOT / a["s3r_anchor_path"]
    s2_anchor = strict_json(anchor_path, cap=32768)
    require(s2_anchor.get("s2_selected_path_sha256") ==
            a["s2_selected_name_list_sha256"]
            and s2_anchor.get("s2_original_receipt_sha256") ==
            a["s2_receipt_sha256"]
            and s2_anchor.get("archive_sha256") ==
            a["archive_sha256"]
            and len(s2_anchor.get("members", [])) == 8,
            "S4_ORIGINAL_S2_IDENTITY_INVALID")
    roles = [(x["role"], x["channel"]) for x in s2_anchor["members"]]
    require(roles == [(r, c) for r in ("static", "moving")
                      for c in (1, 3, 5, 7)],
            "S4_ORIGINAL_PHYSICAL_CHANNEL_MAP_DRIFT")
    for x in s2_anchor["members"]:
        info = x["streaminfo"]
        require(info["native_sample_rate_hz"] == 48000
                and info["bits_per_sample"] == 16
                and info["flac_encoded_channels"] == 1
                and info["total_samples"] ==
                (238895 if x["role"] == "static" else 237071),
                "S4_ORIGINAL_NATIVE_FORMAT_DRIFT")
    return a


def validate_nonpromotion(outcome):
    require(outcome.get("decision") == UNKNOWN and
            isinstance(outcome.get("required_authority_evidence"), dict) and
            set(outcome["required_authority_evidence"]) == set(REQUIRED) and
            all(x.get("status") == "unsupported" for x in
                outcome["required_authority_evidence"].values()) and
            all(outcome.get(flag) is False for flag in (
                "sample_zero_documented", "shared_adc_clock_documented",
                "per_mic_phase_calibrated", "audio_video_time_origin_documented",
                "original_full_csv_admitted", "original_realman_audio_downloaded",
                "original_csv_rows_downloaded", "original_PCM_decoded",
                "doa_or_bf_scores_calculated", "shipping_authority")),
            "S4_UNSUPPORTED_CAPTURE_TIMEBASE_PROMOTED")


def interpretation(manifest, source_readback):
    require(set(source_readback) == set(SOURCE_HASHES)
            and all(source_readback[k]["git_blob_sha1"] == v
                    for k, v in SOURCE_HASHES.items()),
            "S4_SOURCE_LINEAGE_MISSING")
    # Direct code evidence: per-file channel suffixing and software stacking,
    # NOT common ADC clock, sample-zero, polarity or AV clock calibration.
    findings = {name: {
        "status": "unsupported",
        "reason": "NO_DIRECT_CAPTURE_TIME_OR_CALIBRATION_WITNESS_IN_PINNED_SOURCES",
    } for name in REQUIRED}
    require(all(v["status"] == "unsupported" for v in findings.values()),
            "S4_UNSUPPORTED_CAPTURE_TIMEBASE_PROMOTED")
    outcome = {
        "decision": UNKNOWN,
        "required_authority_evidence": findings,
        "documented_native_32_mic_geometry": True,
        "documented_source_filename_channel_convention": True,
        "software_stacked_channels_without_clock_validation": True,
        "nominal_label_rate_hz": 10,
        "native_audio_format_bytes_verified_upstream_s3r_only": True,
        "original_full_csv_admitted": False,
        "d1q_gym_scene_quarantine_is_not_exact_stem_label_join": True,
        "sample_zero_documented": False,
        "shared_adc_clock_documented": False,
        "per_mic_phase_calibrated": False,
        "audio_video_time_origin_documented": False,
        "original_realman_audio_downloaded": False,
        "original_csv_rows_downloaded": False,
        "original_PCM_decoded": False,
        "doa_or_bf_scores_calculated": False,
        "shipping_authority": False,
    }
    validate_nonpromotion(outcome)
    return outcome


def exact_checkout():
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    require(bool(re.fullmatch(r"[0-9a-f]{40}", actual))
            and os.environ.get("GITHUB_SHA") == actual,
            "S4_ACTION_CHECKOUT_SHA_NOT_AUTHORITATIVE")
    return actual


def identity():
    return {
        "schema_version": 1,
        "experiment_id": "FE03-A2-D2-S4-REALMAN-NATIVE-TIMEBASE-METADATA",
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/713",
        "source_commit": exact_checkout(),
        "anchor_sha256": sha(FROZEN.read_bytes()),
        "s4_script_sha256": sha(Path(__file__).read_bytes()),
        "d0_contract_sha256": sha(d0.CONTRACT.read_bytes()),
        "s2_anchor_sha256": sha((ROOT / "tests/validation/frontend_evolution/"
                                "realman_s2_frozen_anchor_d2_s3r.json").read_bytes()),
        "official_code_revision": UPSTREAM_REV,
        "source_role": "disclosed-development-metadata-only",
        "original_d1_csv_source_admitted": False,
        "captured_four_mic_sync_verified": False,
        "sample_zero_origin_verified": False,
        "camera_audio_timebase_verified": False,
        "doa_accuracy_measured": False,
        "bf_or_aec_performance_measured": False,
        "shipping_authority": False,
        "research_rights": "NONCOMMERCIAL_ATTRIBUTION_ONLY",
    }


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    out = path.with_suffix(".tmp")
    out.write_text(json.dumps(data, separators=(",", ":"), sort_keys=True,
                              ensure_ascii=False, allow_nan=False) + "\n",
                   encoding="utf-8")
    out.replace(path)


def collect(receipt):
    result = identity()
    result["collected_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        frozen = frozen_authority()
        original = {path: read_official(path) for path in SOURCE_HASHES}
        source_evidence = inspect_three_sources(original)
        result["official_sources"] = source_evidence
        result["audit"] = interpretation(frozen, source_evidence)
        result["decision"] = UNKNOWN
        status = 0
    except (Reject, OSError, subprocess.SubprocessError) as err:
        result["decision"] = BLOCKED
        result["failure_code"] = getattr(err, "code", "S4_UNEXPECTED_SOURCE_AUDIT_FAILURE")
        status = 1
    save(receipt, result)
    print("decision=" + result["decision"] +
          " failure=" + result.get("failure_code", "NONE"), flush=True)
    return status


def verify(receipt_path):
    result = strict_json(receipt_path)
    require(isinstance(result, dict), "S4_RECEIPT_NOT_OBJECT")
    expected = identity()
    for key, value in expected.items():
        require(result.get(key) == value, "S4_RECEIPT_IDENTITY_DRIFT")
    require(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                              result.get("collected_at_utc", ""))),
            "S4_RECEIPT_DATE_INVALID")
    if result.get("decision") == UNKNOWN:
        require(set(result) == set(expected) |
                {"collected_at_utc", "official_sources", "audit", "decision"},
                "S4_RECEIPT_FIELDS_DRIFT")
        frozen = frozen_authority()
        independent = inspect_three_sources({
            path: read_official(path) for path in SOURCE_HASHES
        })
        validate_nonpromotion(result.get("audit", {}))
        require(result.get("official_sources") == independent
                and result.get("audit") == interpretation(frozen, independent),
                "S4_INDEPENDENT_SOURCE_READBACK_MISMATCH")
    else:
        require(result.get("decision") == BLOCKED
                and bool(re.fullmatch(r"S4_[A-Z0-9_]+",
                                      result.get("failure_code", "")))
                and set(result) == set(expected) |
                {"collected_at_utc", "decision", "failure_code"},
                "S4_FAILED_SOURCE_RECEIPT_INVALID")
    print("S4_INDEPENDENT_READBACK_CONSISTENT=" + result["decision"])


def self_test():
    a = frozen_authority()
    require(len(a["required_authorities"]) == 7 and
            len(SOURCE_HASHES) == 3, "S4_OFFLINE_CONTRACT_INVALID")
    assert bounded_git_source_url("README.md").startswith(GITHUB_RAW)
    for bad in ("../../README.md", "val/ma_noisy_speech/Gym.rar",
                "README.md?ref=main", "baselines/SSL/RecordData.py/.."):
        try:
            bounded_git_source_url(bad)
        except Reject:
            pass
        else:
            raise AssertionError("unapproved source path admitted")
    require(git_blob_sha1(b"hello") ==
            hashlib.sha1(b"blob 5\0hello").hexdigest())
    for modified in (b"file contents", b"", b"\x00"):
        require(git_blob_sha1(modified) != SOURCE_HASHES["README.md"])
    readings = {k: {"git_blob_sha1": v} for k, v in SOURCE_HASHES.items()}
    outcome = interpretation(a, readings)
    validate_nonpromotion(outcome)
    for mutation in [
        {"sample_zero_documented": True},
        {"shared_adc_clock_documented": True},
        {"audio_video_time_origin_documented": True},
        {"original_full_csv_admitted": True},
        {"decision": PASS},
    ]:
        false_claim = dict(outcome, **mutation)
        try:
            validate_nonpromotion(false_claim)
        except Reject:
            pass
        else:
            raise AssertionError("false original capture-clock authority accepted")
    bad_readback = copy.deepcopy(readings)
    bad_readback["README.md"]["git_blob_sha1"] = "0" * 40
    try:
        interpretation(a, bad_readback)
    except Reject:
        pass
    else:
        raise AssertionError("source digest tampering admitted")
    require(a["frozen_original_channel_ids"] == [1, 3, 5, 7]
            and a["d1q_evidence"]["invalid_car_electric_negative_distance_rows"] == 544
            and a["d1q_evidence"]["original_full_csv_admitted"] is False)
    print("REALMAN_D2_S4_OFFLINE_SELF_TEST_PASS; zero audio and no remote fetch")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("self-test", "collect", "verify"))
    p.add_argument("--receipt")
    a = p.parse_args()
    if a.action == "self-test":
        self_test()
        return 0
    require(bool(a.receipt), "S4_RECEIPT_ARGUMENT_MISSING")
    path = Path(a.receipt).resolve()
    if a.action == "collect":
        return collect(path)
    verify(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
