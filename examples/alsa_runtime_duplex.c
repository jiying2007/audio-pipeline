#define _POSIX_C_SOURCE 200809L
#include "audio_pipeline/audio_pipeline.h"
#include "audio_pipeline/audio_runtime.h"
#include <alsa/asoundlib.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

#define RATE 16000u
#define FRAME 160u
#define MIC_CHANNELS 2u

static int configure_pcm(snd_pcm_t *pcm, unsigned channels) {
    int rc = snd_pcm_set_params(pcm, SND_PCM_FORMAT_S16_LE,
                                SND_PCM_ACCESS_RW_INTERLEAVED,
                                channels, RATE, 1, 20000u);
    if (rc < 0) fprintf(stderr, "snd_pcm_set_params: %s\n", snd_strerror(rc));
    return rc;
}

static int write_all(snd_pcm_t *pcm, const int16_t *data, snd_pcm_uframes_t frames) {
    snd_pcm_uframes_t done = 0u;
    while (done < frames) {
        snd_pcm_sframes_t n = snd_pcm_writei(pcm, data + done, frames - done);
        if (n < 0) {
            n = snd_pcm_recover(pcm, (int)n, 1);
            if (n < 0) return -1;
            continue;
        }
        done += (snd_pcm_uframes_t)n;
    }
    return 0;
}

static int read_all(snd_pcm_t *pcm, int16_t *data, snd_pcm_uframes_t frames) {
    snd_pcm_uframes_t done = 0u;
    while (done < frames) {
        snd_pcm_sframes_t n = snd_pcm_readi(pcm, data + (size_t)done * MIC_CHANNELS,
                                            frames - done);
        if (n < 0) {
            n = snd_pcm_recover(pcm, (int)n, 1);
            if (n < 0) return -1;
            continue;
        }
        done += (snd_pcm_uframes_t)n;
    }
    return 0;
}

static void nap_100us(void) {
    const struct timespec t = {0, 100000};
    (void)nanosleep(&t, NULL);
}

int main(int argc, char **argv) {
    AP_ALIGN16 static unsigned char pipeline_mem[AP_PIPELINE_STATE_MAX_BYTES];
    AP_ALIGN16 static unsigned char runtime_mem[AP_RUNTIME_STATE_MAX_BYTES];
    ap_config_t cfg = ap_config_default(AP_PROFILE_CALL);
    ap_runtime_config_t rt_cfg = ap_runtime_config_default();
    ap_pipeline_t *pipeline = NULL;
    ap_runtime_t *runtime = NULL;
    snd_pcm_t *capture = NULL, *playback = NULL;
    FILE *far = NULL, *uplink = NULL;
    int16_t render[FRAME] = {0};
    int16_t mic[FRAME * MIC_CHANNELS] = {0};
    int16_t clean[FRAME] = {0};
    unsigned max_frames = 0u, produced = 0u, received = 0u;
    int silence_render = 0;
    int rc = 1;

    if (argc < 5 || argc > 7) {
        fprintf(stderr,
                "usage: %s <capture> <playback> <farend-s16le|-> <uplink-s16le> [seconds] [dsp-cpu]\n",
                argv[0]);
        return 2;
    }
    if (argc >= 6) max_frames = (unsigned)strtoul(argv[5], NULL, 10) * 100u;
    if (argc == 7) rt_cfg.dsp_cpu = (int)strtol(argv[6], NULL, 10);
    silence_render = strcmp(argv[3], "-") == 0;

    if (!silence_render) {
        far = fopen(argv[3], "rb");
        if (!far) {
            fprintf(stderr, "open far-end %s: %s\n", argv[3], strerror(errno));
            goto done;
        }
    }
    uplink = fopen(argv[4], "wb");
    if (!uplink) {
        fprintf(stderr, "open uplink %s: %s\n", argv[4], strerror(errno));
        goto done;
    }
    if (snd_pcm_open(&capture, argv[1], SND_PCM_STREAM_CAPTURE, 0) < 0 ||
        snd_pcm_open(&playback, argv[2], SND_PCM_STREAM_PLAYBACK, 0) < 0) {
        fprintf(stderr, "cannot open ALSA devices\n");
        goto done;
    }
    if (configure_pcm(capture, MIC_CHANNELS) < 0 || configure_pcm(playback, 1u) < 0) goto done;

    cfg.mic_channels = MIC_CHANNELS;
    if (ap_pipeline_init(pipeline_mem, sizeof(pipeline_mem), &cfg, &pipeline) != AP_OK ||
        ap_runtime_init(runtime_mem, sizeof(runtime_mem), pipeline, &rt_cfg, &runtime) != AP_OK ||
        ap_runtime_start(runtime) != AP_OK) {
        fprintf(stderr, "audio runtime init/start failed\n");
        goto done;
    }

    while (!max_frames || produced < max_frames) {
        size_t got = FRAME;
        ap_status_t s;
        if (silence_render) {
            memset(render, 0, sizeof(render));
        } else {
            got = fread(render, sizeof(render[0]), FRAME, far);
            if (got == 0u) break;
            if (got < FRAME) memset(render + got, 0, (FRAME - got) * sizeof(render[0]));
        }

        if (write_all(playback, render, FRAME) != 0 || read_all(capture, mic, FRAME) != 0) {
            fprintf(stderr, "ALSA XRUN recovery failed\n");
            goto done;
        }

        s = ap_runtime_submit(runtime, mic, silence_render ? NULL : render);
        if (s == AP_EFULL) {
            fprintf(stderr, "DSP input queue full at frame %u\n", produced);
            goto done;
        }
        if (s != AP_OK) goto done;
        produced++;

        while (ap_runtime_receive(runtime, clean, NULL) == AP_OK) {
            if (fwrite(clean, sizeof(clean[0]), FRAME, uplink) != FRAME) goto done;
            received++;
        }
        if (!silence_render && got < FRAME) break;
    }

    /* Drain outstanding DSP results without busy-spinning. */
    while (received < produced) {
        ap_status_t s = ap_runtime_receive(runtime, clean, NULL);
        if (s == AP_OK) {
            if (fwrite(clean, sizeof(clean[0]), FRAME, uplink) != FRAME) goto done;
            received++;
        } else if (s == AP_EEMPTY) {
            nap_100us();
        } else {
            goto done;
        }
    }

    {
        ap_runtime_metrics_t rm;
        ap_metrics_t pm;
        ap_runtime_get_metrics(runtime, &rm);
        ap_pipeline_get_metrics(pipeline, &pm);
        fprintf(stderr,
                "produced=%u received=%u dsp_max_us=%u overruns=%llu input_full=%llu output_drop=%llu quality=%d backend=%d delay_ms=%u resets=%llu\n",
                produced, received, rm.max_dsp_us,
                (unsigned long long)rm.dsp_overruns,
                (unsigned long long)rm.input_full_events,
                (unsigned long long)rm.output_drop_events,
                (int)rm.quality, (int)pm.aec_backend, pm.estimated_delay_ms,
                (unsigned long long)pm.aec_resets);
    }
    rc = 0;

done:
    if (runtime) ap_runtime_stop(runtime);
    if (capture) snd_pcm_close(capture);
    if (playback) snd_pcm_close(playback);
    if (far) fclose(far);
    if (uplink) fclose(uplink);
    return rc;
}
