/* Research-local saved paired echo/residual -> canonical CALL/FULL downstream. */
#include "enhance/ap_enhance.h"
#include "sync/ap_sync.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* The locked D18 unity archive renamed this symbol for its capture observer. */
static uint64_t sync_calls;
int ap_sync_get_reference_d18_real(ap_sync_state_t *,uint32_t,float *);
int ap_sync_get_reference(ap_sync_state_t *state,uint32_t n,float *output) {
    ++sync_calls;return ap_sync_get_reference_d18_real(state,n,output);
}

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
static float clamp(float x,float limit) { return x < -limit ? -limit : x > limit ? limit : x; }
static float effective(const float *x,const ap_agc_state_t *s,int allow) {
    uint32_t i;float peak=0.0f,gain=s->gain;
    for (i=0u;i<160u;++i) if (fabsf(x[i])>peak) peak=fabsf(x[i]);
    if (!allow && gain>1.0f) gain=1.0f;
    if (peak*gain>s->limiter_linear && peak>1e-6f) gain=s->limiter_linear/peak;
    return gain;
}
static int self_test(void) {
    ap_agc_state_t agc;float x[160]={0};uint32_t i;
    ap_agc_init(&agc,-20.0f,-2.0f);agc.gain=.25f;
    ap_agc_process_controlled(&agc,x,160u,0);
    if (!(agc.gain>.25f && agc.gain<1.0f) || effective(x,&agc,0)>1.0f) return 20;
    for (i=0u;i<160u;++i) x[i]=i%2u ? 2.0f : -2.0f;
    ap_agc_process_controlled(&agc,x,160u,1);
    for (i=0u;i<160u;++i) if (fabsf(x[i])>agc.limiter_linear) return 21;
    puts("D40_SELF_TEST_PASS controlled-gain-state-recovery/limiter");return 0;
}
int main(int argc,char **argv) {
    static const char *names[]={"bypass.f32le","ns.f32le","final.f32le","control.csv"};
    FILE *in[3]={NULL},*out[4]={NULL};uint32_t frames=0u,frame=0u,i;int result=0;uint16_t endian=1u;
    float residual[160],echo[160],nsout[160],final[160];unsigned char gate[2];char path[1024];
    ap_ns_state_t ns;ap_agc_state_t agc;ap_vad_state_t vad;
    if (argc==2 && strcmp(argv[1],"--self-test")==0) return self_test();
    if (argc!=7 || !number(argv[4],&frames) || strcmp(argv[6],"full") ||
        sizeof(float)!=4u || *(const unsigned char *)&endian!=1u) return 2;
    for (i=0u;i<3u;++i) {
        in[i]=fopen(argv[i+1u],"rb");
        if (!in[i] || !length(in[i],(long)frames*(i==2u ? 2L : 640L))) { result=4;goto done; }
    }
    /* Reject malformed inputs before creating any output or invoking DSP. */
    for (frame=0u;frame<frames;++frame) {
        if (fread(residual,sizeof(float),160u,in[0])!=160u || fread(echo,sizeof(float),160u,in[1])!=160u ||
            fread(gate,1u,2u,in[2])!=2u || gate[0]>1u || gate[1]>1u) { result=4;goto done; }
        for (i=0u;i<160u;++i) if (!isfinite(residual[i]) || !isfinite(echo[i])) { result=4;goto done; }
    }
    for (i=0u;i<3u;++i) if (fseek(in[i],0,SEEK_SET)) { result=4;goto done; }
    for (i=0u;i<4u;++i) {
        int n=snprintf(path,sizeof(path),"%s/%s",argv[5],names[i]);
        if (n<0 || (size_t)n>=sizeof(path)) { result=2;goto done; }
        out[i]=fopen(path,"wbx");if (!out[i]) { result=4;goto done; }
    }
    ap_ns_init(&ns,160u);ap_agc_init(&agc,-20.0f,-2.0f);ap_vad_init(&vad);
    if (fprintf(out[3],"frame,far,dt,frequency_active,speech_probability,noise_rms_dbfs,residual_gain,agc_allow,gain_before,gain_after,effective_gain,vad_probability,vad_active,vad_noise_rms,vad_hangover\n")<0) { result=8;goto done; }
    for (frame=0u;frame<frames;++frame) {
        ap_ns_result_t nr;ap_vad_result_t vr;float before,gain;int allow;
        if (fread(residual,sizeof(float),160u,in[0])!=160u || fread(echo,sizeof(float),160u,in[1])!=160u || fread(gate,1u,2u,in[2])!=2u) { result=4;goto done; }
        ap_ns_process(&ns,AP_ENHANCE_FULL,.12f,residual,echo,nsout,160u,0,(int)gate[0],(int)gate[1],&nr);
        allow=!(gate[0] && !gate[1]);before=agc.gain;memcpy(final,nsout,sizeof(final));
        ap_agc_process_controlled(&agc,final,160u,allow);gain=effective(nsout,&agc,allow);
        ap_vad_process(&vad,final,160u,nr.speech_probability,1,&vr);
        if (sync_calls || nr.frequency_res_active!=0u || nr.residual_echo_gain!=1.0f || !isfinite(before) || !isfinite(agc.gain) ||
            !isfinite(gain) || (!allow && gain>1.0f) || !isfinite(nr.noise_rms_dbfs) ||
            !isfinite(nr.residual_echo_gain) || nr.residual_echo_gain<0.0f || nr.residual_echo_gain>1.0f ||
            !isfinite(nr.speech_probability) || nr.speech_probability<0.0f || nr.speech_probability>1.0f ||
            !isfinite(vr.probability) || vr.probability<0.0f || vr.probability>1.0f || !isfinite(vad.noise_rms)) { result=7;goto done; }
        for (i=0u;i<160u;++i) if (!isfinite(nsout[i]) || !isfinite(final[i]) ||
            final[i]!=clamp(nsout[i]*gain,agc.limiter_linear) || fabsf(final[i])>agc.limiter_linear) { result=7;goto done; }
        if (fwrite(residual,sizeof(float),160u,out[0])!=160u || fwrite(nsout,sizeof(float),160u,out[1])!=160u || fwrite(final,sizeof(float),160u,out[2])!=160u ||
            fprintf(out[3],"%u,%u,%u,%u,%.9g,%.9g,%.9g,%d,%.9g,%.9g,%.9g,%.9g,%u,%.9g,%u\n",frame,(unsigned)gate[0],(unsigned)gate[1],(unsigned)nr.frequency_res_active,
                (double)nr.speech_probability,(double)nr.noise_rms_dbfs,(double)nr.residual_echo_gain,allow,(double)before,(double)agc.gain,(double)gain,
                (double)vr.probability,(unsigned)vr.active,(double)vad.noise_rms,vad.hangover)<0) { result=8;goto done; }
    }
done:
    for (i=0u;i<3u;++i) if (in[i] && fclose(in[i])) result=9;
    for (i=0u;i<4u;++i) if (out[i] && fclose(out[i])) result=9;
    if (!result) printf("{\"frames\":%u,\"samples\":%u,\"ns_calls\":%u,\"agc_calls\":%u,\"vad_calls\":%u,\"res_calls\":0,\"aec_calls\":0,\"ns_state_bytes\":%zu,\"agc_state_bytes\":%zu,\"vad_state_bytes\":%zu,\"frame_buffer_bytes\":%zu,\"scoped_bytes\":%zu}\n",
        frames,frames*160u,frames,frames,frames,sizeof(ns),sizeof(agc),sizeof(vad),sizeof(residual)+sizeof(echo)+sizeof(nsout)+sizeof(final),sizeof(ns)+sizeof(agc)+sizeof(vad)+sizeof(residual)+sizeof(echo)+sizeof(nsout)+sizeof(final));
    return result;
}
