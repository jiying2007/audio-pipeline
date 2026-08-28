#include "audio_pipeline/audio_pipeline.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

static void usage(const char *argv0) {
    fprintf(stderr,
            "usage: %s [--sample-rate HZ] [--mic-channels 1|2] "
            "[--capture-only] <mic.pcm> [render.pcm] <out.pcm>\n",
            argv0);
}

static int parse_u32(const char *text, uint32_t *value) {
    char *end = NULL;
    unsigned long parsed;
    errno = 0;
    parsed = strtoul(text, &end, 10);
    if (errno || !end || *end != '\0' || parsed > 0xfffffffful) return 0;
    *value = (uint32_t)parsed;
    return 1;
}

int main(int argc, char **argv) {
    AP_ALIGN16 static unsigned char state[AP_PIPELINE_STATE_MAX_BYTES];
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS];
    int16_t render[AP_MAX_IO_FRAME_SAMPLES];
    int16_t out[AP_MAX_IO_FRAME_SAMPLES];
    FILE *fm = NULL;
    FILE *fr = NULL;
    FILE *fo = NULL;
    ap_config_t cfg = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *pipeline = NULL;
    uint32_t sample_rate = cfg.io_sample_rate_hz;
    uint32_t channels = cfg.mic_channels;
    int capture_only = 0;
    int arg = 1;
    const char *mic_path;
    const char *render_path = NULL;
    const char *out_path;
    size_t frame;

    while (arg < argc && argv[arg][0] == '-') {
        if (strcmp(argv[arg], "--sample-rate") == 0) {
            if (++arg >= argc || !parse_u32(argv[arg], &sample_rate)) {
                usage(argv[0]);
                return 2;
            }
        } else if (strcmp(argv[arg], "--mic-channels") == 0) {
            if (++arg >= argc || !parse_u32(argv[arg], &channels)) {
                usage(argv[0]);
                return 2;
            }
        } else if (strcmp(argv[arg], "--capture-only") == 0) {
            capture_only = 1;
        } else {
            usage(argv[0]);
            return 2;
        }
        arg++;
    }

    if (channels < 1u || channels > AP_MAX_MIC_CHANNELS ||
        sample_rate == 0u || sample_rate % 100u != 0u) {
        usage(argv[0]);
        return 2;
    }
    if ((!capture_only && argc - arg != 3) || (capture_only && argc - arg != 2)) {
        usage(argv[0]);
        return 2;
    }

    mic_path = argv[arg++];
    if (!capture_only) render_path = argv[arg++];
    out_path = argv[arg++];

    cfg.io_sample_rate_hz = sample_rate;
    cfg.mic_channels = channels;
    if (channels == 1u) cfg.stages &= ~AP_STAGE_BF;
    if (capture_only)
        cfg.stages &= ~(AP_STAGE_SYNC | AP_STAGE_AEC | AP_STAGE_RES);
    if (ap_pipeline_validate_config(&cfg) != AP_OK) {
        fprintf(stderr, "invalid processor geometry/stage configuration\n");
        return 2;
    }
    frame = ap_pipeline_io_frame_samples(&cfg);
    if (!frame || frame > AP_MAX_IO_FRAME_SAMPLES) return 2;

    fm = fopen(mic_path, "rb");
    if (!capture_only) fr = fopen(render_path, "rb");
    fo = fopen(out_path, "wb");
    if (!fm || (!capture_only && !fr) || !fo) {
        perror("fopen");
        if (fm) fclose(fm);
        if (fr) fclose(fr);
        if (fo) fclose(fo);
        return 2;
    }
    if (ap_pipeline_state_size() > sizeof(state) ||
        ap_pipeline_init(state, sizeof(state), &cfg, &pipeline) != AP_OK)
        return 3;

    while (fread(mic, sizeof(int16_t) * channels, frame, fm) == frame) {
        if (!capture_only) {
            const size_t got = fread(render, sizeof(int16_t), frame, fr);
            if (got < frame)
                memset(render + got, 0, (frame - got) * sizeof(int16_t));
            if (ap_pipeline_push_render(pipeline, render, frame) != AP_OK) return 4;
        }
        if (ap_pipeline_process_capture(pipeline, mic, frame, out) != AP_OK) return 4;
        if (fwrite(out, sizeof(int16_t), frame, fo) != frame) return 5;
    }

    fclose(fm);
    if (fr) fclose(fr);
    fclose(fo);
    return 0;
}
