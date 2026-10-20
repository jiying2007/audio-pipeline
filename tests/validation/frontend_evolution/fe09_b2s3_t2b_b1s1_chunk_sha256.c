/* FE09 B1-S1 research-only SHA-256 byte identity (FIPS 180-4).
 * No source authentication: attacker with access to chunks and manifest can
 * rewrite hashes. Independently cross-verify digest with Python hashlib.
 */
#include "fe09_b2s3_t2b_b1s1_chunk_sha256.h"
#include <stdint.h>
#include <string.h>

static const uint32_t K[64] = {
UINT32_C(0x428a2f98),UINT32_C(0x71374491),UINT32_C(0xb5c0fbcf),UINT32_C(0xe9b5dba5),
UINT32_C(0x3956c25b),UINT32_C(0x59f111f1),UINT32_C(0x923f82a4),UINT32_C(0xab1c5ed5),
UINT32_C(0xd807aa98),UINT32_C(0x12835b01),UINT32_C(0x243185be),UINT32_C(0x550c7dc3),
UINT32_C(0x72be5d74),UINT32_C(0x80deb1fe),UINT32_C(0x9bdc06a7),UINT32_C(0xc19bf174),
UINT32_C(0xe49b69c1),UINT32_C(0xefbe4786),UINT32_C(0x0fc19dc6),UINT32_C(0x240ca1cc),
UINT32_C(0x2de92c6f),UINT32_C(0x4a7484aa),UINT32_C(0x5cb0a9dc),UINT32_C(0x76f988da),
UINT32_C(0x983e5152),UINT32_C(0xa831c66d),UINT32_C(0xb00327c8),UINT32_C(0xbf597fc7),
UINT32_C(0xc6e00bf3),UINT32_C(0xd5a79147),UINT32_C(0x06ca6351),UINT32_C(0x14292967),
UINT32_C(0x27b70a85),UINT32_C(0x2e1b2138),UINT32_C(0x4d2c6dfc),UINT32_C(0x53380d13),
UINT32_C(0x650a7354),UINT32_C(0x766a0abb),UINT32_C(0x81c2c92e),UINT32_C(0x92722c85),
UINT32_C(0xa2bfe8a1),UINT32_C(0xa81a664b),UINT32_C(0xc24b8b70),UINT32_C(0xc76c51a3),
UINT32_C(0xd192e819),UINT32_C(0xd6990624),UINT32_C(0xf40e3585),UINT32_C(0x106aa070),
UINT32_C(0x19a4c116),UINT32_C(0x1e376c08),UINT32_C(0x2748774c),UINT32_C(0x34b0bcb5),
UINT32_C(0x391c0cb3),UINT32_C(0x4ed8aa4a),UINT32_C(0x5b9cca4f),UINT32_C(0x682e6ff3),
UINT32_C(0x748f82ee),UINT32_C(0x78a5636f),UINT32_C(0x84c87814),UINT32_C(0x8cc70208),
UINT32_C(0x90befffa),UINT32_C(0xa4506ceb),UINT32_C(0xbef9a3f7),UINT32_C(0xc67178f2)
};
static uint32_t rotr(uint32_t x,unsigned s) {
    return (x>>s)|(x<<(32u-s));
}
int fe_b1s1_sha256(const uint8_t *data,size_t n,uint8_t out[32]) {
    uint32_t h[8] = {
       UINT32_C(0x6a09e667),UINT32_C(0xbb67ae85),
       UINT32_C(0x3c6ef372),UINT32_C(0xa54ff53a),
       UINT32_C(0x510e527f),UINT32_C(0x9b05688c),
       UINT32_C(0x1f83d9ab),UINT32_C(0x5be0cd19)
    };
    uint32_t w[64],v[8];
    uint8_t block[64];
    size_t blk, j, blocks;
    uint64_t bits;
    if(!out||(!data&&n)||n>1048576u) return -1;
    bits=(uint64_t)n*UINT64_C(8);
    blocks=(n+9u+63u)/64u;
    for(blk=0u;blk<blocks;++blk) {
        for(j=0u;j<64u;++j) {
            size_t p=blk*64u+j;
            if(p<n) block[j]=data[p];
            else if(p==n) block[j]=0x80u;
            else if(p>=blocks*64u-8u) {
                unsigned shift=(unsigned)((blocks*64u-1u-p)*8u);
                block[j]=(uint8_t)(bits>>shift);
            } else block[j]=0u;
        }
        for(j=0u;j<16u;++j) {
            size_t i=j*4u;
            w[j]=((uint32_t)block[i]<<24u)|
                 ((uint32_t)block[i+1u]<<16u)|
                 ((uint32_t)block[i+2u]<<8u)|
                 (uint32_t)block[i+3u];
        }
        for(j=16u;j<64u;++j) {
            uint32_t x=w[j-15u],y=w[j-2u];
            uint32_t s0=rotr(x,7u)^rotr(x,18u)^(x>>3u);
            uint32_t s1=rotr(y,17u)^rotr(y,19u)^(y>>10u);
            w[j]=w[j-16u]+s0+w[j-7u]+s1;
        }
        memcpy(v,h,sizeof(v));
        for(j=0u;j<64u;++j) {
            uint32_t s1=rotr(v[4],6u)^rotr(v[4],11u)^rotr(v[4],25u);
            uint32_t ch=(v[4]&v[5])^((~v[4])&v[6]);
            uint32_t t1=v[7]+s1+ch+K[j]+w[j];
            uint32_t s0=rotr(v[0],2u)^rotr(v[0],13u)^rotr(v[0],22u);
            uint32_t maj=(v[0]&v[1])^(v[0]&v[2])^(v[1]&v[2]);
            uint32_t t2=s0+maj;
            v[7]=v[6];v[6]=v[5];v[5]=v[4];v[4]=v[3]+t1;
            v[3]=v[2];v[2]=v[1];v[1]=v[0];v[0]=t1+t2;
        }
        for(j=0u;j<8u;++j) h[j]+=v[j];
    }
    for(j=0u;j<8u;++j) {
        out[4u*j]=(uint8_t)(h[j]>>24u);
        out[4u*j+1u]=(uint8_t)(h[j]>>16u);
        out[4u*j+2u]=(uint8_t)(h[j]>>8u);
        out[4u*j+3u]=(uint8_t)h[j];
    }
    return 0;
}
