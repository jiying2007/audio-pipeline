import json,statistics,math,hashlib
from pathlib import Path
p=Path(__file__).parent
med={};counts={}
for mode in ('EMA','MCRA'):
 rows={}
 lines=(p/f'result-{mode}.txt').read_text().splitlines();counts[mode]=lines[0]
 for line in lines[1:]:
  _,bins,rep,base,cand,ratio=line.split();rows.setdefault(bins,[]).append(float(cand)/float(base))
 assert len(rows)==4 and all(len(x)==9 for x in rows.values())
 for bins,v in rows.items():med[mode+'/'+bins]=statistics.median(v)
g=math.exp(statistics.mean(math.log(x) for x in med.values()))
r={'experiment':'FE-NS-CLAMP-INLINE-V1','equivalence':counts,'median_pair_ratios':med,'geometric_mean_ratio':g,'time_reduction_percent':100*(1-g),'screen_pass':g<=.95 and max(med.values())<=1.05,'decision':'REVIEW_ONLY' if g<=.95 and max(med.values())<=1.05 else 'NO_ADVANCE','promotion_allowed':False,'scope':'synthetic noise-tracker host microbenchmark, not full NS/pipeline/SSC305; no affinity or confidence interval','observations':72}
(p/'summary.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
