from pathlib import Path
p=Path(__file__).parent
s=(p/'src/enhance/ap_noise_tracker.c').read_text()
for arm in ('baseline','candidate'):
 t=s
 if arm=='candidate':
  assert t.count('ap_clampf(')==2
  t=t.replace('ap_clampf(', 'local_clampf(')
  t=t.replace('#include <string.h>', '#include <string.h>\nstatic inline float local_clampf(float x,float lo,float hi) { return x < lo ? lo : (x > hi ? hi : x); }')
 for fn in ('init','update','next_frame'):t=t.replace('ap_noise_tracker_'+fn+'(',arm+'_'+fn+'(')
 (p/(arm+'.c')).write_text(t)
