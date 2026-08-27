#include "frontend/ap_frontend.h"
#include "dsp/ap_dsp.h"
#include <math.h>
#include <stdint.h>
#include <string.h>

void ap_hpf_init(ap_hpf_state_t *s,
                 uint32_t sample_rate_hz,
                 uint32_t channels) {
    memset(s, 0, sizeof(*s));
    s->r = expf(-2.0f * AP_PI * 80.0f / (float)sample_rate_hz);
    s->channels = channels;
}

void ap_hpf_process(ap_hpf_state_t *s,
                    float *x,
                    uint32_t n,
                    uint32_t ch) {
    uint32_t i;
    float px = s->x[ch], py = s->y[ch];
    for (i = 0u; i < n; ++i) {
        const float in = x[i];
        const float y = in - px + s->r * py;
        x[i] = y;
        px = in;
        py = y;
    }
    s->x[ch] = px;
    s->y[ch] = py;
}
