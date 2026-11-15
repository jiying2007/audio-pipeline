# Post-hoc descriptive trace of existing files only. No DSP or candidate selection.
import csv,json,pathlib,struct,hashlib
P=pathlib.Path(__file__).parent
result={'kind':'POSTHOC_EXISTING_OUTPUT_TRACE','dsp_runs':0,'causal_limits':'Temporal first differences and gain-state differences under jointly changed downstream inputs locate observable divergence, not independent module effects. DT changes multiple downstream paths jointly. No inferred adaptation updates from gate eligibility.','cases':[]}
for profile in ['call','assistant']:
 b=P/('baseline-'+profile);c=P/('candidate-'+profile);br=list(csv.DictReader((b/'taps/control.csv').open()));cr=list(csv.DictReader((c/'taps/control.csv').open()));fields={}
 for k in br[0]:
  d=[i for i,(x,y) in enumerate(zip(br,cr)) if x[k]!=y[k]]
  fields[k]={'differing_frames':len(d),'first_frame':d[0] if d else None,'last_frame':d[-1] if d else None}
 lanes={}
 for name in ['aec_input','reference','echo','aec_residual','ns_input','ns_output','agc_output']:
  x=(b/'taps'/(name+'.f32le')).read_bytes();y=(c/'taps'/(name+'.f32le')).read_bytes();d=[i for i in range(len(x)//4) if x[i*4:i*4+4]!=y[i*4:i*4+4]];offset=160 if name in ['ns_output','agc_output'] else 0
  lanes[name]={'different_samples':len(d),'first_output_sample':d[0] if d else None,'first_input_axis_sample':d[0]-offset if d else None,'baseline_sha256':hashlib.sha256(x).hexdigest(),'candidate_sha256':hashlib.sha256(y).hexdigest()}
 # Exact native control state, not quality attribution.
 gains={arm:{'gain_after_min':min(float(r['gain_after']) for r in rows),'gain_after_max':max(float(r['gain_after']) for r in rows),'agc_allow_frames':sum(int(r['agc_allow']) for r in rows),'gain_after_last':float(rows[-1]['gain_after'])} for arm,rows in [('baseline',br),('candidate',cr)]}
 result['cases'].append({'profile':profile,'fields':fields,'lanes':lanes,'agc_state_descriptive':gains})
(P/'existing-trace.json').write_text(json.dumps(result,indent=2)+'\n')
