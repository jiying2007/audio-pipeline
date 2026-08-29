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

static int supported_rate(unsigned rate) {
    return rate == 8000u || rate == 16000u || rate == 24000u ||
           rate == 32000u || rate == 48000u;
}

static int configure_pcm(snd_pcm_t *pcm, unsigned channels, unsigned rate) {
    int rc = snd_pcm_set_params(pcm, SND_PCM_FORMAT_S16_LE,
                                SND_PCM_ACCESS_RW_INTERLEAVED,
                                channels, rate, 1, 20000u);
    if (rc < 0) fprintf(stderr, "snd_pcm_set_params: %s\n", snd_strerror(rc));
    return rc;
}

static int recover_pcm(snd_pcm_t *pcm, int error, uint64_t *xruns) {
    int rc;
    if (error == -EPIPE || error == -ESTRPIPE) (*xruns)++;
    rc = snd_pcm_recover(pcm, error, 1);
    return rc < 0 ? -1 : 0;
}

static int write_all(snd_pcm_t *pcm, const int16_t *data,
                     snd_pcm_uframes_t frames, uint64_t *xruns) {
    snd_pcm_uframes_t done = 0u;
    while (done < frames) {
        snd_pcm_sframes_t n = snd_pcm_writei(pcm, data + done, frames - done);
        if (n < 0) {
            if (recover_pcm(pcm, (int)n, xruns) != 0) return -1;
            continue;
        }
        done += (snd_pcm_uframes_t)n;
    }
    return 0;
}

static int read_all(snd_pcm_t *pcm, int16_t *data, snd_pcm_uframes_t frames,
                    unsigned channels, uint64_t *xruns) {
    snd_pcm_uframes_t done = 0u;
    while (done < frames) {
        snd_pcm_sframes_t n = snd_pcm_readi(pcm, data + (size_t)done * channels,
                                            frames - done);
        if (n < 0) {
            if (recover_pcm(pcm, (int)n, xruns) != 0) return -1;
            continue;
        }
        done += (snd_pcm_uframes_t)n;
    }
    return 0;
}

static int fill_render(FILE *far, int silence, int repeat, int16_t *render,
                       size_t frame, int *ended) {
    size_t done = 0u;
    *ended = 0;
    if (silence) {
        memset(render, 0, frame * sizeof(render[0]));
        return 0;
    }
    while (done < frame) {
        size_t got = fread(render + done, sizeof(render[0]), frame - done, far);
        done += got;
        if (done == frame) return 0;
        if (ferror(far)) return -1;
        if (!feof(far)) continue;
        if (!repeat) {
            memset(render + done, 0, (frame - done) * sizeof(render[0]));
            *ended = 1;
            return 0;
        }
        clearerr(far);
        if (fseek(far, 0L, SEEK_SET) != 0) return -1;
        if (got == 0u) {
            int probe = fgetc(far);
            if (probe == EOF) return -1;
            if (ungetc(probe, far) == EOF) return -1;
        }
    }
    return 0;
}

static void nap_100us(void) {
    const struct timespec t = {0, 100000};
    (void)nanosleep(&t, NULL);
}

static void nap_ms(unsigned ms) {
    struct timespec t;
    t.tv_sec = (time_t)(ms / 1000u);
    t.tv_nsec = (long)(ms % 1000u) * 1000000L;
    (void)nanosleep(&t, NULL);
}

static unsigned env_u32(const char *name, unsigned default_value) {
    const char *value = getenv(name);
    char *end = NULL;
    unsigned long parsed;
    if (!value || !*value) return default_value;
    errno = 0;
    parsed = strtoul(value, &end, 10);
    if (errno != 0 || !end || *end != '\0' || parsed > 0xfffffffful) {
        fprintf(stderr, "invalid %s=%s\n", name, value);
        exit(2);
    }
    return (unsigned)parsed;
}

static int restart_pcm(snd_pcm_t *pcm) {
    int rc;
    if (!pcm) return 0;
    rc = snd_pcm_drop(pcm);
    if (rc < 0) return -1;
    rc = snd_pcm_prepare(pcm);
    return rc < 0 ? -1 : 0;
}

static void usage(const char *argv0) {
    fprintf(stderr,
            "usage: %s <capture> <playback|-> <farend-s16le|-> <uplink-s16le|-> "
            "[seconds] [dsp-cpu] [sample-rate] [mic-channels]\n",
            argv0);
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
    int16_t render[AP_MAX_IO_FRAME_SAMPLES] = {0};
    int16_t mic[AP_MAX_IO_FRAME_SAMPLES * AP_MAX_MIC_CHANNELS] = {0};
    int16_t clean[AP_MAX_IO_FRAME_SAMPLES] = {0};
    unsigned rate = 16000u, mic_channels = 2u, frame;
    unsigned max_frames = 0u, produced = 0u, received = 0u;
    uint64_t xruns = 0u;
    uint64_t injected_route_restarts = 0u;
    uint64_t injected_render_gap_frames = 0u;
    uint64_t injected_cpu_stalls = 0u;
    const unsigned fault_route_restart_every = env_u32("AP_FAULT_ROUTE_RESTART_EVERY", 0u);
    const unsigned fault_render_gap_every = env_u32("AP_FAULT_RENDER_GAP_EVERY", 0u);
    const unsigned fault_render_gap_frames = env_u32("AP_FAULT_RENDER_GAP_FRAMES", 0u);
    const unsigned fault_cpu_stall_every = env_u32("AP_FAULT_CPU_STALL_EVERY", 0u);
    const unsigned fault_cpu_stall_ms = env_u32("AP_FAULT_CPU_STALL_MS", 0u);
    unsigned render_gap_remaining = 0u;
    int silence_render;
    int have_playback;
    int discard_uplink;
    int rc = 1;

    if (argc < 5 || argc > 9) {
        usage(argv[0]);
        return 2;
    }
    if (argc >= 6) max_frames = (unsigned)strtoul(argv[5], NULL, 10) * 100u;
    if (argc >= 7) rt_cfg.dsp_cpu = (int)strtol(argv[6], NULL, 10);
    if (argc >= 8) rate = (unsigned)strtoul(argv[7], NULL, 10);
    if (argc >= 9) mic_channels = (unsigned)strtoul(argv[8], NULL, 10);
    if (!supported_rate(rate) || mic_channels < 1u || mic_channels > AP_MAX_MIC_CHANNELS) {
        usage(argv[0]);
        return 2;
    }
    frame = rate / 100u;
    have_playback = strcmp(argv[2], "-") != 0;
    silence_render = strcmp(argv[3], "-") == 0;
    discard_uplink = strcmp(argv[4], "-") == 0;
    if (!have_playback && !silence_render) {
        fprintf(stderr, "far-end stimulus requires a playback device\n");
        return 2;
    }

    if (!silence_render) {
        far = fopen(argv[3], "rb");
        if (!far) {
            fprintf(stderr, "open far-end %s: %s\n", argv[3], strerror(errno));
            goto done;
        }
    }
    if (!discard_uplink) {
        uplink = fopen(argv[4], "wb");
        if (!uplink) {
            fprintf(stderr, "open uplink %s: %s\n", argv[4], strerror(errno));
            goto done;
        }
    }
    if (snd_pcm_open(&capture, argv[1], SND_PCM_STREAM_CAPTURE, 0) < 0) {
        fprintf(stderr, "cannot open ALSA capture device\n");
        goto done;
    }
    if (have_playback && snd_pcm_open(&playback, argv[2], SND_PCM_STREAM_PLAYBACK, 0) < 0) {
        fprintf(stderr, "cannot open ALSA playback device\n");
        goto done;
    }
    if (configure_pcm(capture, mic_channels, rate) < 0 ||
        (playback && configure_pcm(playback, 1u, rate) < 0)) goto done;

    cfg.io_sample_rate_hz = rate;
    cfg.internal_sample_rate_hz = rate < 16000u ? rate : 16000u;
    cfg.mic_channels = mic_channels;
    if (mic_channels == 1u) cfg.stages &= ~AP_STAGE_BF;
    if (ap_pipeline_validate_config(&cfg) != AP_OK) {
        fprintf(stderr, "pipeline does not support requested route geometry\n");
        goto done;
    }
    if (ap_pipeline_init(pipeline_mem, sizeof(pipeline_mem), &cfg, &pipeline) != AP_OK ||
        ap_runtime_init(runtime_mem, sizeof(runtime_mem), pipeline, &rt_cfg, &runtime) != AP_OK ||
        ap_runtime_start(runtime) != AP_OK) {
        fprintf(stderr, "audio runtime init/start failed\n");
        goto done;
    }

    while (!max_frames || produced < max_frames) {
        ap_status_t s;
        ap_frame_metadata_t metadata;
        const ap_frame_metadata_t *metadata_ptr = NULL;
        int ended = 0;
        int gap_started = 0;
        memset(&metadata, 0, sizeof(metadata));
        metadata.struct_size = sizeof(metadata);
        metadata.api_version = AP_RUNTIME_CONTROL_API_VERSION;
        metadata.stream_sequence = produced;

        if (fault_route_restart_every && produced > 0u &&
            produced % fault_route_restart_every == 0u) {
            if (restart_pcm(capture) != 0 || restart_pcm(playback) != 0) {
                fprintf(stderr, "injected ALSA route restart failed\n");
                goto done;
            }
            metadata.flags |= AP_FRAME_CAPTURE_DISCONTINUITY | AP_FRAME_CODEC_REOPEN;
            metadata.lost_capture_frames = 1u;
            if (playback) {
                metadata.flags |= AP_FRAME_RENDER_DISCONTINUITY;
                metadata.lost_render_frames = 1u;
            }
            metadata_ptr = &metadata;
            injected_route_restarts++;
        }

        if (fill_render(far, silence_render, max_frames != 0u,
                        render, frame, &ended) != 0) {
            fprintf(stderr, "cannot read/repeat far-end stimulus\n");
            goto done;
        }
        if (playback && fault_render_gap_every && fault_render_gap_frames &&
            render_gap_remaining == 0u && produced > 0u &&
            produced % fault_render_gap_every == 0u) {
            render_gap_remaining = fault_render_gap_frames;
            gap_started = 1;
        }
        if (playback && render_gap_remaining > 0u) {
            memset(render, 0, frame * sizeof(render[0]));
            render_gap_remaining--;
            injected_render_gap_frames++;
            if (gap_started) {
                metadata.flags |= AP_FRAME_RENDER_DISCONTINUITY;
                metadata.lost_render_frames = fault_render_gap_frames;
                metadata_ptr = &metadata;
            }
        }
        if (playback && write_all(playback, render, frame, &xruns) != 0) {
            fprintf(stderr, "ALSA playback XRUN recovery failed\n");
            goto done;
        }
        if (read_all(capture, mic, frame, mic_channels, &xruns) != 0) {
            fprintf(stderr, "ALSA capture XRUN recovery failed\n");
            goto done;
        }

        if (fault_cpu_stall_every && fault_cpu_stall_ms && produced > 0u &&
            produced % fault_cpu_stall_every == 0u) {
            nap_ms(fault_cpu_stall_ms);
            injected_cpu_stalls++;
        }
        s = ap_runtime_submit_ex(runtime, mic, playback ? render : NULL, metadata_ptr);
        if (s == AP_EFULL) {
            fprintf(stderr, "DSP input queue full at frame %u\n", produced);
            goto done;
        }
        if (s != AP_OK) goto done;
        produced++;

        for (;;) {
            s = ap_runtime_receive(runtime, clean, NULL);
            if (s == AP_OK) {
                if (uplink && fwrite(clean, sizeof(clean[0]), frame, uplink) != frame) goto done;
                received++;
                continue;
            }
            if (s != AP_EEMPTY) goto done;
            break;
        }
        if (ended) break;
    }

    while (received < produced) {
        ap_status_t s = ap_runtime_receive(runtime, clean, NULL);
        if (s == AP_OK) {
            if (uplink && fwrite(clean, sizeof(clean[0]), frame, uplink) != frame) goto done;
            received++;
        } else if (s == AP_EEMPTY) {
            nap_100us();
        } else {
            goto done;
        }
    }

    {
        ap_runtime_metrics_v3_t rm;
        ap_metrics_t pm;
        memset(&rm, 0, sizeof(rm));
        rm.struct_size = sizeof(rm);
        rm.api_version = AP_RUNTIME_METRICS_V3_API_VERSION;
        if (ap_runtime_get_metrics_v3(runtime, &rm) != AP_OK) goto done;
        ap_pipeline_get_metrics(pipeline, &pm);
        fprintf(stderr,
                "produced=%u received=%u xruns=%llu dsp_overruns=%llu input_full=%llu "
                "output_drop=%llu p50_dsp_us=%u p95_dsp_us=%u p99_dsp_us=%u "
                "max_dsp_us=%u failed_frames=%llu critical_events=%llu "
                "render_push_failures=%llu capture_process_failures=%llu "
                "scheduler_bind_failures=%llu memory_lock_failures=%llu "
                "actual_cpu=%d actual_policy=%d actual_priority=%d quality=%d "
                "backend=%d delay_ms=%u resets=%llu injected_route_restarts=%llu "
                "injected_render_gap_frames=%llu injected_cpu_stalls=%llu\n",
                produced, received, (unsigned long long)xruns,
                (unsigned long long)rm.dsp_overruns,
                (unsigned long long)rm.input_full_events,
                (unsigned long long)rm.output_drop_events,
                rm.p50_dsp_us, rm.p95_dsp_us, rm.p99_dsp_us, rm.max_dsp_us,
                (unsigned long long)rm.failed_frames,
                (unsigned long long)rm.critical_events,
                (unsigned long long)rm.render_push_failures,
                (unsigned long long)rm.capture_process_failures,
                (unsigned long long)rm.scheduler_bind_failures,
                (unsigned long long)rm.memory_lock_failures,
                rm.actual_cpu, rm.actual_policy, rm.actual_priority,
                (int)rm.quality, (int)pm.aec_backend, pm.estimated_delay_ms,
                (unsigned long long)pm.aec_resets,
                (unsigned long long)injected_route_restarts,
                (unsigned long long)injected_render_gap_frames,
                (unsigned long long)injected_cpu_stalls);
        if (produced != received || rm.failed_frames != 0u ||
            rm.input_full_events != 0u || rm.output_drop_events != 0u ||
            rm.capture_process_failures != 0u || rm.render_push_failures != 0u) {
            fprintf(stderr, "route runtime integrity gate failed\n");
            goto done;
        }
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
