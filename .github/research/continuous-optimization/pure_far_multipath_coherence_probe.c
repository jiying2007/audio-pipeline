#include <errno.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

typedef struct complex64 {
    double re;
    double im;
} complex64_t;

typedef struct wav_data {
    int16_t *samples;
    size_t count;
    uint32_t sample_rate;
} wav_data_t;

typedef struct coherence_stats {
    size_t fft_size;
    size_t segment_count;
    size_t analyzed_samples;
    size_t start_sample;
    size_t end_sample;
    size_t valid_bins;
    double mic_energy_weighted;
    double render_energy_weighted;
    double unweighted_mean;
    double p25;
    double median;
    double p75;
} coherence_stats_t;

static uint16_t read_le16(const unsigned char *p) {
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

static uint32_t read_le32(const unsigned char *p) {
    return (uint32_t)p[0] |
           ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static int read_exact(FILE *f, void *dst, size_t bytes) {
    return fread(dst, 1u, bytes, f) == bytes;
}

static int skip_bytes(FILE *f, uint32_t bytes) {
    unsigned char scratch[4096];
    uint32_t left = bytes;
    while (left > 0u) {
        const size_t chunk = left < sizeof(scratch) ? (size_t)left : sizeof(scratch);
        if (fread(scratch, 1u, chunk, f) != chunk) return 0;
        left -= (uint32_t)chunk;
    }
    return 1;
}

static int load_wav_mono16(const char *path, wav_data_t *out) {
    FILE *f = NULL;
    unsigned char header[12];
    uint16_t format = 0u, channels = 0u, bits = 0u;
    uint32_t sample_rate = 0u;
    int have_fmt = 0;
    int have_data = 0;
    int16_t *samples = NULL;
    size_t sample_count = 0u;

    memset(out, 0, sizeof(*out));
    f = fopen(path, "rb");
    if (!f) return 0;
    if (!read_exact(f, header, sizeof(header)) ||
        memcmp(header, "RIFF", 4u) != 0 || memcmp(header + 8u, "WAVE", 4u) != 0)
        goto fail;

    while (!have_data) {
        unsigned char chunk_header[8];
        uint32_t chunk_size;
        if (!read_exact(f, chunk_header, sizeof(chunk_header))) break;
        chunk_size = read_le32(chunk_header + 4u);
        if (memcmp(chunk_header, "fmt ", 4u) == 0) {
            unsigned char fmt[16];
            if (chunk_size < sizeof(fmt) || !read_exact(f, fmt, sizeof(fmt))) goto fail;
            format = read_le16(fmt + 0u);
            channels = read_le16(fmt + 2u);
            sample_rate = read_le32(fmt + 4u);
            bits = read_le16(fmt + 14u);
            if (chunk_size > sizeof(fmt) && !skip_bytes(f, chunk_size - (uint32_t)sizeof(fmt))) goto fail;
            have_fmt = 1;
        } else if (memcmp(chunk_header, "data", 4u) == 0) {
            unsigned char *raw;
            size_t i;
            if (!have_fmt || format != 1u || channels != 1u || bits != 16u ||
                sample_rate == 0u || (chunk_size & 1u) != 0u)
                goto fail;
            raw = (unsigned char *)malloc(chunk_size ? chunk_size : 1u);
            if (!raw || !read_exact(f, raw, chunk_size)) {
                free(raw);
                goto fail;
            }
            sample_count = chunk_size / 2u;
            samples = (int16_t *)malloc(sample_count * sizeof(*samples));
            if (!samples) {
                free(raw);
                goto fail;
            }
            for (i = 0u; i < sample_count; ++i)
                samples[i] = (int16_t)read_le16(raw + 2u * i);
            free(raw);
            have_data = 1;
        } else {
            if (!skip_bytes(f, chunk_size)) goto fail;
        }
        if ((chunk_size & 1u) != 0u) {
            unsigned char pad;
            if (!read_exact(f, &pad, 1u)) goto fail;
        }
    }

    if (!have_fmt || !have_data || !samples || sample_count == 0u) goto fail;
    fclose(f);
    out->samples = samples;
    out->count = sample_count;
    out->sample_rate = sample_rate;
    return 1;

fail:
    if (f) fclose(f);
    free(samples);
    return 0;
}

static void free_wav(wav_data_t *wav) {
    free(wav->samples);
    memset(wav, 0, sizeof(*wav));
}

static size_t next_power_of_two(size_t value) {
    size_t result = 1u;
    while (result < value) {
        if (result > (SIZE_MAX >> 1u)) return 0u;
        result <<= 1u;
    }
    return result;
}

static void fft(complex64_t *a, size_t n, int inverse) {
    size_t i, j, len;
    for (i = 1u, j = 0u; i < n; ++i) {
        size_t bit = n >> 1u;
        for (; j & bit; bit >>= 1u) j ^= bit;
        j ^= bit;
        if (i < j) {
            const complex64_t tmp = a[i];
            a[i] = a[j];
            a[j] = tmp;
        }
    }
    for (len = 2u; len <= n; len <<= 1u) {
        const double angle = (inverse ? 2.0 : -2.0) * M_PI / (double)len;
        const double wr = cos(angle);
        const double wi = sin(angle);
        size_t base;
        for (base = 0u; base < n; base += len) {
            double ur = 1.0, ui = 0.0;
            size_t k;
            for (k = 0u; k < len / 2u; ++k) {
                const complex64_t even = a[base + k];
                const complex64_t odd = a[base + k + len / 2u];
                const double vr = odd.re * ur - odd.im * ui;
                const double vi = odd.re * ui + odd.im * ur;
                const double next_ur = ur * wr - ui * wi;
                const double next_ui = ur * wi + ui * wr;
                a[base + k].re = even.re + vr;
                a[base + k].im = even.im + vi;
                a[base + k + len / 2u].re = even.re - vr;
                a[base + k + len / 2u].im = even.im - vi;
                ur = next_ur;
                ui = next_ui;
            }
        }
    }
    if (inverse) {
        for (i = 0u; i < n; ++i) {
            a[i].re /= (double)n;
            a[i].im /= (double)n;
        }
    }
}

static int compare_double(const void *a, const void *b) {
    const double da = *(const double *)a;
    const double db = *(const double *)b;
    return (da > db) - (da < db);
}

static double percentile_sorted(const double *values, size_t count, double q) {
    const double pos = (double)(count - 1u) * q;
    const size_t lo = (size_t)floor(pos);
    const size_t hi = (size_t)ceil(pos);
    if (lo == hi) return values[lo];
    return values[lo] * ((double)hi - pos) + values[hi] * (pos - (double)lo);
}

static int analyze_range(const wav_data_t *mic,
                         const wav_data_t *render,
                         size_t delay,
                         size_t start,
                         size_t end,
                         size_t fft_size,
                         coherence_stats_t *out) {
    const size_t bins = fft_size / 2u + 1u;
    double *sxx = NULL, *syy = NULL, *sxy_re = NULL, *sxy_im = NULL, *coh = NULL;
    complex64_t *x = NULL, *y = NULL;
    size_t segment_count, segment, k, valid = 0u;
    double mic_weighted_num = 0.0, mic_weighted_den = 0.0;
    double render_weighted_num = 0.0, render_weighted_den = 0.0;
    double unweighted_sum = 0.0;

    memset(out, 0, sizeof(*out));
    if (start < delay) start = delay;
    if (end > mic->count) end = mic->count;
    if (end > render->count + delay) end = render->count + delay;
    if (end <= start) return 0;
    segment_count = (end - start) / fft_size;
    if (segment_count < 2u) return 0;

    sxx = (double *)calloc(bins, sizeof(*sxx));
    syy = (double *)calloc(bins, sizeof(*syy));
    sxy_re = (double *)calloc(bins, sizeof(*sxy_re));
    sxy_im = (double *)calloc(bins, sizeof(*sxy_im));
    coh = (double *)malloc(bins * sizeof(*coh));
    x = (complex64_t *)calloc(fft_size, sizeof(*x));
    y = (complex64_t *)calloc(fft_size, sizeof(*y));
    if (!sxx || !syy || !sxy_re || !sxy_im || !coh || !x || !y) goto fail;

    for (segment = 0u; segment < segment_count; ++segment) {
        const size_t base = start + segment * fft_size;
        for (k = 0u; k < fft_size; ++k) {
            x[k].re = (double)render->samples[base + k - delay] / 32768.0;
            x[k].im = 0.0;
            y[k].re = (double)mic->samples[base + k] / 32768.0;
            y[k].im = 0.0;
        }
        fft(x, fft_size, 0);
        fft(y, fft_size, 0);
        for (k = 0u; k < bins; ++k) {
            const double xr = x[k].re, xi = x[k].im;
            const double yr = y[k].re, yi = y[k].im;
            sxx[k] += xr * xr + xi * xi;
            syy[k] += yr * yr + yi * yi;
            sxy_re[k] += xr * yr + xi * yi;
            sxy_im[k] += xr * yi - xi * yr;
        }
    }

    for (k = 0u; k < bins; ++k) {
        double c;
        if (!(sxx[k] > 0.0) || !(syy[k] > 0.0)) continue;
        c = (sxy_re[k] * sxy_re[k] + sxy_im[k] * sxy_im[k]) / (sxx[k] * syy[k]);
        if (c < 0.0) c = 0.0;
        if (c > 1.0) c = 1.0;
        coh[valid++] = c;
        unweighted_sum += c;
        mic_weighted_num += c * syy[k];
        mic_weighted_den += syy[k];
        render_weighted_num += c * sxx[k];
        render_weighted_den += sxx[k];
    }
    if (valid == 0u || !(mic_weighted_den > 0.0) || !(render_weighted_den > 0.0)) goto fail;
    qsort(coh, valid, sizeof(*coh), compare_double);
    out->fft_size = fft_size;
    out->segment_count = segment_count;
    out->analyzed_samples = segment_count * fft_size;
    out->start_sample = start;
    out->end_sample = start + out->analyzed_samples;
    out->valid_bins = valid;
    out->mic_energy_weighted = mic_weighted_num / mic_weighted_den;
    out->render_energy_weighted = render_weighted_num / render_weighted_den;
    out->unweighted_mean = unweighted_sum / (double)valid;
    out->p25 = percentile_sorted(coh, valid, 0.25);
    out->median = percentile_sorted(coh, valid, 0.50);
    out->p75 = percentile_sorted(coh, valid, 0.75);

    free(sxx); free(syy); free(sxy_re); free(sxy_im); free(coh); free(x); free(y);
    return 1;

fail:
    free(sxx); free(syy); free(sxy_re); free(sxy_im); free(coh); free(x); free(y);
    return 0;
}

static void write_stats(FILE *f, const char *name, const coherence_stats_t *s, int trailing_comma) {
    fprintf(f,
            "\"%s\":{\"fft_size\":%zu,\"segment_count\":%zu,\"analyzed_samples\":%zu,"
            "\"start_sample\":%zu,\"end_sample\":%zu,\"valid_bins\":%zu,"
            "\"mic_energy_weighted_coherence\":%.17g,"
            "\"render_energy_weighted_coherence\":%.17g,"
            "\"unweighted_mean_coherence\":%.17g,"
            "\"coherence_p25\":%.17g,\"coherence_median\":%.17g,\"coherence_p75\":%.17g}%s",
            name, s->fft_size, s->segment_count, s->analyzed_samples,
            s->start_sample, s->end_sample, s->valid_bins,
            s->mic_energy_weighted, s->render_energy_weighted, s->unweighted_mean,
            s->p25, s->median, s->p75, trailing_comma ? "," : "");
}

static int parse_size(const char *text, size_t *value) {
    char *end = NULL;
    unsigned long long parsed;
    errno = 0;
    parsed = strtoull(text, &end, 10);
    if (errno || !end || *end != '\0' || parsed > (unsigned long long)SIZE_MAX) return 0;
    *value = (size_t)parsed;
    return 1;
}

static int run_self_test(void) {
    const size_t n = 32768u;
    wav_data_t render, mic;
    coherence_stats_t stats;
    uint32_t state = 7u;
    size_t i;
    memset(&render, 0, sizeof(render));
    memset(&mic, 0, sizeof(mic));
    render.samples = (int16_t *)malloc(n * sizeof(int16_t));
    mic.samples = (int16_t *)malloc(n * sizeof(int16_t));
    if (!render.samples || !mic.samples) goto fail;
    render.count = mic.count = n;
    render.sample_rate = mic.sample_rate = 16000u;
    for (i = 0u; i < n; ++i) {
        int32_t sample;
        state = state * 1664525u + 1013904223u;
        sample = (int32_t)((state >> 16u) & 0xffffu) - 32768;
        render.samples[i] = (int16_t)(sample / 2);
    }
    for (i = 0u; i < n; ++i) mic.samples[i] = (int16_t)((int32_t)render.samples[i] / 2);
    if (!analyze_range(&mic, &render, 0u, 0u, n, 4096u, &stats)) goto fail;
    if (!(stats.mic_energy_weighted > 0.999999 &&
          stats.render_energy_weighted > 0.999999 &&
          stats.unweighted_mean > 0.999999)) goto fail;
    free_wav(&render); free_wav(&mic);
    puts("pure-far multipath coherence probe self-test: OK");
    return 0;
fail:
    free_wav(&render); free_wav(&mic);
    fputs("pure-far multipath coherence probe self-test: FAILED\n", stderr);
    return 2;
}

int main(int argc, char **argv) {
    wav_data_t mic, render;
    coherence_stats_t full, first, second;
    size_t delay, tail, fft_size, common, rating_start, aligned_start, aligned_end, split;
    FILE *out = NULL;

    if (argc == 2 && strcmp(argv[1], "--self-test") == 0) return run_self_test();
    if (argc != 6) {
        fprintf(stderr, "usage: %s <mic.wav> <render.wav> <delay_samples> <tail_samples> <output.json>\n", argv[0]);
        return 2;
    }
    if (!parse_size(argv[3], &delay) || !parse_size(argv[4], &tail) || tail == 0u) return 2;
    fft_size = next_power_of_two(2u * tail);
    if (fft_size == 0u || fft_size < tail) return 2;
    if (!load_wav_mono16(argv[1], &mic) || !load_wav_mono16(argv[2], &render)) {
        free_wav(&mic); free_wav(&render);
        fputs("failed to read mono PCM16 WAV inputs\n", stderr);
        return 2;
    }
    if (mic.sample_rate != render.sample_rate || mic.sample_rate != 16000u) {
        free_wav(&mic); free_wav(&render);
        fputs("16 kHz matched-rate inputs required\n", stderr);
        return 2;
    }
    common = mic.count < render.count ? mic.count : render.count;
    rating_start = common - common / 2u;
    aligned_start = rating_start > delay ? rating_start : delay;
    aligned_end = common;
    if (aligned_end <= aligned_start || aligned_end - aligned_start < 4u * fft_size) {
        free_wav(&mic); free_wav(&render);
        fputs("official rating interval too short for fixed coherence geometry\n", stderr);
        return 2;
    }
    split = aligned_start + (aligned_end - aligned_start) / 2u;
    if (!analyze_range(&mic, &render, delay, aligned_start, aligned_end, fft_size, &full) ||
        !analyze_range(&mic, &render, delay, aligned_start, split, fft_size, &first) ||
        !analyze_range(&mic, &render, delay, split, aligned_end, fft_size, &second)) {
        free_wav(&mic); free_wav(&render);
        fputs("coherence analysis failed\n", stderr);
        return 2;
    }

    out = fopen(argv[5], "wb");
    if (!out) {
        free_wav(&mic); free_wav(&render);
        perror("fopen");
        return 2;
    }
    fprintf(out,
            "{\"schema_version\":1,\"diagnostic_only\":true,\"sample_rate_hz\":%u,"
            "\"delay_samples\":%zu,\"tail_samples\":%zu,\"tail_ms\":%.17g,"
            "\"fft_rule\":\"next_power_of_two(2*tail_samples)\","
            "\"window\":\"rectangular\",\"overlap_samples\":0,"
            "\"all_frequency_bins_used\":true,\"acoustic_threshold_used\":false,",
            mic.sample_rate, delay, tail, 1000.0 * (double)tail / (double)mic.sample_rate);
    write_stats(out, "official_rating", &full, 1);
    write_stats(out, "first_half", &first, 1);
    write_stats(out, "second_half", &second, 1);
    fprintf(out,
            "\"split_half_delta\":{"
            "\"mic_energy_weighted_coherence_abs_delta\":%.17g,"
            "\"render_energy_weighted_coherence_abs_delta\":%.17g,"
            "\"unweighted_mean_coherence_abs_delta\":%.17g}}\n",
            fabs(first.mic_energy_weighted - second.mic_energy_weighted),
            fabs(first.render_energy_weighted - second.render_energy_weighted),
            fabs(first.unweighted_mean - second.unweighted_mean));
    fclose(out);
    free_wav(&mic); free_wav(&render);
    return 0;
}
