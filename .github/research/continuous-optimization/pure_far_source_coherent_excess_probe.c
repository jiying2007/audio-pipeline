#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

typedef struct complex64 { double re, im; } complex64_t;
typedef struct wav_data { int16_t *samples; size_t count; uint32_t sample_rate; } wav_data_t;

typedef struct stats {
    size_t fft_size, segment_count, analyzed_samples, start_sample, end_sample, valid_bins;
    double total_mic_render_ratio;
    double mic_energy_weighted_coherence;
    double coherent_mic_render_ratio;
    double incoherent_excess_mic_render_ratio;
    double unweighted_mean_coherence;
} stats_t;

static uint16_t le16(const unsigned char *p) { return (uint16_t)p[0] | ((uint16_t)p[1] << 8); }
static uint32_t le32(const unsigned char *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static int read_exact(FILE *f, void *dst, size_t n) { return fread(dst, 1u, n, f) == n; }
static int skip_bytes(FILE *f, uint32_t n) {
    unsigned char buf[4096];
    while (n) {
        size_t chunk = n < sizeof(buf) ? (size_t)n : sizeof(buf);
        if (fread(buf, 1u, chunk, f) != chunk) return 0;
        n -= (uint32_t)chunk;
    }
    return 1;
}
static int load_wav(const char *path, wav_data_t *out) {
    FILE *f = fopen(path, "rb");
    unsigned char hdr[12];
    uint16_t format = 0u, channels = 0u, bits = 0u;
    uint32_t rate = 0u;
    int have_fmt = 0, have_data = 0;
    int16_t *samples = NULL;
    size_t count = 0u;
    memset(out, 0, sizeof(*out));
    if (!f) return 0;
    if (!read_exact(f, hdr, sizeof(hdr)) || memcmp(hdr, "RIFF", 4u) || memcmp(hdr + 8u, "WAVE", 4u)) goto fail;
    while (!have_data) {
        unsigned char ch[8];
        uint32_t size;
        if (!read_exact(f, ch, sizeof(ch))) break;
        size = le32(ch + 4u);
        if (!memcmp(ch, "fmt ", 4u)) {
            unsigned char fmt[16];
            if (size < sizeof(fmt) || !read_exact(f, fmt, sizeof(fmt))) goto fail;
            format = le16(fmt); channels = le16(fmt + 2u); rate = le32(fmt + 4u); bits = le16(fmt + 14u);
            if (size > sizeof(fmt) && !skip_bytes(f, size - (uint32_t)sizeof(fmt))) goto fail;
            have_fmt = 1;
        } else if (!memcmp(ch, "data", 4u)) {
            unsigned char *raw;
            size_t i;
            if (!have_fmt || format != 1u || channels != 1u || bits != 16u || rate == 0u || (size & 1u)) goto fail;
            raw = (unsigned char *)malloc(size ? size : 1u);
            if (!raw || !read_exact(f, raw, size)) { free(raw); goto fail; }
            count = size / 2u;
            samples = (int16_t *)malloc(count * sizeof(*samples));
            if (!samples) { free(raw); goto fail; }
            for (i = 0u; i < count; ++i) samples[i] = (int16_t)le16(raw + 2u * i);
            free(raw); have_data = 1;
        } else if (!skip_bytes(f, size)) goto fail;
        if (size & 1u) { unsigned char pad; if (!read_exact(f, &pad, 1u)) goto fail; }
    }
    if (!have_fmt || !have_data || !samples || !count) goto fail;
    fclose(f); out->samples = samples; out->count = count; out->sample_rate = rate; return 1;
fail:
    if (f) fclose(f); free(samples); return 0;
}
static void free_wav(wav_data_t *w) { free(w->samples); memset(w, 0, sizeof(*w)); }
static size_t next_pow2(size_t v) {
    size_t r = 1u;
    while (r < v) { if (r > (SIZE_MAX >> 1u)) return 0u; r <<= 1u; }
    return r;
}
static void fft(complex64_t *a, size_t n) {
    size_t i, j, len;
    for (i = 1u, j = 0u; i < n; ++i) {
        size_t bit = n >> 1u;
        for (; j & bit; bit >>= 1u) j ^= bit;
        j ^= bit;
        if (i < j) { complex64_t t = a[i]; a[i] = a[j]; a[j] = t; }
    }
    for (len = 2u; len <= n; len <<= 1u) {
        const double ang = -2.0 * M_PI / (double)len;
        const double wr = cos(ang), wi = sin(ang);
        size_t base;
        for (base = 0u; base < n; base += len) {
            double ur = 1.0, ui = 0.0; size_t k;
            for (k = 0u; k < len / 2u; ++k) {
                complex64_t e = a[base + k], o = a[base + k + len / 2u];
                double vr = o.re * ur - o.im * ui, vi = o.re * ui + o.im * ur;
                double nur = ur * wr - ui * wi, nui = ur * wi + ui * wr;
                a[base + k].re = e.re + vr; a[base + k].im = e.im + vi;
                a[base + k + len / 2u].re = e.re - vr; a[base + k + len / 2u].im = e.im - vi;
                ur = nur; ui = nui;
            }
        }
    }
}
static int analyze(const wav_data_t *mic, const wav_data_t *render, size_t delay, size_t tail, stats_t *out) {
    size_t fft_size = next_pow2(2u * tail), bins, common, start, end, segments, s, k, valid = 0u;
    double *sxx = NULL, *syy = NULL, *xyre = NULL, *xyim = NULL;
    complex64_t *x = NULL, *y = NULL;
    double mic_energy = 0.0, render_energy = 0.0, coherent_mic = 0.0, unweighted = 0.0;
    memset(out, 0, sizeof(*out));
    if (!fft_size || fft_size < tail) return 0;
    common = mic->count < render->count ? mic->count : render->count;
    start = delay; end = common;
    if (end <= start) return 0;
    segments = (end - start) / fft_size;
    if (segments < 4u) return 0;
    bins = fft_size / 2u + 1u;
    sxx = (double *)calloc(bins, sizeof(*sxx)); syy = (double *)calloc(bins, sizeof(*syy));
    xyre = (double *)calloc(bins, sizeof(*xyre)); xyim = (double *)calloc(bins, sizeof(*xyim));
    x = (complex64_t *)calloc(fft_size, sizeof(*x)); y = (complex64_t *)calloc(fft_size, sizeof(*y));
    if (!sxx || !syy || !xyre || !xyim || !x || !y) goto fail;
    for (s = 0u; s < segments; ++s) {
        size_t base = start + s * fft_size;
        for (k = 0u; k < fft_size; ++k) {
            x[k].re = (double)render->samples[base + k - delay] / 32768.0; x[k].im = 0.0;
            y[k].re = (double)mic->samples[base + k] / 32768.0; y[k].im = 0.0;
        }
        fft(x, fft_size); fft(y, fft_size);
        for (k = 0u; k < bins; ++k) {
            double xr=x[k].re, xi=x[k].im, yr=y[k].re, yi=y[k].im;
            sxx[k] += xr*xr + xi*xi; syy[k] += yr*yr + yi*yi;
            xyre[k] += xr*yr + xi*yi; xyim[k] += xr*yi - xi*yr;
        }
    }
    for (k = 0u; k < bins; ++k) {
        double coh, weight = (k == 0u || k + 1u == bins) ? 1.0 : 2.0;
        if (!(sxx[k] > 0.0) || !(syy[k] > 0.0)) continue;
        coh = (xyre[k]*xyre[k] + xyim[k]*xyim[k]) / (sxx[k]*syy[k]);
        if (coh < 0.0) coh = 0.0; if (coh > 1.0) coh = 1.0;
        render_energy += weight * sxx[k]; mic_energy += weight * syy[k];
        coherent_mic += weight * coh * syy[k]; unweighted += coh; valid++;
    }
    if (!valid || !(render_energy > 0.0) || !(mic_energy > 0.0)) goto fail;
    out->fft_size = fft_size; out->segment_count = segments; out->analyzed_samples = segments * fft_size;
    out->start_sample = start; out->end_sample = start + out->analyzed_samples; out->valid_bins = valid;
    out->total_mic_render_ratio = mic_energy / render_energy;
    out->mic_energy_weighted_coherence = coherent_mic / mic_energy;
    out->coherent_mic_render_ratio = coherent_mic / render_energy;
    out->incoherent_excess_mic_render_ratio = (mic_energy - coherent_mic) / render_energy;
    out->unweighted_mean_coherence = unweighted / (double)valid;
    free(sxx); free(syy); free(xyre); free(xyim); free(x); free(y); return 1;
fail:
    free(sxx); free(syy); free(xyre); free(xyim); free(x); free(y); return 0;
}
static int parse_size(const char *t, size_t *v) {
    char *e = NULL; unsigned long long p; errno = 0; p = strtoull(t, &e, 10);
    if (errno || !e || *e || p > (unsigned long long)SIZE_MAX) return 0; *v = (size_t)p; return 1;
}
static int self_test(void) {
    size_t n = 131072u, i; wav_data_t r={0}, m={0}; stats_t s; uint32_t st=17u;
    r.samples=(int16_t *)malloc(n*sizeof(int16_t)); m.samples=(int16_t *)malloc(n*sizeof(int16_t));
    if (!r.samples || !m.samples) goto fail; r.count=m.count=n; r.sample_rate=m.sample_rate=48000u;
    for (i=0u;i<n;++i) { st=st*1664525u+1013904223u; r.samples[i]=(int16_t)(((int32_t)((st>>16u)&0xffffu)-32768)/3); m.samples[i]=(int16_t)((int32_t)r.samples[i]/2); }
    if (!analyze(&m,&r,0u,4608u,&s)) goto fail;
    if (!(s.mic_energy_weighted_coherence > 0.999999 && s.incoherent_excess_mic_render_ratio < 1e-6)) goto fail;
    free_wav(&r); free_wav(&m); puts("pure-far source coherent-excess probe self-test: OK"); return 0;
fail:
    free_wav(&r); free_wav(&m); fputs("pure-far source coherent-excess probe self-test: FAILED\n",stderr); return 2;
}
int main(int argc, char **argv) {
    wav_data_t mic={0}, render={0}; stats_t s; size_t delay, tail; FILE *f;
    if (argc==2 && !strcmp(argv[1],"--self-test")) return self_test();
    if (argc!=6 || !parse_size(argv[3],&delay) || !parse_size(argv[4],&tail) || !tail) return 2;
    if (!load_wav(argv[1],&mic) || !load_wav(argv[2],&render)) goto fail;
    if (mic.sample_rate != 48000u || render.sample_rate != 48000u) goto fail;
    if (!analyze(&mic,&render,delay,tail,&s)) goto fail;
    f=fopen(argv[5],"wb"); if(!f) goto fail;
    fprintf(f,"{\"schema_version\":1,\"diagnostic_only\":true,\"sample_rate_hz\":48000,\"delay_samples\":%zu,\"tail_samples\":%zu,\"tail_ms\":%.17g,\"fft_size\":%zu,\"fft_rule\":\"next_power_of_two(2*tail_samples)\",\"window\":\"rectangular\",\"overlap_samples\":0,\"segment_count\":%zu,\"analyzed_samples\":%zu,\"start_sample\":%zu,\"end_sample\":%zu,\"valid_bins\":%zu,\"total_mic_render_ratio\":%.17g,\"mic_energy_weighted_coherence\":%.17g,\"coherent_mic_render_ratio\":%.17g,\"incoherent_excess_mic_render_ratio\":%.17g,\"unweighted_mean_coherence\":%.17g,\"signal_correction_applied\":false,\"acoustic_threshold_used\":false}\n",delay,tail,1000.0*(double)tail/48000.0,s.fft_size,s.segment_count,s.analyzed_samples,s.start_sample,s.end_sample,s.valid_bins,s.total_mic_render_ratio,s.mic_energy_weighted_coherence,s.coherent_mic_render_ratio,s.incoherent_excess_mic_render_ratio,s.unweighted_mean_coherence);
    fclose(f); free_wav(&mic); free_wav(&render); return 0;
fail:
    free_wav(&mic); free_wav(&render); fputs("source coherent-excess analysis failed\n",stderr); return 2;
}
