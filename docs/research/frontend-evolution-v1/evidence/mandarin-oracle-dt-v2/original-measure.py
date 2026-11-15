import csv,hashlib,io,json,math,pathlib,struct,time,zipfile
P=pathlib.Path(__file__).parent;start=time.monotonic();plan=json.loads((P/'PLAN.json').read_text())
assert not (P/'result.json').exists(),'do not overwrite'
zpath=pathlib.Path('/tmp/audio-d9/original.zip');h=hashlib.sha256()
with zpath.open('rb') as f:
 for b in iter(lambda:f.read(1048576),b''):h.update(b)
assert h.hexdigest()==plan['source_zip_sha256']
z=zipfile.ZipFile(zpath);manifest=json.loads(z.read('result/artifact-manifest.json'))['files'];locks={}
def rd(rel):
 b=z.read('result/'+rel);q=manifest[rel];assert len(b)==q['bytes'] and hashlib.sha256(b).hexdigest()==q['sha256'],rel
 locks[rel]=q;return b
np=pathlib.Path('/tmp/audio-fe-mandarin-near-admission-v1');nearbytes=(np/'known-near.pcm').read_bytes();assert hashlib.sha256(nearbytes).hexdigest()==plan['known_near_sha256'];assert hashlib.sha256((np/'result.json').read_bytes()).hexdigest()==plan['admission_result_sha256']
near=[x/32768. for x in struct.unpack('<100640h',nearbytes)]
rawbytes=z.read('originals/C/prepared/duplex_mono.pcm');prep=json.loads(z.read('originals/C/prepared/preparation.json'));q=prep['prepared_files']['duplex_mono.pcm'];assert hashlib.sha256(rawbytes).hexdigest()==q['sha256'] and len(rawbytes)==q['bytes'];raw=[x/32768. for x in struct.unpack('<100640h',rawbytes)]
N=100480;windows=[('common',0,N)]+[(f'second-{i//16000}',i,min(i+16000,N)) for i in range(0,N,16000)]+[(f'construction-{i}',a,b) for i,(a,b) in enumerate(zip([0,16000,64000,65280,84496],[16000,64000,65280,84496,N]))]
def db_ratio(a,b):return 10*math.log10(a/b) if a>0 and b>0 else None
def stats(y,x):
 n=len(y);e=math.fsum(v*v for v in y);ne=math.fsum(v*v for v in x);err=math.fsum((a-b)*(a-b) for a,b in zip(y,x));xy=math.fsum(a*b for a,b in zip(y,x));g=xy/ne if ne>0 else None
 proj=math.fsum((g*v)*(g*v) for v in x) if g is not None else None;res=math.fsum((a-g*b)*(a-g*b) for a,b in zip(y,x)) if g is not None else None
 return {'samples':n,'output_energy':e,'near_energy':ne,'error_energy':err,'rms':math.sqrt(e/n),'peak':max(map(abs,y)),'gain_sensitive_error_db':db_ratio(err,ne),'projection_gain':g,'noncanonical_projection_si_sdr_db':db_ratio(proj,res) if g is not None else None,'projection_residual_energy':res}
cases=[]
for profile in plan['profiles']:
 root=f'cases/C/{profile}/';o=json.loads(rd(root+'taps/observer.json'));assert o['frames']==629 and o['observer_error_count']==0 and o['cli_exit_code']==0
 for fn in ['out.pcm','metrics.jsonl']:
  a=rd(root+'observed/'+fn);b=rd(root+'plain/'+fn);c=z.read('originals/C/prepared/processed/'+profile+'/'+fn);q=prep['prepared_files']['processed/'+profile+'/'+fn]
  assert len(c)==q['bytes'] and hashlib.sha256(c).hexdigest()==q['sha256'] and a==b==c,(profile,fn)
 lanes={'raw_mic0':raw,'final_s16':[x/32768. for x in struct.unpack('<100640h',rd(root+'observed/out.pcm'))]}
 for lane in ['aec_input','aec_residual','ns_input','ns_output','agc_output']:
  m=o['lanes'][lane];assert m['offset_samples']==plan['lanes'][lane] and m['samples']==100640
  b=rd(root+'taps/'+lane+'.f32le');assert len(b)==m['bytes']==402560
  lanes[lane]=list(struct.unpack('<100640f',b));assert all(math.isfinite(x) for x in lanes[lane])
 assert lanes['aec_residual']==lanes['ns_input']
 rows=list(csv.DictReader(io.StringIO(rd(root+'taps/control.csv').decode())));assert len(rows)==629
 for i,r in enumerate(rows):assert int(r['frame'])==i and all(math.isfinite(float(v)) for v in r.values())
 framegroups={'all':list(range(629)),'near_waveform_nonzero':[f for f in range(629) if any(near[f*160:(f+1)*160])],'near_waveform_zero':[f for f in range(629) if not any(near[f*160:(f+1)*160])]}
 gates={}
 for name,inds in framegroups.items():
  vals=[rows[i] for i in inds];ratios=[float(r['mic_energy'])/(float(r['reference_energy'])+1e-12) for r in vals if int(r['far'])];emas=[float(r['smoothed_mic_after'])/(float(r['smoothed_reference_after'])+1e-12) for r in vals if int(r['far'])]
  gates[name]={'frames':len(vals),'far_frames':sum(int(r['far']) for r in vals),'dt_frames':sum(int(r['dt']) for r in vals),'gate_eligible_frames':sum(int(r['gate_eligible']) for r in vals),'recorded_instant_ratio_far_minmax':[min(ratios),max(ratios)] if ratios else None,'recorded_smoothed_ratio_far_minmax':[min(emas),max(emas)] if emas else None}
 measurements=[]
 for name,a,b in windows:
  measurements.append({'window':name,'physical_range':[a,b],'lanes':{lane:{'output_range':[a+plan['lanes'][lane],b+plan['lanes'][lane]],**stats(y[a+plan['lanes'][lane]:b+plan['lanes'][lane]],near[a:b])} for lane,y in lanes.items()}})
 cases.append({'profile':profile,'gates':gates,'measurements':measurements})
r={'experiment':plan['experiment'],'decision':'DESCRIPTIVE_BASELINE_ONLY','cases':cases,'source_locks':locks,'near_sha256':plan['known_near_sha256'],'windows_per_profile':len(windows),'measurement_groups':len(cases)*len(windows)*7,'elapsed_seconds':time.monotonic()-start,'dsp_executions':0,'promotion_allowed':False,'reference_constraints':plan['reference_constraints']};assert r['elapsed_seconds']<=120
(P/'result.json').write_text(json.dumps(r,indent=2,allow_nan=False)+'\n');print(json.dumps({'decision':r['decision'],'measurement_groups':r['measurement_groups'],'elapsed_seconds':r['elapsed_seconds'],'gates':{c['profile']:c['gates'] for c in cases}},indent=2))
