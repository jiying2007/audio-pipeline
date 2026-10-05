/* First-party offline reference adapter. libfvad is linked only by research CI.
 * Upstream LICENSE/PATENTS/AUTHORS accompany the separate source/binary evidence.
 * CLI: runner MODE MIC_S16LE OUTPUT_S16LE TRACE_JSONL, or --self-test.
 * One output decision per 160 samples at 16 kHz; no padding or normalisation.
 */
#include "fvad.h"
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define HOP 160u

static int configure(Fvad *v, int mode) {
    fvad_reset(v); /* Upstream reset restores 8 kHz / mode 0. */
    return fvad_set_sample_rate(v, 16000) == 0 && fvad_set_mode(v, mode) == 0;
}

static void decode(const unsigned char *raw, int16_t *pcm) {
    size_t i;
    for (i = 0; i < HOP; ++i) {
        uint32_t u = (uint32_t)raw[2 * i] | ((uint32_t)raw[2 * i + 1] << 8);
        pcm[i] = (int16_t)(u < 32768u ? (int32_t)u : (int32_t)u - 65536);
    }
}

static int self_test(void) {
    Fvad *a = fvad_new(), *b = fvad_new();
    int16_t frames[12][HOP];
    int saved[12];
    uint32_t rng = 1u;
    size_t i, j;
    int mode, pass, ok = a != NULL && b != NULL;
    if (!ok) goto done;
    for (i = 0; i < 12; ++i) for (j = 0; j < HOP; ++j) {
        rng = rng * 1664525u + 1013904223u;
        frames[i][j] = i < 3 ? 0 : (int16_t)((int32_t)(rng >> 18) - 8192);
    }
    if (fvad_set_mode(a, 4) != -1 || fvad_set_sample_rate(a, 44100) != -1 ||
        fvad_process(a, frames[0], 1) != -1) { ok = 0; goto done; }
    for (mode = 0; mode <= 3; ++mode) {
        for (pass = 0; pass < 2; ++pass) {
            if (!configure(a, mode) || !configure(b, mode)) { ok = 0; goto done; }
            for (i = 0; i < 12; ++i) {
                int x = fvad_process(a, frames[i], HOP);
                int y = fvad_process(b, frames[i], HOP);
                if (x < 0 || x > 1 || x != y || (pass && x != saved[i])) {
                    ok = 0; goto done;
                }
                saved[i] = x;
            }
        }
    }
done:
    if (a) fvad_free(a);
    if (b) fvad_free(b);
    if (ok) puts("libfvad reset/rate/mode/replay contracts: PASS");
    return ok ? 0 : 1;
}

int main(int argc, char **argv) {
    FILE *input = NULL, *output = NULL, *trace = NULL;
    Fvad *v = NULL;
    unsigned char raw[HOP * 2];
    int16_t pcm[HOP];
    size_t count, frame = 0;
    long mode;
    char *end = NULL;
    int rc = 1;
    if (argc == 2 && strcmp(argv[1], "--self-test") == 0) return self_test();
    if (argc != 5) { fputs("expected MODE MIC OUTPUT TRACE\n", stderr); return 2; }
    errno = 0;
    mode = strtol(argv[1], &end, 10);
    if (errno || !argv[1][0] || !end || *end || mode < 0 || mode > 3) return 2;
    if (strcmp(argv[2], argv[3]) == 0 || strcmp(argv[2], argv[4]) == 0 ||
        strcmp(argv[3], argv[4]) == 0) return 2;
    input = fopen(argv[2], "rb");
    if (!input) goto done;
    output = fopen(argv[3], "wbx");
    trace = fopen(argv[4], "wx");
    v = fvad_new();
    if (!output || !trace || !v || !configure(v, (int)mode)) goto done;
    while ((count = fread(raw, 1, sizeof(raw), input)) != 0) {
        int decision;
        if (count != sizeof(raw)) { fputs("partial 10 ms frame\n", stderr); goto done; }
        decode(raw, pcm);
        decision = fvad_process(v, pcm, HOP);
        if (decision < 0 || decision > 1) goto done;
        if (fwrite(raw, 1, sizeof(raw), output) != sizeof(raw)) goto done;
        if (fprintf(trace, "{\"frame\":%zu,\"vad_active\":%d,\"mode\":%ld,"
                    "\"decision_available_after_samples\":%zu}\n",
                    frame, decision, mode, (frame + 1) * HOP) < 0) goto done;
        ++frame;
    }
    if (ferror(input) || frame == 0) goto done;
    rc = 0;
done:
    if (v) fvad_free(v);
    if (input && fclose(input)) rc = 1;
    if (output && fclose(output)) rc = 1;
    if (trace && fclose(trace)) rc = 1;
    if (rc) fputs("libfvad adapter failed; partial outputs are not valid evidence\n", stderr);
    return rc;
}
