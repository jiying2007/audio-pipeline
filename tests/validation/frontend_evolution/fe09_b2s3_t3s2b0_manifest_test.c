/* #797 actual first-party original S2 APX3 + S1 consumer + S2-A outboard
 * followed by B0 source-index. Hosted POSIX research, NOT a rolling archive,
 * physical powercut, real array microphone or product SDK qualification.
 */
#define _POSIX_C_SOURCE 200809L
#include "fe09_b2s3_t3s2b0_manifest.h"
#include <fcntl.h>
#include <inttypes.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static unsigned PROFILES,NEGATIVES,ROUNDTRIPS,FRAMES,RECOVERIES;
static void must(int condition,const char *why) {
    if(!condition){fprintf(stderr,"FE09_T3S2B0_NOT_ADMITTED reason=%s\n",why);exit(1);}
}
static void reject(int condition,const char *why) {
    must(condition,why);++NEGATIVES;
}
static void p32(uint8_t *p,uint32_t v) {
    for(unsigned i=0u;i<4u;++i)p[i]=(uint8_t)(v>>(8u*i));
}
static void p64(uint8_t *p,uint64_t v) {
    for(unsigned i=0u;i<8u;++i)p[i]=(uint8_t)(v>>(8u*i));
}
static uint64_t fnv_pcm(const int16_t *p,size_t n) {
    uint64_t h=UINT64_C(14695981039346656037);
    for(size_t i=0u;i<n;++i) {
        uint16_t v=(uint16_t)p[i];
        h=(h^(uint8_t)v)*UINT64_C(1099511628211);
        h=(h^(uint8_t)(v>>8u))*UINT64_C(1099511628211);
    }
    return h;
}
static const uint32_t MICS[4]={1u,2u,4u,4u};
static const uint32_t MAPS[4][4]={
    {0u,UINT32_MAX,UINT32_MAX,UINT32_MAX},
    {1u,0u,UINT32_MAX,UINT32_MAX},
    {2u,0u,3u,1u},
    {3u,2u,1u,0u}
};
static const uint32_t RATES[3]={16000u,32000u,48000u};
typedef struct {
    fe_b1s0_config config;
    fe_t3s2a_spool storage_owner;
    fe_t3s2b0_index index;
    fe_t3s1_ring ring;
    fe_t3s1_slot *slots;
    uint32_t k,cap;
    int fd;
    char dir[64];
    int16_t capture[1920],render[480];
} fixture;
static void setup(fixture *f,uint32_t scene,uint32_t rate,
                  uint32_t render,uint32_t slots,uint32_t cap) {
    memset(f,0,sizeof(*f));
    f->fd=-1;
    f->k=slots;f->cap=cap;
    f->config.depth=slots==1u?2u:4u;
    f->config.physical_mics=MICS[scene];
    f->config.input_hz=rate;
    f->config.render_enabled=render;
    f->config.capture_source_id=301u+MICS[scene];
    f->config.render_source_id=render?401u+MICS[scene]:0u;
    f->config.source_generation=UINT64_C(1234509876);
    strcpy(f->dir,"/tmp/fe09-b0-source-XXXXXX");
    must(mkdtemp(f->dir)!=NULL,"HOSTED_PRIVATE_DIR_CREATE");
    f->fd=open(f->dir,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    must(f->fd>=0,"SOURCE_OWNED_DIR_FD");
    must(fe_t3s2a_bind(&f->storage_owner,f->fd,&f->config,
         MAPS[scene],cap)==0,"REAL_S2A_BIND");
    must(fe_t3s2b0_bind(&f->index,&f->storage_owner,cap)==0 &&
         fe_t3s2b0_can_accept(&f->index)==1,
         "SOURCE_EXACT_B0_INDEX_BIND_EMPTY");
    f->slots=(fe_t3s1_slot *)calloc((size_t)slots,sizeof(*f->slots));
    must(f->slots!=NULL,"EXACT_K1_K2_S1_PHYSICAL_STORAGE");
    f->ring.pinned_cfg=f->config;
    f->ring.pinned_sink=fe_t3s2a_outboard_sink;
    f->ring.pinned_sink_context=&f->storage_owner;
    f->ring.slot=f->slots;
    f->ring.slot_count=slots;
    f->ring.slot_allocation_bytes=(size_t)slots*sizeof(*f->slots);
    memcpy(f->ring.physical_to_slot,MAPS[scene],
           sizeof(f->ring.physical_to_slot));
    atomic_init(&f->ring.head,0u);
    atomic_init(&f->ring.tail,0u);
}
static void teardown(fixture *f) {
    for(uint64_t seq=1u;seq<=(uint64_t)f->cap;++seq) {
        char filename[FE_T3S2A_NAME_CAP],tmp[FE_T3S2A_NAME_CAP];
        must(fe_t3s2a_record_name(seq,filename)==0,"EXACT_FINAL_NAME");
        (void)unlinkat(f->fd,filename,0);
        must(snprintf(tmp,sizeof(tmp),"fbs1-%016" PRIx64 ".part",seq)>0,
             "EXACT_ORIGINAL_TEMP_NAME");
        (void)unlinkat(f->fd,tmp,0);
    }
    must(close(f->fd)==0&&rmdir(f->dir)==0,
         "NO_TEST_DIR_RESIDUE");
    free(f->slots);
    f->slots=NULL;
}
/* Use only canonical original first-party writer/decode, never synthesize
 * APX3 byte layout or duplicate CRC. Build its separate original FBS1 row.
 */
static void prepare(fixture *f,uint64_t global,int present,
                    const uint8_t prior[32]) {
    fe_t3s1_slot *slot;
    fe_s2_config sc;
    fe_s2_frame frame;
    fe_s2_writer writer;
    fe_s2_stream decoded;
    size_t n,stride,completed,ncap,nref;
    uint32_t event=FE_B1S0_RENDER_DISABLED,physical=f->config.physical_mics;
    uint32_t rate=f->config.input_hz;
    uint8_t *row;
    must(global>=UINT64_C(1)&&global<=(uint64_t)f->cap,
         "ORIGINAL_GLOBAL_SEQ_BOUND");
    slot=&f->slots[(global-1u)%(uint64_t)f->k];
    ncap=(size_t)rate*physical/100u;
    nref=(size_t)rate/100u;
    for(size_t i=0u;i<ncap;++i)
        f->capture[i]=(int16_t)((int)((i*13u+(unsigned)global*43u)%48000u)-24000);
    for(size_t i=0u;i<nref;++i)
        f->render[i]=(int16_t)((int)((i*17u+(unsigned)global*47u)%46000u)-23000);
    if(f->config.render_enabled)
        event=present?FE_B1S0_RENDER_PRESENT:FE_B1S0_RENDER_ABSENT;
    memset(&sc,0,sizeof(sc));
    sc.rate_hz=rate;sc.physical_mics=physical;
    sc.render_channels=(uint32_t)(event==FE_B1S0_RENDER_PRESENT);
    sc.capture_source_id=f->config.capture_source_id;
    sc.render_source_id=sc.render_channels?f->config.render_source_id:0u;
    sc.capture_epoch=1u;
    sc.render_epoch=sc.render_channels?1u:0u;
    memcpy(sc.physical_to_capture_slot,f->ring.physical_to_slot,
           sizeof(sc.physical_to_capture_slot));
    must(fe_s2_layout(&sc,1u,&n,&stride)==FE_S2_OK&&
         n>0u&&n<=FE_T3S1_CHUNK_BYTES&&stride>0u,
         "ORIGINAL_S2_ONE_FRAME_LAYOUT");
    must(fe_s2_writer_begin(&writer,slot->apx3,
         sizeof(slot->apx3),&sc,1u)==FE_S2_OK,
         "ORIGINAL_S2_WRITER_BEGIN");
    memset(&frame,0,sizeof(frame));
    frame.sequence=UINT64_C(1);frame.capture_epoch=1u;
    frame.render_epoch=sc.render_epoch;
    frame.capture=f->capture;frame.capture_count=ncap;
    frame.render=sc.render_channels?f->render:NULL;
    frame.render_count=sc.render_channels?nref:0u;
    must(fe_s2_writer_append(&writer,&frame)==FE_S2_OK &&
         fe_s2_writer_finish(&writer,&completed)==FE_S2_OK &&
         completed==n &&
         fe_s2_decode(slot->apx3,n,&decoded)==FE_S2_OK,
         "ORIGINAL_APX3_WRITER_CRC_DECODE_REPLAY");
    slot->apx3_bytes=(uint32_t)n;
    row=slot->canonical_row;
    memset(row,0,FE_T3S1_ROW_BYTES);
    p32(row,FE_B1S1_MANIFEST_MAGIC);
    p32(row+4u,FE_B1S1_MANIFEST_VERSION);
    p32(row+8u,event);
    p32(row+12u,rate);
    p32(row+16u,physical);
    p64(row+20u,f->config.source_generation);
    p32(row+28u,f->config.capture_source_id);
    p32(row+32u,f->config.render_source_id);
    p32(row+36u,1u);
    p32(row+40u,f->config.render_enabled?1u:0u);
    p32(row+44u,event==FE_B1S0_RENDER_ABSENT?
        FE_B1S0_ABSENT_SOURCE_REPORTED:0u);
    p64(row+48u,global);
    p64(row+56u,UINT64_C(1));
    p32(row+64u,1u);
    p32(row+68u,(uint32_t)n);
    p64(row+72u,fnv_pcm(f->capture,ncap));
    p64(row+80u,sc.render_channels?fnv_pcm(f->render,nref):UINT64_C(0));
    for(unsigned j=0u;j<4u;++j)
        p32(row+88u+4u*j,f->ring.physical_to_slot[j]);
    must(fe_b1s1_sha256(slot->apx3,n,row+104u)==0,
         "ACTUAL_FIRST_PARTY_CHUNK_HASH");
    memcpy(row+136u,prior,32u);
    must(fe_b1s1_sha256(row,FE_B1S1_ROW_DIGEST_OFFSET,
         row+FE_B1S1_ROW_DIGEST_OFFSET)==0,
         "ACTUAL_FIRST_PARTY_CANONICAL_FBS1_DIGEST");
}
/* A failed index observation must not mutate the previously committed
 * source manifest, including its root and all 16 possible original rows.
 */
static void failed_observation(fixture *f,
    const fe_t3s1_slot *slot,const fe_t3s1_drain_receipt *receipt,
    const char *why) {
    fe_t3s2b0_index original=f->index;
    reject(fe_t3s2b0_observe_acked(&f->index,slot,receipt)!=0&&
           memcmp(&original,&f->index,sizeof(original))==0,why);
}
static void commit(fixture *f,uint64_t seq,int present,int mutate) {
    uint8_t prior[32]={0};
    fe_t3s1_slot *slot;
    fe_t3s1_drain_receipt receipt,bad;
    must(fe_t3s2b0_can_accept(&f->index)==1,
         "INDEPENDENT_PRE_ACK_INDEX_CAPACITY_RESERVATION");
    if(seq>UINT64_C(1)) {
        must(fe_b1s1_sha256(f->index.rows[f->index.count-1u],
             FE_T3S1_ROW_BYTES,prior)==0,"GLOBAL_PRIOR_FBS1_FULL_SHA");
    }
    prepare(f,seq,present,prior);
    slot=&f->slots[(seq-1u)%(uint64_t)f->k];
    atomic_store_explicit(&f->ring.head,(uint32_t)seq,memory_order_release);
    memset(&receipt,0,sizeof(receipt));
    must(fe_t3s1_drain_one(&f->ring,fe_t3s2a_outboard_sink,
         &f->storage_owner,&receipt)==FE_T3S1_OK &&
         receipt.source_sequence==seq &&
         f->storage_owner.committed==seq,
         "ORIGINAL_S1_TO_S2A_REAL_SOURCE_ACK");
    if(mutate) {
        bad=receipt;++bad.source_sequence;
        failed_observation(f,slot,&bad,"INDEX_WRONG_GLOBAL_CAPTURE_ACK");
        bad=receipt;bad.hardware_qualified=1u;
        failed_observation(f,slot,&bad,"FALSE_HIL_IN_ACK_REJECTED");
        bad=receipt;--bad.actually_accounted_bytes;
        failed_observation(f,slot,&bad,"PARTIAL_DISK_TRANSFER_NOT_INDEXED");
        slot->canonical_row[72u]^=0x40u;
        failed_observation(f,slot,&receipt,"CHANGED_CAPTURE_FNV_HASH_NOT_INDEXED");
        slot->canonical_row[72u]^=0x40u;
        slot->apx3[0u]^=0x10u;
        failed_observation(f,slot,&receipt,"ORIGINAL_APX3_CRC_NOT_INDEXED");
        slot->apx3[0u]^=0x10u;
    }
    must(fe_t3s2b0_observe_acked(&f->index,slot,&receipt)==0 &&
         f->index.count==seq &&
         f->index.last_seq==seq &&
         f->index.high_water==seq &&
         f->index.first_seq==UINT64_C(1),
         "FIRST_PARTY_ACK_COMMITTED_TO_CANONICAL_INDEX");
    ++FRAMES;
}
static void roundtrip(fixture *f,int mutate) {
    uint8_t bytes[FE_T3S2B0_MAX_BYTES+1u],again[FE_T3S2B0_MAX_BYTES];
    fe_t3s2b0_index decoded;
    fe_t3s2a_spool recovery;
    size_t size=0u,again_size=0u;
    must(fe_t3s2b0_encode(&f->index,bytes,sizeof(bytes),&size)==0&&
         size==FE_T3S2B0_HEADER_BYTES+
            (size_t)f->index.count*FE_T3S1_ROW_BYTES,
         "LE_MANIFEST_SERIALIZER_EXACT_SIZE");
    must(fe_t3s2a_bind(&recovery,f->fd,&f->config,
         f->ring.physical_to_slot,f->cap)==0&&
         recovery.binding_complete==1u &&
         recovery.committed==f->index.count,
         "FIRST_PARTY_ORIGINAL_S2A_POST_RESTART_COMPLETE");
    must(fe_t3s2b0_decode(&decoded,&recovery,bytes,size)==0&&
         decoded.source==&recovery &&
         decoded.count==f->index.count &&
         decoded.last_seq==f->index.last_seq &&
         memcmp(decoded.root_sha256,f->index.root_sha256,32u)==0,
         "RESTART_SOURCE_ANCHORED_INDEX_ROUNDTRIP");
    must(fe_t3s2b0_encode(&decoded,again,sizeof(again),&again_size)==0 &&
         again_size==size&&memcmp(bytes,again,size)==0,
         "CANONICAL_ROUNDTRIP_BYTE_IDENTITY");
    ++ROUNDTRIPS;++RECOVERIES;
    if(mutate) {
        /* These are actual intra-owner/manifest aliases. The public B0
         * functions must reject before any output or source mutation.
         * The source/fixture extent is a real bounded allocated object.
         */
        {
            fe_t3s2b0_index frozen=f->index;
            fe_t3s2a_spool frozen_owner=recovery;
            size_t out_count=987654u;
            reject(fe_t3s2b0_encode(&f->index,(uint8_t *)f,
                   sizeof(*f),&out_count)!=0 &&
                   out_count==987654u &&
                   memcmp(&f->index,&frozen,sizeof(frozen))==0,
                   "OUTER_INDEX_OUTPUT_MUST_NOT_OVERLAP_SOURCE_OR_INDEX");
            reject(fe_t3s2b0_encode(&f->index,again,sizeof(again),
                   (size_t *)(void *)&f->index.last_seq)!=0 &&
                   memcmp(&f->index,&frozen,sizeof(frozen))==0,
                   "INDEX_SIZE_OUTPUT_MUST_NOT_ALIAS_INDEX");
            reject(fe_t3s2b0_decode((fe_t3s2b0_index *)(void *)&recovery,
                   &recovery,bytes,size)!=0 &&
                   memcmp(&recovery,&frozen_owner,sizeof(recovery))==0,
                   "INDEX_DECODE_MUST_NOT_OVERWRITE_RECOVERED_S2A_OWNER");
        }
        const size_t touched[]={
            0u,4u,8u,12u,16u,20u,24u,28u,32u,36u,40u,44u,
            60u,68u,76u,84u,92u,124u,156u,
            FE_T3S2B0_HEADER_BYTES+0u,
            FE_T3S2B0_HEADER_BYTES+20u,
            FE_T3S2B0_HEADER_BYTES+48u,
            FE_T3S2B0_HEADER_BYTES+72u,
            FE_T3S2B0_HEADER_BYTES+104u,
            FE_T3S2B0_HEADER_BYTES+136u,
            FE_T3S2B0_HEADER_BYTES+168u,
        };
        for(size_t j=0u;j<sizeof(touched)/sizeof(touched[0]);++j) {
            fe_t3s2b0_index unchanged;
            must(touched[j]<size,"NEGATIVE_MUTATION_WITHIN_MANIFEST");
            bytes[touched[j]]^=1u;
            memset(&decoded,0x5A,sizeof(decoded));
            unchanged=decoded;
            reject(fe_t3s2b0_decode(&decoded,&recovery,bytes,size)!=0 &&
                   memcmp(&decoded,&unchanged,sizeof(decoded))==0,
                   "MUTATED_SOURCE_ROLE_OR_ROOT_MUST_FAIL_CLOSED");
            bytes[touched[j]]^=1u;
        }
        memset(&decoded,0x5A,sizeof(decoded));
        reject(fe_t3s2b0_decode(&decoded,&recovery,bytes,size-1u)!=0,
               "TRUNCATED_INDEX_REJECTED");
        bytes[size]=0x7Fu;
        reject(fe_t3s2b0_decode(&decoded,&recovery,bytes,size+1u)!=0,
               "EXTRA_TRAILING_BYTE_REJECTED");
        {
            uint8_t frozen[FE_T3S2B0_MAX_BYTES+1u];
            size_t wrote=123456u;
            memset(frozen,0x6Bu,sizeof(frozen));
            reject(fe_t3s2b0_encode(&f->index,frozen,size-1u,&wrote)!=0&&
                   wrote==123456u && frozen[0]==0x6Bu,
                   "SHORT_ENCODE_PRESERVES_CALLER_OUTPUT");
        }
    }
}
static void matrix_case(uint32_t scene,uint32_t rate,uint32_t render,
                        uint32_t slots) {
    fixture *f=(fixture *)calloc(1,sizeof(*f));
    uint32_t map[4];
    must(f!=NULL,"ALLOC_ACTUAL_CASE");
    setup(f,scene,rate,render,slots,2u);
    memcpy(map,f->ring.physical_to_slot,sizeof(map));
    {
        fe_t3s2a_spool fake=f->storage_owner;
        fe_t3s2b0_index rejected,untouched;
        memset(&rejected,0xA5,sizeof(rejected));
        untouched=rejected;
        fake.mics=33u; /* MUST NOT perform (1u << source_mics) */
        reject(fe_t3s2b0_bind(&rejected,&fake,2u)!=0 &&
               memcmp(&rejected,&untouched,sizeof(rejected))==0,
               "INVALID_SOURCE_MICS_REJECTED_BEFORE_SHIFT_UB");
        fake=f->storage_owner;fake.rate_hz=24000u;
        reject(fe_t3s2b0_bind(&rejected,&fake,2u)!=0,
               "FOREIGN_SOURCE_RATE_REJECTED_BEFORE_INDEX_BIND");
        fake=f->storage_owner;fake.render_enabled=2u;
        reject(fe_t3s2b0_bind(&rejected,&fake,2u)!=0,
               "INVALID_RENDER_OWNER_FLAG_REJECTED_BEFORE_INDEX_BIND");
        fake=f->storage_owner;fake.capture_id=0u;
        reject(fe_t3s2b0_bind(&rejected,&fake,2u)!=0,
               "ZERO_ORIGINAL_CAPTURE_OWNER_REJECTED_BEFORE_BIND");
        fake=f->storage_owner;fake.generation=UINT64_MAX;
        reject(fe_t3s2b0_bind(&rejected,&fake,2u)!=0,
               "SOURCE_UINT64_EPOCH_WRAP_REJECTED_BEFORE_BIND");
        fake=f->storage_owner;fake.render_enabled=1u;
        fake.render_id=fake.capture_id;
        reject(fe_t3s2b0_bind(&rejected,&fake,2u)!=0,
               "CAPTURE_RENDER_ID_COLLISION_REJECTED_BEFORE_BIND");
    }
    reject(fe_t3s2b0_bind(&f->index,&f->storage_owner,0u)!=0,
           "ZERO_MANIFEST_CAPACITY_REJECTED");
    reject(fe_t3s2b0_bind(&f->index,&f->storage_owner,17u)!=0,
           "OVERSIZED_MANIFEST_CAPACITY_REJECTED");
    commit(f,1u,1,1);
    roundtrip(f,1);
    commit(f,2u,0,1);
    roundtrip(f,1);
    reject(fe_t3s2b0_can_accept(&f->index)==0,
           "EXHAUSTED_INDEX_BLOCKS_FUTURE_SOURCE_ACK");
    reject(fe_t3s2b0_bind((fe_t3s2b0_index *)&f->storage_owner,
           &f->storage_owner,2u)!=0,
           "ALIAS_SOURCE_OWNER_MUST_NOT_BE_REBOUND");
    teardown(f);
    free(f);
    ++PROFILES;
}
static void capacity_case(void) {
    fixture *f=(fixture *)calloc(1,sizeof(*f));
    uint8_t record[FE_T3S2B0_MAX_BYTES];
    size_t bytes=0u;
    must(f!=NULL,"CAPACITY_FIXTURE_ALLOCATION");
    setup(f,3u,48000u,1u,1u,16u);
    for(uint64_t seq=1u;seq<=16u;++seq)
        commit(f,seq,(int)(seq&UINT64_C(1)),0);
    roundtrip(f,0);
    must(fe_t3s2b0_encode(&f->index,record,sizeof(record),&bytes)==0 &&
         bytes==FE_T3S2B0_MAX_BYTES &&
         f->index.count==16u &&
         f->index.last_seq==UINT64_C(16) &&
         f->index.high_water==UINT64_C(16),
         "EXACT_REAL_SIXTEEN_ORIGINAL_FBS1_ROWS");
    reject(fe_t3s2b0_can_accept(&f->index)==0,
           "REAL_CAPACITY_EXHAUSTION_NO_SILENT_RING_OVERWRITE");
    teardown(f);free(f);
}
int main(void) {
    for(uint32_t geometry=0u;geometry<4u;++geometry)
        for(uint32_t rate=0u;rate<3u;++rate)
            for(uint32_t render=0u;render<2u;++render)
                for(uint32_t slots=1u;slots<=2u;++slots)
                    matrix_case(geometry,RATES[rate],render,slots);
    capacity_case();
    must(PROFILES==48u && NEGATIVES>=1500u && ROUNDTRIPS==97u &&
         RECOVERIES==97u && FRAMES==112u,
         "ACTUAL_FIRST_PARTY_INDEX_TEST_ACCOUNTING");
    printf("{\"decision\":\"FE09_T3S2B0_ORIGINAL_FBS1_SOURCE_INDEX_RESEARCH_ONLY\","
           "\"source_role\":\"first-party-synthetic\","
           "\"profiles\":%u,\"negative_checks\":%u,"
           "\"roundtrip_checks\":%u,\"original_frames\":%u,"
           "\"physical_one_two_slots\":true,\"maximum_rows\":16,"
           "\"original_apx3_codec_reused\":true,"
           "\"on_disk_manifest_published\":false,"
           "\"rolling_retention_qualified\":false,"
           "\"durable_powerloss_qualified\":false,"
           "\"ssc305_hardware_qualified\":false,"
           "\"whole_device_memory_qualified\":false,"
           "\"public_sdk_installed\":false}\n",
           PROFILES,NEGATIVES,ROUNDTRIPS,FRAMES);
    return 0;
}
