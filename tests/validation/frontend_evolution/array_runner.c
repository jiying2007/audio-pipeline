/* Offline research transport only. All allocation/file I/O is outside DSP core. */
#include "array_native.h"
#include <errno.h>
#include <float.h>
#include <limits.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

_Static_assert(sizeof(float) == 4 && FLT_RADIX == 2 && FLT_MANT_DIG == 24, "IEEE binary32 required");
static int word(FILE *f, char s[96]) { return fscanf(f, "%95s", s) == 1; }
static int uint_value(FILE *f, uint32_t *value) {
    char s[96], *end;
    unsigned long n;
    if (!word(f,s) || s[0]<'0' || s[0]>'9') return 0;
    errno=0; n=strtoul(s,&end,10);
    if(errno || *end || n>UINT32_MAX)return 0;
    *value=(uint32_t)n; return 1;
}
static int real_value(FILE *f, double *value) {
    char s[96], *end;
    if(!word(f,s))return 0;
    errno=0; *value=strtod(s,&end);
    return !errno && !*end && isfinite(*value);
}
static int read_config(const char *path, fe_array_config *c) {
    char version[96], extra[96];
    FILE *f=fopen(path,"rb");
    uint32_t mode=0u,i,k;
    int ok;
    if(!f)return 0;
    memset(c,0,sizeof(*c));
    ok=word(f,version) && strcmp(version,"FE_ARRAY_V1")==0 &&
       uint_value(f,&c->sample_rate_hz) && uint_value(f,&c->mic_count) &&
       uint_value(f,&mode) && mode<=1u && uint_value(f,&c->active_mask) &&
       uint_value(f,&c->reference_mic) && c->mic_count<=4u;
    c->interpolation=(fe_array_interpolation)mode;
    for(k=0u;ok && k<3u;++k)ok=real_value(f,&c->direction[k]);
    for(i=0u;ok && i<c->mic_count;++i) {
        for(k=0u;ok && k<3u;++k)ok=real_value(f,&c->microphones[i].position_m[k]);
        ok=ok && real_value(f,&c->microphones[i].gain) &&
            real_value(f,&c->microphones[i].latency_samples) && uint_value(f,&c->microphones[i].input_channel);
    }
    ok=ok && !word(f,extra) && !ferror(f);
    if(fclose(f)!=0)ok=0;
    return ok;
}

/* Optional offline steering schedule, not a data-plane parser. */
typedef struct { uint32_t sample, duration; double direction[3]; } steer_command;
static int read_commands(const char *path, steer_command commands[64], uint32_t *count) {
    FILE *f=fopen(path,"rb"); char version[96], extra[96];
    uint32_t i,k; int ok;
    if(!f)return 0;
    ok=word(f,version) && strcmp(version,"FE_STEERING_V1")==0 &&
       uint_value(f,count) && *count>0u && *count<=64u;
    for(i=0u;ok && i<*count;++i) {
        ok=uint_value(f,&commands[i].sample) && uint_value(f,&commands[i].duration) &&
           (i==0u || commands[i].sample>commands[i-1u].sample);
        for(k=0u;ok && k<3u;++k)ok=real_value(f,&commands[i].direction[k]);
    }
    ok=ok && !word(f,extra) && !ferror(f);
    if(fclose(f)!=0)ok=0;
    return ok;
}

int main(int argc,char **argv) {
    _Alignas(FE_ARRAY_ALIGNMENT) unsigned char memory[4096];
    unsigned char raw[3840], encoded[1920];
    float input[1920], output[480];
    fe_array_config c;
    fe_array_info info;
    fe_array *state=NULL;
    FILE *in=NULL,*out=NULL,*meta=NULL;
    long length;
    size_t bytes,hop,count,i;
    int result=2;
    steer_command commands[64];
    uint32_t command_count=0u, command_index=0u, chunk_limit=480u;
    uint64_t position=0u;
    if(argc<5 || argc>7) { fprintf(stderr,"usage: array-runner GEOMETRY INPUT.s16le OUTPUT.f32le INFO.json [COMMANDS [MAX_CHUNK_SAMPLES]]\n"); return 2; }
    if(!read_config(argv[1],&c) || fe_array_init(memory,sizeof(memory),&c,&state)!=FE_ARRAY_OK) {
        fprintf(stderr,"invalid array geometry\n"); return 2;
    }
    if(argc>=6 && !read_commands(argv[5],commands,&command_count))return 2;
    if(argc==7) {
        char *end; unsigned long v;
        errno=0; v=strtoul(argv[6],&end,10);
        if(errno || argv[6][0]<'1' || argv[6][0]>'9' || *end || !v || v>480u)return 2;
        chunk_limit=(uint32_t)v;
    }
    in=fopen(argv[2],"rb");
    if(!in || fseek(in,0,SEEK_END)!=0 || (length=ftell(in))<=0 || fseek(in,0,SEEK_SET)!=0)goto done;
    hop=c.sample_rate_hz/100u; bytes=hop*c.mic_count*2u;
    if((unsigned long)length%bytes!=0u) { fprintf(stderr,"partial or empty PCM\n"); goto done; }
    if(command_count && (uint64_t)commands[command_count-1u].sample>=
       (uint64_t)((unsigned long)length/(c.mic_count*2u)))goto done;
    out=fopen(argv[3],"wbx");
    if(!out) { fprintf(stderr,"output already exists or is not writable\n"); goto done; }
    meta=fopen(argv[4],"wbx");
    if(!meta)goto done;
    while((count=fread(raw,1,bytes,in))!=0u) {
        if(count!=bytes)goto done;
        for(i=0u;i<hop*c.mic_count;++i) {
            const unsigned u=(unsigned)raw[2u*i] | ((unsigned)raw[2u*i+1u]<<8u);
            const int signed_value=u>=32768u ? (int)u-65536 : (int)u;
            input[i]=(float)signed_value/32768.0f;
        }
        {
            size_t offset=0u;
            while(offset<hop) {
                size_t batch=hop-offset;
                if(command_index<command_count && position==commands[command_index].sample) {
                    if(fe_array_request_steer(state,commands[command_index].direction,
                       commands[command_index].duration)!=FE_ARRAY_OK)goto done;
                    ++command_index;
                }
                if(batch>chunk_limit)batch=chunk_limit;
                if(command_index<command_count && (uint64_t)batch>commands[command_index].sample-position)
                    batch=(size_t)(commands[command_index].sample-position);
                if(!batch || fe_array_process(state,input+offset*c.mic_count,batch*c.mic_count,
                   output+offset,batch)!=FE_ARRAY_OK)goto done;
                offset+=batch; position+=batch;
            }
        }
        for(i=0u;i<hop;++i) {
            uint32_t bits;
            if(!isfinite(output[i]))goto done;
            memcpy(&bits,&output[i],sizeof(bits));
            encoded[4u*i]=(unsigned char)(bits&255u);
            encoded[4u*i+1u]=(unsigned char)((bits>>8u)&255u);
            encoded[4u*i+2u]=(unsigned char)((bits>>16u)&255u);
            encoded[4u*i+3u]=(unsigned char)((bits>>24u)&255u);
        }
        if(fwrite(encoded,4u,hop,out)!=hop)goto done;
    }
    if(ferror(in) || command_index!=command_count || fe_array_get_info(state,&info)!=FE_ARRAY_OK)goto done;
    if(fclose(out)!=0) { out=NULL; goto done; } out=NULL;
    if(info.samples_processed!=(uint64_t)((unsigned long)length/(c.mic_count*2u)))goto done;
    if(fprintf(meta,"{\"status\":\"PASS\",\"mic_count\":%u,\"sample_rate_hz\":%u,\"active_mask\":%u,\"interpolation\":%u,\"common_delay_samples\":%u,\"state_bytes\":%zu,\"samples_processed\":%llu,\"compensation_samples\":[",
        info.mic_count,info.sample_rate_hz,info.active_mask,(unsigned)info.interpolation,
        info.common_delay_samples,info.state_bytes,(unsigned long long)info.samples_processed)<0)goto done;
    for(i=0u;i<c.mic_count;++i)if(fprintf(meta,"%s%.17g",i?",":"",info.compensation_samples[i])<0)goto done;
    if(fprintf(meta,"],\"steering_accepted\":%llu,\"steering_completed\":%llu,\"steering_cancelled\":%llu,\"transition_remaining_samples\":%u,\"direction\":[%.17g,%.17g,%.17g]",
        (unsigned long long)info.steering_accepted,(unsigned long long)info.steering_completed,
        (unsigned long long)info.steering_cancelled,info.transition_total_samples-info.transition_done_samples,
        info.direction[0],info.direction[1],info.direction[2])<0)goto done;
    if(fprintf(meta,",\"output_encoding\":\"f32le-unclipped\",\"shipping_authority\":false}\n")<0)goto done;
    if(fclose(meta)!=0) { meta=NULL; goto done; } meta=NULL;
    result=0;
done:
    if(in && fclose(in)!=0)result=2;
    if(out && fclose(out)!=0)result=2;
    if(meta && fclose(meta)!=0)result=2;
    if(result)fprintf(stderr,"array transport failed; partial files are not evidence of success\n");
    return result;
}
