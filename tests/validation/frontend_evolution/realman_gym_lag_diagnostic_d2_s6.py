#!/usr/bin/env python3
"""FE03 A2 D2-S6: 36 frozen original Gym GCC-PHAT lag diagnostics, NO clock proof.

Independently preregistered: https://github.com/jiying2007/audio-pipeline/issues/723
No source-selection, acoustic score, clock calibration, shipping or new audio library.
"""
from __future__ import annotations

import argparse
from array import array
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

import realman_single_archive_d2_s1 as s1
import realman_flac_quartets_d2_s2 as s2
import realman_flac_decoder_toolchain_d2_t0 as t0
import realman_pcm_reference_d2_s3r as s3r
from doa_gccphat_a1 import fft as first_party_fft

ROOT = Path(__file__).resolve().parents[3]
FROZEN = Path(__file__).with_name("realman_gym_lag_diagnostic_d2_s6.json")
PASS = "REALMAN_D2_S6_GYM_SPATIAL_LAG_DIAGNOSTIC_RECORDED_NO_CLOCK_AUTHORITY"
BLOCKED = "REALMAN_D2_S6_SOURCE_OR_DIAGNOSTIC_NOT_ADMITTED"
WIN = 8192
NFFT = 16384
FLOOR = 1e-12
MIN_RMS = 1 / 32768
AMBIGUOUS = 1e-6
ROLES = ("static", "moving")
CHANNELS = (1, 3, 5, 7)
PAIRS = ((1, 3), (1, 5), (1, 7), (3, 5), (3, 7), (5, 7))
FALSE_FIELDS = (
    "original_gym_sample_zero_verified",
    "original_gym_residual_clock_skew_or_drift_measured",
    "original_microphone_gain_phase_polarity_calibrated",
    "original_video_to_audio_timestamp_verified",
    "exact_original_label_timestamp_join_verified",
    "source_label_doa_accuracy_measured",
    "beamformer_aec_ns_improvement_measured",
    "shipping_authority", "commercial_authority",
    "original_audio_redistribution_authorized",
    "original_csv_video_download_authorized",
)
HANN = tuple(0.5-0.5*math.cos(2*math.pi*i/(WIN-1)) for i in range(WIN))

class Reject(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code

def require(value, code="S6_DIAGNOSTIC_CONTRACT_INVALID"):
    if not value:
        raise Reject(code)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def strict_json(path, cap=131072):
    require(path.is_file() and 0 < path.stat().st_size < cap, "S6_JSON_MISSING_OR_TOO_LARGE")
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "S6_DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    try:
        result = json.loads(path.read_text("utf-8"), object_pairs_hook=pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(
                                Reject("S6_NONFINITE_JSON")))
        require(isinstance(result, dict), "S6_JSON_OBJECT_REQUIRED")
        return result
    except (UnicodeError, OSError, ValueError):
        raise Reject("S6_INVALID_JSON") from None

def contract():
    c = strict_json(FROZEN)
    q = c.get("frozen_diagnostics", {})
    z = c.get("budgets", {})
    fixed = {
        "schema_version": 1,
        "experiment_id": "FE03-A2-D2-S6-ORIGINAL-GYM-PAIR-LAG-DIAGNOSTIC",
        "preregistration": "https://github.com/jiying2007/audio-pipeline/issues/723",
        "prereq_ci_merged_main": "5cdf7cac5814b3ae990fec48465b2c7da2e39f03",
        "prereq_exact_main_verify_run": 38143015640,
        "prereq_exact_main_release_run": 38145090533,
        "research_role": "DISCLOSED_DEVELOPMENT_DIAGNOSTIC_ONLY",
        "dataset": "AISHELL/RealMAN",
        "dataset_revision": s1.REV,
        "original_archive": s1.REL,
        "original_archive_bytes": s1.EXPECTED_BYTES,
        "original_archive_sha256": s1.EXPECTED_SHA,
        "source_selection_sha256": s3r.S2_SELECTED_SHA,
        "upstream_s3r_artifact_id": 11687520995,
        "upstream_s3r_artifact_zip_sha256":
            "f21e77672841dba4a0cab16fa29047f8a2e524067d4b5c14bd1e9390f0a34743",
        "upstream_flac_source_commit": t0.COMMIT,
        "upstream_flac_source_tree": s3r.T0_OFFICIAL_SOURCE_TREE,
        "native_reference_flac_version": "flac 1.4.3",
        "original_roles": list(ROLES),
        "physical_mic_ids": list(CHANNELS),
        "pcm_encoding": "signed-s16le-no-resample-or-gain",
        "sample_rate_hz": 48000,
        "positive_decision": PASS,
        "blocked_decision": BLOCKED,
    }
    require(all(c.get(k) == v for k, v in fixed.items()), "S6_FROZEN_SOURCE_DRIFT")
    require(set(c) == set(fixed) | {"frozen_streams", "frozen_diagnostics",
            "budgets", *FALSE_FIELDS}
            and all(c.get(k) is False for k in FALSE_FIELDS),
            "S6_UNAUTHORIZED_SCOPE_PROMOTION")
    require(q == {
        "roles":2, "windows_per_role":3, "pairs_per_window":6,"observations":36,
        "sample_window":WIN,"window_starts":"0,(N-8192)//2,N-8192",
        "hann":"0.5-0.5*cos(2*pi*i/(8192-1))",
        "fft_length":NFFT,"fft":"first-party radix-2 a1.fft, unchanged",
        "gcc_phat":"X_left*conj(X_right)/max(abs(cross),1e-12)",
        "phat_floor":FLOOR,"peak_search_min_lag":-16,"peak_search_max_lag":16,
        "peak_score":"abs(real(ifft(phat)))", "peak_tie":"smallest signed lag",
        "sidelobe_exclusion_lags":2,
        "separation_proxy":"(peak_abs-max_other_abs_outside_two_lags)/max(peak_abs,1e-12)",
        "ambiguous_gap_floor":AMBIGUOUS,
        "rms":"sqrt(mean((raw_signed_s16/32768)^2))",
        "minimum_rms":MIN_RMS,
        "constant_sample_rejection":True, "boundary_is_unknown":True,
        "pairs":[list(x) for x in PAIRS],
        "no_polarity_certification":True,
    }, "S6_FROZEN_ESTIMATOR_DRIFT")
    require(z == {
        "max_archive_bytes":536870912,"max_decoded_pcm_bytes":16777216,
        "source_job_minutes":30,"max_diagnostics_seconds_per_pass":240,
        "max_decode_seconds_per_stream":30,"retention_days":30,
    }, "S6_FROZEN_BUDGET_DRIFT")
    anchor = s3r.load_anchor()
    streams = c.get("frozen_streams")
    require(isinstance(streams, list) and len(streams) == 8,
            "S6_FROZEN_PCM_STREAMS_INVALID")
    require(sum(x.get("samples", 0)*2 for x in streams
                if isinstance(x, dict)) < z["max_decoded_pcm_bytes"],
            "S6_DECODED_PCM_TOTAL_BUDGET_INVALID")
    for record, original in zip(streams, anchor["members"]):
        require(isinstance(record, dict) and set(record) ==
                {"role", "channel", "samples", "md5", "sha256"},
                "S6_PCM_ANCHOR_RECORD_SHAPE")
        require(record["role"] == original["role"] and
                record["channel"] == original["channel"] and
                record["samples"] == original["streaminfo"]["total_samples"] and
                record["md5"] == original["streaminfo"]["streaminfo_pcm_md5_hex"] and
                isinstance(record["sha256"], str) and
                bool(re.fullmatch(r"[0-9a-f]{64}",record["sha256"])),
                "S6_ORIGINAL_PCM_IDENTITY_DRIFT")
    return c, anchor

def windows(samples):
    require(samples in (238895,237071), "S6_SAMPLE_COUNT_DRIFT")
    return (0,(samples-WIN)//2,samples-WIN)

def rms(samples, start):
    require(0<=start and start+WIN<=len(samples), "S6_TRUNCATED_WINDOW")
    window = samples[start:start+WIN]
    power=sum((int(x)/32768)**2 for x in window)/WIN
    level=math.sqrt(power)
    require(math.isfinite(level), "S6_NUMERIC_RMS_NONFINITE")
    return level, min(window)!=max(window)

def spectrum(samples,start):
    require(0<=start and start+WIN<=len(samples),"S6_TRUNCATED_WINDOW")
    signal=[complex(int(samples[start+i])/32768*HANN[i],0.0)
            for i in range(WIN)]
    signal.extend([0j]*(NFFT-WIN))
    return first_party_fft(signal)

def observed_pair(spec_left,spec_right,level_left,level_right,var_left,var_right):
    base={
        "status":"UNDETERMINED_SIGNAL","lag_samples":None,
        "rms_left":round(level_left,10),"rms_right":round(level_right,10),
        "peak_abs":None,"sidelobe_abs":None,"separation_proxy":None,
    }
    if (level_left<=MIN_RMS or level_right<=MIN_RMS or
            not var_left or not var_right):
        return base
    values=[]
    for x,y in zip(spec_left,spec_right):
        v=x*y.conjugate()
        mag=abs(v)
        values.append(v/max(mag,FLOOR))
    corr=first_party_fft(values,inverse=True)
    scores=[abs(corr[lag%NFFT].real) for lag in range(-16,17)]
    if not all(math.isfinite(k) for k in scores):
        return dict(base,status="UNDETERMINED_NUMERIC")
    best=max(range(-16,17),key=lambda lag:scores[lag+16])
    peak=scores[best+16]
    sidelobe=max(scores[lag+16] for lag in range(-16,17)
                 if abs(lag-best)>2)
    gap=max(0.0,(peak-sidelobe)/max(peak,FLOOR))
    base.update({
        "status":("UNDETERMINED_PEAK" if gap<=AMBIGUOUS else
                  "OUT_OF_SEARCH_WINDOW_UNKNOWN" if abs(best)==16 else
                  "OBSERVED_DIAGNOSTIC_ONLY"),
        "lag_samples":(None if gap<=AMBIGUOUS else best),
        "peak_abs":round(peak,10),
        "sidelobe_abs":round(sidelobe,10),
        "separation_proxy":round(gap,10),
    })
    return base

def diagnose(pcm, deadline):
    observations=[]
    for role in ROLES:
        streams={ch:pcm[(role,ch)] for ch in CHANNELS}
        length=len(streams[CHANNELS[0]])
        require(all(len(x)==length for x in streams.values()),
                "S6_ROLE_DECODED_CHANNEL_LENGTHS_DIVERGE")
        for wi,start in enumerate(windows(length)):
            require(time.monotonic()<deadline,"S6_DIAGNOSTIC_CPU_TIME_EXCEEDED")
            specs={}
            statistics={}
            for ch in CHANNELS:
                statistics[ch]=rms(streams[ch],start)
                # Avoid FFT for uninformative channels; no channel/window replaced.
                if statistics[ch][0]>MIN_RMS and statistics[ch][1]:
                    specs[ch]=spectrum(streams[ch],start)
            for left,right in PAIRS:
                lv, lc=statistics[left]
                rv, rc=statistics[right]
                if left not in specs or right not in specs:
                    obs=observed_pair([],[],lv,rv,lc,rc)
                else:
                    obs=observed_pair(specs[left],specs[right],lv,rv,lc,rc)
                observations.append({
                    "role":role,"window":wi,"start_sample":start,
                    "left_mic":left,"right_mic":right,**obs
                })
    validate_observations(observations)
    return observations

def validate_observations(observations):
    require(isinstance(observations,list) and len(observations)==36,
            "S6_NOT_ALL_36_DIAGNOSTICS_RETAINED")
    i=0
    for role in ROLES:
        length=238895 if role=="static" else 237071
        for wi,start in enumerate(windows(length)):
            for l,r in PAIRS:
                v=observations[i]
                require(isinstance(v,dict) and set(v)=={
                    "role","window","start_sample","left_mic","right_mic",
                    "status","lag_samples","rms_left","rms_right",
                    "peak_abs","sidelobe_abs","separation_proxy"
                },"S6_OBSERVATION_SCHEMA_DRIFT")
                require((v["role"],v["window"],v["start_sample"],
                         v["left_mic"],v["right_mic"])==(role,wi,start,l,r),
                        "S6_OBSERVATION_ORDER_OR_ORIGIN_DRIFT")
                require(v["status"] in {
                    "OBSERVED_DIAGNOSTIC_ONLY","OUT_OF_SEARCH_WINDOW_UNKNOWN",
                    "UNDETERMINED_PEAK","UNDETERMINED_SIGNAL",
                    "UNDETERMINED_NUMERIC"
                }, "S6_OBSERVATION_STATUS_FORGED")
                require(all(type(v[k]) in (int,float) and
                            math.isfinite(v[k]) and 0<=v[k]<=1.1
                            for k in ("rms_left","rms_right")),
                        "S6_RMS_NOT_FINITE")
                if v["lag_samples"] is not None:
                    require(type(v["lag_samples"]) is int and
                            -16<=v["lag_samples"]<=16,
                            "S6_DIAGNOSTIC_LAG_OUT_OF_RANGE")
                for k in ("peak_abs","sidelobe_abs","separation_proxy"):
                    if v[k] is not None:
                        require(type(v[k]) in (int,float) and
                                math.isfinite(v[k]) and v[k]>=0,
                                "S6_DIAGNOSTIC_PROXY_NONFINITE")
                require(v["status"] not in {"OBSERVED_DIAGNOSTIC_ONLY",
                                         "OUT_OF_SEARCH_WINDOW_UNKNOWN"} or
                        v["lag_samples"] is not None,
                        "S6_DIAGNOSTIC_WITHOUT_LAG")
                require(v["status"]!="OUT_OF_SEARCH_WINDOW_UNKNOWN" or
                        abs(v["lag_samples"])==16,
                        "S6_BOUNDARY_LAG_FALSELY_CLASSIFIED")
                i+=1

def decode_pcm(native_cli, path, baseline):
    sample_count=baseline["samples"]
    require(path.is_file() and sample_count in (238895,237071),
            "S6_ORIGINAL_DECODE_SOURCE_MISSING")
    try:
        p=subprocess.run(t0.decode_cmd(native_cli,path),
                         stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,timeout=30)
    except (OSError,subprocess.SubprocessError):
        raise Reject("S6_PINNED_FLAC_DECODE_TIMEOUT_OR_MISSING") from None
    require(p.returncode==0 and len(p.stderr)<16384 and
            len(p.stdout)==2*sample_count,
            "S6_DECODE_PCM_SIZE_OR_EXIT_MISMATCH")
    require(hashlib.md5(p.stdout).hexdigest()==baseline["md5"] and
            sha(p.stdout)==baseline["sha256"],
            "S6_DECODED_PCM_FROZEN_S3R_HASH_MISMATCH")
    decoded=array("h")
    decoded.frombytes(p.stdout)
    if sys.byteorder!="little":
        decoded.byteswap()
    require(len(decoded)==sample_count,"S6_DECODED_PCM_SAMPLES_INVALID")
    return decoded

def original_audio(work,anchor,c,native_cli,*,extract):
    archive=work/"Gym.rar"
    extractor, selected, inventory=s2.list_and_select(archive)
    s3r.validate_selection(anchor,selected,inventory)
    pcm={}
    members=[]
    deadline=time.monotonic()+s2.OVERALL_EXTRACT_TIMEOUT
    for row,original,baseline in zip(selected,anchor["members"],c["frozen_streams"]):
        path=work/("%s-ch%d.flac"%(row["role"],row["channel"]))
        if extract:
            size,h=s2.extract_exact(extractor,archive,row["name"],path,
                                    row["size"],deadline)
            require((size,h)==(original["original_flac_bytes"],
                               original["original_flac_sha256"]),
                    "S6_EXTRACTED_SOURCE_FLAC_HASH_MISMATCH")
        size,h=s1.file_hash(path,cap=s2.PER_FILE_LIMIT)
        require((size,h)==(original["original_flac_bytes"],
                           original["original_flac_sha256"]),
                "S6_ORIGINAL_FLAC_REHASH_MISMATCH")
        require(s2.flac_streaminfo(path)==original["streaminfo"],
                "S6_FLAC_STREAMINFO_DRIFT")
        data=decode_pcm(native_cli,path,baseline)
        pcm[(row["role"],row["channel"])]=data
        members.append({"role":row["role"],"channel":row["channel"],
                        "original_flac_sha256":h,"pcm_bytes":len(data)*2,
                        "decoded_pcm_md5":baseline["md5"],
                        "decoded_pcm_sha256":baseline["sha256"]})
    require(len(pcm)==8 and sum(len(a)*2 for a in pcm.values())<16777216,
            "S6_DECODED_PCM_MEMORY_BUDGET")
    return pcm,members,inventory

def identity():
    return {
        "schema_version":1,
        "experiment_id":"FE03-A2-D2-S6-ORIGINAL-GYM-PAIR-LAG-DIAGNOSTIC",
        "preregistration":"https://github.com/jiying2007/audio-pipeline/issues/723",
        "source_commit":s2.source_sha(),
        "frozen_contract_sha256":sha(FROZEN.read_bytes()),
        "s6_script_sha256":sha(Path(__file__).read_bytes()),
        "s3r_script_sha256":sha(Path(s3r.__file__).read_bytes()),
        "s2_anchor_sha256":sha(s3r.ANCHOR_PATH.read_bytes()),
        "source_role":"DISCLOSED_DEVELOPMENT_DIAGNOSTIC_ONLY",
        "original_gym_sample_zero_verified":False,
        "measured_original_clock_skew_drift":False,
        "original_video_audio_timebase_verified":False,
        "original_csv_labels_joined":False,
        "doa_or_bf_acoustic_gain_measured":False,
        "shipping_authority":False,
        "commercial_authority":False,
    }

def save(path, obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(".tmp")
    temp.write_text(json.dumps(obj,sort_keys=True,separators=(",",":"),
                               allow_nan=False)+"\n",encoding="utf-8")
    temp.replace(path)

def collect(work,receipt):
    report=identity()
    report["captured_at_utc"]=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        c,anchor=contract()
        require(not work.exists(),"S6_EPHEMERAL_WORKSPACE_NOT_EMPTY")
        work.mkdir(parents=True)
        require(t0.collect(work/"reference",work/"t0-proof.json")==0,
                "S6_REFERENCE_SYNTHETIC_PREQUALIFICATION_FAILED")
        t0.verify(work/"reference",work/"t0-proof.json")
        tool,meta,proof=s3r.pinned_reference(work)
        require(meta["native_version"]=="flac 1.4.3" and
                proof["synthetic_proof"]["raw_bitwise_match"] is True,
                "S6_REFERENCE_SOURCE_OR_SYNTHETIC_INVALID")
        # The only original audio network transfer, after reference qualification.
        archive=s1.download(work)
        s1.verify_archive(work/"Gym.rar",archive,s1.EXPECTED_BYTES,s1.EXPECTED_SHA)
        pcm,members,inventory=original_audio(work,anchor,c,tool,extract=True)
        observations=diagnose(pcm,time.monotonic()+240)
        report.update({
            "source_archive":archive,"reference_upstream":t0.source_identity(work/"reference"),
            "native_tool":meta,"local_synthetic_sha256":sha((work/"t0-proof.json").read_bytes()),
            "inventory":inventory,"members":members,"observations":observations,
            "observations_retained":36,"research_interpretation":"LAG_NOT_CLOCK_OR_DOA",
            "decision":PASS,
        })
        rc=0
    except Exception as exc:
        report={**identity(),"captured_at_utc":report["captured_at_utc"],
                "decision":BLOCKED}
        code=getattr(exc,"code",None)
        report["failure_code"]=(code if isinstance(code,str) and
               re.fullmatch(r"[A-Z][A-Z0-9_]{2,99}",code)
               else "S6_SOURCE_OR_INTERNAL_EXECUTION_FAILED")
        rc=1
    save(receipt,report)
    print("decision="+report["decision"]+" failure="+report.get("failure_code","NONE"),
          flush=True)
    return rc

def verify(work,receipt):
    report=strict_json(receipt)
    expected=identity()
    require(all(report.get(k)==v for k,v in expected.items()),
            "S6_RECEIPT_EXACT_SOURCE_IDENTITY_DRIFT")
    require(bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                              report.get("captured_at_utc",""))),
            "S6_RECEIPT_CAPTURE_TIME_INVALID")
    if report.get("decision")==BLOCKED:
        require(set(report)==set(expected)|{
            "captured_at_utc","decision","failure_code"
        } and bool(re.fullmatch(r"[A-Z][A-Z0-9_]{2,99}",
                                report.get("failure_code",""))),
                "S6_FAILED_RECEIPT_SCHEMA_INVALID")
        print("S6_ORIGINAL_GYM_READBACK="+BLOCKED)
        return
    require(report.get("decision")==PASS and set(report)==set(expected)|{
        "captured_at_utc","source_archive","reference_upstream","native_tool",
        "local_synthetic_sha256","inventory","members","observations",
        "observations_retained","research_interpretation","decision"
    } and report.get("observations_retained")==36 and
            report.get("research_interpretation")=="LAG_NOT_CLOCK_OR_DOA",
            "S6_POSITIVE_RECEIPT_SCHEMA_INVALID")
    validate_observations(report["observations"])
    c,anchor=contract()
    require(sha((work/"t0-proof.json").read_bytes())==
            report["local_synthetic_sha256"],"S6_SYNTHETIC_RECEIPT_DRIFT")
    t0.verify(work/"reference",work/"t0-proof.json")
    tool,meta,_=s3r.pinned_reference(work)
    require(t0.source_identity(work/"reference")==report["reference_upstream"]
            and meta==report["native_tool"],
            "S6_SOURCE_BUILT_DECODER_READBACK_DRIFT")
    s1.verify_archive(work/"Gym.rar",report["source_archive"],
                      s1.EXPECTED_BYTES,s1.EXPECTED_SHA)
    pcm,members,inventory=original_audio(work,anchor,c,tool,extract=False)
    second=diagnose(pcm,time.monotonic()+240)
    require(members==report["members"] and inventory==report["inventory"]
            and second==report["observations"],
            "S6_INDEPENDENT_PCM_OR_LAG_READBACK_DRIFT")
    print("S6_ORIGINAL_GYM_36_OBSERVATIONS_IDENTICAL="+PASS)

def expect_reject(call):
    try:
        call()
    except Reject:
        return
    raise AssertionError("S6 illegal synthetic or forged diagnostic accepted")

def self_test():
    c,_=contract()
    require(c["frozen_diagnostics"]["observations"]==36)
    import random
    rnd=random.Random(151623)
    original=array("h",(rnd.randint(-16000,16000) for _ in range(WIN)))
    for delay in (3,-3,7,-7):
        shifted=array("h",[0]*WIN)
        if delay>0:
            shifted[delay:]=original[:-delay]
        else:
            shifted[:delay]=original[-delay:]
        rms_l,var_l=rms(original,0)
        rms_r,var_r=rms(shifted,0)
        o=observed_pair(spectrum(original,0),spectrum(shifted,0),
                        rms_l,rms_r,var_l,var_r)
        require(o["status"]=="OBSERVED_DIAGNOSTIC_ONLY" and
                o["lag_samples"]==-delay,
                "S6_SYNTHETIC_KNOWN_LAG_WRONG")
    for data in (array("h",[0]*WIN),array("h",[4]*WIN)):
        level,variable=rms(data,0)
        o=observed_pair([],[],level,level,variable,variable)
        require(o["status"]=="UNDETERMINED_SIGNAL" and
                o["lag_samples"] is None,
                "S6_SILENCE_OR_CONSTANT_FALSE_PEAK")
    expect_reject(lambda:rms(original,1))
    expect_reject(lambda:spectrum(original,WIN))
    fake=[]
    for role in ROLES:
        length=238895 if role=="static" else 237071
        for wi,start in enumerate(windows(length)):
            for l,r in PAIRS:
                fake.append({"role":role,"window":wi,"start_sample":start,
                             "left_mic":l,"right_mic":r,
                             "status":"UNDETERMINED_SIGNAL","lag_samples":None,
                             "rms_left":0.0,"rms_right":0.0,
                             "peak_abs":None,"sidelobe_abs":None,
                             "separation_proxy":None})
    validate_observations(fake)
    expect_reject(lambda:validate_observations(fake[:-1]))
    forged=[dict(row) for row in fake]
    forged[0]["status"]="ORIGINAL_CLOCK_VERIFIED"
    expect_reject(lambda:validate_observations(forged))
    forged=[dict(row) for row in fake]
    forged[0]["start_sample"]+=1
    expect_reject(lambda:validate_observations(forged))
    require(all(c[k] is False for k in FALSE_FIELDS),
            "S6_FROZEN_AUTHORITY_WAS_PROMOTED")
    with tempfile.TemporaryDirectory(prefix="s6-fixture-") as d:
        file=Path(d)/"duplicate.json"
        file.write_text('{"decision":1,"decision":2}',encoding="utf-8")
        expect_reject(lambda:strict_json(file))
    print("REALMAN_D2_S6_OFFLINE_DIAGNOSTIC_NEGATIVES_PASS_NO_ORIGINAL_AUDIO")

def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("action",choices=("self-test","collect","verify"))
    cli.add_argument("--workspace")
    cli.add_argument("--receipt")
    a=cli.parse_args()
    if a.action=="self-test":
        self_test()
        return 0
    require(a.workspace and a.receipt,"S6_REQUIRED_ARGUMENTS_MISSING")
    work,receipt=Path(a.workspace).resolve(),Path(a.receipt).resolve()
    if a.action=="collect":
        return collect(work,receipt)
    verify(work,receipt)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
