/* Actual controls for the finite FE04 guard; no acoustic success threshold. */
#include "correlation_guard.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
static unsigned assertions;
#define CHECK(x) do { ++assertions; if(!(x)) { fprintf(stderr,"check failed at line %d: %s\n",__LINE__,#x); return 1; } } while(0)
static uint32_t rng=17107u;
static float noise(void) {rng=rng*1664525u+1013904223u;return (float)((double)(rng>>8)/16777216.0-0.5);}
int main(void) {
    float source[6400],independent[6400],mic[160],ref[160];
    fe_correlation_guard s,before;fe_correlation_result r={0};
    unsigned controls=0u;double seconds;clock_t started;
    for(unsigned k=0;k<6400;++k){source[k]=noise();independent[k]=noise();}
    for(unsigned d=0;d<4;++d)for(unsigned polarity=0;polarity<2;++polarity) {
        const unsigned delays[4]={0u,97u,509u,1023u};
        const unsigned delay=delays[d];
        const float gain=polarity?-0.125f:2.0f;
        fe_correlation_reset(&s);
        for(unsigned f=0;f<30;++f) {
            for(unsigned j=0;j<160;++j){unsigned k=f*160+j;ref[j]=source[k];mic[j]=k>=delay?gain*source[k-delay]:0.0f;}
            CHECK(fe_correlation_process(&s,mic,ref,160,1,&r));
            if(f>=12u){CHECK(r.warm && !r.blocked);CHECK(r.lag==delay);CHECK(r.score>0.999999);}
        }
        ++controls;
    }
    /* Independent near noise should veto, then correlated-only input should
     * release. Gain/polarity controls above also prove it is not always frozen. */
    fe_correlation_reset(&s);
    for(unsigned f=0;f<30;++f) {
        for(unsigned j=0;j<160;++j){unsigned k=f*160+j;ref[j]=source[k];mic[j]=(k>=97u?.2f*source[k-97u]:0.0f)+(f<16u?independent[k]:0.0f);}
        CHECK(fe_correlation_process(&s,mic,ref,160,1,&r));
        if(f>=10u && f<16u)CHECK(r.blocked);
        if(f>=22u)CHECK(!r.blocked && r.score>0.999999);
    }
    ++controls;
    /* Constant/DC observations have no identifiable correlation, not score1. */
    for(unsigned j=0;j<160;++j){mic[j]=.1f;ref[j]=.2f;}
    fe_correlation_reset(&s);
    for(unsigned f=0;f<12;++f)CHECK(fe_correlation_process(&s,mic,ref,160,1,&r));
    CHECK(r.blocked && r.score==0.0);
    CHECK(fe_correlation_process(&s,mic,ref,160,0,&r));CHECK(!r.blocked);
    ++controls;
    before=s;mic[37]=NAN;
    CHECK(!fe_correlation_process(&s,mic,ref,160,1,&r));CHECK(!memcmp(&s,&before,sizeof(s)));
    mic[37]=0;
    CHECK(!fe_correlation_process(&s,mic,ref,159,1,&r));CHECK(!memcmp(&s,&before,sizeof(s)));
    CHECK(!fe_correlation_process(&s,mic,ref,160,2,&r));CHECK(!memcmp(&s,&before,sizeof(s)));
    CHECK(!fe_correlation_process(NULL,mic,ref,160,1,&r));
    fe_correlation_reset(&s);memset(&before,0,sizeof(before));CHECK(!memcmp(&s,&before,sizeof(s)));
    ++controls;
    /* Same-runner only: includes frame copies, not AEC/BF and not DUT timing. */
    started=clock();fe_correlation_reset(&s);
    for(unsigned f=0;f<200;++f) {
        for(unsigned j=0;j<160;++j){unsigned k=(f*160+j)%6400;ref[j]=source[k];mic[j]=.2f*source[(k+6400-97)%6400];}
        CHECK(fe_correlation_process(&s,mic,ref,160,1,&r));
    }
    seconds=(double)(clock()-started)/(double)CLOCKS_PER_SEC;
    printf("{\"status\":\"PASS\",\"controls\":%u,\"assertions\":%u,\"state_bytes\":%zu,\"benchmark_frames\":200,\"host_guard_cpu_ms_per_audio_second\":%.9g,\"timing_authority\":\"NONE_TARGET\"}\n",controls,assertions,sizeof(s),seconds*500.0);
    return 0;
}
