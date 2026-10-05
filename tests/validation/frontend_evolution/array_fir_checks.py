"""FIR known answers extending the ONE native-array qualifier (no acoustic gate)."""
from __future__ import annotations
import cmath
import copy
import math
from pathlib import Path
import struct
import unittest
from contracts import ROOT, load_json, require, sha256
from libfvad_reference import run_logged
from array_qualification import PLAN as OLD_PLAN, FLAGS, delays, geometry_text, make_input
from array_steering_checks import read_floats

PLAN = ROOT/'.github/research/frontend-evolution-v1/array-fir-v1.json'
HERE = Path(__file__).resolve().parent
MODES = {'fir17': 2, 'fir33': 3}
RADII = {'fir17': 8, 'fir33': 16}


def config_text(g, mode):
    lines=geometry_text(g,'linear').decode().splitlines()
    head=lines[0].split();head[3]=str(MODES[mode]);lines[0]=' '.join(head)
    return ('\n'.join(lines)+'\n').encode()


def taps(delay, radius):
    """Double precision direct mathematical reference, not stored C coefficients."""
    m=math.floor(delay); f=delay-m
    if f==0.0:return [(k,1.0 if k==m else 0.0) for k in range(m-radius,m+radius+1)]
    pairs=[]
    for k in range(m-radius,m+radius+1):
        distance=k-delay
        value=math.sin(math.pi*distance)/(math.pi*distance)
        value*=math.sin(math.pi*(k-m+radius)/(2*radius))**2
        pairs.append((k,value))
    total=math.fsum(w for _,w in pairs)
    return [(k,w/total) for k,w in pairs]


def oracle(data,g,mode):
    n=len(g['positions_m']);x=[a[0]/32768 for a in struct.iter_unpack('<h',data)]
    common,d=delays(g); radius=RADII[mode]
    kernels=[taps(delay+radius,radius) for delay in d]
    active=[i for i in range(n) if g['active_mask']&(1<<i)]
    out=[0.0]*(len(x)//n)
    # Tap-major convolution is structurally independent of the C sample/ring loop.
    for i in active:
        for at,w in kernels[i]:
            for j in range(at,len(out)):
                out[j]+=g['gains'][i]*w*x[(j-at)*n+g['channel_map'][i]]/len(active)
    return common+radius,out


def cases(plan):
    geometries={g['id']:g for g in load_json(OLD_PLAN)['geometries']}
    for name in plan['geometries']:
        for mode in MODES:
            for pattern in plan['patterns']:
                yield f'{name}-{mode}-{pattern}',geometries[name],mode,pattern


def commands(plan):
    return ('FE_STEERING_V1 1\n'+' '.join(map(str,[plan['transition_sample'],plan['transition_samples'],*plan['target_direction']]))+'\n').encode()


def expected(data,g,mode,plan,steer=False):
    delay,old=oracle(data,g,mode)
    if not steer:return delay,old
    other=copy.deepcopy(g);other['direction']=plan['target_direction'];_,new=oracle(data,other,mode)
    for j in range(plan['transition_sample'],len(old)):
        alpha=min(1.0,(j-plan['transition_sample'])/(plan['transition_samples']-1))
        old[j]=(1-alpha)*old[j]+alpha*new[j]
    return delay,old


def execute(binary,prefix,cfg,pcm,dest,cmd=None,chunk=None):
    argv=[*prefix,binary,cfg,pcm,dest.with_suffix('.f32'),dest.with_suffix('.json')]
    if cmd is not None:argv.extend([cmd,str(chunk or 480)])
    run_logged(argv,dest.with_suffix('.log'))


def response(data,plan):
    # Actual C impulse output amplitude .5 at sample 64; phase includes that offset.
    return [{'frequency_hz':freq,'magnitude_db':20*math.log10(max(abs(sum(v*cmath.exp(-2j*math.pi*freq*j/16000) for j,v in enumerate(data)))*2,1e-30))}
            for freq in plan['frequency_hz']]


def run(root,targets):
    p=load_json(PLAN);d=root/'fir';d.mkdir();(d/'experiment.json').write_bytes(PLAN.read_bytes())
    record={'experiment_id':p['experiment_id'],'decision':p['decision'],'shipping_authority':False,
            'acoustic_improvement_proved':False,'cases':[],'responses':[],'unit_binaries':{}}
    # Use the same architecture set as the existing mandatory native-array gate.
    for arch,binary,prefix in [*targets,('sanitized',None,[])]:
        compiler='arm-linux-gnueabihf-gcc' if arch=='arm' else 'cc'
        flags=['-mcpu=cortex-a32','-mfpu=neon-fp-armv8','-mfloat-abi=hard'] if arch=='arm' else []
        if arch=='sanitized':flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-pie','-no-pie']
        dest=d/('unit-'+arch)
        run_logged([compiler,*FLAGS,*flags,HERE/'array_native.c',HERE/'array_fir_test.c','-lm','-o',dest],d/('build-'+arch+'.log'))
        run_logged([*prefix,dest],d/('unit-'+arch+'.json'),timeout=180)
        record['unit_binaries'][arch]=sha256(dest.read_bytes())
    # CPU is explicitly host process CPU, not QEMU/DUT timing. Retain raw one-pass data.
    run_logged([d/'unit-native','--benchmark'],d/'host-cpu.json',timeout=120)
    for key,g,mode,pattern in cases(p):
        sub=d/key;sub.mkdir();data=make_input(g,pattern,p['frames_per_case'])
        (sub/'input.pcm').write_bytes(data);(sub/'geometry.txt').write_bytes(config_text(g,mode))
        (sub/'commands.txt').write_bytes(commands(p));cut=p['prefix_frames']*len(g['positions_m'])*2
        (sub/'future.pcm').write_bytes(data[:cut]+bytes(v^0x5a for v in data[cut:]))
        refs={kind:expected(data,g,mode,p,kind=='steer') for kind in ('static','steer')}
        for arch,binary,prefix in targets:
            for kind in ('static','steer','repeat','chunk','future'):
                execute(binary,prefix,sub/'geometry.txt',sub/('future.pcm' if kind=='future' else 'input.pcm'),
                        sub/(arch+'-'+kind),sub/'commands.txt' if kind!='static' else None,
                        p['alternate_chunk_samples'] if kind=='chunk' else 480)
            for kind,(delay,ref) in refs.items():
                actual=read_floats(sub/f'{arch}-{kind}.f32',len(ref));error=max(abs(a-b) for a,b in zip(actual,ref))
                require(error<=p['maximum_absolute_oracle_error'],'FIR numerical mismatch')
                record['cases'].append({'case_id':key,'target':arch,'kind':kind,'delay_samples':delay,'maximum_absolute_oracle_error':error})
    for mode in MODES:
        for fraction in p['frequency_fractions']:
            key=f'probe-{mode}-{fraction}';sub=d/key;sub.mkdir()
            g={'positions_m':[[0,0,0]],'sample_rate_hz':16000,'reference_mic':0,'active_mask':1,'direction':[1,0,0],
               'gains':[1.0],'latency_samples':[1-fraction],'channel_map':[0]}
            data=struct.pack('<'+'h'*320,*([0]*64+[16384]+[0]*255))
            (sub/'geometry.txt').write_bytes(config_text(g,mode));(sub/'input.pcm').write_bytes(data)
            for arch,binary,prefix in targets:
                execute(binary,prefix,sub/'geometry.txt',sub/'input.pcm',sub/arch)
                actual=read_floats(sub/f'{arch}.f32',320)
                record['responses'].append({'case_id':key,'target':arch,'mode':mode,'fraction':fraction,'response':response(actual,p)})
    return record


def verify(root,record,targets):
    p=load_json(PLAN);d=root/'fir'
    require(load_json(d/'experiment.json')==p,'FIR plan changed')
    require(record['experiment_id']==p['experiment_id'] and record['decision']==p['decision'] and
            record['shipping_authority'] is False and record['acoustic_improvement_proved'] is False,'FIR authority changed')
    require(set(record['unit_binaries'])==set([*targets,'sanitized']),'FIR unit target missing')
    for arch in [*targets,'sanitized']:
        blob=(d/('unit-'+arch)).read_bytes();require(sha256(blob)==record['unit_binaries'][arch] and blob[:4]==b'\x7fELF','FIR unit binary')
        unit=load_json(d/('unit-'+arch+'.json'))
        require(unit['status']=='PASS' and unit['configurations']==30 and unit['stress_frames']==8192 and unit['lifecycles']==32 and unit['assertions']>100000,'FIR C contracts incomplete')
        require(unit['state_bytes_4mic']==[2648,3192,3704],'FIR explicit memory changed')
    host=load_json(d/'host-cpu.json')
    require(host['authority']=='HOST_CPU_ONLY_NOT_DUT' and host['audio_seconds_per_arm']==40.96 and len(host['arms'])==3,'host performance identity')
    require([a['mode'] for a in host['arms']]==[1,2,3] and all(math.isfinite(a['cpu_ms_per_audio_second']) and a['cpu_ms_per_audio_second']>=0 for a in host['arms']),'host timing malformed')
    rows={(r['case_id'],r['target'],r['kind']):r for r in record['cases']}
    keys={(key,t,kind) for key,*_ in cases(p) for t in targets for kind in ('static','steer')}
    require(set(rows)==keys and len(rows)==len(record['cases']),'FIR missing/duplicate cases')
    for key,g,mode,pattern in cases(p):
        sub=d/key;data=make_input(g,pattern,p['frames_per_case']);cut=p['prefix_frames']*len(g['positions_m'])*2
        require((sub/'input.pcm').read_bytes()==data and (sub/'geometry.txt').read_bytes()==config_text(g,mode) and (sub/'commands.txt').read_bytes()==commands(p),'FIR input/config/command changed')
        require((sub/'future.pcm').read_bytes()==data[:cut]+bytes(v^0x5a for v in data[cut:]),'FIR future fixture')
        for kind in ('static','steer'):
            delay,ref=expected(data,g,mode,p,kind=='steer')
            for arch in targets:
                values=read_floats(sub/f'{arch}-{kind}.f32',len(ref));error=max(abs(a-b) for a,b in zip(values,ref))
                row=rows[key,arch,kind];require(row['delay_samples']==delay and row['maximum_absolute_oracle_error']==error and error<=p['maximum_absolute_oracle_error'],'FIR oracle changed')
                meta=load_json(sub/f'{arch}-{kind}.json')
                require(meta['common_delay_samples']==delay and meta['interpolation']==MODES[mode] and meta['samples_processed']==len(ref) and meta['mic_count']==len(g['positions_m']) and meta['active_mask']==g['active_mask'] and meta['shipping_authority'] is False,'FIR metadata changed')
                require(meta['state_bytes']<=p['maximum_state_bytes'],'FIR memory budget')
                if kind=='steer':
                    require(meta['steering_completed']==1 and meta['transition_remaining_samples']==0 and meta['direction']==p['target_direction'],'FIR transition incomplete')
                    blob=(sub/f'{arch}-steer.f32').read_bytes()
                    require(all((sub/f'{arch}-{suffix}.f32').read_bytes()==blob for suffix in ('repeat','chunk')),'FIR repeat/chunk changed')
                    alt=(sub/f'{arch}-future.f32').read_bytes()
                    require(len(alt)==len(blob) and alt[:p['prefix_frames']*4]==blob[:p['prefix_frames']*4],'FIR future dependency')
    responses={(r['mode'],r['fraction'],r['target']):r for r in record['responses']}
    require(len(responses)==len(record['responses']) and set(responses)=={(m,f,a) for m in MODES for f in p['frequency_fractions'] for a in targets},'FIR impulse probes missing')
    for (mode,fraction,arch),row in responses.items():
        sub=d/row['case_id'];g={'positions_m':[[0,0,0]],'sample_rate_hz':16000,'reference_mic':0,'active_mask':1,'direction':[1,0,0],
             'gains':[1.0],'latency_samples':[1-fraction],'channel_map':[0]}
        data=struct.pack('<'+'h'*320,*([0]*64+[16384]+[0]*255))
        require(row['case_id']==f'probe-{mode}-{fraction}' and (sub/'geometry.txt').read_bytes()==config_text(g,mode) and (sub/'input.pcm').read_bytes()==data,'FIR probe identity')
        _,ref=oracle(data,g,mode);actual=read_floats(sub/f'{arch}.f32',320)
        require(max(abs(a-b) for a,b in zip(ref,actual))<=p['maximum_absolute_oracle_error'] and row['response']==response(actual,p),'FIR response changed')
    return len(rows)


class FIROracleTests(unittest.TestCase):
    def test_integer_identity(self):
        for r in RADII.values():self.assertEqual(dict(taps(r+3,r))[r+3],1.0)
    def test_dc(self):
        for r in RADII.values():
            for f in (0,.001,.125,.5,.875,.999):self.assertAlmostEqual(sum(w for _,w in taps(r+3+f,r)),1,places=12)
    def test_causal_range(self):
        for _,g,m,_ in cases(load_json(PLAN)):
            common,d=delays(g);r=RADII[m]
            for delay in d:
                self.assertGreaterEqual(min(k for k,_ in taps(delay+r,r)),0)
                self.assertLess(max(k for k,_ in taps(delay+r,r)),128)
    def test_frozen_structures(self):
        self.assertEqual(load_json(PLAN)['modes'],MODES);self.assertEqual(load_json(PLAN)['radii'],RADII)
