import array,csv,hashlib,io,json,math,os,pathlib,struct,subprocess,tarfile,time,zipfile
P=pathlib.Path(__file__).parent;start=time.monotonic();plan=json.loads((P/'PLAN.json').read_text());assert not (P/'run-state.json').exists(),'single execution only'
(P/'run-state.json').write_text(json.dumps({'started':time.time(),'plan_sha256':hashlib.sha256((P/'PLAN.json').read_bytes()).hexdigest()}))
commands=[]
source_start={n:hashlib.sha256((P/n).read_bytes()).hexdigest() for n in ['PLAN.json','run.py']}
def dump(name,obj): (P/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
def command(name,argv,limit,env=None):
 begun=time.monotonic();rec={'name':name,'argv':list(map(str,argv)),'cwd':str(P),'started_epoch':time.time(),'terminal':False,'timeout':False};dump(name+'-command.json',rec)
 with (P/(name+'.stdout')).open('wb') as out,(P/(name+'.stderr')).open('wb') as err:
  try:
   r=subprocess.run(list(map(str,argv)),cwd=P,env=env,stdout=out,stderr=err,timeout=min(limit,180-(time.monotonic()-start)))
   rec.update(exit_code=r.returncode,terminal=True)
  except subprocess.TimeoutExpired:
   rec.update(exit_code=None,terminal=True,timeout=True)
 rec['elapsed_seconds']=time.monotonic()-begun;commands.append(rec);dump(name+'-receipt.json',rec)
 assert rec.get('exit_code')==0 and not rec['timeout'],name+' failed'
 return rec
zpath=pathlib.Path('/tmp/audio-d9/original.zip');h=hashlib.sha256()
with zpath.open('rb') as f:
 for b in iter(lambda:f.read(1048576),b''):h.update(b)
assert h.hexdigest()==plan['zip_sha256'];z=zipfile.ZipFile(zpath)
manifest=json.loads(z.read('result/artifact-manifest.json'))['files'];locks={}
def rd(name):
 b=z.read('result/'+name);q=manifest[name];assert len(b)==q['bytes'] and hashlib.sha256(b).hexdigest()==q['sha256'],name;locks[name]=q;return b
source=P/'source';source.mkdir();t=tarfile.open(fileobj=io.BytesIO(rd('build/exact-source.tar')))
for m in t.getmembers():
 rel=pathlib.PurePosixPath(m.name)
 if not m.isfile() or rel.is_absolute() or '..' in rel.parts or not rel.parts or rel.parts[0] not in ['include','src','examples']:continue
 out=source/str(rel);out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(t.extractfile(m).read())
original=rd('build/observer-source/tests/validation/frontend_evolution/dualmic_stages_d1.c');wrapper=source/'tests/validation/frontend_evolution';wrapper.mkdir(parents=True);(wrapper/'baseline.c').write_bytes(original)
nearpath=pathlib.Path('/tmp/audio-fe-mandarin-near-admission-v1/known-near.pcm');nearbytes=nearpath.read_bytes();assert hashlib.sha256(nearbytes).hexdigest()==plan['known_near_sha256'];near=list(struct.unpack('<100640h',nearbytes));mask=[int(any(near[i:i+160])) for i in range(0,len(near),160)];assert len(mask)==629
(P/'oracle-mask.bin').write_bytes(bytes(mask));text=original.decode();needle='    ap_activity_process_d1_real(state, mic_energy, reference_energy, result);\n';assert text.count(needle)==1
injection='    d1_expect(d1_activity_calls < 629u, "oracle_frame_range");\n    if (d1_activity_calls < 629u) result->double_talk_active = (uint8_t)(result->far_end_active && oracle_mask[d1_activity_calls]);\n'
text=text.replace(needle,needle+injection).replace('static FILE *d1_lanes', 'static const unsigned char oracle_mask[629] = {'+','.join(map(str,mask))+'};\n\nstatic FILE *d1_lanes')
assert text.replace(injection,'').replace('static const unsigned char oracle_mask[629] = {'+','.join(map(str,mask))+'};\n\n','')==original.decode()
(wrapper/'candidate.c').write_text(text)
lib=P/'libaudio_pipeline.a';lib.write_bytes(rd('build/observer-build/libaudio_pipeline.a'));gen=P/'generated/audio_pipeline/audio_pipeline_build.h';gen.parent.mkdir(parents=True);gen.write_bytes(rd('build/observer-build/generated/audio_pipeline/audio_pipeline_build.h'))
bm=json.loads(rd('build/build-manifest.json'))['builds']['observer'];assert hashlib.sha256(lib.read_bytes()).hexdigest()==bm['library']['sha256']
for name in ['duplex_capture.pcm','duplex_render.pcm']:
 b=z.read('originals/C/prepared/'+name);prep=json.loads(z.read('originals/C/prepared/preparation.json'));q=prep['prepared_files'][name];assert len(b)==q['bytes'] and hashlib.sha256(b).hexdigest()==q['sha256'];(P/name).write_bytes(b)
build={'library_original':bm['library'],'wrapper_original_sha256':hashlib.sha256(original).hexdigest(),'candidate_wrapper_sha256':hashlib.sha256(text.encode()).hexdigest(),'oracle_mask_sha256':hashlib.sha256(bytes(mask)).hexdigest(),'oracle_support_frames':sum(mask),'source_locks':locks}
dump('build.json',build)
command('compiler',['gcc','--version'],10)
for arm in ['baseline','candidate']:
 argv=['gcc']+bm['definitions']+['-I'+str(P/'generated'),'-I'+str(source/'include'),'-I'+str(source/'src')]+bm['flags']+[str(wrapper/(arm+'.c')),str(lib),'-lm','-o',str(P/arm)]
 command('compile-'+arm,argv,30)
# Every baseline validates before either candidate. No candidate runs on a failed baseline.
for arm in ['baseline','candidate']:
 for profile in plan['profiles']:
  out=P/(arm+'-'+profile);out.mkdir();taps=out/'taps';taps.mkdir();env=dict(os.environ);env['AP_D1_STAGE_DIR']=str(taps)
  argv=[P/arm,'--profile',profile,'--sample-rate','16000','--mic-channels','2','--strict-capture-frames','--metrics-jsonl',out/'metrics.jsonl',P/'duplex_capture.pcm',P/'duplex_render.pcm',out/'out.pcm']
  command(arm+'-'+profile,argv,30,env)
  o=json.loads((taps/'observer.json').read_text());assert o['frames']==629 and o['observer_error_count']==0 and o['cli_exit_code']==0
  if arm=='baseline':
   for name in ['aec_input.f32le','reference.f32le','echo.f32le','aec_residual.f32le','ns_input.f32le','ns_output.f32le','agc_output.f32le','control.csv']:
    assert (taps/name).read_bytes()==rd('cases/C/'+profile+'_duplex/taps/'+name),('baseline mismatch',profile,name)
   for name in ['out.pcm','metrics.jsonl']:assert (out/name).read_bytes()==rd('cases/C/'+profile+'_duplex/observed/'+name),('baseline mismatch',profile,name)
  else:
   rows=list(csv.DictReader(io.StringIO((taps/'control.csv').read_text())));base=list(csv.DictReader(io.StringIO((P/('baseline-'+profile)/'taps/control.csv').read_text())));assert len(rows)==629
   for i,(a,b) in enumerate(zip(base,rows)):
    for k in ['frame','mic_energy','reference_energy','smoothed_mic_before','smoothed_reference_before','smoothed_mic_after','smoothed_reference_after','far_threshold','double_talk_ratio','hangover_frames','far_hangover_before','far_hangover_after','dt_hangover_before','dt_hangover_after','far']:
     assert a[k]==b[k],('upstream drift',profile,i,k)
    assert int(b['dt'])==int(b['far'])*mask[i]
hend=hashlib.sha256()
with zpath.open('rb') as f:
 for b in iter(lambda:f.read(1048576),b''):hend.update(b)
assert hend.hexdigest()==plan['zip_sha256']
assert all(hashlib.sha256((P/n).read_bytes()).hexdigest()==v for n,v in source_start.items())
assert hashlib.sha256(lib.read_bytes()).hexdigest()==bm['library']['sha256']
assert hashlib.sha256(nearpath.read_bytes()).hexdigest()==plan['known_near_sha256']
assert (wrapper/'baseline.c').read_bytes()==original and (wrapper/'candidate.c').read_text()==text
dump('execution.json',{'status':'BASELINE_EXACT_CANDIDATE_EXECUTED','commands':commands,'elapsed_seconds':time.monotonic()-start,'dsp_executions':4,'source_locks':locks,'promotion_allowed':False})
print('BASELINE_EXACT_CANDIDATE_EXECUTED')
