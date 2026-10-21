"""D23 same-input full-reset benefit and false-event cost diagnostic."""
from __future__ import annotations
import argparse
import math
from pathlib import Path
import subprocess
import sys

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.codex_assets.device_capture import ROOT, bounded, require, sha, strict_json
from tools.codex_assets.device_exact_reference import dump, logged, read_json
from tools.codex_assets.device_multipath import preflight as d22_preflight, measure, TRACES
from tools.codex_assets.device_replay import FLAGS
from tools.codex_assets.device_stages import D18

BASE = Path('/tmp/audio-fe-device-multipath-d22-20261011')
BASE_HASHES = {'result.json':'96c7e749eac0e435b28e9f0ffdfe4d7985adc2e7bc7e4c45b8b25ac5ac77dd78',
               'binding.json':'fdcd9b3e4ead2e3d7767a30a1eacaefdcad8c6fe9f64e7ca88a505e48b727a19'}
PLAN = ROOT/'docs/research/frontend-evolution-v1/DEVICE_RESET_D23_PLAN.zh-CN.md'
RUNNER = ROOT/'tests/validation/frontend_evolution/device_reset_d23.c'
CASES = [(f'{shape}-r{offset}-{policy}',shape,offset,'normal',policy)
         for shape in ('A','B','switch') for offset in (16,20) for policy in ('keep','reset')] + [
         (mode,'A',16,mode,'reset') for mode in ('disabled','hold','zero')] + [
         ('repeat','switch',20,'normal','reset'),('future','switch',20,'future','reset')]


def preflight(root):
    d22_preflight(root)
    for name,expected in BASE_HASHES.items():
        require(sha(bounded(BASE/name,4*1024*1024)) == expected,'D22 dependency drift')
    binding = read_json(BASE/'binding.json')
    for name,expected in binding['source_files'].items():
        require(sha(bounded(Path(name),4*1024*1024)) == expected,'D22 source drift')
    for name,expected in binding['artifacts'].items():
        require(sha(bounded(BASE/name,4*1024*1024)) == expected,'D22 artifact drift')
    require(sha(bounded(BASE/'runner',4*1024*1024)) == binding['runner_sha256'],'D22 runner drift')


def difference(a,b):
    return {key:b[key]-a[key] for key in ('residual_rms_dbfs','known_echo_erle_db')}


def verify_summary(summary,policy,mode):
    require(set(summary) == {'frames','samples','sync_calls','reset_calls','reset_frame','reset_pre_weight_l2',
                            'reset_post_weight_l2','reset_post_x_power_total','reset_post_steady_frames','reset_post_x_head'},'summary schema')
    require(all(type(summary[key]) is int for key in ('frames','samples','sync_calls','reset_calls')),'summary integer types')
    require(summary['frames'] == 2000 and summary['samples'] == 320000 and summary['sync_calls'] == 0,'execution summary')
    require(summary['reset_calls'] == (1 if policy == 'reset' else 0),'reset count')
    fields = ('reset_frame','reset_pre_weight_l2','reset_post_weight_l2','reset_post_x_power_total','reset_post_steady_frames','reset_post_x_head')
    if policy == 'keep':
        require(all(summary[key] is None for key in fields),'keep reset observations')
    else:
        require(all(type(summary[key]) is int for key in ('reset_frame','reset_post_steady_frames','reset_post_x_head')),'reset integer types')
        require(all(type(summary[key]) in (int,float) and math.isfinite(summary[key])
                    for key in ('reset_pre_weight_l2','reset_post_weight_l2','reset_post_x_power_total')),'reset numeric types')
        require(summary['reset_frame'] == 1000 and summary['reset_post_weight_l2'] == 0 and summary['reset_post_x_power_total'] == 0 and
                summary['reset_post_steady_frames'] == 0 and summary['reset_post_x_head'] == 47,'reset returned state')
        weight = summary['reset_pre_weight_l2']
        require(isinstance(weight,(int,float)) and math.isfinite(weight) and weight >= 0,'pre-reset weight')
        require(weight == 0 if mode in ('disabled','hold','zero') else weight > 0,'pre-reset control weight')


def run(root,output,created):
    preflight(root)
    require(not output.exists() and not output.is_symlink() and Path('/tmp') in output.resolve().parents,'new /tmp output required')
    sources = [Path(__file__).resolve(),PLAN,RUNNER,*[Path(p) for p in read_json(BASE/'binding.json')['source_files']]]
    initial = {str(f):sha(bounded(f,4*1024*1024)) for f in sources}
    output.mkdir(); created.append(output)
    flags = D18/'build/CMakeFiles/audio_pipeline.dir/flags.make'
    definitions = [line.split('=',1)[1].split() for line in flags.read_text().splitlines() if line.startswith('C_DEFINES =')]
    require(len(definitions) == 1 and definitions[0] and all(v.startswith('-DAP_BUILD_') for v in definitions[0]),'build definitions')
    logged(output,'compile',['cc',*FLAGS,'-ffp-contract=off',*definitions[0],'-I',str(D18/'source/src'),'-I',str(D18/'source/include'),
           '-I',str(D18/'build/generated'),str(RUNNER),str(D18/'build/libaudio_pipeline.a'),'-lm','-lpthread','-o',str(output/'runner')],ROOT)
    executable_hash = sha((output/'runner').read_bytes())
    logged(output,'invalid',[str(output/'runner'),'invalid'],ROOT,expected=2)
    cases = []
    for name,shape,offset,mode,policy in CASES:
        directory=output/name; directory.mkdir()
        summary=strict_json(logged(output,name,[str(output/'runner'),shape,str(offset),mode,str(directory),policy],ROOT).encode())
        verify_summary(summary,policy,mode)
        cases.append(dict(name=name,path_shape=shape,reference_offset=offset,mode=mode,policy=policy,execution_summary=summary,
                          measurement=measure(directory,shape,offset,mode)))
    names=[n+'.f32le' for n in TRACES]+['state.csv']
    records={c['name']:c['measurement'] for c in cases}
    pairs=[]
    for shape in ('A','B','switch'):
        for offset in (16,20):
            prefix=f'{shape}-r{offset}'
            for name in names:
                keep=(output/(prefix+'-keep')/name).read_bytes()
                reset=(output/(prefix+'-reset')/name).read_bytes()
                require(keep == (BASE/prefix/name).read_bytes(),'D22 keep equivalence')
                require(keep[:640000] == reset[:640000] if name.endswith('.f32le') else
                        keep.splitlines()[:1001] == reset.splitlines()[:1001],'reset prefix equivalence')
                if name in ('mic.f32le','reference.f32le'):
                    require(keep == reset,'paired inputs')
            a,b=records[prefix+'-keep'],records[prefix+'-reset']
            pairs.append(dict(path_shape=shape,reference_offset=offset,whole=difference(a['whole'],b['whole']),
                         windows=[dict(seconds=x['seconds'],**difference(x,y)) for x,y in zip(a['windows'],b['windows'])]))
    for name in names:
        original=(output/'switch-r20-reset'/name).read_bytes()
        require(original == (output/'repeat'/name).read_bytes(),'repeat equivalence')
        future=(output/'future'/name).read_bytes()
        require(original[:640000] == future[:640000] if name.endswith('.f32le') else
                original.splitlines()[:1001] == future.splitlines()[:1001],'future prefix causality')
    preflight(root)
    require(initial == {str(f):sha(bounded(f,4*1024*1024)) for f in sources} and executable_hash == sha((output/'runner').read_bytes()),'experiment identity drift')
    dump(output/'result.json',dict(experiment='FE_DEVICE_RESET_D23',decision='RESET_BENEFIT_FALSE_EVENT_COST_DIAGNOSTIC_NO_PROMOTION',
         data_role='synthetic-engineering',executions=17,promotion_allowed=False,shipping_approved=False,algorithm_changed=False,
         operation='original_full_reset_before_frame_1000',cases=cases,reset_minus_keep=pairs))
    dump(output/'binding.json',dict(source_files=initial,runner_sha256=executable_hash,d22_hashes=BASE_HASHES,
         source_start_end_equal=True,input_start_end_equal=True,library_sha256=initial[str(D18/'build/libaudio_pipeline.a')],
         artifacts={str(f.relative_to(output)):sha(f.read_bytes()) for f in sorted(output.rglob('*')) if f.is_file()}))
    print('D23_RESET_PASS 17 executions',flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True); parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args(argv); created=[]
    try:
        if args.dry_run:
            preflight(args.root); print('D23_PREFLIGHT_PASS 17 registered executions; writes=False')
        else: run(args.root,args.output,created)
        return 0
    except (ValueError,OSError,KeyError,TypeError,subprocess.TimeoutExpired) as error:
        if created == [args.output]: dump(args.output/'measurement-invalid.json',dict(decision='MEASUREMENT_INVALID',error=str(error)))
        print('device_reset: '+str(error),file=sys.stderr); return 2


if __name__ == '__main__':
    raise SystemExit(main())
