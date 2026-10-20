#ifndef DEVICE_GUARD_INVALIDATION_D33_H
#define DEVICE_GUARD_INVALIDATION_D33_H
#include <math.h>
#include <stdint.h>
#include <string.h>

typedef struct {
    double cme,cre,ratio;
    uint32_t stable,armed,hold;
    uint8_t valid_me,valid_re;
} d33_guard_t;

/* The only D33 algorithm change: invalidate historical confidence on an actual notification. */
static void d33_invalidate(d33_guard_t *s,int feedback,int notified) {
    if (feedback && notified) memset(s,0,sizeof(*s));
}

/* Read previous-frame observations before processing the current frame. */
static int d33_gate(d33_guard_t *s,int far) {
    if (!far) { memset(s,0,sizeof(*s));return 0; }
    if (s->armed && s->valid_me && s->valid_re && s->cme>.2 && s->cme<.9 && s->cre<.1 && s->ratio>.2) s->hold=3u;
    else if (s->hold) --s->hold;
    return s->hold>0u;
}

/* No selected/shadow feedback and no truth/label inputs. */
static int d33_observe(d33_guard_t *s,const float *mic,const float *echo,const float *residual,int far,int detected_dt) {
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

static int d33_guard_self_test(void) {
    d33_guard_t s={0};float mic[160],echo[160],residual[160];uint32_t i,k;
    s.cme=.5;s.cre=.01;s.ratio=.5;s.stable=100u;s.armed=1u;s.hold=3u;s.valid_me=1u;s.valid_re=1u;
    {
        d33_guard_t saved=s;const unsigned char *bytes=(const unsigned char *)&s;
        d33_invalidate(&s,0,1);if (memcmp(&s,&saved,sizeof(s))) return 8;
        d33_invalidate(&s,1,0);if (memcmp(&s,&saved,sizeof(s))) return 9;
        d33_invalidate(&s,1,1);
        for (i=0u;i<sizeof(s);++i) if (bytes[i]) return 10;
    }
    for (i=0u;i<160u;++i) { mic[i]=1.0f;echo[i]=1.0f;residual[i]=0.0f; }
    for (k=0u;k<100u;++k) {
        if (d33_gate(&s,1) || !d33_observe(&s,mic,echo,residual,1,0) || s.armed!=(uint32_t)(k==99u)) return 1;
    }
    if (d33_gate(&s,1)) return 2;
    for (i=0u;i<160u;++i) { residual[i]=(i&1u) ? -1.0f : 1.0f;mic[i]=echo[i]+residual[i]; }
    if (!d33_observe(&s,mic,echo,residual,1,0) || !d33_gate(&s,1) || s.hold!=3u) return 3;
    for (i=0u;i<160u;++i) { mic[i]=echo[i];residual[i]=0.0f; }
    if (!d33_observe(&s,mic,echo,residual,1,0)) return 4;
    for (k=0u;k<3u;++k) if (d33_gate(&s,1)!=(k<2u) || s.hold!=2u-k) return 5;
    if (d33_gate(&s,0) || s.armed || s.stable || s.hold) return 6;
    memset(mic,0,sizeof(mic));memset(echo,0,sizeof(echo));memset(residual,0,sizeof(residual));
    if (!d33_observe(&s,mic,echo,residual,1,0) || s.valid_me || s.valid_re || s.cme!=-1.0 || s.cre!=-1.0 || s.ratio!=-1.0 || d33_gate(&s,1)) return 7;
    return 0;
}
#endif

