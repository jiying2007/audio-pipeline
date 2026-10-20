/* Private research output transition; no AEC or selector dependency. */
#ifndef DEVICE_TRANSITION_D28_H
#define DEVICE_TRANSITION_D28_H
#include <stdint.h>
#define D28_SAMPLES 320u
typedef struct { uint32_t bank, from_bank, pos, remaining; } d28_transition_t;
static void d28_reset(d28_transition_t *s) {
    s->bank=0u;s->from_bank=0u;s->pos=0u;s->remaining=0u;
}
static int d28_begin(d28_transition_t *s,uint32_t bank) {
    if (bank>1u || bank==s->bank || s->remaining) return 0;
    s->from_bank=s->bank;s->bank=bank;s->pos=0u;s->remaining=D28_SAMPLES;return 1;
}
static double d28_alpha(const d28_transition_t *s) {
    return s->remaining ? (double)s->pos/(double)(D28_SAMPLES-1u) : 1.0;
}
static float d28_mix(float old,float current,double alpha) {
    if (alpha==0.0) return old;
    if (alpha==1.0) return current;
    return (float)((double)old+alpha*((double)current-(double)old));
}
static void d28_advance(d28_transition_t *s) {
    if (s->remaining) { ++s->pos;--s->remaining; }
}
#endif
