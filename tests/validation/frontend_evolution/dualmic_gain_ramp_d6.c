/* D6 isolated output-domain ramp. Original production state is unchanged. */
#include "candidate-api.h"
#include <fenv.h>
#include <float.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
_Static_assert(sizeof(float)==4 && FLT_RADIX==2 && FLT_MANT_DIG==24 &&
               FLT_MAX_EXP==128 && FLT_EVAL_METHOD==0, "IEEE binary32 required");
_Static_assert(sizeof(ap_agc_state_t)==12 && sizeof(d6_ramp_state_t)==8 &&
               sizeof(d6_observation_t)==8, "exact state layout required");
typedef struct { uint32_t allow, reset; float before, after; } control_t;
_Static_assert(sizeof(control_t)==16, "exact control required");

static void reset_extra(d6_ramp_state_t *r) { r->previous=0.0f; r->initialized=0u; }
static int finite_input(const float *x) {
    for(unsigned i=0;i<160;i++) if(!isfinite(x[i])) return 0;
    return 1;
}
static int finite_state(const ap_agc_state_t *s) {
    return isfinite(s->gain) && isfinite(s->target_linear) && isfinite(s->limiter_linear);
}
static int valid_extra(const d6_ramp_state_t *r) {
    return isfinite(r->previous) && r->initialized<=1u;
}
static float cap(float c,float peak,float limit,int allow) {
    if(!allow && c>1.0f) c=1.0f;
    if(peak*c>limit && peak>1.0e-6f) c=limit/peak;
    return c;
}
static float clamp(float x,float limit) {
    return x < -limit ? -limit : (x > limit ? limit : x);
}
static int same(float a,float b) { return memcmp(&a,&b,4)==0; }
static int check_case(float target,float initial,float level,int allow,
                      float previous,unsigned initialized,unsigned *rises,
                      unsigned *falls,unsigned *neutral) {
    ap_agc_state_t b,t; d6_ramp_state_t extra={previous,initialized};
    d6_observation_t obs;
    float input[160],x[160],y[160],gains[160],peak=fabsf(level);
    ap_agc_init(&b,target,-2.0f); d6_agc_init(&t,target,-2.0f);
    if(memcmp(&b,&t,12)) return 1;
    b.gain=t.gain=initial;
    for(unsigned i=0;i<160;i++) input[i]=(i%2) ? level : -level;
    memcpy(x,input,sizeof x);memcpy(y,input,sizeof y);
    ap_agc_process_controlled(&b,x,160,allow);
    float G=cap(b.gain,peak,b.limiter_linear,allow);
    /* initialized==2 is a self-test selector, never an algorithm mode. */
    if(initialized==2u) { extra.initialized=1u;extra.previous=G; }
    float S=extra.initialized ? cap(extra.previous,peak,b.limiter_linear,allow) : G;
    if(!finite_state(&t)||!finite_input(y)||!valid_extra(&extra)) return 1;
    d6_agc_process_controlled(&t,y,160,allow,&extra,gains,&obs);
    if(memcmp(&b,&t,12)||!finite_state(&t)||!finite_input(y)||!finite_input(gains)||
       !valid_extra(&extra)||extra.initialized!=1u||!same(obs.start,S)||
       !same(obs.end,G)||!same(cap(G,peak,b.limiter_linear,allow),G)||
       !same(gains[159],G)||!same(extra.previous,G)) return 1;
    const float delta=G-S;
    for(unsigned i=0;i<160;i++) {
        const float weight=(float)(i+1u)/160.0f;
        const float product=delta*weight;
        const float raw=(i==159u) ? G : S+product;
        const float expected=cap(raw,peak,b.limiter_linear,allow);
        const float pcm=clamp(input[i]*expected,b.limiter_linear);
        if(!same(gains[i],expected)||!same(y[i],pcm)||
           (!allow && gains[i]>1.0f)||fabsf(y[i])>b.limiter_linear) return 1;
    }
    if(same(S,G)) {
        if(memcmp(x,y,sizeof x)) return 1;
        for(unsigned i=0;i<160;i++) if(!same(gains[i],G)) return 1;
        (*neutral)++;
    }
    *rises+=(S<G);*falls+=(S>G);
    return 0;
}
static int selftest(void) {
    const float starts[]={.25f,.75f,1.0f,2.0f,8.0f};
    const float levels[]={0.0f,-0.0f,1.0e-20f,.01f,.2f,1.0f,2.0f,
                         nextafterf(1.0e-6f,0.0f),1.0e-6f,nextafterf(1.0e-6f,1.0f)};
    unsigned cases=0,rises=0,falls=0,neutral=0;
    for(unsigned p=0;p<2;p++) for(unsigned a=0;a<2;a++)
    for(unsigned g=0;g<5;g++) for(unsigned k=0;k<10;k++)
    for(unsigned prev=0;prev<5;prev++) for(unsigned init=0;init<3;init++) {
        if(check_case(p ? -18.0f : -20.0f,starts[g],levels[k],(int)a,
                      starts[prev],init,&rises,&falls,&neutral)) return 1;
        cases++;
    }
    /* Independent continuous histories include gate changes and exact resets. */
    for(unsigned p=0;p<2;p++) {
        ap_agc_state_t b,t;d6_ramp_state_t extra;reset_extra(&extra);
        ap_agc_init(&b,p ? -18.0f : -20.0f,-2.0f);d6_agc_init(&t,p ? -18.0f : -20.0f,-2.0f);
        for(unsigned frame=0;frame<20;frame++) {
            float x[160],y[160],gains[160];d6_observation_t obs;
            if(frame==7u||frame==13u) {
                ap_agc_init(&b,p ? -18.0f : -20.0f,-2.0f);
                d6_agc_init(&t,p ? -18.0f : -20.0f,-2.0f);reset_extra(&extra);
            }
            const d6_ramp_state_t before=extra;
            const float level=levels[frame%10u],peak=fabsf(level);
            const int allow=(int)(frame%2u);
            for(unsigned i=0;i<160;i++) x[i]=(i%2) ? level : -level;
            memcpy(y,x,sizeof x);
            ap_agc_process_controlled(&b,x,160,allow);
            d6_agc_process_controlled(&t,y,160,allow,&extra,gains,&obs);
            const float G=cap(b.gain,peak,b.limiter_linear,allow);
            const float S=before.initialized ? cap(before.previous,peak,b.limiter_linear,allow) : G;
            if(memcmp(&b,&t,12)||!same(S,obs.start)||!same(G,obs.end)||
               !same(extra.previous,G)||extra.initialized!=1u||
               (!before.initialized && memcmp(x,y,sizeof x))) return 1;
        }
    }
    const float bad[]={NAN,INFINITY,-INFINITY};
    for(unsigned k=0;k<3;k++) {
        float x[160]={0};x[12]=bad[k];if(finite_input(x)) return 1;
        ap_agc_state_t s={bad[k],1,1};if(finite_state(&s)) return 1;
        s.gain=1;s.target_linear=bad[k];if(finite_state(&s)) return 1;
        s.target_linear=1;s.limiter_linear=bad[k];if(finite_state(&s)) return 1;
        d6_ramp_state_t e={bad[k],1u};if(valid_extra(&e)) return 1;
    }
    d6_ramp_state_t bad_flag={1.0f,2u};if(valid_extra(&bad_flag)) return 1;
    if(!rises||!falls||!neutral) return 1;
    printf("D6_ENGINEERING_SELF_TEST_PASS cases=%u rises=%u falls=%u neutral=%u\n",
           cases,rises,falls,neutral);
    return 0;
}
int main(int argc,char **argv) {
    uint32_t endian=1;
    if(*(unsigned char *)&endian!=1 || fegetround()!=FE_TONEAREST) return 2;
    if(argc==2 && !strcmp(argv[1],"--self-test")) return selftest();
    if(argc!=10) return 2;
    float target;
    if(!strcmp(argv[8],"call")) target=-20.0f;
    else if(!strcmp(argv[8],"assistant")) target=-18.0f;
    else return 2;
    char *end;unsigned long frames=strtoul(argv[9],&end,10);
    if(*end||frames==0||frames>1000) return 2;
    FILE *in=fopen(argv[1],"rb"),*ref=fopen(argv[2],"rb"),*ctl=fopen(argv[3],"rb");
    FILE *bo=fopen(argv[4],"wb"),*co=fopen(argv[5],"wb"),*trace=fopen(argv[6],"wb");
    FILE *go=fopen(argv[7],"wb");
    if(!in||!ref||!ctl||!bo||!co||!trace||!go) return 2;
    ap_agc_state_t b,t;d6_ramp_state_t extra;reset_extra(&extra);
    ap_agc_init(&b,target,-2.0f);d6_agc_init(&t,target,-2.0f);
    unsigned resets=0,zeros=0;
    for(unsigned long frame=0;frame<frames;frame++) {
        float x[160],y[160],expected[160],gains[160];control_t control;d6_observation_t obs;
        if(fread(x,4,160,in)!=160||fread(expected,4,160,ref)!=160||
           fread(&control,16,1,ctl)!=1||control.allow>1||control.reset>1||
           !isfinite(control.before)||!isfinite(control.after)||!finite_input(x)||!finite_input(expected)) return 3;
        uint32_t zero=1;
        for(unsigned i=0;i<160;i++) if(x[i]!=0.0f) zero=0;
        memcpy(y,x,sizeof x);
        if(control.reset) {
            ap_agc_init(&b,target,-2.0f);d6_agc_init(&t,target,-2.0f);reset_extra(&extra);resets++;
        }
        ap_agc_state_t before_b=b,before_t=t;d6_ramp_state_t before_extra=extra;
        if(memcmp(&b.gain,&control.before,4)||memcmp(&b,&t,12)) return 4;
        if(!finite_state(&b)||!finite_state(&t)||!valid_extra(&extra)) return 5;
        ap_agc_process_controlled(&b,x,160,(int)control.allow);
        d6_agc_process_controlled(&t,y,160,(int)control.allow,&extra,gains,&obs);
        if(memcmp(&b.gain,&control.after,4)||memcmp(x,expected,sizeof x)||memcmp(&b,&t,12)) return 4;
        if(!finite_input(x)||!finite_input(y)||!finite_input(gains)||!finite_state(&b)||
           !finite_state(&t)||!valid_extra(&extra)||!isfinite(obs.start)||!isfinite(obs.end)) return 5;
        ap_agc_state_t state[4]={before_b,b,before_t,t};
        d6_ramp_state_t ramps[2]={before_extra,extra};
        uint32_t flags[3]={control.allow,control.reset,zero};
        if(fwrite(x,4,160,bo)!=160||fwrite(y,4,160,co)!=160||fwrite(gains,4,160,go)!=160||
           fwrite(state,48,1,trace)!=1||fwrite(ramps,16,1,trace)!=1||
           fwrite(&obs,8,1,trace)!=1||fwrite(flags,12,1,trace)!=1) return 6;
        zeros+=zero;
    }
    if(fgetc(in)!=EOF||fgetc(ref)!=EOF||fgetc(ctl)!=EOF||ferror(in)||ferror(ref)||ferror(ctl)) return 3;
    if(fclose(in)||fclose(ref)||fclose(ctl)||fclose(bo)||fclose(co)||fclose(trace)||fclose(go)) return 6;
    printf("D6_CONTROLLED_REPLAY_COMPLETE frames=%lu resets=%u zero_frames=%u\n",frames,resets,zeros);
    return 0;
}
