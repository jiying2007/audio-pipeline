/* D35 standalone post-frame observer; no AEC, feedback, truth or future reads. */
#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    uint32_t tested,valid;
    int lag;
    double rr,maximum,chosen,zero;
} feature_t;

static int observe(const float history[1696],const float residual[160],uint32_t tested,feature_t *out) {
    double scores[1536],rr=0.0;uint32_t lag,i;
    if (!tested || tested>1536u) return 0;
    *out=(feature_t){tested,0u,-1,0.0,-1.0,-1.0,-1.0};
    for (i=0u;i<160u;++i) { double r=(double)residual[i];rr+=r*r; }
    out->rr=rr;
    for (lag=0u;lag<tested;++lag) {
        double xx=0.0,rx=0.0;
        for (i=0u;i<160u;++i) {
            double x=(double)history[1536u+i-lag],r=(double)residual[i];xx+=x*x;rx+=r*x;
        }
        scores[lag]=(rr>0.0 && xx>0.0) ? rx*rx/(rr*xx) : -1.0;
        if (!isfinite(scores[lag]) || scores[lag]<-1.0 || scores[lag]>1.0+1e-12) return 0;
        if (!lag) out->zero=scores[lag];
        if (scores[lag]>=0.0) {
            ++out->valid;
            if (scores[lag]>out->maximum) out->maximum=scores[lag];
        }
    }
    if (out->valid) for (lag=0u;lag<tested;++lag) if (scores[lag]>=0.0 && scores[lag]>=out->maximum-1e-12) {
        out->lag=(int)lag;out->chosen=scores[lag];break;
    }
    return isfinite(rr);
}

static int self_test(void) {
    float history[1696],residual[160];uint32_t state=0x12345678u,i;feature_t f;
    for (i=0u;i<1696u;++i) {
        state^=state<<13;state^=state>>17;state^=state<<5;
        history[i]=(float)((int32_t)(state&65535u)-32768)/65536.0f;
    }
    for (i=0u;i<160u;++i) residual[i]=-history[1536u+i-7u];
    if (!observe(history,residual,1536u,&f) || f.lag!=7 || fabs(f.maximum-1.0)>1e-12 || f.valid!=1536u) return 10;
    for (i=0u;i<1696u;++i) history[i]=1.0f;
    for (i=0u;i<160u;++i) residual[i]=1.0f;
    if (!observe(history,residual,1u,&f) || f.tested!=1u || f.valid!=1u || f.lag || f.zero!=1.0) return 11;
    if (!observe(history,residual,1536u,&f) || f.lag || f.chosen!=1.0 || f.maximum!=1.0) return 12;
    memset(history,0,sizeof(history));
    if (!observe(history,residual,1536u,&f) || f.valid || f.lag!=-1 || f.maximum!=-1.0 || f.zero!=-1.0) return 13;
    for (i=0u;i<1696u;++i) history[i]=1.0f;
    memset(residual,0,sizeof(residual));
    if (!observe(history,residual,1536u,&f) || f.valid || f.rr!=0.0 || f.maximum!=-1.0) return 14;
    puts("D35_OBSERVER_SELF_TEST_PASS delay/antiphase/tie/zero/startup");return 0;
}

static int number(const char *text,uint32_t *value) {
    unsigned long parsed;char *end;const char *p;
    if (!*text) return 0;
    for (p=text;*p;++p) if (*p<'0' || *p>'9') return 0;
    errno=0;parsed=strtoul(text,&end,10);
    if (errno || *end || !parsed || parsed>10000ul) return 0;
    *value=(uint32_t)parsed;return 1;
}

static int length(FILE *stream,long expected) {
    return fseek(stream,0L,SEEK_END)==0 && ftell(stream)==expected && fseek(stream,0L,SEEK_SET)==0;
}

int main(int argc,char **argv) {
    float history[1696]={0},residual[160],reference[160];FILE *inputs[2]={NULL,NULL},*output=NULL;
    uint32_t frames=0u,frame,i;uint16_t endian=1u;int result=0;unsigned long long candidates=0ull;feature_t f;
    if (argc==2 && strcmp(argv[1],"--self-test")==0) return self_test();
    if (argc!=5 || !number(argv[3],&frames) || sizeof(float)!=4u || *(const unsigned char *)&endian!=1u) {
        fputs("D35_INVALID_ARGUMENT_REJECT observer_calls=0\n",stderr);return 2;
    }
    for (i=0u;i<2u;++i) {
        inputs[i]=fopen(argv[i+1u],"rb");
        if (!inputs[i] || !length(inputs[i],(long)frames*640L)) { result=4;goto done; }
    }
    output=fopen(argv[4],"wb");if (!output) { result=4;goto done; }
    if (fputs("frame,tested_lags,valid_lags,residual_energy,max_cos2,chosen_lag,chosen_cos2,zero_lag_cos2\n",output)==EOF) { result=5;goto done; }
    for (frame=0u;frame<frames;++frame) {
        uint32_t start=frame*160u,tested=start<1535u ? start+1u : 1536u;
        if (fread(reference,sizeof(float),160u,inputs[0])!=160u || fread(residual,sizeof(float),160u,inputs[1])!=160u) { result=4;goto done; }
        for (i=0u;i<160u;++i) if (!isfinite(reference[i]) || !isfinite(residual[i])) { result=6;goto done; }
        memcpy(history+1536u,reference,sizeof(reference));
        if (!observe(history,residual,tested,&f)) { result=6;goto done; }
        candidates+=(unsigned long long)tested;
        if (fprintf(output,"%u,%u,%u,%.17g,%.17g,%d,%.17g,%.17g\n",frame,f.tested,f.valid,f.rr,f.maximum,f.lag,f.chosen,f.zero)<0) { result=5;goto done; }
        memmove(history,history+160u,1536u*sizeof(float));
    }
done:
    for (i=0u;i<2u;++i) if (inputs[i] && fclose(inputs[i])) result=7;
    if (output && fclose(output)) result=7;
    if (!result) printf("{\"frames\":%u,\"observer_calls\":%u,\"lag_candidates\":%llu,\"aec_calls\":0,\"observer_scoped_bytes\":%zu}\n",frames,frames,candidates,sizeof(history)+sizeof(reference)+sizeof(residual)+1536u*sizeof(double)+sizeof(f));
    return result;
}
