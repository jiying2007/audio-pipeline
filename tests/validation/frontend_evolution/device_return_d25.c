/* Frozen D25 engineering inputs; the D24 selector and real MDF are unchanged. */
#define main d25_unused_fixture_main
#include "device_multipath_d22.c"
#undef main
#include "device_shadow_selector_d24.h"

static ap_aec_state_t shadow_state;

static uint32_t next_random(uint32_t *value) {
    *value ^= *value << 13u; *value ^= *value >> 17u; *value ^= *value << 5u;
    return *value;
}

int main(int argc, char **argv) {
    static const char *names[] = {"mic.f32le","reference.f32le","echo.f32le","residual.f32le",
        "primary_echo.f32le","primary_residual.f32le","shadow_echo.f32le","shadow_residual.f32le",
        "true_echo.f32le","near.f32le","state.csv","selector.csv"};
    FILE *files[12] = {NULL};
    float mic[160], ref[160], pe[160], pr[160], se[160] = {0}, sr[160] = {0};
    float selected_echo[160], selected_residual[160], truth[160], near[160];
    uint32_t render_random = UINT32_C(0x12345678), near_random = UINT32_C(0x87654321);
    uint32_t frame, i, offset, shadow_calls = 0u, resets = 0u, dt_frames = 0u;
    uint16_t endian = 1u;
    int shape, condition, policy, future, result = 0;
    d24_selection_t selection = {0u,0u,0u};
    char filename[1024];
    if (argc != 6 && argc != 7) return 2;
    shape = strcmp(argv[1],"A") == 0 ? 0 : strcmp(argv[1],"ABA") == 0 ? 1 : -1;
    offset = strcmp(argv[2],"16") == 0 ? 16u : strcmp(argv[2],"20") == 0 ? 20u : 0u;
    condition = strcmp(argv[3],"echo") == 0 ? 0 : strcmp(argv[3],"dt") == 0 ? 1 : strcmp(argv[3],"unguarded") == 0 ? 2 : -1;
    policy = strcmp(argv[5],"keep") == 0 ? 0 : strcmp(argv[5],"shadow") == 0 ? 1 : -1;
    future = argc == 7;
    if (shape < 0 || !offset || condition < 0 || policy < 0 || *(const unsigned char *)&endian != 1u || sizeof(float) != 4u ||
        (future && (strcmp(argv[6],"future") != 0 || shape != 1 || offset != 20u || condition != 2 || policy != 1))) {
        fprintf(stderr,"D25_INVALID_ARGUMENT_REJECT primary_calls=0 shadow_calls=0\n"); return 2;
    }
    for (i = 0u; i < 320000u; ++i) {
        raw[i] = (float)((int32_t)(next_random(&render_random) & UINT32_C(65535))-32768)/262144.0f;
        if (future && i >= 160000u) raw[i] = -raw[i];
    }
    for (i = 0u; i < 12u; ++i) {
        int written = snprintf(filename,sizeof(filename),"%s/%s",argv[4],names[i]);
        if (written < 0 || (size_t)written >= sizeof(filename)) { result = 2; goto done; }
        files[i] = fopen(filename,"wb"); if (!files[i]) { result = 4; goto done; }
    }
    ap_aec_backend_init(&state,160u,1536u,2u);
    if (state.backend.block != 32u || state.backend.active_partitions != 48u ||
        fprintf(files[10],"frame,runtime_stride,steady_frames,adapt_phase,constrain_partition,x_head,x_power_total,weight_l2\n") < 0 ||
        fprintf(files[11],"frame,active,dt,bank,streak,change,primary_energy,shadow_energy\n") < 0) { result = 5; goto done; }
    for (frame = 0u; frame < 2000u; ++frame) {
        const int near_active = (frame >= 1000u && frame < 1200u) || (frame >= 1600u && frame < 1800u);
        const int dt = condition == 1 && near_active;
        const int active = policy && frame >= 1000u;
        double primary_energy = 0.0, shadow_energy = 0.0, weight_l2 = 0.0;
        uint32_t part, bin;
        ap_aec_result_t primary_result;
        int change;
        if (dt) ++dt_frames;
        for (i = 0u; i < 160u; ++i) {
            uint32_t n = frame*160u+i, tap;
            int kernel = shape && n >= 160000u && n < 192000u ? 1 : 0;
            float noise = (float)((int32_t)(next_random(&near_random) & UINT32_C(65535))-32768)/524288.0f;
            if (future && n >= 160000u) noise = -noise;
            truth[i] = 0.0f;
            for (tap = 0u; tap < 3u; ++tap) if (n >= delays[kernel][tap]) {
                float product = gains[kernel][tap]*raw[n-delays[kernel][tap]];
                truth[i] = truth[i]+product;
            }
            near[i] = condition && near_active ? noise : 0.0f;
            mic[i] = truth[i]+near[i];
            ref[i] = n < offset ? 0.0f : raw[n-offset];
        }
        if (policy && frame == 1000u) { shadow_state = state; ap_aec_backend_reset(&shadow_state); ++resets; }
        ap_aec_backend_process(&state,1,0.22f,160u,mic,ref,pr,pe,1,dt,&primary_result);
        if (active) {
            ap_aec_result_t shadow_result;
            ++shadow_calls;
            ap_aec_backend_process(&shadow_state,1,0.22f,160u,mic,ref,sr,se,1,dt,&shadow_result);
            if (!isfinite(shadow_result.echo_energy)) { result = 6; goto done; }
        }
        for (i = 0u; i < 160u; ++i) {
            double p = (double)pr[i], s = (double)sr[i];
            primary_energy += p*p; shadow_energy += s*s;
            if (!isfinite(pe[i]) || !isfinite(pr[i]) || !isfinite(se[i]) || !isfinite(sr[i]) ||
                fabsf(mic[i]-(pe[i]+pr[i])) > 1e-6f || (active && fabsf(mic[i]-(se[i]+sr[i])) > 1e-6f)) { result = 7; goto done; }
        }
        change = d24_choose(&selection,active,!dt,primary_energy,shadow_energy);
        if (change < 0 || sync_calls || !isfinite(primary_result.echo_energy) || !isfinite(state.backend.x_power_total) ||
            state.runtime_adapt_stride != 2u || state.backend.adapt_phase > 1u) { result = 6; goto done; }
        memcpy(selected_echo,selection.bank ? se : pe,sizeof(pe)); memcpy(selected_residual,selection.bank ? sr : pr,sizeof(pr));
        for (part = 0u; part < state.backend.active_partitions; ++part) for (bin = 0u; bin < state.backend.bins; ++bin) {
            double re = (double)state.backend.weights[part][bin].re, im = (double)state.backend.weights[part][bin].im;
            weight_l2 += re*re+im*im;
        }
        if (!isfinite(weight_l2)) { result = 7; goto done; }
        {
            const float *traces[] = {mic,ref,selected_echo,selected_residual,pe,pr,se,sr,truth,near};
            for (i = 0u; i < 10u; ++i) if (fwrite(traces[i],sizeof(float),160u,files[i]) != 160u) { result = 8; goto done; }
        }
        if (fprintf(files[10],"%u,%u,%u,%u,%u,%u,%.9g,%.17g\n",frame,state.runtime_adapt_stride,state.steady_frames,
                    state.backend.adapt_phase,state.backend.constrain_partition,state.backend.x_head,(double)state.backend.x_power_total,weight_l2) < 0 ||
            fprintf(files[11],"%u,%d,%d,%u,%u,%d,%.17g,%.17g\n",frame,active,dt,selection.bank,selection.streak,change,primary_energy,shadow_energy) < 0) { result = 8; goto done; }
    }
done:
    for (i = 0u; i < 12u; ++i) if (files[i] && fclose(files[i])) result = 9;
    if (!result) printf("{\"frames\":2000,\"samples\":320000,\"sync_calls\":%llu,\"primary_calls\":2000,\"shadow_calls\":%u,\"shadow_reset_calls\":%u,\"switch_count\":%u,\"dt_frames\":%u,\"state_bytes\":%zu}\n",
        (unsigned long long)sync_calls,shadow_calls,resets,selection.changes,dt_frames,sizeof(ap_aec_state_t));
    return result;
}
