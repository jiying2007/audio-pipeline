#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, platform, subprocess, time
from pathlib import Path
VERSION='1.0'
def digest(path: Path) -> str:
    h=hashlib.sha256();
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20), b''): h.update(chunk)
    return h.hexdigest()
def text(path, default='unknown'):
    try:return Path(path).read_text().strip()
    except OSError:return default
def cmd(args, default='unknown'):
    try:return subprocess.check_output(args,text=True,stderr=subprocess.DEVNULL).strip()
    except Exception:return default
def thermal_max():
    vals=[]
    for p in Path('/sys/class/thermal').glob('thermal_zone*/temp'):
        try:
            v=float(p.read_text().strip()); vals.append(v/1000.0 if v>1000 else v)
        except Exception:pass
    return max(vals) if vals else None
def manifest(paths, output: Path):
    items=[]
    for typ,p in paths:
        p=Path(p); items.append({'path':str(p),'type':typ,'size':p.stat().st_size,'sha256':digest(p)})
    obj={'schema_version':1,'collector_version':VERSION,'generated_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'artifacts':items}
    output.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n'); return obj
def main():
    p=argparse.ArgumentParser(); p.add_argument('--sku',required=True); p.add_argument('--policy',type=Path,required=True); p.add_argument('--corpus-manifest',type=Path,required=True); p.add_argument('--benchmark-json',type=Path,required=True); p.add_argument('--acoustic-json',type=Path,required=True); p.add_argument('--soak-json',type=Path,required=True); p.add_argument('--output-dir',type=Path,required=True); p.add_argument('--capture-device',required=True); p.add_argument('--playback-device'); p.add_argument('--sample-rate',type=int,default=16000); p.add_argument('--mic-channels',type=int,default=2); a=p.parse_args()
    a.output_dir.mkdir(parents=True,exist_ok=True)
    bench=json.loads(a.benchmark_json.read_text()); acoustic=json.loads(a.acoustic_json.read_text()); soak=json.loads(a.soak_json.read_text())
    commit=cmd(['git','rev-parse','HEAD']); version='unknown'
    for line in Path('CMakeLists.txt').read_text().splitlines():
        if line.startswith('project(audio_pipeline VERSION '): version=line.split()[2]
    governor=text('/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor')
    cpuset=text('/proc/self/status'); cpuset=next((x.split(':',1)[1].strip() for x in cpuset.splitlines() if x.startswith('Cpus_allowed_list:')),'unknown')
    compiler=cmd(['cc','--version']).splitlines()[0]
    toolchain_digest=hashlib.sha256((compiler+'\n'+platform.machine()+'\n'+platform.libc_ver()[0]+' '+platform.libc_ver()[1]).encode()).hexdigest()
    evidence_path=a.output_dir/'evidence-manifest.json'
    manifest([('benchmark',a.benchmark_json),('acoustic',a.acoustic_json),('soak',a.soak_json),('corpus-manifest',a.corpus_manifest),('policy',a.policy)], evidence_path)
    record={'schema_version':2,'sku':a.sku,'status':'product-certified','policy':json.loads(a.policy.read_text())['policy_id'],'policy_sha256':digest(a.policy),'corpus_manifest_sha256':digest(a.corpus_manifest),'evidence_manifest_sha256':digest(evidence_path),'collector_version':VERSION,'toolchain_digest':toolchain_digest,'build':{'commit':commit,'version':version,'fingerprint':commit,'compiler':compiler,'abi':platform.machine()},'platform':{'soc':platform.machine(),'kernel':platform.release(),'governor':governor,'cpuset':cpuset},'audio_route':{'capture_device':a.capture_device,'playback_device':a.playback_device,'sample_rate_hz':a.sample_rate,'mic_channels':a.mic_channels},'performance':bench['performance'],'acoustic':acoustic['acoustic'],'thermal_power':bench.get('thermal_power',{'ambient_c':bench.get('ambient_c',25.0),'max_soc_c':thermal_max() or 0.0,'average_power_w':bench.get('average_power_w',0.0)}),'soak':soak['soak'],'artifacts':{'result_json':str(a.output_dir/'record.json'),'benchmark_json':str(a.benchmark_json),'evidence_manifest':str(evidence_path),'sha256':digest(evidence_path)}}
    out=a.output_dir/'record.json'; out.write_text(json.dumps(record,indent=2,sort_keys=True)+'\n'); print(out)
if __name__=='__main__': main()
