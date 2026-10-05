/* Offline free-field stimulus renderer, NOT deployable DSP or a real RIR.
 * First-party 63-tap Hann-windowed sinc; uses future samples and zero extension.
 * Geometry file: channel-count gain, followed by source advances in samples.
 */
#include <errno.h>
#include <float.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

_Static_assert(sizeof(double)==8 && DBL_MANT_DIG==53, "IEEE binary64 required");
#define N 64000
#define PI 3.14159265358979323846264338327950288
int main(int argc,char **argv) {
    FILE *in=NULL,*cfg=NULL,*out=NULL;
    unsigned char *raw=NULL;
    double *x=NULL;
    double gain,advance[4],weights[4][63];
    int offset[4][63],channels=0,result=2;
    char extra;
    if(argc!=4)return 2;
    cfg=fopen(argv[1],"rb");
    if(!cfg || fscanf(cfg,"%d %lf",&channels,&gain)!=2 || channels<1 || channels>4 ||
       !isfinite(gain) || gain<=0 || gain>1000)goto done;
    for(int m=0;m<channels;++m) {
        if(fscanf(cfg,"%lf",&advance[m])!=1 || !isfinite(advance[m]) || fabs(advance[m])>16)goto done;
        int base=(int)floor(advance[m]);double sum=0;
        for(int j=0;j<63;++j) {
            int k=base+j-31;double t=advance[m]-(double)k;
            double sinc=fabs(t)<1e-14 ? 1.0 : sin(PI*t)/(PI*t);
            double window=fabs(t)<=32 ? 0.5*(1.0+cos(PI*t/32.0)) : 0.0;
            offset[m][j]=k; weights[m][j]=sinc*window;sum+=weights[m][j];
        }
        if(!isfinite(sum)||fabs(sum)<0.1)goto done;
        for(int j=0;j<63;++j)weights[m][j]/=sum;
    }
    if(fscanf(cfg," %c",&extra)==1 || ferror(cfg))goto done;
    in=fopen(argv[2],"rb");if(!in)goto done;
    raw=malloc(2u*N);x=malloc(sizeof(double)*N);if(!raw||!x)goto done;
    if(fread(raw,1,2u*N,in)!=2u*N || fgetc(in)!=EOF || ferror(in))goto done;
    for(int t=0;t<N;++t) {
        unsigned u=(unsigned)raw[2*t]|((unsigned)raw[2*t+1]<<8);
        int v=u>=32768u ? (int)u-65536 : (int)u;
        x[t]=((double)v/32768.0)*gain;
    }
    out=fopen(argv[3],"wbx");if(!out)goto done;
    for(int t=0;t<N;++t)for(int m=0;m<channels;++m) {
        double y=0;uint64_t bits;unsigned char encoded[8];
        for(int j=0;j<63;++j) {int at=t+offset[m][j];if(at>=0 && at<N)y+=weights[m][j]*x[at];}
        if(!isfinite(y))goto done;
        memcpy(&bits,&y,sizeof(bits));
        for(unsigned k=0;k<8;++k)encoded[k]=(unsigned char)((bits>>(8u*k))&255u);
        if(fwrite(encoded,1,8,out)!=8)goto done;
    }
    result=0;
done:
    free(raw);free(x);
    if(in && fclose(in)!=0)result=2;
    if(cfg && fclose(cfg)!=0)result=2;
    if(out && fclose(out)!=0)result=2;
    if(result)fputs("speech rendering failed; partial output is not success\n",stderr);
    return result;
}
