#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, statistics, subprocess, tempfile
from pathlib import Path


def require(ok: bool, msg: str) -> None:
    if not ok: raise ValueError(msg)

def load_json(path: Path) -> dict:
    v=json.loads(path.read_text(encoding='utf-8')); require(isinstance(v,dict),f'object required: {path}'); return v

def write_json(path: Path, v: object) -> None:
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(v,indent=2,sort_keys=True,allow_nan=False)+'\n',encoding='utf-8')

def import_module(path: Path):
    spec=importlib.util.spec_from_file_location('frozen_helper',path); require(spec and spec.loader,f'cannot import {path}')
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def percentile(vals:list[float],q:float):
    a=sorted(float(v) for v in vals if v is not None and math.isfinite(float(v)))
    if not a:return None
    if len(a)==1:return a[0]
    p=(len(a)-1)*q; lo=math.floor(p); hi=math.ceil(p)
    return a[lo] if lo==hi else a[lo]*(hi-p)+a[hi]*(p-lo)

def distribution(vals:list[float])->dict:
    a=[float(v) for v in vals if v is not None and math.isfinite(float(v))]
    return {'count':len(a),'min':min(a) if a else None,'median':statistics.median(a) if a else None,'p05':percentile(a,.05),'p95':percentile(a,.95),'max':max(a) if a else None}

def ranks(vals:list[float])->list[float]:
    s=sorted((float(v),i) for i,v in enumerate(vals)); r=[0.0]*len(vals); i=0
    while i<len(s):
        j=i+1
        while j<len(s) and s[j][0]==s[i][0]:j+=1
        rank=((i+1)+j)/2.0
        for k in range(i,j):r[s[k][1]]=rank
        i=j
    return r

def spearman(xs:list[float],ys:list[float])->dict:
    p=[(float(x),float(y)) for x,y in zip(xs,ys) if x is not None and y is not None and math.isfinite(float(x)) and math.isfinite(float(y))]
    if len(p)<2:return {'count':len(p),'rho':None}
    xr=ranks([x for x,_ in p]); yr=ranks([y for _,y in p]); mx=statistics.mean(xr); my=statistics.mean(yr)
    num=sum((x-mx)*(y-my) for x,y in zip(xr,yr)); dx=sum((x-mx)**2 for x in xr); dy=sum((y-my)**2 for y in yr)
    return {'count':len(p),'rho':None if dx<=0 or dy<=0 else num/math.sqrt(dx*dy)}

def validate_manifest(m:dict)->None:
    require(m.get('schema_version')==1,'manifest schema'); require(m.get('investigation_id')=='pure-far-source-coherent-excess-v1','manifest id')
    require(m.get('status')=='DIAGNOSTIC_ONLY' and m.get('candidate_budget')==0,'candidate-zero authority')
    require(m['selection']['subsampling_allowed'] is False and m['selection']['result_dependent_selection'] is False,'selection authority')
    g=m['geometry']; require(g['baseline_aec_tail_ms']==96 and g['source_tail_samples']==4608 and g['expected_fft_size']==16384,'geometry drift')
    require(g['new_delay_search_performed'] is False and g['geometry_optimization_forbidden'] is True,'search forbidden')
    o=m['observation_method']; require(o['signal_correction_applied'] is False and o['filter_fit_or_application'] is False and o['threshold_search_performed'] is False and o['candidate_selection'] is False,'observation authority')

def validate_inventory(inv:dict,m:dict)->list[dict]:
    s=m['selection']; require(inv['source_revision']==m['source']['revision'] and inv['source_tree_sha']==m['source']['dataset_tree_sha'],'source drift')
    require(inv['complete_pair_count']==s['expected_complete_pair_count']==125,'count drift'); require(inv['total_lfs_bytes']==s['expected_total_lfs_bytes'],'bytes drift'); require(inv['selection_fingerprint_sha256']==s['expected_selection_fingerprint_sha256'],'fingerprint drift')
    cases=inv['cases']; require(len(cases)==125,'case list drift'); require([c['guid'] for c in cases]==sorted(c['guid'] for c in cases),'GUID ordering')
    canonical=json.dumps(cases,sort_keys=True,separators=(',',':')).encode(); require(hashlib.sha256(canonical).hexdigest()==inv['selection_fingerprint_sha256'],'canonical fingerprint')
    return cases

def run_case(case:dict,source_root:Path,provenance_probe:Path,coherence_probe:Path,helper,m:dict)->dict:
    mic_path=helper.verify_file(source_root,case['mic']); render_path=helper.verify_file(source_root,case['lpb'])
    mic_rate,mic=helper.read_wav(mic_path); render_rate,render=helper.read_wav(render_path)
    require(mic_rate==render_rate==48000,f'rate drift: {case["guid"]}'); common=min(len(mic),len(render)); require(common>=4*16384,f'clip too short: {case["guid"]}')
    mic=mic[:common]; render=render[:common]
    with tempfile.TemporaryDirectory(prefix='source-coherent-excess-') as td:
        root=Path(td); mic_pcm=root/'mic.pcm'; render_pcm=root/'render.pcm'; trace=root/'trace.jsonl'; spectral=root/'spectral.json'
        helper.write_pcm16(mic_pcm,mic); helper.write_pcm16(render_pcm,render)
        subprocess.run([str(provenance_probe),'48000',str(mic_pcm),str(render_pcm),str(trace)],check=True)
        rows=[json.loads(x) for x in trace.read_text(encoding='utf-8').splitlines() if x.strip()]
        require(rows and all(int(r['frame'])==i for i,r in enumerate(rows)),'contiguous trace')
        frame_samples=480; rows=rows[:min(len(rows),common//frame_samples)]
        constants=m['baseline_code_lock']['activity_constants_observed_not_tuned']; activity=helper.summarize_rows(rows,0,len(rows),constants)
        far=[r for r in rows if int(r['far_end_active'])!=0]; require(far,'far-active rows required')
        median_delay_ms=statistics.median(float(r['estimated_delay_ms']) for r in far)
        delay_samples=int(round(median_delay_ms*48.0)); require(0<=delay_samples<common,'delay geometry')
        subprocess.run([str(coherence_probe),str(mic_path),str(render_path),str(delay_samples),'4608',str(spectral)],check=True)
        sp=load_json(spectral)
    require(sp['diagnostic_only'] is True and sp['sample_rate_hz']==48000 and sp['tail_samples']==4608 and sp['fft_size']==16384,'spectral geometry')
    require(sp['signal_correction_applied'] is False and sp['acoustic_threshold_used'] is False,'spectral authority')
    total=float(sp['total_mic_render_ratio']); coh=float(sp['coherent_mic_render_ratio']); excess=float(sp['incoherent_excess_mic_render_ratio'])
    require(total>=0 and coh>=0 and excess>=-1e-12 and math.isclose(total,coh+excess,rel_tol=1e-9,abs_tol=1e-12),'energy partition identity')
    return {'guid':case['guid'],'activity':activity,'production_sync_delay_ms_median':median_delay_ms,'source_delay_samples':delay_samples,'spectral':sp}

def aggregate(cases:list[dict])->dict:
    dtd=[c['activity']['double_talk_fraction'] for c in cases]; total=[c['spectral']['total_mic_render_ratio'] for c in cases]; coherent=[c['spectral']['coherent_mic_render_ratio'] for c in cases]; excess=[c['spectral']['incoherent_excess_mic_render_ratio'] for c in cases]; coherence=[c['spectral']['mic_energy_weighted_coherence'] for c in cases]; delay=[c['production_sync_delay_ms_median'] for c in cases]
    return {'case_count':len(cases),'cases_with_nonzero_public_dtd':sum(float(v)>0 for v in dtd),'distributions':{'public_dtd_fraction':distribution(dtd),'source_total_mic_render_ratio':distribution(total),'source_coherent_mic_render_ratio':distribution(coherent),'source_incoherent_excess_mic_render_ratio':distribution(excess),'mic_energy_weighted_coherence':distribution(coherence),'production_sync_delay_ms_median':distribution(delay)},'spearman_associations':{'dtd_vs_total_source_ratio':spearman(dtd,total),'dtd_vs_coherent_source_ratio':spearman(dtd,coherent),'dtd_vs_incoherent_excess_source_ratio':spearman(dtd,excess),'dtd_vs_mic_energy_weighted_coherence':spearman(dtd,coherence),'total_vs_coherent_source_ratio':spearman(total,coherent),'total_vs_incoherent_excess_source_ratio':spearman(total,excess),'coherent_vs_incoherent_excess_source_ratio':spearman(coherent,excess)}}

def self_test()->None:
    require(abs(spearman([1,2,3],[4,5,6])['rho']-1.0)<1e-12,'Spearman self-test'); require(distribution([1,2,3])['median']==2.0,'distribution self-test'); print('pure-far source coherent-excess analyzer self-test: OK')

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument('--self-test',action='store_true'); p.add_argument('--manifest',type=Path); p.add_argument('--inventory',type=Path); p.add_argument('--source-root',type=Path); p.add_argument('--provenance-probe',type=Path); p.add_argument('--coherence-probe',type=Path); p.add_argument('--helper',type=Path); p.add_argument('--output',type=Path); a=p.parse_args()
    if a.self_test:self_test(); return 0
    if any(x is None for x in (a.manifest,a.inventory,a.source_root,a.provenance_probe,a.coherence_probe,a.helper,a.output)):p.error('all diagnostic paths required')
    m=load_json(a.manifest); validate_manifest(m); inv=load_json(a.inventory); cases_meta=validate_inventory(inv,m); helper=import_module(a.helper)
    cases=[run_case(c,a.source_root,a.provenance_probe,a.coherence_probe,helper,m) for c in cases_meta]
    payload={'schema_version':1,'investigation_id':m['investigation_id'],'status':'DIAGNOSTIC_ONLY','authority':'research-diagnostic-only','candidate_budget':0,'inventory':{'complete_pair_count':inv['complete_pair_count'],'total_lfs_bytes':inv['total_lfs_bytes'],'selection_fingerprint_sha256':inv['selection_fingerprint_sha256']},'signal_correction_applied':False,'threshold_search_performed':False,'candidate_selection_performed':False,'cases':cases,'aggregate':aggregate(cases),'interpretation_rule':m['interpretation_rule']}
    a.output.mkdir(parents=True,exist_ok=True); write_json(a.output/'pure-far-source-coherent-excess-result.json',payload)
    with (a.output/'summary.md').open('w',encoding='utf-8') as f:
        f.write('## Pure-far source coherent/excess v1\n\n- Authority: `research-diagnostic-only`\n- Candidate budget: `0`\n- Frozen cases: `125`\n- Signal correction / threshold search: `false`\n\n')
        for k,v in sorted(payload['aggregate']['distributions'].items()):f.write(f'- {k}: `{json.dumps(v,sort_keys=True)}`\n')
        f.write('\n### Descriptive Spearman associations\n')
        for k,v in sorted(payload['aggregate']['spearman_associations'].items()):f.write(f'- {k}: `{json.dumps(v,sort_keys=True)}`\n')
    return 0
if __name__=='__main__': raise SystemExit(main())
