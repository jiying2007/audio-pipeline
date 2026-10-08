/* FE05 NS frequency-RES causal diagnostic. Offline research only. */
#include "audio_pipeline/audio_modules.h"
#include "audio_pipeline/audio_pipeline_build.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define RATE 16000u
#define HOP 160u
#define COLS 4u
#define NS_PER_SAMPLE 62500ull
#define BASE_NS 30000000000ull
#define NS_FLOOR 0.18f

enum fault_kind { FAULT_STATIC=1, FAULT_ROUTE=2, FAULT_DRIFT=3 };

static size_t round16(size_t n) { return (n + 15u) & ~(size_t)15u; }

static float physical_ref(const float *data, size_t samples, uint64_t index) {
    return index < samples ? data[index * COLS + 3u] : 0.0f;
}

static uint32_t lead_for(enum fault_kind fault, uint32_t frame, uint32_t frames) {
    const uint64_t end = (uint64_t)(frame + 1u) * HOP;
    if (fault == FAULT_ROUTE)
        return frame >= frames / 2u ? 800u : 320u;
    if (fault == FAULT_DRIFT)
        return 320u + (uint32_t)((end * 250ull) / 1000000ull);
    return 320u;
}

static uint32_t float_bits(float x) {
    uint32_t u;
    memcpy(&u, &x, sizeof(u));
    return u;
}

static int self_test(void) {
    const size_t bytes = round16(ap_module_ns_state_size());
    unsigned char *a_mem=NULL,*b_mem=NULL;
    ap_ns_module_t *a=NULL,*b=NULL;
    const ap_module_ns_config_t cfg={RATE,NS_FLOOR};
    float input[HOP],echo[HOP],oa[HOP],ob[HOP];
    ap_module_ns_result_t ra,rb;
    unsigned i;

    a_mem=(unsigned char*)aligned_alloc(16,bytes);
    b_mem=(unsigned char*)aligned_alloc(16,bytes);
    if(!a_mem||!b_mem ||
       ap_module_ns_init(a_mem,ap_module_ns_state_size(),&cfg,&a)!=AP_OK ||
       ap_module_ns_init(b_mem,ap_module_ns_state_size(),&cfg,&b)!=AP_OK)
        goto fail;

    for(i=0u;i<HOP;++i){
        input[i]=0.12f*sinf((float)i*0.071f)+0.03f*cosf((float)i*0.037f);
        echo[i]=0.08f*sinf((float)i*0.049f);
    }
    if(ap_module_ns_process(a,AP_QUALITY_FULL,input,echo,oa,HOP,0,1,0,&ra)!=AP_OK ||
       ap_module_ns_process(b,AP_QUALITY_FULL,input,echo,ob,HOP,1,1,0,&rb)!=AP_OK)
        goto fail;
    if(ra.frequency_res_active || !rb.frequency_res_active ||
       float_bits(ra.noise_rms_dbfs)!=float_bits(rb.noise_rms_dbfs) ||
       float_bits(ra.speech_probability)!=float_bits(rb.speech_probability))
        goto fail;

    /* First protected frame may retain one-frame OLA from prior active RES. */
    if(ap_module_ns_process(a,AP_QUALITY_FULL,input,echo,oa,HOP,0,1,1,&ra)!=AP_OK ||
       ap_module_ns_process(b,AP_QUALITY_FULL,input,echo,ob,HOP,1,1,1,&rb)!=AP_OK)
        goto fail;
    if(ra.frequency_res_active || rb.frequency_res_active ||
       float_bits(ra.noise_rms_dbfs)!=float_bits(rb.noise_rms_dbfs) ||
       float_bits(ra.speech_probability)!=float_bits(rb.speech_probability))
        goto fail;

    /* A second protected frame must have converged synthesis overlap. */
    if(ap_module_ns_process(a,AP_QUALITY_FULL,input,echo,oa,HOP,0,1,1,&ra)!=AP_OK ||
       ap_module_ns_process(b,AP_QUALITY_FULL,input,echo,ob,HOP,1,1,1,&rb)!=AP_OK)
        goto fail;
    if(memcmp(oa,ob,sizeof(oa))!=0 ||
       float_bits(ra.noise_rms_dbfs)!=float_bits(rb.noise_rms_dbfs) ||
       float_bits(ra.speech_probability)!=float_bits(rb.speech_probability))
        goto fail;

    ap_module_ns_reset(a);
    ap_module_ns_reset(b);
    if(ap_module_ns_process(a,AP_QUALITY_FULL,input,echo,oa,HOP,0,0,0,&ra)!=AP_OK ||
       ap_module_ns_process(b,AP_QUALITY_FULL,input,echo,ob,HOP,1,0,0,&rb)!=AP_OK ||
       memcmp(oa,ob,sizeof(oa))!=0 || rb.frequency_res_active)
        goto fail;

    if(ap_module_ns_process(b,AP_QUALITY_FULL,input,NULL,ob,HOP,1,1,0,&rb)!=AP_EINVAL)
        goto fail;

    free(a_mem);free(b_mem);
    puts("{\"status\":\"PASS\",\"noise_speech_identity\":true,"
         "\"protected_second_frame_identity\":true,\"frequency_res_requires_echo\":true}");
    return 0;
fail:
    free(a_mem);free(b_mem);
    fputs("NS frequency-RES self-test failed\n",stderr);
    return 2;
}

int main(int argc,char **argv){
    FILE *in=NULL,*out=NULL,*meta=NULL,*trace=NULL;
    float *data=NULL;
    long bytes_long;
    size_t bytes,samples;
    uint32_t frames;
    enum fault_kind fault=0;
    int rc=2;

    void *sync_mem=NULL,*activity_mem=NULL,*aec_mem=NULL,*ns0_mem=NULL,*ns1_mem=NULL;
    ap_sync_module_t *sync=NULL;
    ap_activity_module_t *activity=NULL;
    ap_aec_module_t *aec=NULL;
    ap_ns_module_t *ns0=NULL,*ns1=NULL;
    const ap_module_activity_config_t ac={1.0e-7f,1.5f,3u};
    const ap_module_aec_config_t ec={RATE,64u,1u,0.2f};
    const ap_module_ns_config_t nc={RATE,NS_FLOOR};

    float mic[HOP],reference[HOP],render_chunk[HOP],aec_out[HOP],predicted_echo[HOP];
    float ns_only[HOP],ns_freq[HOP],packed[HOP*5u];
    uint64_t render_cursor=0u;
    unsigned timestamp_observations=0u,route_jumps=0u,aec_resets=0u,underruns=0u;
    unsigned far_frames=0u,dt_frames=0u,freq_active_frames=0u;
    unsigned protected_frames=0u,protected_steady_frames=0u,protected_carryover_frames=0u;
    unsigned protected_steady_diff_samples=0u,carryover_diff_samples=0u;
    unsigned noise_bits_mismatch=0u,speech_bits_mismatch=0u;
    double residual_gain_sum=0.0;
    float residual_gain_min=1.0f,residual_gain_max=1.0f;
    ap_module_aec_result_t final_aec={0};
    ap_module_sync_status_t final_sync={0};
    int previous_freq_active=0;

    if(argc==2 && !strcmp(argv[1],"--self-test")) return self_test();
    if(argc!=6){
        fputs("usage: ns-frequency-res static|route|drift INPUT.f32 OUTPUT.f32 META.json TRACE.csv\n",stderr);
        return 2;
    }
    if(!strcmp(argv[1],"static"))fault=FAULT_STATIC;
    else if(!strcmp(argv[1],"route"))fault=FAULT_ROUTE;
    else if(!strcmp(argv[1],"drift"))fault=FAULT_DRIFT;
    else{fputs("invalid fault\n",stderr);return 2;}

    in=fopen(argv[2],"rb");if(!in)goto done;
    if(fseek(in,0,SEEK_END))goto done;
    bytes_long=ftell(in);
    if(bytes_long<=0 || (unsigned long)bytes_long%(COLS*sizeof(float)) || fseek(in,0,SEEK_SET))goto done;
    bytes=(size_t)bytes_long;samples=bytes/(COLS*sizeof(float));
    if(samples%HOP || samples/HOP>2000u)goto done;
    frames=(uint32_t)(samples/HOP);
    data=(float*)malloc(bytes);if(!data || fread(data,1,bytes,in)!=bytes)goto done;
    for(size_t i=0;i<samples*COLS;++i)if(!isfinite(data[i]))goto done;
    if(fclose(in)){in=NULL;goto done;}in=NULL;

    sync_mem=aligned_alloc(16,round16(ap_module_sync_state_size()));
    activity_mem=aligned_alloc(16,round16(ap_module_activity_state_size()));
    aec_mem=aligned_alloc(16,round16(ap_module_aec_state_size()));
    ns0_mem=aligned_alloc(16,round16(ap_module_ns_state_size()));
    ns1_mem=aligned_alloc(16,round16(ap_module_ns_state_size()));
    if(!sync_mem||!activity_mem||!aec_mem||!ns0_mem||!ns1_mem ||
       ap_module_sync_init(sync_mem,ap_module_sync_state_size(),0u,&sync)!=AP_OK ||
       ap_module_activity_init(activity_mem,ap_module_activity_state_size(),&ac,&activity)!=AP_OK ||
       ap_module_aec_init(aec_mem,ap_module_aec_state_size(),&ec,&aec)!=AP_OK ||
       ap_module_ns_init(ns0_mem,ap_module_ns_state_size(),&nc,&ns0)!=AP_OK ||
       ap_module_ns_init(ns1_mem,ap_module_ns_state_size(),&nc,&ns1)!=AP_OK)
        goto done;

    out=fopen(argv[3],"wbx");if(!out)goto done;
    meta=fopen(argv[4],"wbx");if(!meta)goto done;
    trace=fopen(argv[5],"wbx");if(!trace)goto done;
    if(fputs("frame,known_lead_samples,timestamp_observed,route_jump,aec_reset,sync_delay_samples,underrun,used_far,used_dt,aec_echo_energy,pre_ns_energy,ns_only_noise_dbfs,ns_freq_noise_dbfs,ns_only_speech_probability,ns_freq_speech_probability,ns_only_residual_echo_gain,ns_freq_residual_echo_gain,ns_freq_active,output_diff_samples,protected,carryover_allowed\n",trace)==EOF)
        goto done;

    for(uint32_t frame=0u;frame<frames;++frame){
        const uint64_t capture_end=(uint64_t)(frame+1u)*HOP;
        const uint32_t lead=lead_for(fault,frame,frames);
        const uint64_t desired=capture_end+lead;
        const uint64_t capture_ns=BASE_NS+capture_end*NS_PER_SAMPLE;
        const uint64_t render_ns=capture_ns-(uint64_t)lead*NS_PER_SAMPLE;
        ap_module_sync_event_t event={0};
        ap_module_sync_status_t sync_status={0};
        ap_module_activity_result_t ar;
        ap_module_aec_result_t aec_result={0};
        ap_module_ns_result_t n0={0},n1={0};
        int underrun=0,reset_this_frame=0;
        float mic_energy=1.0e-12f,ref_energy=1.0e-12f,pre_energy=1.0e-12f;
        unsigned diff_samples=0u;
        int protected_now,carryover_allowed;

        for(unsigned k=0;k<HOP;++k)mic[k]=data[((size_t)frame*HOP+k)*COLS];
        while(render_cursor<desired){
            const uint64_t remain=desired-render_cursor;
            const size_t chunk=remain>HOP?HOP:(size_t)remain;
            for(size_t k=0;k<chunk;++k)render_chunk[k]=physical_ref(data,samples,render_cursor+k);
            if(ap_module_sync_push_render(sync,render_chunk,chunk,frame)!=AP_OK)goto done;
            render_cursor+=chunk;
        }

        if(ap_module_sync_observe_timestamps(sync,capture_ns,render_ns,RATE,120u,&event)!=AP_OK)
            goto done;
        if(!event.timestamp_observed||!event.delay_observed)goto done;
        ++timestamp_observations;
        if(event.route_jump){
            ++route_jumps;
            ap_module_aec_reset(aec);
            ++aec_resets;
            reset_this_frame=1;
        }
        if(ap_module_sync_get_reference(sync,HOP,reference,&underrun)!=AP_OK)goto done;
        ap_module_sync_get_status(sync,&sync_status);
        underruns+=(unsigned)(underrun!=0);

        for(unsigned k=0;k<HOP;++k){
            mic_energy+=mic[k]*mic[k];
            ref_energy+=reference[k]*reference[k];
        }
        mic_energy/=HOP;ref_energy/=HOP;
        if(ap_module_activity_process(activity,mic_energy,ref_energy,&ar)!=AP_OK)goto done;
        far_frames+=ar.far_end_active;dt_frames+=ar.double_talk_active;

        if(ap_module_aec_process(aec,mic,reference,aec_out,predicted_echo,HOP,
                                 ar.far_end_active,ar.double_talk_active,&aec_result)!=AP_OK)
            goto done;
        for(unsigned k=0;k<HOP;++k)pre_energy+=aec_out[k]*aec_out[k];
        pre_energy/=HOP;

        if(ap_module_ns_process(ns0,AP_QUALITY_FULL,aec_out,predicted_echo,ns_only,HOP,
                                0,ar.far_end_active,ar.double_talk_active,&n0)!=AP_OK ||
           ap_module_ns_process(ns1,AP_QUALITY_FULL,aec_out,predicted_echo,ns_freq,HOP,
                                1,ar.far_end_active,ar.double_talk_active,&n1)!=AP_OK)
            goto done;

        if(float_bits(n0.noise_rms_dbfs)!=float_bits(n1.noise_rms_dbfs))++noise_bits_mismatch;
        if(float_bits(n0.speech_probability)!=float_bits(n1.speech_probability))++speech_bits_mismatch;
        if(noise_bits_mismatch||speech_bits_mismatch)goto done;

        protected_now=(!ar.far_end_active)||ar.double_talk_active;
        carryover_allowed=protected_now&&previous_freq_active;
        if(n1.frequency_res_active!=(uint8_t)(ar.far_end_active&&!ar.double_talk_active))
            goto done;
        if(n0.frequency_res_active)goto done;

        if(n1.frequency_res_active){
            ++freq_active_frames;
            residual_gain_sum+=(double)n1.residual_echo_gain;
            if(n1.residual_echo_gain<residual_gain_min)residual_gain_min=n1.residual_echo_gain;
            if(n1.residual_echo_gain>residual_gain_max)residual_gain_max=n1.residual_echo_gain;
        }
        if(protected_now)++protected_frames;

        for(unsigned k=0;k<HOP;++k){
            if(float_bits(ns_only[k])!=float_bits(ns_freq[k]))++diff_samples;
            packed[5u*k]=aec_out[k];
            packed[5u*k+1u]=predicted_echo[k];
            packed[5u*k+2u]=ns_only[k];
            packed[5u*k+3u]=ns_freq[k];
            packed[5u*k+4u]=reference[k];
        }

        if(protected_now){
            if(carryover_allowed){
                ++protected_carryover_frames;
                carryover_diff_samples+=diff_samples;
            }else{
                ++protected_steady_frames;
                protected_steady_diff_samples+=diff_samples;
                if(diff_samples)goto done;
            }
        }

        if(fwrite(packed,sizeof(float),HOP*5u,out)!=HOP*5u)goto done;
        if(fprintf(trace,"%u,%u,%u,%u,%u,%u,%u,%u,%u,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%.9g,%u,%u,%u,%u\n",
           frame,lead,(unsigned)event.timestamp_observed,(unsigned)event.route_jump,(unsigned)reset_this_frame,
           sync_status.delay_samples,(unsigned)(underrun!=0),(unsigned)ar.far_end_active,(unsigned)ar.double_talk_active,
           (double)aec_result.echo_energy,(double)pre_energy,(double)n0.noise_rms_dbfs,(double)n1.noise_rms_dbfs,
           (double)n0.speech_probability,(double)n1.speech_probability,(double)n0.residual_echo_gain,
           (double)n1.residual_echo_gain,(unsigned)n1.frequency_res_active,diff_samples,(unsigned)protected_now,
           (unsigned)carryover_allowed)<0)
            goto done;

        previous_freq_active=(int)n1.frequency_res_active;
        final_aec=aec_result;final_sync=sync_status;
    }

    if(fprintf(meta,
      "{\"status\":\"PASS\",\"fault\":\"%s\",\"frames\":%u,\"samples\":%zu,"
      "\"sample_rate_hz\":16000,\"frame_samples\":160,\"timestamp_authority\":true,"
      "\"route_jump_resets_aec\":true,\"time_domain_res_executed\":false,\"ns_quality\":\"FULL\","
      "\"ns_floor_gain\":0.18,\"timestamp_observations\":%u,\"route_jumps\":%u,\"aec_resets\":%u,"
      "\"underruns\":%u,\"far_frames\":%u,\"double_talk_frames\":%u,\"frequency_res_active_frames\":%u,"
      "\"protected_frames\":%u,\"protected_steady_frames\":%u,\"protected_carryover_frames\":%u,"
      "\"protected_steady_diff_samples\":%u,\"carryover_diff_samples\":%u,"
      "\"noise_bits_mismatch_frames\":%u,\"speech_bits_mismatch_frames\":%u,"
      "\"residual_echo_gain_mean_active\":%.9g,\"residual_echo_gain_min_active\":%.9g,"
      "\"residual_echo_gain_max_active\":%.9g,\"sync_state_bytes\":%zu,\"activity_state_bytes\":%zu,"
      "\"aec_state_bytes\":%zu,\"ns_state_bytes_each\":%zu,\"aec_active_taps\":%u,"
      "\"aec_block_samples\":%u,\"final_sync_delay_samples\":%u,"
      "\"shipping_authority\":false,\"source_revision\":\"%s\"}\n",
      fault==FAULT_STATIC?"static-lead":fault==FAULT_ROUTE?"route-jump":"drift-plus-250ppm",
      frames,samples,timestamp_observations,route_jumps,aec_resets,underruns,far_frames,dt_frames,
      freq_active_frames,protected_frames,protected_steady_frames,protected_carryover_frames,
      protected_steady_diff_samples,carryover_diff_samples,noise_bits_mismatch,speech_bits_mismatch,
      freq_active_frames?residual_gain_sum/(double)freq_active_frames:1.0,
      (double)residual_gain_min,(double)residual_gain_max,
      ap_module_sync_state_size(),ap_module_activity_state_size(),ap_module_aec_state_size(),
      ap_module_ns_state_size(),final_aec.active_taps,final_aec.block_samples,final_sync.delay_samples,
      AP_BUILD_SOURCE_REVISION)<0)
        goto done;

    rc=0;
done:
    free(data);free(sync_mem);free(activity_mem);free(aec_mem);free(ns0_mem);free(ns1_mem);
    if(in&&fclose(in))rc=2;
    if(out&&fclose(out))rc=2;
    if(meta&&fclose(meta))rc=2;
    if(trace&&fclose(trace))rc=2;
    if(rc)fputs("FE05 NS frequency-RES diagnostic failed; partial files are not evidence\n",stderr);
    return rc;
}
