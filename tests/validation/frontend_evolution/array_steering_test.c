#include "array_direction_control.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#define CHECK(x) do { if(!(x)){fprintf(stderr,"line %d: %s\n",__LINE__,#x);return 1;} ++checks; } while(0)
static unsigned checks;
static double maximum_blend_error;
static fe_array_config configuration(uint32_t n,uint32_t rate,uint32_t mode) {
    fe_array_config c; uint32_t i;
    memset(&c,0,sizeof(c)); c.sample_rate_hz=rate; c.mic_count=n;
    c.active_mask=(1u<<n)-1u; c.interpolation=(fe_array_interpolation)mode; c.direction[1]=1.0;
    for(i=0u;i<n;++i) {
        c.microphones[i].position_m[0]=0.035*(double)i;
        c.microphones[i].input_channel=n-1u-i;
        c.microphones[i].gain=i==1u?-1.25:1.0;
        c.microphones[i].latency_samples=(double)i*0.125;
    }
    return c;
}
static void signal(float *x,uint32_t n,uint32_t frames,uint32_t start) {
    uint32_t i,j;
    for(j=0u;j<frames;++j)for(i=0u;i<n;++i)
        x[j*n+i]=(float)(0.31*sin((double)(start+j)*(0.021+0.023*(double)i)));
}
static int blends(void) {
    const uint32_t ns[]={1u,2u,4u}, rates[]={8000u,16000u,24000u,32000u,48000u};
    size_t a,r; uint32_t mode,choice;
    for(a=0u;a<3u;++a)for(r=0u;r<5u;++r)for(mode=0u;mode<2u;++mode)for(choice=0u;choice<4u;++choice) {
        _Alignas(16) unsigned char old_memory[4096],new_memory[4096],fade_memory[4096],split_memory[4096];
        fe_array_config c=configuration(ns[a],rates[r],mode), target=c;
        fe_array *old=NULL,*next=NULL,*fade=NULL,*split=NULL;
        fe_array_info info,old_info;
        float input[1920],yo[480],yn[480],yf[480],ys[480];
        const uint32_t hop=rates[r]/100u, durations[]={2u,17u,hop,2u*hop}, total=durations[choice];
        uint32_t frame,t; uint64_t progress=0u;
        target.direction[0]=0.6;target.direction[1]=0.8;
        CHECK(fe_array_init(old_memory,sizeof(old_memory),&c,&old)==FE_ARRAY_OK);
        CHECK(fe_array_init(new_memory,sizeof(new_memory),&target,&next)==FE_ARRAY_OK);
        CHECK(fe_array_init(fade_memory,sizeof(fade_memory),&c,&fade)==FE_ARRAY_OK);
        CHECK(fe_array_init(split_memory,sizeof(split_memory),&c,&split)==FE_ARRAY_OK);
        for(frame=0u;frame<3u;++frame) {
            signal(input,c.mic_count,hop,frame*hop);
            CHECK(fe_array_process(old,input,c.mic_count*hop,yo,hop)==FE_ARRAY_OK);
            CHECK(fe_array_process(next,input,c.mic_count*hop,yn,hop)==FE_ARRAY_OK);
            CHECK(fe_array_process(fade,input,c.mic_count*hop,yf,hop)==FE_ARRAY_OK);
            CHECK(fe_array_process(split,input,c.mic_count*hop,ys,hop)==FE_ARRAY_OK);
        }
        CHECK(fe_array_request_steer(fade,target.direction,total)==FE_ARRAY_OK);
        CHECK(fe_array_request_steer(split,target.direction,total)==FE_ARRAY_OK);
        for(frame=3u;frame<7u;++frame) {
            signal(input,c.mic_count,hop,frame*hop);
            CHECK(fe_array_process(old,input,c.mic_count*hop,yo,hop)==FE_ARRAY_OK);
            CHECK(fe_array_process(next,input,c.mic_count*hop,yn,hop)==FE_ARRAY_OK);
            CHECK(fe_array_process(fade,input,c.mic_count*hop,yf,hop)==FE_ARRAY_OK);
            for(t=0u;t<hop;++t)CHECK(fe_array_process(split,input+t*c.mic_count,c.mic_count,ys+t,1u)==FE_ARRAY_OK);
            CHECK(memcmp(yf,ys,hop*sizeof(float))==0);
            for(t=0u;t<hop;++t,++progress) {
                const double alpha=progress>=total?1.0:(double)progress/(double)(total-1u);
                const double expected=(1.0-alpha)*(double)yo[t]+alpha*(double)yn[t];
                const double error=fabs(expected-(double)yf[t]);
                if(error>maximum_blend_error)maximum_blend_error=error;
                CHECK(error<2.0e-6);
                if(progress==0u)CHECK(memcmp(yf+t,yo+t,sizeof(float))==0);
                if(progress>=total-1u)CHECK(memcmp(yf+t,yn+t,sizeof(float))==0);
            }
        }
        CHECK(fe_array_get_info(fade,&info)==FE_ARRAY_OK && fe_array_get_info(old,&old_info)==FE_ARRAY_OK);
        CHECK(info.common_delay_samples==old_info.common_delay_samples && info.samples_processed==old_info.samples_processed);
        CHECK(!info.transition_total_samples && info.steering_accepted==1u && info.steering_completed==1u);
        CHECK(memcmp(info.direction,target.direction,sizeof(info.direction))==0);
        CHECK(fe_array_reset(fade)==FE_ARRAY_OK && fe_array_reset(next)==FE_ARRAY_OK);
        CHECK(fe_array_process(fade,input,c.mic_count*hop,yf,hop)==FE_ARRAY_OK);
        CHECK(fe_array_process(next,input,c.mic_count*hop,yn,hop)==FE_ARRAY_OK && memcmp(yf,yn,hop*sizeof(float))==0);
    }
    return 0;
}
static int atomic_and_faults(void) {
    _Alignas(16) unsigned char memory[4096]={0},saved[4096];
    fe_array_config c=configuration(4u,16000u,1u); fe_array *s=NULL;
    double target[]={1.0,0.0,0.0},bad[]={NAN,0.0,0.0};
    float x[640]={0},y[160]; fe_array_info info;
    CHECK(fe_array_init(memory,sizeof(memory),&c,&s)==FE_ARRAY_OK);
    memcpy(saved,memory,sizeof(memory));
    CHECK(fe_array_request_steer(NULL,target,320u)==FE_ARRAY_ESTATE);
    CHECK(fe_array_request_steer(s,NULL,320u)==FE_ARRAY_EINVAL);
    CHECK(fe_array_request_steer(s,bad,320u)==FE_ARRAY_EINVAL);
    bad[0]=2.0;CHECK(fe_array_request_steer(s,bad,320u)==FE_ARRAY_EINVAL);
    CHECK(fe_array_request_steer(s,target,1u)==FE_ARRAY_EINVAL);
    CHECK(fe_array_request_steer(s,target,1601u)==FE_ARRAY_EINVAL);
    CHECK(fe_array_request_steer(s,(double *)memory,320u)==FE_ARRAY_EINVAL);
    CHECK(fe_array_request_steer(s,c.direction,320u)==FE_ARRAY_OK);
    CHECK(memcmp(saved,memory,sizeof(memory))==0);
    CHECK(fe_array_request_steer(s,target,320u)==FE_ARRAY_OK);memcpy(saved,memory,sizeof(memory));
    CHECK(fe_array_request_steer(s,target,320u)==FE_ARRAY_EBUSY);
    x[639]=NAN;CHECK(fe_array_process(s,x,640u,y,160u)==FE_ARRAY_EINVAL);
    CHECK(fe_array_set_active_mask(s,15u)==FE_ARRAY_OK);
    CHECK(fe_array_set_active_mask(s,0u)==FE_ARRAY_EINVAL);
    CHECK(memcmp(saved,memory,sizeof(memory))==0);
    x[639]=0.0f;CHECK(fe_array_process(s,x,640u,y,160u)==FE_ARRAY_OK);
    CHECK(fe_array_set_active_mask(s,7u)==FE_ARRAY_OK);
    CHECK(fe_array_get_info(s,&info)==FE_ARRAY_OK && !info.transition_total_samples && info.steering_cancelled==1u);
    CHECK(memcmp(info.direction,c.direction,sizeof(info.direction))==0);
    CHECK(fe_array_request_steer(s,target,320u)==FE_ARRAY_OK);
    CHECK(fe_array_process(s,x,640u,y,160u)==FE_ARRAY_OK && fe_array_reset(s)==FE_ARRAY_OK);
    CHECK(fe_array_get_info(s,&info)==FE_ARRAY_OK && !info.transition_total_samples && !info.steering_accepted && !info.samples_processed);
    CHECK(memcmp(info.direction,c.direction,sizeof(info.direction))==0);
    return 0;
}
static int tick(fe_array *s) {float x[640]={0},y[160];return fe_array_process(s,x,640u,y,160u)==FE_ARRAY_OK;}
static fe_direction_observation observation(fe_array *s) {
    fe_direction_observation o;fe_array_info i;memset(&o,0,sizeof(o));
    (void)fe_array_get_info(s,&i);o.sample_index=i.samples_processed;o.direction[0]=1.0;o.confidence=0.9;o.near_speech=1u;return o;
}
static int control(void) {
    _Alignas(16) unsigned char memory[4096]={0},saved[4096];
    fe_array_config cfg=configuration(4u,16000u,1u);fe_array *s=NULL;fe_array_info info;
    fe_direction_control c,before;fe_direction_observation o;uint32_t i;
    CHECK(fe_array_init(memory,sizeof(memory),&cfg,&s)==FE_ARRAY_OK);fe_direction_control_reset(&c);
    for(i=0u;i<3u;++i){CHECK(tick(s));o=observation(s);CHECK(fe_direction_control_offer(&c,s,&o)==(i==2u?FE_DIRECTION_ACCEPTED:FE_DIRECTION_HOLD));}
    CHECK(c.accepted==1u && c.cooldown_until==3680u);
    CHECK(tick(s));o=observation(s);CHECK(fe_direction_control_offer(&c,s,&o)==FE_DIRECTION_BUSY);
    CHECK(tick(s));o=observation(s);CHECK(fe_direction_control_offer(&c,s,&o)==FE_DIRECTION_COOLDOWN);
    CHECK(fe_array_get_info(s,&info)==FE_ARRAY_OK && info.steering_completed==1u);
    /* Invalid observations are atomic even while other control states are active. */
    for(i=0u;i<7u;++i) {
        o=observation(s);before=c;memcpy(saved,memory,sizeof(memory));
        switch(i){case 0:o.sample_index++;break;case 1:o.sample_index=0u;break;case 2:o.confidence=NAN;break;
        case 3:o.direction[0]=2.0;break;case 4:o.near_speech=2u;break;case 5:o.render_active=2u;break;default:break;}
        CHECK(fe_direction_control_offer(&c,s,&o)==FE_DIRECTION_INVALID);
        CHECK(memcmp(&c,&before,sizeof(c))==0 && memcmp(saved,memory,sizeof(memory))==0);
    }
    CHECK(fe_array_reset(s)==FE_ARRAY_OK);o=observation(s);before=c;
    CHECK(fe_direction_control_offer(&c,s,&o)==FE_DIRECTION_RESET_REQUIRED && memcmp(&c,&before,sizeof(c))==0);
    CHECK(fe_array_init(memory,sizeof(memory),&cfg,&s)==FE_ARRAY_OK);fe_direction_control_reset(&c);
    for(i=0u;i<30u;++i){CHECK(tick(s));o=observation(s);o.direction[0]=i%2u?1.0:-1.0;CHECK(fe_direction_control_offer(&c,s,&o)==FE_DIRECTION_HOLD);}
    CHECK(!c.accepted);
    for(i=0u;i<3u;++i){CHECK(tick(s));o=observation(s);
        if(i==0u)o.confidence=0.79;else if(i==1u)o.near_speech=0u;else o.render_active=1u;
        CHECK(fe_direction_control_offer(&c,s,&o)==FE_DIRECTION_HOLD && !c.coherent_count);}
    CHECK(fe_array_get_info(s,&info)==FE_ARRAY_OK && info.steering_accepted==0u);
    /* Direction outside ring reach must reject without committing controller state. */
    cfg.sample_rate_hz=48000u;cfg.mic_count=2u;cfg.active_mask=3u;cfg.direction[0]=-1.;cfg.direction[1]=0.;
    cfg.microphones[0].input_channel=0u;cfg.microphones[1].input_channel=1u;
    cfg.microphones[1].position_m[0]=0.6;
    CHECK(fe_array_init(memory,sizeof(memory),&cfg,&s)==FE_ARRAY_OK);fe_direction_control_reset(&c);
    for(i=0u;i<3u;++i) {
        float x[960]={0},y[480];CHECK(fe_array_process(s,x,960u,y,480u)==FE_ARRAY_OK);
        o=observation(s);before=c;memcpy(saved,memory,sizeof(memory));
        CHECK(fe_direction_control_offer(&c,s,&o)==(i==2u?FE_DIRECTION_INVALID:FE_DIRECTION_HOLD));
        if(i==2u)CHECK(memcmp(&c,&before,sizeof(c))==0 && memcmp(saved,memory,sizeof(memory))==0);
    }
    return 0;
}
static int policy_boundaries(void) {
    _Alignas(16) unsigned char memory[4096];fe_array *s=NULL;
    fe_array_config cfg=configuration(4u,16000u,1u);fe_direction_control c;
    fe_direction_observation o;float input[1280]={0},output[320];uint32_t i;
    CHECK(fe_array_init(memory,sizeof(memory),&cfg,&s)==FE_ARRAY_OK);fe_direction_control_reset(&c);
    for(i=0u;i<3u;++i) {
        CHECK(fe_array_process(s,input,4u,output,1u)==FE_ARRAY_OK);o=observation(s);o.confidence=0.8;
        CHECK(fe_direction_control_offer(&c,s,&o)==FE_DIRECTION_HOLD);
    }
    CHECK(c.coherent_count==3u && c.accepted==0u); /* Three packets alone do not satisfy 20ms. */
    CHECK(fe_array_process(s,input,4u*160u,output,160u)==FE_ARRAY_OK);
    CHECK(fe_array_process(s,input,4u*158u,output,158u)==FE_ARRAY_OK);
    o=observation(s);o.confidence=0.8;
    CHECK(fe_direction_control_offer(&c,s,&o)==FE_DIRECTION_ACCEPTED && c.accepted==1u);
    CHECK(fe_array_init(memory,sizeof(memory),&cfg,&s)==FE_ARRAY_OK);fe_direction_control_reset(&c);
    CHECK(tick(s));o=observation(s);CHECK(fe_direction_control_offer(&c,s,&o)==FE_DIRECTION_HOLD);
    CHECK(tick(s) && tick(s) && tick(s));o=observation(s);
    CHECK(fe_direction_control_offer(&c,s,&o)==FE_DIRECTION_HOLD && c.coherent_count==1u); /* gap >20ms */
    for(i=0u;i<3u;++i){CHECK(tick(s));o=observation(s);o.direction[0]=0.1;o.direction[1]=sqrt(0.99);
        CHECK(fe_direction_control_offer(&c,s,&o)==FE_DIRECTION_HOLD && c.coherent_count==0u);}
    for(i=0u;i<3u;++i){double angle=(double)i*4.0*3.141592653589793/180.0;
        CHECK(tick(s));o=observation(s);o.direction[0]=cos(angle);o.direction[1]=sin(angle);
        CHECK(fe_direction_control_offer(&c,s,&o)==FE_DIRECTION_HOLD);}
    CHECK(c.coherent_count==1u); /* Coherence is to anchor, not creeping pairwise drift. */
    CHECK(fe_array_init(memory,sizeof(memory),&cfg,&s)==FE_ARRAY_OK);fe_direction_control_reset(&c);
    for(i=0u;i<3u;++i){CHECK(tick(s));o=observation(s);CHECK(fe_direction_control_offer(&c,s,&o)==(i==2u?FE_DIRECTION_ACCEPTED:FE_DIRECTION_HOLD));}
    for(i=0u;i<20u;++i)CHECK(tick(s));
    o=observation(s);o.direction[0]=-1.0;
    CHECK(o.sample_index==c.cooldown_until);
    CHECK(fe_direction_control_offer(&c,s,&o)==FE_DIRECTION_HOLD && c.coherent_count==1u);
    return 0;
}
static int stress(void) {
    _Alignas(16) unsigned char memory[4096];fe_array_config c=configuration(4u,16000u,1u);fe_array *s=NULL;
    float x[640],y[160],previous[160];uint32_t cycle,frame;double d[]={1.,0.,0.};
    signal(x,4u,160u,17u);
    for(cycle=0u;cycle<64u;++cycle) {
        CHECK(fe_array_init(memory,sizeof(memory),&c,&s)==FE_ARRAY_OK);
        for(frame=0u;frame<500u;++frame) {
            if(frame%10u==0u){d[0]=(frame/10u)%2u?1.:-1.;CHECK(fe_array_request_steer(s,d,320u)==FE_ARRAY_OK);}
            CHECK(fe_array_process(s,x,640u,y,160u)==FE_ARRAY_OK);
        }
        if(cycle)CHECK(memcmp(previous,y,sizeof(y))==0);
        memcpy(previous,y,sizeof(y));
    }
    return 0;
}
int main(void) {
    if(blends() || atomic_and_faults() || control() || policy_boundaries() || stress())return 1;
    printf("{\"status\":\"PASS\",\"assertions\":%u,\"blend_configurations\":120,\"stress_frames\":32000,\"lifecycles\":64,\"maximum_blend_error\":%.17g,\"array_state_bytes\":%zu,\"controller_state_bytes\":%zu}\n",checks,maximum_blend_error,fe_array_state_bytes(4u),sizeof(fe_direction_control));return 0;
}
