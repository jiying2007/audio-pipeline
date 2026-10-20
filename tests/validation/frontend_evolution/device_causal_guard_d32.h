#ifndef DEVICE_CAUSAL_GUARD_D32_H
#define DEVICE_CAUSAL_GUARD_D32_H
#include <math.h>
#include <stdint.h>
#include <string.h>

typedef struct {
    double cme,cre,ratio;
    uint32_t stable,armed,hold;
    uint8_t valid_me,valid_re;
} d32_guard_t;

/* Read previous-frame observations before processing the current frame. */
static int d32_gate(d32_guard_t *s,int far) {
    if (!far) { memset(s,0,sizeof(*s));return 0; }
    if (s->armed && s->valid_me && s->valid_re && s->cme>.2 && s->cme<.9 && s->cre<.1 && s->ratio>.2) s->hold=3u;
    else if (s->hold) --s->hold;
    return s->hold>0u;
}

/* No selected/shadow feedback and no truth/label inputs. */
static int d32_observe(d32_guard_t *s,const float *mic,const float *echo,const float *residual,int far,int detected_dt) {
    double mm=0.0,ee=0.0,rr=0.0,me=0.0,re=0.0;uint32_t i;
    for (i=0u;i<160u;++i) {
        double m=(double)mic[i],e=(double)echo[i],r=(double)residual[i];
        mm+=m*m;ee+=e*e;rr+=r*r;me+=m*e;re+=r*e;
    }
    s->valid_me=(uint8_t)(mm>0.0 && ee>0.0);s->valid_re=(uint8_t)(rr>0.0 && ee>0.0);
    s->cme=s->valid_me ? (me*me)/(mm*ee) : -1.0;
    s->cre=s->valid_re ? (re*re)/(rr*ee) : -1.0;
    s->ratio=mm>0.0 ? rr/mm : -1.0;
    if (!isfinite(s->cme) || !isfinite(s->cre) || !isfinite(s->ratio) || s->cme>1.0+1e-12 || s->cre>1.0+1e-12) return 0;
    if (far && !detected_dt && s->valid_me && s->cme>.95 && s->ratio>=0.0 && s->ratio<.05) {
        if (s->stable<100u) ++s->stable;
        if (s->stable==100u) s->armed=1u;
    } else s->stable=0u;
    return 1;
}

static int d32_guard_self_test(void) {
    d32_guard_t s={0};float mic[160],echo[160],residual[160];uint32_t i,k;
    for (i=0u;i<160u;++i) { mic[i]=1.0f;echo[i]=1.0f;residual[i]=0.0f; }
    for (k=0u;k<100u;++k) {
        if (d32_gate(&s,1) || !d32_observe(&s,mic,echo,residual,1,0) || s.armed!=(uint32_t)(k==99u)) return 1;
    }
    if (d32_gate(&s,1)) return 2;
    for (i=0u;i<160u;++i) { residual[i]=(i&1u) ? -1.0f : 1.0f;mic[i]=echo[i]+residual[i]; }
    if (!d32_observe(&s,mic,echo,residual,1,0) || !d32_gate(&s,1) || s.hold!=3u) return 3;
    for (i=0u;i<160u;++i) { mic[i]=echo[i];residual[i]=0.0f; }
    if (!d32_observe(&s,mic,echo,residual,1,0)) return 4;
    for (k=0u;k<3u;++k) if (d32_gate(&s,1)!=(k<2u) || s.hold!=2u-k) return 5;
    if (d32_gate(&s,0) || s.armed || s.stable || s.hold) return 6;
    memset(mic,0,sizeof(mic));memset(echo,0,sizeof(echo));memset(residual,0,sizeof(residual));
    if (!d32_observe(&s,mic,echo,residual,1,0) || s.valid_me || s.valid_re || s.cme!=-1.0 || s.cre!=-1.0 || s.ratio!=-1.0 || d32_gate(&s,1)) return 7;
    return 0;
}
#endif
