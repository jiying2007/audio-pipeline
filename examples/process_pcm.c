#include "audio_pipeline/audio_pipeline.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

static void usage(const char *argv0) {
    fprintf(stderr, "usage: %s <mic_s16le_2ch.pcm> <render_s16le_mono.pcm> <out_s16le_mono.pcm>\n", argv0);
}

int main(int argc, char **argv) {
    AP_ALIGN16 static unsigned char state[AP_PIPELINE_STATE_MAX_BYTES];
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * 2u];
    int16_t render[AP_MAX_IO_FRAME_SAMPLES];
    int16_t out[AP_MAX_IO_FRAME_SAMPLES];
    FILE *fm, *fr, *fo;
    ap_config_t cfg = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *p = NULL;
    const size_t frame = cfg.io_sample_rate_hz / 100u;
    if (argc != 4) { usage(argv[0]); return 2; }
    fm = fopen(argv[1], "rb"); fr = fopen(argv[2], "rb"); fo = fopen(argv[3], "wb");
    if (!fm || !fr || !fo) { perror("fopen"); return 2; }
    if (ap_pipeline_state_size() > sizeof(state) || ap_pipeline_init(state, sizeof(state), &cfg, &p) != AP_OK) return 3;
    while (fread(mic, sizeof(int16_t) * 2u, frame, fm) == frame) {
        const size_t got = fread(render, sizeof(int16_t), frame, fr);
        if (got < frame) memset(render + got, 0, (frame - got) * sizeof(int16_t));
        (void)ap_pipeline_push_render(p, render, frame);
        if (ap_pipeline_process_capture(p, mic, frame, out) != AP_OK) return 4;
        if (fwrite(out, sizeof(int16_t), frame, fo) != frame) return 5;
    }
    fclose(fm); fclose(fr); fclose(fo);
    return 0;
}
