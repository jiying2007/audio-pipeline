/* Research-local saved paired echo/residual -> canonical CALL/FULL downstream. */
#include "device_innovation_noise_gate_d44.h"
#include <float.h>
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
    uint16_t endian=1u;
    if (sizeof(float)!=4u || FLT_MANT_DIG!=24 || sizeof(double)!=8u || DBL_MANT_DIG!=53 || FLT_EVAL_METHOD!=0 || *(unsigned char *)&endian!=1u) return 40;
    { uint32_t f,n=0u;for(f=0u;f<2000u;++f)n+=(uint32_t)ap_power_snapshot_d43(f,2000u);if(n!=33u)return 41;
      n=0u;for(f=0u;f<3024u;++f)n+=(uint32_t)ap_power_snapshot_d43(f,3024u);if(n!=44u)return 42; }

    ap_agc_state_t agc;float x[160]={0};uint32_t i;
    ap_agc_init(&agc,-20.0f,-2.0f);agc.gain=.25f;
    ap_agc_process_controlled(&agc,x,160u,0);
    if (!(agc.gain>.25f && agc.gain<1.0f) || effective(x,&agc,0)>1.0f) return 20;
    for (i=0u;i<160u;++i) x[i]=i%2u ? 2.0f : -2.0f;
    ap_agc_process_controlled(&agc,x,160u,1);
    for (i=0u;i<160u;++i) if (fabsf(x[i])>agc.limiter_linear) return 21;
    {
        ap_noise_conditioned_guard_d42_t g;float floor;int valid;memset(&g,0,sizeof(g));
        if (!ap_innovation_noise_floor_d44(1,1,1,0,0.0,10u,&floor,&valid) || !valid || floor!=0.0f) return 22;
        if (!ap_innovation_noise_floor_d44(1,1,0,0,0.0,10u,&floor,&valid) || !valid || floor!=1.0f) return 23;
        if (!ap_innovation_noise_floor_d44(1,1,0,0,0.0,9u,&floor,&valid) || valid || floor!=0.0f) return 24;
        if (!ap_innovation_noise_floor_d44(0,1,0,0,0.0,10u,&floor,&valid) || valid) return 25;
        if (ap_innovation_noise_floor_d44(NAN,1,0,0,0.0,10u,&floor,&valid)) return 26;
        if (!ap_innovation_noise_floor_d44(1,1,2,0,0.0,10u,&floor,&valid) || floor!=0.0f) return 27;
        if (!ap_noise_conditioned_update_d42(&g,0u,1,2,3,4) || g.e[0]!=1.0 || g.r[0]!=5.0 || g.cr[0]!=2.2 || g.ci[0]!=-0.4) return 28;
        if (ap_noise_conditioned_update_d42(&g,0u,INFINITY,0,0,0)) return 29;
        if (!ap_innovation_noise_floor_d44(1,1,0,0,.75,10u,&floor,&valid) || !valid || floor!=0.0f) return 32;
        if (!ap_innovation_noise_floor_d44(1,1,0,0,1,10u,&floor,&valid) || !valid || floor!=0.0f) return 33;
        if (!ap_innovation_noise_floor_d44(4,4,0,0,3,10u,&floor,&valid) || !valid || floor!=0.0f) return 34;
        if (ap_innovation_noise_floor_d44(1,1,0,0,-1,10u,&floor,&valid) ||
            ap_innovation_noise_floor_d44(1,1,0,0,NAN,10u,&floor,&valid) ||
            ap_innovation_noise_floor_d44(1,1,0,0,INFINITY,10u,&floor,&valid)) return 35;
        /* Exact binary64 threshold and adjacent representable values. */
        if (!ap_innovation_noise_floor_d44(1,1,0,0,.5,10u,&floor,&valid) || !valid || floor!=0.0f) return 48;
        if (!ap_innovation_noise_floor_d44(1,1,0,0,nextafter(.5,0),10u,&floor,&valid) || !valid || floor!=1.0f) return 49;
        if (!ap_innovation_noise_floor_d44(1,1,0,0,nextafter(.5,1),10u,&floor,&valid) || !valid || floor!=0.0f) return 50;
        if (!ap_innovation_noise_floor_d44(1,1,.5,0,.25,10u,&floor,&valid) || !valid || floor!=(float)sqrt(.75)) return 51;
        if (!ap_innovation_noise_floor_d44(1,1,1,0,0,10u,&floor,&valid) || !valid || floor!=0.0f) return 52;
        if (ap_innovation_noise_floor_d44(1,1,0,0,0,11u,&floor,&valid) ||
            ap_innovation_noise_floor_d44(-1,1,0,0,0,10u,&floor,&valid) ||
            ap_innovation_noise_floor_d44(1,-1,0,0,0,10u,&floor,&valid) ||
            ap_innovation_noise_floor_d44(1,1,INFINITY,0,0,10u,&floor,&valid) ||
            ap_innovation_noise_floor_d44(1,1,0,NAN,0,10u,&floor,&valid) ||
            ap_innovation_noise_floor_d44(1,1,0,0,DBL_MAX,10u,&floor,&valid)) return 53;
        if (!ap_innovation_noise_floor_d44(1e-12,1,0,0,0,10u,&floor,&valid) || valid || floor!=0.0f ||
            !ap_innovation_noise_floor_d44(1,1e-12,0,0,0,10u,&floor,&valid) || valid || floor!=0.0f) return 54;
        {
            ap_ns_state_t test_ns;ap_ns_result_t nr;float zero[160]={0},echo_test[160],output[160];uint32_t j;
            memset(&g,0,sizeof(g));ap_ns_init(&test_ns,160u);
            for (j=0u;j<160u;++j) echo_test[j]=1.0f;
            for (j=0u;j<11u;++j) {
                if (!ap_ns_process_d44(&test_ns,&g,NULL,1,AP_ENHANCE_FULL,.12f,zero,echo_test,output,160u,1,1,0,&nr) ||
                    g.count_before!=(j<10u ? j : 10u) || g.count!=(j<9u ? j+1u : 10u) || g.raised_bins) return 30;
            }
            g.e[0]=NAN;
            if (!ap_ns_process_d44(&test_ns,&g,NULL,1,AP_ENHANCE_FULL,.12f,zero,echo_test,output,160u,1,0,0,&nr) ||
                g.count || g.valid_bins || g.raised_bins || g.e[0]!=0.0 || g.floor_mean!=0.0) return 31;
        }
    }
    {
        ap_ns_state_t observed,plain;ap_noise_conditioned_guard_d42_t go,gp;
        ap_power_observer_d43_t observer;ap_ns_result_t ro,rp;
        float input[160],echo_test[160],yo[160],yp[160];uint32_t f,k;
        memset(&observed,0,sizeof(observed));memset(&plain,0,sizeof(plain));
        memset(&go,0,sizeof(go));memset(&gp,0,sizeof(gp));
        ap_ns_init(&observed,160u);ap_ns_init(&plain,160u);
        for(f=0u;f<40u;++f) {
            double previous_noise[AP_NS_BINS_MAX],previous_e[AP_NS_BINS_MAX];
            int far=f<30u,dt=f>=20u && f<25u;
            for(k=0u;k<AP_NS_BINS_MAX;++k) {
                previous_noise[k]=(double)observed.noise_tracker.estimate[k];
                previous_e[k]=(far && !dt) ? go.e[k] : 0.0;
            }
            for(k=0u;k<160u;++k) {
                input[k]=.07f*sinf((float)(f*160u+k)*.031f);
                echo_test[k]=.11f*cosf((float)(f*160u+k)*.043f);
            }
            memset(&ro,0,sizeof(ro));memset(&rp,0,sizeof(rp));
            if(!ap_ns_process_d44(&observed,&go,&observer,1,AP_ENHANCE_FULL,.12f,
                input,echo_test,yo,160u,1,far,dt,&ro) ||
                !ap_ns_process_d44(&plain,&gp,NULL,1,AP_ENHANCE_FULL,.12f,
                input,echo_test,yp,160u,1,far,dt,&rp)) return 43;
            if(memcmp(&observed,&plain,sizeof(plain)) || memcmp(&go,&gp,sizeof(gp)) ||
                memcmp(&ro,&rp,sizeof(rp)) || memcmp(yo,yp,sizeof(yp))) return 44;
            for(k=0u;k<AP_NS_BINS_MAX;++k) {
                const ap_power_bin_d43_t *b=&observer.bin[k];
                if(b->noise!=previous_noise[k] || b->e!=previous_e[k]) return 45;
                if((!far || dt) && (b->valid || b->floor!=0.0f ||
                    b->original_target!=0.0f || b->old_gain!=0.0f ||
                    b->applied_target!=0.0f || b->res_gain!=0.0f ||
                    b->er!=0.0f || b->ei!=0.0f || b->echo_power!=0.0f)) return 46;
                if(f<10u && b->valid) return 47;
            }
        }
    }
    puts("D44_SELF_TEST_PASS controlled-gain/complex-known-answers/nonfinite/observer-null-equivalence/pre-update-noise/snapshot-schedule");return 0;
}

static int diagnostics(FILE *power_file,FILE *bins_file,uint32_t frame,uint32_t frames,
    const unsigned char *gate,const ap_noise_conditioned_guard_d42_t *g,
    const ap_power_observer_d43_t *observer) {
    uint32_t k,valid=0u,dominant=0u,positive=0u,would=0u;
    double qs=0.0,es=0.0,rs=0.0,is=0.0,ns=0.0,xs=0.0,fs=0.0;
    for(k=0u;k<AP_NS_BINS_MAX;++k) {
        const ap_power_bin_d43_t *b=&observer->bin[k];
        if (!isfinite(b->e) || !isfinite(b->r) || !isfinite(b->cr) ||
            !isfinite(b->ci) || !isfinite(b->noise) || b->noise<0.0 ||
            !isfinite(b->er) || !isfinite(b->ei) || !isfinite(b->rr) ||
            !isfinite(b->ri) || !isfinite(b->power) || !isfinite(b->echo_power) ||
            !isfinite(b->floor) || !isfinite(b->original_target) ||
            !isfinite(b->old_gain) || !isfinite(b->applied_target) ||
            !isfinite(b->res_gain) || b->valid>1u) return 0;
        if(b->valid) {
            double q=(b->cr*b->cr+b->ci*b->ci)/(b->e*b->r),fraction;
            if(!(gate[0] && !gate[1]) || g->count_before<10u ||
                b->e<=1e-12 || b->r<=1e-12 || !isfinite(q)) return 0;
            q=q<0.0 ? 0.0 : q>1.0 ? 1.0 : q;
            fraction=(1.0-q)-(b->noise/b->r);
            ++valid;dominant+=(uint32_t)(fraction<=0.0);
            positive+=(uint32_t)(b->floor>0.0f);
            would+=(uint32_t)(b->floor>b->original_target);
            qs+=q;es+=b->e;rs+=b->r;is+=b->r*(1.0-q);
            ns+=b->noise;xs+=b->r*(fraction>0.0 ? fraction : 0.0);
            fs+=((double)b->floor*(double)b->floor)*b->r;
        }
        if(ap_power_snapshot_d43(frame,frames) &&
            fprintf(bins_file,"%u,%u,%u,%u,%u,%u,%.17g,%.17g,%.17g,%.17g,%.17g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g\n",
                frame,k,(unsigned)gate[0],(unsigned)gate[1],g->count_before,b->valid,
                b->e,b->r,b->cr,b->ci,b->noise,(double)b->er,(double)b->ei,
                (double)b->rr,(double)b->ri,(double)b->power,(double)b->echo_power,
                (double)b->original_target,(double)b->old_gain,(double)b->floor,
                (double)b->applied_target,(double)b->res_gain)<0) return 0;
    }
    if(valid!=g->valid_bins || !isfinite(qs) || !isfinite(es) || !isfinite(rs) ||
        !isfinite(is) || !isfinite(ns) || !isfinite(xs) || !isfinite(fs) ||
        !isfinite(g->floor_mean)) return 0;
    return fprintf(power_file,"%u,%u,%u,%u,%u,%u,%u,%u,%u,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g,%.17g\n",
        frame,(unsigned)gate[0],(unsigned)gate[1],g->count_before,valid,dominant,
        positive,would,g->raised_bins,valid ? qs/(double)valid : 0.0,
        es,rs,is,ns,xs,g->floor_mean,fs)>=0;
}

int main(int argc,char **argv) {
    static const char *names[]={"bypass.f32le","ns.f32le","final.f32le","control.csv","protection.csv","power.csv","bins.csv"};
    FILE *in[3]={NULL},*out[7]={NULL};uint32_t frames=0u,frame=0u,i;int result=0;uint16_t endian=1u;
    float residual[160],echo[160],nsout[160],final[160];unsigned char gate[2];char path[1024];
    ap_power_observer_d43_t observer;ap_ns_state_t ns;ap_noise_conditioned_guard_d42_t guard;int protect;ap_agc_state_t agc;ap_vad_state_t vad;
    if (argc==2 && strcmp(argv[1],"--self-test")==0) return self_test();
    if (argc!=7 || !number(argv[4],&frames) || (strcmp(argv[6],"monitor") && strcmp(argv[6],"candidate")) ||
        sizeof(float)!=4u || *(const unsigned char *)&endian!=1u) return 2;
    protect=strcmp(argv[6],"candidate")==0;
    memset(&guard,0,sizeof(guard));
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
    for (i=0u;i<7u;++i) {
        int n=snprintf(path,sizeof(path),"%s/%s",argv[5],names[i]);
        if (n<0 || (size_t)n>=sizeof(path)) { result=2;goto done; }
        out[i]=fopen(path,"wbx");if (!out[i]) { result=4;goto done; }
    }
    ap_ns_init(&ns,160u);ap_agc_init(&agc,-20.0f,-2.0f);ap_vad_init(&vad);
    if (fprintf(out[3],"frame,far,dt,frequency_active,speech_probability,noise_rms_dbfs,residual_gain,agc_allow,gain_before,gain_after,effective_gain,vad_probability,vad_active,vad_noise_rms,vad_hangover\n")<0) { result=8;goto done; }
    if (fprintf(out[4],"frame,far,dt,count_before,count_after,valid_bins,raised_bins,floor_mean\n")<0) { result=8;goto done; }
    if(fprintf(out[5],"frame,far,dt,count_before,valid_bins,noise_dominant_bins,positive_floor_bins,would_raise_bins,raised_bins,q_mean,echo_sum,residual_sum,innovation_sum,noise_sum,excess_sum,floor_mean,floor2_residual_sum\n")<0 ||
        fprintf(out[6],"frame,bin,far,dt,count_before,valid,E,R,Cr,Ci,N,er,ei,rr,ri,power,echo_power,original_target,old_gain,floor,applied_target,res_gain\n")<0) { result=8;goto done; }
    for (frame=0u;frame<frames;++frame) {
        ap_ns_result_t nr;ap_vad_result_t vr;float before,gain;int allow;
        if (fread(residual,sizeof(float),160u,in[0])!=160u || fread(echo,sizeof(float),160u,in[1])!=160u || fread(gate,1u,2u,in[2])!=2u) { result=4;goto done; }
        if (!ap_ns_process_d44(&ns,&guard,&observer,protect,AP_ENHANCE_FULL,.12f,residual,echo,nsout,160u,1,(int)gate[0],(int)gate[1],&nr)) { result=7;goto done; }
        if(!diagnostics(out[5],out[6],frame,frames,gate,&guard,&observer)) { result=7;goto done; }
        allow=!(gate[0] && !gate[1]);before=agc.gain;memcpy(final,nsout,sizeof(final));
        ap_agc_process_controlled(&agc,final,160u,allow);gain=effective(nsout,&agc,allow);
        ap_vad_process(&vad,final,160u,nr.speech_probability,1,&vr);
        if (sync_calls || nr.frequency_res_active!=(uint8_t)(gate[0] && !gate[1]) || !isfinite(before) || !isfinite(agc.gain) ||
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
        if (fprintf(out[4],"%u,%u,%u,%u,%u,%u,%u,%.17g\n",frame,(unsigned)gate[0],(unsigned)gate[1],guard.count_before,guard.count,guard.valid_bins,guard.raised_bins,guard.floor_mean)<0) { result=8;goto done; }
    }
done:
    for (i=0u;i<3u;++i) if (in[i] && fclose(in[i])) result=9;
    for (i=0u;i<7u;++i) if (out[i] && fclose(out[i])) result=9;
    if (!result) printf("{\"frames\":%u,\"samples\":%u,\"ns_calls\":%u,\"agc_calls\":%u,\"vad_calls\":%u,\"res_calls\":0,\"aec_calls\":0,\"ns_state_bytes\":%zu,\"agc_state_bytes\":%zu,\"vad_state_bytes\":%zu,\"frame_buffer_bytes\":%zu,\"scoped_bytes\":%zu,\"observer_state_bytes\":%zu,\"measurement_scoped_bytes\":%zu}\n",
        frames,frames*160u,frames,frames,frames,sizeof(ns)+sizeof(guard),sizeof(agc),sizeof(vad),sizeof(residual)+sizeof(echo)+sizeof(nsout)+sizeof(final),sizeof(ns)+sizeof(guard)+sizeof(agc)+sizeof(vad)+sizeof(residual)+sizeof(echo)+sizeof(nsout)+sizeof(final),sizeof(observer),sizeof(observer)+sizeof(ns)+sizeof(guard)+sizeof(agc)+sizeof(vad)+sizeof(residual)+sizeof(echo)+sizeof(nsout)+sizeof(final));
    return result;
}

