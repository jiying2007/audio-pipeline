/* FE04 pristine SpeexDSP whole-AEC reference. Offline research only. */
#include "audio_pipeline/audio_modules.h"
#include "speex/speex_echo.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define HOP 160u
#define RATE 16000u
#define REQUESTED_FILTER_SAMPLES 1024u

static int16_t q16(float x, unsigned *clipped) {
    const double v = (double)x * 32768.0;
    long q;
    if (v >= 32767.0) {
        if (v > 32767.0 && clipped) ++*clipped;
        return 32767;
    }
    if (v <= -32768.0) {
        if (v < -32768.0 && clipped) ++*clipped;
        return -32768;
    }
    q = (long)(v >= 0.0 ? floor(v + 0.5) : ceil(v - 0.5));
    if (q > 32767) {
        if (clipped) ++*clipped;
        q = 32767;
    }
    if (q < -32768) {
        if (clipped) ++*clipped;
        q = -32768;
    }
    return (int16_t)q;
}

static float f16(int16_t x) {
    return (float)x / 32768.0f;
}

static size_t round16(size_t n) {
    return (n + 15u) & ~(size_t)15u;
}

int main(int argc, char **argv) {
    FILE *in = NULL, *out = NULL, *meta = NULL, *trace = NULL;
    int mode = 0, rc = 2;
    long length;
    const size_t frame_bytes = HOP * 2u * sizeof(int16_t);
    int16_t packet[HOP * 2u], mic16[HOP], ref16[HOP], written[HOP];
    float mic[HOP], ref[HOP], ap_out[HOP], echo[HOP];
    void *activity_mem = NULL, *aec_mem = NULL;
    ap_activity_module_t *activity = NULL;
    ap_aec_module_t *aec = NULL;
    SpeexEchoState *speex = NULL;
    unsigned frames = 0u, ap_clipped = 0u, full_scale = 0u;
    unsigned far_count = 0u, dt_count = 0u;
    int speex_frame = 0, speex_rate = 0;
    spx_int32_t speex_tail = 0;
    ap_module_aec_result_t last = {0};
    const ap_module_activity_config_t ac = {1.0e-7f, 1.5f, 3u};
    const ap_module_aec_config_t ec = {RATE, 64u, 1u, 0.2f};

    if (argc != 6) {
        fputs("usage: speex-aec-reference ap|speex INPUT.s16le OUTPUT.s16le META.json TRACE.csv\n", stderr);
        return 2;
    }
    if (!strcmp(argv[1], "ap")) mode = 1;
    else if (!strcmp(argv[1], "speex")) mode = 2;
    else {
        fputs("invalid backend\n", stderr);
        return 2;
    }

    in = fopen(argv[2], "rb");
    if (!in) goto done;
    if (fseek(in, 0, SEEK_END)) goto done;
    length = ftell(in);
    if (length <= 0 || (unsigned long)length % frame_bytes ||
        (unsigned long)length / frame_bytes > 2000ul ||
        fseek(in, 0, SEEK_SET)) goto done;

    out = fopen(argv[3], "wbx");
    if (!out) goto done;
    meta = fopen(argv[4], "wbx");
    if (!meta) goto done;
    trace = fopen(argv[5], "wbx");
    if (!trace) goto done;
    if (fputs("frame,mic_energy,reference_energy,monitor_far,monitor_dt,used_by_backend\n", trace) == EOF)
        goto done;

    activity_mem = aligned_alloc(16, round16(ap_module_activity_state_size()));
    if (!activity_mem ||
        ap_module_activity_init(activity_mem, ap_module_activity_state_size(), &ac, &activity) != AP_OK)
        goto done;

    if (mode == 1) {
        aec_mem = aligned_alloc(16, round16(ap_module_aec_state_size()));
        if (!aec_mem ||
            ap_module_aec_init(aec_mem, ap_module_aec_state_size(), &ec, &aec) != AP_OK)
            goto done;
    } else {
        int rate = RATE;
        speex = speex_echo_state_init((int)HOP, (int)REQUESTED_FILTER_SAMPLES);
        if (!speex ||
            speex_echo_ctl(speex, SPEEX_ECHO_SET_SAMPLING_RATE, &rate) ||
            speex_echo_ctl(speex, SPEEX_ECHO_GET_FRAME_SIZE, &speex_frame) ||
            speex_echo_ctl(speex, SPEEX_ECHO_GET_SAMPLING_RATE, &speex_rate) ||
            speex_echo_ctl(speex, SPEEX_ECHO_GET_IMPULSE_RESPONSE_SIZE, &speex_tail))
            goto done;
        if (speex_frame != (int)HOP || speex_rate != (int)RATE ||
            speex_tail < (spx_int32_t)REQUESTED_FILTER_SAMPLES)
            goto done;
    }

    for (;;) {
        const size_t got = fread(packet, 1, frame_bytes, in);
        float me = 1.0e-12f, re = 1.0e-12f;
        ap_module_activity_result_t ar;
        if (got == 0 && !ferror(in)) break;
        if (got != frame_bytes) goto done;

        for (unsigned k = 0; k < HOP; ++k) {
            mic16[k] = packet[2u * k];
            ref16[k] = packet[2u * k + 1u];
            mic[k] = f16(mic16[k]);
            ref[k] = f16(ref16[k]);
            me += mic[k] * mic[k];
            re += ref[k] * ref[k];
        }
        me /= (float)HOP;
        re /= (float)HOP;
        if (ap_module_activity_process(activity, me, re, &ar) != AP_OK) goto done;
        far_count += ar.far_end_active;
        dt_count += ar.double_talk_active;

        if (mode == 1) {
            if (ap_module_aec_process(aec, mic, ref, ap_out, echo, HOP,
                                      ar.far_end_active, ar.double_talk_active, &last) != AP_OK)
                goto done;
            for (unsigned k = 0; k < HOP; ++k)
                written[k] = q16(ap_out[k], &ap_clipped);
        } else {
            speex_echo_cancellation(speex, mic16, ref16, written);
        }

        for (unsigned k = 0; k < HOP; ++k)
            if (written[k] == 32767 || written[k] == -32768) ++full_scale;
        if (fwrite(written, sizeof(int16_t), HOP, out) != HOP) goto done;
        if (fprintf(trace, "%u,%.9g,%.9g,%u,%u,%u\n", frames, (double)me, (double)re,
                    (unsigned)ar.far_end_active, (unsigned)ar.double_talk_active,
                    (unsigned)(mode == 1)) < 0)
            goto done;
        ++frames;
    }

    if (!frames) goto done;
    if (fprintf(meta,
        "{\"status\":\"PASS\",\"backend\":\"%s\",\"frames\":%u,\"samples\":%u,"
        "\"sample_rate_hz\":16000,\"frame_samples\":160,\"input_encoding\":\"s16le\","
        "\"output_encoding\":\"s16le\",\"activity_monitor_far_frames\":%u,"
        "\"activity_monitor_dt_frames\":%u,\"activity_used_by_backend\":%s,"
        "\"ap_activity_state_bytes\":%zu,\"ap_aec_state_bytes\":%zu,"
        "\"ap_active_taps\":%u,\"ap_block_samples\":%u,\"requested_filter_samples\":1024,"
        "\"speex_frame_samples\":%d,\"speex_sampling_rate_hz\":%d,"
        "\"speex_realized_filter_samples\":%d,\"speex_fft_window_samples\":%d,"
        "\"explicit_playback_buffer_delay_samples\":0,\"output_available_after_samples\":160,"
        "\"ap_output_quantization_clip_count\":%u,\"output_full_scale_values\":%u,"
        "\"shipping_authority\":false,\"source_revision\":\"%s\"}\n",
        mode == 1 ? "ap-activity-mdf" : "speexdsp-direct", frames, frames * HOP,
        far_count, dt_count, mode == 1 ? "true" : "false",
        ap_module_activity_state_size(), ap_module_aec_state_size(),
        last.active_taps, last.block_samples, speex_frame, speex_rate, (int)speex_tail,
        speex_frame ? 2 * speex_frame : 0, ap_clipped, full_scale,
        AP_BUILD_SOURCE_REVISION) < 0)
        goto done;

    rc = 0;
done:
    if (speex) speex_echo_state_destroy(speex);
    free(activity_mem);
    free(aec_mem);
    if (in && fclose(in)) rc = 2;
    if (out && fclose(out)) rc = 2;
    if (meta && fclose(meta)) rc = 2;
    if (trace && fclose(trace)) rc = 2;
    if (rc) fputs("Speex AEC reference failed; partial files are not evidence\n", stderr);
    return rc;
}
