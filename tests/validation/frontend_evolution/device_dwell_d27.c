/* Select only from frozen AEC bank outputs. No AEC library is linked. */
#include "device_dwell_selector_d27.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int number(const char *text,uint32_t *value) {
    uint32_t n=0u; const unsigned char *p=(const unsigned char *)text;
    if (!*p || (*p=='0' && p[1])) return 0;
    while (*p) { if (*p<'0' || *p>'9' || n>10000u) return 0; n=n*10u+(uint32_t)(*p-'0'); ++p; }
    if (n>10000u) return 0;
    *value=n;return 1;
}
static int length(FILE *f,long expected) {
    return fseek(f,0,SEEK_END)==0 && ftell(f)==expected && fseek(f,0,SEEK_SET)==0;
}
static int self_test(void) {
    d27_selection_t s={{0u,0u,0u},0u,0u}, legacy={{0u,0u,0u},0u,0u};
    d24_selection_t old={0u,0u,0u}; uint32_t frame;
    for (frame=0u;frame<200u;++frame) {
        double pe=frame%8u<4u ? 1.0 : 0.1, se=frame%8u<4u ? 0.1 : 1.0;
        int a=d24_choose(&old,1,1,pe,se), b=d27_choose(&legacy,frame,0u,1,1,pe,se);
        if (a!=b || memcmp(&old,&legacy.base,sizeof(old))) return 10;
    }
    for (frame=0u;frame<=54u;++frame) {
        int changed=d27_choose(&s,frame,50u,1,1,frame<3u ? 1.0 : 0.1,frame<3u ? 0.1 : 1.0);
        if (changed!=((frame==2u || frame==54u) ? 1 : 0)) return 11;
        if (frame>=3u && frame<54u && s.base.bank!=1u) return 12;
    }
    if (d27_choose(&s,55u,50u,1,1,NAN,1.0)!=-1) return 13;
    if (d27_choose(&s,56u,50u,0,1,1.0,0.1)!=0 || s.has_last || s.base.bank || s.base.streak) return 14;
    for (frame=57u;frame<60u;++frame) if (d27_choose(&s,frame,50u,1,1,1.0,0.1)!=(frame==59u)) return 15;
    /* Wall-clock hold continues through ineligible frames; confirmation restarts. */
    for (frame=60u;frame<109u;++frame) if (d27_choose(&s,frame,50u,1,0,0.1,1.0)!=0 || s.base.streak) return 16;
    if (d27_choose(&s,109u,50u,1,1,0.1,1.0)!=0 || s.base.streak!=1u) return 17;
    if (d27_choose(&s,110u,50u,1,0,0.1,1.0)!=0 || s.base.streak) return 18;
    for (frame=111u;frame<=113u;++frame) if (d27_choose(&s,frame,50u,1,1,0.1,1.0)!=(frame==113u)) return 19;
    puts("D27_SELF_TEST_PASS legacy/dwell/finite/inactive/wall-clock/gate");return 0;
}
int main(int argc,char **argv) {
    static const char *names[]={"echo.f32le","residual.f32le","selector.csv"};
    FILE *inputs[5]={NULL},*outputs[3]={NULL};
    uint32_t frames=0u,dwell=0u,frame=0u,i,eligible=0u;int future,result=0;
    d27_selection_t selection={{0u,0u,0u},0u,0u};uint16_t endian=1u;
    float trace[4][160];char path[1024];
    if (argc==2 && strcmp(argv[1],"--self-test")==0) return self_test();
    if (argc!=10) return 2;
    future=strcmp(argv[9],"future")==0;
    if (!number(argv[6],&frames) || !frames || !number(argv[7],&dwell) || (dwell!=0u && dwell!=50u) ||
        (!future && strcmp(argv[9],"normal")!=0) || (future && dwell!=50u) ||
        *(const unsigned char *)&endian!=1u || sizeof(float)!=4u) {
        fprintf(stderr,"D27_INVALID_ARGUMENT_REJECT selector_calls=0\n");return 2;
    }
    for (i=0u;i<5u;++i) { inputs[i]=fopen(argv[i+1u],"rb");
        if (!inputs[i] || !length(inputs[i],(long)frames*(i==4u ? 3L : 640L))) { result=4;goto done; } }
    for (i=0u;i<3u;++i) {
        int n=snprintf(path,sizeof(path),"%s/%s",argv[8],names[i]);
        if (n<0 || (size_t)n>=sizeof(path)) { result=2;goto done; }
        outputs[i]=fopen(path,"wb");if (!outputs[i]) { result=4;goto done; }
    }
    if (fprintf(outputs[2],"frame,active,far,dt,bank,streak,change,primary_energy,shadow_energy,hold_remaining\n")<0) { result=8;goto done; }
    for (frame=0u;frame<frames;++frame) {
        unsigned char gates[3];double pe=0.0,se=0.0;int changed;
        if (fread(gates,1u,3u,inputs[4])!=3u || gates[0]>1u || gates[1]>1u || gates[2]>1u) { result=4;goto done; }
        for (i=0u;i<4u;++i) {
            uint32_t sample;
            if (fread(trace[i],sizeof(float),160u,inputs[i])!=160u) { result=4;goto done; }
            for (sample=0u;sample<160u;++sample) {
                if (future && gates[0]) trace[i][sample]*=i<2u ? 1.125f : -0.875f;
                if (!isfinite(trace[i][sample])) { result=7;goto done; }
            }
        }
        for (i=0u;i<160u;++i) { double p=(double)trace[1][i],s=(double)trace[3][i];pe+=p*p;se+=s*s; }
        eligible+=(uint32_t)(gates[1] && !gates[2]);
        changed=d27_choose(&selection,frame,dwell,gates[0],gates[1] && !gates[2],pe,se);
        if (changed<0) { result=7;goto done; }
        for (i=0u;i<2u;++i) if (fwrite(trace[selection.base.bank*2u+i],sizeof(float),160u,outputs[i])!=160u) { result=8;goto done; }
        if (fprintf(outputs[2],"%u,%u,%u,%u,%u,%u,%d,%.17g,%.17g,%u\n",frame,(unsigned)gates[0],(unsigned)gates[1],(unsigned)gates[2],
                    selection.base.bank,selection.base.streak,changed,pe,se,gates[0] ? d27_remaining(&selection,frame,dwell) : 0u)<0) { result=8;goto done; }
    }
done:
    for (i=0u;i<5u;++i) if (inputs[i] && fclose(inputs[i])) result=9;
    for (i=0u;i<3u;++i) if (outputs[i] && fclose(outputs[i])) result=9;
    if (!result) printf("{\"frames\":%u,\"samples\":%u,\"selector_calls\":%u,\"switch_count\":%u,\"eligible_frames\":%u,\"selection_state_bytes\":%zu,\"aec_calls\":0}\n",
                       frames,frames*160u,frame,selection.base.changes,eligible,sizeof(selection));
    return result;
}
