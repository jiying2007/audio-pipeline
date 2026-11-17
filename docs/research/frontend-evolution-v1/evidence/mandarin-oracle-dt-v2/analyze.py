import ast,csv,hashlib,json,math,pathlib,struct,time,zipfile
P=pathlib.Path(__file__).parent;start=time.monotonic();plan=json.loads((P/'PLAN.json').read_text());assert not (P/'analysis.json').exists()
execution=json.loads((P/'execution.json').read_text());assert execution['status']=='BASELINE_EXACT_CANDIDATE_EXECUTED' and execution['dsp_executions']==4
src=(P/'original-measure.py').read_text();tree=ast.parse(src)
# Copy exactly the two previously independently reviewed metric functions.
funcs=[ast.get_source_segment(src,n) for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['db_ratio','stats']];assert len(funcs)==2
exec('\n\n'.join(funcs),globals())
mp=json.loads((P/'original-measure-plan.json').read_text());nearbytes=pathlib.Path('/tmp/audio-fe-mandarin-near-admission-v1/known-near.pcm').read_bytes();assert hashlib.sha256(nearbytes).hexdigest()==plan['known_near_sha256']
near=[x/32768. for x in struct.unpack('<100640h',nearbytes)]
z=zipfile.ZipFile('/tmp/audio-d9/original.zip');rawbytes=z.read('originals/C/prepared/duplex_mono.pcm');prep=json.loads(z.read('originals/C/prepared/preparation.json'));q=prep['prepared_files']['duplex_mono.pcm'];assert len(rawbytes)==q['bytes'] and hashlib.sha256(rawbytes).hexdigest()==q['sha256'];raw=[x/32768. for x in struct.unpack('<100640h',rawbytes)]
N=100480;windows=[('common',0,N)]+[(f'second-{i//16000}',i,min(i+16000,N)) for i in range(0,N,16000)]+[(f'construction-{i}',a,b) for i,(a,b) in enumerate(zip([0,16000,64000,65280,84496],[16000,64000,65280,84496,N]))]
assert len(windows)==13
cases=[];hashes={}
for profile in ['call','assistant']:
 for arm in ['baseline','candidate']:
  root=P/(arm+'-'+profile);obs=json.loads((root/'taps/observer.json').read_text());assert obs['frames']==629 and obs['observer_error_count']==0
  pcm=(root/'out.pcm').read_bytes();lanes={'raw_mic0':raw,'final_s16':[x/32768. for x in struct.unpack('<100640h',pcm)]}
  for lane in ['aec_input','aec_residual','ns_input','ns_output','agc_output']:
   m=obs['lanes'][lane];assert m['offset_samples']==mp['lanes'][lane] and m['samples']==100640
   b=(root/'taps'/(lane+'.f32le')).read_bytes();assert len(b)==402560;lanes[lane]=list(struct.unpack('<100640f',b));assert all(math.isfinite(v) for v in lanes[lane])
  assert lanes['aec_residual']==lanes['ns_input']
  rows=list(csv.DictReader((root/'taps/control.csv').open()));assert len(rows)==629
  for i,r in enumerate(rows):assert int(r['frame'])==i and all(math.isfinite(float(v)) for v in r.values())
  groups={'all':list(range(629)),'near_waveform_nonzero':[f for f in range(629) if any(near[f*160:(f+1)*160])],'near_waveform_zero':[f for f in range(629) if not any(near[f*160:(f+1)*160])]}
  gates={name:{'frames':len(inds),'far_frames':sum(int(rows[i]['far']) for i in inds),'dt_frames':sum(int(rows[i]['dt']) for i in inds),'gate_eligible_frames':sum(int(rows[i]['gate_eligible']) for i in inds)} for name,inds in groups.items()}
  measurements=[{'window':name,'physical_range':[a,b],'lanes':{lane:{'output_range':[a+mp['lanes'][lane],b+mp['lanes'][lane]],**stats(y[a+mp['lanes'][lane]:b+mp['lanes'][lane]],near[a:b])} for lane,y in lanes.items()}} for name,a,b in windows]
  cases.append({'profile':profile,'arm':arm,'gates':gates,'measurements':measurements})
  hashes[arm+'-'+profile]={str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in root.rglob('*') if f.is_file()}
comparisons=[]
for profile in ['call','assistant']:
 b=next(x for x in cases if x['profile']==profile and x['arm']=='baseline');c=next(x for x in cases if x['profile']==profile and x['arm']=='candidate')
 comparisons.append({'profile':profile,'windows':[{'window':x['window'],'lanes':{lane:{k:(y['lanes'][lane][k]-v if v is not None and y['lanes'][lane][k] is not None else None) for k,v in x['lanes'][lane].items() if k not in ['output_range','samples']}for lane in x['lanes']}}for x,y in zip(b['measurements'],c['measurements'])]})
result={'experiment':plan['experiment'],'decision':'DIAGNOSTIC_ONLY_NO_PROMOTION','cases':cases,'candidate_minus_baseline':comparisons,'output_hashes':hashes,'windows_per_arm_profile':13,'measurement_groups':364,'dsp_runs_in_analysis':0,'promotion_allowed':False,'reference_constraints':mp['reference_constraints'],'scope':'one engineered Mandarin utterance, offline waveform-support oracle not deployable/human VAD or guaranteed upper bound; metrics raw-near-domain descriptive, no corpus/ASR/KWS/target claim','gate_denominator':'629 unshifted input frames, audio common span628 frames; not interchangeable','elapsed_seconds':time.monotonic()-start}
assert result['elapsed_seconds']<30
(P/'analysis.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
