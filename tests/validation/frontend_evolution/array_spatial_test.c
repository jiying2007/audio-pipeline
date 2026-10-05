#include "array_native.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr,"spatial check line %d\n",__LINE__); return 1; } } while (0)
static fe_array_config config(unsigned n, unsigned rate) {
    fe_array_config c; unsigned i; memset(&c,0,sizeof(c));
    c.mic_count=n;c.sample_rate_hz=rate;c.active_mask=(1u<<n)-1u;
    c.direction[1]=1;c.interpolation=FE_ARRAY_SPATIAL33;
    for (i=0;i<n;++i) {c.microphones[i].position_m[0]=0.01*(double)i;c.microphones[i].gain=1;c.microphones[i].input_channel=n-i-1u;}
    return c;
}
static void coefficients(float *a,float *b,unsigned n) {
    unsigned i; memset(a,0,132*sizeof(float));memset(b,0,132*sizeof(float));
    for (i=0;i<n;++i) {a[i*33u+16u]=1.0f/(float)n;b[i*33u+15u]=0.75f/(float)n;b[i*33u+17u]=0.25f/(float)n;}
}
int main(void) {
    static const unsigned rates[]={8000,16000,24000,32000,48000},counts[]={1,2,4};
    _Alignas(16) unsigned char arena[4096],other[4096],saved[4096];
    float a[132],b[132],bad[132],input[4*960],out[960],split[960],old[960],fresh[960];
    unsigned r,nv,case_count=0,stress=0;
    for (r=0;r<5;++r) for(nv=0;nv<3;++nv) {
        unsigned n=counts[nv],rate=rates[r],hop=rate/100u,t,i,k;size_t bytes;
        fe_array_config c=config(n,rate);fe_array *s=NULL,*q=NULL;fe_array_info info;
        double dir[3]={1,0,0};coefficients(a,b,n);bytes=fe_array_state_bytes_for_mode(n,FE_ARRAY_SPATIAL33);
        CHECK(bytes<=sizeof(arena));memset(arena,0xa5,sizeof(arena));
        CHECK(fe_array_init_spatial33(arena,bytes-1,&c,a,n*33u,&s)==FE_ARRAY_ENOMEM && s==NULL);
        for(i=0;i<sizeof(arena);++i)CHECK(arena[i]==0xa5);
        CHECK(fe_array_init(arena,bytes,&c,&s)==FE_ARRAY_EINVAL && s==NULL);
        CHECK(fe_array_init_spatial33(arena,bytes,&c,NULL,n*33u,&s)==FE_ARRAY_EINVAL && s==NULL);
        CHECK(fe_array_init_spatial33(arena,bytes,&c,a,n*33u,&s)==FE_ARRAY_OK);
        for(i=(unsigned)bytes;i<sizeof(arena);++i)CHECK(arena[i]==0xa5);
        CHECK(fe_array_get_info(s,&info)==FE_ARRAY_OK && info.state_bytes==bytes);
        for(t=0;t<2u*hop;++t)for(i=0;i<n;++i)input[t*n+i]=(float)((int)((t*7u+i*11u)%61u)-30)/128.0f;
        CHECK(fe_array_process(s,input,hop*n,out,hop)==FE_ARRAY_OK);
        CHECK(fe_array_process(s,input+hop*n,hop*n,out+hop,hop)==FE_ARRAY_OK);
        for(t=0;t<2u*hop;++t) {
            double expected=0;
            for(i=0;i<n;++i)for(k=0;k<33;++k) {
                unsigned delay=info.common_delay_samples-16u+k;
                if(t>=delay)expected+=(double)a[i*33u+k]*input[(t-delay)*n+c.microphones[i].input_channel];
            }
            CHECK(fabs(expected-out[t])<2e-6);
        }
        CHECK(fe_array_reset(s)==FE_ARRAY_OK);
        for(t=0;t<2u*hop;++t)CHECK(fe_array_process(s,input+t*n,n,split+t,1)==FE_ARRAY_OK);
        CHECK(memcmp(out,split,2u*hop*sizeof(float))==0);
        memcpy(saved,arena,bytes);memcpy(bad,a,sizeof(a));bad[0]=NAN;
        CHECK(fe_array_request_spatial33(s,dir,bad,n*33u,hop)==FE_ARRAY_EINVAL && memcmp(saved,arena,bytes)==0);
        CHECK(fe_array_request_spatial33(s,dir,b,n*33u-1,hop)==FE_ARRAY_EINVAL && memcmp(saved,arena,bytes)==0);
        CHECK(fe_array_request_spatial33(s,dir,(float*)arena,n*33u,hop)==FE_ARRAY_EINVAL && memcmp(saved,arena,bytes)==0);
        CHECK(fe_array_request_steer(s,dir,hop)==FE_ARRAY_EINVAL && memcmp(saved,arena,bytes)==0);
        if(n>1)CHECK(fe_array_set_active_mask(s,1)==FE_ARRAY_EINVAL && memcmp(saved,arena,bytes)==0);
        CHECK(fe_array_request_spatial33(s,c.direction,a,n*33u,hop)==FE_ARRAY_OK && memcmp(saved,arena,bytes)==0);
        CHECK(fe_array_reset(s)==FE_ARRAY_OK);
        CHECK(fe_array_init_spatial33(other,bytes,&c,b,n*33u,&q)==FE_ARRAY_OK);
        CHECK(fe_array_process(s,input,hop*n,old,hop)==FE_ARRAY_OK);
        CHECK(fe_array_process(q,input,hop*n,fresh,hop)==FE_ARRAY_OK);
        CHECK(fe_array_request_spatial33(s,c.direction,b,n*33u,hop)==FE_ARRAY_OK); /* same direction, new bank */
        memcpy(saved,arena,bytes);
        CHECK(fe_array_request_spatial33(s,dir,a,n*33u,hop)==FE_ARRAY_EBUSY && memcmp(saved,arena,bytes)==0);
        CHECK(fe_array_process(s,input+hop*n,hop*n,out,hop)==FE_ARRAY_OK);
        CHECK(fe_array_process(q,input+hop*n,hop*n,fresh,hop)==FE_ARRAY_OK);
        for(t=0;t<hop;++t) {
            double expected_old=0;unsigned at=hop+t;
            for(i=0;i<n;++i)expected_old+=(double)a[i*33u+16u]*input[(at-info.common_delay_samples)*n+c.microphones[i].input_channel];
            double alpha=(double)t/(hop-1u),expected=(1-alpha)*expected_old+alpha*fresh[t];
            CHECK(fabs(out[t]-expected)<2e-6);
        }
        CHECK(out[hop-1u]==fresh[hop-1u]);
        CHECK(fe_array_get_info(s,&info)==FE_ARRAY_OK && info.steering_completed==1 && info.transition_total_samples==0);
        for(i=0;i<16;++i) {CHECK(fe_array_reset(s)==FE_ARRAY_OK);for(t=0;t<32;++t){CHECK(fe_array_process(s,input,hop*n,out,hop)==FE_ARRAY_OK);++stress;}}
        memcpy(saved,arena,bytes);input[hop*n-1u]=NAN;
        CHECK(fe_array_process(s,input,hop*n,out,hop)==FE_ARRAY_EINVAL && memcmp(saved,arena,bytes)==0);
        ++case_count;
    }
    printf("{\"status\":\"PASS\",\"configurations\":%u,\"assertions\":%u,\"stress_frames\":%u,\"state_bytes_4\":%zu}\n",case_count,checks,stress,fe_array_state_bytes_for_mode(4,FE_ARRAY_SPATIAL33));
    return 0;
}
