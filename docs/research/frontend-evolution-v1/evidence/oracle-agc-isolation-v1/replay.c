#define _POSIX_C_SOURCE 200809L
#include "enhance/ap_enhance.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#define FRAMES 629u
#define N (FRAMES*160u)
static int read_exact(const char *p,void *b,size_t n){FILE*f=fopen(p,"rb");if(!f)return 0;int ok=fread(b,1,n,f)==n&&fgetc(f)==EOF;return fclose(f)==0&&ok;}
static int write_exact(const char*p,const void*b,size_t n){FILE*f=fopen(p,"wb");if(!f)return 0;int ok=fwrite(b,1,n,f)==n;return fclose(f)==0&&ok;}
int main(int argc,char**argv){
 if(argc!=8)return 2;
 float *input=malloc(N*sizeof(float)),*output=malloc(N*sizeof(float)),*states=malloc(FRAMES*2*sizeof(float));uint8_t allow[FRAMES];
 if(!input||!output||!states)return 3;
 if(!read_exact(argv[1],input,N*sizeof(float))||!read_exact(argv[2],allow,FRAMES))return 4;
 for(unsigned i=0;i<FRAMES;i++)if(allow[i]>1)return 5;
 float target=strcmp(argv[3],"call")==0?-20.0f:-18.0f;if(strcmp(argv[3],"call")&&strcmp(argv[3],"assistant"))return 6;
 int repeats=atoi(argv[4]);if(repeats!=1&&repeats!=100)return 7;
 struct timespec a,b;if(clock_gettime(CLOCK_THREAD_CPUTIME_ID,&a))return 8;
 for(int r=0;r<repeats;r++){
  ap_agc_state_t s;ap_agc_init(&s,target,-2.0f);
  for(unsigned f=0;f<FRAMES;f++){
   memcpy(output+f*160,input+f*160,160*sizeof(float));states[f*2]=s.gain;
   ap_agc_process_controlled(&s,output+f*160,160,allow[f]);states[f*2+1]=s.gain;
  }
 }
 if(clock_gettime(CLOCK_THREAD_CPUTIME_ID,&b))return 8;
 double sec=(double)(b.tv_sec-a.tv_sec)+1e-9*(double)(b.tv_nsec-a.tv_nsec);
 if(!write_exact(argv[5],output,N*sizeof(float))||!write_exact(argv[6],states,FRAMES*2*sizeof(float)))return 9;
 FILE*f=fopen(argv[7],"w");if(!f)return 10;fprintf(f,"{\"thread_cpu_seconds\":%.17g,\"repeats\":%d,\"frames_per_repeat\":629,\"samples_per_repeat\":100640}\n",sec,repeats);if(fclose(f))return 10;
 free(input);free(output);free(states);return 0;
}
