/* FE09-B3-F0 #837. Frozen finite D0 driver, not an algorithm candidate.
 * Original B1B1 is compiled once in the seam TU. Test uses its read-only
 * pointer-normalized fingerprint helper; no copied DSP implementation. */
#define _POSIX_C_SOURCE 200809L
#include "fe09_b3_f0_composition.h"
#include "core/ap_pipeline_internal.h"
#include <errno.h>
#include <fenv.h>
#include <inttypes.h>
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#define B3_SAMPLES (FE_B3_F0_FRAMES*FE_B3_F0_HOP)
#define B3_STATE 16384u
#define B3_WORK 32768u
#define B3_ID "FE09-B3-F0-C4-16K-RENDER-PAP-V1"

typedef struct {
    fe_b1s0_state q;
    fe_t2b_b0 front;
    fe_b3_f0 seam;
    fe_b1b1 *core;
    ap_pipeline_t *mono;
    size_t state_bytes,work_bytes,mono_bytes;
    _Alignas(16) uint8_t state[B3_STATE],work[B3_WORK];
    _Alignas(16) uint8_t mono_memory[AP_PIPELINE_STATE_MAX_BYTES];
} b3_test_fixture;
typedef struct {
    fe_b3_f0_receipt receipt;
    ap_metrics_t metrics;
    uint64_t beam_hash,output_hash,capture_hash,render_hash,state_hash;
    uint64_t capture_accepted,capture_epoch,clock_epoch;
    uint32_t render_src_epoch;
} b3_test_frame;

static b3_test_fixture main_fixture,negative_fixture,snapshot;
static b3_test_frame log_rows[FE_B3_F0_FRAMES];
static int16_t capture_pcm[B3_SAMPLES*4u],render_pcm[B3_SAMPLES];
static int16_t output_pcm[B3_SAMPLES],negative_output[FE_B3_F0_HOP],saved_output[FE_B3_F0_HOP];
static float beam_pcm[B3_SAMPLES];
static fe_b3_f0_receipt negative_receipt,saved_receipt;
static _Alignas(16) uint8_t fresh_mono_memory[AP_PIPELINE_STATE_MAX_BYTES];
static ap_pipeline_t *fresh_mono;
static uint8_t canonical_state[B3_STATE];
static uint32_t completed,negative_mask,setup_publications;
static uint32_t attempted_frame,active_negative;
static const char *phase="initialization";
static b3_test_fixture *failure_fixture=&main_fixture;
static uint64_t present_count,absent_count,notify_count,beam_clips,reference_clips;
static uint64_t direct_render_ordinal;
static const char *failure;
static int case_pap,mode_direct,future_change,do_negatives;

static int b3_test_need(int ok,const char *why) {
    if (!ok && !failure) failure=why;
    return ok;
}
static uint32_t b3_test_next(uint32_t *s) {
    *s=UINT32_C(1664525)*(*s)+UINT32_C(1013904223);
    return *s;
}
/* This integer generator is independent of root's pre-result Python fixture.
 * Always advance near RNG, including when its contribution is zero. */
static void b3_test_generate(void) {
    uint32_t rr=UINT32_C(2654435769),nr=UINT32_C(608135816);
    uint32_t mr[4]={UINT32_C(286331153),UINT32_C(572662306),
                    UINT32_C(858993459),UINT32_C(1145324612)};
    for (uint32_t n=0;n<B3_SAMPLES;++n) {
        int32_t r=(int32_t)((b3_test_next(&rr)>>16u)&8191u)-4096;
        render_pcm[n]=(int16_t)r;
    }
    for (uint32_t n=0;n<B3_SAMPLES;++n) {
        uint32_t f=n/FE_B3_F0_HOP+1u;
        int32_t near=(int32_t)((b3_test_next(&nr)>>16u)&32767u)-16384;
        int32_t echo=n<640u?0:(int32_t)render_pcm[n-640u]/4;
        if (f<161u || f>280u) near=0;
        for (uint32_t j=0;j<4u;++j) {
            int32_t noise=(int32_t)((b3_test_next(&mr[j])>>24u)&127u)-64;
            capture_pcm[(size_t)n*4u+j]=(int16_t)(echo+near+noise);
        }
    }
}
static fe_b1b1_config b3_test_array_config(uint32_t hz) {
    fe_b1b1_config c;
    static const double x[4]={0.0,0.035,0.07,0.105};
    memset(&c,0,sizeof(c));
    c.ingress.struct_size=(uint32_t)sizeof(c.ingress);
    c.ingress.api_version=FE_B1B0_VERSION;
    c.ingress.capture_and_render_rate_hz=hz;
    c.ingress.frame_ms=10u;
    c.ingress.physical_mics=4u;
    c.ingress.active_mic_mask=15u;
    c.array.sample_rate_hz=16000u;
    c.array.mic_count=4u;c.array.active_mask=15u;
    c.array.reference_mic=0u;c.array.interpolation=FE_ARRAY_FIR33_HANN;
    c.array.direction[1]=1.0;
    for (uint32_t j=0;j<4u;++j) {
        c.ingress.physical_to_capture_slot[j]=j;
        c.array.microphones[j].input_channel=j;
        c.array.microphones[j].gain=1.0;
        c.array.microphones[j].position_m[0]=x[j];
    }
    return c;
}
static ap_config_t b3_test_mono_config(void) {
    ap_config_t c=ap_config_default(AP_PROFILE_CALL);
    c.io_sample_rate_hz=16000u;c.internal_sample_rate_hz=16000u;
    c.mic_channels=1u;c.stages&=~(ap_stage_mask_t)AP_STAGE_BF;
    return c;
}
static int b3_test_init(b3_test_fixture *f,uint32_t rate,int ns,int bind) {
    fe_b1b1_config c=b3_test_array_config(rate);
    ap_config_t mono=b3_test_mono_config();
    fe_b1s0_config q;
    failure_fixture=f;
    memset(f,0,sizeof(*f));
    memset(&q,0,sizeof(q));
    f->state_bytes=fe_b1b1_state_bytes(&c);
    f->work_bytes=fe_b1b1_work_bytes(&c);
    f->mono_bytes=ap_pipeline_state_size();
    if (!b3_test_need(f->state_bytes>0u && f->state_bytes<=B3_STATE &&
        f->work_bytes>0u && f->work_bytes<=B3_WORK &&
        f->mono_bytes<=sizeof(f->mono_memory),"CONFIGURATION_ARENA_BOUND"))
        return 0;
    if (!ns) mono.stages&=~(ap_stage_mask_t)AP_STAGE_NS;
    if (!b3_test_need(fe_b1b1_init(f->state,f->state_bytes,&c,&f->core)==FE_B1B1_OK &&
        fe_t2b_b0_bind(&f->front,f->core,rate,4u)==FE_T2B_B0_OK &&
        ap_pipeline_init(f->mono_memory,f->mono_bytes,&mono,&f->mono)==AP_OK,
        "ORIGINAL_INITIALIZER_FAILED")) return 0;
    q.depth=2u;q.physical_mics=4u;q.input_hz=rate;q.render_enabled=1u;
    q.capture_source_id=FE_B3_F0_CAPTURE_ID;q.render_source_id=FE_B3_F0_RENDER_ID;
    q.source_generation=FE_B3_F0_GENERATION;
    if (!b3_test_need(fe_b1s0_init(&f->q,&q,&f->front)==FE_B1S0_OK,
                       "ORIGINAL_OWNER_INIT_FAILED")) return 0;
    if (bind && !b3_test_need(fe_b3_f0_bind(&f->seam,&f->q,f->mono,f->mono_bytes)
                  ==FE_B3_F0_OK,"FROZEN_SEAM_BIND_FAILED")) return 0;
    return 1;
}
static uint64_t b3_test_state_fingerprint(const b3_test_fixture *f) {
    /* Actual original layout, not a guessed ABI mirror. All SRC/FIR histories
     * and every scalar are retained; only two allocation addresses are zeroed. */
    return fe_b3_f0_capture_fingerprint(f->core,f->state_bytes,
                                       canonical_state,sizeof(canonical_state));
}
static void b3_test_snapshot(b3_test_fixture *f) {
    /* The frozen driver has NO running producer threads. Full snapshots here
     * test reject nonmutation only; they are never runtime rollback. */
    failure_fixture=f;
    memcpy(&snapshot,f,sizeof(snapshot));
    memcpy(saved_output,negative_output,sizeof(saved_output));
    memcpy(&saved_receipt,&negative_receipt,sizeof(saved_receipt));
}
static int b3_test_negative_done(b3_test_fixture *f,unsigned id,int ok) {
    if (!b3_test_need(ok && memcmp(&snapshot,f,sizeof(snapshot))==0 &&
        memcmp(saved_output,negative_output,sizeof(saved_output))==0 &&
        memcmp(&saved_receipt,&negative_receipt,sizeof(saved_receipt))==0,
        "API_REJECTION_NOT_ATOMIC")) return 0;
    if (!b3_test_need(id>=1u && id<=16u &&
        (negative_mask&(UINT32_C(1)<<(id-1u)))==0u,"DUPLICATE_NEGATIVE")) return 0;
    negative_mask|=UINT32_C(1)<<(id-1u);
    active_negative=0u;failure_fixture=&main_fixture;
    return 1;
}
#define NEGATIVE(f,id,expr) do { \
    active_negative=(id); \
    b3_test_snapshot(f); \
    if (!b3_test_negative_done(f,id,(expr))) return 0; \
} while (0)

static int b3_test_initial_negatives(void) {
    b3_test_fixture *f=&negative_fixture;
    memset(negative_output,0x5a,sizeof(negative_output));
    memset(&negative_receipt,0xa5,sizeof(negative_receipt));
    if (!b3_test_init(f,16000u,1,1)) return 0;
    NEGATIVE(f,1u,fe_b1s0_capture_submit(&f->q,105u,FE_B3_F0_GENERATION,
        1u,capture_pcm,640u)==FE_B1S0_REJECT);
    NEGATIVE(f,2u,fe_b1s0_render_present(&f->q,204u,UINT64_C(900002),
        1u,1u,0u,render_pcm,160u)==FE_B1S0_REJECT);
    NEGATIVE(f,3u,fe_b1s0_capture_submit(&f->q,104u,FE_B3_F0_GENERATION,
        2u,capture_pcm,640u)==FE_B1S0_REJECT);
    NEGATIVE(f,7u,fe_b1s0_render_absent(&f->q,204u,FE_B3_F0_GENERATION,
        1u,1u,0u)==FE_B1S0_REJECT);
    NEGATIVE(f,8u,fe_b1s0_render_present(&f->q,204u,FE_B3_F0_GENERATION,
        1u,1u,0u,render_pcm,159u)==FE_B1S0_REJECT);
    if (!b3_test_need(fe_b1s0_capture_submit(&f->q,104u,FE_B3_F0_GENERATION,
        1u,capture_pcm,640u)==FE_B1S0_OK,"N04_SETUP_FAILED")) return 0;
    ++setup_publications;
    NEGATIVE(f,4u,fe_b3_f0_process_one(&f->seam,negative_output,160u,
        f->work,f->work_bytes,&negative_receipt)==FE_B3_F0_PENDING);
    if (!b3_test_init(f,16000u,0,0)) return 0;
    NEGATIVE(f,12u,fe_b3_f0_bind(&f->seam,&f->q,f->mono,f->mono_bytes)==FE_B3_F0_REJECT);
    if (!b3_test_init(f,32000u,1,0)) return 0;
    NEGATIVE(f,13u,fe_b3_f0_bind(&f->seam,&f->q,f->mono,f->mono_bytes)==FE_B3_F0_REJECT);
    if (!b3_test_init(f,16000u,1,1)) return 0;
    for (uint32_t seq=1u;seq<=2u;++seq) {
        if (!b3_test_need(fe_b1s0_capture_submit(&f->q,104u,FE_B3_F0_GENERATION,
            seq,capture_pcm+(size_t)(seq-1u)*640u,640u)==FE_B1S0_OK &&
            fe_b1s0_render_present(&f->q,204u,FE_B3_F0_GENERATION,seq,1u,0u,
            render_pcm+(size_t)(seq-1u)*160u,160u)==FE_B1S0_OK,
            "N16_SETUP_FAILED")) return 0;
        setup_publications+=2u;
    }
    NEGATIVE(f,16u,fe_b1s0_capture_submit(&f->q,104u,FE_B3_F0_GENERATION,
        3u,capture_pcm+1280u,640u)==FE_B1S0_FULL);
    return b3_test_need(setup_publications==5u,"NEGATIVE_SETUP_BUDGET_CHANGED");
}
static int b3_test_frame1_negatives(void) {
    b3_test_fixture *f=&main_fixture;
    NEGATIVE(f,9u,fe_b3_f0_process_one(&f->seam,negative_output,159u,
        f->work,f->work_bytes,&negative_receipt)==FE_B3_F0_REJECT);
    NEGATIVE(f,10u,fe_b3_f0_process_one(&f->seam,(int16_t *)f->mono_memory,160u,
        f->work,f->work_bytes,&negative_receipt)==FE_B3_F0_REJECT);
    f->q.cfg.source_generation=UINT64_C(900002);
    NEGATIVE(f,11u,fe_b3_f0_process_one(&f->seam,negative_output,160u,
        f->work,f->work_bytes,&negative_receipt)==FE_B3_F0_REJECT);
    f->q.cfg.source_generation=FE_B3_F0_GENERATION;
    NEGATIVE(f,15u,fe_b3_f0_process_one(&f->seam,negative_output,160u,
        f->work,f->work_bytes-1u,&negative_receipt)==FE_B3_F0_REJECT);
    return 1;
}
static int b3_test_postframe1_negative(void) {
    b3_test_fixture *f=&main_fixture;
    NEGATIVE(f,14u,fe_b3_f0_bind(&f->seam,&f->q,f->mono,f->mono_bytes)==FE_B3_F0_REJECT);
    return 1;
}
static int b3_test_reentry_negatives(void) {
    b3_test_fixture *f=&main_fixture;
    const int16_t *r=render_pcm+(size_t)240u*160u;
    NEGATIVE(f,5u,fe_b1s0_render_present(&f->q,204u,FE_B3_F0_GENERATION,
        241u,2u,0u,r,160u)==FE_B1S0_REJECT);
    NEGATIVE(f,6u,fe_b1s0_render_present(&f->q,204u,FE_B3_F0_GENERATION,
        241u,1u,FE_B1S0_RENDER_GAP,r,160u)==FE_B1S0_REJECT);
    return 1;
}
#undef NEGATIVE

/* Expected source publisher belongs to the TEST, never to the new adapter. */
static int b3_test_publish(uint32_t seq,const int16_t *capture,const int16_t *render) {
    fe_b1s0_status rc;
    if (!b3_test_need(fe_b1s0_capture_submit(&main_fixture.q,104u,
        FE_B3_F0_GENERATION,seq,capture,640u)==FE_B1S0_OK,"CAPTURE_PUBLICATION_FAILED"))
        return 0;
    if (case_pap && seq>=201u && seq<=240u)
        rc=fe_b1s0_render_absent(&main_fixture.q,204u,FE_B3_F0_GENERATION,
                                seq,1u,FE_B1S0_ABSENT_SOURCE_REPORTED);
    else rc=fe_b1s0_render_present(&main_fixture.q,204u,FE_B3_F0_GENERATION,
        seq,(case_pap && seq>=241u)?2u:1u,
        (case_pap && seq==241u)?FE_B1S0_RENDER_GAP:0u,render,160u);
    return b3_test_need(rc==FE_B1S0_OK,"RENDER_OWNER_EVENT_FAILED");
}
/* Independent literal-control replay. No adapter bind/process/classifier,
 * no adapter receipt/control data and no oracle Activity/DTD/AEC gate. */
static int16_t b3_test_direct_s16(float x,uint64_t *clipped) {
    long v;
    if (x>=1.0f) { ++*clipped; return INT16_MAX; }
    if (x<=-1.0f) { if (x < -1.0f) ++*clipped; return INT16_MIN; }
    v=lrintf(x*32768.0f);
    if (v>INT16_MAX) { ++*clipped; return INT16_MAX; }
    if (v<INT16_MIN) { ++*clipped; return INT16_MIN; }
    return (int16_t)v;
}
static int b3_test_direct(uint32_t seq,const int16_t *capture,const int16_t *render,
                          int16_t *out,fe_b3_f0_receipt *receipt) {
    b3_test_fixture *f=&main_fixture;
    float ref[160];
    int16_t mono[160],r16[160];
    int missing=0;
    uint64_t before;
    if (case_pap==1 && seq>=201u && seq<=240u) missing=1;
    memset(receipt,0,sizeof(*receipt));
    if (!missing) {
        ++direct_render_ordinal;
        if (!b3_test_need(fe_t2b_b0_render(&f->front,direct_render_ordinal,
            (case_pap==1 && seq==241u)?FE_T2B_B0_RENDER_GAP:0u,
            render,160u,ref,160u)==FE_T2B_B0_OK,"DIRECT_REAL_RENDER_SRC_FAILED"))
            return 0;
    }
    if (!b3_test_need(fe_t2b_b0_capture(&f->front,seq,capture,640u,
        receipt->beam,160u,f->work,f->work_bytes)==FE_T2B_B0_OK,
        "DIRECT_REAL_CAPTURE_BF_FAILED")) return 0;
    for (uint32_t i=0;i<160u;++i) {
        if (!b3_test_need(isfinite(receipt->beam[i]) &&
            (missing || isfinite(ref[i])),"DIRECT_NONFINITE")) return 0;
        mono[i]=b3_test_direct_s16(receipt->beam[i],&receipt->beam_clips);
        if (!missing) r16[i]=b3_test_direct_s16(ref[i],&receipt->reference_clips);
    }
    /* Literal frozen boundary, not shared edge-detection code. */
    if (case_pap==1 && (seq==201u || seq==241u)) {
        before=fe_b3_f0_hash_bytes(f->state,f->state_bytes);
        if (!b3_test_need(ap_pipeline_notify_stream_discontinuity(f->mono,
            AP_DISCONTINUITY_RENDER_GAP,1u)==AP_OK,"DIRECT_NOTIFY_FAILED")) return 0;
        receipt->notify_capture_preserved=(uint32_t)(before==
            fe_b3_f0_hash_bytes(f->state,f->state_bytes));
        receipt->explicit_notify=1u;
        if (!b3_test_need(receipt->notify_capture_preserved,"DIRECT_FRONT_RESET")) return 0;
    }
    if (!missing && !b3_test_need(ap_pipeline_push_render(f->mono,r16,160u)==AP_OK,
                                   "DIRECT_RENDER_PUSH_FAILED")) return 0;
    if (!b3_test_need(ap_pipeline_process_capture(f->mono,mono,160u,out)==AP_OK,
                       "DIRECT_CAPTURE_FAILED")) return 0;
    receipt->source.source_generation=FE_B3_F0_GENERATION;
    receipt->source.capture_sequence=seq;
    receipt->source.capture_source_id=104u;receipt->source.render_source_id=204u;
    receipt->source.capture_pcm_hash=fe_b3_f0_hash_s16(capture,640u);
    receipt->source.render_pcm_hash=missing?0u:fe_b3_f0_hash_s16(render,160u);
    receipt->source.render_event=missing?FE_B1S0_RENDER_ABSENT:FE_B1S0_RENDER_PRESENT;
    receipt->source.render_epoch=(case_pap==1 && seq>=241u)?2u:1u;
    receipt->source.render_reason=missing?FE_B1S0_ABSENT_SOURCE_REPORTED:0u;
    receipt->source.mic_bf_progressed=1u;receipt->source.reference_actual_pcm=(uint32_t)!missing;
    receipt->absent_reference_untouched=(uint32_t)missing;
    return 1;
}
static int b3_test_metrics_finite(const ap_metrics_t *m) {
    return isfinite(m->input_rms_dbfs) && isfinite(m->output_rms_dbfs) &&
        isfinite(m->noise_rms_dbfs) && isfinite(m->erle_db) &&
        isfinite(m->residual_echo_gain) && isfinite(m->vad_probability) &&
        isfinite(m->estimated_drift_ppm);
}
static int b3_test_run(void) {
    b3_test_fixture *f=&main_fixture;
    ap_config_t fresh_config=b3_test_mono_config();
    if (!b3_test_init(f,16000u,1,!mode_direct)) return 0;
    if (!b3_test_need(ap_pipeline_init(fresh_mono_memory,sizeof(fresh_mono_memory),
        &fresh_config,&fresh_mono)==AP_OK,"FRESH_RESET_REFERENCE_INIT_FAILED")) return 0;
    phase="initial_negative_controls";
    if (do_negatives && !b3_test_initial_negatives()) return 0;
    failure_fixture=f;
    fe_b3_observer_configure(f->state,f->state_bytes,fresh_mono);
    for (uint32_t seq=1u;seq<=600u;++seq) {
        int16_t cap[640],ref[160];
        size_t at=(size_t)(seq-1u)*160u;
        b3_test_frame *row=&log_rows[seq-1u];
        fe_b1b1_info info;
        int expected_missing=(case_pap && seq>=201u && seq<=240u);
        int expected_notify=(case_pap && (seq==201u || seq==241u));
        attempted_frame=seq;phase="source_publication";
        memcpy(cap,capture_pcm+at*4u,sizeof(cap));
        memcpy(ref,render_pcm+at,sizeof(ref));
        if (future_change && seq>240u) {
            for (uint32_t i=0;i<640u;++i) cap[i]=(int16_t)-cap[i];
            for (uint32_t i=0;i<160u;++i) ref[i]=(int16_t)-ref[i];
        }
        if (do_negatives && seq==241u) {
            phase="reentry_negative_controls";
            if (!b3_test_reentry_negatives()) return 0;
        }
        phase="source_publication";
        if (!mode_direct && !b3_test_publish(seq,cap,ref)) return 0;
        if (do_negatives && seq==1u) {
            phase="precommit_negative_controls";
            if (!b3_test_frame1_negatives()) return 0;
        }
        phase="processing";
        fe_b3_observer_begin(seq);
        if (mode_direct) {
            if (!b3_test_direct(seq,cap,ref,output_pcm+at,&row->receipt)) {
                fe_b3_observer_end();return 0;
            }
        } else {
            fe_b3_f0_status rc=fe_b3_f0_process_one(&f->seam,output_pcm+at,160u,
                 f->work,f->work_bytes,&row->receipt);
            if (!b3_test_need(rc==FE_B3_F0_OK,
                rc==FE_B3_F0_FATAL?"COMPOSITION_INVARIANT_BREACH":"COMPOSITION_FRAME_REJECTED")) {
                fe_b3_observer_end();return 0;
            }
        }
        fe_b3_observer_end();
        phase="frame_validation";
        memcpy(beam_pcm+at,row->receipt.beam,sizeof(row->receipt.beam));
        ap_pipeline_get_metrics(f->mono,&row->metrics);
        if (!b3_test_need(fe_b1b1_get_info(f->core,&info)==FE_B1B1_OK,
                           "CAPTURE_INFO_FAILED")) return 0;
        row->beam_hash=fe_b3_f0_hash_f32(row->receipt.beam,160u);
        row->output_hash=fe_b3_f0_hash_s16(output_pcm+at,160u);
        row->capture_hash=fe_b3_f0_hash_s16(cap,640u);
        row->render_hash=expected_missing?0u:fe_b3_f0_hash_s16(ref,160u);
        row->state_hash=b3_test_state_fingerprint(f);
        row->capture_accepted=info.accepted_frames;
        row->capture_epoch=info.source.capture_epoch;
        row->clock_epoch=info.source.clock_epoch;
        row->render_src_epoch=f->front.render_epoch;
        completed=seq;
        present_count+=(uint64_t)!expected_missing;
        absent_count+=(uint64_t)expected_missing;
        notify_count+=row->receipt.explicit_notify;
        beam_clips+=row->receipt.beam_clips;reference_clips+=row->receipt.reference_clips;
        if (!b3_test_need(row->receipt.source.capture_sequence==seq &&
            row->receipt.source.source_generation==FE_B3_F0_GENERATION &&
            row->receipt.source.capture_source_id==104u &&
            row->receipt.source.render_source_id==204u &&
            row->receipt.source.capture_pcm_hash==row->capture_hash &&
            row->receipt.source.render_pcm_hash==row->render_hash &&
            row->receipt.source.render_event==(uint32_t)(expected_missing?
                FE_B1S0_RENDER_ABSENT:FE_B1S0_RENDER_PRESENT) &&
            row->receipt.source.render_epoch==((case_pap && seq>=241u)?2u:1u) &&
            row->receipt.source.render_reason==(uint32_t)(expected_missing?
                FE_B1S0_ABSENT_SOURCE_REPORTED:0u) &&
            row->receipt.source.reference_actual_pcm==(uint32_t)!expected_missing &&
            row->receipt.source.mic_bf_progressed==1u &&
            !row->receipt.source.source_clock_known && !row->receipt.source.recorder_qualified &&
            !row->receipt.source.public_sdk_qualified && !row->receipt.source.device_qualified &&
            row->receipt.explicit_notify==(uint32_t)expected_notify &&
            (!expected_notify || row->receipt.notify_capture_preserved) &&
            (!expected_missing || row->receipt.absent_reference_untouched) &&
            row->metrics.processed_frames==seq && row->capture_accepted==seq &&
            info.source.accepted_frames==seq && info.array.samples_processed==(uint64_t)seq*160u &&
            row->capture_epoch==0u && row->clock_epoch==0u &&
            row->render_src_epoch==((case_pap && seq>=241u)?2u:1u) &&
            b3_test_metrics_finite(&row->metrics),"LITERAL_CONTROL_OR_SOURCE_CONTRACT_MISMATCH"))
            return 0;
        if (fe_b3_observer_enabled()) {
            const fe_b3_observation *o=fe_b3_observer_frame(seq);
            if (!b3_test_need(o && !o->violations &&
                o->calls[FE_B3_OBS_PUSH]==(uint32_t)!expected_missing &&
                o->calls[FE_B3_OBS_NOTIFY]==(uint32_t)expected_notify &&
                o->far==row->metrics.far_end_active &&
                o->dt==row->metrics.double_talk_active &&
                o->frequency_res_active==row->metrics.frequency_res_active &&
                o->vad_active==row->metrics.vad_active,"ACTUAL_STAGE_OBSERVATION_FAILED"))
                return 0;
        }
        if (do_negatives && seq==1u) {
            phase="postframe_negative_control";
            if (!b3_test_postframe1_negative()) return 0;
        }
    }
    return b3_test_need(!do_negatives ||
        (negative_mask==UINT32_C(65535) && setup_publications==5u),"NEGATIVE_SUITE_INCOMPLETE");
}

static uint32_t b3_test_float_bits(float v) { uint32_t u;memcpy(&u,&v,sizeof(u));return u; }
static void b3_test_metrics_json(FILE *f,const ap_metrics_t *m) {
    fprintf(f,"{\"float_bits\":[%" PRIu32 ",%" PRIu32 ",%" PRIu32 ",%" PRIu32
        ",%" PRIu32 ",%" PRIu32 ",%" PRIu32 "],"
        "\"delay_error_samples\":%" PRId32 ",\"estimated_delay_ms\":%" PRIu32
        ",\"active_aec_taps\":%" PRIu32 ",\"active_aec_adapt_stride\":%" PRIu32
        ",\"active_aec_partitions\":%" PRIu32 ",\"aec_block_samples\":%" PRIu32
        ",\"aec_convergence_frames\":%" PRIu32 ",\"processed_frames\":%" PRIu64
        ",\"render_underruns\":%" PRIu64 ",\"aec_resets\":%" PRIu64
        ",\"delay_jumps\":%" PRIu64 ",\"reference_sample_slips\":%" PRIu64
        ",\"timestamp_observations\":%" PRIu64
        ",\"vad_active\":%u,\"far_end_active\":%u,\"double_talk_active\":%u,"
        "\"frequency_res_active\":%u,\"erle_valid\":%u,\"aec_converged\":%u,"
        "\"quality\":%u,\"aec_backend\":%u}",
        b3_test_float_bits(m->input_rms_dbfs),b3_test_float_bits(m->output_rms_dbfs),
        b3_test_float_bits(m->noise_rms_dbfs),b3_test_float_bits(m->erle_db),
        b3_test_float_bits(m->residual_echo_gain),b3_test_float_bits(m->vad_probability),
        b3_test_float_bits(m->estimated_drift_ppm),m->delay_error_samples,m->estimated_delay_ms,
        m->active_aec_taps,m->active_aec_adapt_stride,m->active_aec_partitions,
        m->aec_block_samples,m->aec_convergence_frames,m->processed_frames,
        m->render_underruns,m->aec_resets,m->delay_jumps,m->reference_sample_slips,
        m->timestamp_observations,(unsigned)m->vad_active,(unsigned)m->far_end_active,
        (unsigned)m->double_talk_active,(unsigned)m->frequency_res_active,
        (unsigned)m->erle_valid,(unsigned)m->aec_converged,(unsigned)m->quality,
        (unsigned)m->aec_backend);
}
static void b3_test_observer_json(FILE *f,const fe_b3_observation *o) {
    if (!o) { fputs("null",f); return; }
    fputs("{\"calls\":[",f);
    for (unsigned j=0;j<FE_B3_OBS_CALLS;++j) fprintf(f,"%s%u",j?",":"",o->calls[j]);
    fputs("],\"order\":[",f);
    for (unsigned j=0;j<o->order_count;++j) fprintf(f,"%s%u",j?",":"",o->order[j]);
    fprintf(f,"],\"violations\":%u,\"far\":%u,\"dt\":%u,\"aec_far\":%u,\"aec_dt\":%u,"
      "\"ns_far\":%u,\"ns_dt\":%u,\"ns_enable\":%u,\"ns_echo_present\":%u,\"ns_mode\":%u,"
      "\"frequency_res_active\":%u,\"agc_allow\":%u,\"vad_active\":%u,"
      "\"sync_delay_samples\":%u,\"route_jump\":%u,\"notify_flags\":%u,"
      "\"notify_lost_frames\":%u,\"notify_status\":%" PRId32
      ",\"explicit_aec_resets\":%u,\"automatic_aec_resets\":%u,"
      "\"notify_capture_preserved\":%u,\"notify_processed_preserved\":%u,"
      "\"notify_reset_state_mask\":%u,\"agc_gain_before_bits\":%u,\"agc_gain_after_bits\":%u,"
      "\"vad_probability_bits\":%u,\"residual_gain_bits\":%u}",
      o->violations,o->far,o->dt,o->aec_far,o->aec_dt,o->ns_far,o->ns_dt,o->ns_enable,
      o->ns_echo_present,o->ns_mode,o->frequency_res_active,o->agc_allow,o->vad_active,
      o->sync_delay_samples,o->route_jump,o->notify_flags,o->notify_lost_frames,
      o->notify_status,o->explicit_aec_resets,o->automatic_aec_resets,
      o->notify_capture_preserved,o->notify_processed_preserved,o->notify_reset_state_mask,
      o->agc_gain_before_bits,o->agc_gain_after_bits,o->vad_probability_bits,o->residual_gain_bits);
}
static FILE *b3_test_file(const char *dir,const char *name) {
    char path[4096];
    int n=snprintf(path,sizeof(path),"%s/%s",dir,name);
    if (n<0 || (size_t)n>=sizeof(path)) return NULL;
    return fopen(path,"wbx");
}
static int b3_test_write_s16(const char *dir,const char *name,const int16_t *p,size_t n) {
    FILE *f=b3_test_file(dir,name);
    int ok=1;
    if (!f) return 0;
    for (size_t i=0;i<n;++i) {
        uint16_t v=(uint16_t)p[i];
        if (fputc((int)(v&255u),f)==EOF || fputc((int)(v>>8u),f)==EOF) { ok=0;break; }
    }
    if (fclose(f)!=0) ok=0;
    return ok;
}
static int b3_test_write_f32(const char *dir,const char *name,const float *p,size_t n) {
    FILE *f=b3_test_file(dir,name);
    int ok=1;
    if (!f) return 0;
    for (size_t i=0;i<n && ok;++i) {
        uint32_t v=b3_test_float_bits(p[i]);
        for (unsigned k=0;k<4u;++k)
            if (fputc((int)((v>>(8u*k))&255u),f)==EOF) { ok=0;break; }
    }
    if (fclose(f)!=0) ok=0;
    return ok;
}
static int b3_test_write_fixture(const char *dir) {
    FILE *f;
    int ok=b3_test_write_s16(dir,"capture.s16le",capture_pcm,B3_SAMPLES*4u) &&
           b3_test_write_s16(dir,"render.s16le",render_pcm,B3_SAMPLES);
    if (!ok) return 0;
    f=b3_test_file(dir,"render-pap.s16le");
    if (!f) return 0;
    for (uint32_t seq=1;seq<=600u && ok;++seq) {
        if (seq>=201u && seq<=240u) continue;
        for (uint32_t i=0;i<160u;++i) {
            uint16_t v=(uint16_t)render_pcm[(size_t)(seq-1u)*160u+i];
            if (fputc((int)(v&255u),f)==EOF || fputc((int)(v>>8u),f)==EOF) { ok=0;break; }
        }
    }
    if (fclose(f)!=0) ok=0;
    return ok;
}
static int b3_test_write_frames(const char *dir) {
    FILE *f=b3_test_file(dir,"frames.jsonl");
    int ok;
    if (!f) return 0;
    for (uint32_t j=0;j<completed;++j) {
        const b3_test_frame *r=&log_rows[j];
        const fe_b1s0_receipt *s=&r->receipt.source;
        fprintf(f,"{\"seq\":%u,\"event\":%u,\"epoch\":%u,\"reason\":%u,"
          "\"source_generation\":%" PRIu64 ",\"capture_source_id\":%u,\"render_source_id\":%u,"
          "\"capture_fnv64\":\"%016" PRIx64 "\",\"render_fnv64\":\"%016" PRIx64 "\","
          "\"beam_fnv64\":\"%016" PRIx64 "\",\"output_fnv64\":\"%016" PRIx64 "\","
          "\"capture_arena_fnv64\":\"%016" PRIx64 "\","
          "\"capture_accepted\":%" PRIu64 ",\"capture_epoch\":%" PRIu64
          ",\"clock_epoch\":%" PRIu64 ",\"render_src_epoch\":%u,"
          "\"reference_actual_pcm\":%u,\"explicit_notify\":%u,"
          "\"absent_reference_untouched\":%u,\"notify_capture_preserved\":%u,"
          "\"beam_clips\":%" PRIu64 ",\"reference_clips\":%" PRIu64 ",\"metrics\":",
          j+1u,s->render_event,s->render_epoch,s->render_reason,s->source_generation,
          s->capture_source_id,s->render_source_id,r->capture_hash,r->render_hash,
          r->beam_hash,r->output_hash,r->state_hash,r->capture_accepted,r->capture_epoch,
          r->clock_epoch,r->render_src_epoch,s->reference_actual_pcm,
          r->receipt.explicit_notify,r->receipt.absent_reference_untouched,
          r->receipt.notify_capture_preserved,r->receipt.beam_clips,r->receipt.reference_clips);
        b3_test_metrics_json(f,&r->metrics);
        fputs(",\"observer\":",f);
        b3_test_observer_json(f,fe_b3_observer_frame(j+1u));
        fputs("}\n",f);
    }
    ok=!ferror(f);
    if (fclose(f)!=0) ok=0;
    return ok;
}
static int b3_test_write_result(const char *dir) {
    uint32_t freq_on=0u,dt=0u,agc_allow=0u,observed_violations=0u;
    uint64_t calls[FE_B3_OBS_CALLS]={0};
    unsigned reached;
    FILE *f;
    int ok;
    ap_config_t config;
    fe_b1b1_info info;
    memset(&config,0,sizeof(config));memset(&info,0,sizeof(info));
    if (main_fixture.mono) (void)ap_pipeline_get_config(main_fixture.mono,&config);
    if (main_fixture.core) (void)fe_b1b1_get_info(main_fixture.core,&info);
    for (uint32_t j=0;j<completed;++j) {
        const ap_metrics_t *m=&log_rows[j].metrics;
        const fe_b3_observation *o=fe_b3_observer_frame(j+1u);
        freq_on+=(uint32_t)(m->frequency_res_active!=0u);
        dt+=(uint32_t)(m->double_talk_active!=0u);
        agc_allow+=(uint32_t)!(m->far_end_active && !m->double_talk_active);
        if (o) {
            observed_violations+=o->violations;
            for (unsigned k=0;k<FE_B3_OBS_CALLS;++k) calls[k]+=o->calls[k];
        }
    }
    reached=(unsigned)(completed==600u && freq_on>0u && freq_on<completed &&
                        dt>0u && agc_allow>0u && agc_allow<completed);
    f=b3_test_file(dir,"result.json");
    if (!f) return 0;
    fprintf(f,"{\"schema_version\":1,\"id\":\"%s\",\"status\":\"%s\",\"failure\":",
        B3_ID,failure?"FAILED":(reached?"OK":"INCONCLUSIVE"));
    if (failure) fprintf(f,"\"%s\"",failure); else fputs("null",f);
    fprintf(f,",\"attempted_frame\":%u,\"failed_frame\":%u,\"failed_negative\":%u,"
              "\"failure_phase\":",attempted_frame,failure?attempted_frame:0u,
              failure?active_negative:0u);
    if (failure) fprintf(f,"\"%s\"",phase); else fputs("null",f);
    fputs(",\"failure_state\":",f);
    if (failure) {
        const b3_test_fixture *x=failure_fixture;
        ap_metrics_t actual;
        int owner_initialized=x->q.core!=NULL;
        memset(&actual,0,sizeof(actual));
        if (x->mono) ap_pipeline_get_metrics(x->mono,&actual);
        fprintf(f,"{\"fixture\":\"%s\",\"owner_initialized\":%s,\"mono_initialized\":%s,"
          "\"cap_head\":%u,\"cap_tail\":%u,\"ref_head\":%u,\"ref_tail\":%u,"
          "\"owner_processed\":%" PRIu64 ",\"front_accepted_capture\":%" PRIu64
          ",\"front_accepted_render\":%" PRIu64 ",\"mono_processed\":%" PRIu64
          ",\"bridge_accepted\":%" PRIu64 ",\"bridge_failed\":%u}",
          x==&main_fixture?"main":"isolated_negative",owner_initialized?"true":"false",
          x->mono?"true":"false",
          owner_initialized?atomic_load_explicit(&x->q.cap_head,memory_order_relaxed):0u,
          owner_initialized?atomic_load_explicit(&x->q.cap_tail,memory_order_relaxed):0u,
          owner_initialized?atomic_load_explicit(&x->q.ref_head,memory_order_relaxed):0u,
          owner_initialized?atomic_load_explicit(&x->q.ref_tail,memory_order_relaxed):0u,
          x->q.processed,x->front.accepted_capture,x->front.accepted_render,
          actual.processed_frames,x->seam.accepted,x->seam.failed);
    } else fputs("null",f);
    fputs(",\"failed_observation\":",f);
    b3_test_observer_json(f,failure && attempted_frame?
                         fe_b3_observer_frame(attempted_frame):NULL);
    fprintf(f,",\"case\":\"%s\",\"mode\":\"%s\",\"observed\":%s,\"future\":%s,"
      "\"negatives_requested\":%s,\"frames\":%u,"
      "\"source_role\":\"D0_FIRST_PARTY_DISCLOSED_SYNTHETIC_ENGINEERING\","
      "\"capture_source_fnv64\":\"%016" PRIx64 "\",\"render_source_fnv64\":\"%016" PRIx64 "\","
      "\"counters\":{\"accepted\":%u,\"present\":%" PRIu64 ",\"absent\":%" PRIu64
      ",\"notify\":%" PRIu64 ",\"negative_mask\":%u,\"negative_count\":%u,"
      "\"setup_source_publications\":%u,\"beam_clips\":%" PRIu64
      ",\"reference_clips\":%" PRIu64 "},",
      case_pap?"PAP":"ALL_P",mode_direct?"direct":"adapter",
      fe_b3_observer_enabled()?"true":"false",future_change?"true":"false",
      do_negatives?"true":"false",completed,
      fe_b3_f0_hash_s16(capture_pcm,B3_SAMPLES*4u),fe_b3_f0_hash_s16(render_pcm,B3_SAMPLES),
      completed,present_count,absent_count,notify_count,negative_mask,
      (unsigned)__builtin_popcount(negative_mask),setup_publications,beam_clips,reference_clips);
    fprintf(f,"\"config\":{\"io_rate_hz\":%u,\"internal_rate_hz\":%u,\"physical_mics\":4,"
      "\"mono_mics\":%u,\"stage_mask\":%u,\"compiled_stage_mask\":%u,"
      "\"aec_filter_ms\":%u,\"aec_mu_bits\":%u,\"aec_adapt_stride\":%u,"
      "\"max_delay_ms\":%u,\"initial_delay_ms\":%u,\"ns_floor_bits\":%u,"
      "\"agc_target_dbfs_bits\":%u,\"limiter_dbfs_bits\":%u,\"resource_class\":%u,"
      "\"enable_delay_tracking\":%u,\"enable_clock_drift_compensation\":%u,"
      "\"quality\":2,\"aec_backend\":\"MDF\",\"simd\":\"SCALAR\",\"ns_estimator\":\"EMA\"},",
      config.io_sample_rate_hz,config.internal_sample_rate_hz,config.mic_channels,
      config.stages,ap_pipeline_compiled_stages(),config.aec_filter_ms,
      b3_test_float_bits(config.aec_mu),config.aec_adapt_stride,config.max_delay_ms,
      config.initial_delay_ms,b3_test_float_bits(config.ns_floor),
      b3_test_float_bits(config.agc_target_dbfs),b3_test_float_bits(config.limiter_dbfs),
      (unsigned)config.resource_class,(unsigned)config.enable_delay_tracking,
      (unsigned)config.enable_clock_drift_compensation);
    fprintf(f,"\"latency\":{\"input_src_samples\":%u,\"bf_samples\":%u,"
      "\"mono_ms\":%u,\"declared_sum_samples\":182},"
      "\"resource\":{\"capture_state_bytes\":%zu,\"capture_work_bytes\":%zu,"
      "\"mono_state_bytes\":%zu,\"owner_queue_bytes\":%zu,\"bridge_bytes\":%zu,"
      "\"receipt_bytes\":%zu,\"fixture_bytes\":%zu,\"negative_fixture_bytes\":%zu,"
      "\"bind_reference_scratch_bytes\":%u,"
      "\"snapshot_bytes\":%zu,\"fresh_mono_bytes\":%zu,\"canonical_scratch_bytes\":%zu,"
      "\"input_fixture_bytes\":%zu,\"output_buffers_bytes\":%zu,"
      "\"frame_log_bytes\":%zu,\"observer_record_bytes\":%zu,\"observer_storage_bytes\":%zu},",
      info.source.existing_first_party_filter_delay_samples,info.array.common_delay_samples,
      main_fixture.mono?ap_pipeline_algorithmic_latency_ms(main_fixture.mono):0u,
      main_fixture.state_bytes,main_fixture.work_bytes,main_fixture.mono_bytes,
      sizeof(fe_b1s0_state),sizeof(fe_b3_f0),sizeof(fe_b3_f0_receipt),
      sizeof(main_fixture),sizeof(negative_fixture),FE_B3_F0_BIND_REFERENCE_BYTES,
      sizeof(snapshot)+sizeof(saved_output)+sizeof(saved_receipt),
      sizeof(fresh_mono_memory),sizeof(canonical_state),sizeof(capture_pcm)+sizeof(render_pcm),
      sizeof(output_pcm)+sizeof(beam_pcm),sizeof(log_rows),
      sizeof(fe_b3_observation),fe_b3_observer_storage_bytes());
    fprintf(f,"\"coverage\":{\"frequency_on_frames\":%u,\"frequency_off_frames\":%u,"
      "\"double_talk_frames\":%u,\"agc_allow_frames\":%u,\"agc_disallow_frames\":%u,"
      "\"required_reached\":%s},\"observed_violations\":%u,\"observed_calls\":[",
      freq_on,completed-freq_on,dt,agc_allow,completed-agc_allow,reached?"true":"false",observed_violations);
    for (unsigned k=0;k<FE_B3_OBS_CALLS;++k) fprintf(f,"%s%" PRIu64,k?",":"",calls[k]);
    fputs("],\"promotion\":{\"public_sdk\":false,\"acoustic_superiority\":false,"
      "\"physical_clock\":false,\"ssc305\":false,\"full_resource_budget\":false,"
      "\"shipping\":false}}\n",f);
    ok=!ferror(f);
    if (fclose(f)!=0) ok=0;
    return ok;
}
int main(int argc,char **argv) {
    const char *dir=NULL;
    int fixture_only=0;
    struct stat st;
    if (argc==3 && strcmp(argv[1],"--fixture-only")==0) {
        fixture_only=1;dir=argv[2];
    } else {
        int have_case=0,have_mode=0,have_future=0,have_neg=0;
        for (int i=1;i<argc;i+=2) {
            if (i+1>=argc) { fputs("B3_BAD_CLI\n",stderr);return 2; }
            if (strcmp(argv[i],"--case")==0 && !have_case) {
                have_case=1;
                if (strcmp(argv[i+1],"PAP")==0) case_pap=1;
                else if (strcmp(argv[i+1],"ALL_P")!=0) return 2;
            } else if (strcmp(argv[i],"--mode")==0 && !have_mode) {
                have_mode=1;
                if (strcmp(argv[i+1],"direct")==0) mode_direct=1;
                else if (strcmp(argv[i+1],"adapter")!=0) return 2;
            } else if (strcmp(argv[i],"--future")==0 && !have_future) {
                have_future=1;
                if (strcmp(argv[i+1],"1")==0) future_change=1;
                else if (strcmp(argv[i+1],"0")!=0) return 2;
            } else if (strcmp(argv[i],"--negatives")==0 && !have_neg) {
                have_neg=1;
                if (strcmp(argv[i+1],"1")==0) do_negatives=1;
                else if (strcmp(argv[i+1],"0")!=0) return 2;
            } else if (strcmp(argv[i],"--output")==0 && !dir) dir=argv[i+1];
            else { fputs("B3_BAD_CLI\n",stderr);return 2; }
        }
        if (!have_case || !have_mode || !have_future || !have_neg || !dir ||
            (mode_direct && (fe_b3_observer_enabled() || do_negatives || future_change)) ||
            (future_change && (!fe_b3_observer_enabled() || !case_pap || do_negatives)) ||
            (do_negatives && (fe_b3_observer_enabled() || !case_pap)))
            { fputs("B3_UNREGISTERED_INVOCATION\n",stderr);return 2; }
    }
    if (lstat(dir,&st)!=0) {
        if (errno!=ENOENT || mkdir(dir,0700)!=0 || lstat(dir,&st)!=0) return 2;
    }
    if (!S_ISDIR(st.st_mode) || S_ISLNK(st.st_mode)) return 2;
    b3_test_generate();
    if (fixture_only) {
        if (!b3_test_write_fixture(dir)) return 2;
        fputs("B3_F0_FIXTURE_ONLY_NO_DSP\n",stdout);
        return 0;
    }
    if (fesetround(FE_TONEAREST)!=0 || fegetround()!=FE_TONEAREST)
        failure="FE_TONEAREST_UNAVAILABLE";
    if (!failure) (void)b3_test_run();
    /* Every file write occurs after all processing has stopped. Preserve even
     * failed prefixes; Python hashes raw PCM before omitting successful PCM. */
    if (!b3_test_write_s16(dir,"output.s16le",output_pcm,(size_t)completed*160u) ||
        !b3_test_write_f32(dir,"beam.f32le",beam_pcm,(size_t)completed*160u) ||
        !b3_test_write_frames(dir) || !b3_test_write_result(dir)) {
        fputs("B3_EVIDENCE_WRITE_FAILED\n",stderr);return 2;
    }
    if (failure) { fprintf(stderr,"B3_F0_FAILED:%s\n",failure);return 2; }
    {
        unsigned freq=0u,dt=0u,allow=0u;
        for (unsigned j=0;j<completed;++j) {
            const ap_metrics_t *m=&log_rows[j].metrics;
            freq+=(unsigned)(m->frequency_res_active!=0u);
            dt+=(unsigned)(m->double_talk_active!=0u);
            allow+=(unsigned)!(m->far_end_active && !m->double_talk_active);
        }
        if (!freq || freq==completed || !dt || !allow || allow==completed) {
            fputs("B3_F0_FIXED_COVERAGE_INCONCLUSIVE\n",stdout);return 3;
        }
    }
    fputs("B3_F0_FINITE_CASE_COMPLETE_NO_PROMOTION\n",stdout);
    return 0;
}
