#include "device_transition_d28.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int number(const char *text,uint32_t *value) {
    uint32_t n=0u;const unsigned char *p=(const unsigned char *)text;
    if (!*p || (*p=='0' && p[1])) return 0;
    while (*p) { if (*p<'0' || *p>'9' || n>10000u) return 0;n=n*10u+(uint32_t)(*p-'0');++p; }
    if (!n || n>10000u) return 0;
    *value=n;return 1;
}
static int length(FILE *f,long expected) {
    return fseek(f,0,SEEK_END)==0 && ftell(f)==expected && fseek(f,0,SEEK_SET)==0;
}
static int self_test(void) {
    d28_transition_t s={0u,0u,0u,0u},saved;uint32_t i;float a=-0.0f,b=0.75f,out;
    if (!d28_begin(&s,1u) || d28_alpha(&s)!=0.0) return 10;
    out=d28_mix(a,b,d28_alpha(&s));if (memcmp(&out,&a,sizeof(a))) return 11;
    saved=s;if (d28_begin(&s,0u) || memcmp(&s,&saved,sizeof(s))) return 12;
    for (i=0u;i<D28_SAMPLES;++i) {
        if (s.pos!=i || s.remaining!=D28_SAMPLES-i || d28_alpha(&s)!=(double)i/319.0) return 13;
        if (i==319u) { out=d28_mix(a,b,d28_alpha(&s));if (memcmp(&out,&b,sizeof(b))) return 14; }
        d28_advance(&s);
    }
    if (s.remaining || d28_alpha(&s)!=1.0 || !d28_begin(&s,0u)) return 15;
    d28_advance(&s);d28_reset(&s);if (s.bank || s.remaining || s.pos || s.from_bank) return 16;
    saved=s;if (d28_begin(&s,0u) || d28_begin(&s,2u) || memcmp(&s,&saved,sizeof(s))) return 17;
    if (!d28_begin(&s,1u)) return 18;
    for (i=0u;i<160u;++i) d28_advance(&s);
    if (s.remaining!=160u || s.pos!=160u) return 19;
    puts("D28_SELF_TEST_PASS endpoints/atomic-overlap/inactive/two-frame/EOS");return 0;
}
int main(int argc,char **argv) {
    static const char *names[]={"echo.f32le","residual.f32le","transition.csv"};
    FILE *inputs[5]={NULL},*outputs[3]={NULL};uint32_t frames=0u,frame,i,events=0u,mixed=0u,calls=0u;
    int fade,future,result=0;uint16_t endian=1u;char path[1024];
    d28_transition_t state={0u,0u,0u,0u};float traces[4][160],out[2][160];
    if (argc==2 && strcmp(argv[1],"--self-test")==0) return self_test();
    if (argc!=10) return 2;
    fade=strcmp(argv[7],"fade")==0;future=strcmp(argv[9],"future")==0;
    if (!number(argv[6],&frames) || (!fade && strcmp(argv[7],"hard")) ||
        (!future && strcmp(argv[9],"normal")) || (future && !fade) ||
        *(const unsigned char *)&endian!=1u || sizeof(float)!=4u) {
        fprintf(stderr,"D28_INVALID_ARGUMENT_REJECT transition_calls=0\n");return 2;
    }
    for (i=0u;i<5u;++i) {
        inputs[i]=fopen(argv[i+1u],"rb");
        if (!inputs[i] || !length(inputs[i],(long)frames*(i==4u ? 5L : 640L))) { result=4;goto done; }
    }
    for (i=0u;i<3u;++i) {
        int n=snprintf(path,sizeof(path),"%s/%s",argv[8],names[i]);
        if (n<0 || (size_t)n>=sizeof(path)) { result=2;goto done; }
        outputs[i]=fopen(path,"wb");if (!outputs[i]) { result=4;goto done; }
    }
    if (fprintf(outputs[2],"frame,active,far,dt,bank,change,remaining_after_frame,alpha_first,alpha_last\n")<0) { result=8;goto done; }
    for (frame=0u;frame<frames;++frame) {
        unsigned char control[5];uint32_t sample;double first=1.0,last=1.0;
        if (fread(control,1u,5u,inputs[4])!=5u) { result=4;goto done; }
        for (i=0u;i<5u;++i) if (control[i]>1u) { result=4;goto done; }
        for (i=0u;i<4u;++i) {
            if (fread(traces[i],sizeof(float),160u,inputs[i])!=160u) { result=4;goto done; }
            for (sample=0u;sample<160u;++sample) {
                if (future && control[0]) traces[i][sample]*=i<2u ? 1.125f : -0.875f;
                if (!isfinite(traces[i][sample])) { result=7;goto done; }
            }
        }
        if (!control[0]) {
            if (control[3] || control[4]) { result=7;goto done; }
            d28_reset(&state);
        } else if (control[4]) {
            if (!d28_begin(&state,(uint32_t)control[3])) { result=7;goto done; }
            ++events;if (!fade) state.remaining=0u;
        } else if (state.bank!=(uint32_t)control[3]) { result=7;goto done; }
        ++calls;
        for (sample=0u;sample<160u;++sample) {
            double alpha=d28_alpha(&state);if (!sample) first=alpha;last=alpha;
            for (i=0u;i<2u;++i) {
                float current=traces[state.bank*2u+i][sample];
                out[i][sample]=state.remaining ? d28_mix(traces[state.from_bank*2u+i][sample],current,alpha) : current;
                if (!isfinite(out[i][sample])) { result=7;goto done; }
            }
            if (state.remaining) ++mixed;
            d28_advance(&state);
        }
        for (i=0u;i<2u;++i) if (fwrite(out[i],sizeof(float),160u,outputs[i])!=160u) { result=8;goto done; }
        if (fprintf(outputs[2],"%u,%u,%u,%u,%u,%u,%u,%.17g,%.17g\n",frame,(unsigned)control[0],(unsigned)control[1],
            (unsigned)control[2],state.bank,(unsigned)control[4],state.remaining,first,last)<0) { result=8;goto done; }
    }
done:
    for (i=0u;i<5u;++i) if (inputs[i] && fclose(inputs[i])) result=9;
    for (i=0u;i<3u;++i) if (outputs[i] && fclose(outputs[i])) result=9;
    if (!result) printf("{\"frames\":%u,\"samples\":%u,\"transition_calls\":%u,\"switch_count\":%u,\"mixed_samples\":%u,\"remaining\":%u,\"transition_state_bytes\":%zu,\"aec_calls\":0,\"selector_calls\":0}\n",
        frames,frames*160u,calls,events,mixed,state.remaining,sizeof(state));
    return result;
}
