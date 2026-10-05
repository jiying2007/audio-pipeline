#include "array_native.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "line %d: %s\n", __LINE__, #x); return 1; } ++checks; } while (0)
static unsigned checks;
static fe_array_config config(uint32_t n) {
    fe_array_config c;
    uint32_t i;
    memset(&c, 0, sizeof(c));
    c.sample_rate_hz = 16000u; c.mic_count = n; c.active_mask = (1u << n) - 1u;
    c.interpolation = FE_ARRAY_LAGRANGE3; c.direction[1] = 1.0;
    for (i = 0u; i < n; ++i) {
        c.microphones[i].position_m[0] = 0.035 * (double)i;
        c.microphones[i].gain = 1.0; c.microphones[i].input_channel = i;
    }
    return c;
}
static int init_errors(void) {
    _Alignas(FE_ARRAY_ALIGNMENT) unsigned char a[4096], saved[4096];
    fe_array *s = NULL;
    fe_array_config c = config(4u), bad;
    uint32_t i;
    memset(a, 0x5a, sizeof(a)); memcpy(saved, a, sizeof(a));
    CHECK(fe_array_state_bytes(1u) < fe_array_state_bytes(2u));
    CHECK(fe_array_state_bytes(2u) < fe_array_state_bytes(4u));
    CHECK(fe_array_state_bytes(3u) == 0u);
    CHECK(fe_array_init(a, fe_array_state_bytes(4u)-1u, &c, &s) == FE_ARRAY_ENOMEM && s == NULL);
    CHECK(memcmp(saved, a, sizeof(a)) == 0);
    CHECK(fe_array_init(a+1u, sizeof(a)-1u, &c, &s) == FE_ARRAY_EINVAL);
    CHECK(fe_array_init(NULL, sizeof(a), &c, &s) == FE_ARRAY_EINVAL);
    CHECK(fe_array_init(a, sizeof(a), NULL, &s) == FE_ARRAY_EINVAL);
    CHECK(fe_array_init(a, sizeof(a), &c, NULL) == FE_ARRAY_EINVAL);
    CHECK(fe_array_init(a, sizeof(a), &c, (fe_array **)a) == FE_ARRAY_EINVAL);
    for (i = 0u; i < 20u; ++i) {
        bad = c;
        switch (i) {
        case 0: bad.mic_count = 0u; break;
        case 1: bad.mic_count = 3u; break;
        case 2: bad.mic_count = 5u; break;
        case 3: bad.sample_rate_hz = 44100u; break;
        case 4: bad.reference_mic = 4u; break;
        case 5: bad.active_mask = 0u; break;
        case 6: bad.active_mask = 16u; break;
        case 7: bad.microphones[1].input_channel = 0u; break;
        case 8: bad.microphones[1].input_channel = 4u; break;
        case 9: bad.direction[1] = 2.0; break;
        case 10: bad.direction[1] = NAN; break;
        case 11: bad.microphones[1].position_m[0] = INFINITY; break;
        case 12: bad.microphones[1].position_m[0] = 0.0; break;
        case 13: bad.microphones[1].gain = 0.0; break;
        case 14: bad.microphones[1].gain = NAN; break;
        case 15: bad.microphones[1].latency_samples = INFINITY; break;
        case 16: bad.microphones[1].latency_samples = 9.0; break;
        case 17: bad.interpolation = (fe_array_interpolation)3; break;
        case 18: bad.sample_rate_hz = 48000u; bad.microphones[1].position_m[0] = 1.0; break;
        default: bad.direction[1] = 0.0; break;
        }
        CHECK(fe_array_init(a, sizeof(a), &bad, &s) == FE_ARRAY_EINVAL && s == NULL);
        CHECK(memcmp(saved, a, sizeof(a)) == 0);
    }
    CHECK(fe_array_init(a, sizeof(a), &c, &s) == FE_ARRAY_OK);
    return 0;
}
static int process_contracts(void) {
    _Alignas(FE_ARRAY_ALIGNMENT) unsigned char a[4096], b[4096], before[4096];
    fe_array *s = NULL, *other = NULL;
    fe_array_config c = config(4u);
    fe_array_info info;
    float x[640], y[160], z[160], sentinel[160];
    size_t i;
    CHECK(fe_array_init(a, sizeof(a), &c, &s) == FE_ARRAY_OK);
    CHECK(fe_array_init(b, sizeof(b), &c, &other) == FE_ARRAY_OK);
    for (i = 0u; i < 640u; ++i) x[i] = (float)((int)(i % 79u)-39) / 100.0f;
    for (i = 0u; i < 160u; ++i) y[i] = sentinel[i] = -0.123f;
    memcpy(before, a, sizeof(a));
    CHECK(fe_array_process(NULL, x, 640u, y, 160u) == FE_ARRAY_ESTATE);
    CHECK(fe_array_process(s, x, 639u, y, 160u) == FE_ARRAY_EINVAL);
    CHECK(fe_array_process(s, x, 644u, y, 161u) == FE_ARRAY_EINVAL);
    CHECK(fe_array_process(s, x, 640u, y, 159u) == FE_ARRAY_EINVAL);
    CHECK(fe_array_process(s, x, 0u, y, 0u) == FE_ARRAY_EINVAL);
    CHECK(fe_array_process(s, x, 640u, x, 160u) == FE_ARRAY_EINVAL);
    CHECK(fe_array_process(s, x, 640u, (float *)a, 160u) == FE_ARRAY_EINVAL);
    CHECK(fe_array_process(s, (float *)a, 640u, y, 160u) == FE_ARRAY_EINVAL);
    x[639] = NAN;
    CHECK(fe_array_process(s, x, 640u, y, 160u) == FE_ARRAY_EINVAL);
    CHECK(memcmp(a, before, sizeof(a)) == 0 && memcmp(y, sentinel, sizeof(y)) == 0);
    x[639] = 1.01f;
    CHECK(fe_array_process(s, x, 640u, y, 160u) == FE_ARRAY_EINVAL);
    x[639] = -INFINITY;
    CHECK(fe_array_process(s, x, 640u, y, 160u) == FE_ARRAY_EINVAL);
    x[639] = 0.25f;
    CHECK(fe_array_process(s, x, 640u, y, 160u) == FE_ARRAY_OK);
    CHECK(fe_array_process(other, x, 4u*17u, z, 17u) == FE_ARRAY_OK);
    CHECK(fe_array_process(other, x+4u*17u, 4u*143u, z+17u, 143u) == FE_ARRAY_OK);
    CHECK(memcmp(y, z, sizeof(y)) == 0);
    CHECK(fe_array_get_info(s, &info) == FE_ARRAY_OK && info.samples_processed == 160u);
    CHECK(fe_array_get_info(s, (fe_array_info *)a) == FE_ARRAY_EINVAL);
    CHECK(fe_array_reset(s) == FE_ARRAY_OK);
    CHECK(fe_array_process(s, x, 640u, z, 160u) == FE_ARRAY_OK && memcmp(y, z, sizeof(y)) == 0);
    memcpy(before, a, sizeof(a));
    CHECK(fe_array_set_active_mask(s, 0u) == FE_ARRAY_EINVAL);
    CHECK(fe_array_set_active_mask(s, 31u) == FE_ARRAY_EINVAL);
    CHECK(memcmp(before, a, sizeof(a)) == 0);
    CHECK(fe_array_set_active_mask(s, 7u) == FE_ARRAY_OK);
    x[639] = NAN; /* Masked fourth microphone cannot contaminate output/history. */
    CHECK(fe_array_process(s, x, 640u, y, 160u) == FE_ARRAY_OK);
    CHECK(fe_array_get_info(s, &info) == FE_ARRAY_OK && info.active_mask == 7u && info.common_delay_samples == 6u);
    CHECK(fe_array_set_active_mask(s, 15u) == FE_ARRAY_OK);
    CHECK(fe_array_process(s, x, 640u, y, 160u) == FE_ARRAY_EINVAL);
    x[639] = 0.25f;
    CHECK(fe_array_process(s, x, 640u, y, 160u) == FE_ARRAY_OK);
    for (i = 0u; i < 160u; ++i) CHECK(isfinite(y[i]));
    return 0;
}
static int geometry_and_stream(void) {
    _Alignas(FE_ARRAY_ALIGNMENT) unsigned char a[4096], b[4096];
    const uint32_t ns[] = {1u, 2u, 4u}, rates[] = {8000u,16000u,24000u,32000u,48000u};
    size_t ni, ri, f, t;
    uint32_t mode, m;
    for (ni = 0u; ni < 3u; ++ni) for (ri = 0u; ri < 5u; ++ri) for (mode = 0u; mode < 2u; ++mode) {
        fe_array_config c = config(ns[ni]);
        fe_array *s = NULL, *other = NULL;
        fe_array_info info;
        float x[1920], y[480], z[480];
        c.sample_rate_hz = rates[ri]; c.interpolation = (fe_array_interpolation)mode;
        CHECK(fe_array_init(a, sizeof(a), &c, &s) == FE_ARRAY_OK);
        CHECK(fe_array_init(b, sizeof(b), &c, &other) == FE_ARRAY_OK);
        CHECK(fe_array_get_info(s, &info) == FE_ARRAY_OK);
        for (f = 0u; f < 10u; ++f) {
            const size_t hop = rates[ri]/100u;
            for (t = 0u; t < hop; ++t) for (m = 0u; m < c.mic_count; ++m)
                x[t*c.mic_count+m] = (float)((int)((f*hop+t)%101u)-50)/100.0f;
            CHECK(fe_array_process(s, x, hop*c.mic_count, y, hop) == FE_ARRAY_OK);
            for (t = 0u; t < hop; ++t) CHECK(fe_array_process(other, x+t*c.mic_count, c.mic_count, z+t, 1u) == FE_ARRAY_OK);
            CHECK(memcmp(y,z,hop*sizeof(float)) == 0);
            for (t = 0u; t < hop; ++t) {
                const size_t at = f*hop+t;
                const float expected = at < info.common_delay_samples ? 0.0f :
                    (float)((int)((at-info.common_delay_samples)%101u)-50)/100.0f;
                CHECK(fabsf(y[t]-expected)<1.0e-6f);
            }
        }
    }
    return 0;
}
static int calibration_polynomial(void) {
    _Alignas(FE_ARRAY_ALIGNMENT) unsigned char a[4096];
    fe_array_config c = config(4u);
    fe_array *s = NULL;
    fe_array_info info;
    float x[640], y[160];
    size_t i;
    uint32_t m;
    c.direction[0] = 0.6; c.direction[1] = 0.8;
    for (m=0u;m<4u;++m) {
        c.microphones[m].input_channel=3u-m;
        c.microphones[m].gain = m==1u ? -2.0 : 2.0;
        c.microphones[m].latency_samples = 0.25*(double)m;
    }
    CHECK(fe_array_init(a,sizeof(a),&c,&s)==FE_ARRAY_OK);
    CHECK(fe_array_get_info(s,&info)==FE_ARRAY_OK);
    for (i=0u;i<160u;++i) for(m=0u;m<4u;++m) {
        const double advance=c.microphones[m].position_m[0]*0.6*16000.0/343.0-c.microphones[m].latency_samples;
        const double t=((double)i+advance)/1000.0;
        x[i*4u+c.microphones[m].input_channel]=(float)((0.2+t+t*t+t*t*t)/c.microphones[m].gain);
    }
    CHECK(fe_array_process(s,x,640u,y,160u)==FE_ARRAY_OK);
    for(i=24u;i<160u;++i) {
        const double t=((double)i-(double)info.common_delay_samples)/1000.0;
        CHECK(fabs((double)y[i]-(0.2+t+t*t+t*t*t))<1.0e-6);
    }
    return 0;
}
static int repeated_lifecycles(void) {
    _Alignas(FE_ARRAY_ALIGNMENT) unsigned char a[4096];
    fe_array_config c=config(4u);
    float x[640], y[160], previous[160];
    uint32_t cycle, frame, i;
    fe_array *s=NULL;
    for(i=0u;i<640u;++i)x[i]=(float)((int)(i%61u)-30)/100.0f;
    for(cycle=0u;cycle<64u;++cycle){
        CHECK(fe_array_init(a,sizeof(a),&c,&s)==FE_ARRAY_OK);
        for(frame=0u;frame<1000u;++frame){
            CHECK(fe_array_process(s,x,640u,y,160u)==FE_ARRAY_OK);
            if(frame==999u){
                if(cycle>0u) CHECK(memcmp(y,previous,sizeof(y))==0);
                memcpy(previous,y,sizeof(y));
            }
        }
    }
    return 0;
}
int main(void) {
    if(init_errors() || process_contracts() || geometry_and_stream() || calibration_polynomial() || repeated_lifecycles())return 1;
    printf("{\"status\":\"PASS\",\"assertions\":%u,\"stress_frames\":64000,\"lifecycles\":64,\"state_bytes\":[%zu,%zu,%zu]}\n",
        checks,fe_array_state_bytes(1u),fe_array_state_bytes(2u),fe_array_state_bytes(4u));
    return 0;
}
