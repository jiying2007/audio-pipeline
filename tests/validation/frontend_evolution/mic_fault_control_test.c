#include "mic_fault_control.h"
#include "array_native.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define D0_FRAMES 1600u
#define D0_SAMPLES 160u
#define D0_CASES 11u
#define FNV_OFFSET UINT64_C(14695981039346656037)
#define FNV_PRIME UINT64_C(1099511628211)

enum scene {
    QUIET, COHERENT, WEAK_SIDE, DIFFUSE, MOTOR_TONE, CLIPPED,
    HARD_ZERO, RAIL_PLUS, RAIL_MINUS, SEQUENTIAL, RECOVERY
};
static const char *const SCENE_NAMES[D0_CASES] = {
    "quiet", "coherent", "weak-side", "diffuse", "motor-tone", "clipped",
    "hard-zero", "rail-plus", "rail-minus", "sequential", "recovery"
};
static unsigned assertions;
#define CHECK(expr) do { ++assertions; if (!(expr)) { \
    fprintf(stderr, "FE06 failed at line %d: %s\n", __LINE__, #expr); return 1; \
} } while (0)

static fe_array_config geometry(unsigned circle) {
    fe_array_config c;
    uint32_t i;
    memset(&c, 0, sizeof(c));
    c.sample_rate_hz = 16000u; c.mic_count = 4u;
    c.active_mask = 15u; c.direction[1] = 1.0;
    c.interpolation = FE_ARRAY_FIR33_HANN;
    for (i = 0u; i < 4u; ++i) {
        c.microphones[i].gain = 1.0;
        c.microphones[i].input_channel = i;
        if (!circle) c.microphones[i].position_m[0] = 0.035*(double)i;
        else {
            static const double x[4] = {0.035, 0.0, -0.035, 0.0};
            static const double y[4] = {0.0, 0.035, 0.0, -0.035};
            c.microphones[i].position_m[0] = x[i];
            c.microphones[i].position_m[1] = y[i];
        }
    }
    return c;
}

static void make_frame(enum scene which, unsigned circle, uint32_t frame,
                       float recorded[D0_SAMPLES*4u], float healthy[D0_SAMPLES*4u]) {
    uint32_t t, channel;
    for (t = 0u; t < D0_SAMPLES; ++t) for (channel = 0u; channel < 4u; ++channel) {
        const double n = (double)frame*(double)D0_SAMPLES + (double)t;
        const double phase = 0.020*n + (double)channel*(circle ? 0.23 : 0.10);
        double v = 0.100*sin(phase) + 0.035*sin(0.071*n + 0.12*(double)channel);
        if (which == QUIET) v = 0.0;
        if (which == WEAK_SIDE && channel == 3u) v *= 0.001;
        if (which == DIFFUSE) v = 0.12*sin(n*(0.014+0.009*(double)channel)+channel);
        if (which == MOTOR_TONE) v = 0.06*sin(0.12*n) + 0.08*sin(phase);
        if (which == CLIPPED && frame % 103u == 0u && t % 13u == 0u)
            v = ((frame+t)&1u) ? 1.0 : -1.0;
        healthy[t*4u+channel] = (float)v;
        if ((which == HARD_ZERO || which == SEQUENTIAL ||
             (which == RECOVERY && frame < 1000u)) &&
            frame >= 400u && channel == 0u) v = 0.0;
        if (which == RAIL_PLUS && frame >= 400u && channel == 0u) v = 1.0;
        if (which == RAIL_MINUS && frame >= 400u && channel == 0u) v = -1.0;
        if (which == SEQUENTIAL && frame >= 800u && channel == 2u) v = 1.0;
        recorded[t*4u+channel] = (float)v;
    }
}

static uint64_t checksum(uint64_t h, const void *data, size_t size) {
    const unsigned char *bytes = (const unsigned char *)data;
    size_t i;
    for (i = 0u; i < size; ++i) { h ^= bytes[i]; h *= FNV_PRIME; }
    return h;
}

/* Only this research runner writes evidence. Detector/BF data planes remain I/O-free. */
static FILE *trace_open(const char *root, unsigned circle, enum scene which,
                        const char *suffix) {
    char path[1024];
    int size;
    if (!root) return NULL;
    size = snprintf(path, sizeof(path), "%s/%s-%s.%s",
                    root, circle ? "UCA4" : "ULA4", SCENE_NAMES[which], suffix);
    if (size < 0 || (size_t)size >= sizeof(path)) return NULL;
    return fopen(path, "wbx"); /* Never overwrite pre-existing evidence. */
}

static int run_scene(unsigned circle, enum scene which, unsigned index,
                     const char *trace_root, int alternate_future) {
    _Alignas(FE_ARRAY_ALIGNMENT) unsigned char arena[8192], split_arena[8192], healthy_arena[8192];
    unsigned char saved[8192];
    fe_array *array = NULL, *split = NULL, *baseline = NULL;
    fe_array_config cfg = geometry(circle);
    fe_mic_fault_control detector, before;
    fe_mic_fault_observation obs, obs_before;
    float pcm[D0_SAMPLES*4u], healthy[D0_SAMPLES*4u];
    float out[D0_SAMPLES], chunked[D0_SAMPLES], base[D0_SAMPLES];
    const size_t bytes = fe_array_state_bytes_for_mode(4u,FE_ARRAY_FIR33_HANN);
    uint32_t mask = 15u, frame, first = UINT32_MAX, second = UINT32_MAX;
    unsigned suggestions = 0u, recoveries = 0u;
    uint64_t input_hash = FNV_OFFSET, output_hash = FNV_OFFSET, mask_hash = FNV_OFFSET;
    double rms_delta_energy = 0.0, maximum_discontinuity = 0.0;
    float prev = 0.0f;
    FILE *input_file = NULL, *output_file = NULL, *mask_file = NULL;
    size_t t;

    if (trace_root) {
        input_file = trace_open(trace_root, circle, which, "input.f32le");
        output_file = trace_open(trace_root, circle, which, "output.f32le");
        mask_file = trace_open(trace_root, circle, which, "mask.u32le");
        CHECK(input_file && output_file && mask_file);
    }
    CHECK(bytes <= sizeof(arena));
    CHECK(fe_array_init(arena,bytes,&cfg,&array)==FE_ARRAY_OK);
    CHECK(fe_array_init(split_arena,bytes,&cfg,&split)==FE_ARRAY_OK);
    CHECK(fe_array_init(healthy_arena,bytes,&cfg,&baseline)==FE_ARRAY_OK);
    CHECK(fe_mic_fault_init(&detector)==0);
    memset(&obs,0xa5,sizeof(obs));

    for (frame = 0u; frame < D0_FRAMES; ++frame) {
        make_frame(which,circle,frame,pcm,healthy);
        if (alternate_future && frame >= 1200u) {
            uint32_t channel;
            /* Fixed prefix (frames 0..1199) remains bit-identical.
             * Perturb only healthy/remaining live signals; preserve exact
             * injected zero/rail faults and their fixed detection schedule.
             */
            for (t = 0u; t < D0_SAMPLES; ++t)
                for (channel = 0u; channel < 4u; ++channel) {
                    const unsigned stuck_zero = channel == 0u && frame >= 400u &&
                        (which == HARD_ZERO || which == SEQUENTIAL ||
                         (which == RECOVERY && frame < 1000u));
                    const unsigned stuck_rail = frame >= 400u &&
                        ((channel == 0u && (which == RAIL_PLUS || which == RAIL_MINUS)) ||
                         (channel == 2u && which == SEQUENTIAL && frame >= 800u));
                    const size_t at = t*4u + channel;
                    if (!stuck_zero && !stuck_rail) {
                        pcm[at] = pcm[at] == 0.0f ? 0.02f : -pcm[at];
                        healthy[at] = healthy[at] == 0.0f ? 0.02f : -healthy[at];
                    }
                }
        }
        input_hash = checksum(input_hash,pcm,sizeof(pcm));
        if (input_file) CHECK(fwrite(pcm,sizeof(float),D0_SAMPLES*4u,input_file)==D0_SAMPLES*4u);
        if (frame == 250u) {
            /* Invalid/noisy observations cannot advance counters or mutate outputs. */
            float saved_value;
            before = detector; obs_before = obs;
            CHECK(fe_mic_fault_observe(&detector,pcm,639u,mask,&obs)!=0);
            CHECK(memcmp(&detector,&before,sizeof(before))==0 &&
                  memcmp(&obs,&obs_before,sizeof(obs))==0);
            saved_value = pcm[17];
            pcm[17] = NAN;
            CHECK(fe_mic_fault_observe(&detector,pcm,640u,mask,&obs)!=0);
            CHECK(memcmp(&detector,&before,sizeof(before))==0 &&
                  memcmp(&obs,&obs_before,sizeof(obs))==0);
            pcm[17] = 1.1f;
            CHECK(fe_mic_fault_observe(&detector,pcm,640u,mask,&obs)!=0);
            CHECK(memcmp(&detector,&before,sizeof(before))==0 &&
                  memcmp(&obs,&obs_before,sizeof(obs))==0);
            pcm[17] = saved_value;
            CHECK(fe_mic_fault_observe(&detector,pcm,640u,0u,&obs)!=0);
            CHECK(memcmp(&detector,&before,sizeof(before))==0);
        }
        if (which == RECOVERY && frame == 1020u) {
            /* Explicit caller re-enable, not a detector or BF implicit recovery. */
            CHECK(mask == 14u);
            CHECK(fe_array_set_active_mask(array,15u)==FE_ARRAY_OK);
            CHECK(fe_array_set_active_mask(split,15u)==FE_ARRAY_OK);
            mask = 15u; ++recoveries;
        }
        CHECK(fe_mic_fault_observe(&detector,pcm,640u,mask,&obs)==0);
        CHECK(obs.complete_frames == (uint64_t)frame+1u && obs.observed_mask==mask);
        if (obs.proposed_mask != mask) {
            CHECK(obs.newly_suspected_mask != 0u &&
                  obs.proposed_mask == (mask & ~obs.newly_suspected_mask) &&
                  obs.proposed_mask != 0u);
            ++suggestions;
            if (first == UINT32_MAX) first = frame;
            else if (second == UINT32_MAX) second = frame;
            CHECK(frame == 402u || (which==SEQUENTIAL && frame==802u));
            CHECK(obs.proposed_mask == (frame==402u ? 14u : 10u));
            CHECK((obs.zero_signature_mask & 1u) != 0u || which==RAIL_PLUS || which==RAIL_MINUS);
            memcpy(saved,arena,bytes);
            CHECK(fe_array_set_active_mask(array,0u)==FE_ARRAY_EINVAL &&
                  memcmp(arena,saved,bytes)==0);
            CHECK(fe_array_set_active_mask(array,16u)==FE_ARRAY_EINVAL &&
                  memcmp(arena,saved,bytes)==0);
            CHECK(fe_array_set_active_mask(array,obs.proposed_mask)==FE_ARRAY_OK);
            CHECK(fe_array_set_active_mask(split,obs.proposed_mask)==FE_ARRAY_OK);
            mask = obs.proposed_mask;
        }
        CHECK(fe_array_process(array,pcm,640u,out,160u)==FE_ARRAY_OK);
        CHECK(fe_array_process(split,pcm,17u*4u,chunked,17u)==FE_ARRAY_OK);
        CHECK(fe_array_process(split,pcm+17u*4u,143u*4u,chunked+17u,143u)==FE_ARRAY_OK);
        CHECK(memcmp(out,chunked,sizeof(out))==0);
        CHECK(fe_array_process(baseline,healthy,640u,base,160u)==FE_ARRAY_OK);
        mask_hash = checksum(mask_hash,&mask,sizeof(mask));
        output_hash = checksum(output_hash,out,sizeof(out));
        if (output_file) CHECK(fwrite(out,sizeof(float),D0_SAMPLES,output_file)==D0_SAMPLES);
        if (mask_file) CHECK(fwrite(&mask,sizeof(mask),1u,mask_file)==1u);
        for (t = 0u; t < D0_SAMPLES; ++t) {
            const double error = (double)out[t]-(double)base[t];
            const double jump = fabs((double)out[t]-(double)prev);
            CHECK(isfinite(out[t]) && isfinite(base[t]));
            rms_delta_energy += error*error;
            if (frame!=0u || t!=0u)
                if (jump > maximum_discontinuity) maximum_discontinuity = jump;
            prev = out[t];
        }
    }
    if (which <= CLIPPED) CHECK(suggestions==0u && first==UINT32_MAX && mask==15u);
    else if (which==SEQUENTIAL) CHECK(suggestions==2u && first==402u &&
                                     second==802u && mask==10u);
    else CHECK(suggestions==1u && first==402u &&
               mask==(which==RECOVERY?15u:14u));
    CHECK(recoveries==(which==RECOVERY?1u:0u));
    if (input_file) CHECK(fclose(input_file)==0);
    if (output_file) CHECK(fclose(output_file)==0);
    if (mask_file) CHECK(fclose(mask_file)==0);
    printf("%s{\"case_id\":\"%s-%s\",\"geometry\":\"%s\","
           "\"scene\":\"%s\",\"frames\":1600,"
           "\"suggestions\":%u,\"first_frame\":%u,"
           "\"second_frame\":%u,\"final_mask\":%u,"
           "\"explicit_reenables\":%u,\"input_fnv64\":\"%016llx\","
           "\"output_fnv64\":\"%016llx\",\"mask_fnv64\":\"%016llx\","
           "\"delta_rms\":%.9f,\"max_discontinuity\":%.9f}",
           index==0u?"":",",circle?"UCA4":"ULA4",SCENE_NAMES[which],
           circle?"UCA4":"ULA4",SCENE_NAMES[which],
           suggestions,first,second,mask,recoveries,
           (unsigned long long)input_hash,(unsigned long long)output_hash,
           (unsigned long long)mask_hash,
           sqrt(rms_delta_energy/(double)(D0_FRAMES*D0_SAMPLES)),maximum_discontinuity);
    return 0;
}

static int spatial_reject_and_single_active(void) {
    _Alignas(FE_ARRAY_ALIGNMENT) unsigned char arena[8192];
    unsigned char saved[8192];
    float coeffs[132] = {0.0f};
    fe_array *s = NULL;
    fe_array_config c = geometry(1u);
    size_t bytes;
    uint32_t i;
    for (i=0u;i<4u;++i) coeffs[i*33u+16u]=0.25f;
    c.interpolation=FE_ARRAY_SPATIAL33;
    bytes=fe_array_state_bytes_for_mode(4u,c.interpolation);
    CHECK(fe_array_init_spatial33(arena,bytes,&c,coeffs,132u,&s)==FE_ARRAY_OK);
    memcpy(saved,arena,bytes);
    CHECK(fe_array_set_active_mask(s,14u)==FE_ARRAY_EINVAL &&
          memcmp(saved,arena,bytes)==0);
    c.interpolation=FE_ARRAY_FIR33_HANN;
    CHECK(fe_array_init(arena,bytes,&c,&s)==FE_ARRAY_OK);
    CHECK(fe_array_set_active_mask(s,1u)==FE_ARRAY_OK);
    CHECK(fe_array_get_info(s,(fe_array_info *)arena)==FE_ARRAY_EINVAL);
    return 0;
}

int main(int argc, char **argv) {
    unsigned geo,scene,index=0u;
    const char *trace_root = NULL;
    int alternate_future = 0;
    if (argc != 1 && argc != 3) return 2;
    if (argc == 3) {
        trace_root = argv[1];
        if (strcmp(argv[2], "base") == 0) alternate_future = 0;
        else if (strcmp(argv[2], "future") == 0) alternate_future = 1;
        else return 2;
    }
    CHECK(spatial_reject_and_single_active()==0);
    printf("{\"schema_version\":1,\"experiment_id\":\"FE06-MIC-FAULT-CONTROL-D0\","
           "\"shipping_authority\":false,\"decision\":\"MIC_FAULT_HARD_SIGNATURE_D0_NO_PROMOTION\","
           "\"cases\":[");
    for (geo=0u;geo<2u;++geo)
        for (scene=0u;scene<D0_CASES;++scene) {
            CHECK(run_scene(geo,(enum scene)scene,index,trace_root,alternate_future)==0);
            ++index;
        }
    printf("],\"case_count\":%u,\"assertions\":%u}\n",index,assertions);
    return 0;
}
