#include "frontend/ap_resampler.h"
#include <stdint.h>
#include <string.h>

static float ap_s16_to_f32(int16_t x) { return (float)x * (1.0f / 32768.0f); }
static float ap_clamp(float x, float lo, float hi) { return x < lo ? lo : (x > hi ? hi : x); }
static int16_t ap_f32_to_s16(float x) {
    const float y = ap_clamp(x, -0.999969f, 0.999969f) * 32768.0f;
    return (int16_t)(y >= 0.0f ? y + 0.5f : y - 0.5f);
}

void ap_resampler_init(ap_resampler_state_t *s) { memset(s, 0, sizeof(*s)); }
void ap_resampler_reset(ap_resampler_state_t *s) { ap_resampler_init(s); }

int ap_supported_io_rate(uint32_t hz) {
    return hz == 8000u || hz == 16000u || hz == 24000u || hz == 32000u || hz == 48000u;
}

#if defined(AP_BUILD_RESAMPLER_BANDLIMITED)
static const float ap_fir_2x[11] = {
    0.003576532f,-0.007797274f,-0.037354116f,0.033318692f,0.284801475f,
    0.446909380f,0.284801475f,0.033318692f,-0.037354116f,-0.007797274f,0.003576532f};
static const float ap_fir_3x[15] = {
    0.001118295f,-0.003894765f,-0.016034917f,-0.020363771f,0.020951807f,
    0.124497813f,0.244506832f,0.298437412f,0.244506832f,0.124497813f,
    0.020951807f,-0.020363771f,-0.016034917f,-0.003894765f,0.001118295f};
static const float ap_fir_4x[15] = {
    -0.003587446f,-0.006018985f,-0.006255848f,0.010914446f,0.058936550f,
    0.131812053f,0.200104829f,0.228188802f,0.200104829f,0.131812053f,
    0.058936550f,0.010914446f,-0.006255848f,-0.006018985f,-0.003587446f};
static const float ap_fir_6x[15] = {
    -0.000657576f,0.002378398f,0.013170169f,0.038272379f,0.077785502f,
    0.123013466f,0.159374828f,0.173325667f,0.159374828f,0.123013466f,
    0.077785502f,0.038272379f,0.013170169f,0.002378398f,-0.000657576f};
static const float ap_fir_3to2[11] = {
    0.0f,0.012698117f,-0.024801914f,-0.063787150f,0.276018100f,
    0.599745691f,0.276018100f,-0.063787150f,-0.024801914f,0.012698117f,0.0f};

typedef struct ap_fir_desc { const float *h; uint32_t taps; } ap_fir_desc_t;
static ap_fir_desc_t ap_fir_for_ratio(uint32_t in_frames, uint32_t out_frames) {
    ap_fir_desc_t d = {0,0};
    if (in_frames == out_frames || in_frames < out_frames) return d;
    if (in_frames == out_frames * 2u) { d.h=ap_fir_2x; d.taps=11u; }
    else if (in_frames == out_frames * 3u) { d.h=ap_fir_3x; d.taps=15u; }
    else if (in_frames == out_frames * 4u) { d.h=ap_fir_4x; d.taps=15u; }
    else if (in_frames == out_frames * 6u) { d.h=ap_fir_6x; d.taps=15u; }
    else if (in_frames * 2u == out_frames * 3u) { d.h=ap_fir_3to2; d.taps=11u; }
    return d;
}

static float ap_hist_s16(const int16_t *in, uint32_t frames, uint32_t channels,
                         uint32_t channel, const float *hist, int32_t index) {
    if (index >= 0 && (uint32_t)index < frames)
        return ap_s16_to_f32(in[(uint32_t)index * channels + channel]);
    if (index < 0 && index >= -(int32_t)AP_RESAMPLER_HISTORY)
        return hist[AP_RESAMPLER_HISTORY + index];
    return 0.0f;
}
static float ap_hist_f32(const float *in, uint32_t frames, const float *hist, int32_t index) {
    if (index >= 0 && (uint32_t)index < frames) return in[index];
    if (index < 0 && index >= -(int32_t)AP_RESAMPLER_HISTORY)
        return hist[AP_RESAMPLER_HISTORY + index];
    return 0.0f;
}
static float ap_filter_s16(const int16_t *in, uint32_t frames, uint32_t channels,
                           uint32_t channel, const float *hist, int32_t index,
                           ap_fir_desc_t d) {
    float y=0.0f; uint32_t k;
    if (!d.taps) return ap_hist_s16(in,frames,channels,channel,hist,index);
    for(k=0u;k<d.taps;++k) y += d.h[k]*ap_hist_s16(in,frames,channels,channel,hist,index-(int32_t)k);
    return y;
}
static float ap_filter_f32(const float *in, uint32_t frames, const float *hist,
                           int32_t index, ap_fir_desc_t d) {
    float y=0.0f; uint32_t k;
    if (!d.taps) return ap_hist_f32(in,frames,hist,index);
    for(k=0u;k<d.taps;++k) y += d.h[k]*ap_hist_f32(in,frames,hist,index-(int32_t)k);
    return y;
}
static void ap_update_s16_history(float *hist, const int16_t *in, uint32_t frames,
                                  uint32_t channels, uint32_t channel) {
    uint32_t i;
    if (frames >= AP_RESAMPLER_HISTORY) {
        for(i=0u;i<AP_RESAMPLER_HISTORY;++i)
            hist[i]=ap_s16_to_f32(in[(frames-AP_RESAMPLER_HISTORY+i)*channels+channel]);
    } else {
        memmove(hist,hist+frames,(AP_RESAMPLER_HISTORY-frames)*sizeof(float));
        for(i=0u;i<frames;++i) hist[AP_RESAMPLER_HISTORY-frames+i]=ap_s16_to_f32(in[i*channels+channel]);
    }
}
static void ap_update_f32_history(float *hist, const float *in, uint32_t frames) {
    if (frames >= AP_RESAMPLER_HISTORY)
        memcpy(hist,in+frames-AP_RESAMPLER_HISTORY,AP_RESAMPLER_HISTORY*sizeof(float));
    else {
        memmove(hist,hist+frames,(AP_RESAMPLER_HISTORY-frames)*sizeof(float));
        memcpy(hist+AP_RESAMPLER_HISTORY-frames,in,frames*sizeof(float));
    }
}
#endif

static void ap_fast_input(const int16_t *in,uint32_t in_frames,uint32_t channels,uint32_t channel,float *out,uint32_t out_frames) {
    uint32_t i;
    if(in_frames==out_frames){for(i=0;i<out_frames;++i)out[i]=ap_s16_to_f32(in[i*channels+channel]);return;}
    if(in_frames>out_frames&&in_frames%out_frames==0u){uint32_t step=in_frames/out_frames;for(i=0;i<out_frames;++i)out[i]=ap_s16_to_f32(in[(i*step)*channels+channel]);return;}
    if(in_frames*2u==out_frames*3u){uint32_t src=0;for(i=0;i+1u<out_frames;i+=2u,src+=3u){out[i]=ap_s16_to_f32(in[src*channels+channel]);out[i+1u]=0.5f*(ap_s16_to_f32(in[(src+1u)*channels+channel])+ap_s16_to_f32(in[(src+2u)*channels+channel]));}return;}
    if(out_frames==in_frames*2u){for(i=0;i<in_frames;++i){uint32_t next=i+1u<in_frames?i+1u:i;float a=ap_s16_to_f32(in[i*channels+channel]);float b=ap_s16_to_f32(in[next*channels+channel]);out[2u*i]=a;out[2u*i+1u]=0.5f*(a+b);}return;}
    for(i=0;i<out_frames;++i){float pos=(float)i*(float)in_frames/(float)out_frames;uint32_t i0=(uint32_t)pos;float frac=pos-(float)i0;uint32_t i1;if(i0>=in_frames)i0=in_frames-1u;i1=i0+1u<in_frames?i0+1u:i0;out[i]=ap_s16_to_f32(in[i0*channels+channel])*(1.0f-frac)+ap_s16_to_f32(in[i1*channels+channel])*frac;}
}
static void ap_fast_output(const float *in,uint32_t in_frames,int16_t *out,uint32_t out_frames){uint32_t i;if(in_frames==out_frames){for(i=0;i<out_frames;++i)out[i]=ap_f32_to_s16(in[i]);return;}if(in_frames>out_frames&&in_frames%out_frames==0u){uint32_t step=in_frames/out_frames;for(i=0;i<out_frames;++i)out[i]=ap_f32_to_s16(in[i*step]);return;}if(out_frames*2u==in_frames*3u){uint32_t src=0;const float a=1.0f/3.0f,b=2.0f/3.0f;for(i=0;i+2u<out_frames;i+=3u,src+=2u){uint32_t n=src+1u<in_frames?src+1u:src,n2=src+2u<in_frames?src+2u:n;out[i]=ap_f32_to_s16(in[src]);out[i+1u]=ap_f32_to_s16(a*in[src]+b*in[n]);out[i+2u]=ap_f32_to_s16(b*in[n]+a*in[n2]);}return;}if(out_frames>in_frames&&out_frames%in_frames==0u){uint32_t phases=out_frames/in_frames,src=0,phase=0;float inv=1.0f/(float)phases;for(i=0;i<out_frames;++i){uint32_t n=src+1u<in_frames?src+1u:src;float f=(float)phase*inv;out[i]=ap_f32_to_s16(in[src]*(1.0f-f)+in[n]*f);if(++phase==phases){phase=0;if(src+1u<in_frames)src++;}}return;}for(i=0;i<out_frames;++i){float pos=(float)i*(float)in_frames/(float)out_frames;uint32_t i0=(uint32_t)pos;float f=pos-(float)i0;uint32_t i1;if(i0>=in_frames)i0=in_frames-1u;i1=i0+1u<in_frames?i0+1u:i0;out[i]=ap_f32_to_s16(in[i0]*(1.0f-f)+in[i1]*f);}}

void ap_resample_input_channel(ap_resampler_state_t *s,uint32_t stream,const int16_t *in,uint32_t in_frames,uint32_t channels,uint32_t channel,float *out,uint32_t out_frames){
#if defined(AP_BUILD_RESAMPLER_BANDLIMITED)
    ap_fir_desc_t d=ap_fir_for_ratio(in_frames,out_frames);uint32_t i;float *hist=s->input_history[stream];
    if(d.taps){for(i=0;i<out_frames;++i){float pos=(float)i*(float)in_frames/(float)out_frames;int32_t i0=(int32_t)pos;float f=pos-(float)i0;float a=ap_filter_s16(in,in_frames,channels,channel,hist,i0,d);float b=ap_filter_s16(in,in_frames,channels,channel,hist,i0+1,d);out[i]=a*(1.0f-f)+b*f;}ap_update_s16_history(hist,in,in_frames,channels,channel);return;}
#endif
    (void)s;(void)stream;ap_fast_input(in,in_frames,channels,channel,out,out_frames);
#if defined(AP_BUILD_RESAMPLER_BANDLIMITED)
    ap_update_s16_history(s->input_history[stream],in,in_frames,channels,channel);
#endif
}
void ap_resample_output(ap_resampler_state_t *s,const float *in,uint32_t in_frames,int16_t *out,uint32_t out_frames){
#if defined(AP_BUILD_RESAMPLER_BANDLIMITED)
    ap_fir_desc_t d=ap_fir_for_ratio(in_frames,out_frames);uint32_t i;
    if(d.taps){for(i=0;i<out_frames;++i){float pos=(float)i*(float)in_frames/(float)out_frames;int32_t i0=(int32_t)pos;float f=pos-(float)i0;float a=ap_filter_f32(in,in_frames,s->output_history,i0,d);float b=ap_filter_f32(in,in_frames,s->output_history,i0+1,d);out[i]=ap_f32_to_s16(a*(1.0f-f)+b*f);}ap_update_f32_history(s->output_history,in,in_frames);return;}
#endif
    (void)s;ap_fast_output(in,in_frames,out,out_frames);
#if defined(AP_BUILD_RESAMPLER_BANDLIMITED)
    ap_update_f32_history(s->output_history,in,in_frames);
#endif
}
uint32_t ap_resampler_filter_delay_samples(uint32_t in_frames,uint32_t out_frames){
#if defined(AP_BUILD_RESAMPLER_BANDLIMITED)
    ap_fir_desc_t d=ap_fir_for_ratio(in_frames,out_frames);return d.taps?(d.taps-1u)/2u:0u;
#else
    (void)in_frames;(void)out_frames;return 0u;
#endif
}
