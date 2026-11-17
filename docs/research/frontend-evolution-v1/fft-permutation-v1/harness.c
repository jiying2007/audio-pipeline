#define _POSIX_C_SOURCE 200809L
#include "dsp/ap_dsp.h"
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <math.h>
void baseline_fft(ap_complex_t*,uint32_t,int);
void candidate_fft(ap_complex_t*,uint32_t,int);
static uint32_t rng=20261114u;
static uint32_t next(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static double now(void){struct timespec t;clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t);return t.tv_sec+t.tv_nsec*1e-9;}
static ap_complex_t input[1024],a[1024],b[1024];
static volatile float sink;
static void fill(unsigned n,unsigned trial){for(unsigned i=0;i<n;++i){a[i].re=(float)(int32_t)next()/2147483648.0f;a[i].im=(float)(int32_t)next()/2147483648.0f;if(trial<8){const float special[]={0.0f,-0.0f,1e-38f,-1e-38f,1e10f,-1e10f,INFINITY,NAN};a[i].re=special[trial];a[i].im=special[7-trial];}}}
static double bench(void(*fn)(ap_complex_t*,uint32_t,int),unsigned n,int inv){double t=now();for(unsigned r=0;r<10000;++r){memcpy(a,input,n*sizeof(*a));fn(a,n,inv);sink=a[r%n].re;}return now()-t;}
int main(void){unsigned cases=0;for(unsigned n=1;n<=1024;n*=2)for(int inv=0;inv<2;++inv)for(unsigned trial=0;trial<1000;++trial){fill(n,trial);memcpy(b,a,n*sizeof(*a));baseline_fft(a,n,inv);candidate_fft(b,n,inv);if(memcmp(a,b,n*sizeof(*a))){fprintf(stderr,"MISMATCH %u %d %u\n",n,inv,trial);return 1;}++cases;}printf("EQUIVALENCE %u PASS\n",cases);unsigned sizes[]={32,64,256,512};for(unsigned z=0;z<4;++z)for(int inv=0;inv<2;++inv){unsigned n=sizes[z];fill(n,10);memcpy(input,a,n*sizeof(*a));for(unsigned r=0;r<7;++r){double base,cand;if(r%2){cand=bench(candidate_fft,n,inv);base=bench(baseline_fft,n,inv);}else{base=bench(baseline_fft,n,inv);cand=bench(candidate_fft,n,inv);}printf("PERF %u %d %u %.9f %.9f %.9f\n",n,inv,r,base,cand,cand/base);}}return 0;}
