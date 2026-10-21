/* Research dual-state observer and output selector, frozen single-bank fixture. */
#include "aec/ap_aec.h"
#include "device_shadow_selector_d24.h"
#include <stdio.h>
#include <string.h>

static ap_aec_state_t d24_shadow;
static float d24_shadow_echo[160], d24_shadow_residual[160];
static uint32_t d24_primary_calls, d24_shadow_calls, d24_reset_calls;
static int d24_policy, d24_invalid;
static d24_selection_t d24_selection;
static FILE *d24_files[5];

static void d24_process(ap_aec_state_t *s, int enabled, float mu, uint32_t n,
                        const float *mic, const float *ref, float *residual, float *echo,
                        int far, int dt, ap_aec_result_t *result) {
    float primary_echo[160], primary_residual[160];
    double primary_energy = 0.0, shadow_energy = 0.0;
    const uint32_t frame = d24_primary_calls;
    const int active = d24_policy && frame >= 1000u;
    int change;
    uint32_t i;
    if (d24_policy && frame == 1000u) {
        d24_shadow = *s;
        ap_aec_backend_reset(&d24_shadow);
        ++d24_reset_calls;
    }
    ++d24_primary_calls;
    ap_aec_backend_process(s,enabled,mu,n,mic,ref,residual,echo,far,dt,result);
    memcpy(primary_echo,echo,sizeof(primary_echo)); memcpy(primary_residual,residual,sizeof(primary_residual));
    if (active) {
        ap_aec_result_t shadow_result;
        ++d24_shadow_calls;
        ap_aec_backend_process(&d24_shadow,enabled,mu,n,mic,ref,d24_shadow_residual,d24_shadow_echo,far,dt,&shadow_result);
        if (!isfinite(shadow_result.echo_energy)) d24_invalid = 1;
    }
    for (i = 0u; i < 160u; ++i) {
        const double p = (double)primary_residual[i], q = (double)d24_shadow_residual[i];
        primary_energy += p*p; shadow_energy += q*q;
        if (!isfinite(d24_shadow_residual[i]) || !isfinite(d24_shadow_echo[i])) d24_invalid = 1;
    }
    change = d24_choose(&d24_selection,active,enabled && far && !dt,primary_energy,shadow_energy);
    if (change < 0) d24_invalid = 1;
    if (d24_selection.bank) { memcpy(echo,d24_shadow_echo,sizeof(d24_shadow_echo)); memcpy(residual,d24_shadow_residual,sizeof(d24_shadow_residual)); }
    if (fwrite(primary_echo,sizeof(float),160u,d24_files[0]) != 160u || fwrite(primary_residual,sizeof(float),160u,d24_files[1]) != 160u ||
        fwrite(d24_shadow_echo,sizeof(float),160u,d24_files[2]) != 160u || fwrite(d24_shadow_residual,sizeof(float),160u,d24_files[3]) != 160u ||
        fprintf(d24_files[4],"%u,%d,%u,%u,%d,%.17g,%.17g\n",frame,active,d24_selection.bank,d24_selection.streak,change,primary_energy,shadow_energy) < 0) d24_invalid = 1;
}

static int d24_report(const char *text) {
    (void)text;
    return printf("{\"frames\":2000,\"samples\":320000,\"sync_calls\":0,\"primary_calls\":%u,\"shadow_calls\":%u,\"shadow_reset_calls\":%u,\"switch_count\":%u,\"state_bytes\":%zu}\n",
                  d24_primary_calls,d24_shadow_calls,d24_reset_calls,d24_selection.changes,sizeof(ap_aec_state_t));
}

#define ap_aec_backend_process d24_process
#define puts d24_report
#define main d24_fixture_main
#include "device_multipath_d22.c"
#undef main
#undef puts
#undef ap_aec_backend_process

static int d24_self_test(void) {
    d24_selection_t s = {0u,0u,0u};
    if (d24_choose(&s,1,1,1.0,0.8) || s.streak) return 3;
    if (d24_choose(&s,1,1,1.0,0.5) || s.streak != 1u) return 3;
    if (d24_choose(&s,1,0,1.0,0.5) || s.streak) return 3;
    if (d24_choose(&s,1,1,1.0,0.5) || d24_choose(&s,1,1,1.0,0.5) ||
        d24_choose(&s,1,1,1.0,0.5) != 1 || s.bank != 1u || s.changes != 1u) return 3;
    if (d24_choose(&s,1,1,0.1,1.0) || d24_choose(&s,1,1,0.1,1.0) ||
        d24_choose(&s,1,1,0.1,1.0) != 1 || s.bank || s.changes != 2u) return 3;
    if (d24_choose(&s,1,1,0.0,0.0) || s.streak || d24_choose(&s,1,1,NAN,0.0) != -1) return 3;
    if (d24_choose(&s,0,1,1.0,0.0) || s.bank || s.streak) return 3;
    puts("D24_SELECTOR_SELF_TEST_PASS");
    return 0;
}

int main(int argc, char **argv) {
    static const char *names[] = {"primary_echo.f32le","primary_residual.f32le","shadow_echo.f32le","shadow_residual.f32le","selector.csv"};
    char filename[1024];
    uint32_t i;
    int result = 0;
    int shape, future;
    uint32_t offset;
    if (argc == 2 && strcmp(argv[1],"--selector-self-test") == 0) return d24_self_test();
    if (argc != 6) return 2;
    if (strcmp(argv[5],"shadow") == 0) d24_policy = 1;
    else if (strcmp(argv[5],"keep") != 0) return 2;
    shape = strcmp(argv[1],"A") == 0 ? 0 : strcmp(argv[1],"B") == 0 ? 1 : strcmp(argv[1],"switch") == 0 ? 2 : -1;
    offset = strcmp(argv[2],"16") == 0 ? 16u : strcmp(argv[2],"20") == 0 ? 20u : 0u;
    future = strcmp(argv[3],"future") == 0;
    if (shape < 0 || !offset ||
        (strcmp(argv[3],"normal") != 0 && strcmp(argv[3],"disabled") != 0 && strcmp(argv[3],"hold") != 0 &&
         strcmp(argv[3],"zero") != 0 && !future) ||
        (strcmp(argv[3],"normal") != 0 && (future ? (shape != 2 || offset != 20u) : (shape != 0 || offset != 16u)))) {
        fprintf(stderr,"D24_INVALID_ARGUMENT_REJECT primary_calls=%u shadow_calls=%u\n",d24_primary_calls,d24_shadow_calls);
        return 2;
    }
    for (i = 0u; i < 5u; ++i) {
        const int written = snprintf(filename,sizeof(filename),"%s/%s",argv[4],names[i]);
        if (written < 0 || (size_t)written >= sizeof(filename)) { result = 2; goto done; }
        d24_files[i] = fopen(filename,"wb");
        if (!d24_files[i]) { result = 4; goto done; }
    }
    if (fprintf(d24_files[4],"frame,active,bank,streak,change,primary_energy,shadow_energy\n") < 0) { result = 4; goto done; }
    result = d24_fixture_main(argc-1,argv);
    if (!result && (d24_invalid || d24_primary_calls != 2000u || d24_shadow_calls != (d24_policy ? 1000u : 0u) ||
                    d24_reset_calls != (uint32_t)d24_policy)) result = 6;
done:
    for (i = 0u; i < 5u; ++i) if (d24_files[i] && fclose(d24_files[i])) result = 9;
    return result;
}
