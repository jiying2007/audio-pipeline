/* Research host adapter. The linked fir_generic.c and FIR coefficients are
 * pristine SOF bytes. This transport and Q5.27 mixer are first-party, not a
 * complete SOF firmware/testbench or shipping component benchmark. */
#define _POSIX_C_SOURCE 200809L
#include <sof/math/fir_generic.h>
#include <user/fir.h>
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

_Static_assert(sizeof(int32_t) == 4 && sizeof(int16_t) == 2, "fixed width required");
_Static_assert((-1 >> 1) == -1, "SOF generic FIR requires arithmetic signed right shift");

static int get_s16(FILE *file, int16_t *value) {
    unsigned char bytes[2];
    if (fread(bytes, 1, 2, file) != 2) return 0;
    unsigned n = (unsigned)bytes[0] | ((unsigned)bytes[1] << 8);
    *value = (int16_t)(n >= 32768 ? (int)n - 65536 : (int)n);
    return 1;
}

static int32_t read_q31(const unsigned char *p) {
    unsigned n = (unsigned)p[0] | ((unsigned)p[1] << 8);
    int32_t x = n >= 32768 ? (int32_t)n - 65536 : (int32_t)n;
    return x * 65536; /* avoid left-shifting a negative C integer */
}

static int32_t mix_q27(int64_t sum, uint64_t *clips) {
    int64_t value = sum * 16;
    if (value > INT32_MAX) { ++*clips; return INT32_MAX; }
    if (value < INT32_MIN) { ++*clips; return INT32_MIN; }
    return (int32_t)value;
}

int main(int argc, char **argv) {
    struct fir_state_32x16 states[4] = {{0}};
    struct sof_fir_coef_data *coefficients[4] = {0};
    int32_t *delays[4] = {0};
    FILE *bank = NULL, *input = NULL, *output = NULL, *meta = NULL;
    unsigned char raw[480 * 4 * 2], encoded[480 * 4];
    uint64_t *durations = NULL, clips = 0;
    unsigned chunk, count = 0;
    uint64_t processed = 0;
    size_t persistent = sizeof(states), blocks = 0;
    int status = 2;
    long length;
    char *end;
    if (argc != 6) return 2;
    errno = 0;
    unsigned long parsed = strtoul(argv[5], &end, 10);
    if (errno || *end || parsed < 2 || parsed > 480 || (parsed & 1)) return 2;
    chunk = (unsigned)parsed;
    bank = fopen(argv[1], "rb");
    if (!bank) goto done;
    for (unsigned i = 0; i < 4; ++i) {
        int16_t taps, shift;
        if (!get_s16(bank, &taps) || !get_s16(bank, &shift) || taps != 64 || shift < 1 || shift > 2) goto done;
        size_t bytes = sizeof(struct sof_fir_coef_data) + 64 * sizeof(int16_t);
        coefficients[i] = calloc(1, bytes);
        if (!coefficients[i]) goto done;
        coefficients[i]->length = taps;
        coefficients[i]->out_shift = shift;
        for (unsigned k = 0; k < 64; ++k) {
            int16_t value;
            if (!get_s16(bank, &value)) goto done;
            coefficients[i]->coef[k] = value;
        }
        int delay_bytes = fir_delay_size(coefficients[i]);
        if (delay_bytes <= 0) goto done;
        delays[i] = calloc(1, (size_t)delay_bytes);
        if (!delays[i] || fir_init_coef(&states[i], coefficients[i]) != 0) goto done;
        int32_t *position = delays[i];
        fir_init_delay(&states[i], &position);
        persistent += bytes + (size_t)delay_bytes;
    }
    if (fgetc(bank) != EOF || ferror(bank)) goto done;
    input = fopen(argv[2], "rb");
    if (!input || fseek(input, 0, SEEK_END) || (length = ftell(input)) <= 0 ||
        length > 256000 * 8 || length % 16 || fseek(input, 0, SEEK_SET)) goto done;
    size_t maximum_blocks = ((size_t)length / 8 + chunk - 1) / chunk;
    durations = calloc(maximum_blocks, sizeof(*durations));
    if (!durations) goto done;
    output = fopen(argv[3], "wbx");
    meta = fopen(argv[4], "wbx");
    if (!output || !meta) goto done;
    size_t got;
    while ((got = fread(raw, 1, (size_t)chunk * 8, input)) != 0) {
        struct timespec before, after;
        if (got % 16 || blocks >= maximum_blocks) goto done;
        count = (unsigned)(got / 8);
        if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &before)) goto done;
        for (unsigned k = 0; k < count; k += 2) {
            int64_t mix0 = 0, mix1 = 0;
            for (unsigned channel = 0; channel < 4; ++channel) {
                int32_t y0, y1;
                int32_t x0 = read_q31(raw + ((size_t)k * 4 + channel) * 2);
                int32_t x1 = read_q31(raw + ((size_t)(k + 1) * 4 + channel) * 2);
                fir_32x16_2x(&states[channel], x0, x1, &y0, &y1);
                /* Match tdfb_core's per-filter Q1.31 -> Q5.27 mix boundary. */
                mix0 += y0 >> 4;
                mix1 += y1 >> 4;
            }
            int32_t values[2] = {mix_q27(mix0, &clips), mix_q27(mix1, &clips)};
            for (unsigned j = 0; j < 2; ++j) {
                uint32_t bits = (uint32_t)values[j];
                for (unsigned b = 0; b < 4; ++b)
                    encoded[((size_t)k + j) * 4 + b] = (unsigned char)(bits >> (8 * b));
            }
        }
        if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &after)) goto done;
        durations[blocks++] = (uint64_t)((after.tv_sec - before.tv_sec) * INT64_C(1000000000)
                                        + after.tv_nsec - before.tv_nsec);
        if (fwrite(encoded, 4, count, output) != count) goto done;
        processed += count;
    }
    if (ferror(input) || processed != (uint64_t)length / 8) goto done;
    if (fprintf(meta, "{\"status\":\"SUCCESS\",\"shipping_authority\":false,"
                "\"samples\":%" PRIu64 ",\"sample_rate_hz\":16000,\"mic_count\":4,"
                "\"taps_per_mic\":64,\"output_count\":1,\"clip_count\":%" PRIu64 ","
                "\"fir_state_coefficient_delay_bytes\":%zu,\"chunk_samples\":%u,"
                "\"thread_cpu_process_ns\":[", processed, clips, persistent, chunk) < 0) goto done;
    for (size_t i = 0; i < blocks; ++i)
        if (fprintf(meta, "%s%" PRIu64, i ? "," : "", durations[i]) < 0) goto done;
    if (fputs("]}\n", meta) == EOF) goto done;
    status = 0;
done:
    for (unsigned i = 0; i < 4; ++i) { free(coefficients[i]); free(delays[i]); }
    free(durations);
    if (bank && fclose(bank)) status = 2;
    if (input && fclose(input)) status = 2;
    if (output && fclose(output)) status = 2;
    if (meta && fclose(meta)) status = 2;
    if (status) fputs("SOF host reference failed; partial outputs are not evidence\n", stderr);
    return status;
}
