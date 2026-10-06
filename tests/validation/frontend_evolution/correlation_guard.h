/* First-party FE04 research veto, not production DTD or matrix NCC.
 * Fixed lag/threshold design. No allocation, I/O, oracle labels or AEC feedback.
 */
#ifndef FE_LAG_CORRELATION_GUARD_H
#define FE_LAG_CORRELATION_GUARD_H
#include <math.h>
#include <stddef.h>
#include <string.h>
#define FE_CG_HOP 160u
#define FE_CG_WINDOW 320u
#define FE_CG_HISTORY 1344u
#define FE_CG_MAX_LAG 1023u
#define FE_CG_STEP 4u

typedef struct {
    float reference[FE_CG_HISTORY];
    float microphone[FE_CG_WINDOW];
    unsigned filled,blocked,release_count;
} fe_correlation_guard;
typedef struct {
    double score;
    unsigned lag,warm,blocked;
} fe_correlation_result;

static void fe_correlation_reset(fe_correlation_guard *s) {
    if(s)memset(s,0,sizeof(*s));
}
static int fe_correlation_process(fe_correlation_guard *s,const float *mic,
                                  const float *ref,size_t samples,int far,
                                  fe_correlation_result *out) {
    double sm=0.0,mm=0.0,variance,best=0.0;
    const double count=(double)(FE_CG_WINDOW/FE_CG_STEP);
    unsigned lag=0u,limit;
    if(!s || !mic || !ref || !out || samples!=FE_CG_HOP || (far!=0 && far!=1))return 0;
    for(unsigned k=0;k<FE_CG_HOP;++k)
        if(!isfinite(mic[k]) || !isfinite(ref[k]))return 0;
    memmove(s->reference,s->reference+FE_CG_HOP,(FE_CG_HISTORY-FE_CG_HOP)*sizeof(float));
    memcpy(s->reference+FE_CG_HISTORY-FE_CG_HOP,ref,FE_CG_HOP*sizeof(float));
    memmove(s->microphone,s->microphone+FE_CG_HOP,(FE_CG_WINDOW-FE_CG_HOP)*sizeof(float));
    memcpy(s->microphone+FE_CG_WINDOW-FE_CG_HOP,mic,FE_CG_HOP*sizeof(float));
    s->filled=s->filled>FE_CG_HISTORY-FE_CG_HOP ? FE_CG_HISTORY : s->filled+FE_CG_HOP;
    out->warm=s->filled>=FE_CG_WINDOW;
    if(out->warm) {
        limit=s->filled-FE_CG_WINDOW;if(limit>FE_CG_MAX_LAG)limit=FE_CG_MAX_LAG;
        for(unsigned k=0;k<FE_CG_WINDOW;k+=FE_CG_STEP) {
            const double m=s->microphone[k];sm+=m;mm+=m*m;
        }
        variance=mm-sm*sm/count;
        /* Numerical degeneracy guard, frozen before execution: raw moments of
         * DC/nearly-DC windows can cancel. They must not imply correlation1. */
        if(variance>1.0e-20 && variance>1.0e-12*mm)for(unsigned d=0;d<=limit;++d) {
            double sr=0.0,rr=0.0,mr=0.0,rv,cross,score;
            const unsigned begin=FE_CG_HISTORY-FE_CG_WINDOW-d;
            for(unsigned k=0;k<FE_CG_WINDOW;k+=FE_CG_STEP) {
                const double r=s->reference[begin+k],m=s->microphone[k];
                sr+=r;rr+=r*r;mr+=m*r;
            }
            rv=rr-sr*sr/count;
            if(rv<=1.0e-20 || rv<=1.0e-12*rr)continue;
            cross=mr-sm*sr/count;score=cross*cross/(variance*rv);
            if(score>1.0)score=1.0;
            if(score>best){best=score;lag=d;}
        }
    }
    if(!far){s->blocked=0u;s->release_count=0u;}
    else if(!out->warm || best<0.55){s->blocked=1u;s->release_count=0u;}
    else if(s->blocked) {
        if(best>=0.65) {
            ++s->release_count;
            if(s->release_count>=3u){s->blocked=0u;s->release_count=0u;}
        } else s->release_count=0u;
    } else s->release_count=0u;
    out->score=best;out->lag=lag;out->blocked=s->blocked;return 1;
}
#endif
