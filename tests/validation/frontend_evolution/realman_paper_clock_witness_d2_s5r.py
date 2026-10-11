#!/usr/bin/env python3
"""FE03 A2 D2-S5R: pinned pypdf on one official NeurIPS paper, author claims only.

Preregistered at https://github.com/jiying2007/audio-pipeline/issues/720.
Original #716 / draft #717 preinstalled-tool failure remains FAILED.
No original RAR, FLAC, CSV, acoustic scoring, or shipping authority.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import realman_pypdf_toolchain_d2_s5_t0 as t0

ROOT = Path(__file__).resolve().parents[3]
ANCHOR = Path(__file__).with_name("realman_paper_clock_source_anchor_d2_s5r.json")
PDF_URL = ("https://proceedings.neurips.cc/paper_files/paper/2024/file/"
           "bf8f6f5b017dc60d0c4e28a7a9a4ee7b-Paper-Datasets_and_Benchmarks_Track.pdf")
PASS = "REALMAN_D2_S5R_PUBLISHED_SHARED_CLOCK_DESIGN_COHORT_TIMEBASE_UNRESOLVED"
BLOCKED = "REALMAN_D2_S5R_PUBLISHER_SOURCE_OR_DESIGN_NOT_ADMITTED"
MAX_PDF = 16 * 1024 * 1024
MAX_TEXT = 128 * 1024
CLAIMS = (
    "PAPER_REPORTS_CLOCK_SYNCHRONIZED_4X8_AUDIO_FRONTEND",
    "PAPER_REPORTS_FISHEYE_CAMERA_AUDIO_SYNC",
    "PAPER_REPORTS_100MS_SOURCE_ANNOTATION_INTERVAL",
)
UNKNOWN = (
    "exact_Gym_s3r_channel_sample_zero",
    "measured_interchannel_capture_skew_and_drift",
    "measured_microphone_polarity_and_frequency_response",
    "original_video_to_audio_numeric_timestamp_offset",
    "exact_original_Gym_stem_to_CSV_row_and_clock_join",
)
FORBIDDEN = (
    "original_realman_audio_used", "original_original_csv_rows_downloaded",
    "original_gym_sample_zero_verified", "original_gym_clock_drift_verified",
    "original_gym_mic_polarity_verified", "camera_sample_numeric_epoch_verified",
    "gym_csv_exact_timestamp_join_verified", "bf_doa_aec_ns_gains_measured",
    "shipping_authority", "commercial_authority",
)

class Reject(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code

def require(value, code="S5R_PROTOCOL_INVALID"):
    if not value:
        raise Reject(code)

def digest(blob):
    return hashlib.sha256(blob).hexdigest()

def strict_json(path, limit=32768):
    require(path.is_file() and 0 < path.stat().st_size <= limit,
            "S5R_JSON_FILE_MISSING_OR_OVERSIZE")
    def pairs_unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "S5R_DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    try:
        return json.loads(path.read_text("utf-8"),
                          object_pairs_hook=pairs_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              Reject("S5R_JSON_NONFINITE")))
    except (UnicodeError, OSError, ValueError):
        raise Reject("S5R_JSON_INVALID") from None

def contract():
    a = strict_json(ANCHOR)
    fixed = {
        "schema_version": 1,
        "experiment_id": "FE03-A2-D2-S5R-PINNED-PYPDF-PUBLISHER-CLOCK-DESIGN",
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/720",
        "prerequisite_closed_issue": 718,
        "prerequisite_protected_main": "d3f89e54beed483fcc0f8ce59e74b28533ed19b5",
        "prerequisite_source_run": 38110668124,
        "prerequisite_verify_run": 38110668384,
        "prerequisite_release_run": 38112340555,
        "prerequisite_artifact": 11691277965,
        "prerequisite_artifact_zip_sha256": "d4071e579fc3d45d8f47df3892c053a78a6745baad73979b0f1dc54e2db37be1",
        "original_failed_issue": 716,
        "original_failed_draft_pr": 717,
        "original_failed_decision": "S5_PREINSTALLED_PDF_TEXT_TOOL_MISSING",
        "original_failed_source_run": 38106174694,
        "original_failed_artifact": 11690216460,
        "original_failed_artifact_zip_sha256": "96644eb6cb4c9211f328a159fd7950138e91718c7e4e1a0ba08b36707b5d7c2b",
        "expected_claims": list(CLAIMS),
        "unresolved_gym_clock_authorities": list(UNKNOWN),
        "positive_decision": PASS,
        "negative_decision": BLOCKED,
        "publisher_pdf_binary_sha_preregistered": False,
        "hypothesis_informed_not_blinded": True,
        "original_audio_download_authorized": False,
        "original_csv_download_authorized": False,
        "acoustic_quality_scoring_authorized": False,
        "shipping_authority": False,
        "commercial_authority": False,
    }
    require(set(a) == set(fixed) | {"paper", "parser"} and
            all(a.get(k) == v for k, v in fixed.items()),
            "S5R_FROZEN_PROTOCOL_DRIFT")
    paper = {
        "official_url": PDF_URL,
        "doi": "10.52202/079017-3363",
        "expected_pdf_pages": 23,
        "title_pdf_page_1_based": 1,
        "recording_system_pdf_page_1_based": 4,
        "source_annotation_pdf_page_1_based": 7,
        "max_bytes": MAX_PDF,
        "transfer_timeout_seconds": 90,
        "max_page_text_bytes": MAX_TEXT,
        "two_independent_downloads_required": True,
        "same_runner_only": True,
        "source_pdf_redistribution_authorized": False,
    }
    parser = {
        "official_git_url": t0.UPSTREAM,
        "tag": t0.TAG,
        "commit": t0.COMMIT,
        "tree": t0.TREE,
        "annotated_tag_object_sha": "6e3ae92515aefb7add4dae40fc840ad77274ba57",
        "synthetic_preflight_required_before_original_pdf": True,
        "parser_binary_install_authorized": False,
        "different_parser_fallback_authorized": False,
    }
    require(a.get("paper") == paper and a.get("parser") == parser,
            "S5R_SOURCE_OR_PARSER_POLICY_DRIFT")
    t0.anchor()  # Read-only code/tooling validation; T0 never downloads this paper.
    return a

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, new_url):
        raise Reject("S5R_PUBLISHER_REDIRECT_FORBIDDEN")

def safe_publisher():
    p = urlsplit(PDF_URL)
    require(p.scheme == "https" and p.hostname == "proceedings.neurips.cc"
            and p.port in (None, 443) and p.username is None
            and p.password is None and not p.query and not p.fragment
            and p.path.endswith("-Paper-Datasets_and_Benchmarks_Track.pdf"),
            "S5R_OFFICIAL_PUBLISHER_URL_CHANGED")
    return PDF_URL

def fetch_paper(target):
    url = safe_publisher()
    require(not target.exists(), "S5R_PDF_READBACK_PATH_REUSED")
    req = Request(url, headers={
        "Accept": "application/pdf",
        "Accept-Encoding": "identity",
        "User-Agent": "audio-pipeline-fe03-d2-s5r-pinned-source-audit/1",
    })
    started = time.monotonic()
    try:
        with build_opener(NoRedirect()).open(req, timeout=15) as response:
            require(response.geturl() == url, "S5R_PUBLISHER_ORIGIN_CHANGED")
            ctype = response.headers.get("Content-Type", "").split(";")[0].lower().strip()
            require(ctype in ("application/pdf", "application/octet-stream"),
                    "S5R_PDF_MIME_REJECTED")
            require(response.headers.get("Content-Encoding", "identity").lower()
                    in ("", "identity"), "S5R_PDF_TRANSFER_ENCODING_REJECTED")
            n = response.headers.get("Content-Length")
            require(n is None or (n.isdecimal() and 0 < int(n) <= MAX_PDF),
                    "S5R_PDF_SIZE_HEADER_REJECTED")
            h = hashlib.sha256()
            count = 0
            with target.open("xb") as output:
                while True:
                    require(time.monotonic() - started < 90, "S5R_PDF_TIMEOUT")
                    data = response.read(min(65536, MAX_PDF + 1 - count))
                    if not data:
                        break
                    count += len(data)
                    require(count <= MAX_PDF, "S5R_PDF_OVER_BUDGET")
                    h.update(data)
                    output.write(data)
            require(100000 <= count <= MAX_PDF and
                    (n is None or count == int(n)),
                    "S5R_PDF_TRUNCATED_OR_WRONG_SIZE")
            with target.open("rb") as data:
                require(data.read(8).startswith(b"%PDF-"),
                        "S5R_PDF_HEADER_REJECTED")
                data.seek(max(0, count - 8192))
                require(b"%%EOF" in data.read(), "S5R_PDF_EOF_REJECTED")
            return {"bytes": count, "sha256": h.hexdigest()}
    except Reject:
        raise
    except (HTTPError, URLError, TimeoutError, OSError):
        raise Reject("S5R_OFFICIAL_PDF_UNAVAILABLE") from None

def normalized(raw):
    require(isinstance(raw, str), "S5R_PDF_TEXT_NOT_UNICODE")
    require(100 < len(raw.encode("utf-8")) <= MAX_TEXT,
            "S5R_PDF_TEXT_MISSING_OR_OVER_BUDGET")
    return re.sub(r"\s+", " ", raw).strip()

def claims_on_pages(p1, p4, p7):
    title = (
        re.search(r"RealMAN:\s*A\s+Real-Recorded\s+and\s+Annotated", p1, re.I)
        and re.search(r"Microphone\s+Array\s+Dataset\s+for\s+Dynamic\s+Speech", p1, re.I)
        and re.search(r"Enhancement\s+and\s+Localization", p1, re.I)
    )
    found = (
        bool(re.search(r"\b32[\s-]*channel\s+microphone\s+array\b", p4, re.I))
        and bool(re.search(r"\b48\s*kHz\b", p4, re.I))
        and bool(re.search(r"\b4\s+clock[\s-]*synchronized\s+8[\s-]*channel\b", p4, re.I))
        and bool(re.search(r"\bRME\s+OctoMic\s+II\b", p4, re.I))
        and bool(re.search(r"\bRME\s+Digiface\s+USB\b", p4, re.I)),
        bool(re.search(r"\bfisheye\s+camera\b", p4, re.I))
        and bool(re.search(r"\bcamera\s+records.{0,175}\bsynchronized\s+with\s+the\s+microphone\s+recording\b", p4, re.I)),
        bool(re.search(r"temporal\s+resolution\s+of\s+source\s+location\s+annotation\s+is\s+set\s+to\s+100\s*ms\b", p7, re.I)),
    )
    require(bool(title), "S5R_PUBLISHER_TITLE_MISMATCH")
    require(all(found), "S5R_FROZEN_PUBLISHED_AUTHOR_CLAIM_MISSING")
    proof = {
        "scope": "published_authors_system_design_only_not_measured_gym_clock",
        "pdf_pages": 23,
        "pdf_page_text_sha256": {
            "1": digest(p1.encode("utf-8")),
            "4": digest(p4.encode("utf-8")),
            "7": digest(p7.encode("utf-8")),
        },
        "author_claims": [
            {"id": label, "pdf_page": (4 if i < 2 else 7),
             "published_author_assertion": True,
             "record_specific_measurement": False}
            for i, label in enumerate(CLAIMS)
        ],
        "gym_record_specific_unknowns": {name: "UNRESOLVED" for name in UNKNOWN},
        "publisher_pdf_binary_sha_preregistered": False,
        "original_d1_csv_admission_blocked": True,
        "original_s4_clock_result_preserved": True,
        **{field: False for field in FORBIDDEN},
    }
    validate_proof(proof)
    return proof

def validate_proof(p):
    required = {
        "scope", "pdf_pages", "pdf_page_text_sha256", "author_claims",
        "gym_record_specific_unknowns", "publisher_pdf_binary_sha_preregistered",
        "original_d1_csv_admission_blocked", "original_s4_clock_result_preserved",
        *FORBIDDEN,
    }
    require(isinstance(p, dict) and set(p) == required
            and p["scope"] == "published_authors_system_design_only_not_measured_gym_clock"
            and p["pdf_pages"] == 23
            and p["publisher_pdf_binary_sha_preregistered"] is False
            and p["original_d1_csv_admission_blocked"] is True
            and p["original_s4_clock_result_preserved"] is True
            and all(p.get(k) is False for k in FORBIDDEN),
            "S5R_RECORDING_OR_SHIPPING_CLAIM_FORGED")
    hashes = p["pdf_page_text_sha256"]
    require(isinstance(hashes, dict) and set(hashes) == {"1", "4", "7"}
            and all(isinstance(v, str) and re.fullmatch("[a-f0-9]{64}", v)
                    for v in hashes.values()), "S5R_TEXT_HASH_INVALID")
    actual = p["author_claims"]
    require(isinstance(actual, list) and len(actual) == 3
            and [v.get("id") for v in actual if isinstance(v, dict)] == list(CLAIMS)
            and all(set(v) == {"id", "pdf_page", "published_author_assertion",
                               "record_specific_measurement"}
                    and v["pdf_page"] == (4 if i < 2 else 7)
                    and v["published_author_assertion"] is True
                    and v["record_specific_measurement"] is False
                    for i, v in enumerate(actual)), "S5R_AUTHOR_CLAIM_SCHEMA_FORGED")
    require(p["gym_record_specific_unknowns"] ==
            {name: "UNRESOLVED" for name in UNKNOWN},
            "S5R_GYM_TIMEBASE_FALSELY_PROMOTED")

def child_parse(src, paper):
    """New process, direct import from verified official commit; no system pypdf."""
    require(paper.is_file() and 100000 <= paper.stat().st_size <= MAX_PDF,
            "S5R_PAPER_FOR_PARSER_INVALID")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(src))
    import pypdf
    from pypdf import PdfReader
    require(str(pypdf.__version__) == t0.TAG and
            Path(pypdf.__file__).resolve().is_relative_to(
                (src/"pypdf").resolve()), "S5R_PARSER_IMPORT_UNPINNED")
    with paper.open("rb") as source:
        reader = PdfReader(source, strict=True)
        require(len(reader.pages) == 23, "S5R_PAPER_PAGE_COUNT_CHANGED")
        pages = [normalized(reader.pages[n].extract_text()) for n in (0, 3, 6)]
    proof = claims_on_pages(*pages)
    print(json.dumps(proof, sort_keys=True, separators=(",", ":")))
    return 0

def separate_paper_parse(src, paper):
    args = [sys.executable, str(Path(__file__).resolve()), "paper-child",
            "--source", str(src), "--paper", str(paper)]
    try:
        proc = subprocess.run(args, cwd=ROOT, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                              timeout=35, check=False)
        require(proc.returncode == 0 and len(proc.stdout) <= 16384,
                "S5R_PINNED_PYPDF_PAPER_PARSE_FAILED")
        proof = json.loads(proc.stdout.decode("utf-8"),
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               Reject("S5R_CHILD_NONFINITE")))
        validate_proof(proof)
        return proof
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        raise Reject("S5R_CHILD_PAPER_PROOF_INVALID") from None

def identity():
    return {
        "schema_version": 1,
        "experiment_id": "FE03-A2-D2-S5R-PINNED-PYPDF-PUBLISHER-CLOCK-DESIGN",
        "source_commit": t0.checkout_sha(),
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/720",
        "contract_sha256": digest(ANCHOR.read_bytes()),
        "script_sha256": digest(Path(__file__).read_bytes()),
        "t0_script_sha256": digest(Path(t0.__file__).read_bytes()),
        "official_publisher_url": PDF_URL,
        "doi": "10.52202/079017-3363",
        "prereq_t0_synthetic_only_qualified": True,
        "hypothesis_informed_not_blind": True,
        "publisher_pdf_binary_sha_preregistered": False,
        **{field: False for field in FORBIDDEN},
    }

def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                              allow_nan=False, ensure_ascii=False)+"\n", "utf-8")
    tmp.replace(path)

def collect(work, receipt):
    report = identity()
    report["captured_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        contract()
        require(not work.exists(), "S5R_WORKSPACE_REUSED")
        work.mkdir(parents=True)
        require(sys.version_info >= (3, 11), "S5R_PYTHON_NOT_QUALIFIED")
        git, _ = t0.program("git")
        src = t0.native_source(work, git)
        report["source"] = t0.source_identity(src, git)
        # Strict synthetic T0 on THIS runner precedes any original paper network.
        report["synthetic_preflight"] = t0.synthetic_child_process(src)
        require(report["synthetic_preflight"]["synthetic_pdf_bytes"] == 623
                and report["synthetic_preflight"]["two_exact_text_readbacks"]
                and report["synthetic_preflight"]["truncated_pdf_rejected"]
                and report["synthetic_preflight"]["altered_text_not_accepted"],
                "S5R_SAME_RUNNER_SYNTHETIC_PREQUALIFICATION_FAILED")
        original = work / "publisher-original.pdf"
        report["publisher_pdf"] = fetch_paper(original)
        report["paper_claims"] = separate_paper_parse(src, original)
        require(report["source"] == t0.source_identity(src, git),
                "S5R_PARSER_SOURCE_CHANGED_DURING_FIRST_READ")
        report["decision"] = PASS
        rc = 0
    except (Reject, t0.Reject, OSError, subprocess.SubprocessError) as exc:
        for field in ("source", "synthetic_preflight", "publisher_pdf", "paper_claims"):
            report.pop(field, None)
        report["decision"] = BLOCKED
        report["failure_code"] = getattr(exc, "code", "S5R_SOURCE_OR_EXECUTION_FAILURE")
        rc = 1
    save(receipt, report)
    print("decision="+report["decision"]+" failure="+report.get("failure_code", "NONE"),
          flush=True)
    return rc

def verify(work, receipt):
    got = strict_json(receipt)
    expected = identity()
    require(isinstance(got, dict)
            and all(got.get(k) == v for k, v in expected.items())
            and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                                  got.get("captured_at_utc", ""))),
            "S5R_RECEIPT_IDENTITY_OR_TIME_DRIFT")
    if got.get("decision") != PASS:
        require(got.get("decision") == BLOCKED
                and re.fullmatch(r"(S5R|S5T0)_[A-Z0-9_]+",
                                 got.get("failure_code", ""))
                and set(got) == set(expected) | {
                    "captured_at_utc", "decision", "failure_code"},
                "S5R_FAILED_RECEIPT_TAMPER")
        print("S5R_PUBLISHER_READBACK="+BLOCKED)
        return
    require(set(got) == set(expected) | {
        "captured_at_utc", "source", "synthetic_preflight",
        "publisher_pdf", "paper_claims", "decision"},
        "S5R_RECEIPT_EXTRA_OR_MISSING_FIELD")
    contract()
    git, _ = t0.program("git")
    src = work / "pypdf-official"
    require(got["source"] == t0.source_identity(src, git),
            "S5R_VERIFIER_PARSER_SOURCE_DRIFT")
    require(t0.synthetic_child_process(src) == got["synthetic_preflight"],
            "S5R_INDEPENDENT_SYNTHETIC_READBACK_FAILED")
    validate_proof(got["paper_claims"])
    second = work / "publisher-independent-readback.pdf"
    new_pdf = fetch_paper(second)
    new_proof = separate_paper_parse(src, second)
    require(new_pdf == got["publisher_pdf"]
            and new_proof == got["paper_claims"],
            "S5R_PUBLISHER_BYTES_OR_PUBLISHED_CLAIMS_DRIFT")
    require(t0.source_identity(src, git) == got["source"],
            "S5R_PARSER_SOURCE_CHANGED_DURING_READBACK")
    print("S5R_PUBLISHER_PDF_DOUBLE_SHA_AND_CLAIMS_READBACK="+PASS)

def expect_fail(fn):
    try:
        fn()
    except Reject:
        return
    raise AssertionError("S5R offline mutation unexpectedly admitted")

def self_test():
    c = contract()
    require(c["paper"]["expected_pdf_pages"] == 23)
    p1 = "RealMAN: A Real-Recorded and Annotated Microphone Array Dataset for Dynamic Speech Enhancement and Localization."
    p4 = ("3.1 Recording system. The 32-channel microphone array contains microphones. "
          "The sampling rate of microphone recording is 48 kHz. "
          "The sampled audio is digitized by 4 clock-synchronized 8-channel "
          "microphone pre-amplifiers (RME OctoMic II) through an interface "
          "(RME Digiface USB). A 360-degree fisheye camera sits above the array. "
          "The camera records in real time synchronized with the microphone recording.")
    p7 = ("According to the fisheye camera, the temporal resolution of source "
          "location annotation is set to 100 ms.")
    proof = claims_on_pages(p1, p4, p7)
    validate_proof(proof)
    for changed in (
        p4.replace("4 clock-synchronized", "4 independent"),
        p4.replace("8-channel", "6-channel"),
        p4.replace("RME OctoMic II", "another device"),
        p4.replace("RME Digiface USB", "another interface"),
        p4.replace("48 kHz", "44 kHz"),
        p4.replace("synchronized with the microphone recording",
                   "unsynchronized with the microphone recording"),
    ):
        expect_fail(lambda v=changed: claims_on_pages(p1, v, p7))
    expect_fail(lambda: claims_on_pages(p1, p4, p7.replace("100 ms", "200 ms")))
    expect_fail(lambda: claims_on_pages(p1.replace("RealMAN", "Changed"), p4, p7))
    for field in FORBIDDEN:
        expect_fail(lambda f=field: validate_proof(dict(proof, **{f: True})))
    expect_fail(lambda: validate_proof(dict(proof, gym_record_specific_unknowns={
        **proof["gym_record_specific_unknowns"],
        UNKNOWN[0]: "VERIFIED"})))
    expect_fail(lambda: validate_proof(dict(proof, author_claims=[])))
    with tempfile.TemporaryDirectory(prefix="s5r-negative-") as d:
        p = Path(d)/"dup.json"
        p.write_text('{"x":1,"x":2}', encoding="utf-8")
        expect_fail(lambda: strict_json(p))
    require(safe_publisher() == PDF_URL)
    print("REALMAN_D2_S5R_OFFLINE_FROZEN_PDF_AND_FALSE_CLOCK_NEGATIVES_PASS; no network")

def main():
    args = argparse.ArgumentParser()
    args.add_argument("action", choices=("self-test", "collect", "verify", "paper-child"))
    args.add_argument("--workspace")
    args.add_argument("--receipt")
    args.add_argument("--source")
    args.add_argument("--paper")
    a = args.parse_args()
    if a.action == "self-test":
        self_test()
        return 0
    if a.action == "paper-child":
        require(a.source and a.paper, "S5R_CHILD_ARGS_MISSING")
        return child_parse(Path(a.source).resolve(), Path(a.paper).resolve())
    require(a.workspace and a.receipt, "S5R_CLI_ARGS_MISSING")
    work, receipt = Path(a.workspace).resolve(), Path(a.receipt).resolve()
    if a.action == "collect":
        return collect(work, receipt)
    verify(work, receipt)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
