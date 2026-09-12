#!/usr/bin/env python3
"""PCR02 real-capture bundle v1: create, seal, validate, replay and diagnose.

Repository-internal measurement tooling only. It does not change APD v1 or grant
HIL, Extended Real, Product Qualification, or Product Certification authority.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, re, subprocess, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAG = "v2.3.16"
SOURCE = "57e4c64adc1cf06819e46e24e275ecd746d5f17f"
VERSION = "2.3.16"
ZERO = "0" * 64
REQUIRED_ROLES = {"mic_raw","render_reference","pipeline_output","frame_timeline","telemetry"}
OPTIONAL_ROLES = {"aec_output","bf_output","ns_output","agc_output","frame_metrics","system_metrics","app_log","dmesg","apd","config_snapshot"}
MONO_PCM = {"render_reference","pipeline_output","aec_output","bf_output","ns_output","agc_output"}
REQUIRED_SIGNALS = {"timestamp_ns","left_motor_rpm","right_motor_rpm","left_foc_iq","right_foc_iq","left_pwm","right_pwm","servo_state","motion_state"}
H40 = re.compile(r"^[0-9a-f]{40}$"); H64 = re.compile(r"^[0-9a-f]{64}$")


def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024), b""): h.update(chunk)
    return h.hexdigest()


def safe_rel(text: str) -> bool:
    p=Path(text); return bool(text) and not p.is_absolute() and ".." not in p.parts


def under(root: Path, text: str) -> Path:
    if not safe_rel(text): raise ValueError(f"unsafe relative path: {text!r}")
    root=root.resolve(); p=(root/text).resolve()
    if p != root and root not in p.parents: raise ValueError(f"path escapes bundle root: {text!r}")
    return p


def digest(value: dict) -> str:
    v=copy.deepcopy(value); v.pop("bundle_digest_sha256", None)
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()


def jsonl(path: Path) -> list[dict]:
    out=[]
    for n,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        if not line.strip(): continue
        try: row=json.loads(line)
        except json.JSONDecodeError as exc: raise ValueError(f"{path}: bad JSONL line {n}: {exc}") from exc
        if not isinstance(row,dict): raise ValueError(f"{path}: line {n} is not an object")
        out.append(row)
    return out


def plan_slot(plan_path: Path, slot_id: str) -> tuple[dict,dict]:
    plan=json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("schema_version") != 1 or plan.get("product") != "PCR02": raise ValueError("capture plan identity mismatch")
    found=[x for x in plan.get("slots",[]) if x.get("slot_id")==slot_id]
    if len(found)!=1: raise ValueError(f"expected one capture-plan slot {slot_id!r}")
    slot=found[0]; scene={k:v for k,v in slot.items() if k not in {"slot_id","track"}}
    return slot,scene


def check_structure(v: dict, allow_unsealed: bool=False) -> None:
    keys={"schema_version","authority","sealed","capture_id","capture_purpose","product","slot_id","track","created_utc","release_authority","software","hardware","scene","clock","duration_seconds","files","telemetry_signals","evidence_claims","bundle_digest_sha256"}
    if set(v)!=keys: raise ValueError(f"manifest keys drifted: missing={sorted(keys-set(v))} unexpected={sorted(set(v)-keys)}")
    if v["schema_version"]!=1 or v["authority"]!="pcr02-real-capture-bundle" or v["product"]!="PCR02": raise ValueError("bundle identity mismatch")
    if not isinstance(v["sealed"],bool) or (not v["sealed"] and not allow_unsealed): raise ValueError("unsealed working set is not evidence")
    if not v["capture_id"] or v["capture_purpose"] not in {"development","qualification-candidate"}: raise ValueError("capture identity/purpose invalid")
    if v["track"] not in {"bf-geometry","self-noise","aec-product-path"}: raise ValueError("track invalid")
    if v["release_authority"] != {"tag":TAG,"source_sha":SOURCE}: raise ValueError("immutable release authority drifted")
    sw=v["software"]
    if set(sw)!={"git_sha","version","binary_sha256","build_info"} or not H40.fullmatch(str(sw["git_sha"])) or not H64.fullmatch(str(sw["binary_sha256"])): raise ValueError("software identity invalid")
    if set(sw["build_info"])!={"aec_backend","ns_estimator","simd_backend","resampler_mode"} or any(not str(x) for x in sw["build_info"].values()): raise ValueError("build_info invalid")
    if v["capture_purpose"]=="qualification-candidate" and (sw["git_sha"]!=SOURCE or sw["version"]!=VERSION): raise ValueError("qualification candidate must execute exact v2.3.16 source")
    hw=v["hardware"]; expected={"soc":"SSC305","mic_channels":2,"mic_spacing_mm":35.0,"sample_rate_hz":16000,"sample_format":"s16le","frame_samples":160}
    if set(hw)!=set(expected)|{"board_revision","device_id"} or any(hw.get(k)!=x for k,x in expected.items()) or not hw["board_revision"] or not hw["device_id"]: raise ValueError("PCR02 hardware geometry/identity invalid")
    if v["clock"]!={"domain":"monotonic","timestamp_unit":"ns"} or not isinstance(v["scene"],dict) or float(v["duration_seconds"])<0: raise ValueError("clock/scene/duration invalid")
    files=v["files"]; missing=REQUIRED_ROLES-set(files); unknown=set(files)-REQUIRED_ROLES-OPTIONAL_ROLES
    if missing or unknown: raise ValueError(f"file roles invalid: missing={sorted(missing)} unknown={sorted(unknown)}")
    seen=set()
    for role,d in files.items():
        if set(d)!={"path","sha256","size_bytes"} or not safe_rel(str(d["path"])) or d["path"] in seen or not H64.fullmatch(str(d["sha256"])) or not isinstance(d["size_bytes"],int) or d["size_bytes"]<0: raise ValueError(f"file descriptor invalid: {role}")
        seen.add(d["path"])
    signals=v["telemetry_signals"]
    if not isinstance(signals,list) or len(signals)!=len(set(signals)) or not REQUIRED_SIGNALS <= set(signals): raise ValueError("telemetry signal contract incomplete")
    claims=v["evidence_claims"]; ck={"real_capture","hil_pass","extended_real_pass","product_qualification_pass","product_certification_pass"}
    if set(claims)!=ck or any(claims[k] is not False for k in ck-{"real_capture"}) or not isinstance(claims["real_capture"],bool): raise ValueError("capture bundle cannot claim HIL/Extended Real/PQ/Certification PASS")
    if v["sealed"] != claims["real_capture"]: raise ValueError("sealed/real_capture state mismatch")
    if not H64.fullmatch(str(v["bundle_digest_sha256"])): raise ValueError("bundle digest format invalid")


def check_plan(v: dict, plan_path: Path) -> None:
    slot,scene=plan_slot(plan_path,v["slot_id"])
    if v["track"]!=slot["track"] or v["scene"]!=scene: raise ValueError("manifest scene does not exactly match capture-plan slot")


def files(v: dict, root: Path, verify_hash: bool=True) -> dict[str,Path]:
    out={}
    for role,d in v["files"].items():
        p=under(root,d["path"])
        if not p.is_file(): raise FileNotFoundError(p)
        if verify_hash and (p.stat().st_size!=d["size_bytes"] or sha(p)!=d["sha256"]): raise ValueError(f"file binding mismatch: {role}")
        out[role]=p
    return out


def check_payload(v: dict, paths: dict[str,Path]) -> dict:
    hw=v["hardware"]; m=paths["mic_raw"].stat().st_size
    if m<=0 or m%(2*hw["mic_channels"]): raise ValueError("mic_raw must be non-empty interleaved s16le stereo")
    samples=m//(2*hw["mic_channels"])
    for role in MONO_PCM & set(paths):
        size=paths[role].stat().st_size
        if size%2 or size//2!=samples: raise ValueError(f"PCM sample count mismatch: {role}")
    if samples%hw["frame_samples"]: raise ValueError("audio is not an integer number of 10 ms frames")
    n=samples//hw["frame_samples"]; timeline=jsonl(paths["frame_timeline"])
    if len(timeline)!=n: raise ValueError("frame timeline row count does not match audio")
    prev_seq=prev_cap=prev_render=None
    for i,row in enumerate(timeline):
        req={"index","sequence","capture_timestamp_ns","render_timestamp_ns"}
        if not req<=set(row) or int(row["index"])!=i: raise ValueError(f"frame timeline row {i} invalid")
        seq,cap,ren=int(row["sequence"]),int(row["capture_timestamp_ns"]),int(row["render_timestamp_ns"])
        if prev_seq is not None and seq!=prev_seq+1: raise ValueError("frame sequence discontinuity")
        if prev_cap is not None and cap<=prev_cap: raise ValueError("capture timestamp not strictly monotonic")
        if prev_render is not None and ren<prev_render: raise ValueError("render timestamp regressed")
        prev_seq,prev_cap,prev_render=seq,cap,ren
    telemetry=jsonl(paths["telemetry"])
    if not telemetry: raise ValueError("telemetry is empty")
    prev=None
    for i,row in enumerate(telemetry):
        if not set(v["telemetry_signals"])<=set(row): raise ValueError(f"telemetry row {i} missing declared signals")
        ts=int(row["timestamp_ns"])
        if prev is not None and ts<prev: raise ValueError("telemetry timestamp regressed")
        prev=ts
    start,end=int(timeline[0]["capture_timestamp_ns"]),int(timeline[-1]["capture_timestamp_ns"])
    if int(telemetry[0]["timestamp_ns"])>start or int(telemetry[-1]["timestamp_ns"])<end: raise ValueError("telemetry does not cover the capture interval")
    duration=samples/hw["sample_rate_hz"]
    if abs(float(v["duration_seconds"])-duration)>1/hw["sample_rate_hz"]: raise ValueError("manifest duration does not match PCM")
    return {"audio_samples":samples,"frame_count":n,"telemetry_rows":len(telemetry),"duration_seconds":duration}


def validate(manifest: Path, root: Path, plan: Path) -> dict:
    v=json.loads(manifest.read_text(encoding="utf-8")); check_structure(v); check_plan(v,plan)
    stats=check_payload(v,files(v,root))
    if v["bundle_digest_sha256"]!=digest(v): raise ValueError("bundle digest mismatch")
    return {"result":"PASS","capture_id":v["capture_id"],"slot_id":v["slot_id"],"track":v["track"],"capture_purpose":v["capture_purpose"],"bundle_digest_sha256":v["bundle_digest_sha256"],"file_roles":sorted(v["files"]),"evidence_claims":v["evidence_claims"],**stats}


def new(args) -> dict:
    slot,scene=plan_slot(args.plan,args.slot_id)
    if args.purpose=="qualification-candidate" and (args.source_sha!=SOURCE or args.version!=VERSION): raise ValueError("qualification candidate requires exact v2.3.16 source/version")
    if not H40.fullmatch(args.source_sha) or not H64.fullmatch(args.binary_sha256): raise ValueError("source/binary identity format invalid")
    args.output_dir.mkdir(parents=True,exist_ok=True); (args.output_dir/"audio").mkdir(exist_ok=True)
    def d(path): return {"path":path,"sha256":ZERO,"size_bytes":0}
    f={"mic_raw":d("audio/mic_raw.pcm"),"render_reference":d("audio/render_reference.pcm"),"pipeline_output":d("audio/pipeline_output.pcm"),"frame_timeline":d("frame_timeline.jsonl"),"telemetry":d("telemetry.jsonl")}
    for item in args.optional_file:
        role,sep,path=item.partition("=")
        if not sep or role not in OPTIONAL_ROLES or role in f: raise ValueError(f"bad --optional-file {item!r}")
        f[role]=d(path)
    v={"schema_version":1,"authority":"pcr02-real-capture-bundle","sealed":False,"capture_id":args.capture_id,"capture_purpose":args.purpose,"product":"PCR02","slot_id":args.slot_id,"track":slot["track"],"created_utc":datetime.now(timezone.utc).isoformat(),"release_authority":{"tag":TAG,"source_sha":SOURCE},"software":{"git_sha":args.source_sha,"version":args.version,"binary_sha256":args.binary_sha256,"build_info":{"aec_backend":args.aec_backend,"ns_estimator":args.ns_estimator,"simd_backend":args.simd_backend,"resampler_mode":args.resampler_mode}},"hardware":{"soc":"SSC305","board_revision":args.board_revision,"device_id":args.device_id,"mic_channels":2,"mic_spacing_mm":35.0,"sample_rate_hz":16000,"sample_format":"s16le","frame_samples":160},"scene":scene,"clock":{"domain":"monotonic","timestamp_unit":"ns"},"duration_seconds":0.0,"files":f,"telemetry_signals":sorted(REQUIRED_SIGNALS),"evidence_claims":{"real_capture":False,"hil_pass":False,"extended_real_pass":False,"product_qualification_pass":False,"product_certification_pass":False},"bundle_digest_sha256":ZERO}
    check_structure(v,True); check_plan(v,args.plan); out=args.output_dir/"manifest.json"; out.write_text(json.dumps(v,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return {"result":"INITIALIZED","manifest":str(out),"required_paths":{r:f[r]["path"] for r in sorted(REQUIRED_ROLES)}}


def seal(manifest: Path, root: Path, plan: Path) -> dict:
    v=json.loads(manifest.read_text(encoding="utf-8")); check_structure(v,True); check_plan(v,plan)
    if v["sealed"]: raise ValueError("sealed evidence is immutable; create a new capture")
    p=files(v,root,False)
    for role,path in p.items(): v["files"][role].update(sha256=sha(path),size_bytes=path.stat().st_size)
    stats=check_payload({**v,"duration_seconds":0.0},p); v["duration_seconds"]=stats["duration_seconds"]
    v["sealed"]=True; v["evidence_claims"]["real_capture"]=True; v["bundle_digest_sha256"]=digest(v)
    tmp=manifest.with_suffix(manifest.suffix+".tmp"); tmp.write_text(json.dumps(v,indent=2,sort_keys=True)+"\n",encoding="utf-8"); tmp.replace(manifest)
    return validate(manifest,root,plan)


def compare_s16(a: bytes,b: bytes) -> dict:
    if len(a)!=len(b): return {"bit_exact":False,"expected_bytes":len(a),"actual_bytes":len(b),"mae_lsb":None,"max_abs_lsb":None}
    if a==b: return {"bit_exact":True,"expected_bytes":len(a),"actual_bytes":len(b),"mae_lsb":0.0,"max_abs_lsb":0}
    import array
    x=array.array("h"); y=array.array("h"); x.frombytes(a); y.frombytes(b)
    if sys.byteorder!="little": x.byteswap(); y.byteswap()
    d=[abs(int(i)-int(j)) for i,j in zip(x,y)]
    return {"bit_exact":False,"expected_bytes":len(a),"actual_bytes":len(b),"mae_lsb":sum(d)/len(d),"max_abs_lsb":max(d)}


def replay(args) -> dict:
    s=validate(args.manifest,args.root,args.plan); v=json.loads(args.manifest.read_text()); p=files(v,args.root)
    with tempfile.TemporaryDirectory(prefix="pcr02-replay-") as t:
        out=Path(t)/"out.pcm"; subprocess.run([str(args.processor),"--sample-rate","16000","--mic-channels","2",str(p["mic_raw"]),str(p["render_reference"]),str(out)],check=True)
        actual=out.read_bytes()
    if args.output_pcm: args.output_pcm.parent.mkdir(parents=True,exist_ok=True); args.output_pcm.write_bytes(actual)
    return {"result":"PASS","capture_id":s["capture_id"],"bundle_digest_sha256":s["bundle_digest_sha256"],"comparison":compare_s16(p["pipeline_output"].read_bytes(),actual),"causal_proof":False,"note":"Replay is A/B evidence unless the complete effective runtime configuration is independently bound."}


def diagnose(args) -> dict:
    s=validate(args.manifest,args.root,args.plan); v=json.loads(args.manifest.read_text()); p=files(v,args.root)
    if "apd" not in p: raise ValueError("diagnose requires optional file role apd")
    triage=args.output_dir/"triage"; diagnosis=args.output_dir/"diagnosis"; args.output_dir.mkdir(parents=True,exist_ok=True)
    cmd=[sys.executable,str(ROOT/"tests/diagnostics/aptriage.py"),str(p["apd"]),"--processor",str(args.processor),"--processor-build-info",str(args.processor_build_info),"--output-dir",str(triage)]
    if args.require_bit_exact: cmd.append("--require-bit-exact")
    if args.stage_counterfactuals: cmd.append("--stage-counterfactuals")
    subprocess.run(cmd,cwd=ROOT,check=True); subprocess.run([sys.executable,str(ROOT/"tests/diagnostics/apdiagnose.py"),str(triage/"triage.json"),"--output-dir",str(diagnosis)],cwd=ROOT,check=True)
    result={"result":"PASS","capture_id":s["capture_id"],"bundle_digest_sha256":s["bundle_digest_sha256"],"apd_sha256":v["files"]["apd"]["sha256"],"triage_sha256":sha(triage/"triage.json"),"diagnosis_sha256":sha(diagnosis/"diagnosis.json"),"causal_proof":False}
    (args.output_dir/"capture-analysis.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8"); return result


def self_test() -> None:
    with tempfile.TemporaryDirectory() as t:
        root=Path(t); (root/"audio").mkdir(); plan={"schema_version":1,"product":"PCR02","slots":[{"slot_id":"self-noise-01","track":"self-noise","motion_class":"idle","floor_surface":"hard-floor","speech_state":"none"}]}; pp=root/"plan.json"; pp.write_text(json.dumps(plan))
        samples=320; (root/"audio/mic_raw.pcm").write_bytes(b"\0"*samples*4); (root/"audio/render_reference.pcm").write_bytes(b"\0"*samples*2); (root/"audio/pipeline_output.pcm").write_bytes(b"\0"*samples*2)
        tl=[{"index":0,"sequence":1,"capture_timestamp_ns":1_000_000_000,"render_timestamp_ns":999_000_000},{"index":1,"sequence":2,"capture_timestamp_ns":1_010_000_000,"render_timestamp_ns":1_009_000_000}]; (root/"frame_timeline.jsonl").write_text("".join(json.dumps(x)+"\n" for x in tl))
        tele=[]
        for ts in (999_000_000,1_011_000_000):
            row={k:0 for k in REQUIRED_SIGNALS}; row.update(timestamp_ns=ts,servo_state="idle",motion_state="idle"); tele.append(row)
        (root/"telemetry.jsonl").write_text("".join(json.dumps(x)+"\n" for x in tele))
        desc={}
        for r,p in {"mic_raw":"audio/mic_raw.pcm","render_reference":"audio/render_reference.pcm","pipeline_output":"audio/pipeline_output.pcm","frame_timeline":"frame_timeline.jsonl","telemetry":"telemetry.jsonl"}.items():
            f=root/p; desc[r]={"path":p,"sha256":sha(f),"size_bytes":f.stat().st_size}
        v={"schema_version":1,"authority":"pcr02-real-capture-bundle","sealed":True,"capture_id":"self-test","capture_purpose":"qualification-candidate","product":"PCR02","slot_id":"self-noise-01","track":"self-noise","created_utc":"2026-09-12T00:00:00+00:00","release_authority":{"tag":TAG,"source_sha":SOURCE},"software":{"git_sha":SOURCE,"version":VERSION,"binary_sha256":"1"*64,"build_info":{"aec_backend":"nlms","ns_estimator":"mcra","simd_backend":"neon","resampler_mode":"bandlimited"}},"hardware":{"soc":"SSC305","board_revision":"test","device_id":"test","mic_channels":2,"mic_spacing_mm":35.0,"sample_rate_hz":16000,"sample_format":"s16le","frame_samples":160},"scene":{"motion_class":"idle","floor_surface":"hard-floor","speech_state":"none"},"clock":{"domain":"monotonic","timestamp_unit":"ns"},"duration_seconds":0.02,"files":desc,"telemetry_signals":sorted(REQUIRED_SIGNALS),"evidence_claims":{"real_capture":True,"hil_pass":False,"extended_real_pass":False,"product_qualification_pass":False,"product_certification_pass":False},"bundle_digest_sha256":ZERO}; v["bundle_digest_sha256"]=digest(v); mf=root/"manifest.json"; mf.write_text(json.dumps(v)); assert validate(mf,root,pp)["frame_count"]==2
        bad=copy.deepcopy(v); bad["evidence_claims"]["hil_pass"]=True
        try: check_structure(bad)
        except ValueError: pass
        else: raise AssertionError("HIL overclaim accepted")
        bad=copy.deepcopy(v); bad["bundle_digest_sha256"]="f"*64; bm=root/"bad.json"; bm.write_text(json.dumps(bad))
        try: validate(bm,root,pp)
        except ValueError: pass
        else: raise AssertionError("bad digest accepted")
    print("PCR02 capture bundle self-test: OK")


def common(p):
    p.add_argument("--manifest",type=Path,required=True); p.add_argument("--root",type=Path); p.add_argument("--plan",type=Path,default=ROOT/"tests/validation/pcr02_capture_plan.json")


def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--self-test",action="store_true"); sub=p.add_subparsers(dest="cmd")
    n=sub.add_parser("new"); n.add_argument("--slot-id",required=True); n.add_argument("--capture-id",required=True); n.add_argument("--purpose",choices=["development","qualification-candidate"],required=True); n.add_argument("--output-dir",type=Path,required=True); n.add_argument("--plan",type=Path,default=ROOT/"tests/validation/pcr02_capture_plan.json"); n.add_argument("--source-sha",required=True); n.add_argument("--version",required=True); n.add_argument("--binary-sha256",required=True); n.add_argument("--board-revision",required=True); n.add_argument("--device-id",required=True); n.add_argument("--aec-backend",required=True); n.add_argument("--ns-estimator",required=True); n.add_argument("--simd-backend",required=True); n.add_argument("--resampler-mode",required=True); n.add_argument("--optional-file",action="append",default=[])
    s=sub.add_parser("seal"); common(s); v=sub.add_parser("validate"); common(v); r=sub.add_parser("replay"); common(r); r.add_argument("--processor",type=Path,required=True); r.add_argument("--output-pcm",type=Path); r.add_argument("--require-bit-exact",action="store_true")
    d=sub.add_parser("diagnose"); common(d); d.add_argument("--processor",type=Path,required=True); d.add_argument("--processor-build-info",type=Path,required=True); d.add_argument("--output-dir",type=Path,required=True); d.add_argument("--require-bit-exact",action="store_true"); d.add_argument("--stage-counterfactuals",action="store_true")
    a=p.parse_args()
    try:
        if a.self_test: self_test(); return 0
        if a.cmd=="new": out=new(a)
        elif a.cmd:
            a.root=a.root or a.manifest.parent
            if a.cmd=="seal": out=seal(a.manifest,a.root,a.plan)
            elif a.cmd=="validate": out=validate(a.manifest,a.root,a.plan)
            elif a.cmd=="replay":
                out=replay(a)
                if a.require_bit_exact and not out["comparison"]["bit_exact"]: print(json.dumps(out,indent=2,sort_keys=True)); return 1
            else: out=diagnose(a)
        else: p.error("choose a command or --self-test")
        print(json.dumps(out,indent=2,sort_keys=True)); return 0
    except (OSError,ValueError,subprocess.CalledProcessError) as exc: print(f"pcr02_capture_bundle: {exc}",file=sys.stderr); return 2

if __name__=="__main__": raise SystemExit(main())
