/* First-party engineering tests; no upstream coefficients or recorded audio. */
#include "array_native.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr,"FIR line %d: %s\n",__LINE__,#x); return 1; } ++checks; } while (0)
static unsigned checks;
static fe_array_config config(uint32_t rate, uint32_t n, unsigned mode) {
    fe_array_config c; uint32_t i;
    memset(&c,0,sizeof(c)); c.sample_rate_hz=rate; c.mic_count=n;
    c.active_mask=(1u<<n)-1u; c.interpolation=(fe_array_interpolation)mode;
    c.direction[0]=0.6; c.direction[1]=0.8;
    for(i=0u;i<n;++i) {
        c.microphones[i].position_m[0]=0.021*(double)i;
        c.microphones[i].input_channel=n-1u-i;
        c.microphones[i].gain=1.0;
        c.microphones[i].latency_samples=(double)i*0.125;
    }
    return c;
}
static int one(uint32_t rate,uint32_t n,unsigned mode) {
    _Alignas(16) unsigned char a[4096],b[4096],saved[4096];
    float x[1920], y[480], z[480];
    const double direction[3]={-0.6,0.8,0.0}, invalid[3]={NAN,0.0,0.0};
    fe_array_config c=config(rate,n,mode); fe_array *s=NULL,*other=NULL; fe_array_info info;
    size_t size=fe_array_state_bytes_for_mode(n,c.interpolation), hop=rate/100u, j;
    uint32_t block;
    CHECK(size==fe_array_state_bytes(n)+2u*n*(mode==2u?17u:33u)*sizeof(float));
    CHECK(size<sizeof(a)); memset(a,0xa5,sizeof(a));memcpy(saved,a,sizeof(a));
    CHECK(fe_array_init(a,size-1u,&c,&s)==FE_ARRAY_ENOMEM && !s);
    CHECK(memcmp(a,saved,sizeof(a))==0);
    CHECK(fe_array_init(a,size,&c,&s)==FE_ARRAY_OK);
    CHECK(memcmp(a+size,saved+size,sizeof(a)-size)==0);
    CHECK(fe_array_init(b,size,&c,&other)==FE_ARRAY_OK);
    CHECK(fe_array_get_info(s,&info)==FE_ARRAY_OK && info.state_bytes==size);
    for(j=0u;j<hop*n;++j)x[j]=(float)((int)(j%43u)-21)/64.0f;
    memcpy(saved,a,sizeof(a));
    CHECK(fe_array_request_steer(s,invalid,2u)==FE_ARRAY_EINVAL);
    CHECK(memcmp(saved,a,sizeof(a))==0);
    /* Alias rejection must cover the FIR tail, not just the legacy arena. */
    CHECK(fe_array_process(s,x,hop*n,(float *)(a+fe_array_state_bytes(n)),hop)==FE_ARRAY_EINVAL);
    CHECK(memcmp(saved,a,sizeof(a))==0);
    for(block=0u;block<8u;++block) {
        if(block==2u) {
            CHECK(fe_array_request_steer(s,direction,rate/50u)==FE_ARRAY_OK);
            CHECK(fe_array_request_steer(other,direction,rate/50u)==FE_ARRAY_OK);
            memcpy(saved,a,sizeof(a));
            CHECK(fe_array_request_steer(s,direction,2u)==FE_ARRAY_EBUSY);
            CHECK(memcmp(saved,a,sizeof(a))==0);
        }
        CHECK(fe_array_process(s,x,hop*n,y,hop)==FE_ARRAY_OK);
        for(j=0u;j<hop;++j)CHECK(fe_array_process(other,x+j*n,n,z+j,1u)==FE_ARRAY_OK);
        CHECK(memcmp(y,z,hop*sizeof(float))==0);
    }
    CHECK(fe_array_get_info(s,&info)==FE_ARRAY_OK && info.steering_completed==1u);
    CHECK(fe_array_request_steer(s,c.direction,rate/50u)==FE_ARRAY_OK);
    CHECK(fe_array_process(s,x,hop*n,y,hop)==FE_ARRAY_OK);
    CHECK(fe_array_reset(s)==FE_ARRAY_OK);
    memcpy(c.direction,direction,sizeof(direction));
    CHECK(fe_array_init(b,size,&c,&other)==FE_ARRAY_OK);
    CHECK(fe_array_process(s,x,hop*n,y,hop)==FE_ARRAY_OK);
    CHECK(fe_array_process(other,x,hop*n,z,hop)==FE_ARRAY_OK);
    CHECK(memcmp(y,z,hop*sizeof(float))==0);
    if(n==4u) {
        CHECK(fe_array_set_active_mask(s,7u)==FE_ARRAY_OK);
        /* physical mic 3 maps to input channel 0 */
        for(j=0u;j<hop;++j)x[j*n]=NAN;
        CHECK(fe_array_process(s,x,hop*n,y,hop)==FE_ARRAY_OK);
        for(j=0u;j<hop;++j)CHECK(isfinite(y[j]));
        CHECK(fe_array_set_active_mask(s,15u)==FE_ARRAY_OK);
        memcpy(saved,a,sizeof(a));
        CHECK(fe_array_process(s,x,hop*n,y,hop)==FE_ARRAY_EINVAL);
        CHECK(memcmp(saved,a,sizeof(a))==0);
    }
    CHECK(fe_array_get_info(s,&info)==FE_ARRAY_OK);
    CHECK(memcmp(a+size,saved+size,sizeof(a)-size)==0);
    return 0;
}
static int integer_delay(unsigned mode) {
    _Alignas(16) unsigned char arena[4096]; fe_array *s=NULL; fe_array_info info;
    fe_array_config c=config(16000u,1u,mode); float x[160],y[160];size_t j;
    CHECK(fe_array_init(arena,sizeof(arena),&c,&s)==FE_ARRAY_OK);
    CHECK(fe_array_get_info(s,&info)==FE_ARRAY_OK);
    for(j=0u;j<160u;++j)x[j]=(float)j/512.0f;
    CHECK(fe_array_process(s,x,160u,y,160u)==FE_ARRAY_OK);
    for(j=0u;j<160u;++j)CHECK(y[j]==(j<info.common_delay_samples?0.0f:x[j-info.common_delay_samples]));
    return 0;
}
static int stress(void) {
    _Alignas(16) unsigned char arena[4096]; fe_array *s=NULL; fe_array_info info;
    float x[640],y[160]; unsigned mode,cycle,frame,j; double direction[3]={-0.6,0.8,0.0};
    for(j=0u;j<640u;++j)x[j]=(float)((int)(j%47u)-23)/128.0f;
    for(mode=2u;mode<=3u;++mode)for(cycle=0u;cycle<16u;++cycle) {
        fe_array_config c=config(16000u,4u,mode);
        CHECK(fe_array_init(arena,sizeof(arena),&c,&s)==FE_ARRAY_OK);
        for(frame=0u;frame<256u;++frame) {
            if(frame==37u)CHECK(fe_array_request_steer(s,direction,320u)==FE_ARRAY_OK);
            if(frame==83u)CHECK(fe_array_set_active_mask(s,7u)==FE_ARRAY_OK);
            if(frame==101u)CHECK(fe_array_set_active_mask(s,15u)==FE_ARRAY_OK);
            if(frame==139u)CHECK(fe_array_reset(s)==FE_ARRAY_OK);
            CHECK(fe_array_process(s,x,640u,y,160u)==FE_ARRAY_OK);
            for(j=0u;j<160u;++j)CHECK(isfinite(y[j]));
        }
        CHECK(fe_array_get_info(s,&info)==FE_ARRAY_OK);
        CHECK(info.samples_processed==117u*160u);
    }
    return 0;
}
static int benchmark(void) {
    _Alignas(16) unsigned char arena[4096]; fe_array *s=NULL;
    float x[640],y[160]; unsigned mode,j,frame; volatile float checksum=0.0f;
    for(j=0u;j<640u;++j)x[j]=(float)((int)(j%47u)-23)/128.0f;
    printf("{\"authority\":\"HOST_CPU_ONLY_NOT_DUT\",\"audio_seconds_per_arm\":40.96,\"arms\":[");
    for(mode=1u;mode<=3u;++mode) {
        const fe_array_config c=config(16000u,4u,mode); clock_t begin,end;
        CHECK(fe_array_init(arena,sizeof(arena),&c,&s)==FE_ARRAY_OK);
        begin=clock(); CHECK(begin!=(clock_t)-1);
        for(frame=0u;frame<4096u;++frame) {
            if(fe_array_process(s,x,640u,y,160u)!=FE_ARRAY_OK)return 1;
            checksum+=y[frame%160u];
        }
        end=clock();CHECK(end>=begin);
        printf("%s{\"mode\":%u,\"cpu_ms_per_audio_second\":%.9g,\"state_bytes\":%zu}",
               mode==1u?"":",",mode,1000.0*(double)(end-begin)/(double)CLOCKS_PER_SEC/40.96,
               fe_array_state_bytes_for_mode(4u,c.interpolation));
    }
    printf("],\"checksum\":%.9g}\n",(double)checksum);return 0;
}
int main(int argc,char **argv) {
    const uint32_t rates[]={8000u,16000u,24000u,32000u,48000u},counts[]={1u,2u,4u};
    unsigned i,j,mode;
    if(argc==2 && strcmp(argv[1],"--benchmark")==0)return benchmark();
    if(argc!=1)return 2;
    CHECK(fe_array_state_bytes_for_mode(3u,FE_ARRAY_FIR17_HANN)==0u);
    CHECK(fe_array_state_bytes_for_mode(4u,(fe_array_interpolation)99)==0u);
    CHECK(fe_array_state_bytes_for_mode(4u,FE_ARRAY_LAGRANGE3)==fe_array_state_bytes(4u));
    for(i=0u;i<5u;++i)for(j=0u;j<3u;++j)for(mode=2u;mode<=3u;++mode)CHECK(one(rates[i],counts[j],mode)==0);
    CHECK(integer_delay(2u)==0);CHECK(integer_delay(3u)==0);CHECK(stress()==0);
    printf("{\"status\":\"PASS\",\"assertions\":%u,\"configurations\":30,\"stress_frames\":8192,\"lifecycles\":32,\"state_bytes_4mic\":[%zu,%zu,%zu]}\n",
           checks,fe_array_state_bytes(4u),fe_array_state_bytes_for_mode(4u,FE_ARRAY_FIR17_HANN),fe_array_state_bytes_for_mode(4u,FE_ARRAY_FIR33_HANN));
    return 0;
}
