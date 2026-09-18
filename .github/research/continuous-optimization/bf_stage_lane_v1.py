#!/usr/bin/env python3
"""Development-only BF algorithm/parameter lane.

The shipping BF remains the authority baseline. Research candidates are emulated
off-line on deterministic two-mic corpora and can at most become a frozen stage
research candidate. Validation/shadow reject only.
"""
from __future__ import annotations

import argparse
import array
import json
import math
import os
import subprocess
import tempfile
from pathlib import Path
from statistics import median
from typing import Any

FRAME = 160
HISTORY = 8
MIN_DEVELOPMENT_SCORE = 0.50

def read_pcm(path: Path) -> list[int]:
    values=array.array("h")
    values.frombytes(path.read_bytes())
    if os.sys.byteorder != "little": values.byteswap()
    return list(values)

def clamp16(x: float) -> int:
    return max(-32768, min(32767, int(round(x))))

def si_sdr(ref: list[int], est: list[int]) -> float:
    n=min(len(ref),len(est))
    if n < 16: return -120.0
    r=[float(x) for x in ref[:n]]
    e=[float(x) for x in est[:n]]
    rr=sum(x*x for x in r)
    if rr <= 1e-12: return -120.0
    scale=sum(x*y for x,y in zip(r,e))/rr
    target=sum((scale*x)**2 for x in r)
    error=sum((y-scale*x)**2 for x,y in zip(r,e))
    return 10.0*math.log10((target+1e-12)/(error+1e-12))

def roughness(x: list[float]) -> float:
    if not x: return 1.0
    energy=1e-12 + sum(v*v for v in x)
    diff=1e-12 + sum((x[i]-x[i-1])**2 for i in range(1,len(x)))
    return diff/energy

def past(history: list[list[float]], x: list[float], ch: int, index: int) -> float:
    if index >= 0: return x[index]
    if index < -HISTORY: return 0.0
    return history[ch][HISTORY+index]

class BF:
    def __init__(self, variant: str, parameter: float):
        self.variant=variant
        self.parameter=parameter
        self.history=[[0.0]*HISTORY for _ in range(2)]
        self.scores=[0.0]*(2*HISTORY+1)
        self.score_updates=0
        self.lag=0
        self.counter=3
        self.max_lag=3
        self.fallback=False
        self.strong=0
        self.fallback_lag=0
        self.fallback_gain=1.0

    def estimate(self,a:list[float],b:list[float]) -> tuple[int,float,float,float,float]:
        best=self.lag; best_score=-1e30; best_aa=best_bb=1e-12; best_xy=0.0
        for lag in range(-self.max_lag,self.max_lag+1):
            aa=bb=1e-12; xy=0.0
            for i in range(0,len(a),2):
                if lag>=0:
                    x=a[i]; y=past(self.history,b,1,i-lag)
                else:
                    x=past(self.history,a,0,i+lag); y=b[i]
                xy+=x*y; aa+=x*x; bb+=y*y
            score=xy/math.sqrt(aa*bb)
            idx=lag+HISTORY
            if self.score_updates==0: self.scores[idx]=score
            else: self.scores[idx]+=0.25*(score-self.scores[idx])
        self.score_updates+=1
        for lag in range(-self.max_lag,self.max_lag+1):
            idx=lag+HISTORY
            score=self.scores[idx]
            if score>best_score:
                best_score=score; best=lag
        lag=best if best_score>0.15 else self.lag
        aa=bb=1e-12; xy=0.0
        for i in range(0,len(a),2):
            if lag>=0:
                x=a[i]; y=past(self.history,b,1,i-lag)
            else:
                x=past(self.history,a,0,i+lag); y=b[i]
            xy+=x*y; aa+=x*x; bb+=y*y
        return lag,best_score,aa,bb,xy

    def process(self,a:list[float],b:list[float]) -> list[int]:
        update=((self.counter+1)&3)==0
        self.counter+=1
        coherence=1.0; aa=bb=1.0; xy=0.0
        if update:
            lag,coherence,aa,bb,xy=self.estimate(a,b)
            if self.variant=="confidence-gated-tracking":
                if coherence >= self.parameter:
                    self.lag += 1 if lag>self.lag else (-1 if lag<self.lag else 0)
            else:
                self.lag += 1 if lag>self.lag else (-1 if lag<self.lag else 0)
            ratio=math.sqrt(min(aa,bb)/max(max(aa,bb),1e-12))
            energy_strong=0 if aa>=bb else 1
            if self.variant=="health-selected-bypass":
                severe=ratio < self.parameter
                ra,rb=roughness(a),roughness(b)
                if severe:
                    if energy_strong==0 and ra < 0.18*max(rb,1e-12): self.strong=1
                    elif energy_strong==1 and rb < 0.18*max(ra,1e-12): self.strong=0
                    else: self.strong=energy_strong
                    self.fallback=True; self.fallback_lag=self.lag
                elif ratio>0.60:
                    self.fallback=False
            elif self.variant=="reliability-weighted-das":
                self.strong=energy_strong
                self.fallback=ratio<0.60
                self.fallback_lag=self.lag
            elif self.variant=="shipping-bf":
                severe=coherence<0.980 and ratio<0.45
                if severe:
                    self.strong=energy_strong; self.fallback=True; self.fallback_lag=self.lag
                elif coherence>0.988 or ratio>0.52:
                    self.fallback=False

        out=[]
        lag=self.fallback_lag if self.fallback else self.lag
        for i in range(len(a)):
            if lag>=0:
                x=a[i]; y=past(self.history,b,1,i-lag)
            else:
                x=past(self.history,a,0,i+lag); y=b[i]
            if self.variant=="health-selected-bypass" and self.fallback:
                z=x if self.strong==0 else y
            elif self.variant=="reliability-weighted-das" and self.fallback:
                w=float(self.parameter)
                strong=x if self.strong==0 else y
                weak=y if self.strong==0 else x
                z=w*strong+(1.0-w)*weak
            elif self.variant=="shipping-bf" and self.fallback:
                strong=x if self.strong==0 else y
                weak=y if self.strong==0 else x
                z=0.75*strong+0.25*weak
            else:
                z=0.5*(x+y)
            out.append(clamp16(z))
        for k in range(HISTORY):
            src=len(a)-HISTORY+k if len(a)>HISTORY else k
            self.history[0][k]=a[src] if src<len(a) else 0.0
            self.history[1][k]=b[src] if src<len(b) else 0.0
        return out

def process_interleaved(samples:list[int],variant:str,param:float) -> list[int]:
    state=BF(variant,param); out=[]
    frames=len(samples)//(FRAME*2)
    for frame in range(frames):
        base=frame*FRAME*2
        a=[float(samples[base+2*i]) for i in range(FRAME)]
        b=[float(samples[base+2*i+1]) for i in range(FRAME)]
        out.extend(state.process(a,b))
    return out

def shipping_output(processor:Path, mic:Path) -> list[int]:
    with tempfile.TemporaryDirectory(prefix="ap-bf-lane-") as tmp:
        out=Path(tmp)/"out.pcm"
        subprocess.run([str(processor),"--sample-rate","16000","--mic-channels","2",
                        "--capture-profile","bf-isolated","--capture-only",str(mic),str(out)],
                       check=True)
        return read_pcm(out)

def sensitivity_rows(corpus_path:Path,variant:str,param:float) -> list[dict[str,Any]]:
    corpus=json.loads(corpus_path.read_text())
    rows=[]
    for case in corpus["cases"]:
        mic=read_pcm(corpus_path.parent/case["mic_audio"])
        clean=read_pcm(corpus_path.parent/case["clean_near_audio"])
        out=process_interleaved(mic,variant,param)
        ch0=mic[0::2]
        improvement=si_sdr(clean,out)-si_sdr(clean,ch0)
        rows.append({"case_id":case["case_id"],"model":case["dimensions"]["mismatch_model"],
                     "ratio":float(case["dimensions"]["weak_channel_ratio"]),
                     "improvement_db":improvement})
    return rows

def hard_rows(corpus_path:Path,variant:str,param:float) -> list[dict[str,Any]]:
    corpus=json.loads(corpus_path.read_text())
    rows=[]
    for case in corpus["cases"]:
        mic=read_pcm(corpus_path.parent/case["mic_audio"])
        clean=read_pcm(corpus_path.parent/case["clean_audio"])
        reliable=read_pcm(corpus_path.parent/case["reliable_audio"])
        out=process_interleaved(mic,variant,param)
        start=(int(case["fault_start_frame"])+40)*FRAME
        end=(int(case["fault_end_frame"])-20)*FRAME
        current=si_sdr(clean[start:end],out[start:end])
        oracle=si_sdr(clean[start:end],reliable[start:end])
        rows.append({"case_id":case["case_id"],"fault_type":case["fault_type"],
                     "delta_vs_reliable_db":current-oracle})
    return rows

def summarize(sens:list[dict], hard:list[dict]) -> dict[str,float]:
    sf=[r["improvement_db"] for r in sens if r["model"]=="sensitivity-floor"]
    global_gain=[r["improvement_db"] for r in sens if r["model"]=="global-channel-gain"]
    faults=[r["delta_vs_reliable_db"] for r in hard if r["fault_type"] not in {
        "control","soft-global-gain","soft-sensitivity-floor"}]
    soft=[r["delta_vs_reliable_db"] for r in hard if r["fault_type"] in {
        "soft-global-gain","soft-sensitivity-floor"}]
    control=[r["delta_vs_reliable_db"] for r in hard if r["fault_type"]=="control"]
    return {
        "sensitivity_floor_min_db":min(sf),
        "global_gain_min_db":min(global_gain),
        "hard_fault_median_delta_db":median(faults),
        "hard_fault_min_delta_db":min(faults),
        "soft_control_min_delta_db":min(soft),
        "control_delta_db":control[0],
    }

def regressions(base:dict[str,float], cand:dict[str,float]) -> list[dict]:
    checks={
        "sensitivity_floor_min_db":0.30,
        "global_gain_min_db":0.30,
        "soft_control_min_delta_db":0.30,
        "control_delta_db":0.30,
    }
    out=[]
    for key,allowed in checks.items():
        drop=base[key]-cand[key]
        if drop>allowed:
            out.append({"gate":"metric_regression","metric":key,"drop":drop,"allowed":allowed})
    return out

def score(base:dict[str,float],cand:dict[str,float]) -> float:
    return (
        (cand["sensitivity_floor_min_db"]-base["sensitivity_floor_min_db"])/0.25+
        (cand["hard_fault_median_delta_db"]-base["hard_fault_median_delta_db"])/0.50+
        (cand["hard_fault_min_delta_db"]-base["hard_fault_min_delta_db"])/0.50
    )

CANDIDATES=[
    ("shipping-bf",0.75),
    ("reliability-weighted-das",0.65),("reliability-weighted-das",0.75),("reliability-weighted-das",0.85),
    ("confidence-gated-tracking",0.30),("confidence-gated-tracking",0.50),("confidence-gated-tracking",0.70),
    ("health-selected-bypass",0.25),("health-selected-bypass",0.35),("health-selected-bypass",0.45),
]

def evaluate_pair(sensitivity:Path, hard:Path, variant:str,param:float)->dict:
    sens=sensitivity_rows(sensitivity,variant,param)
    hr=hard_rows(hard,variant,param)
    return {"summary":summarize(sens,hr),"sensitivity":sens,"hard_fault":hr}

def run(processor:Path, dev_sens:list[Path],dev_hard:list[Path],
        val_sens:Path,val_hard:Path,shadow_sens:Path,shadow_hard:Path,output:Path)->dict:
    if len(dev_sens)!=2 or len(dev_hard)!=2:
        raise ValueError("exactly two development sensitivity/hard-fault corpora required")
    dev=[]
    for variant,param in CANDIDATES:
        per=[evaluate_pair(s,h,variant,param) for s,h in zip(dev_sens,dev_hard)]
        merged={k:median([x["summary"][k] for x in per]) for k in per[0]["summary"]}
        dev.append({"variant":variant,"parameter":param,"summary":merged})
    baseline=next(x for x in dev if x["variant"]=="shipping-bf")
    for row in dev:
        row["score"]=score(baseline["summary"],row["summary"])
        row["violations"]=regressions(baseline["summary"],row["summary"])
        row["eligible"]=not row["violations"] and row["score"]>=MIN_DEVELOPMENT_SCORE
    eligible=[x for x in dev if x["eligible"] and x["variant"]!="shipping-bf"]
    eligible.sort(key=lambda x:(-x["score"],x["variant"],x["parameter"]))
    selected=eligible[0] if eligible else baseline
    val_base=evaluate_pair(val_sens,val_hard,"shipping-bf",0.75)
    val_cand=evaluate_pair(val_sens,val_hard,selected["variant"],selected["parameter"])
    shadow_base=evaluate_pair(shadow_sens,shadow_hard,"shipping-bf",0.75)
    shadow_cand=evaluate_pair(shadow_sens,shadow_hard,selected["variant"],selected["parameter"])
    val_v=regressions(val_base["summary"],val_cand["summary"])
    shadow_v=regressions(shadow_base["summary"],shadow_cand["summary"])

    # Baseline fidelity: compare emulator and exact shipping processor on validation sensitivity corpus.
    fidelity=[]
    corpus=json.loads(val_sens.read_text())
    for case in corpus["cases"]:
        if float(case.get("dimensions", {}).get("weak_channel_ratio", 0.0)) != 1.0:
            continue
        mic_path=val_sens.parent/case["mic_audio"]
        clean=read_pcm(val_sens.parent/case["clean_near_audio"])
        exact=shipping_output(processor,mic_path)
        emu=process_interleaved(read_pcm(mic_path),"shipping-bf",0.75)
        delta=abs(si_sdr(clean,exact)-si_sdr(clean,emu))
        fidelity.append({"case_id":case["case_id"],"si_sdr_delta_db":delta})
    fidelity_max=max(x["si_sdr_delta_db"] for x in fidelity)
    if fidelity_max>0.25:
        raise ValueError(f"shipping BF emulator fidelity drift: {fidelity_max:.6f} dB")

    if selected is baseline:
        decision="KEEP_BASELINE"
    elif val_v or shadow_v:
        decision="REJECT_CANDIDATE"
    else:
        decision="FROZEN_STAGE_RESEARCH_CANDIDATE"
    result={
        "schema_version":1,
        "authority":"research-stage-selection-only",
        "lane_id":"bf",
        "decision":decision,
        "baseline":{"variant":"shipping-bf","parameter":0.75},
        "selected":{"variant":selected["variant"],"parameter":selected["parameter"],
                    "development_score":selected["score"]},
        "development":{"ranking":sorted(dev,key=lambda x:(-x["score"],x["variant"],x["parameter"]))},
        "validation":{"baseline":val_base["summary"],"candidate":val_cand["summary"],
                      "regression_violations":val_v},
        "shadow":{"baseline":shadow_base["summary"],"candidate":shadow_cand["summary"],
                  "regression_violations":shadow_v},
        "baseline_fidelity":{"max_si_sdr_delta_db":fidelity_max,"cases":fidelity},
        "effective_winner":(
            {"variant":selected["variant"],"parameter":selected["parameter"]}
            if decision=="FROZEN_STAGE_RESEARCH_CANDIDATE"
            else {"variant":"shipping-bf","parameter":0.75}
        ),
        "executable_binding":{
            "bound":decision!="FROZEN_STAGE_RESEARCH_CANDIDATE",
            "kind":"shipping-baseline" if decision!="FROZEN_STAGE_RESEARCH_CANDIDATE" else "research-emulator",
        },
        "automatic_main_mutation":False,"shipping_authority":False,
        "hil_authority":False,"product_certification_authority":False,
        "next_gate":"separate-source-candidate-review" if decision=="FROZEN_STAGE_RESEARCH_CANDIDATE" else None,
    }
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    return result

def self_test()->None:
    # State machine smoke test on coherent delayed channels.
    samples=[]
    for n in range(FRAME*20):
        a=int(7000*math.sin(2*math.pi*440*n/16000))
        b=int(7000*math.sin(2*math.pi*440*max(0,n-2)/16000))
        samples.extend([a,b])
    out=process_interleaved(samples,"shipping-bf",0.75)
    assert len(out)==FRAME*20
    assert all(-32768<=x<=32767 for x in out)
    base={"sensitivity_floor_min_db":1.0,"global_gain_min_db":1.0,
          "hard_fault_median_delta_db":-3.0,"hard_fault_min_delta_db":-6.0,
          "soft_control_min_delta_db":-1.0,"control_delta_db":0.0}
    better=dict(base); better["hard_fault_median_delta_db"]=-2.0
    assert score(base,better)>0 and not regressions(base,better)
    print("BF stage lane self-test: OK")

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--processor",type=Path)
    p.add_argument("--development-sensitivity",action="append",type=Path,default=[])
    p.add_argument("--development-hard-fault",action="append",type=Path,default=[])
    p.add_argument("--validation-sensitivity",type=Path)
    p.add_argument("--validation-hard-fault",type=Path)
    p.add_argument("--shadow-sensitivity",type=Path)
    p.add_argument("--shadow-hard-fault",type=Path)
    p.add_argument("--output",type=Path)
    a=p.parse_args()
    if a.self_test:
        self_test(); return 0
    required=(a.processor,a.validation_sensitivity,a.validation_hard_fault,
              a.shadow_sensitivity,a.shadow_hard_fault,a.output)
    if any(x is None for x in required): p.error("all processor/validation/shadow/output arguments required")
    result=run(a.processor.resolve(),[x.resolve() for x in a.development_sensitivity],
               [x.resolve() for x in a.development_hard_fault],
               a.validation_sensitivity.resolve(),a.validation_hard_fault.resolve(),
               a.shadow_sensitivity.resolve(),a.shadow_hard_fault.resolve(),a.output.resolve())
    print(json.dumps({"decision":result["decision"],"selected":result["selected"]},sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
