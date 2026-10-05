#!/usr/bin/env python3
"""First-party fixed diffuse-field design. No audio-dependent fitting or promotion.

SOF TDFB public equations are a mathematical reference; no code/tables are copied.
The actual 33-tap real impulse responses, NOT ideal MVDR bins, are evaluated.
"""
from __future__ import annotations
import cmath
import math
import struct
from contracts import require

NFFT, TAPS, CENTER = 256, 33, 16
LOADS = (0.1, 1.0)


def solve(matrix, vector):
    """Bounded pivoted complex elimination for N<=4; no singular fallback."""
    n=len(vector); a=[list(map(complex,row))+[complex(v)] for row,v in zip(matrix,vector)]
    require(n in (1,2,4) and all(len(row)==n+1 for row in a), 'invalid linear system')
    for k in range(n):
        pivot=max(range(k,n),key=lambda i:abs(a[i][k]))
        require(abs(a[pivot][k])>1e-12,'singular spatial design')
        a[k],a[pivot]=a[pivot],a[k]; p=a[k][k]
        a[k]=[x/p for x in a[k]]
        for i in range(n):
            if i!=k:
                p=a[i][k];a[i]=[x-p*y for x,y in zip(a[i],a[k])]
    answer=[row[-1] for row in a]
    require(max(abs(sum(matrix[i][j]*answer[j] for j in range(n))-vector[i]) for i in range(n))<1e-9,'solve residual')
    return answer


def parameters(g):
    p=g['positions_m']; n=len(p); rate=g['sample_rate_hz']; u=g['direction'];ref=g['reference_mic']
    require(n in (1,2,4) and rate in (8000,16000,24000,32000,48000) and 0<=ref<n,'geometry/rate')
    require(len(u)==3 and all(math.isfinite(v) for v in u) and abs(sum(v*v for v in u)-1)<1e-6,'unit direction')
    require(all(len(v)==3 and all(math.isfinite(x) and abs(x)<=1 for x in v) for v in p),'position bounds')
    require(g['active_mask']==(1<<n)-1 and g['gains']==[1]*n and g['latency_samples']==[0]*n,'design scope: full calibrated array only')
    require(sorted(g['channel_map'])==list(range(n)),'PCM permutation')
    distances=[[math.sqrt(sum((x-y)**2 for x,y in zip(a,b))) for b in p] for a in p]
    require(all(distances[i][j]>=1e-6 for i in range(n) for j in range(i)), 'coincident microphones')
    tau=[sum((v-p[ref][k])*u[k] for k,v in enumerate(pos))*rate/343.0 for pos in p]
    common=math.ceil(max(distances[ref])*rate/343.0)+1+CENTER
    require(common>=CENTER and common+CENTER<128,'causal history bound')
    return n,rate,distances,tau,common


def coherence(distances, frequency):
    def sinc(x):return 1.0 if x==0 else math.sin(x)/x
    return [[sinc(2*math.pi*frequency*d/343.0) for d in row] for row in distances]


def design(g, diagonal_load):
    require(type(diagonal_load) is float and diagonal_load in LOADS,'unregistered diagonal load')
    n,rate,distances,tau,common=parameters(g)
    spectra=[[] for _ in range(n)]
    for b in range(NFFT//2+1):
        omega=2*math.pi*b/NFFT;a=[cmath.exp(1j*omega*t) for t in tau]
        r=coherence(distances,b*rate/NFFT)
        loaded=[[r[i][j]+(diagonal_load if i==j else 0) for j in range(n)] for i in range(n)]
        z=solve(loaded,a);den=sum(a[i].conjugate()*z[i] for i in range(n))
        require(den.real>1e-12 and abs(den.imag)<1e-9,'nonpositive MVDR normalization')
        for i in range(n):
            value=z[i].conjugate()/den.real*cmath.exp(-1j*omega*CENTER)
            spectra[i].append(complex(value.real,0) if b in (0,NFFT//2) else value)
    taps=[]
    for half in spectra:
        full=half+[v.conjugate() for v in reversed(half[1:-1])]
        row=[]
        for k in range(TAPS):
            impulse=sum(v*cmath.exp(2j*math.pi*b*k/NFFT) for b,v in enumerate(full))/NFFT
            require(abs(impulse.imag)<1e-10,'nonreal impulse')
            row.append(impulse.real*(0.5-0.5*math.cos(2*math.pi*k/(TAPS-1))))
        taps.append(row)
    dc=sum(sum(row) for row in taps)
    require(math.isfinite(dc) and 0.1<dc<10,'invalid aggregate DC normalization')
    f32=lambda v:struct.unpack('<f',struct.pack('<f',v))[0]
    taps=[[f32(v/dc) for v in row] for row in taps]
    require(sum(abs(v) for row in taps for v in row)<=64 and max(abs(v) for row in taps for v in row)<=16,'unsafe coefficients')
    return {'schema_version':1,'kind':'fixed-diffuse-spatial-fir33','diagonal_load':diagonal_load,'geometry':g,
            'nfft':NFFT,'taps_per_microphone':TAPS,'tap_start_samples':common-CENTER,'common_delay_samples':common,
            'dc_normalization_before_f32':dc,'coefficients':taps,'shipping_authority':False}


def response(bank):
    g=bank['geometry'];n,rate,distances,tau,common=parameters(g);taps=bank['coefficients'];rows=[]
    require(bank['common_delay_samples']==common and bank['tap_start_samples']==common-CENTER,'bank timing')
    for f in (0,200,500,1000,2000,3000,4000,6000,7000):
        if f>rate/2:continue
        omega=2*math.pi*f/rate
        h=[sum(v*cmath.exp(-1j*omega*(k+bank['tap_start_samples'])) for k,v in enumerate(row)) for row in taps]
        a=[cmath.exp(1j*omega*t) for t in tau];look=sum(x*y for x,y in zip(h,a))
        white=sum(abs(v)**2 for v in h);r=coherence(distances,f)
        diffuse=sum(h[i]*r[i][j]*h[j].conjugate() for i in range(n) for j in range(n)).real
        db=lambda a,b:10*math.log10(max(a,1e-30)/max(b,1e-30))
        rows.append({'frequency_hz':f,'look_gain_db':db(abs(look)**2,1),'wng_db':db(abs(look)**2,white),
                     'diffuse_di_db':db(abs(look)**2,diffuse),'aligned_transfer_error':abs(look*cmath.exp(1j*omega*common)-1)})
    return rows


def config_text(g, bank):
    # Reuse the existing geometry text format; mode4 appends explicit taps.
    from array_qualification import geometry_text
    base=geometry_text(g,'lagrange3').decode().split()
    base[3]='4'
    return (' '.join(base)+'\n'+' '.join(format(v,'.9g') for row in bank['coefficients'] for v in row)+'\n').encode()
