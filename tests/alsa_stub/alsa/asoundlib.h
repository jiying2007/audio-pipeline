/* Unit-test transport declarations only. Never installed or used by HIL. */
#ifndef AP_TEST_ALSA_STUB_H
#define AP_TEST_ALSA_STUB_H

typedef struct snd_pcm snd_pcm_t;
typedef unsigned long snd_pcm_uframes_t;
typedef long snd_pcm_sframes_t;
#define SND_PCM_STREAM_CAPTURE 1
#define SND_PCM_STREAM_PLAYBACK 2
#define SND_PCM_FORMAT_S16_LE 1
#define SND_PCM_ACCESS_RW_INTERLEAVED 1

int snd_pcm_open(snd_pcm_t **pcm, const char *name, int stream, int flags);
int snd_pcm_close(snd_pcm_t *pcm);
int snd_pcm_set_params(snd_pcm_t *pcm, int format, int access, unsigned channels,
                       unsigned rate, int resample, unsigned latency);
const char *snd_strerror(int error);
int snd_pcm_recover(snd_pcm_t *pcm, int error, int silent);
snd_pcm_sframes_t snd_pcm_writei(snd_pcm_t *pcm, const void *data,
                                 snd_pcm_uframes_t frames);
snd_pcm_sframes_t snd_pcm_readi(snd_pcm_t *pcm, void *data,
                                snd_pcm_uframes_t frames);
int snd_pcm_drop(snd_pcm_t *pcm);
int snd_pcm_prepare(snd_pcm_t *pcm);

#endif
