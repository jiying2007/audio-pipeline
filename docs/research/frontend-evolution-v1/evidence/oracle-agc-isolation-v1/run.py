import ast,csv,hashlib,json,math,os,pathlib,statistics,struct,subprocess,sys,time,signal
P=pathlib.Path(__file__).parent;start=time.monotonic();assert sys.byteorder=='little';assert not (P/'started.json').exists();(P/'started.json').write_text(json.dumps({'epoch':time.time()}))
plan=json.loads((P/'PLAN.json').read_text());locks=json.loads((P/'input-lock.json').read_text());receipts=[]
source={n:hashlib.sha256((P/n).read_bytes()).hexdigest()for n in ['PLAN.json','input-lock.json','run.py','replay.c','original-measure.py']}
def dump(n,x):(P/n).write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def check():
 assert all(hashlib.sha256((P/n).read_bytes()).hexdigest()==v['sha256'] and (P/n).stat().st_size==v['bytes'] for n,v in locks.items())
 assert all(hashlib.sha256((P/n).read_bytes()).hexdigest()==v for n,v in source.items())
check()
dump('loader-environment-presence.json',{'LD_names_present':[k for k in os.environ if k.startswith('LD_')],'GLIBC_TUNABLES_present':'GLIBC_TUNABLES' in os.environ})
assert not any(k.startswith('LD_') or k=='GLIBC_TUNABLES' for k in os.environ),'unexpected runtime override'
def command(name,args,limit):
 t=time.monotonic();dump(name+'-command.json',{'argv':list(map(str,args)),'cwd':str(P),'limit':limit})
 with (P/(name+'.stdout')).open('wb') as o,(P/(name+'.stderr')).open('wb') as e:
  try:r=subprocess.run(list(map(str,args)),cwd=P,stdout=o,stderr=e,timeout=min(limit,180-(time.monotonic()-start)));status=r.returncode
  except subprocess.TimeoutExpired:status='TIMEOUT'
 rec={'name':name,'exit':status,'elapsed':time.monotonic()-t};dump(name+'-receipt.json',rec);receipts.append(rec);assert status==0,(name,status)
command('compiler',['gcc','--version'],10)
command('compile',['gcc','-std=c11','-O3','-ffp-contract=off','-Wall','-Wextra','-Werror','-DAP_BUILD_STAGE_AGC=1','-I'+str(P/'src'),P/'src/ap_agc.c',P/'replay.c','-lm','-o',P/'replay'],30)
elfhash=hashlib.sha256((P/'replay').read_bytes()).hexdigest()
def invoke(profile,arm,name,repeats):
 check();assert hashlib.sha256((P/'replay').read_bytes()).hexdigest()==elfhash
 command(name,[P/'replay',P/(profile+'-input.f32le'),P/(profile+'-'+arm+'.allow'),profile,str(repeats),P/(name+'.f32le'),P/(name+'.states'),P/(name+'.cpu.json')],10)
 check();assert hashlib.sha256((P/'replay').read_bytes()).hexdigest()==elfhash
 return json.loads((P/(name+'.cpu.json')).read_text())
for profile in plan['profiles']:
 name='oracle-'+profile;invoke(profile,'oracle',name,1)
 assert (P/(name+'.f32le')).read_bytes()==(P/(profile+'-expected.f32le')).read_bytes(),(profile,'output mismatch')
 assert (P/(name+'.states')).read_bytes()==(P/(profile+'-expected.states')).read_bytes(),(profile,'gain state mismatch')
dump('baseline-gate.json',{'profiles':plan['profiles'],'all_output_and_gain_bytes_exact':True})
for profile in plan['profiles']:invoke(profile,'restored','restored-'+profile,1)
perf=[]
for rep in range(7):
 for profile in plan['profiles']:
  arms=['oracle','restored'] if rep%2==0 else ['restored','oracle'];row={'rep':rep,'profile':profile,'order':arms}
  for arm in arms:
   name=f'bench-{rep}-{profile}-{arm}';row[arm]=invoke(profile,arm,name,100)
   for suffix in ['.f32le','.states']:assert (P/(name+suffix)).read_bytes()==(P/(arm+'-'+profile+suffix)).read_bytes(),(name,suffix)
  row['ratio']=row['restored']['thread_cpu_seconds']/row['oracle']['thread_cpu_seconds'];perf.append(row)
# Same frozen, independently-reviewed metric functions; no output gain or delay fit.
def analysis_timeout(signum,frame):raise TimeoutError('analysis exceeded frozen30s')
signal.signal(signal.SIGALRM,analysis_timeout);signal.alarm(30)
try:
 analysis_start=time.monotonic()
 src=(P/'original-measure.py').read_text();tree=ast.parse(src);funcs=[ast.get_source_segment(src,n)for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['db_ratio','stats']];assert len(funcs)==2;exec('\n\n'.join(funcs),globals())
 near=[x/32768. for x in struct.unpack('<100640h',(P/'known-near.pcm').read_bytes())];N=100480
 windows=[('common',0,N)]+[(f'second-{i//16000}',i,min(i+16000,N)) for i in range(0,N,16000)]+[(f'construction-{i}',a,b) for i,(a,b) in enumerate(zip([0,16000,64000,65280,84496],[16000,64000,65280,84496,N]))];assert len(windows)==13
 cases=[]
 for profile in plan['profiles']:
  measurements={}
  for arm in ['oracle','restored']:
   y=struct.unpack('<100640f',(P/(arm+'-'+profile+'.f32le')).read_bytes());assert all(math.isfinite(v)for v in y)
   measurements[arm]=[{'window':name,'physical_range':[a,b],'output_range':[a+160,b+160],**stats(y[a+160:b+160],near[a:b])} for name,a,b in windows]
  cases.append({'profile':profile,'measurements':measurements})
 check();assert hashlib.sha256((P/'replay').read_bytes()).hexdigest()==elfhash
 assert time.monotonic()-analysis_start<=30
 output_hashes={f.name:hashlib.sha256(f.read_bytes()).hexdigest()for f in P.iterdir()if f.suffix in ['.f32le','.states']}
 dump('result.json',{'decision':'CONDITIONAL_SINGLE_MODULE_DIAGNOSTIC_NO_PROMOTION','cases':cases,'performance':perf,'median_pair_ratios':{p:statistics.median(x['ratio']for x in perf if x['profile']==p)for p in plan['profiles']},'elapsed':time.monotonic()-start,'commands':receipts,'elf_sha256':elfhash,'source_hashes':source,'output_hashes':output_hashes,'whole_pipeline_runs':0,'old_runtime_runs':0,'promotion_allowed':False,'limits':plan['quality']+'; not additive decomposition of total DT effect. Native CPU times include identical copy/init/trace stores; no target claim.'})
finally:signal.alarm(0)
