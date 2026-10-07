/* FE04 timestamp robustness diagnostic. Offline research only. */
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
#define BASE_NS 20000000000ull

enum profile_kind { PROFILE_JITTER=1, PROFILE_DROPOUT=2, PROFILE_COMBINED=3 };
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

static int jitter_for(uint32_t frame) {
    static const int8_t pattern[4] = {0, 1, 0, -1};
    return (int)pattern[frame & 3u];
}

static int observe_frame(enum profile_kind profile, uint32_t frame) {
    if (profile == PROFILE_JITTER) return 1;
    return !(frame > 0u && frame % 20u == 0u);
}

static uint32_t timestamp_lead(enum profile_kind profile, uint32_t true_lead,
                               uint32_t frame) {
    int lead = (int)true_lead;
    if (profile == PROFILE_JITTER || profile == PROFILE_COMBINED)
        lead += jitter_for(frame);
    return (uint32_t)lead;
}

static int self_test(void) {
    unsigned char *mem = NULL;
    ap_sync_module_t *sync = NULL;
    ap_module_sync_event_t event;
    ap_module_sync_status_t before, after;
    const size_t bytes = round16(ap_module_sync_state_size());
    const uint64_t capture = BASE_NS + 1000ull * NS_PER_SAMPLE;

    mem = (unsigned char *)aligned_alloc(16, bytes);
    if (!mem || ap_module_sync_init(mem, ap_module_sync_state_size(), 0u, &sync) != AP_OK)
        goto fail;

    if (ap_module_sync_observe_timestamps(sync, capture, capture - 320ull * NS_PER_SAMPLE,
                                          RATE, 120u, &event) != AP_OK)
        goto fail;
    if (!event.timestamp_observed || !event.delay_observed || event.route_jump)
        goto fail;
    ap_module_sync_get_status(sync, &before);
    if (before.delay_samples != 320u) goto fail;

    if (ap_module_sync_observe_timestamps(sync, capture, capture, RATE, 120u, &event) != AP_EINVAL)
        goto fail;
    ap_module_sync_get_status(sync, &after);
    if (after.delay_samples != before.delay_samples ||
        after.estimated_drift_ppm != before.estimated_drift_ppm)
        goto fail;

    if (ap_module_sync_observe_timestamps(sync, capture,
                                          capture - 200ull * 1000000ull,
                                          RATE, 120u, &event) != AP_EINVAL)
        goto fail;
    ap_module_sync_get_status(sync, &after);
    if (after.delay_samples != before.delay_samples ||
        after.estimated_drift_ppm != before.estimated_drift_ppm)
        goto fail;

    if (ap_module_sync_observe_timestamps(sync, capture + 10000000ull,
                                          capture + 10000000ull - 800ull * NS_PER_SAMPLE,
                                          RATE, 120u, &event) != AP_OK)
        goto fail;
    ap_module_sync_get_status(sync, &after);
    if (!event.timestamp_observed || !event.delay_observed || !event.route_jump ||
        after.delay_samples != 800u)
        goto fail;

    free(mem);
    puts("{\"status\":\"PASS\",\"invalid_order_preserved\":true,"
         "\"invalid_range_preserved\":true,\"route_jump_semantics\":true}");
    return 0;
fail:
    free(mem);
    fputs("timestamp robustness self-test failed\n", stderr);
    return 2;
}

int main(int argc, char **argv) {
    FILE *in=NULL,*out=NULL,*meta=NULL,*trace=NULL;
    float *data=NULL; long bytes_long; size_t bytes,samples; uint32_t frames;
    enum profile_kind profile=0; enum fault_kind fault=0; int rc=2;
    void *sync_mem=NULL,*activity_mem=NULL,*aec_mem=NULL;
    ap_sync_module_t *sync=NULL; ap_activity_module_t *activity=NULL; ap_aec_module_t *aec=NULL;
    const ap_module_activity_config_t ac={1.0e-7f,1.5f,3u};
    const ap_module_aec_config_t ec={RATE,64u,1u,0.2f};
    float mic[HOP],reference[HOP],render_chunk[HOP],aec_out[HOP],echo_est[HOP],packed[HOP*2u];
    uint64_t render_cursor=0u;
    unsigned underruns=0u,route_jumps=0u,timestamp_observations=0u,timestamp_dropouts=0u;
    unsigned far_frames=0u,dt_frames=0u,aec_resets=0u;
    ap_module_sync_status_t final_sync={0}; ap_module_aec_result_t final_aec={0};

    if (argc==2 && !strcmp(argv[1],"--self-test")) return self_test();
    if(argc!=7){fputs("usage: sync-ts-robust jitter|dropout|combined static|route|drift INPUT.f32 OUTPUT.f32 META.json TRACE.csv\n",stderr);return 2;}
    if(!strcmp(argv[1],"jitter"))profile=PROFILE_JITTER;
    else if(!strcmp(argv[1],"dropout"))profile=PROFILE_DROPOUT;
    else if(!strcmp(argv[1],"combined"))profile=PROFILE_COMBINED;
    else{fputs("invalid profile\n",stderr);return 2;}
    if(!strcmp(argv[2],"static"))fault=FAULT_STATIC;
    else if(!strcmp(argv[2],"route"))fault=FAULT_ROUTE;
    else if(!strcmp(argv[2],"drift"))fault=FAULT_DRIFT;
    else{fputs("invalid fault\n",stderr);return 2;}

    in=fopen(argv[3],"rb");if(!in)goto done;
    if (fseek(in, 0, SEEK_END)) goto done;
    bytes_long = ftell(in);
    if(bytes_long<=0 || (unsigned long)bytes_long%(COLS*sizeof(float)) || fseek(in,0,SEEK_SET))goto done;
    bytes=(size_t)bytes_long;samples=bytes/(COLS*sizeof(float));
    if (samples % HOP || samples / HOP > 2000u) goto done;
    frames = (uint32_t)(samples / HOP);
    data=(float*)malloc(bytes);if(!data || fread(data,1,bytes,in)!=bytes)goto done;
    for(size_t i=0;i<samples*COLS;++i)if(!isfinite(data[i]))goto done;
    if(fclose(in)){in=NULL;goto done;}in=NULL;

    sync_mem=aligned_alloc(16,round16(ap_module_sync_state_size()));
    activity_mem=aligned_alloc(16,round16(ap_module_activity_state_size()));
    aec_mem=aligned_alloc(16,round16(ap_module_aec_state_size()));
    if(!sync_mem || !activity_mem || !aec_mem ||
       ap_module_sync_init(sync_mem,ap_module_sync_state_size(),0u,&sync)!=AP_OK ||
       ap_module_activity_init(activity_mem,ap_module_activity_state_size(),&ac,&activity)!=AP_OK ||
       ap_module_aec_init(aec_mem,ap_module_aec_state_size(),&ec,&aec)!=AP_OK)goto done;

    out=fopen(argv[4],"wbx");if(!out)goto done;
    meta=fopen(argv[5],"wbx");if(!meta)goto done;
    trace=fopen(argv[6],"wbx");if(!trace)goto done;
    if(fputs("frame,true_lead_samples,timestamp_lead_samples,timestamp_observed,pushed_samples,capture_timestamp_ns,render_timestamp_ns,sync_delay_samples,delay_error_samples,route_jump,underrun,aec_reset,mic_energy,reference_energy,used_far,used_dt\n",trace)==EOF)goto done;

    for(uint32_t frame=0u;frame<frames;++frame){
        const uint64_t capture_end=(uint64_t)(frame+1u)*HOP;
        const uint32_t true_lead=lead_for(fault,frame,frames);
        const uint32_t ts_lead=timestamp_lead(profile,true_lead,frame);
        const uint64_t desired=capture_end+true_lead;
        const uint64_t before=render_cursor;
        const uint64_t capture_ns=BASE_NS+capture_end*NS_PER_SAMPLE;
        const uint64_t render_ns=capture_ns-(uint64_t)ts_lead*NS_PER_SAMPLE;
        const int observe=observe_frame(profile,frame);
        ap_module_sync_event_t event={0};
        ap_module_sync_status_t status={0};
        ap_module_activity_result_t ar;
        int underrun=0,reset_this_frame=0;
        float me=1.0e-12f,re=1.0e-12f;

        for(unsigned k=0;k<HOP;++k)mic[k]=data[((size_t)frame*HOP+k)*COLS];
        while(render_cursor<desired){
            const uint64_t remain=desired-render_cursor;
            const size_t chunk=remain>HOP?HOP:(size_t)remain;
            for(size_t k=0;k<chunk;++k)render_chunk[k]=physical_ref(data,samples,render_cursor+k);
            if(ap_module_sync_push_render(sync,render_chunk,chunk,frame)!=AP_OK)goto done;
            render_cursor+=chunk;
        }

        if(observe){
            if(ap_module_sync_observe_timestamps(sync,capture_ns,render_ns,RATE,120u,&event)!=AP_OK)
                goto done;
            if(!event.timestamp_observed || !event.delay_observed)goto done;
            ++timestamp_observations;
            if(event.route_jump){
                ++route_jumps;
                ap_module_aec_reset(aec);
                ++aec_resets;
                reset_this_frame=1;
            }
        } else {
            ++timestamp_dropouts;
        }

        if(ap_module_sync_get_reference(sync,HOP,reference,&underrun)!=AP_OK)goto done;
        ap_module_sync_get_status(sync,&status);
        underruns+=(unsigned)(underrun!=0);

        for(unsigned k=0;k<HOP;++k){me+=mic[k]*mic[k];re+=reference[k]*reference[k];}
        me/=HOP;re/=HOP;
        if(ap_module_activity_process(activity,me,re,&ar)!=AP_OK ||
           ap_module_aec_process(aec,mic,reference,aec_out,echo_est,HOP,
                                 ar.far_end_active,ar.double_talk_active,&final_aec)!=AP_OK)goto done;
        far_frames+=ar.far_end_active;dt_frames+=ar.double_talk_active;
        for(unsigned k=0;k<HOP;++k){packed[2u*k]=aec_out[k];packed[2u*k+1u]=reference[k];}
        if(fwrite(packed,sizeof(float),HOP*2u,out)!=HOP*2u)goto done;

        if(fprintf(trace,"%u,%u,%u,%u,%llu,%llu,%llu,%u,%d,%u,%u,%u,%.9g,%.9g,%u,%u\n",
             frame,true_lead,ts_lead,(unsigned)observe,(unsigned long long)(render_cursor-before),
             (unsigned long long)capture_ns,(unsigned long long)render_ns,
             status.delay_samples,event.delay_error_samples,(unsigned)event.route_jump,
             (unsigned)(underrun!=0),(unsigned)reset_this_frame,
             (double)me,(double)re,(unsigned)ar.far_end_active,(unsigned)ar.double_talk_active)<0)goto done;
        final_sync=status;
    }

    if(fprintf(meta,
      "{\"status\":\"PASS\",\"profile\":\"%s\",\"fault\":\"%s\",\"frames\":%u,\"samples\":%zu,"
      "\"sample_rate_hz\":16000,\"frame_samples\":160,\"max_delay_ms\":120,"
      "\"timestamp_authority\":true,\"acoustic_tracking\":false,\"route_jump_resets_aec\":true,"
      "\"timestamp_observations\":%u,\"timestamp_dropouts\":%u,\"route_jumps\":%u,\"aec_resets\":%u,"
      "\"underruns\":%u,\"sync_state_bytes\":%zu,\"activity_state_bytes\":%zu,\"aec_state_bytes\":%zu,"
      "\"aec_active_taps\":%u,\"aec_block_samples\":%u,\"render_samples_pushed\":%llu,"
      "\"final_sync_delay_samples\":%u,\"final_estimated_drift_ppm\":%.9g,"
      "\"used_far_frames\":%u,\"used_dt_frames\":%u,\"shipping_authority\":false,\"source_revision\":\"%s\"}\n",
      profile==PROFILE_JITTER?"jitter-1s-reset":profile==PROFILE_DROPOUT?"dropout-5pct-reset":"jitter-1s-dropout-5pct-reset",
      fault==FAULT_STATIC?"static-lead":fault==FAULT_ROUTE?"route-jump":"drift-plus-250ppm",
      frames,samples,timestamp_observations,timestamp_dropouts,route_jumps,aec_resets,underruns,
      ap_module_sync_state_size(),ap_module_activity_state_size(),ap_module_aec_state_size(),
      final_aec.active_taps,final_aec.block_samples,(unsigned long long)render_cursor,
      final_sync.delay_samples,(double)final_sync.estimated_drift_ppm,
      far_frames,dt_frames,AP_BUILD_SOURCE_REVISION)<0)goto done;
    rc=0;
done:
    free(data);free(sync_mem);free(activity_mem);free(aec_mem);
    if (in && fclose(in)) rc = 2;
    if (out && fclose(out)) rc = 2;
    if (meta && fclose(meta)) rc = 2;
    if (trace && fclose(trace)) rc = 2;
    if(rc)fputs("FE04 timestamp robustness diagnostic failed; partial files are not evidence\n",stderr);
    return rc;
}
