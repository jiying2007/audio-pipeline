#!/usr/bin/env python3
"""Fixed recorded-speech / synthetic-free-field BF diagnostics. No promotion."""
from __future__ import annotations
import argparse
import array
import json
import math
import os
from pathlib import Path
import shutil
import struct
import sys
from contracts import ROOT, hex_digest, load_json, require, sha256, verified_file
from libfvad_reference import write_json, run_logged, seal_output
from array_qualification import FLAGS, geometry_text, delays, interpolation_taps
from speech_source import PLAN, flac_info
sys.path.insert(0, str(ROOT / 'validation/tools'))
from run_validation_engine import si_sdr_span

HERE = Path(__file__).resolve().parent
ADMISSION = ROOT / '.github/research/frontend-evolution-v1/speech-admission-v1.json'
N, RATE, EDGE = 64000, 16000, 1600
ARMS = ('reference', 'mean', 'linear', 'lagrange3')
SCENES = ((0, 90), (60, 150), (90, 90))
POSITIONS = {
    'dual70': [[-.035, 0, 0], [.035, 0, 0]],
    'ula4-70': [[-.035, 0, 0], [-.035/3, 0, 0], [.035/3, 0, 0], [.035, 0, 0]],
    'uca4-70': [[-.035, 0, 0], [0, -.035, 0], [.035, 0, 0], [0, .035, 0]],
}
SOURCE_NAMES = ('array_native.c', 'array_native.h', 'array_runner.c', 'speech_render.c',
                'speech_source.py', 'speech_spatial.py', 'contracts.py', 'libfvad_reference.py',
                'array_qualification.py', 'test_speech_spatial.py')


def values(blob: bytes, kind: str, count: int) -> list:
    size = struct.calcsize('<'+kind)
    require(len(blob) == count*size, 'exact PCM cardinality required')
    data = [r[0] for r in struct.iter_unpack('<'+kind, blob)]
    require(all(math.isfinite(x) for x in data), 'non-finite PCM')
    return data


def encode(data: list, kind: str) -> bytes:
    a = array.array(kind, data)
    if sys.byteorder != 'little': a.byteswap()
    return a.tobytes()


def source_check(path: Path) -> dict:
    review = load_json(ADMISSION); record = load_json(path/'source-receipt.json')
    require(review['decision'] == 'ADMITTED_RECORDED_SPEECH_FIXED_DIAGNOSTICS', 'speech is not admitted')
    require(record['plan_sha256'] == sha256(PLAN.read_bytes()), 'data selection plan changed')
    bound = {key: record[key] for key in ('archive_sha256','archive_md5','archive_bytes','speaker_selection')}
    bound['files_sha256'] = {k:v for k,v in record['files_sha256'].items() if k!='decoder-version.txt'}
    digest=sha256(json.dumps(bound,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
    require(digest==review['bound_source_sha256'],'speech source/roles/files differ from independently admitted bytes')
    require(record['shipping_authority'] is False and record['source_id']=='librispeech-dev-clean-fe03' and
            record['url']==load_json(PLAN)['archive_url'] and record['status']=='SOURCE_ONLY_NOT_ACOUSTIC_EVIDENCE', 'source authority changed')
    expected = set(bound['files_sha256']) | {'decoder-version.txt', 'source-receipt.json'}
    actual = {p.relative_to(path).as_posix() for p in path.rglob('*') if p.is_file()}
    require(actual == expected and all(not p.is_symlink() for p in path.rglob('*')), 'source file set mismatch')
    for name, digest in record['files_sha256'].items():
        require(sha256(verified_file(path,name).read_bytes()) == digest, 'source receipt byte mismatch: '+name)
    rows=record['speaker_selection']
    require(len(rows)==8 and len({r['speaker'] for r in rows})==8,'eight unique speakers required')
    for i,r in enumerate(rows):
        require(r['pair_index']==i//2 and r['position']==('target' if i%2==0 else 'interferer'),'speaker pair changed')
        require(r['role']==load_json(PLAN)['roles'][i//2], 'speaker role changed')
        values((path/r['window_file']).read_bytes(), 'h', N)
        for original in r['originals']:
            blob=(path/'flac'/Path(original['member']).name).read_bytes()
            require(flac_info(blob)[3]==original['frames'],'FLAC sample identity mismatch')
    return record


def geometry(name: str, azimuth: int) -> dict:
    p=POSITIONS[name];r=math.radians(azimuth);m=len(p)
    return {'positions_m':p,'direction':[math.cos(r),math.sin(r),0.0], 'sample_rate_hz':RATE,
            'active_mask':(1<<m)-1,'reference_mic':0, 'gains':[1]*m,'latency_samples':[0]*m,'channel_map':list(range(m))}


def all_cases():
    for pair in range(4):
        for name in POSITIONS:
            for target,interferer in SCENES:
                yield f'p{pair}-{name}-{target}-{interferer}',pair,name,target,interferer


def gains(t: list, i: list) -> tuple[float,float]:
    rt=math.sqrt(sum(x*x for x in t)/len(t));ri=math.sqrt(sum(x*x for x in i)/len(i))
    require(min(rt,ri)>0,'zero-energy source; no replacement')
    common=.25/(max(map(abs,t))/rt+max(map(abs,i))/ri)
    return common/rt, common/ri


def sinc_taps(advance: float) -> list[tuple[int,float]]:
    base=math.floor(advance);taps=[]
    for k in range(base-31,base+32):
        x=advance-k
        sinc=1.0 if abs(x)<1e-14 else math.sin(math.pi*x)/(math.pi*x)
        window=.5*(1+math.cos(math.pi*x/32.0)) if abs(x)<=32 else 0.0
        taps.append((k,sinc*window))
    total=sum(w for _,w in taps)
    return [(k,w/total) for k,w in taps]


def render_config(g:dict, gain:float) -> bytes:
    _,d=delays(g);latency,_=delays(g)
    advances=[x-latency for x in d]
    return (f'{len(d)} {gain:.17g}\n'+' '.join(f'{x:.17g}' for x in advances)+'\n').encode()


def energy(data:list) -> float:
    return sum(float(x)*float(x) for x in data)


def metrics(tref:list, iref:list, yt:list, yi:list, ym:list, latency:int) -> dict:
    require(len(tref)==len(iref)==len(yt)==len(yi)==len(ym)==N,'metric length mismatch')
    count=N-2*EDGE-5  # All three 70mm-aperture geometries have common delay 5.
    t=tref[EDGE:EDGE+count];i=iref[EDGE:EDGE+count]
    ot=yt[EDGE+latency:EDGE+latency+count];oi=yi[EDGE+latency:EDGE+latency+count]
    require(min(energy(t),energy(i),energy(ot),energy(oi))>1e-12,'undefined component metric')
    ratio=lambda a,b:10*math.log10(a/b)
    residual=max(abs(a-b-c) for a,b,c in zip(ym,yt,yi))
    require(residual<=2e-6,'linear component decomposition failed')
    score=si_sdr_span(tref,ym,EDGE,EDGE+latency,count)
    require(score is not None and math.isfinite(score),'undefined canonical SI-SDR')
    input_sir=ratio(energy(t),energy(i));out_sir=ratio(energy(ot),energy(oi))
    error=energy([a-b for a,b in zip(ot,t)])/energy(t)
    return {'evaluated_samples':count,'input_component_sir_db':input_sir,'output_component_sir_db':out_sir,
            'component_sir_gain_db':out_sir-input_sir,'interferer_attenuation_db':ratio(energy(i),energy(oi)),
            'target_gain_db':ratio(energy(ot),energy(t)), 'target_relative_error_energy':error,
            'canonical_si_sdr_db':score,'maximum_decomposition_error':residual,
            'output_peak':max(map(abs,ym)), 'output_outside_s16_range':sum(v < -1 or v >= 1 for v in ym)}


def build(root:Path) -> dict:
    commands=[]
    for name,sources in [('renderer',['speech_render.c']),('array',['array_native.c','array_runner.c'])]:
        command=['gcc',*FLAGS,*[str(HERE/s) for s in sources],'-lm','-o',str(root/name)]
        run_logged(command,root/(name+'-build.log'));commands.append(command)
    run_logged(['gcc','--version'],root/'compiler.txt')
    write_json(root/'build.json',{'commands':commands,'native_only':True,'runner_image':os.environ.get('ImageVersion','LOCAL_UNSPECIFIED')})
    return {name:sha256((root/name).read_bytes()) for name in ('renderer','array')}


def run(data:Path, root:Path, revision:str) -> dict:
    require(hex_digest(revision,40) and not root.exists(),'fresh output and exact revision required')
    source=source_check(data);plan=load_json(PLAN)
    root.mkdir(parents=True);shutil.copytree(data,root/'data')
    shutil.copyfile(PLAN,root/'experiment.json');shutil.copyfile(ADMISSION,root/'admission.json')
    (root/'source').mkdir()
    for name in SOURCE_NAMES:shutil.copyfile(HERE/name,root/'source'/name)
    shutil.copyfile(ROOT/'validation/tools/run_validation_engine.py',root/'source/run_validation_engine.py')
    binaries=build(root);rows=[];speakers=source['speaker_selection']
    for key,pair,name,target,interferer in all_cases():
        d=root/'cases'/key;d.mkdir(parents=True)
        m=len(POSITIONS[name]);g=geometry(name,target);latency,_=delays(g);require(latency==5,'unexpected common delay')
        source_t=root/'data'/speakers[2*pair]['window_file'];source_i=root/'data'/speakers[2*pair+1]['window_file']
        original_t=[x/32768.0 for x in values(source_t.read_bytes(),'h',N)]
        original_i=[x/32768.0 for x in values(source_i.read_bytes(),'h',N)]
        gt,gi=gains(original_t,original_i);rendered={}
        for tag,src,gain,az in [('target',source_t,gt,target),('interferer',source_i,gi,interferer)]:
            cfg=d/(tag+'-render.txt');cfg.write_bytes(render_config(geometry(name,az),gain))
            out=d/(tag+'.f64');run_logged([root/'renderer',cfg,src,out],d/(tag+'-render.log'))
            blob=out.read_bytes();f=values(blob,'d',N*m)
            q=[round(x*32768) for x in f];require(all(abs(v)<32760 for v in q),'render clipping; no hidden rescale')
            (d/(tag+'.s16')).write_bytes(encode(q,'h'));rendered[tag]=q;out.unlink()
        mix=[a+b for a,b in zip(rendered['target'],rendered['interferer'])]
        require(all(abs(v)<32760 for v in mix),'mixture clipping; no hidden rescale')
        (d/'mixture.s16').write_bytes(encode(mix,'h'));rendered['mixture']=mix
        case={'case_id':key,'pair':pair,'role':plan['roles'][pair],'geometry':name,'target_degrees':target,
              'interferer_degrees':interferer,'gains':[gt,gi],
              'input_peak':max(map(abs,mix))/32768.0,'arms':{}}
        tref=[v/32768.0 for v in rendered['target'][::m]];iref=[v/32768.0 for v in rendered['interferer'][::m]]
        for arm in ARMS:
            output={};dest=d/arm;dest.mkdir()
            if arm in ('linear','lagrange3'):(dest/'geometry.txt').write_bytes(geometry_text(g,arm))
            for tag,pcm in rendered.items():
                if arm in ('reference','mean'):
                    y=[v/32768.0 for v in pcm[::m]] if arm=='reference' else [sum(pcm[j:j+m])/(32768.0*m) for j in range(0,len(pcm),m)]
                    blob=encode(y,'f');(dest/(tag+'.f32')).write_bytes(blob)
                else:
                    run_logged([root/'array',dest/'geometry.txt',d/(tag+'.s16'),dest/(tag+'.f32'),dest/(tag+'.json')],dest/(tag+'.log'))
                    blob=(dest/(tag+'.f32')).read_bytes()
                output[tag]=values(blob,'f',N)
            if arm in ('linear','lagrange3'):
                run_logged([root/'array',dest/'geometry.txt',d/'mixture.s16',dest/'repeat.f32',dest/'repeat.json'],dest/'repeat.log')
                require((dest/'repeat.f32').read_bytes()==(dest/'mixture.f32').read_bytes(),'recorded-speech BF repeat mismatch')
            delay=latency if arm in ('linear','lagrange3') else 0
            case['arms'][arm]={'delay_samples':delay, **metrics(tref,iref,output['target'],output['interferer'],output['mixture'],delay)}
        rows.append(case)
    report={'schema_version':1,'experiment_id':plan['experiment_id'],'execution_source_revision':revision,
            'decision':plan['decision'],'status':'RECORDED_SPEECH_FIXED_DIAGNOSTIC_COMPLETE','shipping_authority':False,
            'native_only':True,'oracle_directions':True,'real_array_recording':False,'binaries':binaries,
            'cases':rows,'summary':summaries(rows)}
    write_json(root/'result.json',report);seal_output(root,report)
    return verify(root,revision)


def summaries(rows:list) -> list:
    result=[]
    for role in ('development-diagnostic','speaker-disjoint-confirmation-diagnostic'):
        for name in POSITIONS:
            for arm in ARMS:
                group=[r['arms'][arm] for r in rows if r['role']==role and r['geometry']==name]
                result.append({'role':role,'geometry':name,'arm':arm,'speaker_pairs':2,'cases':len(group),
                               **{metric:{'mean':sum(x[metric] for x in group)/len(group),'minimum':min(x[metric] for x in group),'maximum':max(x[metric] for x in group)}
                                  for metric in ('component_sir_gain_db','target_gain_db','canonical_si_sdr_db')}})
    return result


def verify(root:Path, revision:str|None=None) -> dict:
    require(not (root/'failure.json').exists(),'failed experiment')
    require(all(not p.is_symlink() for p in root.rglob('*')),'symlink evidence')
    actual={p.relative_to(root).as_posix():sha256(p.read_bytes()) for p in root.rglob('*')
            if p.is_file() and p.relative_to(root).as_posix() not in ('manifest.json','SHA256SUMS')}
    manifest=load_json(root/'manifest.json');require(manifest['files']==actual and manifest['shipping_authority'] is False,'manifest identity')
    lines=(root/'SHA256SUMS').read_text().splitlines();sums={}
    for line in lines:
        digest,name=line.split('  ',1);require(name not in sums,'duplicate checksum');sums[name]=digest
    require(sums=={**actual,'manifest.json':sha256((root/'manifest.json').read_bytes())},'checksums changed')
    require(load_json(root/'experiment.json')==load_json(PLAN),'plan changed')
    require((root/'admission.json').read_bytes()==ADMISSION.read_bytes(),'admission changed')
    source=source_check(root/'data')
    for name in SOURCE_NAMES:require((root/'source'/name).read_bytes()==(HERE/name).read_bytes(),'source changed: '+name)
    require((root/'source/run_validation_engine.py').read_bytes()==(ROOT/'validation/tools/run_validation_engine.py').read_bytes(),'canonical evaluator drift')
    report=load_json(root/'result.json');plan=load_json(PLAN)
    require(report['decision']==plan['decision'] and report['shipping_authority'] is False and report['oracle_directions'] is True
            and report['real_array_recording'] is False and report['native_only'] is True,'authority changed')
    require(report['experiment_id']==manifest['experiment_id']==plan['experiment_id'],'experiment mismatch')
    require(report['status']=='RECORDED_SPEECH_FIXED_DIAGNOSTIC_COMPLETE' and hex_digest(report['execution_source_revision'],40),'status/revision')
    if revision is not None:require(report['execution_source_revision']==revision,'wrong execution source')
    require(set(report['binaries'])=={'array','renderer'},'binary set')
    for name,digest in report['binaries'].items():
        b=(root/name).read_bytes();require(sha256(b)==digest and b[:6]==b'\x7fELF\x02\x01','native ELF identity')
    rows={r['case_id']:r for r in report['cases']}
    require(len(rows)==len(report['cases'])==36 and set(rows)=={c[0] for c in all_cases()},'partial/duplicate cases')
    for key,pair,name,target,interferer in all_cases():
        row=rows[key];d=root/'cases'/key;m=len(POSITIONS[name]);g=geometry(name,target)
        require((row['pair'],row['role'],row['geometry'],row['target_degrees'],row['interferer_degrees'])==
                (pair,plan['roles'][pair],name,target,interferer),'case identity changed')
        require(set(row['arms'])==set(ARMS),'missing arm')
        originals=[values((root/'data'/source['speaker_selection'][2*pair+j]['window_file']).read_bytes(),'h',N) for j in (0,1)]
        expected_gains=gains(*[[v/32768.0 for v in x] for x in originals]);require(row['gains']==list(expected_gains),'gain changed')
        raw={tag:values((d/(tag+'.s16')).read_bytes(),'h',N*m) for tag in ('target','interferer','mixture')}
        require(raw['mixture']==[a+b for a,b in zip(raw['target'],raw['interferer'])],'input components do not sum')
        require(row['input_peak']==max(map(abs,raw['mixture']))/32768.0 and max(map(abs,raw['mixture']))<32760,'clipped input')
        for j,tag in enumerate(('target','interferer')):
            sg=geometry(name,(target,interferer)[j]);cfg=render_config(sg,expected_gains[j]);require((d/(tag+'-render.txt')).read_bytes()==cfg,'render config changed')
            _,comp=delays(sg);advances=[x-5 for x in comp]
            # Predeclared finite source-render checks, not a claim of full independent sinc recomputation.
            for mic,advance in enumerate(advances):
                taps=sinc_taps(advance)
                for sample in range(1600,N-1600,251):
                    exact=sum(w*originals[j][sample+k]/32768.0*expected_gains[j] for k,w in taps if 0<=sample+k<N)
                    require(abs(raw[tag][sample*m+mic]-round(exact*32768))<=1,'recorded source/geometry rendering mismatch')
        tref=[v/32768.0 for v in raw['target'][::m]];iref=[v/32768.0 for v in raw['interferer'][::m]]
        for arm in ARMS:
            dest=d/arm;output={tag:values((dest/(tag+'.f32')).read_bytes(),'f',N) for tag in raw}
            delay=5 if arm in ('linear','lagrange3') else 0
            if arm in ('linear','lagrange3'):
                require((dest/'geometry.txt').read_bytes()==geometry_text(g,arm),'BF config changed')
                require((dest/'repeat.f32').read_bytes()==(dest/'mixture.f32').read_bytes(),'BF recorded repeat changed')
                require(load_json(dest/'repeat.json')==load_json(dest/'mixture.json'),'BF repeat metadata changed')
                _,comp=delays(g)
                for tag,y in output.items():
                    meta=load_json(dest/(tag+'.json'))
                    require(meta['status']=='PASS' and meta['samples_processed']==N and meta['mic_count']==m and
                            meta['common_delay_samples']==5 and meta['sample_rate_hz']==RATE and meta['active_mask']==(1<<m)-1 and
                            meta['output_encoding']=='f32le-unclipped' and meta['direction']==g['direction'] and meta['interpolation']==('linear','lagrange3').index(arm) and
                            len(meta['compensation_samples'])==m and max(abs(a-b) for a,b in zip(meta['compensation_samples'],comp))<=1e-10 and meta['shipping_authority'] is False and meta['steering_accepted']==0,'BF receipt mismatch')
                    for sample in range(1600,N-1600,251):
                        expected=sum(sum(w*raw[tag][(sample-k)*m+mic]/32768.0 for k,w in interpolation_taps(comp[mic],arm)) for mic in range(m))/m
                        require(abs(y[sample]-expected)<=2e-6,'BF finite oracle mismatch')
            else:
                for tag,y in output.items():
                    expected=[v/32768.0 for v in raw[tag][::m]] if arm=='reference' else [sum(raw[tag][k:k+m])/(32768.0*m) for k in range(0,N*m,m)]
                    require((dest/(tag+'.f32')).read_bytes()==encode(expected,'f'),'reference/mean changed')
            expected_metrics={'delay_samples':delay,**metrics(tref,iref,output['target'],output['interferer'],output['mixture'],delay)}
            require(row['arms'][arm]==expected_metrics,'canonical/component metric mismatch')
    require(report['summary']==summaries(report['cases']),'summary changed')
    return {'status':'VERIFIED_RECORDED_SPEECH_DIAGNOSTICS','files':len(actual),'cases':36,'arm_outputs':144,
            'speaker_pairs':4,'shipping_authority':False,'decision':report['decision']}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--execution-source');p.add_argument('--verify',action='store_true');a=p.parse_args()
    output_existed=a.output.exists()
    try:
        result=verify(a.output,a.execution_source) if a.verify else run(a.source,a.output,a.execution_source)
        print(json.dumps(result,sort_keys=True))
    except Exception as error:
        if not a.verify and not output_existed and a.output.exists():write_json(a.output/'failure.json',{'error':str(error),'shipping_authority':False})
        raise
