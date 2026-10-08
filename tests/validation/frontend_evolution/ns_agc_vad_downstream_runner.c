/* FE05 NS -> production-style controlled AGC -> VAD downstream diagnostic. */
#include "audio_pipeline/audio_pipeline_build.h"
#include "enhance/ap_enhance.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define HOP 160u
#define INPUT_LANES 5u
#define CONTROL_LANES 3u
#define OUTPUT_LANES 4u
#define AGC_TARGET_DBFS (-18.0f)
#define LIMITER_DBFS (-2.0f)

static uint32_t float_bits(float x) {
    uint32_t u;
    memcpy(&u, &x, sizeof(u));
    return u;
}

static float energy(const float *x, uint32_t n) {
    float e=1.0e-12f;
    for(uint32_t i=0u;i<n;++i)e+=x[i]*x[i];
    return e/(float)n;
}

static float peak_abs(const float *x, uint32_t n) {
    float p=0.0f;
    for(uint32_t i=0u;i<n;++i){
        const float a=fabsf(x[i]);
        if(a>p)p=a;
    }
    return p;
}

static int self_test(void) {
#if !AP_BUILD_STAGE_AGC || !AP_BUILD_STAGE_VAD
    fputs("AGC/VAD stages not compiled\n",stderr);
    return 2;
#else
    ap_agc_state_t a0,a1;
    ap_vad_state_t v0,v1;
    ap_vad_result_t r0,r1;
    float x0[HOP],x1[HOP];
    unsigned i;

    ap_agc_init(&a0,AGC_TARGET_DBFS,LIMITER_DBFS);
    ap_agc_init(&a1,AGC_TARGET_DBFS,LIMITER_DBFS);
    ap_vad_init(&v0);
    ap_vad_init(&v1);
    for(i=0u;i<HOP;++i)x0[i]=x1[i]=0.02f*sinf((float)i*0.071f);
    ap_agc_process_controlled(&a0,x0,HOP,1);
    ap_agc_process_controlled(&a1,x1,HOP,1);
    if(memcmp(x0,x1,sizeof(x0))!=0 ||
       float_bits(a0.gain)!=float_bits(a1.gain) ||
       float_bits(a0.target_linear)!=float_bits(a1.target_linear) ||
       float_bits(a0.limiter_linear)!=float_bits(a1.limiter_linear))
        goto fail;
    ap_vad_process(&v0,x0,HOP,0.7f,1,&r0);
    ap_vad_process(&v1,x1,HOP,0.7f,1,&r1);
    if(float_bits(r0.probability)!=float_bits(r1.probability) ||
       r0.active!=r1.active ||
       float_bits(v0.noise_rms)!=float_bits(v1.noise_rms) ||
       v0.hangover!=v1.hangover)
        goto fail;

    ap_agc_init(&a0,AGC_TARGET_DBFS,LIMITER_DBFS);
    for(i=0u;i<HOP;++i)x0[i]=0.001f;
    ap_agc_process_controlled(&a0,x0,HOP,0);
    if(a0.gain>1.0f || peak_abs(x0,HOP)>0.001001f)goto fail;

    ap_agc_init(&a0,AGC_TARGET_DBFS,LIMITER_DBFS);
    ap_vad_init(&v0);
    if(float_bits(a0.gain)!=float_bits(1.0f) || float_bits(v0.noise_rms)!=float_bits(1.0e-3f) ||
       v0.hangover!=0u)
        goto fail;

    puts("{\"status\":\"PASS\",\"identical_arm_identity\":true,"
         "\"far_only_gain_increase_blocked\":true,\"reset_lifecycle\":true}");
    return 0;
fail:
    fputs("NS/AGC/VAD downstream self-test failed\n",stderr);
    return 2;
#endif
}

int main(int argc,char **argv) {
#if !AP_BUILD_STAGE_AGC || !AP_BUILD_STAGE_VAD
    (void)argc;(void)argv;
    fputs("AGC/VAD stages not compiled\n",stderr);
    return 2;
#else
    FILE *in=NULL,*ctl=NULL,*out=NULL,*meta=NULL,*trace=NULL;
    float *packed_in=NULL,*controls=NULL;
    long input_bytes_long,control_bytes_long;
    size_t samples,frames;
    int rc=2;

    ap_agc_state_t agc0,agc1;
    ap_vad_state_t vad0,vad1;
    float pre0[HOP],pre1[HOP],post0[HOP],post1[HOP],packed_out[HOP*OUTPUT_LANES];
    unsigned allow_false_frames=0u,pre_diff_frames=0u,post_diff_frames=0u;
    unsigned agc_state_before_diff_frames=0u,agc_state_after_diff_frames=0u;
    unsigned vad_state_before_diff_frames=0u,vad_state_after_diff_frames=0u;
    unsigned vad_probability_diff_frames=0u,vad_active_disagreement_frames=0u;
    unsigned limiter0_frames=0u,limiter1_frames=0u;
    unsigned fullscale0_samples=0u,fullscale1_samples=0u;

    if(argc==2 && !strcmp(argv[1],"--self-test"))return self_test();
    if(argc!=7){
        fputs("usage: ns-agc-vad PREDECESSOR.f32 CONTROLS.f32 OUTPUT.f32 META.json TRACE.csv SOURCE_REV\n",stderr);
        return 2;
    }

    in=fopen(argv[1],"rb");if(!in)goto done;
    if(fseek(in,0,SEEK_END))goto done;
    input_bytes_long=ftell(in);
    if(input_bytes_long<=0 || (unsigned long)input_bytes_long%(INPUT_LANES*sizeof(float)) ||
       fseek(in,0,SEEK_SET))
        goto done;
    samples=(size_t)input_bytes_long/(INPUT_LANES*sizeof(float));
    if(samples%HOP || samples/HOP>2000u)goto done;
    frames=samples/HOP;
    packed_in=(float*)malloc((size_t)input_bytes_long);
    if(!packed_in || fread(packed_in,1,(size_t)input_bytes_long,in)!=(size_t)input_bytes_long)goto done;
    if(fclose(in)){in=NULL;goto done;}in=NULL;
    for(size_t i=0;i<samples*INPUT_LANES;++i)if(!isfinite(packed_in[i]))goto done;

    ctl=fopen(argv[2],"rb");if(!ctl)goto done;
    if(fseek(ctl,0,SEEK_END))goto done;
    control_bytes_long=ftell(ctl);
    if(control_bytes_long!=(long)(frames*CONTROL_LANES*sizeof(float)) || fseek(ctl,0,SEEK_SET))goto done;
    controls=(float*)malloc((size_t)control_bytes_long);
    if(!controls || fread(controls,1,(size_t)control_bytes_long,ctl)!=(size_t)control_bytes_long)goto done;
    if(fclose(ctl)){ctl=NULL;goto done;}ctl=NULL;
    for(size_t i=0;i<frames*CONTROL_LANES;++i)if(!isfinite(controls[i]))goto done;

    out=fopen(argv[3],"wbx");if(!out)goto done;
    meta=fopen(argv[4],"wbx");if(!meta)goto done;
    trace=fopen(argv[5],"wbx");if(!trace)goto done;

    ap_agc_init(&agc0,AGC_TARGET_DBFS,LIMITER_DBFS);
    ap_agc_init(&agc1,AGC_TARGET_DBFS,LIMITER_DBFS);
    ap_vad_init(&vad0);
    ap_vad_init(&vad1);

    if(fputs("frame,used_far,used_dt,allow_gain_increase,upstream_speech_probability,"
             "pre_diff_samples,agc_state_before_equal,agc0_gain_before,agc1_gain_before,"
             "pre0_rms,pre1_rms,pre0_peak,pre1_peak,"
             "agc0_gain_after,agc1_gain_after,post0_rms,post1_rms,post0_peak,post1_peak,"
             "limiter0_active,limiter1_active,post_diff_samples,"
             "vad_state_before_equal,vad0_noise_before,vad1_noise_before,vad0_hangover_before,vad1_hangover_before,"
             "vad0_probability,vad1_probability,vad0_active,vad1_active,"
             "vad0_noise_after,vad1_noise_after,vad0_hangover_after,vad1_hangover_after,vad_state_after_equal\n",trace)==EOF)
        goto done;

    for(size_t frame=0;frame<frames;++frame){
        const float upstream=controls[frame*CONTROL_LANES];
        const float farf=controls[frame*CONTROL_LANES+1u];
        const float dtf=controls[frame*CONTROL_LANES+2u];
        int far,dt,allow;
        unsigned pre_diffs=0u,post_diffs=0u;
        const float agc0_gain_before=agc0.gain;
        const float agc1_gain_before=agc1.gain;
        const float vad0_noise_before=vad0.noise_rms;
        const float vad1_noise_before=vad1.noise_rms;
        const uint32_t vad0_hang_before=vad0.hangover;
        const uint32_t vad1_hang_before=vad1.hangover;
        const int agc_before_equal=
            float_bits(agc0.gain)==float_bits(agc1.gain) &&
            float_bits(agc0.target_linear)==float_bits(agc1.target_linear) &&
            float_bits(agc0.limiter_linear)==float_bits(agc1.limiter_linear);
        const int vad_before_equal=
            float_bits(vad0.noise_rms)==float_bits(vad1.noise_rms) &&
            vad0.hangover==vad1.hangover;
        ap_vad_result_t vr0,vr1;
        float epre0,epre1,epost0,epost1,ppre0,ppre1,ppost0,ppost1;
        int lim0,lim1;

        if(upstream<0.0f || upstream>1.0f || (farf!=0.0f&&farf!=1.0f) || (dtf!=0.0f&&dtf!=1.0f))
            goto done;
        far=(int)farf;dt=(int)dtf;allow=!(far&&!dt);
        if(!allow)++allow_false_frames;

        for(unsigned k=0u;k<HOP;++k){
            const size_t s=frame*HOP+k;
            pre0[k]=packed_in[s*INPUT_LANES+2u];
            pre1[k]=packed_in[s*INPUT_LANES+3u];
            post0[k]=pre0[k];
            post1[k]=pre1[k];
            if(float_bits(pre0[k])!=float_bits(pre1[k]))++pre_diffs;
        }
        if(pre_diffs)++pre_diff_frames;
        if(agc_before_equal==0)++agc_state_before_diff_frames;
        if(vad_before_equal==0)++vad_state_before_diff_frames;

        epre0=energy(pre0,HOP);epre1=energy(pre1,HOP);
        ppre0=peak_abs(pre0,HOP);ppre1=peak_abs(pre1,HOP);
        ap_agc_process_controlled(&agc0,post0,HOP,allow);
        ap_agc_process_controlled(&agc1,post1,HOP,allow);
        epost0=energy(post0,HOP);epost1=energy(post1,HOP);
        ppost0=peak_abs(post0,HOP);ppost1=peak_abs(post1,HOP);
        lim0=ppost0>=agc0.limiter_linear*(1.0f-1.0e-6f);
        lim1=ppost1>=agc1.limiter_linear*(1.0f-1.0e-6f);
        limiter0_frames+=(unsigned)lim0;limiter1_frames+=(unsigned)lim1;

        for(unsigned k=0u;k<HOP;++k){
            if(float_bits(post0[k])!=float_bits(post1[k]))++post_diffs;
            if(fabsf(post0[k])>=agc0.limiter_linear*(1.0f-1.0e-6f))++fullscale0_samples;
            if(fabsf(post1[k])>=agc1.limiter_linear*(1.0f-1.0e-6f))++fullscale1_samples;
            packed_out[OUTPUT_LANES*k]=pre0[k];
            packed_out[OUTPUT_LANES*k+1u]=pre1[k];
            packed_out[OUTPUT_LANES*k+2u]=post0[k];
            packed_out[OUTPUT_LANES*k+3u]=post1[k];
        }
        if(post_diffs)++post_diff_frames;
        if(float_bits(agc0.gain)!=float_bits(agc1.gain) ||
           float_bits(agc0.target_linear)!=float_bits(agc1.target_linear) ||
           float_bits(agc0.limiter_linear)!=float_bits(agc1.limiter_linear))
            ++agc_state_after_diff_frames;

        /* Production semantics: both arms receive the same upstream NS probability. */
        ap_vad_process(&vad0,post0,HOP,upstream,1,&vr0);
        ap_vad_process(&vad1,post1,HOP,upstream,1,&vr1);
        if(float_bits(vr0.probability)!=float_bits(vr1.probability))++vad_probability_diff_frames;
        if(vr0.active!=vr1.active)++vad_active_disagreement_frames;
        if(float_bits(vad0.noise_rms)!=float_bits(vad1.noise_rms) ||
           vad0.hangover!=vad1.hangover)
            ++vad_state_after_diff_frames;

        if(pre_diffs==0u && agc_before_equal && post_diffs!=0u)goto done;
        if(post_diffs==0u && vad_before_equal &&
           (float_bits(vr0.probability)!=float_bits(vr1.probability) || vr0.active!=vr1.active))
            goto done;

        if(fwrite(packed_out,sizeof(float),HOP*OUTPUT_LANES,out)!=HOP*OUTPUT_LANES)goto done;
        if(fprintf(trace,
           "%zu,%d,%d,%d,%.9g,%u,%d,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,"
           "%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%d,%d,%u,%d,%.9g,%.9g,%u,%u,"
           "%.9g,%.9g,%u,%u,%.9g,%.9g,%u,%u,%d\n",
           frame,far,dt,allow,(double)upstream,pre_diffs,agc_before_equal,
           (double)agc0_gain_before,(double)agc1_gain_before,
           (double)sqrtf(epre0),(double)sqrtf(epre1),(double)ppre0,(double)ppre1,
           (double)agc0.gain,(double)agc1.gain,(double)sqrtf(epost0),(double)sqrtf(epost1),
           (double)ppost0,(double)ppost1,lim0,lim1,post_diffs,vad_before_equal,
           (double)vad0_noise_before,(double)vad1_noise_before,vad0_hang_before,vad1_hang_before,
           (double)vr0.probability,(double)vr1.probability,(unsigned)vr0.active,(unsigned)vr1.active,
           (double)vad0.noise_rms,(double)vad1.noise_rms,vad0.hangover,vad1.hangover,
           (float_bits(vad0.noise_rms)==float_bits(vad1.noise_rms) &&
            vad0.hangover==vad1.hangover))<0)
            goto done;
    }

    if(fprintf(meta,
      "{\"status\":\"PASS\",\"frames\":%zu,\"samples\":%zu,"
      "\"agc_target_dbfs\":-18.0,\"limiter_dbfs\":-2.0,\"production_controlled_agc\":true,"
      "\"vad_uses_upstream_probability\":true,\"allow_gain_increase_false_frames\":%u,"
      "\"pre_diff_frames\":%u,\"post_diff_frames\":%u,"
      "\"agc_state_before_diff_frames\":%u,\"agc_state_after_diff_frames\":%u,"
      "\"vad_state_before_diff_frames\":%u,\"vad_state_after_diff_frames\":%u,"
      "\"vad_probability_diff_frames\":%u,\"vad_active_disagreement_frames\":%u,"
      "\"limiter0_active_frames\":%u,\"limiter1_active_frames\":%u,"
      "\"limiter0_samples\":%u,\"limiter1_samples\":%u,"
      "\"final_agc0_gain\":%.9g,\"final_agc1_gain\":%.9g,"
      "\"final_vad0_noise\":%.9g,\"final_vad1_noise\":%.9g,"
      "\"final_vad0_hangover\":%u,\"final_vad1_hangover\":%u,"
      "\"shipping_authority\":false,\"source_revision\":\"%s\"}\n",
      frames,samples,allow_false_frames,pre_diff_frames,post_diff_frames,
      agc_state_before_diff_frames,agc_state_after_diff_frames,
      vad_state_before_diff_frames,vad_state_after_diff_frames,
      vad_probability_diff_frames,vad_active_disagreement_frames,
      limiter0_frames,limiter1_frames,fullscale0_samples,fullscale1_samples,
      (double)agc0.gain,(double)agc1.gain,(double)vad0.noise_rms,(double)vad1.noise_rms,
      vad0.hangover,vad1.hangover,argv[6])<0)
        goto done;

    rc=0;
done:
    free(packed_in);free(controls);
    if (in && fclose(in)) rc = 2;
    if (ctl && fclose(ctl)) rc = 2;
    if (out && fclose(out)) rc = 2;
    if (meta && fclose(meta)) rc = 2;
    if (trace && fclose(trace)) rc = 2;
    if(rc)fputs("FE05 NS/AGC/VAD downstream diagnostic failed; partial files are not evidence\n",stderr);
    return rc;
#endif
}
