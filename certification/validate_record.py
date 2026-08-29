#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re
from pathlib import Path
PRODUCT_PERF_REQUIRED={"active_cpu_percent","p95_us","p99_us","deadline_misses","rss_kib","xruns","overruns","input_full_events","output_drop_events"}
PRODUCT_ACOUSTIC_REQUIRED={"corpus_revision","cases_total","cases_passed","far_end_erle_db","aec_convergence_ms","double_talk_near_si_sdr_db","noise_si_sdr_improvement_db","vad_f1","threshold_report"}
POLICY_REQUIRED={"policy_id","max_active_cpu_percent","max_rss_kib","max_p95_us","max_p99_us","max_soc_c","max_average_power_w","min_far_end_erle_db","max_aec_convergence_ms","min_double_talk_near_si_sdr_db","min_noise_si_sdr_improvement_db","min_vad_f1","min_soak_hours"}
def sha256(path):
    h=hashlib.sha256(); h.update(Path(path).read_bytes()); return h.hexdigest()
def require_keys(obj,keys,where,errors):
    missing=sorted(k for k in keys if k not in obj)
    if missing:errors.append(f"{where}: missing {', '.join(missing)}")
def validate_manifest(manifest,errors):
    require_keys(manifest,{"schema_version","collector_version","generated_at","artifacts"},"evidence_manifest",errors)
    if errors:return
    if manifest["schema_version"]!=1:errors.append("evidence_manifest.schema_version: expected 1")
    for i,item in enumerate(manifest["artifacts"]):
        require_keys(item,{"path","type","size","sha256"},f"evidence_manifest.artifacts[{i}]",errors)
        if not re.fullmatch(r"[0-9a-fA-F]{64}",str(item.get("sha256",""))):errors.append(f"evidence_manifest.artifacts[{i}].sha256: invalid")
def validate(record,policy=None,policy_hash=None,evidence=None,evidence_hash=None,corpus_hash=None):
    errors=[]; require_keys(record,{"sku","status","build","platform","audio_route","performance","acoustic","soak","artifacts"},"record",errors)
    if errors:return errors
    status=record["status"]
    if status not in {"pending","board-validated","product-certified","failed"}:errors.append(f"status: unsupported value {status!r}")
    require_keys(record["build"],{"commit","version","fingerprint","compiler","abi"},"build",errors); require_keys(record["platform"],{"soc","kernel","governor","cpuset"},"platform",errors); require_keys(record["audio_route"],{"capture_device","playback_device","sample_rate_hz","mic_channels"},"audio_route",errors); require_keys(record["soak"],{"hours","passed"},"soak",errors)
    if record["audio_route"].get("sample_rate_hz") not in {8000,16000,24000,32000,48000}:errors.append("audio_route.sample_rate_hz: unsupported rate")
    if record["audio_route"].get("mic_channels") not in {1,2}:errors.append("audio_route.mic_channels: must be 1 or 2")
    if status!="product-certified":return errors
    require_keys(record,{"schema_version","policy","policy_sha256","corpus_manifest_sha256","evidence_manifest_sha256","collector_version","toolchain_digest","thermal_power"},"record",errors)
    if record.get("schema_version")!=2:errors.append("schema_version: product-certified records require v2")
    for key in ("policy_sha256","corpus_manifest_sha256","evidence_manifest_sha256","toolchain_digest"):
        if not re.fullmatch(r"[0-9a-fA-F]{64}",str(record.get(key,""))):errors.append(f"{key}: must be 64 hexadecimal characters")
    if policy is None:errors.append("policy: product-certified requires --policy"); return errors
    require_keys(policy,POLICY_REQUIRED,"policy",errors)
    if policy_hash and record.get("policy_sha256")!=policy_hash:errors.append("policy_sha256: does not match supplied policy bytes")
    if corpus_hash and record.get("corpus_manifest_sha256")!=corpus_hash:errors.append("corpus_manifest_sha256: does not match supplied corpus manifest")
    if evidence is None:errors.append("evidence_manifest: product-certified requires --evidence-manifest")
    else:
        validate_manifest(evidence,errors)
        if evidence_hash and record.get("evidence_manifest_sha256")!=evidence_hash:errors.append("evidence_manifest_sha256: does not match supplied manifest")
    if errors:return errors
    if record.get("policy")!=policy.get("policy_id"):errors.append("policy: record policy id must match supplied policy")
    perf,acoustic,soak,artifacts=record["performance"],record["acoustic"],record["soak"],record["artifacts"]; thermal=record["thermal_power"]
    require_keys(perf,PRODUCT_PERF_REQUIRED,"performance",errors); require_keys(acoustic,PRODUCT_ACOUSTIC_REQUIRED,"acoustic",errors); require_keys(thermal,{"ambient_c","max_soc_c","average_power_w"},"thermal_power",errors); require_keys(soak,{"hours","passed","xruns","deadline_misses","output_drop_events"},"soak",errors); require_keys(artifacts,{"result_json","benchmark_json","evidence_manifest","sha256"},"artifacts",errors)
    if errors:return errors
    for key in {"deadline_misses","xruns","overruns","input_full_events","output_drop_events"}:
        if int(perf[key])!=0:errors.append(f"performance.{key}: nominal gate requires 0")
    for key in {"xruns","deadline_misses","output_drop_events"}:
        if int(soak[key])!=0:errors.append(f"soak.{key}: nominal gate requires 0")
    checks=[(float(perf["active_cpu_percent"])<=float(policy["max_active_cpu_percent"]),"performance.active_cpu_percent"),(int(perf["rss_kib"])<=int(policy["max_rss_kib"]),"performance.rss_kib"),(float(perf["p95_us"])<=float(policy["max_p95_us"]),"performance.p95_us"),(float(perf["p99_us"])<=float(policy["max_p99_us"]),"performance.p99_us"),(float(thermal["max_soc_c"])<=float(policy["max_soc_c"]),"thermal_power.max_soc_c"),(float(thermal["average_power_w"])<=float(policy["max_average_power_w"]),"thermal_power.average_power_w"),(float(acoustic["far_end_erle_db"])>=float(policy["min_far_end_erle_db"]),"acoustic.far_end_erle_db"),(float(acoustic["aec_convergence_ms"])<=float(policy["max_aec_convergence_ms"]),"acoustic.aec_convergence_ms"),(float(acoustic["double_talk_near_si_sdr_db"])>=float(policy["min_double_talk_near_si_sdr_db"]),"acoustic.double_talk_near_si_sdr_db"),(float(acoustic["noise_si_sdr_improvement_db"])>=float(policy["min_noise_si_sdr_improvement_db"]),"acoustic.noise_si_sdr_improvement_db"),(float(acoustic["vad_f1"])>=float(policy["min_vad_f1"]),"acoustic.vad_f1"),(float(soak["hours"])>=float(policy["min_soak_hours"]),"soak.hours")]
    for passed,name in checks:
        if not passed:errors.append(f"{name}: violates certification policy")
    if soak.get("passed") is not True:errors.append("soak.passed: product-certified requires true")
    if int(acoustic["cases_passed"])!=int(acoustic["cases_total"]):errors.append("acoustic: every certification corpus case must pass")
    return errors
def self_test():
    policy={"policy_id":"test-policy","max_active_cpu_percent":40,"max_rss_kib":4096,"max_p95_us":7000,"max_p99_us":9000,"max_soc_c":85,"max_average_power_w":2,"min_far_end_erle_db":15,"max_aec_convergence_ms":1000,"min_double_talk_near_si_sdr_db":5,"min_noise_si_sdr_improvement_db":3,"min_vad_f1":0.85,"min_soak_hours":8}; ph="1"*64; ch="2"*64; eh="3"*64
    evidence={"schema_version":1,"collector_version":"1","generated_at":"now","artifacts":[{"path":"x","type":"benchmark","size":1,"sha256":"4"*64}]}
    record={"schema_version":2,"sku":"test","status":"product-certified","policy":"test-policy","policy_sha256":ph,"corpus_manifest_sha256":ch,"evidence_manifest_sha256":eh,"collector_version":"1","toolchain_digest":"5"*64,"build":{"commit":"abcdef0","version":"1.2.0","fingerprint":"x","compiler":"gcc","abi":"armv7"},"platform":{"soc":"test","kernel":"6.6","governor":"performance","cpuset":"1"},"audio_route":{"capture_device":"hw:0,0","playback_device":"hw:0,0","sample_rate_hz":16000,"mic_channels":2},"performance":{"active_cpu_percent":20,"p95_us":3000,"p99_us":5000,"deadline_misses":0,"rss_kib":512,"xruns":0,"overruns":0,"input_full_events":0,"output_drop_events":0},"acoustic":{"corpus_revision":"r1","cases_total":10,"cases_passed":10,"far_end_erle_db":20,"aec_convergence_ms":500,"double_talk_near_si_sdr_db":8,"noise_si_sdr_improvement_db":4,"vad_f1":0.9,"threshold_report":"result.json"},"thermal_power":{"ambient_c":25,"max_soc_c":60,"average_power_w":1},"soak":{"hours":8,"passed":True,"xruns":0,"deadline_misses":0,"output_drop_events":0},"artifacts":{"result_json":"result.json","benchmark_json":"bench.json","evidence_manifest":"evidence.json","sha256":"0"*64}}
    assert validate(record,policy,ph,evidence,eh,ch)==[]; bad=json.loads(json.dumps(record));bad["policy_sha256"]="0"*64;assert validate(bad,policy,ph,evidence,eh,ch);print("audio-pipeline certification validator self-test: OK")
def main():
    p=argparse.ArgumentParser();p.add_argument("record",type=Path,nargs="?");p.add_argument("--policy",type=Path);p.add_argument("--evidence-manifest",type=Path);p.add_argument("--corpus-manifest",type=Path);p.add_argument("--self-test",action="store_true");a=p.parse_args()
    if a.self_test:self_test();return 0
    if a.record is None:p.error("record is required unless --self-test is used")
    rec=json.loads(a.record.read_text());pol=json.loads(a.policy.read_text()) if a.policy else None;ev=json.loads(a.evidence_manifest.read_text()) if a.evidence_manifest else None
    errors=validate(rec,pol,sha256(a.policy) if a.policy else None,ev,sha256(a.evidence_manifest) if a.evidence_manifest else None,sha256(a.corpus_manifest) if a.corpus_manifest else None)
    if errors:
        [print(f"ERROR: {e}") for e in errors];return 1
    print(f"certification record OK: {a.record}");return 0
if __name__=="__main__":raise SystemExit(main())
