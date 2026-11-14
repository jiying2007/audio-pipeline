#define _POSIX_C_SOURCE 200809L
#include "enhance/ap_noise_tracker.h"
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <math.h>
void baseline_init(ap_noise_tracker_state_t*);void candidate_init(ap_noise_tracker_state_t*);
void baseline_update(ap_noise_tracker_state_t*,uint32_t,float,ap_noise_tracker_result_t*);
void candidate_update(ap_noise_tracker_state_t*,uint32_t,float,ap_noise_tracker_result_t*);
void baseline_next_frame(ap_noise_tracker_state_t*);void candidate_next_frame(ap_noise_tracker_state_t*);
static uint32_t rng=20261114u;
static uint32_t next(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static float powers[1000][257];static volatile float sink;
static double now(void){struct timespec t;if(clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t))return -1.;return t.tv_sec+t.tv_nsec*1e-9;}
static double bench(unsigned arm,unsigned bins){ap_noise_tracker_state_t s;ap_noise_tracker_result_t r;void(*up)(ap_noise_tracker_state_t*,uint32_t,float,ap_noise_tracker_result_t*)=arm?candidate_update:baseline_update;void(*nf)(ap_noise_tracker_state_t*)=arm?candidate_next_frame:baseline_next_frame;
 if(arm)candidate_init(&s);else baseline_init(&s);double start=now();for(unsigned f=0;f<10000;f++){for(unsigned k=0;k<bins;k++)up(&s,k,powers[f%1000][k],&r);nf(&s);}sink=r.noise;return now()-start;}
int main(int argc,char**argv){(void)argv;unsigned bins[]={17,33,129,257};unsigned long checks=0;for(unsigned f=0;f<1000;f++)for(unsigned k=0;k<257;k++)powers[f][k]=(float)(next()%100000u)*1e-6f;
 for(unsigned z=0;z<4;z++)for(unsigned stress=0;stress<2;stress++){ap_noise_tracker_state_t a,b;baseline_init(&a);candidate_init(&b);for(unsigned f=0;f<1000;f++){if(f==333){baseline_init(&a);candidate_init(&b);}for(unsigned k=0;k<bins[z];k++){float x=powers[f][k];if(stress && f%23==0){float special[]={0.f,-0.f,1e-38f,1e20f,NAN,INFINITY};x=special[k%6];}ap_noise_tracker_result_t ar,br;baseline_update(&a,k,x,&ar);candidate_update(&b,k,x,&br);if(memcmp(&ar,&br,sizeof(ar))||memcmp(&a,&b,sizeof(a))){fprintf(stderr,"MISMATCH %u %u %u %u\n",bins[z],stress,f,k);return 1;}checks++;}baseline_next_frame(&a);candidate_next_frame(&b);if(memcmp(&a,&b,sizeof(a)))return 2;}}
 printf("EQUIVALENCE %lu PASS state_bytes=%zu\n",checks,sizeof(ap_noise_tracker_state_t));if(argc>1)return 0;
 for(unsigned z=0;z<4;z++)for(unsigned r=0;r<9;r++){double b,c;if(r%2){c=bench(1,bins[z]);b=bench(0,bins[z]);}else{b=bench(0,bins[z]);c=bench(1,bins[z]);}printf("PERF %u %u %.12f %.12f %.12f\n",bins[z],r,b,c,c/b);}return 0;}
