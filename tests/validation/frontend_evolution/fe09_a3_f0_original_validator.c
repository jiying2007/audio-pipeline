/* The locked A0 implementation is compiled EXACTLY ONCE through this new
 * adapter. Do not compile fe09_b2s3_t3s2b1ba0_finite_outboard.c separately.
 * Its public bind/sink/name cap and all its original bytes remain unchanged.
 * Only its pure internal source_ok/valid_record are reused for finite17..49.
 */
#include "fe09_b2s3_t3s2b1ba0_finite_outboard.c"
#include "fe09_a3_f0_live_roll.h"

void fe_a3_f0_profile_init(fe_a3_f0_profile *p,uint32_t k) {
    if(!p)return;
    memset(p,0,sizeof(*p));
    if(k!=1u&&k!=2u)return;
    p->source.depth=k==1u?2u:4u;
    p->source.physical_mics=4u;p->source.input_hz=16000u;
    p->source.render_enabled=1u;
    p->source.capture_source_id=305u;p->source.render_source_id=405u;
    p->source.source_generation=UINT64_C(1234509876);
    p->slots[0]=2u;p->slots[1]=0u;p->slots[2]=3u;p->slots[3]=1u;
    p->physical_k=k;
}

const char *fe_a3_f0_validate_profile(const fe_a3_f0_profile *p) {
    if(!p)return "ORIGINAL_SOURCE_MISMATCH";
    if(p->source.physical_mics!=4u||p->source.input_hz!=16000u||
       p->source.render_enabled!=1u||p->source.capture_source_id!=305u||
       p->source.render_source_id!=405u||
       p->source.source_generation!=UINT64_C(1234509876)||
       (p->physical_k!=1u&&p->physical_k!=2u)||
       p->source.depth!=(p->physical_k==1u?2u:4u))
        return "ORIGINAL_SOURCE_MISMATCH";
    if(p->slots[0]!=2u||p->slots[1]!=0u||
       p->slots[2]!=3u||p->slots[3]!=1u)
        return "ORIGINAL_SLOT_MAP_MISMATCH";
    if(!source_ok(&p->source,p->slots))return "ORIGINAL_SOURCE_MISMATCH";
    return NULL;
}

const char *fe_a3_f0_validate_row_metadata(const fe_a3_f0_profile *p,
    const uint8_t row[FE_A3_F0_ROW_BYTES],uint64_t seq,
    const uint8_t prev[32]) {
    uint8_t digest[32];
    const char *error=fe_a3_f0_validate_profile(p);
    if(error)return error;
    if(!row||seq<16u||seq>49u)return "NEW_VALIDATOR_DOMAIN_REJECT";
    if(g64(row+48u)!=seq)return "GLOBAL_SEQUENCE_MISMATCH";
    if(g32(row)!=FE_B1S1_MANIFEST_MAGIC||
       g32(row+4u)!=FE_B1S1_MANIFEST_VERSION||
       g64(row+56u)!=UINT64_C(1)||g32(row+64u)!=1u)
        return "ORIGINAL_ROW_FORMAT_REJECT";
    if(g32(row+12u)!=p->source.input_hz||
       g32(row+16u)!=p->source.physical_mics||
       g64(row+20u)!=p->source.source_generation||
       g32(row+28u)!=p->source.capture_source_id||
       g32(row+32u)!=p->source.render_source_id||g32(row+36u)!=1u)
        return "ORIGINAL_SOURCE_MISMATCH";
    for(unsigned i=0u;i<4u;++i)
        if(g32(row+88u+4u*i)!=p->slots[i])
            return "ORIGINAL_SLOT_MAP_MISMATCH";
    if(prev&&memcmp(row+136u,prev,32u)!=0)
        return "PREVIOUS_WHOLE_ROW_MISMATCH";
    const uint32_t absent=(uint32_t)(seq==33u||seq==34u);
    if(g32(row+8u)!=(absent?FE_B1S0_RENDER_ABSENT:FE_B1S0_RENDER_PRESENT)||
       g32(row+40u)!=(seq>=35u?2u:1u)||
       g32(row+44u)!=(absent?FE_B1S0_ABSENT_SOURCE_REPORTED:0u)||
       g32(row+68u)!=(absent?1440u:1760u)||
       (absent&&g64(row+80u)!=UINT64_C(0)))
        return "FINITE_RENDER_SCHEDULE_MISMATCH";
    if(fe_b1s1_sha256(row,FE_B1S1_ROW_DIGEST_OFFSET,digest)!=0||
       memcmp(digest,row+FE_B1S1_ROW_DIGEST_OFFSET,32u)!=0)
        return "ORIGINAL_ROW_SELF_SHA_REJECT";
    return NULL;
}

const char *fe_a3_f0_validate_record(const fe_a3_f0_profile *p,
    const uint8_t row[FE_A3_F0_ROW_BYTES],const uint8_t *apx,size_t n,
    uint64_t seq,const uint8_t prev[32]) {
    fe_t3b1ba0_owner view;
    fe_s2_stream decoded;
    a0_witness witness;
    uint8_t digest[32];
    /* No actual bound A0 state is copied. This zeroed metadata view cannot
     * pass original same_fd/binding admission and cannot issue a byte ACK. */
    if(seq<17u||seq>49u)return "NEW_VALIDATOR_DOMAIN_REJECT";
    if(!row||!apx||!prev||n==0u||n>FE_T3S1_CHUNK_BYTES)
        return "ORIGINAL_RECORD_FORMAT_REJECT";
    const char *error=fe_a3_f0_validate_row_metadata(p,row,seq,prev);
    if(error)return error;
    if(n!=(size_t)g32(row+68u))return "ORIGINAL_RECORD_SIZE_REJECT";
    memset(&view,0,sizeof(view));view.dirfd=-1;
    view.source=p->source;memcpy(view.slots,p->slots,sizeof(view.slots));
    if(valid_record(&view,row,apx,n,seq,prev))return NULL;

    /* Diagnostic predicates use the same original SHA/decoder/replay, not
     * a new codec. CRC_REJECT denotes an original codec refusal in the
     * registered CRC control; it does not infer an unseen historical cause. */
    if(fe_b1s1_sha256(apx,n,digest)!=0||memcmp(digest,row+104u,32u)!=0)
        return "ORIGINAL_APX3_SHA_REJECT";
    if(fe_s2_decode(apx,n,&decoded)!=FE_S2_OK)
        return "ORIGINAL_CODEC_CRC_REJECT";
    memset(&witness,0,sizeof(witness));
    witness.rate=p->source.input_hz;witness.mics=p->source.physical_mics;
    witness.render=(uint32_t)(g32(row+8u)==FE_B1S0_RENDER_PRESENT);
    witness.capture_hash=g64(row+72u);witness.render_hash=g64(row+80u);
    if(fe_s2_replay(apx,n,original_pcm,&witness,NULL)!=FE_S2_OK||
       witness.seen!=1u)
        return "ORIGINAL_REPLAY_FNV_REJECT";
    return "ORIGINAL_RECORD_SEMANTICS_REJECT";
}
