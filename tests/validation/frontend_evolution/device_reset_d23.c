/* Research-only observer: frozen D22 fixture plus one original full reset. */
#include "aec/ap_aec.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

static uint32_t d23_calls, d23_reset_calls;
static int d23_policy, d23_invalid;
static double d23_pre_weight, d23_post_weight;
static float d23_post_power;
static uint32_t d23_post_steady, d23_post_head;

static double d23_weight(const ap_aec_state_t *s) {
    double value = 0.0;
    uint32_t part, bin;
    for (part = 0u; part < s->backend.active_partitions; ++part)
        for (bin = 0u; bin < s->backend.bins; ++bin) {
            const double re = (double)s->backend.weights[part][bin].re;
            const double im = (double)s->backend.weights[part][bin].im;
            value += re*re+im*im;
        }
    return value;
}

static void d23_process(ap_aec_state_t *s, int enabled, float mu, uint32_t n,
                        const float *mic, const float *ref, float *residual, float *echo,
                        int far, int dt, ap_aec_result_t *result) {
    if (d23_policy && d23_calls == 1000u) {
        d23_pre_weight = d23_weight(s);
        ap_aec_backend_reset(s);
        ++d23_reset_calls;
        d23_post_weight = d23_weight(s);
        d23_post_power = s->backend.x_power_total;
        d23_post_steady = s->steady_frames;
        d23_post_head = s->backend.x_head;
        if (!isfinite(d23_pre_weight) || d23_post_weight != 0.0 || d23_post_power != 0.0f ||
            d23_post_steady != 0u || d23_post_head != 47u || s->runtime_adapt_stride != 2u ||
            s->backend.active_partitions != 48u || s->backend.block != 32u) d23_invalid = 1;
    }
    ++d23_calls;
    ap_aec_backend_process(s,enabled,mu,n,mic,ref,residual,echo,far,dt,result);
}

static int d23_report(const char *text) {
    (void)text;
    if (!d23_reset_calls)
        return printf("{\"frames\":2000,\"samples\":320000,\"sync_calls\":0,\"reset_calls\":0,\"reset_frame\":null,\"reset_pre_weight_l2\":null,\"reset_post_weight_l2\":null,\"reset_post_x_power_total\":null,\"reset_post_steady_frames\":null,\"reset_post_x_head\":null}\n");
    return printf("{\"frames\":2000,\"samples\":320000,\"sync_calls\":0,\"reset_calls\":%u,\"reset_frame\":1000,\"reset_pre_weight_l2\":%.17g,\"reset_post_weight_l2\":%.17g,\"reset_post_x_power_total\":%.9g,\"reset_post_steady_frames\":%u,\"reset_post_x_head\":%u}\n",
                  d23_reset_calls,d23_pre_weight,d23_post_weight,(double)d23_post_power,d23_post_steady,d23_post_head);
}

#define ap_aec_backend_process d23_process
#define puts d23_report
#define main d23_fixture_main
#include "device_multipath_d22.c"
#undef main
#undef puts
#undef ap_aec_backend_process

int main(int argc, char **argv) {
    int result;
    if (argc != 6) return 2;
    if (strcmp(argv[5],"reset") == 0) d23_policy = 1;
    else if (strcmp(argv[5],"keep") != 0) return 2;
    result = d23_fixture_main(argc-1,argv);
    if (!result && (d23_calls != 2000u || d23_reset_calls != (uint32_t)d23_policy || d23_invalid)) return 6;
    return result;
}
