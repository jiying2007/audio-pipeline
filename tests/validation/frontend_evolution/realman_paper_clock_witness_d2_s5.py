#!/usr/bin/env python3
"""FE03 A2 D2-S5: official NeurIPS paper system-clock *design* audit only.

The hardware authors' description is not direct per-utterance Gym ADC/sample-zero
evidence. No raw audio, CSV rows, GCC-PHAT, spatial scores or SDK changes.
Preregistration: https://github.com/jiying2007/audio-pipeline/issues/716
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import realman_source_metadata_d0 as d0

ROOT = Path(__file__).resolve().parents[3]
FROZEN = Path(__file__).with_name("realman_paper_clock_source_anchor_d2_s5.json")
PASS = "REALMAN_D2_S5_PUBLISHED_SHARED_CLOCK_DESIGN_COHORT_TIMEBASE_UNRESOLVED"
BLOCKED = "REALMAN_D2_S5_PAPER_SOURCE_OR_CLAIMS_NOT_ADMITTED"
PDF_URL = ("https://proceedings.neurips.cc/paper_files/paper/2024/file/"
           "bf8f6f5b017dc60d0c4e28a7a9a4ee7b-Paper-Datasets_and_Benchmarks_Track.pdf")
MAX_PDF = 16 * 1024 * 1024
MAX_EXTRACT = 128 * 1024
DESIGN = (
    "four_clock_synchronized_eight_channel_preamps_author_statement",
    "fisheye_camera_audio_synchronized_recording_author_statement",
    "camera_source_location_annotation_interval_100ms_author_statement",
)
UNKNOWN = (
    "exact_Gym_s3r_channel_sample_zero",
    "measured_interchannel_capture_skew_and_drift",
    "measured_microphone_polarity_and_frequency_response",
    "original_video_to_audio_numeric_timestamp_offset",
    "exact_original_Gym_stem_to_CSV_row_and_clock_join",
)


class Reject(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def require(test, code="S5_METADATA_INVALID"):
    if not test:
        raise Reject(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def source_sha():
    out = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                  cwd=ROOT, text=True, timeout=8).strip()
    require(bool(re.fullmatch(r"[0-9a-f]{40}", out))
            and os.environ.get("GITHUB_SHA") == out,
            "S5_SOURCE_CHECKOUT_NOT_AUTHORITATIVE")
    return out


def json_load(path, size=16384):
    require(path.is_file() and 0 < path.stat().st_size <= size,
            "S5_JSON_INPUT_MISSING")
    def distinct(pairs):
        o = {}
        for k, v in pairs:
            require(k not in o, "S5_DUPLICATE_JSON_KEY")
            o[k] = v
        return o
    def not_finite(s):
        raise Reject("S5_NONFINITE_JSON_REJECTED")
    try:
        return json.loads(path.read_text(encoding="utf-8"),
                          object_pairs_hook=distinct, parse_constant=not_finite)
    except (ValueError, UnicodeError, OSError):
        raise Reject("S5_JSON_INPUT_INVALID") from None


def authority():
    r = json_load(FROZEN)
    require(isinstance(r, dict) and
            r.get("preregistration") ==
            "https://github.com/jiying2007/audio-pipeline/issues/716"
            and r.get("experiment_id") ==
            "FE03-A2-D2-S5-OFFICIAL-REALMAN-PAPER-SYSTEM-CLOCK"
            and r.get("prerequisite_closed_issue") == 713
            and r.get("prerequisite_protected_main") ==
            "373008e89f2ebaabc298d2c9613420b1d4811c78"
            and r.get("prerequisite_verify_run") == 38104075774
            and r.get("prerequisite_release_run") == 38105765036
            and r.get("prerequisite_source_vetting_run") == 38104075673
            and r.get("prerequisite_metadata_artifact") == 11688862857
            and r.get("prerequisite_metadata_artifact_zip_sha256") ==
            "cf0b7993c8a3b6cf795a5809d3eb4ff44bbef984c1004e54ddc95a5ef9776a3d"
            and r.get("prior_s4_scoped_decision") ==
            "REALMAN_D2_S4_CAPTURE_TIMEBASE_UNRESOLVED"
            and r.get("original_archive_sha256") ==
            "8175dad412a752a34bdf2722f7e9b5ee671b62e67dfe5179f7a769d63912b2ea"
            and r.get("original_frozen_selection_sha256") ==
            "7b6458adc4d335c6c1897f98e51501f897585623359ef147494d7635d4d9be37"
            and r.get("original_mics") == [1,3,5,7]
            and r.get("expected_decision") == PASS
            and r.get("failed_decision") == BLOCKED
            and r.get("expected_published_design_findings") == list(DESIGN)
            and r.get("unproven_record_specific_authorities") == list(UNKNOWN),
            "S5_FROZEN_PROTOCOL_DRIFT")
    p = r.get("paper")
    require(isinstance(p, dict) and
            p.get("url") == PDF_URL
            and p.get("doi") == "10.52202/079017-3363"
            and p.get("file_sha256_preregistered") is False
            and p.get("expected_page_count") == 23
            and p.get("recording_system_pdf_page_1_based") == 4
            and p.get("annotation_pdf_page_1_based") == 7
            and p.get("max_bytes") == MAX_PDF
            and p.get("transfer_timeout_sec") == 90
            and p.get("pdf_text_extractor") ==
            "preinstalled pdftotext only, no apt/pip/sudo",
            "S5_PUBLISHER_PDF_SOURCE_DRIFT")
    for key in ("source_audio_download_authorized",
                "csv_original_rows_download_authorized",
                "sampled_audio_doa_or_bf_evaluation_authorized",
                "original_s4_decision_mutation_authorized",
                "shipping_authority", "commercial_authority",
                "publication_excerpt_redistribution_authorized"):
        require(r.get(key) is False, "S5_FORBIDDEN_SCOPE_ENABLED")
    assert d0.authoritative_contract()["physical_slot_map"] == [1,3,5,7]
    return r


def publisher_url():
    p = urlsplit(PDF_URL)
    require(p.scheme == "https" and p.hostname == "proceedings.neurips.cc"
            and p.port in (None, 443) and p.username is None and
            p.password is None and not p.query and not p.fragment and
            p.path.endswith("-Paper-Datasets_and_Benchmarks_Track.pdf"),
            "S5_EXTERNAL_PDF_URL_UNTRUSTED")
    return PDF_URL


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Reject("S5_PDF_CROSS_HOST_OR_REDIRECT_NOT_ADMITTED")


def read_paper(path):
    url = publisher_url()
    request = Request(url, headers={
        "Accept": "application/pdf",
        "Accept-Encoding": "identity",
        "User-Agent": "audio-pipeline-d2-s5-paper-source-audit/1",
    })
    try:
        with build_opener(NoRedirect()).open(request, timeout=20) as response:
            require(response.geturl() == url, "S5_PDF_REMOTE_URL_DRIFT")
            content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            require(content_type in ("application/pdf", "application/octet-stream"),
                    "S5_PDF_CONTENT_TYPE_MISMATCH")
            require(response.headers.get("Content-Encoding", "identity").lower()
                    in ("", "identity"), "S5_PDF_ENCODING_UNSUPPORTED")
            n = response.headers.get("Content-Length")
            require(n is None or (n.isdecimal() and int(n) <= MAX_PDF),
                    "S5_PDF_BYTES_LIMIT")
            start = time.monotonic()
            digest = hashlib.sha256()
            count = 0
            with path.open("xb") as output:
                while True:
                    require(time.monotonic()-start < 90, "S5_PDF_TRANSFER_TIMEOUT")
                    data = response.read(min(65536, MAX_PDF+1-count))
                    if not data:
                        break
                    count += len(data)
                    require(count <= MAX_PDF, "S5_PDF_BYTES_LIMIT")
                    output.write(data)
                    digest.update(data)
            require(100000 <= count <= MAX_PDF and
                    (n is None or count == int(n)), "S5_PDF_TRUNCATED")
            with path.open("rb") as f:
                require(f.read(8).startswith(b"%PDF-"), "S5_INVALID_PDF_HEADER")
                f.seek(max(0,count-8192))
                require(b"%%EOF" in f.read(), "S5_INVALID_PDF_TRAILER")
            return {"bytes":count,"sha256":digest.hexdigest()}
    except Reject:
        raise
    except (HTTPError, URLError, TimeoutError, OSError):
        raise Reject("S5_OFFICIAL_PAPER_UNAVAILABLE") from None


def pdftotext_tool():
    exe = shutil.which("pdftotext")
    require(exe is not None, "S5_PREINSTALLED_PDF_TEXT_TOOL_MISSING")
    exe = Path(exe).resolve()
    require(exe.is_file() and exe.stat().st_size < 64*1024*1024 and
            str(exe).startswith(("/usr/bin/", "/usr/local/bin/")),
            "S5_PREINSTALLED_PDF_TEXT_TOOL_NOT_TRUSTED")
    result = subprocess.run([str(exe), "-v"], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=5)
    require(result.returncode == 0 and
            b"pdftotext" in result.stdout+result.stderr,
            "S5_PDF_TOOL_VERSION_INVALID")
    return str(exe), {
        "tool_version":(result.stdout+result.stderr).decode("utf-8", errors="replace").splitlines()[0][:120],
        "tool_binary_sha256":sha(exe.read_bytes()),
    }


def pdf_page_text(tool, file_path, n):
    cmd = [tool, "-f", str(n), "-l", str(n),
           "-enc", "UTF-8", str(file_path), "-"]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                stdin=subprocess.DEVNULL, timeout=25)
    except (OSError, subprocess.SubprocessError):
        raise Reject("S5_PDF_TEXT_EXTRACTION_FAILED") from None
    require(result.returncode == 0 and 1000 < len(result.stdout) < MAX_EXTRACT,
            "S5_PDF_TEXT_EXTRACTION_FAILED")
    try:
        t = result.stdout.decode("utf-8", errors="strict")
    except UnicodeError:
        raise Reject("S5_PDF_TEXT_INVALID_UTF8") from None
    return re.sub(r"\s+", " ", re.sub(r"-\s*\n\s*", "", t)).strip()


def design_proof(page4, page7):
    # Test only the three frozen, published author statements. No text
    # excerpts or full PDF are serialized into public output.
    tests = {
        DESIGN[0]: (
            bool(re.search(r"32[\s-]*channel microphone array",page4,re.I)) and
            bool(re.search(r"48\s*kHz",page4,re.I)) and
            bool(re.search(r"4\s+clock[\s-]*synchronized\s+8[\s-]*channel",page4,re.I)) and
            bool(re.search(r"RME\s+OctoMic\s+II",page4,re.I)) and
            bool(re.search(r"RME\s+Digiface\s+USB",page4,re.I))
        ),
        DESIGN[1]: (
            bool(re.search(r"fisheye camera",page4,re.I)) and
            bool(re.search(r"camera records.{0,160}\\bsynchronized with the microphone recording",
                           page4,re.I))
        ),
        DESIGN[2]: (
            bool(re.search(r"temporal resolution of source location annotation is set to 100 ms",
                           page7,re.I))
        )
    }
    require(all(tests.values()), "S5_EXPECTED_PUBLISHED_DESIGN_CLAIM_MISSING")
    return {
        "scope":"official_author_statement_only_not_independent_capture_measurement",
        "observed_author_claims":[{
            "claim_id":name,
            "page_pdf_1_based":4 if i<2 else 7,
            "publication_support":True,
            "recording_specific_measurement":False,
        } for i,name in enumerate(DESIGN)],
        "record_specific_clock_authorities":{
            k:{"status":"unresolved",
               "reason":"PAPER_SYSTEM_LEVEL_STATEMENT_HAS_NO_GYM_CLIP_NUMERIC_WITNESS"}
            for k in UNKNOWN
        },
        "publisher_pdf_binary_sha_preregistered":False,
        "source_role":"public_recording_system_description_only",
        "original_s4_unresolved_preserved":True,
        "original_d1_csv_admission_blocked":True,
        "original_pcm_redownloaded":False,
        "original_csv_rows_downloaded":False,
        "new_audio_acoustic_scores_measured":False,
        "synchronized_Gym_four_pcm_sample_zero_verified":False,
        "mic_polarity_calibrated":False,
        "camera_audio_numeric_timestamp_proven":False,
        "shipping_authority":False,
        "commercial_authority":False
    }


def validate_nonpromotion(x):
    allowed = {
        "scope", "observed_author_claims", "record_specific_clock_authorities",
        "publisher_pdf_binary_sha_preregistered", "source_role",
        "original_s4_unresolved_preserved", "original_d1_csv_admission_blocked",
        "original_pcm_redownloaded", "original_csv_rows_downloaded",
        "new_audio_acoustic_scores_measured",
        "synchronized_Gym_four_pcm_sample_zero_verified",
        "mic_polarity_calibrated", "camera_audio_numeric_timestamp_proven",
        "shipping_authority", "commercial_authority",
    }
    require(isinstance(x,dict) and set(x)==allowed and
            x.get("scope") ==
            "official_author_statement_only_not_independent_capture_measurement"
            and x.get("publisher_pdf_binary_sha_preregistered") is False
            and x.get("original_s4_unresolved_preserved") is True
            and x.get("original_d1_csv_admission_blocked") is True
            and [z.get("claim_id") for z in
                 x.get("observed_author_claims",[]) if isinstance(z,dict)] == list(DESIGN)
            and all(z.get("publication_support") is True and
                    z.get("recording_specific_measurement") is False
                    for z in x["observed_author_claims"])
            and isinstance(x.get("record_specific_clock_authorities"),dict)
            and set(x["record_specific_clock_authorities"]) == set(UNKNOWN)
            and all(z.get("status") == "unresolved"
                    for z in x["record_specific_clock_authorities"].values())
            and all(x.get(k) is False for k in (
                "original_pcm_redownloaded","original_csv_rows_downloaded",
                "new_audio_acoustic_scores_measured",
                "synchronized_Gym_four_pcm_sample_zero_verified",
                "mic_polarity_calibrated","camera_audio_numeric_timestamp_proven",
                "shipping_authority","commercial_authority")),
            "S5_RECORD_LEVEL_SYNC_OR_PRODUCT_AUTHORITY_FORGED")


def observe(work):
    tool,tool_meta=pdftotext_tool()
    pdf_path = work / "official-paper.pdf"
    data = read_paper(pdf_path)
    cover=pdf_page_text(tool,pdf_path,1)
    require("RealMAN: A Real-Recorded and Annotated" in cover and
            "Microphone Array Dataset for Dynamic Speech" in cover and
            "Enhancement and Localization" in cover,
            "S5_PUBLISHER_PAPER_TITLE_MISMATCH")
    p4=pdf_page_text(tool,pdf_path,4)
    p7=pdf_page_text(tool,pdf_path,7)
    proof=design_proof(p4,p7)
    validate_nonpromotion(proof)
    return {"publisher_pdf":data,"pdf_text_extractor":tool_meta,
            "design_claims_and_unknowns":proof}


def identity():
    return {
        "schema_version":1,
        "experiment_id":"FE03-A2-D2-S5-OFFICIAL-REALMAN-PAPER-SYSTEM-CLOCK",
        "source_commit":source_sha(),
        "preregistration":"https://github.com/jiying2007/audio-pipeline/issues/716",
        "preregistered_contract_sha256":sha(FROZEN.read_bytes()),
        "script_sha256":sha(Path(__file__).read_bytes()),
        "d0_contract_sha256":sha(d0.CONTRACT.read_bytes()),
        "publisher_pdf_source_url":PDF_URL,
        "doi":"10.52202/079017-3363",
        "research_purpose":"NONCOMMERCIAL_RESEARCH_ONLY",
        "source_role":"disclosed-development-paper-system-design-only",
        "original_d1_csv_admitted":False,
        "sample_zero_verified":False,
        "camera_audio_timebase_verified":False,
        "doa_or_bf_scores_measured":False,
        "shipping_authority":False,
        "commercial_authority":False
    }


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, sort_keys=True, separators=(",",":"),
                               ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    temp.replace(path)


def collect(work,receipt):
    r=identity()
    r["captured_at_utc"]=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        authority()
        require(not work.exists(), "S5_EPHEMERAL_WORKSPACE_ALREADY_USED")
        work.mkdir(parents=True)
        r.update(observe(work))
        r["decision"]=PASS
        status=0
    except (Reject, OSError, subprocess.SubprocessError) as e:
        r["decision"]=BLOCKED
        r["failure_code"]=getattr(e,"code","S5_SOURCE_OR_EXECUTION_FAILED")
        status=1
    save(receipt,r)
    print("decision="+r["decision"]+" failure="+r.get("failure_code","NONE"),flush=True)
    return status


def verify(work,receipt_path):
    r=json_load(receipt_path,cap=32768)
    require(isinstance(r,dict),"S5_RECEIPT_INVALID")
    expected=identity()
    for k,v in expected.items():
        require(r.get(k)==v, "S5_RECEIPT_IDENTITY_CHANGED")
    require(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                              r.get("captured_at_utc",""))),
            "S5_TIMESTAMP_RECEIPT_CHANGED")
    if r.get("decision")==PASS:
        require(set(r)==set(expected)|{
            "captured_at_utc","publisher_pdf","pdf_text_extractor",
            "design_claims_and_unknowns","decision"},
            "S5_RECEIPT_EXTRA_OR_MISSING_FIELDS")
        frozen=authority()
        require(frozen["paper"]["url"]==PDF_URL)
        validate_nonpromotion(r["design_claims_and_unknowns"])
        second=work/"independent-readback"
        require(not second.exists(),"S5_SECOND_READBACK_ALREADY_EXISTS")
        second.mkdir(parents=True)
        rebuilt=observe(second)
        require(all(rebuilt[k]==r[k] for k in (
            "publisher_pdf","pdf_text_extractor","design_claims_and_unknowns")),
            "S5_INDEPENDENT_PUBLISHER_PDF_REHASH_OR_DESIGN_DRIFT")
    else:
        require(r.get("decision")==BLOCKED
                and bool(re.fullmatch(r"S5_[A-Z0-9_]+",r.get("failure_code","")))
                and set(r)==set(expected)|{"captured_at_utc","decision","failure_code"},
                "S5_FAILED_RECEIPT_TAMPER")
    print("S5_PUBLISHER_PAPER_READBACK_CONSISTENT="+r["decision"])


def self_test():
    authority()
    p4=("3.1 Recording system. A 32-channel microphone array samples at 48 kHz. "
        "The sampled audio signals are digitized by 4 clock-synchronized "
        "8-channel pre-amplifiers (RME OctoMic II) through an audio interface "
        "(RME Digiface USB). The fisheye camera records in real time "
        "synchronized with the microphone recording.")
    p7=("The temporal resolution of source location annotation is set to 100 ms.")
    good=design_proof(p4,p7)
    validate_nonpromotion(good)
    for changed in (
        p4.replace("4 clock-synchronized","4 independent"),
        p4.replace("8-channel","6-channel"),
        p4.replace("OctoMic","DifferentDevice"),
        p4.replace("synchronized with the microphone recording",
                   "unsynchronized with the microphone recording"),
    ):
        try:
            design_proof(changed,p7)
        except Reject:
            pass
        else:
            raise AssertionError("S5 false paper source claim admitted")
    try:
        design_proof(p4,p7.replace("100 ms","200 ms"))
    except Reject:
        pass
    else:
        raise AssertionError("S5 altered label cadence admitted")
    for field in ("sample_zero_verified","commercial_authority",
                  "synchronized_Gym_four_pcm_sample_zero_verified",
                  "new_audio_acoustic_scores_measured"):
        forged=dict(good,**{field:True})
        try:
            validate_nonpromotion(forged)
        except Reject:
            pass
        else:
            raise AssertionError("S5 false clip-level synchronization admitted")
    require(PDF_URL.endswith(".pdf") and len(UNKNOWN)==5)
    with tempfile.TemporaryDirectory(prefix="s5-test-") as path:
        file=Path(path)/"frozen.json"
        file.write_text('{"a":1,"a":2}')
        try:
            json_load(file)
        except Reject:
            pass
        else:
            raise AssertionError("S5 duplicate JSON key accepted")
    print("REALMAN_D2_S5_OFFLINE_PAPER_WITNESS_NEGATIVES_PASS; no PDF or audio download")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("self-test","collect","verify"))
    p.add_argument("--workspace")
    p.add_argument("--receipt")
    a=p.parse_args()
    if a.action=="self-test":
        self_test()
        return 0
    require(bool(a.workspace and a.receipt),"S5_ARGS_MISSING")
    work=Path(a.workspace).resolve()
    receipt=Path(a.receipt).resolve()
    if a.action=="collect":
        return collect(work,receipt)
    verify(work,receipt)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
