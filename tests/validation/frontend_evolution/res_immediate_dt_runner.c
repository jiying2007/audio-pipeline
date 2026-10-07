/* FE04 immediate double-talk RES protection diagnostic. */
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

static int self_test(void) {
    unsigned char *memory = NULL;
    ap_res_module_t *res = NULL;
    const size_t bytes = round16(ap_module_res_state_size());
    float samples[HOP];
    float gain = 0.0f;
    unsigned i;

    memory = (unsigned char *)aligned_alloc(16, bytes);
    if (!memory || ap_module_res_init(memory, ap_module_res_state_size(), &res) != AP_OK)
        goto fail;
    for (i = 0u; i < HOP; ++i) samples[i] = 1.0f;
    if (ap_module_res_process(res, AP_QUALITY_FULL, samples, HOP,
                              1.0f, 0.01f, 1, 0, &gain) != AP_OK)
        goto fail;
    if (!(gain >= 0.10f && gain < 1.0f) || !(samples[0] > 0.0f && samples[0] < 1.0f))
        goto fail;

    for (i = 0u; i < HOP; ++i) samples[i] = 1.0f;
    if (ap_module_res_process(res, AP_QUALITY_FULL, samples, HOP,
                              1.0f, 0.01f, 1, 1, &gain) != AP_OK)
        goto fail;
    if (gain != 1.0f || samples[0] != 1.0f) goto fail;

    ap_module_res_reset(res);
    for (i = 0u; i < HOP; ++i) samples[i] = 1.0f;
    if (ap_module_res_process(res, AP_QUALITY_FULL, samples, HOP,
                              0.0f, 0.0f, 0, 0, &gain) != AP_OK)
        goto fail;
    if (gain != 1.0f || samples[0] != 1.0f) goto fail;

    if (ap_module_res_process(res, AP_QUALITY_FULL, samples, HOP,
                              0.0f, -1.0f, 0, 0, &gain) != AP_EINVAL)
        goto fail;

    free(memory);
    puts("{\"status\":\"PASS\",\"far_only_attenuates\":true,"
         "\"double_talk_release_is_immediate\":true,\"reset_restores_unity\":true,"
         "\"invalid_energy_rejected\":true}");
    return 0;
fail:
    free(memory);
    fputs("AEC/RES self-test failed\n", stderr);
    return 2;
}

int main(int argc, char **argv) {
    FILE *in=NULL,*out=NULL,*meta=NULL,*trace=NULL;
    float *data=NULL;
    long bytes_long;
    size_t bytes,samples;
    uint32_t frames;
    enum fault_kind fault=0;
    int rc=2;

    void *sync_mem=NULL,*activity_mem=NULL,*aec_mem=NULL,*res_mem=NULL;
    ap_sync_module_t *sync=NULL;
    ap_activity_module_t *activity=NULL;
    ap_aec_module_t *aec=NULL;
    ap_res_module_t *res=NULL;

    const ap_module_activity_config_t ac={1.0e-7f,1.5f,3u};
    const ap_module_aec_config_t ec={RATE,64u,1u,0.2f};

    float mic[HOP],reference[HOP],render_chunk[HOP],aec_out[HOP],predicted_echo[HOP];
    float pre_res[HOP],post_res[HOP],packed[HOP*3u];
    uint64_t render_cursor=0u;
    unsigned route_jumps=0u,aec_resets=0u,timestamp_observations=0u,underruns=0u;
    unsigned far_frames=0u,dt_frames=0u,dt_gain_lt_099=0u,dt_gain_lt_095=0u;
    double gain_sum=0.0;
    float gain_min=1.0f,gain_max=1.0f;
    ap_module_aec_result_t final_aec={0};
    ap_module_sync_status_t final_sync={0};

    if (argc==2 && !strcmp(argv[1],"--self-test")) return self_test();
    if (argc!=6) {
        fputs("usage: res-immediate-dt static|route|drift INPUT.f32 OUTPUT.f32 META.json TRACE.csv\n", stderr);
        return 2;
    }
    if (!strcmp(argv[1],"static")) fault=FAULT_STATIC;
    else if (!strcmp(argv[1],"route")) fault=FAULT_ROUTE;
    else if (!strcmp(argv[1],"drift")) fault=FAULT_DRIFT;
    else { fputs("invalid fault\n", stderr); return 2; }

    in=fopen(argv[2],"rb"); if(!in) goto done;
    if (fseek(in,0,SEEK_END)) goto done;
    bytes_long=ftell(in);
    if (bytes_long<=0 || (unsigned long)bytes_long%(COLS*sizeof(float)) || fseek(in,0,SEEK_SET)) goto done;
    bytes=(size_t)bytes_long;
    samples=bytes/(COLS*sizeof(float));
    if (samples%HOP || samples/HOP>2000u) goto done;
    frames=(uint32_t)(samples/HOP);
    data=(float *)malloc(bytes);
    if (!data || fread(data,1,bytes,in)!=bytes) goto done;
    for (size_t i=0;i<samples*COLS;++i) if(!isfinite(data[i])) goto done;
    if (fclose(in)) { in=NULL; goto done; }
    in=NULL;

    sync_mem=aligned_alloc(16,round16(ap_module_sync_state_size()));
    activity_mem=aligned_alloc(16,round16(ap_module_activity_state_size()));
    aec_mem=aligned_alloc(16,round16(ap_module_aec_state_size()));
    res_mem=aligned_alloc(16,round16(ap_module_res_state_size()));
    if (!sync_mem || !activity_mem || !aec_mem || !res_mem ||
        ap_module_sync_init(sync_mem,ap_module_sync_state_size(),0u,&sync)!=AP_OK ||
        ap_module_activity_init(activity_mem,ap_module_activity_state_size(),&ac,&activity)!=AP_OK ||
        ap_module_aec_init(aec_mem,ap_module_aec_state_size(),&ec,&aec)!=AP_OK ||
        ap_module_res_init(res_mem,ap_module_res_state_size(),&res)!=AP_OK)
        goto done;

    out=fopen(argv[3],"wbx"); if(!out) goto done;
    meta=fopen(argv[4],"wbx"); if(!meta) goto done;
    trace=fopen(argv[5],"wbx"); if(!trace) goto done;
    if (fputs("frame,known_lead_samples,timestamp_observed,route_jump,aec_reset,sync_delay_samples,underrun,used_far,used_dt,aec_echo_energy,pre_residual_energy,res_gain,pre_output_energy,post_output_energy\n",trace)==EOF)
        goto done;

    for (uint32_t frame=0u;frame<frames;++frame) {
        const uint64_t capture_end=(uint64_t)(frame+1u)*HOP;
        const uint32_t lead=lead_for(fault,frame,frames);
        const uint64_t desired=capture_end+lead;
        const uint64_t capture_ns=BASE_NS+capture_end*NS_PER_SAMPLE;
        const uint64_t render_ns=capture_ns-(uint64_t)lead*NS_PER_SAMPLE;
        ap_module_sync_event_t event={0};
        ap_module_sync_status_t sync_status={0};
        ap_module_activity_result_t ar;
        ap_module_aec_result_t aec_result={0};
        int underrun=0,reset_this_frame=0;
        float mic_energy=1.0e-12f,ref_energy=1.0e-12f,residual_energy=1.0e-12f;
        float pre_energy=1.0e-12f,post_energy=1.0e-12f,gain=1.0f;

        for (unsigned k=0;k<HOP;++k) mic[k]=data[((size_t)frame*HOP+k)*COLS];
        while (render_cursor<desired) {
            const uint64_t remain=desired-render_cursor;
            const size_t chunk=remain>HOP?HOP:(size_t)remain;
            for (size_t k=0;k<chunk;++k) render_chunk[k]=physical_ref(data,samples,render_cursor+k);
            if (ap_module_sync_push_render(sync,render_chunk,chunk,frame)!=AP_OK) goto done;
            render_cursor+=chunk;
        }

        if (ap_module_sync_observe_timestamps(sync,capture_ns,render_ns,RATE,120u,&event)!=AP_OK)
            goto done;
        if (!event.timestamp_observed || !event.delay_observed) goto done;
        ++timestamp_observations;
        if (event.route_jump) {
            ++route_jumps;
            ap_module_aec_reset(aec);
            ++aec_resets;
            reset_this_frame=1;
        }
        if (ap_module_sync_get_reference(sync,HOP,reference,&underrun)!=AP_OK) goto done;
        ap_module_sync_get_status(sync,&sync_status);
        underruns+=(unsigned)(underrun!=0);

        for (unsigned k=0;k<HOP;++k) {
            mic_energy+=mic[k]*mic[k];
            ref_energy+=reference[k]*reference[k];
        }
        mic_energy/=HOP; ref_energy/=HOP;
        if (ap_module_activity_process(activity,mic_energy,ref_energy,&ar)!=AP_OK) goto done;
        far_frames+=ar.far_end_active;
        dt_frames+=ar.double_talk_active;

        if (ap_module_aec_process(aec,mic,reference,aec_out,predicted_echo,HOP,
                                  ar.far_end_active,ar.double_talk_active,&aec_result)!=AP_OK)
            goto done;
        for (unsigned k=0;k<HOP;++k) {
            residual_energy+=aec_out[k]*aec_out[k];
            pre_res[k]=aec_out[k];
            post_res[k]=aec_out[k];
        }
        residual_energy/=HOP;

        if (ap_module_res_process(res,AP_QUALITY_FULL,post_res,HOP,
                                  aec_result.echo_energy,residual_energy,
                                  ar.far_end_active,ar.double_talk_active,&gain)!=AP_OK)
            goto done;

        gain_sum+=(double)gain;
        if (gain<gain_min) gain_min=gain;
        if (gain>gain_max) gain_max=gain;
        if (ar.double_talk_active && gain<0.99f) ++dt_gain_lt_099;
        if (ar.double_talk_active && gain<0.95f) ++dt_gain_lt_095;

        for (unsigned k=0;k<HOP;++k) {
            pre_energy+=pre_res[k]*pre_res[k];
            post_energy+=post_res[k]*post_res[k];
            packed[3u*k]=pre_res[k];
            packed[3u*k+1u]=post_res[k];
            packed[3u*k+2u]=reference[k];
        }
        pre_energy/=HOP; post_energy/=HOP;
        if (fwrite(packed,sizeof(float),HOP*3u,out)!=HOP*3u) goto done;

        if (fprintf(trace,"%u,%u,%u,%u,%u,%u,%u,%u,%u,%.9g,%.9g,%.9g,%.9g,%.9g\n",
                    frame,lead,(unsigned)event.timestamp_observed,(unsigned)event.route_jump,
                    (unsigned)reset_this_frame,sync_status.delay_samples,(unsigned)(underrun!=0),
                    (unsigned)ar.far_end_active,(unsigned)ar.double_talk_active,
                    (double)aec_result.echo_energy,(double)residual_energy,(double)gain,
                    (double)pre_energy,(double)post_energy)<0)
            goto done;
        final_aec=aec_result;
        final_sync=sync_status;
    }

    if (fprintf(meta,
      "{\"status\":\"PASS\",\"fault\":\"%s\",\"frames\":%u,\"samples\":%zu,"
      "\"sample_rate_hz\":16000,\"frame_samples\":160,\"timestamp_authority\":true,"
      "\"route_jump_resets_aec\":true,\"route_jump_resets_res\":false,\"res_quality\":\"FULL\","
      "\"timestamp_observations\":%u,\"route_jumps\":%u,\"aec_resets\":%u,\"underruns\":%u,"
      "\"far_frames\":%u,\"double_talk_frames\":%u,\"double_talk_gain_lt_0_99_frames\":%u,"
      "\"double_talk_gain_lt_0_95_frames\":%u,\"res_gain_mean\":%.9g,\"res_gain_min\":%.9g,\"res_gain_max\":%.9g,"
      "\"sync_state_bytes\":%zu,\"activity_state_bytes\":%zu,\"aec_state_bytes\":%zu,\"res_state_bytes\":%zu,"
      "\"aec_active_taps\":%u,\"aec_block_samples\":%u,\"final_sync_delay_samples\":%u,"
      "\"shipping_authority\":false,\"source_revision\":\"%s\"}\n",
      fault==FAULT_STATIC?"static-lead":fault==FAULT_ROUTE?"route-jump":"drift-plus-250ppm",
      frames,samples,timestamp_observations,route_jumps,aec_resets,underruns,far_frames,dt_frames,
      dt_gain_lt_099,dt_gain_lt_095,gain_sum/(double)frames,(double)gain_min,(double)gain_max,
      ap_module_sync_state_size(),ap_module_activity_state_size(),ap_module_aec_state_size(),ap_module_res_state_size(),
      final_aec.active_taps,final_aec.block_samples,final_sync.delay_samples,AP_BUILD_SOURCE_REVISION)<0)
        goto done;

    rc=0;
done:
    free(data); free(sync_mem); free(activity_mem); free(aec_mem); free(res_mem);
    if (in && fclose(in)) rc=2;
    if (out && fclose(out)) rc=2;
    if (meta && fclose(meta)) rc=2;
    if (trace && fclose(trace)) rc=2;
    if (rc) fputs("FE04 immediate-DT RES diagnostic failed; partial files are not evidence\n",stderr);
    return rc;
}
