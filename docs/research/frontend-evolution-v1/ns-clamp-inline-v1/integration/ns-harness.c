#include "enhance/ap_enhance.h"
#include <stdio.h>
#include <string.h>
#include <stdint.h>
static uint32_t r=20261114u;
static float sample(void){r^=r<<13;r^=r>>17;r^=r<<5;return (float)(int32_t)r/2147483648.0f*.1f;}
int main(int argc,char**argv){if(argc!=2)return 2;FILE*f=fopen(argv[1],"wb");if(!f)return 3;unsigned count=0;for(unsigned n=80;n<=160;n+=80)for(unsigned mode=0;mode<3;mode++){ap_ns_state_t s;ap_ns_init(&s,n);for(unsigned t=0;t<600;t++){float in[160]={0},echo[160]={0},out[160]={0};ap_ns_result_t result;for(unsigned i=0;i<n;i++){in[i]=t%97==0?0.f:sample();echo[i]=sample();}if(t==300)ap_ns_init(&s,n);ap_ns_process(&s,(ap_enhance_mode_t)mode,.07f,in,t%5?echo:NULL,out,n,t%2,(t/30)%2,(t/47)%2,&result);if(fwrite(out,sizeof(float),n,f)!=n||fwrite(&s,sizeof(s),1,f)!=1||fwrite(&result,sizeof(result),1,f)!=1)return 4;count++;}}if(fclose(f))return 5;printf("NS_FRAMES %u PASS\n",count);return 0;}
