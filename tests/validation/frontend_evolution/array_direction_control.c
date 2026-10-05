#include "array_direction_control.h"
#include <math.h>
#include <string.h>
#ifdef __FAST_MATH__
#error "Direction control requires finite checks"
#endif
static int overlap(const void *p, size_t n, const void *q, size_t m) {
    const uintptr_t a=(uintptr_t)p, b=(uintptr_t)q;
    if(n>UINTPTR_MAX-a || m>UINTPTR_MAX-b)return 1;
    return a<b+m && b<a+n;
}
static double dot(const double a[3], const double b[3]) {
    return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
}
void fe_direction_control_reset(fe_direction_control *c) {
    if(c)memset(c,0,sizeof(*c));
}
fe_direction_result fe_direction_control_offer(fe_direction_control *c, fe_array *array,
                                                const fe_direction_observation *o) {
    fe_array_info info;
    fe_direction_control next, *destination=c;
    uint64_t gap=0u;
    uint32_t k;
    fe_array_status status;
    /* Cosines are fixed policy constants, not an acoustic optimization. */
    const double cos5=0.9961946980917455, cos15=0.9659258262890683;
    if(!c || !o || fe_array_get_info(array,&info)!=FE_ARRAY_OK)return FE_DIRECTION_INVALID;
    if(overlap(c,sizeof(*c),array,info.state_bytes) || overlap(o,sizeof(*o),array,info.state_bytes) ||
       overlap(c,sizeof(*c),o,sizeof(*o)))return FE_DIRECTION_INVALID;
    if(!isfinite(o->confidence) || o->confidence<0.0 || o->confidence>1.0 ||
       o->near_speech>1u || o->render_active>1u)return FE_DIRECTION_INVALID;
    for(k=0u;k<3u;++k)
        if(!isfinite(o->direction[k]) || fabs(o->direction[k])>1.0)return FE_DIRECTION_INVALID;
    if(fabs(dot(o->direction,o->direction)-1.0)>1.0e-6)return FE_DIRECTION_INVALID;
    if(c->seen && info.samples_processed<c->last_audio)return FE_DIRECTION_RESET_REQUIRED;
    if(o->sample_index>info.samples_processed ||
       info.samples_processed-o->sample_index>(uint64_t)(info.sample_rate_hz/50u) ||
       (c->seen && o->sample_index<=c->last_observation))return FE_DIRECTION_INVALID;
    if(info.samples_processed>UINT64_MAX-info.sample_rate_hz/5u || c->accepted==UINT64_MAX)
        return FE_DIRECTION_INVALID;
    next=*c; c=&next;
    if(c->seen)gap=o->sample_index-c->last_observation;
    c->last_audio=info.samples_processed; c->last_observation=o->sample_index; c->seen=1u;
    if(info.transition_total_samples) { c->coherent_count=0u; *destination=*c; return FE_DIRECTION_BUSY; }
    if(info.samples_processed<c->cooldown_until) { c->coherent_count=0u; *destination=*c; return FE_DIRECTION_COOLDOWN; }
    if(o->confidence<0.8 || !o->near_speech || o->render_active ||
       dot(o->direction,info.direction)>cos15) { c->coherent_count=0u; *destination=*c; return FE_DIRECTION_HOLD; }
    if(!c->coherent_count || gap>(uint64_t)(info.sample_rate_hz/50u) ||
       dot(o->direction,c->anchor)<cos5) {
        memcpy(c->anchor,o->direction,sizeof(c->anchor));
        c->coherent_count=1u; c->first_stable=o->sample_index;
    } else if(c->coherent_count<3u)++c->coherent_count;
    if(c->coherent_count<3u || o->sample_index-c->first_stable<(uint64_t)(info.sample_rate_hz/50u))
        { *destination=*c; return FE_DIRECTION_HOLD; }
    status=fe_array_request_steer(array,o->direction,info.sample_rate_hz/50u);
    c->coherent_count=0u;
    if(status!=FE_ARRAY_OK)return status==FE_ARRAY_EBUSY?FE_DIRECTION_BUSY:FE_DIRECTION_INVALID;
    c->cooldown_until=info.samples_processed+info.sample_rate_hz/5u;
    ++c->accepted;
    *destination=*c;
    return FE_DIRECTION_ACCEPTED;
}
