#include "audio_pipeline/audio_modules.h"
#include <stdio.h>
#include <string.h>
#include <math.h>
int main(void) {
 unsigned cases=0,fail=0;
 for(unsigned rate=8000;rate<=16000;rate+=8000)
 for(int track=0;track<2;track++)
 for(int alias=0;alias<3;alias++) {
  _Alignas(16) unsigned char sa[512]={0},sb[512]={0};
  ap_beamformer_module_t *a,*b; size_t n=rate/100, size=ap_module_beamformer_state_size();
  if(size>sizeof sa || ap_module_beamformer_init(sa,sizeof sa,rate,150,&a)!=AP_OK ||
      ap_module_beamformer_init(sb,sizeof sb,rate,150,&b)!=AP_OK) return 2;
  for(unsigned f=0;f<120;f++) {
   float x[160],y[160],xx[160],yy[160],out[160];
   unsigned char before[512];
   if(f==61) { ap_module_beamformer_reset(a); ap_module_beamformer_reset(b); }
   for(size_t i=0;i<n;i++) {
    x[i]=sinf((float)(f*n+i)*.17f)*.02f;
    y[i]=sinf((float)(f*n+i+4)*.17f)*.017f;
   }
   if(alias==2) memcpy(y,x,n*sizeof(float));
   memcpy(xx,x,n*sizeof(float)); memcpy(yy,y,n*sizeof(float));
   memset(out,0x5a,sizeof out); memcpy(before,sa,sizeof sa);
   ap_status_t ra=ap_module_beamformer_process(a,track,x,y,out,n);
   ap_status_t rb=ap_module_beamformer_process(b,track,xx,alias==2?xx:yy,alias==1?yy:xx,n);
   cases++;
#if !AP_BUILD_BF_DIRECTION_TRACKING
   if(track) {
    unsigned char sentinel[sizeof out]; memset(sentinel,0x5a,sizeof sentinel);
    if(ra!=AP_ESTATE||rb!=AP_ESTATE||memcmp(before,sa,sizeof sa)||
       memcmp(sa,sb,sizeof sa)||memcmp(sentinel,out,sizeof out)||
       memcmp(x,xx,n*sizeof(float))||memcmp(y,yy,n*sizeof(float))) fail++;
    continue;
   }
#endif
   if(ra!=AP_OK||rb!=AP_OK||memcmp(sa,sb,size)||
      memcmp(out,alias==1?yy:xx,n*sizeof(float))) fail++;
  }
 }
 printf("public_wrapper cases=%u failures=%u tracking_enabled=%d state_bytes=%zu\n",
        cases,fail,AP_BUILD_BF_DIRECTION_TRACKING,ap_module_beamformer_state_size());
 return fail?1:0;
}
