/* FE09 T2-B/B0 #771: real first-party mic SRC/FIR33 remains continuous
 * while optional Render is genuinely absent in the DUT. No SPSC/recorder.
 * Paired Render in the BF oracle is a *synthetic counterfactual only*.
 */
#define _POSIX_C_SOURCE 200809L
#include "fe09_b2s3_t2b_b0_capture_only.h"
#define main fe_s3_t0_reference_main_unused
#include "fe09_b2s3_threaded_bridge_test.c"
#undef main

#include <inttypes.h>
#include <string.h>
#define B0_STATE_CAP 16384u
#define B0_WORK_CAP 32768u
#define B0_FRAMES 48u
typedef struct {
    fe_t2b_b0 adapter;
    fe_b1b1 *mic, *paired;
    size_t mic_size, mic_work_size, paired_size, paired_work_size;
    _Alignas(16) uint8_t mic_mem[B0_STATE_CAP], mic_work[B0_WORK_CAP];
    _Alignas(16) uint8_t paired_mem[B0_STATE_CAP], paired_work[B0_WORK_CAP];
    uint8_t mic_snapshot[B0_STATE_CAP];
    float mic_beam[160], paired_beam[160], paired_render[160];
    float actual_reference[160], reference_oracle[160];
    ap_resampler_state_t ref_oracle;
    int16_t capture[1920], render[480];
} b0_test;
static b0_test P;
static uint32_t checked;

static int has_render(uint32_t schedule, uint32_t frame) {
    if (schedule == 0u) return 1;
    if (schedule == 1u) return frame <= 9u || frame >= 25u;
    if (schedule == 2u)
        return frame <= 14u || (frame >= 20u && frame <= 29u) ||
               frame >= 38u;
    return frame <= 6u || frame >= 40u;
}
static void fresh(const scene_t *sc, uint32_t rate) {
    fe_b1b1_config paired_cfg=config_for(sc,rate,1u,2u).pipeline;
    fe_b1b1_config mic_cfg=paired_cfg;
    mic_cfg.ingress.render_channels=0u;
    memset(&P,0,sizeof(P));
    P.mic_size=fe_b1b1_state_bytes(&mic_cfg);
    P.mic_work_size=fe_b1b1_work_bytes(&mic_cfg);
    P.paired_size=fe_b1b1_state_bytes(&paired_cfg);
    P.paired_work_size=fe_b1b1_work_bytes(&paired_cfg);
    must(P.mic_size>0u && P.mic_size<=B0_STATE_CAP &&
         P.mic_work_size>0u && P.mic_work_size<=B0_WORK_CAP &&
         P.paired_size>0u && P.paired_size<=B0_STATE_CAP &&
         P.paired_work_size>0u && P.paired_work_size<=B0_WORK_CAP,
         "B0_FIRST_PARTY_ARENA_BOUNDS");
    must(fe_b1b1_init(P.mic_mem,P.mic_size,&mic_cfg,&P.mic)==FE_B1B1_OK &&
         fe_b1b1_init(P.paired_mem,P.paired_size,&paired_cfg,
                      &P.paired)==FE_B1B1_OK,
         "B0_ACTUAL_FIRST_PARTY_BF_INIT");
    must(fe_t2b_b0_bind(&P.adapter,P.mic,rate,sc->mics)==FE_T2B_B0_OK,
         "B0_ACTUAL_CAPTURE_ONLY_BIND");
    ap_resampler_init(&P.ref_oracle);
    must(memcmp(&P.ref_oracle,&P.adapter.render_src,
                sizeof(P.ref_oracle))==0,
         "B0_ORIGINAL_RENDER_SRC_NOT_INITIALIZED");
}
static void unchanged_after_bad_capture(uint64_t seq,
    const int16_t *pcm, size_t cap_count,
    float *beam, size_t beam_count, void *work, size_t work_bytes) {
    fe_t2b_b0 before=P.adapter;
    float prior[160];
    memcpy(P.mic_snapshot,P.mic_mem,P.mic_size);
    memcpy(prior,P.mic_beam,sizeof(prior));
    must(fe_t2b_b0_capture(&P.adapter,seq,pcm,cap_count,
         beam,beam_count,work,work_bytes)!=FE_T2B_B0_OK,
         "B0_INVALID_CAPTURE_FALSE_ACCEPT");
    must(memcmp(P.mic_snapshot,P.mic_mem,P.mic_size)==0 &&
         memcmp(&before,&P.adapter,sizeof(before))==0 &&
         memcmp(prior,P.mic_beam,sizeof(prior))==0,
         "B0_BAD_CAPTURE_MUTATED_REAL_BF_OR_OUTPUT");
    ++checked;
}
static void unchanged_after_bad_render(uint64_t seq,uint32_t flags,
    const int16_t *pcm,size_t count,float *out,size_t out_count) {
    fe_t2b_b0 before=P.adapter;
    float prior[160];
    memcpy(P.mic_snapshot,P.mic_mem,P.mic_size);
    memcpy(prior,P.actual_reference,sizeof(prior));
    must(fe_t2b_b0_render(&P.adapter,seq,flags,pcm,count,
                          out,out_count)!=FE_T2B_B0_OK,
         "B0_BAD_RENDER_FALSE_ACCEPT");
    must(memcmp(&before,&P.adapter,sizeof(before))==0 &&
         memcmp(P.mic_snapshot,P.mic_mem,P.mic_size)==0 &&
         memcmp(prior,P.actual_reference,sizeof(prior))==0,
         "B0_BAD_RENDER_MUTATED_BF_REF_HISTORY_OR_OUTPUT");
    ++checked;
}
static void receive_real_render(uint32_t rate,uint32_t frame) {
    const size_t n=(size_t)(rate/100u);
    uint32_t flags=0u;
    uint8_t snapshot[B0_STATE_CAP];
    fe_t2b_b0 before;
    if(P.adapter.render_sequence &&
       (uint64_t)frame != P.adapter.render_sequence + UINT64_C(1))
        flags=FE_T2B_B0_RENDER_GAP;
    if(flags) {
        unchanged_after_bad_render(frame,0u,P.render,n,
                                   P.actual_reference,160u);
    }
    unchanged_after_bad_render(frame,FE_B1B0_CLOCK_RESET,
                               P.render,n,P.actual_reference,160u);
    before=P.adapter;
    memcpy(snapshot,P.mic_mem,P.mic_size);
    must(fe_t2b_b0_render(&P.adapter,frame,flags,P.render,n,
                          P.actual_reference,160u)==FE_T2B_B0_OK,
         "B0_ACTUAL_PRESENT_ONLY_RENDER_SRC");
    if(flags) ap_resampler_reset(&P.ref_oracle);
    ap_resample_input_channel(&P.ref_oracle,0u,P.render,rate/100u,1u,0u,
                              P.reference_oracle,160u);
    must(memcmp(P.actual_reference,P.reference_oracle,
                sizeof(P.reference_oracle))==0 &&
         memcmp(&P.ref_oracle,&P.adapter.render_src,
                sizeof(P.ref_oracle))==0,
         "B0_RENDER_NOT_ORIGINAL_INDEPENDENT_SRC");
    must(memcmp(snapshot,P.mic_mem,P.mic_size)==0 &&
         before.capture_sequence==P.adapter.capture_sequence &&
         before.accepted_capture==P.adapter.accepted_capture,
         "B0_RENDER_CHANGED_CAPTURE_BF_HISTORY");
    unchanged_after_bad_render(frame,0u,P.render,n,
                               P.actual_reference,160u);
}
static uint64_t one(const scene_t *sc,uint32_t rate,uint32_t schedule,
                    uint64_t *bf_hash) {
    uint64_t control=FNV0,beam_hash=FNV0;
    uint32_t k,present=0u,missing=0u,ahead=0u;
    fe_b1b1_info capture_info,paired_info;
    const size_t cap_count=(size_t)(rate/100u)*sc->mics;
    const size_t render_count=(size_t)(rate/100u);
    fresh(sc,rate);
    for(k=1u;k<=B0_FRAMES;++k) {
        const int got=has_render(schedule,k);
        const uint32_t old_render_epoch=P.adapter.render_epoch;
        const uint64_t old_render_frames=P.adapter.accepted_render;
        ap_resampler_state_t old_render_hist=P.adapter.render_src;
        const double steer[3]={0.0,1.0,0.0};
        produce_pcm(sc,rate,k,P.capture,P.render);
        /* Explicit identical controls on two ACTUAL first-party BF cores. */
        if(k==17u) {
            const uint32_t mask=sc->mics==4u?13u:1u;
            must(fe_b1b1_set_active_mask(P.mic,mask)==FE_B1B1_OK &&
                 fe_b1b1_set_active_mask(P.paired,mask)==FE_B1B1_OK,
                 "B0_IDENTICAL_REAL_MIC_MASK");
        }
        if(k==29u) {
            must(fe_b1b1_request_steer(P.mic,steer,80u)==FE_B1B1_OK &&
                 fe_b1b1_request_steer(P.paired,steer,80u)==FE_B1B1_OK,
                 "B0_IDENTICAL_REAL_STEER");
        }
        /* Render call may arrive ahead of Capture; never infer clocks. */
        if(got && schedule==3u && k>=40u) {
            receive_real_render(rate,k);
            ++ahead;
        }
        unchanged_after_bad_capture(k+1u,P.capture,cap_count,
                       P.mic_beam,160u,P.mic_work,P.mic_work_size);
        unchanged_after_bad_capture(k,P.capture,cap_count-1u,
                       P.mic_beam,160u,P.mic_work,P.mic_work_size);
        unchanged_after_bad_capture(k,P.capture,cap_count,
                       P.mic_beam,159u,P.mic_work,P.mic_work_size);
        unchanged_after_bad_capture(k,P.capture,cap_count,
                       P.mic_beam,160u,P.mic_mem,P.mic_work_size);
        must(fe_t2b_b0_capture(&P.adapter,k,P.capture,cap_count,
               P.mic_beam,160u,P.mic_work,P.mic_work_size)==FE_T2B_B0_OK,
             "B0_CAPTURE_DID_NOT_PROGRESS_WITH_MISSING_RENDER");
        unchanged_after_bad_capture(k,P.capture,cap_count,
                       P.mic_beam,160u,P.mic_work,P.mic_work_size);
        /* The paired oracle's reference below is a COUNTERFACTUAL synthetic
         * stream, not a render-frame event admitted in this DUT.
         */
        must(fe_b1b1_process(P.paired,P.capture,cap_count,
               P.render,render_count,P.paired_beam,160u,
               P.paired_render,160u,P.paired_work,
               P.paired_work_size)==FE_B1B1_OK,
             "B0_COUNTERFACTUAL_PAIRED_BF_FAILED");
        must(memcmp(P.mic_beam,P.paired_beam,sizeof(P.mic_beam))==0,
             "B0_MIC_BEAM_BITWISE_MISMATCH_SAME_ISA");
        must(fe_b1b1_get_info(P.mic,&capture_info)==FE_B1B1_OK &&
             fe_b1b1_get_info(P.paired,&paired_info)==FE_B1B1_OK &&
             capture_info.accepted_frames==k &&
             paired_info.accepted_frames==k &&
             capture_info.clipped_samples==paired_info.clipped_samples &&
             capture_info.array.samples_processed==
                   paired_info.array.samples_processed &&
             capture_info.array.active_mask==paired_info.array.active_mask &&
             capture_info.array.steering_accepted==
                   paired_info.array.steering_accepted &&
             capture_info.source.capture_frames_in_epoch==
                   paired_info.source.capture_frames_in_epoch,
             "B0_CAPTURE_BF_FIRST_PARTY_HISTORY_DRIFT");
        for(uint32_t i=0u;i<sc->mics;++i)
            must(capture_info.source.mic_output_hash[i]==
                 paired_info.source.mic_output_hash[i],
                 "B0_MIC_SRC_HISTORY_HASH_DRIFT");
        beam_hash=hash(beam_hash,P.mic_beam,sizeof(P.mic_beam));
        if(!got) {
            ++missing;
            must(P.adapter.render_epoch==old_render_epoch &&
                 P.adapter.accepted_render==old_render_frames &&
                 memcmp(&P.adapter.render_src,&old_render_hist,
                        sizeof(old_render_hist))==0,
                 "B0_MISSING_RENDER_ADVANCED_OR_FABRICATED");
        } else {
            ++present;
            if(!(schedule==3u&&k>=40u))
                receive_real_render(rate,k);
        }
        must(P.adapter.accepted_capture==k &&
             P.adapter.capture_sequence==k,
             "B0_CAPTURE_HISTORY_NOT_CONTINUOUS");
        control=hash(control,&k,sizeof(k));
        control=hash(control,&P.adapter.accepted_render,
                     sizeof(P.adapter.accepted_render));
    }
    must(present+missing==B0_FRAMES &&
         (schedule==0u || missing>0u) &&
         (schedule!=3u || ahead>0u),
         "B0_SOURCE_SCHEDULE_NOT_EXECUTED");
    control=hash(control,&rate,sizeof(rate));
    control=hash(control,&sc->mics,sizeof(sc->mics));
    control=hash(control,&schedule,sizeof(schedule));
    control=hash(control,&present,sizeof(present));
    control=hash(control,&missing,sizeof(missing));
    control=hash(control,&ahead,sizeof(ahead));
    *bf_hash=beam_hash;
    return control;
}
int main(void) {
    uint32_t s,r,m,profiles=0u;
    uint64_t digest=FNV0;
    printf("{\"schema_version\":1,\"decision\":\"FE09_S3_T2B_B0_CAPTURE_ONLY_BF_EQUIVALENCE_NO_QUEUE_OR_RECORDER\",\"source_role\":\"first-party-synthetic\",\"capture_bf_progress_qualified\":true,\"recorder_qualified\":false,\"spsc_liveness_qualified\":false,\"physical_clock_qualified\":false,\"public_sdk_installed\":false,\"device_qualified\":false,\"profiles\":[");
    for(s=0u;s<4u;++s)
        for(r=0u;r<3u;++r)
            for(m=0u;m<4u;++m) {
                uint64_t beam_hash,control=one(&SCENES[s],RATES[r],m,
                                                &beam_hash);
                if(profiles) putchar(',');
                digest^=control; digest*=FNV_PRIME;
                printf("{\"scene\":\"%s\",\"rate\":%u,\"schedule\":%u,\"frames\":%u,\"control_hash\":\"%016" PRIx64 "\",\"bf_hash\":\"%016" PRIx64 "\"}",
                       SCENES[s].name,RATES[r],m,B0_FRAMES,control,
                       beam_hash);
                ++profiles;
            }
    must(profiles==48u && checked>=9000u,
         "B0_NEGATIVE_CONTROL_MATRIX_INCOMPLETE");
    printf("],\"profile_count\":%u,\"negative_checks\":%u,\"control_digest\":\"%016" PRIx64 "\"}\n",
           profiles,checked,digest);
    return 0;
}
