/* #797 FE09 T3-S2-B0: a NONINSTALLED original FBS1 source-chain INDEX.
 * No APX3 serializer/parser fork, no filesystem syscalls, no rolling GC.
 * Only the original S2 decode/replay and original B1S1 SHA implementation
 * can validate actual APX3 input; all fields in this file describe OUTER
 * index/source authority, not a second APX3 codec or production SDK.
 */
#include "fe09_b2s3_t3s2b0_manifest.h"
#include <limits.h>
#include <stdint.h>
#include <string.h>

#if UINT_MAX != UINT32_MAX
#error "T3-S2-B0 requires 32-bit uint32 manifest fields"
#endif

static void p32(uint8_t *p,uint32_t v) {
    for(unsigned i=0u;i<4u;++i)p[i]=(uint8_t)(v>>(8u*i));
}
static void p64(uint8_t *p,uint64_t v) {
    for(unsigned i=0u;i<8u;++i)p[i]=(uint8_t)(v>>(8u*i));
}
static uint32_t g32(const uint8_t *p) {
    uint32_t v=0u;
    for(unsigned i=0u;i<4u;++i)v|=(uint32_t)p[i]<<(8u*i);
    return v;
}
static uint64_t g64(const uint8_t *p) {
    uint64_t v=UINT64_C(0);
    for(unsigned i=0u;i<8u;++i)v|=(uint64_t)p[i]<<(8u*i);
    return v;
}
static int zero32(const uint8_t p[32]) {
    uint8_t zero[32]={0};
    return memcmp(p,zero,32u)==0;
}
static int disjoint(const void *a,size_t na,const void *b,size_t nb) {
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    if(!a||!b||!na||!nb)return 0;
    if(x>UINTPTR_MAX-na||y>UINTPTR_MAX-nb)return 0;
    return x+na<=y||y+nb<=x;
}
static int valid_original_owner(const fe_t3s2a_spool *s) {
    return s && s->binding_complete==1u &&
        (s->mics==1u||s->mics==2u||s->mics==4u) &&
        (s->rate_hz==16000u||s->rate_hz==32000u||s->rate_hz==48000u) &&
        s->render_enabled<=1u && s->capture_id!=0u &&
        s->generation>UINT64_C(0) && s->generation!=UINT64_MAX &&
        (s->render_enabled ?
          (s->render_id!=0u && s->render_id!=s->capture_id) :
          s->render_id==0u) &&
        s->maximum_files>=1u &&
        s->maximum_files<=FE_T3S2A_MAX_FILES;
}
static int bound(const fe_t3s2b0_index *i) {
    const fe_t3s2a_spool *s;
    uint32_t mask=0u;
    if(!i||(s=i->source)==NULL||!valid_original_owner(s)||
       i->maximum_rows<1u||i->maximum_rows>FE_T3S2B0_MAX_ROWS||
       i->maximum_rows>s->maximum_files||
       i->source_generation!=s->generation||
       i->rate_hz!=s->rate_hz||i->physical_mics!=s->mics||
       i->render_enabled!=s->render_enabled||
       i->capture_id!=s->capture_id||i->render_id!=s->render_id||
       i->count>i->maximum_rows ||
       !disjoint(i,sizeof(*i),s,sizeof(*s)))
        return 0;
    for(uint32_t n=0u;n<4u;++n) {
        uint32_t x=i->physical_to_slot[n];
        if(x!=s->slots[n])return 0;
        if(n<i->physical_mics) {
            if(x>=i->physical_mics||(mask&(1u<<x)))return 0;
            mask|=1u<<x;
        }else if(x!=UINT32_MAX)return 0;
    }
    if(mask!=((1u<<i->physical_mics)-1u)||
       !zero32(i->left_anchor_sha256))return 0;
    if(i->count==0u) {
        if(i->first_seq||i->last_seq||i->high_water)return 0;
    } else if(i->first_seq!=UINT64_C(1) ||
              i->last_seq!=(uint64_t)i->count ||
              i->high_water!=i->last_seq)return 0;
    return 1;
}
/* 160-byte source-index header: 0 magic,4 version,8 header bytes,
 * 12 original FBS1 row size,16 quota,20 count,24 rate,28 physical mics,
 * 32 Render enabled,36 Capture owner,40 Render owner,44..60 map,
 * 60 generation u64,68 last seq u64,76 first seq u64,
 * 84 high water u64,92..124 previous-retained-row SHA anchor (zero in B0),
 * 124..156 SHA256(whole index with this field zeroed),156..160 reserved=0.
 * Original FBS1 complete 200-byte row bytes follow starting at byte 160.
 */
static int image(const fe_t3s2b0_index *i,uint8_t out[FE_T3S2B0_MAX_BYTES],
                 size_t *length) {
    size_t n;
    if(!bound(i)||!out||!length)return 0;
    n=FE_T3S2B0_HEADER_BYTES+(size_t)i->count*FE_T3S1_ROW_BYTES;
    if(n>FE_T3S2B0_MAX_BYTES)return 0;
    memset(out,0,n);
    p32(out,FE_T3S2B0_MAGIC);
    p32(out+4u,FE_T3S2B0_VERSION);
    p32(out+8u,FE_T3S2B0_HEADER_BYTES);
    p32(out+12u,FE_T3S1_ROW_BYTES);
    p32(out+16u,i->maximum_rows);
    p32(out+20u,i->count);
    p32(out+24u,i->rate_hz);
    p32(out+28u,i->physical_mics);
    p32(out+32u,i->render_enabled);
    p32(out+36u,i->capture_id);
    p32(out+40u,i->render_id);
    for(unsigned j=0u;j<4u;++j)
        p32(out+44u+4u*j,i->physical_to_slot[j]);
    p64(out+60u,i->source_generation);
    p64(out+68u,i->last_seq);
    p64(out+76u,i->first_seq);
    p64(out+84u,i->high_water);
    memcpy(out+92u,i->left_anchor_sha256,32u);
    for(uint32_t j=0u;j<i->count;++j)
        memcpy(out+FE_T3S2B0_HEADER_BYTES+(size_t)j*FE_T3S1_ROW_BYTES,
               i->rows[j],FE_T3S1_ROW_BYTES);
    *length=n;
    return 1;
}
static int root_hash(const fe_t3s2b0_index *i,uint8_t hash[32]) {
    uint8_t data[FE_T3S2B0_MAX_BYTES];
    size_t size=0u;
    if(!image(i,data,&size))return 0;
    return fe_b1s1_sha256(data,size,hash)==0;
}
static int integrity(const fe_t3s2b0_index *i) {
    uint8_t digest[32];
    return root_hash(i,digest) && memcmp(digest,i->root_sha256,32u)==0;
}
int fe_t3s2b0_bind(fe_t3s2b0_index *i,
    const fe_t3s2a_spool *s,uint32_t maximum_rows) {
    fe_t3s2b0_index t;
    if(!i||!valid_original_owner(s)||
       maximum_rows<1u||maximum_rows>FE_T3S2B0_MAX_ROWS||
       maximum_rows>s->maximum_files||
       !disjoint(i,sizeof(*i),s,sizeof(*s)))return -1;
    memset(&t,0,sizeof(t));
    t.source=s;
    t.source_generation=s->generation;
    t.rate_hz=s->rate_hz;t.physical_mics=s->mics;
    t.render_enabled=s->render_enabled;
    t.capture_id=s->capture_id;t.render_id=s->render_id;
    memcpy(t.physical_to_slot,s->slots,sizeof(t.physical_to_slot));
    t.maximum_rows=maximum_rows;
    if(!root_hash(&t,t.root_sha256))return -1;
    memcpy(i,&t,sizeof(t));
    return 0;
}
int fe_t3s2b0_can_accept(const fe_t3s2b0_index *i) {
    if(!i||!integrity(i))return 0;
    return i->count<i->maximum_rows &&
           i->source->committed==(uint64_t)i->count;
}
static int row_policy(const fe_t3s2b0_index *i,const uint8_t *row,
                      uint64_t sequence,const uint8_t prior[32]) {
    uint8_t hash[32];
    uint32_t event;
    if(!row||!prior||!sequence||
       g32(row)!=FE_B1S1_MANIFEST_MAGIC ||
       g32(row+4u)!=FE_B1S1_MANIFEST_VERSION ||
       g32(row+12u)!=i->rate_hz ||
       g32(row+16u)!=i->physical_mics ||
       g64(row+20u)!=i->source_generation ||
       g32(row+28u)!=i->capture_id ||
       g32(row+32u)!=i->render_id ||
       g32(row+36u)!=1u ||
       g64(row+48u)!=sequence ||
       g64(row+56u)!=UINT64_C(1)||
       g32(row+64u)!=1u ||
       g32(row+68u)<FE_S2_HEADER_BYTES ||
       g32(row+68u)>FE_T3S1_CHUNK_BYTES ||
       memcmp(row+136u,prior,32u)!=0 ||
       fe_b1s1_sha256(row,FE_B1S1_ROW_DIGEST_OFFSET,hash)!=0 ||
       memcmp(row+FE_B1S1_ROW_DIGEST_OFFSET,hash,32u)!=0)
        return 0;
    event=g32(row+8u);
    if(event>FE_B1S0_RENDER_ABSENT||
       (i->render_enabled ? event==FE_B1S0_RENDER_DISABLED :
                            event!=FE_B1S0_RENDER_DISABLED)||
       (i->render_enabled?g32(row+40u)==0u:g32(row+40u)!=0u)||
       (event==FE_B1S0_RENDER_ABSENT ?
         g32(row+44u)!=FE_B1S0_ABSENT_SOURCE_REPORTED :
         g32(row+44u)!=0u) ||
       (event!=FE_B1S0_RENDER_PRESENT && g64(row+80u)!=UINT64_C(0)))
        return 0;
    for(unsigned n=0u;n<4u;++n)
        if(g32(row+88u+4u*n)!=i->physical_to_slot[n])return 0;
    return 1;
}
typedef struct {
    uint64_t cap_hash,ref_hash;
    uint32_t mics,render,count;
} pcm_witness;
static uint64_t byte_fnv(const uint8_t *p,size_t n) {
    uint64_t h=UINT64_C(14695981039346656037);
    for(size_t k=0u;k<n;++k)
        h=(h^(uint64_t)p[k])*UINT64_C(1099511628211);
    return h;
}
static int original_replay(const fe_s2_stream *s,uint32_t index,
    uint64_t sequence,uint32_t cap_flags,uint32_t ref_flags,
    const uint8_t *cap,size_t ncap,const uint8_t *ref,size_t nref,
    void *ctx) {
    pcm_witness *w=(pcm_witness *)ctx;
    if(!s||!w||index||sequence!=UINT64_C(1)||
       cap_flags||ref_flags||s->frames!=1u||
       s->config.physical_mics!=w->mics||
       s->config.render_channels!=w->render||
       ncap!=(size_t)s->config.rate_hz*w->mics/50u ||
       nref!=(size_t)s->config.rate_hz*w->render/50u ||
       !cap||byte_fnv(cap,ncap)!=w->cap_hash ||
       (nref ? (!ref||byte_fnv(ref,nref)!=w->ref_hash) :
           (ref!=NULL||w->ref_hash!=UINT64_C(0))))
        return 1;
    ++w->count;
    return 0;
}
static int file_policy(const fe_t3s2b0_index *i,
    const fe_t3s1_slot *slot,uint64_t seq,const uint8_t prior[32]) {
    uint8_t hash[32];
    fe_s2_stream d;
    pcm_witness w;
    const uint8_t *row;
    uint32_t render;
    size_t n;
    if(!slot)return 0;
    row=slot->canonical_row;
    n=slot->apx3_bytes;
    if(n<FE_S2_HEADER_BYTES||n>FE_T3S1_CHUNK_BYTES ||
       !row_policy(i,row,seq,prior) ||
       g32(row+68u)!=(uint32_t)n ||
       fe_b1s1_sha256(slot->apx3,n,hash)!=0 ||
       memcmp(row+104u,hash,32u)!=0 ||
       fe_s2_decode(slot->apx3,n,&d)!=FE_S2_OK ||
       d.frames!=1u||d.total_bytes!=n)
        return 0;
    render=(uint32_t)(g32(row+8u)==FE_B1S0_RENDER_PRESENT);
    if(d.config.rate_hz!=i->rate_hz||
       d.config.physical_mics!=i->physical_mics||
       d.config.render_channels!=render||
       d.config.capture_source_id!=i->capture_id||
       d.config.render_source_id!=(render?i->render_id:0u)||
       d.config.capture_epoch!=1u||
       d.config.render_epoch!=(render?g32(row+40u):0u)||
       d.config.clock_authority||d.config.capture_timestamp_valid||
       d.config.render_timestamp_valid)return 0;
    for(unsigned k=0u;k<4u;++k)
        if(d.config.physical_to_capture_slot[k]!=i->physical_to_slot[k])
            return 0;
    memset(&w,0,sizeof(w));
    w.mics=i->physical_mics;w.render=render;
    w.cap_hash=g64(row+72u);w.ref_hash=g64(row+80u);
    return fe_s2_replay(slot->apx3,n,original_replay,&w,NULL)==FE_S2_OK &&
           w.count==1u;
}
int fe_t3s2b0_observe_acked(fe_t3s2b0_index *i,
    const fe_t3s1_slot *slot,const fe_t3s1_drain_receipt *receipt) {
    uint64_t seq;
    uint8_t hash[32],prior[32];
    fe_t3s2b0_index next;
    if(!i||!slot||!receipt||!integrity(i)||
       i->count>=i->maximum_rows||
       i->source->committed!=(uint64_t)i->count+UINT64_C(1)||
       !disjoint(i,sizeof(*i),slot,sizeof(*slot))||
       !disjoint(i,sizeof(*i),receipt,sizeof(*receipt))||
       !disjoint(i->source,sizeof(*i->source),slot,sizeof(*slot))||
       !disjoint(i->source,sizeof(*i->source),receipt,sizeof(*receipt)))return -1;
    seq=(uint64_t)i->count+UINT64_C(1);
    if(receipt->source_sequence!=seq||
       receipt->source_capture_id!=i->capture_id||
       receipt->source_render_id!=i->render_id||
       receipt->render_event!=g32(slot->canonical_row+8u) ||
       receipt->apx3_bytes!=slot->apx3_bytes||
       receipt->canonical_row_bytes!=FE_T3S1_ROW_BYTES||
       receipt->actually_accounted_bytes!=
           (size_t)slot->apx3_bytes+FE_T3S1_ROW_BYTES||
       receipt->hardware_qualified||receipt->durable_qualified||
       receipt->product_qualified||
       memcmp(i->source->committed_last_row,
              slot->canonical_row,FE_T3S1_ROW_BYTES)!=0)
        return -1;
    if(i->count==0u)memset(prior,0,sizeof(prior));
    else if(fe_b1s1_sha256(i->rows[i->count-1u],
                          FE_T3S1_ROW_BYTES,prior)!=0)return -1;
    if(!file_policy(i,slot,seq,prior)||
       fe_b1s1_sha256(slot->canonical_row,
           FE_T3S1_ROW_BYTES,hash)!=0 ||
       memcmp(i->source->prior_row_sha256,hash,32u)!=0)
        return -1;
    next=*i;
    memcpy(next.rows[next.count],slot->canonical_row,
           FE_T3S1_ROW_BYTES);
    ++next.count;
    next.first_seq=UINT64_C(1);
    next.last_seq=(uint64_t)next.count;
    next.high_water=next.last_seq;
    if(!root_hash(&next,next.root_sha256))return -1;
    *i=next;
    return 0;
}
int fe_t3s2b0_encode(const fe_t3s2b0_index *i,
    uint8_t *dest,size_t capacity,size_t *written) {
    uint8_t data[FE_T3S2B0_MAX_BYTES];
    uint8_t hash[32];
    size_t size=0u;
    if(!i||!dest||!written||!integrity(i)||
       i->source->committed!=(uint64_t)i->count||
       !disjoint(i,sizeof(*i),dest,capacity)||
       !disjoint(i->source,sizeof(*i->source),dest,capacity)||
       !disjoint(i,sizeof(*i),written,sizeof(*written))||
       !disjoint(i->source,sizeof(*i->source),written,sizeof(*written))||
       !disjoint(written,sizeof(*written),dest,capacity)||
       !image(i,data,&size)||capacity<size)return -1;
    if(fe_b1s1_sha256(data,size,hash)!=0||
       memcmp(hash,i->root_sha256,32u)!=0)return -1;
    memcpy(data+124u,hash,32u);
    memcpy(dest,data,size);
    *written=size;
    return 0;
}
int fe_t3s2b0_decode(fe_t3s2b0_index *result,
    const fe_t3s2a_spool *owner,const uint8_t *data,size_t bytes) {
    fe_t3s2b0_index candidate;
    uint8_t temp[FE_T3S2B0_MAX_BYTES],hash[32],prior[32]={0};
    uint32_t maximum,count;
    size_t expected=0u;
    if(!result||!owner||!data||
       bytes<FE_T3S2B0_HEADER_BYTES || bytes>FE_T3S2B0_MAX_BYTES||
       !disjoint(result,sizeof(*result),data,bytes)||
       !disjoint(owner,sizeof(*owner),data,bytes)||
       !disjoint(result,sizeof(*result),owner,sizeof(*owner))||
       g32(data)!=FE_T3S2B0_MAGIC||
       g32(data+4u)!=FE_T3S2B0_VERSION||
       g32(data+8u)!=FE_T3S2B0_HEADER_BYTES ||
       g32(data+12u)!=FE_T3S1_ROW_BYTES ||
       g32(data+156u)!=0u)return -1;
    maximum=g32(data+16u);
    count=g32(data+20u);
    if(!maximum||maximum>FE_T3S2B0_MAX_ROWS||
       count>maximum||
       bytes!=FE_T3S2B0_HEADER_BYTES+(size_t)count*FE_T3S1_ROW_BYTES||
       owner->committed!=(uint64_t)count||
       fe_t3s2b0_bind(&candidate,owner,maximum)!=0)
        return -1;
    if(g32(data+24u)!=candidate.rate_hz||
       g32(data+28u)!=candidate.physical_mics||
       g32(data+32u)!=candidate.render_enabled||
       g32(data+36u)!=candidate.capture_id||
       g32(data+40u)!=candidate.render_id||
       g64(data+60u)!=candidate.source_generation||
       g64(data+68u)!=(uint64_t)count||
       g64(data+76u)!=(count?UINT64_C(1):UINT64_C(0))||
       g64(data+84u)!=(uint64_t)count ||
       !zero32(data+92u))return -1;
    for(unsigned k=0u;k<4u;++k)
        if(g32(data+44u+4u*k)!=candidate.physical_to_slot[k])
            return -1;
    memcpy(temp,data,bytes);
    memset(temp+124u,0,32u);
    if(fe_b1s1_sha256(temp,bytes,hash)!=0 ||
       memcmp(data+124u,hash,32u)!=0)return -1;
    for(uint32_t k=0u;k<count;++k) {
        const uint8_t *row=data+FE_T3S2B0_HEADER_BYTES+
                           (size_t)k*FE_T3S1_ROW_BYTES;
        if(!row_policy(&candidate,row,(uint64_t)k+UINT64_C(1),prior) ||
           fe_b1s1_sha256(row,FE_T3S1_ROW_BYTES,prior)!=0)
            return -1;
        memcpy(candidate.rows[k],row,FE_T3S1_ROW_BYTES);
    }
    if(count && (memcmp(candidate.rows[count-1u],
                        owner->committed_last_row,
                        FE_T3S1_ROW_BYTES)!=0||
                 memcmp(prior,owner->prior_row_sha256,32u)!=0))
        return -1;
    candidate.count=count;
    candidate.first_seq=count?UINT64_C(1):UINT64_C(0);
    candidate.last_seq=(uint64_t)count;
    candidate.high_water=candidate.last_seq;
    if(!image(&candidate,temp,&expected)||
       expected!=bytes||
       !root_hash(&candidate,candidate.root_sha256)||
       memcmp(candidate.root_sha256,hash,32u)!=0)
        return -1;
    *result=candidate;
    return 0;
}
