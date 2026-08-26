#define _POSIX_C_SOURCE 200809L
#include "audio_pipeline/audio_pipeline.h"
#include <alsa/asoundlib.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(_MSC_VER)
#define AP_ALIGN16 __declspec(align(16))
#else
#define AP_ALIGN16 _Alignas(16)
#endif

#define RATE 16000u
#define FRAME 160u
#define MIC_CHANNELS 2u

static int configure_pcm(snd_pcm_t *pcm, unsigned channels) {
    const int rc = snd_pcm_set_params(pcm,
                                      SND_PCM_FORMAT_S16_LE,
                                      SND_PCM_ACCESS_RW_INTERLEAVED,
                                      channels,
                                      RATE,
                                      1,
                                      20000u);
    if (rc < 0) fprintf(stderr, "snd_pcm_set_params: %s\n", snd_strerror(rc));
    return rc;
}

static int pcm_write_all(snd_pcm_t *pcm, const int16_t *data, snd_pcm_uframes_t frames) {
    snd_pcm_uframes_t done = 0;
    while (done < frames) {
        snd_pcm_sframes_t n = snd_pcm_writei(pcm, data + done, frames - done);
        if (n < 0) {
            n = snd_pcm_recover(pcm, (int)n, 1);
            if (n < 0) {
                fprintf(stderr, "playback recover failed: %s\n", snd_strerror((int)n));
                return -1;
            }
            continue;
        }
        done += (snd_pcm_uframes_t)n;
    }
    return 0;
}

static int pcm_read_all(snd_pcm_t *pcm, int16_t *data, snd_pcm_uframes_t frames, unsigned channels) {
    snd_pcm_uframes_t done = 0;
    while (done < frames) {
        snd_pcm_sframes_t n = snd_pcm_readi(pcm, data + (size_t)done * channels, frames - done);
        if (n < 0) {
            n = snd_pcm_recover(pcm, (int)n, 1);
            if (n < 0) {
                fprintf(stderr, "capture recover failed: %s\n", snd_strerror((int)n));
                return -1;
            }
            continue;
        }
        done += (snd_pcm_uframes_t)n;
    }
    return 0;
}

int main(int argc, char **argv) {
    AP_ALIGN16 static unsigned char state[AP_PIPELINE_STATE_MAX_BYTES];
    ap_config_t cfg = ap_config_default(AP_PROFILE_CALL);
    ap_pipeline_t *pipeline = NULL;
    snd_pcm_t *capture = NULL, *playback = NULL;
    FILE *far = NULL, *uplink = NULL;
    int16_t render[FRAME];
    int16_t mic[FRAME * MIC_CHANNELS];
    int16_t clean[FRAME];
    unsigned max_frames = 0u, processed = 0u;
    int rc = 1;

    if (argc < 5 || argc > 6) {
        fprintf(stderr,
                "usage: %s <capture-device> <playback-device> <farend-s16le> <uplink-s16le> [seconds]\n"
                "example: %s hw:0,0 hw:0,0 farend.pcm uplink.pcm 30\n",
                argv[0], argv[0]);
        return 2;
    }
    if (argc == 6) max_frames = (unsigned)strtoul(argv[5], NULL, 10) * 100u;

    far = fopen(argv[3], "rb");
    if (!far) {
        fprintf(stderr, "open far-end %s: %s\n", argv[3], strerror(errno));
        goto done;
    }
    uplink = fopen(argv[4], "wb");
    if (!uplink) {
        fprintf(stderr, "open uplink %s: %s\n", argv[4], strerror(errno));
        goto done;
    }

    if (snd_pcm_open(&capture, argv[1], SND_PCM_STREAM_CAPTURE, 0) < 0) {
        fprintf(stderr, "cannot open capture device %s\n", argv[1]);
        goto done;
    }
    if (snd_pcm_open(&playback, argv[2], SND_PCM_STREAM_PLAYBACK, 0) < 0) {
        fprintf(stderr, "cannot open playback device %s\n", argv[2]);
        goto done;
    }
    if (configure_pcm(capture, MIC_CHANNELS) < 0 || configure_pcm(playback, 1u) < 0) goto done;

    cfg.io_sample_rate_hz = RATE;
    cfg.internal_sample_rate_hz = RATE;
    cfg.mic_channels = MIC_CHANNELS;
    if (ap_pipeline_init(state, sizeof(state), &cfg, &pipeline) != AP_OK) {
        fprintf(stderr, "audio-pipeline init failed\n");
        goto done;
    }

    while (!max_frames || processed < max_frames) {
        size_t got = fread(render, sizeof(render[0]), FRAME, far);
        if (got == 0u) break;
        if (got < FRAME) memset(render + got, 0, (FRAME - got) * sizeof(render[0]));

        /* In a real VoIP application this is the decoded/mixed signal sent to
         * the DAC. Feed the AEC exactly the same post-software-gain samples. */
        if (pcm_write_all(playback, render, FRAME) != 0) goto done;
        if (pcm_read_all(capture, mic, FRAME, MIC_CHANNELS) != 0) goto done;
        if (ap_pipeline_push_render(pipeline, render, FRAME) != AP_OK ||
            ap_pipeline_process_capture(pipeline, mic, FRAME, clean) != AP_OK) {
            fprintf(stderr, "audio-pipeline processing failed\n");
            goto done;
        }
        if (fwrite(clean, sizeof(clean[0]), FRAME, uplink) != FRAME) {
            fprintf(stderr, "write uplink failed\n");
            goto done;
        }
        processed++;
        if (got < FRAME) break;
    }

    {
        ap_metrics_t m;
        ap_pipeline_get_metrics(pipeline, &m);
        fprintf(stderr,
                "processed=%u frames backend=%d erle=%.2f dB delay=%u ms resets=%llu\n",
                processed, (int)m.aec_backend, m.erle_db, m.estimated_delay_ms,
                (unsigned long long)m.aec_resets);
    }
    rc = 0;

done:
    if (capture) snd_pcm_close(capture);
    if (playback) snd_pcm_close(playback);
    if (far) fclose(far);
    if (uplink) fclose(uplink);
    return rc;
}
