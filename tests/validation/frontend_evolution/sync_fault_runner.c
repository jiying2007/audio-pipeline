/* FE04 public-SYNC transport-fault diagnostic. Offline research only. */
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

enum arm_kind { ARM_ORACLE=1, ARM_RAW=2, ARM_SYNC=3, ARM_SYNC_RESET=4 };
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

int main(int argc, char **argv) {
    FILE *in=NULL,*out=NULL,*meta=NULL,*trace=NULL;
    float *data=NULL; long bytes_long; size_t bytes,samples; uint32_t frames;
    enum arm_kind arm=0; enum fault_kind fault=0; int rc=2;
    void *sync_mem=NULL,*activity_mem=NULL,*aec_mem=NULL;
    ap_sync_module_t *sync=NULL; ap_activity_module_t *activity=NULL; ap_aec_module_t *aec=NULL;
    const ap_module_activity_config_t ac={1.0e-7f,1.5f,3u};
    const ap_module_aec_config_t ec={RATE,64u,1u,0.2f};
    float mic[HOP],reference[HOP],render_chunk[HOP],aec_out[HOP],echo_est[HOP],packed[HOP*2u];
    uint64_t render_cursor=0u;
    unsigned underruns=0u,route_jumps=0u,slips=0u,delay_observations=0u,far_frames=0u,dt_frames=0u,aec_resets=0u;
    ap_module_sync_status_t final_sync={0}; ap_module_aec_result_t final_aec={0};
    int sync_enabled;

    if(argc!=7){fputs("usage: sync-fault oracle|raw|sync|sync-reset static|route|drift INPUT.f32 OUTPUT.f32 META.json TRACE.csv\n",stderr);return 2;}
    if(!strcmp(argv[1],"oracle"))arm=ARM_ORACLE;
    else if(!strcmp(argv[1],"raw"))arm=ARM_RAW;
    else if(!strcmp(argv[1],"sync"))arm=ARM_SYNC;
    else if(!strcmp(argv[1],"sync-reset"))arm=ARM_SYNC_RESET;
    else{fputs("invalid arm\n",stderr);return 2;}
    if(!strcmp(argv[2],"static"))fault=FAULT_STATIC;
    else if(!strcmp(argv[2],"route"))fault=FAULT_ROUTE;
    else if(!strcmp(argv[2],"drift"))fault=FAULT_DRIFT;
    else{fputs("invalid fault\n",stderr);return 2;}
    sync_enabled=(arm==ARM_SYNC || arm==ARM_SYNC_RESET);

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

    activity_mem=aligned_alloc(16,round16(ap_module_activity_state_size()));
    aec_mem=aligned_alloc(16,round16(ap_module_aec_state_size()));
    if(!activity_mem || !aec_mem ||
       ap_module_activity_init(activity_mem,ap_module_activity_state_size(),&ac,&activity)!=AP_OK ||
       ap_module_aec_init(aec_mem,ap_module_aec_state_size(),&ec,&aec)!=AP_OK)goto done;
    if(sync_enabled){
        sync_mem=aligned_alloc(16,round16(ap_module_sync_state_size()));
        if(!sync_mem || ap_module_sync_init(sync_mem,ap_module_sync_state_size(),0u,&sync)!=AP_OK)goto done;
    }

    out=fopen(argv[4],"wbx");if(!out)goto done;
    meta=fopen(argv[5],"wbx");if(!meta)goto done;
    trace=fopen(argv[6],"wbx");if(!trace)goto done;
    if(fputs("frame,known_lead_samples,pushed_samples,sync_delay_samples,delay_error_samples,estimated_drift_ppm,reference_sample_slips,delay_observed,route_jump,underrun,mic_energy,reference_energy,used_far,used_dt\n",trace)==EOF)goto done;

    for(uint32_t frame=0u;frame<frames;++frame){
        const uint64_t capture_end=(uint64_t)(frame+1u)*HOP;
        const uint32_t lead=lead_for(fault,frame,frames);
        const uint64_t desired=capture_end+lead;
        const uint64_t before=render_cursor;
        ap_module_sync_event_t event={0}; ap_module_sync_status_t status={0};
        ap_module_activity_result_t ar; int underrun=0;
        float me=1.0e-12f,re=1.0e-12f;
        for(unsigned k=0;k<HOP;++k)mic[k]=data[((size_t)frame*HOP+k)*COLS];
        while(render_cursor<desired){
            const uint64_t remain=desired-render_cursor;
            const size_t chunk=remain>HOP?HOP:(size_t)remain;
            for(size_t k=0;k<chunk;++k)render_chunk[k]=physical_ref(data,samples,render_cursor+k);
            if(sync_enabled && ap_module_sync_push_render(sync,render_chunk,chunk,frame)!=AP_OK)goto done;
            render_cursor+=chunk;
        }
        if(arm==ARM_ORACLE){
            for(unsigned k=0;k<HOP;++k)reference[k]=physical_ref(data,samples,(uint64_t)frame*HOP+k);
        }else if(arm==ARM_RAW){
            const uint64_t start=desired-HOP;
            for(unsigned k=0;k<HOP;++k)reference[k]=physical_ref(data,samples,start+k);
        }else{
            if(ap_module_sync_track(sync,mic,HOP,RATE,120u,1,1,&event)!=AP_OK)goto done;
            if(arm==ARM_SYNC_RESET && event.route_jump){
                ap_module_aec_reset(aec);
                ++aec_resets;
            }
            if(ap_module_sync_get_reference(sync,HOP,reference,&underrun)!=AP_OK)goto done;
            ap_module_sync_get_status(sync,&status);
            if(event.delay_observed)++delay_observations;
            if(event.route_jump)++route_jumps;
            slips+=event.reference_sample_slips;
            underruns+=(unsigned)(underrun!=0);
        }
        for(unsigned k=0;k<HOP;++k){me+=mic[k]*mic[k];re+=reference[k]*reference[k];}
        me/=HOP;re/=HOP;
        if(ap_module_activity_process(activity,me,re,&ar)!=AP_OK ||
           ap_module_aec_process(aec,mic,reference,aec_out,echo_est,HOP,ar.far_end_active,ar.double_talk_active,&final_aec)!=AP_OK)goto done;
        far_frames+=ar.far_end_active;dt_frames+=ar.double_talk_active;
        for(unsigned k=0;k<HOP;++k){packed[2u*k]=aec_out[k];packed[2u*k+1u]=reference[k];}
        if(fwrite(packed,sizeof(float),HOP*2u,out)!=HOP*2u)goto done;
        if(fprintf(trace,"%u,%u,%llu,%u,%d,%.9g,%u,%u,%u,%u,%.9g,%.9g,%u,%u\n",
             frame,lead,(unsigned long long)(render_cursor-before),
             sync_enabled?status.delay_samples:0u,sync_enabled?event.delay_error_samples:0,
             sync_enabled?(double)status.estimated_drift_ppm:0.0,
             sync_enabled?event.reference_sample_slips:0u,
             sync_enabled?(unsigned)event.delay_observed:0u,
             sync_enabled?(unsigned)event.route_jump:0u,(unsigned)(underrun!=0),
             (double)me,(double)re,(unsigned)ar.far_end_active,(unsigned)ar.double_talk_active)<0)goto done;
        if(sync_enabled)final_sync=status;
    }

    if(fprintf(meta,
      "{\"status\":\"PASS\",\"arm\":\"%s\",\"fault\":\"%s\",\"frames\":%u,\"samples\":%zu,"
      "\"sample_rate_hz\":16000,\"frame_samples\":160,\"initial_sync_delay_samples\":0,\"max_delay_ms\":120,"
      "\"delay_tracking\":true,\"drift_compensation\":true,\"route_jump_resets_aec\":%s,\"aec_resets\":%u,"
      "\"sync_state_bytes\":%zu,\"activity_state_bytes\":%zu,\"aec_state_bytes\":%zu,"
      "\"aec_active_taps\":%u,\"aec_block_samples\":%u,\"render_samples_pushed\":%llu,"
      "\"underruns\":%u,\"route_jumps\":%u,\"reference_sample_slips\":%u,\"delay_observations\":%u,"
      "\"final_sync_delay_samples\":%u,\"final_estimated_drift_ppm\":%.9g,"
      "\"used_far_frames\":%u,\"used_dt_frames\":%u,\"shipping_authority\":false,\"source_revision\":\"%s\"}\n",
      arm==ARM_ORACLE?"oracle":arm==ARM_RAW?"raw":arm==ARM_SYNC?"public-sync":"public-sync-reset",
      fault==FAULT_STATIC?"static-lead":fault==FAULT_ROUTE?"route-jump":"drift-plus-250ppm",
      frames,samples,arm==ARM_SYNC_RESET?"true":"false",aec_resets,
      sync_enabled?ap_module_sync_state_size():0u,ap_module_activity_state_size(),ap_module_aec_state_size(),
      final_aec.active_taps,final_aec.block_samples,(unsigned long long)render_cursor,underruns,route_jumps,slips,delay_observations,
      final_sync.delay_samples,(double)final_sync.estimated_drift_ppm,far_frames,dt_frames,AP_BUILD_SOURCE_REVISION)<0)goto done;
    rc=0;
done:
    free(data);free(sync_mem);free(activity_mem);free(aec_mem);
    if (in && fclose(in)) rc = 2;
    if (out && fclose(out)) rc = 2;
    if (meta && fclose(meta)) rc = 2;
    if (trace && fclose(trace)) rc = 2;
    if(rc)fputs("FE04 SYNC fault diagnostic failed; partial files are not evidence\n",stderr);
    return rc;
}
