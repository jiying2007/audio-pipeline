/* FE04 oracle near-presence RES upper-bound diagnostic. Offline research only. */
#include "audio_pipeline/audio_modules.h"
#include "audio_pipeline/audio_pipeline_build.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define HOP 160u
#define FRAMES 1600u

enum mode_kind { MODE_MEASURED=1, MODE_ORACLE_NEAR=2 };

static size_t round16(size_t n) { return (n + 15u) & ~(size_t)15u; }

static int oracle_near(uint32_t frame) {
    return frame < 204u || (frame >= 600u && frame < 1004u) || frame >= 1400u;
}

static int self_test(void) {
    unsigned char *mem=NULL;
    ap_res_module_t *res=NULL;
    const size_t bytes=round16(ap_module_res_state_size());
    float samples[HOP],gain=0.0f;
    unsigned i;
    mem=(unsigned char *)aligned_alloc(16,bytes);
    if(!mem || ap_module_res_init(mem,ap_module_res_state_size(),&res)!=AP_OK) goto fail;
    for(i=0;i<HOP;++i)samples[i]=1.0f;
    if(ap_module_res_process(res,AP_QUALITY_FULL,samples,HOP,1.0f,0.01f,1,0,&gain)!=AP_OK)goto fail;
    if(!(gain>=0.10f && gain<1.0f))goto fail;
    for(i=0;i<HOP;++i)samples[i]=1.0f;
    if(ap_module_res_process(res,AP_QUALITY_FULL,samples,HOP,1.0f,0.01f,1,1,&gain)!=AP_OK)goto fail;
    if(gain!=1.0f || samples[0]!=1.0f)goto fail;
    ap_module_res_reset(res);
    for(i=0;i<HOP;++i)samples[i]=1.0f;
    if(ap_module_res_process(res,AP_QUALITY_FULL,samples,HOP,0.0f,0.0f,0,1,&gain)!=AP_OK)goto fail;
    if(gain!=1.0f || samples[0]!=1.0f)goto fail;
    free(mem);
    puts("{\"status\":\"PASS\",\"far_only_attenuates\":true,\"near_protection_immediate\":true,\"reset_unity\":true}");
    return 0;
fail:
    free(mem);
    fputs("oracle-near RES self-test failed\n",stderr);
    return 2;
}

int main(int argc,char **argv) {
    FILE *audio=NULL,*control=NULL,*out=NULL,*meta=NULL,*trace=NULL;
    enum mode_kind mode=0;
    void *res_mem=NULL;
    ap_res_module_t *res=NULL;
    float packed_in[HOP*3u],packed_out[HOP*3u],post[HOP];
    char header[1024];
    unsigned frames=0u,oracle_frames=0u,measured_frames=0u,control_frames=0u;
    unsigned newly_protected=0u,false_positive_released=0u,gain_lt_099=0u,gain_lt_095=0u;
    double gain_sum=0.0;
    float gain_min=1.0f,gain_max=1.0f;
    int rc=2;

    if(argc==2 && !strcmp(argv[1],"--self-test"))return self_test();
    if(argc!=7){
        fputs("usage: res-oracle-near measured|oracle PREDECESSOR.f32 PREDECESSOR.csv OUTPUT.f32 META.json TRACE.csv\n",stderr);
        return 2;
    }
    if(!strcmp(argv[1],"measured"))mode=MODE_MEASURED;
    else if(!strcmp(argv[1],"oracle"))mode=MODE_ORACLE_NEAR;
    else { fputs("invalid mode\n",stderr); return 2; }

    audio=fopen(argv[2],"rb"); if(!audio)goto done;
    control=fopen(argv[3],"r"); if(!control)goto done;
    out=fopen(argv[4],"wbx"); if(!out)goto done;
    meta=fopen(argv[5],"wbx"); if(!meta)goto done;
    trace=fopen(argv[6],"wbx"); if(!trace)goto done;

    if(!fgets(header,sizeof(header),control))goto done;
    if(strcmp(header,
       "frame,known_lead_samples,timestamp_observed,route_jump,aec_reset,sync_delay_samples,underrun,used_far,used_dt,aec_echo_energy,pre_residual_energy,res_gain,pre_output_energy,post_output_energy\n"))
        goto done;

    res_mem=aligned_alloc(16,round16(ap_module_res_state_size()));
    if(!res_mem || ap_module_res_init(res_mem,ap_module_res_state_size(),&res)!=AP_OK)goto done;

    if(fputs("frame,used_far,measured_dt,oracle_near,res_control_near,aec_echo_energy,pre_residual_energy,predecessor_gain,candidate_gain,pre_output_energy,predecessor_post_output_energy,candidate_post_output_energy\n",trace)==EOF)
        goto done;

    for(uint32_t frame=0u;frame<FRAMES;++frame){
        unsigned f,known_lead,timestamp_observed,route_jump,aec_reset,sync_delay,underrun,used_far,used_dt;
        float echo_energy,residual_energy,predecessor_gain,pre_energy,predecessor_post_energy;
        const int got=fscanf(control,
          "%u,%u,%u,%u,%u,%u,%u,%u,%u,%f,%f,%f,%f,%f\n",
          &f,&known_lead,&timestamp_observed,&route_jump,&aec_reset,&sync_delay,&underrun,
          &used_far,&used_dt,&echo_energy,&residual_energy,&predecessor_gain,&pre_energy,&predecessor_post_energy);
        const int oracle=oracle_near(frame);
        const int selected=mode==MODE_MEASURED?(int)used_dt:oracle;
        float gain=1.0f,candidate_post_energy=1.0e-12f;
        if(got!=14 || f!=frame || used_far>1u || used_dt>1u ||
           timestamp_observed!=1u || underrun!=0u || route_jump>1u || aec_reset>1u ||
           route_jump!=aec_reset || sync_delay!=known_lead ||
           !isfinite(echo_energy) || !isfinite(residual_energy) ||
           !isfinite(predecessor_gain) || !isfinite(pre_energy) || !isfinite(predecessor_post_energy) ||
           echo_energy<0.0f || residual_energy<0.0f || predecessor_gain<=0.0f || predecessor_gain>1.0f)
            goto done;
        if(fread(packed_in,sizeof(float),HOP*3u,audio)!=HOP*3u)goto done;
        for(unsigned k=0;k<HOP;++k){
            const float pre=packed_in[3u*k];
            const float ref=packed_in[3u*k+2u];
            if(!isfinite(pre) || !isfinite(ref))goto done;
            post[k]=pre;
        }
        if(ap_module_res_process(res,AP_QUALITY_FULL,post,HOP,echo_energy,residual_energy,
                                 (int)used_far,selected,&gain)!=AP_OK)goto done;
        for(unsigned k=0;k<HOP;++k){
            packed_out[3u*k]=packed_in[3u*k];
            packed_out[3u*k+1u]=post[k];
            packed_out[3u*k+2u]=packed_in[3u*k+2u];
            candidate_post_energy+=post[k]*post[k];
        }
        candidate_post_energy/=HOP;
        if(fwrite(packed_out,sizeof(float),HOP*3u,out)!=HOP*3u)goto done;

        oracle_frames+=(unsigned)oracle;
        measured_frames+=used_dt;
        control_frames+=(unsigned)selected;
        newly_protected+=(unsigned)(oracle && !used_dt);
        false_positive_released+=(unsigned)(!oracle && used_dt);
        gain_sum+=(double)gain;
        if(gain<gain_min)gain_min=gain;
        if(gain>gain_max)gain_max=gain;
        if(gain<0.99f)++gain_lt_099;
        if(gain<0.95f)++gain_lt_095;

        if(fprintf(trace,"%u,%u,%u,%u,%u,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g\n",
            frame,used_far,used_dt,(unsigned)oracle,(unsigned)selected,
            (double)echo_energy,(double)residual_energy,(double)predecessor_gain,(double)gain,
            (double)pre_energy,(double)predecessor_post_energy,(double)candidate_post_energy)<0)
            goto done;
        ++frames;
    }

    if(fgetc(audio)!=EOF)goto done;
    {
        unsigned extra;
        if(fscanf(control,"%u",&extra)==1)goto done;
    }
    if(frames!=FRAMES)goto done;
    if(fprintf(meta,
      "{\"status\":\"PASS\",\"mode\":\"%s\",\"frames\":%u,\"oracle_near_frames\":%u,"
      "\"measured_dt_frames\":%u,\"res_control_near_frames\":%u,\"newly_protected_frames\":%u,"
      "\"measured_false_positive_frames\":%u,\"gain_mean\":%.9g,\"gain_min\":%.9g,\"gain_max\":%.9g,"
      "\"gain_lt_0_99_frames\":%u,\"gain_lt_0_95_frames\":%u,\"res_state_bytes\":%zu,"
      "\"near_protection_release_alpha\":1.0,\"shipping_authority\":false,\"source_revision\":\"%s\"}\n",
      mode==MODE_MEASURED?"measured-replay":"oracle-near",
      frames,oracle_frames,measured_frames,control_frames,newly_protected,false_positive_released,
      gain_sum/(double)frames,(double)gain_min,(double)gain_max,gain_lt_099,gain_lt_095,
      ap_module_res_state_size(),AP_BUILD_SOURCE_REVISION)<0)goto done;
    rc=0;
done:
    free(res_mem);
    if(audio && fclose(audio))rc=2;
    if(control && fclose(control))rc=2;
    if(out && fclose(out))rc=2;
    if(meta && fclose(meta))rc=2;
    if(trace && fclose(trace))rc=2;
    if(rc)fputs("FE04 oracle-near RES replay failed; partial files are not evidence\n",stderr);
    return rc;
}
