/* Offline replay of frozen upstream AEC inputs/gates, never installed. */
#include "aec/ap_aec.h"
#include "sync/ap_sync.h"
#include "device_shadow_selector_d24.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static ap_aec_state_t primary, shadow;
static uint64_t sync_calls;
int ap_sync_get_reference_d18_real(ap_sync_state_t *,uint32_t,float *);
int ap_sync_get_reference(ap_sync_state_t *s,uint32_t n,float *out) {
    ++sync_calls; return ap_sync_get_reference_d18_real(s,n,out);
}

static int number(const char *text,uint32_t *value) {
    uint32_t n=0u; const unsigned char *p=(const unsigned char *)text;
    if (!*p || (*p=='0' && p[1])) return 0;
    while (*p) {
        if (*p<'0' || *p>'9' || n>10000u) return 0;
        n=n*10u+(uint32_t)(*p-'0'); ++p;
    }
    if (n>10000u) return 0;
    *value=n; return 1;
}

static int length(FILE *f,long expected) {
    return fseek(f,0,SEEK_END)==0 && ftell(f)==expected && fseek(f,0,SEEK_SET)==0;
}

int main(int argc,char **argv) {
    static const char *names[]={"echo.f32le","residual.f32le","primary_echo.f32le","primary_residual.f32le",
        "shadow_echo.f32le","shadow_residual.f32le","state.csv","selector.csv"};
    FILE *mic_file=NULL,*ref_file=NULL,*gate_file=NULL,*files[8]={NULL};
    uint32_t frames=0u,notify=0u,frame=0u,i,shadow_calls=0u,resets=0u;
    uint16_t endian=1u;
    int has_notify,policy,future,result=0;
    d24_selection_t selection={0u,0u,0u};
    float mic[160],ref[160],pe[160],pr[160],se[160]={0},sr[160]={0};
    char filename[1024];
    if (argc!=9) return 2;
    has_notify=strcmp(argv[5],"none")!=0;
    policy=strcmp(argv[7],"keep")==0 ? 0 : strcmp(argv[7],"shadow")==0 ? 1 : -1;
    future=strcmp(argv[8],"future")==0;
    if (!number(argv[4],&frames) || !frames || (has_notify && (!number(argv[5],&notify) || notify>=frames)) ||
        policy<0 || (!future && strcmp(argv[8],"normal")!=0) || (future && (!has_notify || !policy)) ||
        *(const unsigned char *)&endian!=1u || sizeof(float)!=4u) {
        fprintf(stderr,"D26_INVALID_ARGUMENT_REJECT primary_calls=0 shadow_calls=0\n"); return 2;
    }
    mic_file=fopen(argv[1],"rb"); ref_file=fopen(argv[2],"rb"); gate_file=fopen(argv[3],"rb");
    if (!mic_file || !ref_file || !gate_file || !length(mic_file,(long)frames*160L*4L) ||
        !length(ref_file,(long)frames*160L*4L) || !length(gate_file,(long)frames*2L)) { result=4; goto done; }
    for (i=0u;i<8u;++i) {
        int n=snprintf(filename,sizeof(filename),"%s/%s",argv[6],names[i]);
        if (n<0 || (size_t)n>=sizeof(filename)) { result=2;goto done; }
        files[i]=fopen(filename,"wb"); if (!files[i]) { result=4;goto done; }
    }
    ap_aec_backend_init(&primary,160u,1536u,2u);
    if (primary.backend.block!=32u || primary.backend.active_partitions!=48u ||
        fprintf(files[6],"frame,runtime_stride,steady_frames,adapt_phase,constrain_partition,x_head,x_power_total,weight_l2\n")<0 ||
        fprintf(files[7],"frame,active,far,dt,bank,streak,change,primary_energy,shadow_energy\n")<0) { result=5;goto done; }
    for (frame=0u;frame<frames;++frame) {
        unsigned char gates[2];
        int active=policy && has_notify && frame>=notify,change;
        uint32_t part,bin;
        double p_energy=0.0,s_energy=0.0,weight=0.0;
        ap_aec_result_t primary_result;
        if (fread(mic,sizeof(float),160u,mic_file)!=160u || fread(ref,sizeof(float),160u,ref_file)!=160u ||
            fread(gates,1u,2u,gate_file)!=2u || gates[0]>1u || gates[1]>1u) { result=4;goto done; }
        for (i=0u;i<160u;++i) {
            if (!isfinite(mic[i]) || !isfinite(ref[i])) { result=7;goto done; }
            if (future && frame>=notify) { mic[i]=-mic[i];ref[i]=-ref[i]; }
        }
        if (policy && has_notify && frame==notify) { shadow=primary;ap_aec_backend_reset(&shadow);++resets; }
        ap_aec_backend_process(&primary,1,0.22f,160u,mic,ref,pr,pe,gates[0],gates[1],&primary_result);
        if (active) {
            ap_aec_result_t shadow_result;
            ++shadow_calls;
            ap_aec_backend_process(&shadow,1,0.22f,160u,mic,ref,sr,se,gates[0],gates[1],&shadow_result);
            if (!isfinite(shadow_result.echo_energy)) { result=6;goto done; }
        }
        for (i=0u;i<160u;++i) {
            double p=(double)pr[i],s=(double)sr[i];p_energy+=p*p;s_energy+=s*s;
            if (!isfinite(pe[i]) || !isfinite(pr[i]) || !isfinite(se[i]) || !isfinite(sr[i]) ||
                fabsf(mic[i]-(pe[i]+pr[i]))>1e-6f || (active && fabsf(mic[i]-(se[i]+sr[i]))>1e-6f)) { result=7;goto done; }
        }
        change=d24_choose(&selection,active,gates[0] && !gates[1],p_energy,s_energy);
        if (change<0 || sync_calls || !isfinite(primary_result.echo_energy) || !isfinite(primary.backend.x_power_total) ||
            primary.runtime_adapt_stride!=2u || primary.backend.adapt_phase>1u) { result=6;goto done; }
        for (part=0u;part<primary.backend.active_partitions;++part) for (bin=0u;bin<primary.backend.bins;++bin) {
            double re=(double)primary.backend.weights[part][bin].re,im=(double)primary.backend.weights[part][bin].im;
            weight+=re*re+im*im;
        }
        if (!isfinite(weight)) { result=7;goto done; }
        {
            const float *traces[]={selection.bank ? se : pe,selection.bank ? sr : pr,pe,pr,se,sr};
            for (i=0u;i<6u;++i) if (fwrite(traces[i],sizeof(float),160u,files[i])!=160u) { result=8;goto done; }
        }
        if (fprintf(files[6],"%u,%u,%u,%u,%u,%u,%.9g,%.17g\n",frame,primary.runtime_adapt_stride,primary.steady_frames,
                    primary.backend.adapt_phase,primary.backend.constrain_partition,primary.backend.x_head,(double)primary.backend.x_power_total,weight)<0 ||
            fprintf(files[7],"%u,%d,%u,%u,%u,%u,%d,%.17g,%.17g\n",frame,active,(unsigned)gates[0],(unsigned)gates[1],
                    selection.bank,selection.streak,change,p_energy,s_energy)<0) { result=8;goto done; }
    }
done:
    for (i=0u;i<8u;++i) if (files[i] && fclose(files[i])) result=9;
    if (mic_file && fclose(mic_file)) result=9;
    if (ref_file && fclose(ref_file)) result=9;
    if (gate_file && fclose(gate_file)) result=9;
    if (!result) printf("{\"frames\":%u,\"samples\":%u,\"primary_calls\":%u,\"shadow_calls\":%u,\"shadow_reset_calls\":%u,\"sync_calls\":%llu,\"switch_count\":%u,\"state_bytes\":%zu}\n",
        frames,frames*160u,frame,shadow_calls,resets,(unsigned long long)sync_calls,selection.changes,sizeof(ap_aec_state_t));
    return result;
}
