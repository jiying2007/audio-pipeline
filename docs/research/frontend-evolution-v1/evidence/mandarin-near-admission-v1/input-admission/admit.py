import array,hashlib,json,math,pathlib,struct,sys,time,zipfile
P=pathlib.Path(__file__).parent
start=time.monotonic()
assert not (P/'result.json').exists(), 'do not overwrite scientific result'
plan=json.loads((P/'PLAN.json').read_text()); zpath=pathlib.Path('/tmp/audio-d9/original.zip')
h=hashlib.sha256()
with zpath.open('rb') as f:
 for b in iter(lambda:f.read(1048576),b''):h.update(b)
assert h.hexdigest()==plan['input_zip_sha256'],'ZIP identity'
z=zipfile.ZipFile(zpath);prefix='originals/C/prepared/'
prep=json.loads(z.read(prefix+'preparation.json'));d=prep['derivation']
expected={'original_samples':68496,'clean_preroll_samples':8000,'clean_postroll_samples':8000,'clean_alignment_padding_samples':144,'duplex_near_gain':0.5,'duplex_preroll_samples':16000,'duplex_postroll_samples':16000,'duplex_alignment_padding_samples':144,'echo_taps_mic0':[[800,0.25],[1280,0.1]],'echo_taps_mic1':[[801,0.25],[1281,0.1]]}
assert all(d[k]==v for k,v in expected.items()),'frozen recipe mismatch'
locks={}
def read(name):
 b=z.read(prefix+name);q=prep['prepared_files'][name]
 assert len(b)==q['bytes'] and hashlib.sha256(b).hexdigest()==q['sha256'],name
 locks[name]=q;return list(struct.unpack('<'+'h'*(len(b)//2),b))
clean=read('clean_mono.pcm');capclean=read('clean_capture.pcm');cap=read('duplex_capture.pcm');mono=read('duplex_mono.pcm');render=read('duplex_render.pcm')
assert len(clean)==84640 and len(capclean)==2*84640 and len(cap)==2*100640 and len(mono)==len(render)==100640
assert capclean[::2]==clean==capclean[1::2]
assert not any(clean[:8000]) and not any(clean[76496:])
orig=clean[8000:76496];near=[0]*16000+[round(x*0.5) for x in orig]+[0]*(16000+144)
assert len(near)==100640 and mono==cap[::2]
def echo(taps):
 a=[]
 for n in range(len(render)):
  v=0.0
  for delay,g in taps:
   if n>=delay:v+=g*render[n-delay]
  a.append(max(-32768,min(32767,int(round(v)))))
 return a
echos=[echo(d['echo_taps_mic0']),echo(d['echo_taps_mic1'])]
checks=[]
for ch,e in enumerate(echos):
 mixed=[n+x for n,x in zip(near,e)];assert min(mixed)>=-32768 and max(mixed)<=32767
 bad=[i for i,(a,b) in enumerate(zip(mixed,cap[ch::2])) if a!=b]
 checks.append({'channel':ch,'samples':len(mixed),'mismatches':len(bad),'first_mismatch':bad[0] if bad else None,'peak':max(map(abs,mixed))})
 assert not bad,checks[-1]
# Fixed engineering negatives, not new scientific candidates or thresholds.
neg=[]
for name,offset in [('near',16000),('echo',800)]:
 altered=[n+e for n,e in zip(near,echos[0])];altered[offset]+=1
 rejected=altered!=cap[::2];assert rejected;neg.append({'alteration':name,'sample':offset,'rejected':rejected})
out={}
for name,a in [('known-near.pcm',near),('known-echo-mic0.pcm',echos[0]),('known-echo-mic1.pcm',echos[1])]:
 b=struct.pack('<'+'h'*len(a),*a);(P/name).write_bytes(b);out[name]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
result={'experiment':plan['experiment'],'decision':'ENGINEERING_NEAR_REFERENCE_ADMITTED','source_zip_sha256':h.hexdigest(),'preparation_sha256':hashlib.sha256(z.read(prefix+'preparation.json')).hexdigest(),'source_locks':locks,'checked_recipe':expected,'capture_checks':checks,'negative_controls':neg,'outputs':out,'source_original_samples':len(orig),'near_nonzero_samples':sum(x!=0 for x in near),'near_first_nonzero':next(i for i,x in enumerate(near) if x),'near_last_nonzero':max(i for i,x in enumerate(near) if x),'elapsed_seconds':time.monotonic()-start,'algorithm_changed':False,'dsp_executions':0,'asr_kws_executions':0,'promotion_allowed':False,'scope':plan['data_role']}
assert result['elapsed_seconds']<=plan['budget_seconds']
(P/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
