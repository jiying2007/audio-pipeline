/* #837: bounded read-only link observation of the ORIGINAL public library.
 * No oracle gates, copied DSP, callback allocation or callback I/O. */
#include "fe09_b3_f0_composition.h"
#include "core/ap_pipeline_internal.h"
#include <math.h>
#include <string.h>

#ifdef FE_B3_F0_OBSERVED
static fe_b3_observation rows[FE_B3_F0_FRAMES];
static struct {
    fe_b3_observation *current;
    const void *capture;
    size_t capture_bytes;
    const ap_pipeline_t *fresh;
    uint32_t notification_depth;
} context;
_Static_assert(sizeof(rows)+sizeof(context) <= 262144u, "observer RAM cap");
_Static_assert(sizeof(context) <= 8192u, "observer auxiliary RAM cap");

static uint32_t bits(float v) {
    uint32_t b;
    memcpy(&b,&v,sizeof(b));
    return b;
}
static fe_b3_observation *hit(unsigned id) {
    fe_b3_observation *r=context.current;
    if (!r) return NULL;
    ++r->calls[id];
    if (r->order_count < FE_B3_OBS_ORDER_CAP)
        r->order[r->order_count++] = id;
    else ++r->violations;
    return r;
}
static void valid(int yes) {
    if (context.current && !yes) ++context.current->violations;
}
void fe_b3_observer_configure(const void *capture,size_t n,
                              const ap_pipeline_t *fresh) {
    memset(rows,0,sizeof(rows));
    memset(&context,0,sizeof(context));
    context.capture=capture; context.capture_bytes=n; context.fresh=fresh;
}
void fe_b3_observer_begin(uint32_t f) {
    context.current=(f>=1u && f<=FE_B3_F0_FRAMES)?&rows[f-1u]:NULL;
    if (context.current) memset(context.current,0,sizeof(*context.current));
}
void fe_b3_observer_end(void) {
    fe_b3_observation *r=context.current;
    if (r) {
        for (unsigned k=FE_B3_OBS_HPF;k<=FE_B3_OBS_VAD;++k)
            if (r->calls[k] != 1u) ++r->violations;
        if (r->calls[FE_B3_OBS_RES] || r->calls[FE_B3_OBS_LEGACY_BF] ||
            r->calls[FE_B3_OBS_PUSH]>1u || r->calls[FE_B3_OBS_NOTIFY]>1u ||
            context.notification_depth) ++r->violations;
    }
    context.current=NULL;
}
const fe_b3_observation *fe_b3_observer_frame(uint32_t f) {
    return f>=1u && f<=FE_B3_F0_FRAMES?&rows[f-1u]:NULL;
}
size_t fe_b3_observer_storage_bytes(void) { return sizeof(rows)+sizeof(context); }
int fe_b3_observer_enabled(void) { return 1; }

extern void __real_ap_hpf_process(ap_hpf_state_t *,float *,uint32_t,uint32_t);
void __wrap_ap_hpf_process(ap_hpf_state_t *s,float *x,uint32_t n,uint32_t ch) {
    (void)hit(FE_B3_OBS_HPF);
    valid(n==160u && ch==0u);
    __real_ap_hpf_process(s,x,n,ch);
}
extern void __real_ap_beamformer_process(ap_beamformer_state_t *,int,
                                         float *,float *,float *,uint32_t);
void __wrap_ap_beamformer_process(ap_beamformer_state_t *s,int track,
                                   float *a,float *b,float *out,uint32_t n) {
    (void)hit(FE_B3_OBS_LEGACY_BF);
    __real_ap_beamformer_process(s,track,a,b,out,n);
}
extern void __real_ap_sync_track_delay(ap_sync_state_t *,const float *,uint32_t,
                                       uint32_t,uint32_t,int,int,ap_sync_event_t *);
void __wrap_ap_sync_track_delay(ap_sync_state_t *s,const float *mic,uint32_t n,
    uint32_t hz,uint32_t maximum,int tracking,int drift,ap_sync_event_t *event) {
    fe_b3_observation *r=hit(FE_B3_OBS_SYNC_TRACK);
    valid(n==160u && hz==16000u && maximum==180u && tracking==1 && drift==1);
    __real_ap_sync_track_delay(s,mic,n,hz,maximum,tracking,drift,event);
    if (r) { r->sync_delay_samples=s->delay_samples; r->route_jump=event->route_jump; }
}
extern int __real_ap_sync_get_reference(ap_sync_state_t *,uint32_t,float *);
int __wrap_ap_sync_get_reference(ap_sync_state_t *s,uint32_t n,float *out) {
    fe_b3_observation *r=hit(FE_B3_OBS_SYNC_REFERENCE);
    int rc;
    valid(n==160u);
    rc=__real_ap_sync_get_reference(s,n,out);
    if (r) r->sync_delay_samples=s->delay_samples;
    return rc;
}
extern void __real_ap_sync_push_render(ap_sync_state_t *,const float *,uint32_t,uint64_t);
void __wrap_ap_sync_push_render(ap_sync_state_t *s,const float *x,uint32_t n,uint64_t f) {
    (void)hit(FE_B3_OBS_PUSH);
    valid(n==160u);
    __real_ap_sync_push_render(s,x,n,f);
}
extern void __real_ap_sync_reset(ap_sync_state_t *);
void __wrap_ap_sync_reset(ap_sync_state_t *s) {
    (void)hit(FE_B3_OBS_SYNC_RESET);
    __real_ap_sync_reset(s);
}
extern void __real_ap_activity_process(ap_activity_state_t *,float,float,ap_activity_result_t *);
void __wrap_ap_activity_process(ap_activity_state_t *s,float mic,float ref,
                                ap_activity_result_t *result) {
    fe_b3_observation *r=hit(FE_B3_OBS_ACTIVITY);
    valid(isfinite(mic) && isfinite(ref) && mic>=0.0f && ref>=0.0f);
    __real_ap_activity_process(s,mic,ref,result);
    if (r) { r->far=result->far_end_active; r->dt=result->double_talk_active; }
}
extern void __real_ap_aec_backend_process(ap_aec_state_t *,int,float,uint32_t,
    const float *,const float *,float *,float *,int,int,ap_aec_result_t *);
void __wrap_ap_aec_backend_process(ap_aec_state_t *s,int enabled,float mu,uint32_t n,
    const float *mic,const float *ref,float *out,float *echo,int far,int dt,
    ap_aec_result_t *result) {
    fe_b3_observation *r=hit(FE_B3_OBS_AEC);
    valid(enabled==1 && mu==0.22f && n==160u);
    if (r) {
        r->aec_far=(uint32_t)far; r->aec_dt=(uint32_t)dt;
        valid(far==(int)r->far && dt==(int)r->dt &&
              r->calls[FE_B3_OBS_ACTIVITY]==1u);
    }
    __real_ap_aec_backend_process(s,enabled,mu,n,mic,ref,out,echo,far,dt,result);
}
extern void __real_ap_aec_backend_reset(ap_aec_state_t *);
void __wrap_ap_aec_backend_reset(ap_aec_state_t *s) {
    fe_b3_observation *r=hit(FE_B3_OBS_AEC_RESET);
    if (r) {
        if (context.notification_depth) ++r->explicit_aec_resets;
        else ++r->automatic_aec_resets;
    }
    __real_ap_aec_backend_reset(s);
}
extern float __real_ap_res_process(ap_res_state_t *,ap_enhance_mode_t,float *,
                                   uint32_t,float,float,int,int);
float __wrap_ap_res_process(ap_res_state_t *s,ap_enhance_mode_t mode,float *x,
    uint32_t n,float echo,float residual,int far,int dt) {
    (void)hit(FE_B3_OBS_RES);
    return __real_ap_res_process(s,mode,x,n,echo,residual,far,dt);
}
extern void __real_ap_ns_process(ap_ns_state_t *,ap_enhance_mode_t,float,
    const float *,const float *,float *,uint32_t,int,int,int,ap_ns_result_t *);
void __wrap_ap_ns_process(ap_ns_state_t *s,ap_enhance_mode_t mode,float floor,
    const float *in,const float *echo,float *out,uint32_t n,int enable,
    int far,int dt,ap_ns_result_t *result) {
    fe_b3_observation *r=hit(FE_B3_OBS_NS);
    valid(n==160u && floor==0.12f && mode==AP_ENHANCE_FULL && enable==1 && echo);
    if (r) {
        r->ns_far=(uint32_t)far; r->ns_dt=(uint32_t)dt;
        r->ns_enable=(uint32_t)enable; r->ns_echo_present=(uint32_t)(echo!=NULL);
        r->ns_mode=(uint32_t)mode;
        valid(far==(int)r->far && dt==(int)r->dt &&
              r->calls[FE_B3_OBS_AEC]==1u);
    }
    __real_ap_ns_process(s,mode,floor,in,echo,out,n,enable,far,dt,result);
    if (r) {
        r->frequency_res_active=result->frequency_res_active;
        r->residual_gain_bits=bits(result->residual_echo_gain);
        valid(result->frequency_res_active ==
          (uint8_t)(enable && echo && mode!=AP_ENHANCE_SAFE && far && !dt));
        valid(isfinite(result->residual_echo_gain) &&
              isfinite(result->speech_probability) && isfinite(result->noise_rms_dbfs));
    }
}
extern void __real_ap_agc_process_controlled(ap_agc_state_t *,float *,uint32_t,int);
void __wrap_ap_agc_process_controlled(ap_agc_state_t *s,float *x,uint32_t n,int allow) {
    fe_b3_observation *r=hit(FE_B3_OBS_AGC);
    valid(n==160u);
    if (r) {
        r->agc_allow=(uint32_t)allow;
        r->agc_gain_before_bits=bits(s->gain);
        valid(allow == !(r->far && !r->dt) && r->calls[FE_B3_OBS_NS]==1u);
    }
    __real_ap_agc_process_controlled(s,x,n,allow);
    if (r) { r->agc_gain_after_bits=bits(s->gain); valid(isfinite(s->gain)); }
}
extern void __real_ap_vad_process(ap_vad_state_t *,const float *,uint32_t,float,int,
                                  ap_vad_result_t *);
void __wrap_ap_vad_process(ap_vad_state_t *s,const float *x,uint32_t n,
                          float speech,int upstream,ap_vad_result_t *result) {
    fe_b3_observation *r=hit(FE_B3_OBS_VAD);
    valid(n==160u && upstream==1 && isfinite(speech));
    if (r) valid(r->calls[FE_B3_OBS_AGC]==1u);
    __real_ap_vad_process(s,x,n,speech,upstream,result);
    if (r) {
        r->vad_active=result->active; r->vad_probability_bits=bits(result->probability);
        valid(isfinite(result->probability));
    }
}
/* Observe the actual public notification; do not trust an adapter-filled count. */
extern ap_status_t __real_ap_pipeline_notify_stream_discontinuity(ap_pipeline_t *,
                                                          ap_discontinuity_flags_t,uint32_t);
ap_status_t __wrap_ap_pipeline_notify_stream_discontinuity(ap_pipeline_t *p,
    ap_discontinuity_flags_t flags,uint32_t lost) {
    fe_b3_observation *r=hit(FE_B3_OBS_NOTIFY);
    uint64_t before=0u,processed=0u;
    ap_status_t status;
    if (r) {
        r->notify_flags=flags; r->notify_lost_frames=lost;
        valid(flags==AP_DISCONTINUITY_RENDER_GAP && lost==1u &&
              context.capture && context.capture_bytes && context.fresh);
        if (context.capture) before=fe_b3_f0_hash_bytes(context.capture,context.capture_bytes);
        processed=p->metrics.processed_frames;
    }
    ++context.notification_depth;
    status=__real_ap_pipeline_notify_stream_discontinuity(p,flags,lost);
    --context.notification_depth;
    if (r) {
        const ap_pipeline_t *z=context.fresh;
        r->notify_status=(int32_t)status;
        r->notify_capture_preserved=(uint32_t)(context.capture &&
            before==fe_b3_f0_hash_bytes(context.capture,context.capture_bytes));
        r->notify_processed_preserved=(uint32_t)(p->metrics.processed_frames==processed);
        if (status==AP_OK && z) {
#define SAME_MEMBER(member,bit) \
            if (memcmp(&p->member,&z->member,sizeof(p->member))==0) \
                r->notify_reset_state_mask|=UINT32_C(1)<<(bit)
            SAME_MEMBER(resampler,0); SAME_MEMBER(hpf,1); SAME_MEMBER(sync,2);
            SAME_MEMBER(activity,3); SAME_MEMBER(aec,4); SAME_MEMBER(res,5);
            SAME_MEMBER(ns,6); SAME_MEMBER(agc,7); SAME_MEMBER(vad,8);
#undef SAME_MEMBER
        }
        valid(status==AP_OK && r->notify_capture_preserved &&
              r->notify_processed_preserved && r->notify_reset_state_mask==511u);
    }
    return status;
}
#else
void fe_b3_observer_configure(const void *p,size_t n,const ap_pipeline_t *fresh) {
    (void)p; (void)n; (void)fresh;
}
void fe_b3_observer_begin(uint32_t f) { (void)f; }
void fe_b3_observer_end(void) {}
const fe_b3_observation *fe_b3_observer_frame(uint32_t f) { (void)f; return NULL; }
size_t fe_b3_observer_storage_bytes(void) { return 0u; }
int fe_b3_observer_enabled(void) { return 0; }
#endif
