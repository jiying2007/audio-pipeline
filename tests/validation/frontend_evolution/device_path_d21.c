/* Standalone frozen MDF engineering diagnostic, never installed. */
#include "aec/ap_aec.h"
#include "sync/ap_sync.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

static uint64_t sync_calls;
int ap_sync_get_reference_d18_real(ap_sync_state_t *, uint32_t, float *);
int ap_sync_get_reference(ap_sync_state_t *s, uint32_t n, float *out) {
    ++sync_calls;
    return ap_sync_get_reference_d18_real(s, n, out);
}

static uint32_t random_state = UINT32_C(0x12345678);
static float raw[320000];
static ap_aec_state_t state;

int main(int argc, char **argv) {
    static const char *names[] = {"mic.f32le", "reference.f32le", "echo.f32le", "residual.f32le", "state.csv"};
    FILE *files[5] = {NULL, NULL, NULL, NULL, NULL};
    float mic[160], ref[160], echo[160], residual[160];
    uint32_t path, offset, i, frame;
    uint16_t endian = 1u;
    int enabled = 1, far = 1, zero = 0, future = 0, result = 0;
    char filename[1024];
    if (argc != 5 || *(const unsigned char *)&endian != 1u || sizeof(float) != 4u) return 2;
    path = strcmp(argv[1], "32") == 0 ? 32u : strcmp(argv[1], "48") == 0 ? 48u : strcmp(argv[1], "64") == 0 ? 64u : 0u;
    offset = strcmp(argv[2], "16") == 0 ? 16u : strcmp(argv[2], "20") == 0 ? 20u : 0u;
    if (!path || !offset) return 2;
    if (strcmp(argv[3], "disabled") == 0) enabled = 0;
    else if (strcmp(argv[3], "hold") == 0) far = 0;
    else if (strcmp(argv[3], "zero") == 0) zero = 1;
    else if (strcmp(argv[3], "future") == 0) future = 1;
    else if (strcmp(argv[3], "normal") != 0) return 2;
    if (strcmp(argv[3], "normal") != 0 && (path != 48u || offset != (future ? 20u : 16u))) return 2;
    for (i = 0u; i < 320000u; ++i) {
        random_state ^= random_state << 13u;
        random_state ^= random_state >> 17u;
        random_state ^= random_state << 5u;
        raw[i] = (float)((int32_t)(random_state & UINT32_C(65535)) - 32768) / 262144.0f;
        if (future && i >= 160000u) raw[i] = -raw[i];
    }
    for (i = 0u; i < 5u; ++i) {
        const int written = snprintf(filename, sizeof(filename), "%s/%s", argv[4], names[i]);
        if (written < 0 || (size_t)written >= sizeof(filename)) { result = 2; goto done; }
        files[i] = fopen(filename, "wb");
        if (!files[i]) { result = 4; goto done; }
    }
    ap_aec_backend_init(&state, 160u, 1536u, 2u);
    if (state.backend.block != 32u || state.backend.active_partitions != 48u ||
        fprintf(files[4], "frame,runtime_stride,steady_frames,adapt_phase,constrain_partition,x_head,x_power_total,weight_l2\n") < 0) {
        result = 5; goto done;
    }
    for (frame = 0u; frame < 2000u; ++frame) {
        ap_aec_result_t aec_result;
        double weight_l2 = 0.0;
        uint32_t part, bin;
        for (i = 0u; i < 160u; ++i) {
            const uint32_t n = frame * 160u + i;
            mic[i] = n < path ? 0.0f : 0.5f * raw[n - path];
            ref[i] = zero || n < offset ? 0.0f : raw[n - offset];
        }
        ap_aec_backend_process(&state, enabled, 0.22f, 160u, mic, ref, residual, echo, far, 0, &aec_result);
        if (sync_calls || !isfinite(aec_result.echo_energy) || !isfinite(state.backend.x_power_total) ||
            state.runtime_adapt_stride != 2u || state.backend.adapt_phase > 1u) { result = 6; goto done; }
        for (i = 0u; i < 160u; ++i) {
            if (!isfinite(echo[i]) || !isfinite(residual[i]) || fabsf(mic[i] - (echo[i] + residual[i])) > 1.0e-6f) {
                result = 7; goto done;
            }
        }
        for (part = 0u; part < state.backend.active_partitions; ++part)
            for (bin = 0u; bin < state.backend.bins; ++bin) {
                const double re = (double)state.backend.weights[part][bin].re;
                const double im = (double)state.backend.weights[part][bin].im;
                weight_l2 += re * re + im * im;
            }
        if (!isfinite(weight_l2)) { result = 7; goto done; }
        if (fwrite(mic, sizeof(float), 160u, files[0]) != 160u || fwrite(ref, sizeof(float), 160u, files[1]) != 160u ||
            fwrite(echo, sizeof(float), 160u, files[2]) != 160u || fwrite(residual, sizeof(float), 160u, files[3]) != 160u ||
            fprintf(files[4], "%u,%u,%u,%u,%u,%u,%.9g,%.17g\n", frame, state.runtime_adapt_stride,
                    state.steady_frames, state.backend.adapt_phase, state.backend.constrain_partition,
                    state.backend.x_head, (double)state.backend.x_power_total, weight_l2) < 0) { result = 8; goto done; }
    }
done:
    for (i = 0u; i < 5u; ++i) if (files[i] && fclose(files[i])) result = 9;
    if (!result) puts("{\"frames\":2000,\"samples\":320000,\"sync_calls\":0}");
    return result;
}
