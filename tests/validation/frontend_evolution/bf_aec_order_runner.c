/* FE04 offline paired-order probe. Uses unchanged PUBLIC AEC and optional
 * Activity modules and the existing research BF. Default gates are supplied.
 * Measured gates can adapt during near speech: shadows then are instrumentation,
 * NOT an isolated near/echo decomposition. No production API/algorithm change.
 */
#include "audio_pipeline/audio_modules.h"
#include "array_native.h"
#include <errno.h>
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define HOP 160u
#define RATE 16000u
#define SECONDS 16u
#define OUTPUTS 6u
_Static_assert(sizeof(float)==4 && FLT_MANT_DIG==24, "IEEE binary32 required");
typedef struct { void *memory; fe_array *core; } array_owner;
typedef struct { void *memory; ap_aec_module_t *core; } aec_owner;

static int read_u(FILE *f, unsigned *v) {
    char text[80], *end; unsigned long n;
    if (fscanf(f,"%79s",text)!=1 || text[0]<'0' || text[0]>'9') return 0;
    errno=0; n=strtoul(text,&end,10);
    if (errno || *end || n>1000000ul) return 0;
    *v=(unsigned)n; return 1;
}
static int read_r(FILE *f, double *v) {
    char text[80], *end;
    if(fscanf(f,"%79s",text)!=1)return 0;
    errno=0;*v=strtod(text,&end);return !errno && !*end && isfinite(*v);
}
static int config(const char *path,fe_array_config *c,float banks[2][132],unsigned *event) {
    FILE *f=fopen(path,"rb");char name[80],extra[80];unsigned mode,n;int ok;
    if(!f)return 0;
    memset(c,0,sizeof(*c));
    ok=fscanf(f,"%79s",name)==1 && !strcmp(name,"FE04_ORDER_V1") &&
       read_u(f,&n) && (n==1 || n==2 || n==4) && read_u(f,&mode) && (mode==3 || mode==4) &&
       read_u(f,event) && *event<=2;
    if(ok) {
        c->sample_rate_hz=RATE;c->mic_count=n;c->active_mask=(1u<<n)-1u;
        c->interpolation=(fe_array_interpolation)mode;c->direction[0]=1.0;
        for(unsigned m=0;ok && m<n;++m) {
            for(unsigned k=0;ok && k<3;++k)ok=read_r(f,&c->microphones[m].position_m[k]);
            c->microphones[m].gain=1.0;c->microphones[m].input_channel=m;
        }
        if(mode==4)for(unsigned b=0;ok && b<2;++b)for(unsigned j=0;ok && j<n*33;++j) {
            double value;ok=read_r(f,&value) && fabs(value)<=16;
            if(ok)banks[b][j]=(float)value;
        }
    }
    ok=ok && fscanf(f,"%79s",extra)!=1 && !ferror(f);
    if(fclose(f))ok=0;
    return ok;
}
static int array_init(array_owner *a,const fe_array_config *c,const float *bank) {
    size_t size=fe_array_state_bytes_for_mode(c->mic_count,c->interpolation);
    if(!size)return 0;
    a->memory=aligned_alloc(16,(size+15u)&~(size_t)15u);
    if(!a->memory)return 0;
    return (c->interpolation==FE_ARRAY_SPATIAL33 ?
        fe_array_init_spatial33(a->memory,size,c,bank,c->mic_count*33u,&a->core):
        fe_array_init(a->memory,size,c,&a->core))==FE_ARRAY_OK;
}
static int aec_init(aec_owner *a) {
    size_t size=ap_module_aec_state_size();ap_module_aec_config_t c={RATE,64u,1u,0.2f};
    a->memory=aligned_alloc(16,(size+15u)&~(size_t)15u);
    return a->memory && ap_module_aec_init(a->memory,size,&c,&a->core)==AP_OK;
}
static int aec(aec_owner *a,const float *x,const float *ref,float *out,int far,int dt) {
    float estimate[HOP];ap_module_aec_result_t result;
    return ap_module_aec_process(a->core,x,ref,out,estimate,HOP,far,dt,&result)==AP_OK &&
           result.backend==AP_AEC_BACKEND_MDF && result.active_taps==1024u;
}
static int beam(array_owner *a,const float *x,unsigned n,float *y) {
    return fe_array_process(a->core,x,HOP*n,y,HOP)==FE_ARRAY_OK;
}
int main(int argc,char **argv) {
    fe_array_config c;array_owner b[5]={{0}};aec_owner post[2]={{0}},pre[8]={{0}};
    float banks[2][132]={{0}},packet[HOP*11],near[HOP*4],echo[HOP*4],mix[HOP*4],ref[HOP];
    float residual[2][HOP*4],bf_mix[HOP],output[OUTPUTS][HOP],interleaved[HOP*OUTPUTS];
    FILE *input=NULL,*out=NULL,*meta=NULL,*trace=NULL;unsigned event=0,frames=0;int rc=2,gate_mode=0;
    void *activity_memory=NULL;
#if AP_HAVE_MODULE_ACTIVITY
    ap_activity_module_t *activity=NULL;
#endif
    double maximum_additivity=0,maximum_commutation=0,peak=0;unsigned outside=0;
    size_t frame_bytes;unsigned n;fe_array_info info;
    const unsigned marker=1;
    if((argc!=5 && argc!=7) || *(const unsigned char *)&marker!=1) {
        fputs("usage: bf-aec-order CONFIG INPUT.f32le OUTPUT.f32le META.json [--measured-activity|--monitor-activity TRACE.csv] (little endian)\n",stderr);return 2;
    }
    if(argc==7) {
#if AP_HAVE_MODULE_ACTIVITY
        if(!strcmp(argv[5],"--measured-activity"))gate_mode=1;
        else if(!strcmp(argv[5],"--monitor-activity"))gate_mode=2;
        else {fputs("invalid activity mode\n",stderr);return 2;}
#else
        fputs("Activity module is not compiled; no oracle fallback\n",stderr);return 2;
#endif
    }
    if(!config(argv[1],&c,banks,&event)) {fputs("invalid config\n",stderr);return 2;}
    n=c.mic_count;frame_bytes=HOP*(2u*n+3u)*sizeof(float);
    input=fopen(argv[2],"rb");if(!input)goto done;
    if(fseek(input,0,SEEK_END))goto done;
    {long length=ftell(input);if(length<=0 || (unsigned long)length%frame_bytes ||
       (unsigned long)length/frame_bytes>SECONDS*100u || fseek(input,0,SEEK_SET))goto done;}
    /* Exclusive creation: never overwrite an earlier successful or failed run. */
    out=fopen(argv[3],"wbx");if(!out)goto done;
    meta=fopen(argv[4],"wbx");if(!meta)goto done;
#if AP_HAVE_MODULE_ACTIVITY
    if(gate_mode) {
        const ap_module_activity_config_t ac={1.0e-7f,1.5f,3u};
        size_t bytes=ap_module_activity_state_size();
        activity_memory=aligned_alloc(16,(bytes+15u)&~(size_t)15u);
        if(!activity_memory || ap_module_activity_init(activity_memory,bytes,&ac,&activity)!=AP_OK)goto done;
        trace=fopen(argv[6],"wbx");if(!trace)goto done;
        if(fputs("frame,mic_energy,reference_energy,oracle_far,oracle_dt,detected_far,detected_dt,used_far,used_dt\n",trace)==EOF)goto done;
        fprintf(stderr,"ACTIVITY_TRACE_V1 mode=%s state_bytes=%zu threshold=1e-7 ratio=1.5 hold=3\n",
            gate_mode==1?"measured":"monitor-only",bytes);
    }
#else
    (void)gate_mode;
#endif
    for(unsigned j=0;j<5;++j)if(!array_init(&b[j],&c,banks[0]))goto done;
    for(unsigned j=0;j<2;++j)if(!aec_init(&post[j]))goto done;
    for(unsigned j=0;j<2*n;++j)if(!aec_init(&pre[j]))goto done;
    for(;;) {
        size_t got=fread(packet,1,frame_bytes,input);int far,dt;
        if(got==0 && !ferror(input))break;
        if(got!=frame_bytes)goto done;
        far=(packet[2*n+1u]==1.0f);dt=(packet[2*n+2u]==1.0f);
        for(unsigned k=0;k<HOP;++k) {
            size_t at=(size_t)k*(2*n+3u);
            if((packet[at+2*n+1u]!=(float)far) || (packet[at+2*n+2u]!=(float)dt))goto done;
            for(unsigned j=0;j<2*n+1u;++j)if(!isfinite(packet[at+j]) || fabsf(packet[at+j])>1.0f)goto done;
            for(unsigned m=0;m<n;++m) {
                near[k*n+m]=packet[at+m];echo[k*n+m]=packet[at+n+m];
                mix[k*n+m]=near[k*n+m]+echo[k*n+m];
                if(fabsf(mix[k*n+m])>1.0f)goto done;
            }
            ref[k]=packet[at+2*n];
        }
        if(event==1u && frames==800u) {
            const double direction[3]={0.5,0.86602540378443864676,0.0};
            for(unsigned j=0;j<5;++j) {
                fe_array_status status=c.interpolation==FE_ARRAY_SPATIAL33 ?
                  fe_array_request_spatial33(b[j].core,direction,banks[1],n*33u,320u):
                  fe_array_request_steer(b[j].core,direction,320u);
                if(status!=FE_ARRAY_OK)goto done;
            }
        }
        if(!beam(&b[0],mix,n,bf_mix) || !beam(&b[1],near,n,output[0]) || !beam(&b[2],echo,n,output[1]))goto done;
#if AP_HAVE_MODULE_ACTIVITY
        if(gate_mode) {
            float mic_energy=1.0e-12f,reference_energy=1.0e-12f;
            ap_module_activity_result_t ar;int oracle_far=far,oracle_dt=dt;
            for(unsigned k=0;k<HOP;++k) {
                mic_energy+=bf_mix[k]*bf_mix[k];
                reference_energy+=ref[k]*ref[k];
            }
            mic_energy/=HOP;reference_energy/=HOP;
            if(ap_module_activity_process(activity,mic_energy,reference_energy,&ar)!=AP_OK)goto done;
            if(gate_mode==1) {far=ar.far_end_active;dt=ar.double_talk_active;}
            if(fprintf(trace,"%u,%.9g,%.9g,%d,%d,%u,%u,%d,%d\n",frames,
                (double)mic_energy,(double)reference_energy,oracle_far,oracle_dt,
                (unsigned)ar.far_end_active,(unsigned)ar.double_talk_active,far,dt)<0)goto done;
        }
#endif
        if(!aec(&post[0],bf_mix,ref,output[2],far,dt) || !aec(&post[1],output[1],ref,output[3],far,dt))goto done;
        for(unsigned m=0;m<n;++m) {
            float x[HOP],e[HOP],r[HOP],s[HOP];
            for(unsigned k=0;k<HOP;++k){x[k]=mix[k*n+m];e[k]=echo[k*n+m];}
            if(!aec(&pre[m],x,ref,r,far,dt) || !aec(&pre[n+m],e,ref,s,far,dt))goto done;
            for(unsigned k=0;k<HOP;++k){residual[0][k*n+m]=r[k];residual[1][k*n+m]=s[k];}
        }
        if(!beam(&b[3],residual[0],n,output[4]) || !beam(&b[4],residual[1],n,output[5]))goto done;
        for(unsigned k=0;k<HOP;++k) {
            double comm=fabs((double)bf_mix[k]-output[1][k]-output[0][k]);
            if(comm>maximum_commutation)maximum_commutation=comm;
            for(unsigned a=0;a<2;++a) {
                double err=fabs((double)output[2+2*a][k]-output[3+2*a][k]-output[0][k]);
                if(err>maximum_additivity)maximum_additivity=err;
            }
            for(unsigned j=0;j<OUTPUTS;++j) {
                double value=output[j][k];if(!isfinite(value))goto done;
                if(fabs(value)>peak)peak=fabs(value);
                if(fabs(value)>1.0)++outside;
                interleaved[k*OUTPUTS+j]=output[j][k];
            }
        }
        if(fwrite(interleaved,sizeof(float),HOP*OUTPUTS,out)!=HOP*OUTPUTS)goto done;
        ++frames;
    }
    if(!frames || fe_array_get_info(b[0].core,&info)!=FE_ARRAY_OK)goto done;
    if(fprintf(meta,"{\"status\":\"PASS\",\"frames\":%u,\"samples\":%u,\"microphones\":%u,"
        "\"event\":%u,\"mode\":%u,\"columns\":6,\"common_delay_samples\":%u,"
        "\"array_state_bytes\":%zu,\"aec_state_bytes\":%zu,\"post_order_state_bytes\":%zu,"
        "\"pre_order_state_bytes\":%zu,\"max_additivity_error\":%.17g,\"max_commutation_error\":%.17g,"
        "\"peak\":%.17g,\"out_of_range_values\":%u,\"steering_completed\":%llu,"
        "\"source_revision\":\"%s\",\"build_config_digest\":\"%s\",\"shipping_authority\":false}\n",
        frames,frames*HOP,n,event,(unsigned)c.interpolation,info.common_delay_samples,info.state_bytes,
        ap_module_aec_state_size(),info.state_bytes+ap_module_aec_state_size(),
        info.state_bytes+n*ap_module_aec_state_size(),maximum_additivity,maximum_commutation,peak,outside,
        (unsigned long long)info.steering_completed,AP_BUILD_SOURCE_REVISION,AP_BUILD_CONFIG_DIGEST)<0)goto done;
    rc=0;
 done:
    for(unsigned j=0;j<5;++j)free(b[j].memory);
    for(unsigned j=0;j<2;++j)free(post[j].memory);
    for(unsigned j=0;j<8;++j)free(pre[j].memory);
    free(activity_memory);
    if(input && fclose(input))rc=2;
    if(out && fclose(out))rc=2;
    if(meta && fclose(meta))rc=2;
    if(trace && fclose(trace))rc=2;
    if(rc)fputs("FE04 failed; partial files are not evidence of success\n",stderr);
    return rc;
}
