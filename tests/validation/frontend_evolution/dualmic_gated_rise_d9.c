/* Isolated D9 research driver. Production algorithm/defaults stay unchanged. */
#define _POSIX_C_SOURCE 200809L
#include "enhance/ap_enhance.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
void d9_agc_init(ap_agc_state_t *, float, float);
void d9_agc_process_controlled(ap_agc_state_t *, float *, uint32_t, int);
typedef struct { uint32_t allow, reset; float before, after; } control_t;
_Static_assert(sizeof(control_t)==16 && sizeof(ap_agc_state_t)==12 && sizeof(float)==4,"layout");
static double cpu(void) { struct timespec t; if(clock_gettime(CLOCK_THREAD_CPUTIME_ID,&t)) exit(9); return t.tv_sec+t.tv_nsec*1e-9; }
static int finite_signal(const float *x,size_t n) { for(size_t i=0;i<n;i++) if(!isfinite(x[i])) return 0; return 1; }
static void *read_exact(const char *path,size_t n) {
 FILE *f=fopen(path,"rb"); void *p=malloc(n); if(!f||!p||fread(p,1,n,f)!=n||fgetc(f)!=EOF||ferror(f)||fclose(f)) exit(3);return p;
}
static void write_exact(const char *path,const void *p,size_t n) { FILE*f=fopen(path,"wb");if(!f||fwrite(p,1,n,f)!=n||fclose(f)) exit(7); }
static int selftest(void) {
 unsigned cases=0,blocked=0;
 const float gains[]={.25f,.75f,1.f,2.f,8.f}, levels[]={0.f,1e-20f,.01f,.2f,1.f,2.f};
 for(unsigned p=0;p<2;p++)for(unsigned a=0;a<2;a++)for(unsigned g=0;g<5;g++)for(unsigned k=0;k<6;k++) {
 ap_agc_state_t b,c;float x[160],y[160];ap_agc_init(&b,p?-18.f:-20.f,-2.f);d9_agc_init(&c,p?-18.f:-20.f,-2.f);
 if(memcmp(&b,&c,12))return 1;b.gain=c.gain=gains[g];
 for(unsigned i=0;i<160;i++)x[i]=i%2?levels[k]:-levels[k];memcpy(y,x,sizeof x);
 ap_agc_process_controlled(&b,x,160,a);d9_agc_process_controlled(&c,y,160,a);
 if(!finite_signal(x,160)||!finite_signal(y,160)||!isfinite(c.gain))return 1;
 if(a&&(memcmp(&b,&c,12)||memcmp(x,y,sizeof x)))return 1;
 if(!a&&c.gain>gains[g])return 1;
 if(!a&&b.gain>gains[g])blocked++;
 for(unsigned i=0;i<160;i++)if(fabsf(y[i])>c.limiter_linear)return 1;
 ap_agc_init(&b,p?-18.f:-20.f,-2.f);d9_agc_init(&c,p?-18.f:-20.f,-2.f);if(memcmp(&b,&c,12))return 1;cases++;
 }
 float bad[3]={NAN,INFINITY,-INFINITY};for(unsigned i=0;i<3;i++)if(finite_signal(bad+i,1))return 1;
 if(!blocked)return 1;printf("{\"selftest_cases\":%u,\"blocked_rise_cases\":%u,\"nonfinite_rejected\":3}\n",cases,blocked);return 0;
}
int main(int argc,char **argv) {
 if(argc==2&&!strcmp(argv[1],"--self-test"))return selftest();
 if(argc!=9)return 2;uint32_t endian=1;if(*(unsigned char*)&endian!=1)return 2;
 char *end;unsigned long frames=strtoul(argv[8],&end,10);if(*end||!frames||frames>1000)return 2;
 float target;if(!strcmp(argv[7],"call"))target=-20.f;else if(!strcmp(argv[7],"assistant"))target=-18.f;else return 2;
 size_t n=frames*160,bytes=n*4;float *input=read_exact(argv[1],bytes),*ref=read_exact(argv[2],bytes);control_t *ctl=read_exact(argv[3],frames*16);
 if(!finite_signal(input,n)||!finite_signal(ref,n))return 3;
 for(size_t f=0;f<frames;f++)if(ctl[f].allow>1||ctl[f].reset>1||!isfinite(ctl[f].before)||!isfinite(ctl[f].after))return 3;
 float *out[2]={malloc(bytes),malloc(bytes)},*work=malloc(bytes),*trace[2]={malloc(frames*8),malloc(frames*8)};
 if(!out[0]||!out[1]||!work||!trace[0]||!trace[1])return 3;
 double timings[2][7];unsigned blocked=0;
 for(unsigned rep=0;rep<7;rep++)for(unsigned order=0;order<2;order++) {
 unsigned arm=(rep+order)%2;ap_agc_state_t s;double begin=cpu();
 if(arm)d9_agc_init(&s,target,-2.f);else ap_agc_init(&s,target,-2.f);
 for(size_t f=0;f<frames;f++) {
 if(ctl[f].reset){if(arm)d9_agc_init(&s,target,-2.f);else ap_agc_init(&s,target,-2.f);}
 float before=s.gain;memcpy(work+f*160,input+f*160,640);
 if(arm)d9_agc_process_controlled(&s,work+f*160,160,ctl[f].allow);else ap_agc_process_controlled(&s,work+f*160,160,ctl[f].allow);
 if(!arm&&(memcmp(&before,&ctl[f].before,4)||memcmp(&s.gain,&ctl[f].after,4)))return 4;
 if(arm&&!ctl[f].allow&&s.gain>before)return 5;
 if(!isfinite(s.gain))return 5;
 if(!rep){trace[arm][f*2]=before;trace[arm][f*2+1]=s.gain;if(!arm&&!ctl[f].allow&&s.gain>before)blocked++;}
 }
 timings[arm][rep]=cpu()-begin;
 if(!finite_signal(work,n))return 5;
 if(!arm&&memcmp(work,ref,bytes))return 4;
 if(!rep)memcpy(out[arm],work,bytes);else if(memcmp(out[arm],work,bytes))return 6;
 }
 write_exact(argv[4],out[0],bytes);write_exact(argv[5],out[1],bytes);
 FILE*t=fopen(argv[6],"wb");if(!t||fwrite(trace[0],8,frames,t)!=frames||fwrite(trace[1],8,frames,t)!=frames||fclose(t))return 7;
 ap_agc_state_t init_probe;ap_agc_init(&init_probe,target,-2.f);
 printf("{\"target_linear\":%.17g,\"limiter_linear\":%.17g,\"frames\":%lu,\"baseline_gated_rise_frames\":%u,\"cpu_seconds\":[",(double)init_probe.target_linear,(double)init_probe.limiter_linear,frames,blocked);
 for(unsigned a=0;a<2;a++){if(a)printf(",");printf("[");for(unsigned r=0;r<7;r++)printf("%s%.17g",r?",":"",timings[a][r]);printf("]");}printf("]}\n");
 free(input);free(ref);free(ctl);free(out[0]);free(out[1]);free(work);free(trace[0]);free(trace[1]);return 0;
}
