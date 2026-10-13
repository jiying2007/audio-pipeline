/* FE09-R2B1B-S0 first-party reference SRC test. Source-only synthetic.
 * Include the PRIVATE adapter TU exactly once to exercise overflow counters
 * without adding exported debugging functions or weakening the product ABI.
 * The actual first-party src/frontend/ap_resampler.c is linked separately.
 */
#include "fe09_b1b0_src.c"
#include <inttypes.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define ARENA 4096u
#define FRAMES 100u
#define FNV_O UINT64_C(14695981039346656037)
#define FNV_P UINT64_C(1099511628211)

typedef struct {
    const char *name;
    uint32_t n, ref, slots[4];
} scene_t;

static const scene_t SCENES[4] = {
    {"C1_BASELINE", 1u, 0u, {0u, 0u, 0u, 0u}},
    {"C2_ULA", 2u, 1u, {1u, 0u, 0u, 0u}},
    {"C4_ULA", 4u, 1u, {2u, 0u, 3u, 1u}},
    {"C4_UCA", 4u, 1u, {3u, 2u, 1u, 0u}},
};
static const uint32_t RATES[3] = {16000u, 32000u, 48000u};

typedef struct {
    uint64_t source_hash, mic_float_hash, ref_float_hash;
    fe_b1b0_info info;
    uint32_t negatives;
} proof_t;

static uint64_t h16(uint64_t h, int16_t s) {
    const uint16_t w = (uint16_t)s;
    h = (h ^ (uint8_t)(w & UINT16_C(255))) * FNV_P;
    return (h ^ (uint8_t)(w >> 8u)) * FNV_P;
}

static uint64_t hfloat(uint64_t h, float x) {
    uint32_t w, k;
    memcpy(&w, &x, sizeof(w));
    for (k = 0u; k < 4u; ++k)
        h = (h ^ (uint8_t)(w >> (8u * k))) * FNV_P;
    return h;
}

static fe_b1b0_config make_cfg(const scene_t *sc, uint32_t rate) {
    fe_b1b0_config c;
    uint32_t k;
    memset(&c, 0, sizeof(c));
    c.struct_size = (uint32_t)sizeof(c);
    c.api_version = FE_B1B0_VERSION;
    c.capture_and_render_rate_hz = rate;
    c.frame_ms = FE_B1B0_FRAME_MS;
    c.physical_mics = sc->n;
    c.render_channels = sc->ref;
    c.active_mic_mask = (1u << sc->n) - 1u;
    for (k = 0u; k < sc->n; ++k) c.physical_to_capture_slot[k] = sc->slots[k];
    return c;
}

static int16_t mic_source(uint32_t phys, uint32_t sample, uint32_t frame) {
    const uint32_t raw =
        (frame * 337u + sample * 73u + phys * 1931u) % UINT32_C(65536);
    if (frame == 0u && phys == 0u && sample == 0u) return INT16_MIN;
    if (frame == 0u && phys == 0u && sample == 1u) return INT16_MAX;
    return (int16_t)((int32_t)raw - 32768);
}

static int16_t render_source(uint32_t sample, uint32_t frame) {
    const uint32_t raw = (frame * 233u + sample * 229u) % UINT32_C(65536);
    return (int16_t)((int32_t)raw - 32768);
}

static int init_negative(const fe_b1b0_config *cfg,
                         size_t bytes, size_t shift, fe_b1b0_status expected) {
    _Alignas(16) unsigned char buf[ARENA + 16u], before[ARENA + 16u];
    fe_b1b0_src *out = (fe_b1b0_src *)(uintptr_t)1u;
    fe_b1b0_status got;
    memset(buf, 0x45, sizeof(buf));
    memcpy(before, buf, sizeof(buf));
    got = fe_b1b0_init(buf + shift, bytes, cfg, &out);
    return got == expected && out == NULL &&
           memcmp(buf, before, sizeof(buf)) == 0;
}

static int init_null(const fe_b1b0_config *cfg) {
    fe_b1b0_src *out = (fe_b1b0_src *)(uintptr_t)1u;
    return fe_b1b0_init(NULL, 0u, cfg, &out) == FE_B1B0_EINVAL &&
           out == NULL;
}

static int init_alias(const fe_b1b0_config *cfg) {
    _Alignas(16) unsigned char buf[ARENA], before[ARENA];
    fe_b1b0_src *out = (fe_b1b0_src *)(uintptr_t)1u;
    fe_b1b0_status got;
    memset(buf, 0xa3, sizeof(buf));
    memcpy(before, buf, sizeof(before));
    got = fe_b1b0_init(buf, sizeof(buf), cfg, (fe_b1b0_src **)(void *)buf);
    if (got != FE_B1B0_EINVAL || memcmp(buf,before,sizeof(buf))) return 0;
    memcpy(buf, cfg, sizeof(*cfg));
    memcpy(before, buf, sizeof(before));
    got = fe_b1b0_init(buf, sizeof(buf),
                       (const fe_b1b0_config *)(const void *)buf, &out);
    return got == FE_B1B0_EINVAL && out == NULL &&
           memcmp(buf,before,sizeof(buf)) == 0;
}

static int negatives(const scene_t *sc, uint32_t rate, fe_b1b0_src *s,
                     unsigned char *arena, size_t need, uint32_t *nneg) {
    fe_b1b0_config cfg = make_cfg(sc, rate), bad;
    int16_t input[FE_B1B0_MAX_MICS * 480u] = {0};
    int16_t render[480u] = {0};
    float out[FE_B1B0_MAX_MICS * FE_B1B0_INTERNAL_FRAMES];
    float refout[FE_B1B0_INTERNAL_FRAMES];
    unsigned char snapshot[ARENA];
    float out_before[sizeof(out)/sizeof(out[0])];
    float ref_before[sizeof(refout)/sizeof(refout[0])];
    const size_t in_count = (size_t)(rate / 100u) * sc->n;
    const size_t ref_count = (size_t)(rate / 100u) * sc->ref;
    const size_t out_count = (size_t)sc->n * FE_B1B0_INTERNAL_FRAMES;
    const size_t refout_count = (size_t)sc->ref * FE_B1B0_INTERNAL_FRAMES;
    const int16_t *render_p = sc->ref ? render : NULL;
    float *rout_p = sc->ref ? refout : NULL;
    uint32_t count = 0u;
    size_t k;
    uint64_t save;
    if (need > ARENA) return 0;
    for (k = 0u; k < sizeof(out)/sizeof(out[0]); ++k) out[k] = -777.0f;
    for (k = 0u; k < sizeof(refout)/sizeof(refout[0]); ++k)
        refout[k] = -777.0f;
#define BAD_CFG() do { \
    if (!init_negative(&bad, ARENA, 0u, FE_B1B0_EINVAL) || \
        fe_b1b0_state_bytes(&bad) != 0u) return 0; \
    ++count; \
} while (0)
    bad = cfg; bad.struct_size -= 1u; BAD_CFG();
    bad = cfg; bad.api_version = 1u; BAD_CFG();
    bad = cfg; bad.capture_and_render_rate_hz = 8000u; BAD_CFG();
    bad = cfg; bad.capture_and_render_rate_hz = 24000u; BAD_CFG();
    bad = cfg; bad.capture_and_render_rate_hz = 44100u; BAD_CFG();
    bad = cfg; bad.frame_ms = 20u; BAD_CFG();
    bad = cfg; bad.physical_mics = 3u; BAD_CFG();
    bad = cfg; bad.render_channels = 2u; BAD_CFG();
    bad = cfg; bad.active_mic_mask = 0u; BAD_CFG();
    bad = cfg; bad.active_mic_mask = UINT32_MAX; BAD_CFG();
    bad = cfg; bad.capture_clock_authority = 1u; BAD_CFG();
    bad = cfg; bad.physical_to_capture_slot[0] = sc->n; BAD_CFG();
    bad = cfg;
    if (sc->n > 1u)
        bad.physical_to_capture_slot[1] = cfg.physical_to_capture_slot[0];
    else
        bad.physical_to_capture_slot[0] = 1u;
    BAD_CFG();
    bad = cfg; bad.reserved[0] = 1u; BAD_CFG();
    bad = cfg;
    if (sc->n < 4u) bad.physical_to_capture_slot[sc->n] = 1u;
    else bad.reserved[1] = 1u;
    BAD_CFG();
#undef BAD_CFG
    if (!init_negative(&cfg, need-1u, 0u, FE_B1B0_ENOMEM) ||
        !init_negative(&cfg, ARENA-1u, 1u, FE_B1B0_EINVAL) ||
        !init_null(&cfg) || !init_alias(&cfg)) return 0;
    count += 5u; /* undersize, alignment, null arena, out alias, cfg alias */

#define REJECT(operation, expected) do { \
    fe_b1b0_status got; \
    memcpy(snapshot, arena, need); \
    memcpy(out_before, out, sizeof(out)); \
    memcpy(ref_before, refout, sizeof(refout)); \
    got = (operation); \
    if (got != (expected) || memcmp(snapshot,arena,need) || \
        memcmp(out_before,out,sizeof(out)) || \
        memcmp(ref_before,refout,sizeof(refout))) return 0; \
    ++count; \
} while (0)
#define P(a,b,c,d,e,f,g,h) fe_b1b0_process(s,(a),(b),(c),(d),(e),(f),(g),(h))
    REJECT(P(NULL,in_count,render_p,ref_count,out,out_count,rout_p,refout_count), FE_B1B0_EINVAL);
    REJECT(P(input,in_count,render_p,ref_count,NULL,out_count,rout_p,refout_count), FE_B1B0_EINVAL);
    REJECT(P(input,in_count-1u,render_p,ref_count,out,out_count,rout_p,refout_count), FE_B1B0_EINVAL);
    REJECT(P(input,in_count+1u,render_p,ref_count,out,out_count,rout_p,refout_count), FE_B1B0_EINVAL);
    REJECT(P(input,in_count,render_p,ref_count,out,out_count-1u,rout_p,refout_count), FE_B1B0_EINVAL);
    REJECT(P(input,in_count,render_p,ref_count,out,out_count+1u,rout_p,refout_count), FE_B1B0_EINVAL);
    REJECT(P(input,in_count,render_p,ref_count,(float *)(void *)input,out_count,rout_p,refout_count), FE_B1B0_EINVAL);
    REJECT(P((const int16_t *)(const void *)arena,in_count,render_p,ref_count,out,out_count,rout_p,refout_count), FE_B1B0_EINVAL);
    REJECT(P(input,in_count,render_p,ref_count,(float *)(void *)arena,out_count,rout_p,refout_count), FE_B1B0_EINVAL);
    if (sc->ref) {
        REJECT(P(input,in_count,NULL,ref_count,out,out_count,rout_p,refout_count),FE_B1B0_EINVAL);
        REJECT(P(input,in_count,render_p,ref_count,out,out_count,NULL,refout_count),FE_B1B0_EINVAL);
        REJECT(P(input,in_count,render_p,ref_count-1u,out,out_count,rout_p,refout_count),FE_B1B0_EINVAL);
        REJECT(P(input,in_count,render_p,ref_count,out,out_count,rout_p,refout_count-1u),FE_B1B0_EINVAL);
        REJECT(P(input,in_count,input,ref_count,out,out_count,rout_p,refout_count),FE_B1B0_EINVAL);
        REJECT(P(input,in_count,render_p,ref_count,out,out_count,out,refout_count),FE_B1B0_EINVAL);
        REJECT(P(input,in_count,render_p,ref_count,out,out_count,(float *)(void *)render,refout_count),FE_B1B0_EINVAL);
    } else {
        REJECT(P(input,in_count,render,0u,out,out_count,NULL,0u),FE_B1B0_EINVAL);
        REJECT(P(input,in_count,NULL,0u,out,out_count,refout,0u),FE_B1B0_EINVAL);
        REJECT(P(input,in_count,NULL,1u,out,out_count,NULL,0u),FE_B1B0_EINVAL);
        REJECT(P(input,in_count,NULL,0u,out,out_count,NULL,1u),FE_B1B0_EINVAL);
    }
    REJECT(fe_b1b0_set_active_mask(s,0u),FE_B1B0_EINVAL);
    REJECT(fe_b1b0_set_active_mask(s,UINT32_MAX),FE_B1B0_EINVAL);
    REJECT(fe_b1b0_notify_gap(s,0u),FE_B1B0_EINVAL);
    REJECT(fe_b1b0_notify_gap(s,UINT32_MAX),FE_B1B0_EINVAL);
    if (!sc->ref)
        REJECT(fe_b1b0_notify_gap(s,FE_B1B0_RENDER_GAP),FE_B1B0_EINVAL);
    REJECT(fe_b1b0_get_info(s,(fe_b1b0_info *)(void *)arena),FE_B1B0_EINVAL);
#undef P
#undef REJECT

    /* Explicitly force each overflow counter to UINT64_MAX in private test
     * storage, verify atomic rejection, then restore original bytes.
     * This is not an exported production debugging hook or test bypass.
     */
#define OVERFLOW_PROCESS(field) do { \
    save = s->field; s->field = UINT64_MAX; \
    memcpy(snapshot,arena,need); \
    if (fe_b1b0_process(s,input,in_count,render_p,ref_count,out,out_count,rout_p,refout_count) != FE_B1B0_EINVAL || \
        memcmp(snapshot,arena,need)) return 0; \
    s->field = save; ++count; \
} while (0)
    OVERFLOW_PROCESS(accepted);
    OVERFLOW_PROCESS(cap_frames_epoch);
    if (sc->ref) OVERFLOW_PROCESS(ref_frames_epoch);
#undef OVERFLOW_PROCESS
#define OVERFLOW_GAP(field, flag) do { \
    save = s->field; s->field = UINT64_MAX; \
    memcpy(snapshot,arena,need); \
    if (fe_b1b0_notify_gap(s,(flag)) != FE_B1B0_EINVAL || \
        memcmp(snapshot,arena,need)) return 0; \
    s->field = save; ++count; \
} while (0)
    OVERFLOW_GAP(cap_epoch,FE_B1B0_CAPTURE_GAP);
    if (sc->ref) OVERFLOW_GAP(ref_epoch,FE_B1B0_RENDER_GAP);
    OVERFLOW_GAP(clock_epoch,FE_B1B0_CLOCK_RESET);
#undef OVERFLOW_GAP
    if (count < 33u) return 0;
    *nneg = count;
    return 1;
}

static int execute(const scene_t *sc, uint32_t rate, proof_t *result) {
    _Alignas(16) unsigned char arena[ARENA];
    fe_b1b0_config cfg = make_cfg(sc,rate);
    fe_b1b0_src *s = NULL;
    ap_resampler_state_t oracle[5];
    int16_t input[FE_B1B0_MAX_MICS * 480u] = {0};
    int16_t render[480u] = {0};
    float out[FE_B1B0_MAX_MICS * FE_B1B0_INTERNAL_FRAMES], refout[FE_B1B0_INTERNAL_FRAMES];
    float expected[FE_B1B0_INTERNAL_FRAMES];
    const size_t input_count = (size_t)(rate/100u) * sc->n;
    const size_t render_count = (size_t)(rate/100u) * sc->ref;
    const size_t mic_output_count = (size_t)sc->n * FE_B1B0_INTERNAL_FRAMES;
    const size_t ref_output_count = (size_t)sc->ref * FE_B1B0_INTERNAL_FRAMES;
    uint32_t frame,p,k,mask,negative_checks=0u;
    uint64_t source_hash=FNV_O, mic_hash=FNV_O, render_hash=FNV_O;
    memset(result,0,sizeof(*result));
    if (!fe_b1b0_state_bytes(&cfg) ||
        fe_b1b0_state_bytes(&cfg) > ARENA ||
        fe_b1b0_init(arena,sizeof(arena),&cfg,&s) != FE_B1B0_OK || !s ||
        !negatives(sc,rate,s,arena,fe_b1b0_state_bytes(&cfg),&negative_checks))
        return 0;
    for(p=0u;p<sc->n+sc->ref;++p) ap_resampler_init(&oracle[p]);
    for(frame=0u;frame<FRAMES;++frame) {
        const uint32_t cap_source_frame=frame+(frame>=50u?1u:0u);
        const uint32_t ref_source_frame=frame+(frame>=80u?1u:0u);
        mask=frame<70u?(1u<<sc->n)-1u:(sc->n==4u?13u:1u);
        if(frame==50u){
            if(fe_b1b0_notify_gap(s,FE_B1B0_CAPTURE_GAP)!=FE_B1B0_OK) return 0;
            for(p=0u;p<sc->n;++p) ap_resampler_reset(&oracle[p]);
        }
        if(frame==70u && fe_b1b0_set_active_mask(s,mask)!=FE_B1B0_OK) return 0;
        if(frame==80u && sc->ref) {
            if(fe_b1b0_notify_gap(s,FE_B1B0_RENDER_GAP)!=FE_B1B0_OK) return 0;
            ap_resampler_reset(&oracle[sc->n]);
        }
        if(frame==90u){
            if(fe_b1b0_notify_gap(s,FE_B1B0_CLOCK_RESET)!=FE_B1B0_OK) return 0;
            for(p=0u;p<sc->n+sc->ref;++p) ap_resampler_reset(&oracle[p]);
        }
        for(p=0u;p<sc->n;++p) for(k=0u;k<rate/100u;++k){
            const int16_t val=mic_source(p,k,cap_source_frame);
            input[(size_t)k*sc->n+sc->slots[p]]=val;
            source_hash=h16(source_hash,val);
        }
        if(sc->ref) for(k=0u;k<rate/100u;++k)
            render[k]=render_source(k,ref_source_frame);
        if(fe_b1b0_process(s,input,input_count,sc->ref?render:NULL,render_count,
                           out,mic_output_count,sc->ref?refout:NULL,ref_output_count)!=FE_B1B0_OK)
            return 0;
        for(p=0u;p<sc->n;++p){
            ap_resample_input_channel(&oracle[p],0u,input,rate/100u,sc->n,
                                      sc->slots[p],expected,FE_B1B0_INTERNAL_FRAMES);
            if((mask&(1u<<p))==0u) memset(expected,0,sizeof(expected));
            for(k=0u;k<FE_B1B0_INTERNAL_FRAMES;++k){
                const float actual=out[(size_t)p*FE_B1B0_INTERNAL_FRAMES+k];
                if(memcmp(&actual,&expected[k],sizeof(float))) return 0;
                mic_hash=hfloat(mic_hash,actual);
                if(rate==16000u && (mask&(1u<<p))) {
                    const float identity=(float)input[(size_t)k*sc->n+sc->slots[p]]*
                                         (1.0f/32768.0f);
                    if(memcmp(&actual,&identity,sizeof(float))) return 0;
                }
            }
        }
        if(sc->ref){
            ap_resample_input_channel(&oracle[sc->n],0u,render,rate/100u,1u,0u,
                                      expected,FE_B1B0_INTERNAL_FRAMES);
            for(k=0u;k<FE_B1B0_INTERNAL_FRAMES;++k){
                if(memcmp(&expected[k],&refout[k],sizeof(float))) return 0;
                render_hash=hfloat(render_hash,refout[k]);
            }
        }
    }
    if(fe_b1b0_get_info(s,&result->info)!=FE_B1B0_OK ||
       result->info.accepted_frames!=100u ||
       result->info.capture_epoch!=2u ||
       result->info.render_epoch!=(sc->ref?2u:0u) ||
       result->info.clock_epoch!=1u ||
       result->info.capture_frames_in_epoch!=10u ||
       result->info.render_frames_in_epoch!=(sc->ref?10u:0u) ||
       result->info.input_rate_hz!=rate ||
       result->info.capture_frame_samples!=rate/100u ||
       result->info.internal_frame_samples!=160u ||
       result->info.existing_first_party_filter_delay_samples!=(rate==16000u?0u:(rate==32000u?5u:7u)) ||
       result->info.active_mic_mask!=(sc->n==4u?13u:1u) ||
       result->info.render_channels!=sc->ref ||
       result->info.physical_mics!=sc->n ||
       result->info.capture_clock_authority!=0u)
        return 0;
    result->negatives=negative_checks;
    result->source_hash=source_hash;
    result->mic_float_hash=mic_hash;
    result->ref_float_hash=render_hash;
    if(fe_b1b0_reset(s)!=FE_B1B0_OK ||
       fe_b1b0_get_info(s,&result->info)!=FE_B1B0_OK ||
       result->info.accepted_frames!=0u ||
       result->info.capture_epoch!=0u ||
       result->info.render_epoch!=0u ||
       result->info.clock_epoch!=0u)
       return 0;
    return 1;
}

int main(void) {
    uint32_t scene,rate_index;
    int first=1;
    proof_t one,two;
    printf("{\"schema_version\":1,\"decision\":\"FE09_R2B1B_S0_FIRST_PARTY_N_RENDER_SRC_RESEARCH_ONLY_NO_RELEASE\",");
    printf("\"source_role\":\"first-party-synthetic\",\"sample_rate_hz_internal\":16000,");
    printf("\"source_kernel\":\"src/frontend/ap_resampler.c\",\"bandlimited\":true,");
    printf("\"public_sdk_installed\":false,\"shipping_authority\":false,");
    printf("\"render_is_not_aec\":true,\"bf_integrated\":false,\"ssc305_dut_qualified\":false,");
    printf("\"real_adc_clock_qualified\":false,\"full_c4_budget_qualified\":false,");
    printf("\"repeats\":2,\"profile_count\":12,\"profiles\":[");
    for(rate_index=0u;rate_index<3u;++rate_index){
        for(scene=0u;scene<4u;++scene){
            if(!execute(&SCENES[scene],RATES[rate_index],&one) ||
               !execute(&SCENES[scene],RATES[rate_index],&two) ||
               memcmp(&one,&two,sizeof(one))) {
                fprintf(stderr,"FE09_B1B0_PROFILE_FAILED scene=%u rate=%u\n",
                        scene,RATES[rate_index]);
                return 1;
            }
            if(!first) printf(",");
            first=0;
            printf("{\"name\":\"%s\",\"input_rate_hz\":%u,\"mics\":%u,\"render\":%u,",
                    SCENES[scene].name,RATES[rate_index],
                    SCENES[scene].n,SCENES[scene].ref);
            printf("\"input_frame_samples\":%u,\"state_bytes\":%zu,\"src_state_per_stream_bytes\":%zu,",
                    RATES[rate_index]/100u,one.info.requested_state_bytes,
                    one.info.first_party_src_state_bytes_per_stream);
            printf("\"filter_delay_samples\":%u,\"negative_checks\":%u,",
                    one.info.existing_first_party_filter_delay_samples,one.negatives);
            printf("\"accepted_frames\":100,\"capture_epoch\":2,\"render_epoch\":%u,",
                    SCENES[scene].ref?2u:0u);
            printf("\"clock_epoch\":1,\"capture_frames_in_epoch\":10,\"render_frames_in_epoch\":%u,",
                    SCENES[scene].ref?10u:0u);
            printf("\"source_hash\":\"%016" PRIx64 "\",",one.source_hash);
            printf("\"mic_float_hash\":\"%016" PRIx64 "\",",one.mic_float_hash);
            printf("\"render_float_hash\":\"%016" PRIx64 "\"}",one.ref_float_hash);
        }
    }
    puts("]}");
    return 0;
}
