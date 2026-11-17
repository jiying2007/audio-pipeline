#include "frontend/ap_frontend.h"
#include <stdio.h>
#include <string.h>
#include <stdint.h>
/* Engineering equivalence only: no corpus or acoustic promotion. */
int main(int argc, char **argv) {
 FILE *trace=argc==2?fopen(argv[1],"wb"):NULL;
 if(argc>2 || (argc==2 && !trace)) return 2;
 unsigned failures=0,cases=0;
 for(unsigned rate=8000;rate<=16000;rate+=8000)
 for(int lag=-8;lag<=8;lag++) for(int alias=0;alias<3;alias++)
 for(int track=0;track<2;track++) for(int route=0;route<5;route++) {
  ap_beamformer_state_t ref,test; unsigned n=rate/100;
  ap_beamformer_init(&ref,rate,150); ref.lag=lag; ref.max_lag=8;
  ref.fallback_lag=lag; ref.fallback_active=route!=0;
  ref.fallback_hard_fault=route>=3;
  ref.fallback_strong_channel=(route==2||route==4);
  ref.fallback_gain=0.75f; test=ref;
  for(unsigned frame=0;frame<12;frame++) {
   float a[160],b[160],aa[160],bb[160],out[160];
   for(unsigned i=0;i<n;i++) {
    a[i]=(float)((int)((i+frame*7)%23)-11)*0.001f;
    b[i]=(float)((int)((i+frame*3)%17)-8)*0.002f;
   }
   if(alias==2) memcpy(b,a,n*sizeof(float));
   memcpy(aa,a,n*sizeof(float)); memcpy(bb,b,n*sizeof(float));
   ap_beamformer_process(&ref,track,a,b,out,n);
   ap_beamformer_process(&test,track,aa,alias==2?aa:bb,alias==1?bb:aa,n);
   if(trace && (fwrite(out,sizeof(float),n,trace)!=n || fwrite(&ref,sizeof(ref),1,trace)!=1)) return 2;
   cases++;
   if(memcmp(out,alias==1?bb:aa,n*sizeof(float))||memcmp(&ref,&test,sizeof ref)) {
    if(failures<4) printf("mismatch rate=%u lag=%d alias=%d track=%d route=%d frame=%u\n",rate,lag,alias,track,route,frame);
    failures++;
   }
  }
 }
 printf("cases=%u failures=%u state_bytes=%zu\n",cases,failures,sizeof(ap_beamformer_state_t));
 if(trace && fclose(trace)) return 2;
 return failures?1:0;
}
