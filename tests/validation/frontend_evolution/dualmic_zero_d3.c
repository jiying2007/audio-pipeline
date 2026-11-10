/* D3 isolated controlled AGC replay. No production default changes. */
#include "enhance/ap_enhance.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
void d3_agc_init(ap_agc_state_t *, float, float);
void d3_agc_process_controlled(ap_agc_state_t *, float *, uint32_t, int);
_Static_assert(sizeof(float)==4 && sizeof(ap_agc_state_t)==12, "exact f32 state required");
typedef struct { uint32_t allow, reset; float before, after; } control_t;
_Static_assert(sizeof(control_t)==16, "exact control required");

static int finite_input(const float *x) {
    for (unsigned i=0;i<160;i++) if (!isfinite(x[i])) return 0;
    return 1;
}
static float applied(const ap_agc_state_t *s, float peak, int allow) {
    float gain=s->gain;
    if (!allow && gain>1.0f) gain=1.0f;
    if (peak*gain>s->limiter_linear && peak>1.0e-6f) gain=s->limiter_linear/peak;
    return gain;
}
static int selftest(void) {
    unsigned checks=0;
    const float starts[]={0.25f,1.0f,8.0f};
    for(unsigned a=0;a<2;a++) for(unsigned g=0;g<3;g++) for(unsigned k=0;k<4;k++) {
        ap_agc_state_t b,t; float x[160],y[160];
        ap_agc_init(&b,-20.0f,-2.0f); t=b; b.gain=t.gain=starts[g];
        for(unsigned i=0;i<160;i++) x[i]= k==0 ? 0.0f : k==1 ? -0.0f : k==2 ? 1.0e-20f : (i%2 ? 0.2f : -0.2f);
        memcpy(y,x,sizeof x);
        ap_agc_process_controlled(&b,x,160,(int)a);
        d3_agc_process_controlled(&t,y,160,(int)a);
        if(k>=2) {
            if(memcmp(&b,&t,sizeof b)||memcmp(x,y,sizeof x)) return 1;
        } else {
            float expected=b.gain>starts[g]?starts[g]:b.gain;
            if(memcmp(&t.gain,&expected,4)) return 1;
            for(unsigned i=0;i<160;i++) if(y[i]!=0.0f) return 1;
        }
        checks++;
    }
    float invalid[160]={0};
    invalid[12]=NAN; if(finite_input(invalid)) return 1;
    invalid[12]=INFINITY; if(finite_input(invalid)) return 1;
    invalid[12]=-INFINITY; if(finite_input(invalid)) return 1;
    printf("D3_ENGINEERING_SELF_TEST_PASS cases=%u invalid=3\n",checks);
    return 0;
}
int main(int argc,char **argv) {
    uint32_t endian=1;
    if(*(unsigned char *)&endian!=1) return 2;
    if(argc==2 && !strcmp(argv[1],"--self-test")) return selftest();
    if(argc!=9) return 2;
    float target;
    if(!strcmp(argv[7],"call")) target=-20.0f;
    else if(!strcmp(argv[7],"assistant")) target=-18.0f;
    else return 2;
    char *end; unsigned long frames=strtoul(argv[8],&end,10);
    if(*end||frames==0||frames>1000) return 2;
    FILE *in=fopen(argv[1],"rb"),*ref=fopen(argv[2],"rb"),*ctl=fopen(argv[3],"rb");
    FILE *bo=fopen(argv[4],"wb"),*co=fopen(argv[5],"wb"),*trace=fopen(argv[6],"wb");
    if(!in||!ref||!ctl||!bo||!co||!trace) return 2;
    ap_agc_state_t b,t; ap_agc_init(&b,target,-2.0f); d3_agc_init(&t,target,-2.0f);
    unsigned resets=0,zeros=0,held=0;
    for(unsigned long frame=0;frame<frames;frame++) {
        float x[160],y[160],expected[160],peak=0.0f; control_t control;
        if(fread(x,4,160,in)!=160 || fread(expected,4,160,ref)!=160 ||
           fread(&control,sizeof control,1,ctl)!=1 || control.allow>1 || control.reset>1 ||
           !isfinite(control.before)||!isfinite(control.after)||!finite_input(x)||!finite_input(expected)) return 3;
        uint32_t zero=1;
        for(unsigned i=0;i<160;i++) { if(x[i]!=0.0f) zero=0; if(fabsf(x[i])>peak) peak=fabsf(x[i]); }
        memcpy(y,x,sizeof x);
        if(control.reset) { ap_agc_init(&b,target,-2.0f); d3_agc_init(&t,target,-2.0f); resets++; }
        ap_agc_state_t before_b=b,before_t=t;
        if(memcmp(&b.gain,&control.before,4)) return 4;
        ap_agc_process_controlled(&b,x,160,(int)control.allow);
        d3_agc_process_controlled(&t,y,160,(int)control.allow);
        if(memcmp(&b.gain,&control.after,4)||memcmp(x,expected,sizeof x)) return 4;
        if(!finite_input(x)||!finite_input(y)||!isfinite(t.gain)) return 5;
        ap_agc_state_t state[4]={before_b,b,before_t,t};
        float gains[2]={applied(&b,peak,(int)control.allow),applied(&t,peak,(int)control.allow)};
        uint32_t flags[3]={control.allow,control.reset,zero};
        if(fwrite(x,4,160,bo)!=160||fwrite(y,4,160,co)!=160||
           fwrite(state,sizeof state,1,trace)!=1||fwrite(gains,sizeof gains,1,trace)!=1||
           fwrite(flags,sizeof flags,1,trace)!=1) return 6;
        zeros+=zero;
        if(zero && memcmp(&before_t.gain,&t.gain,4)==0) held++;
    }
    if(fgetc(in)!=EOF||fgetc(ref)!=EOF||fgetc(ctl)!=EOF||ferror(in)||ferror(ref)||ferror(ctl)) return 3;
    if(fclose(in)||fclose(ref)||fclose(ctl)||fclose(bo)||fclose(co)||fclose(trace)) return 6;
    printf("D3_CONTROLLED_REPLAY_COMPLETE frames=%lu resets=%u zero_frames=%u held_zero_frames=%u\n",frames,resets,zeros,held);
    return 0;
}
