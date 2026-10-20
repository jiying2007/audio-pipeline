/* #794: actual original S2 APX3+FBS1, ORIGINAL S1 consumer and hosted POSIX.
 * This is genuine file I/O, never SSC305 NAND/UBIFS or process-wide HIL.
 * Tests use constructed first-party synthetic PCM; no physical ADC clocks.
 */
#define _POSIX_C_SOURCE 200809L
#include "fe09_b2s3_t3s2a_atomic_spool.h"
#include <fcntl.h>
#include <inttypes.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static unsigned PROFILES,FAULTS,NEGATIVES,RECOVERIES,COMPLETE;
static void must(int pass,const char *what) {
    if(!pass) {
        fprintf(stderr,"FE09_T3S2A_NOT_ADMITTED reason=%s\n",what);
        exit(1);
    }
}
static void negative(int pass,const char *what) {
    must(pass,what);++NEGATIVES;
}
static void p32(uint8_t *p,uint32_t x) {
    for(unsigned i=0u;i<4u;++i)p[i]=(uint8_t)(x>>(i*8u));
}
static void p64(uint8_t *p,uint64_t x) {
    for(unsigned i=0u;i<8u;++i)p[i]=(uint8_t)(x>>(i*8u));
}
static uint64_t fnv_pcm(const int16_t *p,size_t n) {
    uint64_t h=UINT64_C(14695981039346656037);
    for(size_t i=0;i<n;++i) {
        uint16_t v=(uint16_t)p[i];
        h=(h^(uint8_t)v)*UINT64_C(1099511628211);
        h=(h^(uint8_t)(v>>8u))*UINT64_C(1099511628211);
    }
    return h;
}
typedef struct {
    uint32_t rate,mics,render_enabled,slots[4],actual_physical_slots;
    fe_b1s0_config source;
    fe_t3s2a_spool spool;
    fe_t3s1_ring ring;
    fe_t3s1_slot *storage; /* EXACT physical K=1/2 allocation */
    int16_t capture[1920],render[480];
    int fd;
    char name[96];
} test_t;
static const uint32_t MAPS[4][4]={
    {0u,UINT32_MAX,UINT32_MAX,UINT32_MAX},
    {1u,0u,UINT32_MAX,UINT32_MAX},
    {2u,0u,3u,1u},
    {3u,2u,1u,0u}
};
static const uint32_t MICS[]={1u,2u,4u,4u};
static const uint32_t RATES[]={16000u,32000u,48000u};
static void setup(test_t *p,uint32_t scene,uint32_t rate,
                  uint32_t render_enabled,uint32_t k) {
    memset(p,0,sizeof(*p));
    p->fd=-1;
    p->rate=rate;p->mics=MICS[scene];
    p->render_enabled=render_enabled;p->actual_physical_slots=k;
    memcpy(p->slots,MAPS[scene],sizeof(p->slots));
    p->source.depth=k==1u?2u:4u;
    p->source.physical_mics=p->mics;
    p->source.input_hz=rate;
    p->source.render_enabled=render_enabled;
    p->source.capture_source_id=101u+p->mics;
    p->source.render_source_id=render_enabled?201u+p->mics:0u;
    p->source.source_generation=UINT64_C(987654321);
    strcpy(p->name,"/tmp/fe09-t3s2a-XXXXXX");
    must(mkdtemp(p->name)!=NULL,"MKDTEMP");
    p->fd=open(p->name,O_RDONLY|O_CLOEXEC|O_DIRECTORY|O_NOFOLLOW);
    must(p->fd>=0,"DEDICATED_NOFOLLOW_DIR");
    must(fe_t3s2a_bind(&p->spool,p->fd,&p->source,p->slots,2u)==0,
         "EXACT_BOUND_ORIGINAL_EMPTY_SOURCE_DIR");
    p->storage=(fe_t3s1_slot *)calloc((size_t)k,sizeof(fe_t3s1_slot));
    must(p->storage!=NULL,"ACTUAL_ONE_TWO_PHYSICAL_SLOT_ALLOCATION");
    memset(&p->ring,0,sizeof(p->ring));
    p->ring.pinned_cfg=p->source;
    p->ring.pinned_sink=fe_t3s2a_outboard_sink;
    p->ring.pinned_sink_context=&p->spool;
    p->ring.slot_count=k;
    p->ring.slot=p->storage;
    p->ring.slot_allocation_bytes=(size_t)k*sizeof(fe_t3s1_slot);
    memcpy(p->ring.physical_to_slot,p->slots,sizeof(p->slots));
    atomic_init(&p->ring.head,0u);
    atomic_init(&p->ring.tail,0u);
}
static void finish(test_t *p) {
    char name[FE_T3S2A_NAME_CAP];
    for(uint64_t seq=1u;seq<=2u;++seq) {
        char temp[FE_T3S2A_NAME_CAP];
        must(fe_t3s2a_record_name(seq,name)==0,"EXACT_NAME");
        (void)unlinkat(p->fd,name,0);
        must(snprintf(temp,sizeof(temp),"fbs1-%016" PRIx64 ".part",seq)>0,
             "EXACT_TEMP_NAME");
        (void)unlinkat(p->fd,temp,0);
    }
    must(close(p->fd)==0,"CLOSE_ORIGINAL_SPOOL");
    p->fd=-1;
    must(rmdir(p->name)==0,"NO_HIDDEN_DISK_RESIDUE");
    free(p->storage);p->storage=NULL;
}
/* Exact ORIGINAL first-party writer, checksum/parser and FBS1 canonical row.
 * No cloned APX3 serializer or CRC. Local APX3 sequence always one.
 */
static void prepare(test_t *p,uint64_t global_seq,uint32_t present,
                    const uint8_t prev_sha[32]) {
    fe_s2_config cfg;
    fe_s2_frame frame;
    fe_s2_writer writer;
    fe_s2_stream decoded;
    fe_t3s1_slot *slot;
    uint8_t *row;
    size_t n,completed,stride,nc,nr;
    uint32_t event=FE_B1S0_RENDER_DISABLED;
    must(global_seq>0u&&global_seq<=2u,"BOUNDED_GLOBAL_CAPTURE_SEQUENCE");
    slot=&p->storage[(global_seq-1u)%p->actual_physical_slots];
    nc=(size_t)p->rate/100u*p->mics;
    nr=(size_t)p->rate/100u;
    for(size_t i=0;i<nc;++i)p->capture[i]=(int16_t)((int)((i*31u+
            (unsigned)global_seq*67u)%50000u)-25000);
    for(size_t i=0;i<nr;++i)p->render[i]=(int16_t)((int)((i*59u+
            (unsigned)global_seq*41u)%45000u)-22500);
    if(p->render_enabled)event=present?FE_B1S0_RENDER_PRESENT:
                                       FE_B1S0_RENDER_ABSENT;
    memset(&cfg,0,sizeof(cfg));
    cfg.rate_hz=p->rate;cfg.physical_mics=p->mics;
    cfg.render_channels=(uint32_t)(event==FE_B1S0_RENDER_PRESENT);
    cfg.capture_source_id=p->source.capture_source_id;
    cfg.render_source_id=cfg.render_channels?p->source.render_source_id:0u;
    cfg.capture_epoch=1u;
    cfg.render_epoch=cfg.render_channels?1u:0u;
    memcpy(cfg.physical_to_capture_slot,p->slots,sizeof(p->slots));
    must(fe_s2_layout(&cfg,1u,&n,&stride)==FE_S2_OK&&
         n>0u&&n<=FE_T3S1_CHUNK_BYTES&&stride>0u,
         "FIRST_PARTY_ORIGINAL_APX3_SIZE");
    must(fe_s2_writer_begin(&writer,slot->apx3,
            sizeof(slot->apx3),&cfg,1u)==FE_S2_OK,
         "FIRST_PARTY_BEGIN");
    memset(&frame,0,sizeof(frame));
    frame.sequence=UINT64_C(1);frame.capture_epoch=1u;
    frame.render_epoch=cfg.render_epoch;
    frame.capture=p->capture;frame.capture_count=nc;
    frame.render=cfg.render_channels?p->render:NULL;
    frame.render_count=cfg.render_channels?nr:0u;
    must(fe_s2_writer_append(&writer,&frame)==FE_S2_OK&&
         fe_s2_writer_finish(&writer,&completed)==FE_S2_OK&&
         completed==n&&
         fe_s2_decode(slot->apx3,n,&decoded)==FE_S2_OK&&
         decoded.frames==1u,"ACTUAL_ORIGINAL_APX3_CODEC");
    slot->apx3_bytes=(uint32_t)n;
    row=slot->canonical_row;
    memset(row,0,FE_T3S1_ROW_BYTES);
    p32(row,FE_B1S1_MANIFEST_MAGIC);
    p32(row+4u,FE_B1S1_MANIFEST_VERSION);
    p32(row+8u,event);
    p32(row+12u,p->rate);
    p32(row+16u,p->mics);
    p64(row+20u,p->source.source_generation);
    p32(row+28u,p->source.capture_source_id);
    p32(row+32u,p->source.render_source_id);
    p32(row+36u,1u);
    p32(row+40u,p->render_enabled?1u:0u);
    p32(row+44u,event==FE_B1S0_RENDER_ABSENT?
         FE_B1S0_ABSENT_SOURCE_REPORTED:0u);
    p64(row+48u,global_seq);
    p64(row+56u,UINT64_C(1));
    p32(row+64u,1u);
    p32(row+68u,(uint32_t)n);
    p64(row+72u,fnv_pcm(p->capture,nc));
    p64(row+80u,cfg.render_channels?fnv_pcm(p->render,nr):UINT64_C(0));
    for(uint32_t i=0u;i<4u;++i)p32(row+88u+4u*i,p->slots[i]);
    must(fe_b1s1_sha256(slot->apx3,n,row+104u)==0,
         "ORIGINAL_APX3_SHA256");
    memcpy(row+136u,prev_sha,32u);
    must(fe_b1s1_sha256(row,FE_B1S1_ROW_DIGEST_OFFSET,
           row+FE_B1S1_ROW_DIGEST_OFFSET)==0,
         "ORIGINAL_CANONICAL_FBS1_SHA");
}
static void published(test_t *p,uint64_t seq,fe_t3s1_drain_receipt *out) {
    fe_t3s1_status rc=fe_t3s1_drain_one(&p->ring,
        fe_t3s2a_outboard_sink,&p->spool,out);
    must(rc==FE_T3S1_OK && out->source_sequence==seq &&
         out->actually_accounted_bytes==
            out->canonical_row_bytes+out->apx3_bytes &&
         out->hardware_qualified==0u &&
         out->durable_qualified==0u &&
         out->product_qualified==0u,"ONLY_REAL_EXACT_ACCOUNTED_ACK");
    ++COMPLETE;
}
static void matrix_case(uint32_t scene,uint32_t rate,
    uint32_t render,uint32_t k,fe_t3s2a_fault fault) {
    test_t *p=(test_t *)calloc(1,sizeof(*p));
    fe_t3s1_drain_receipt out;
    fe_t3s2a_spool resumed;
    uint8_t first_digest[32],previous[32]={0};
    uint8_t first_row[FE_T3S1_ROW_BYTES],first_apx[FE_T3S1_CHUNK_BYTES];
    size_t first_apx_bytes;
    size_t actual=999u;
    uint32_t tail;
    must(p!=NULL,"TEST_MEMORY");
    setup(p,scene,rate,render,k);
    prepare(p,1u,1u,previous);
    must(fe_t3s2a_set_test_fault(&p->spool,fault)==0,
         "SET_BOUND_FSYSCALL_FAULT");
    atomic_store(&p->ring.head,1u);
    tail=atomic_load(&p->ring.tail);
    memset(&out,0xA5,sizeof(out));
    negative(fe_t3s1_drain_one(&p->ring,fe_t3s2a_outboard_sink,
               &p->spool,&out)==FE_T3S1_SINK_NOT_ADMITTED,
            "EARLY_ACK_OR_SPSC_TAIL_DURING_INJECTED_IO_FAILURE");
    negative(atomic_load(&p->ring.tail)==tail &&
             p->spool.committed==0u,
             "IO_FAILURE_ADVANCED_ORIGINAL_RING_OR_COMMIT");
    ++FAULTS;
    must(fe_t3s2a_set_test_fault(&p->spool,FE_T3S2A_FAULT_NONE)==0,
         "CLEAR_FAULT_WITHOUT_REBIND");
    published(p,1u,&out);
    must(p->spool.committed==1u && atomic_load(&p->ring.tail)==1u,
         "ACTUAL_FIRST_PARTY_S1_TAIL_COMMIT_AFTER_SYNC");
    first_apx_bytes=p->storage[0].apx3_bytes;
    memcpy(first_row,p->storage[0].canonical_row,sizeof(first_row));
    memcpy(first_apx,p->storage[0].apx3,first_apx_bytes);
    must(fe_b1s1_sha256(first_row,
           FE_T3S1_ROW_BYTES,first_digest)==0,"FIRST_ROW_FULL_SHA");
    must(fe_t3s2a_bind(&resumed,p->fd,&p->source,p->slots,2u)==0 &&
         resumed.committed==1u && resumed.restart_recovered==1u &&
         memcmp(resumed.prior_row_sha256,first_digest,32u)==0,
         "INDEPENDENT_POST_RESTART_ORIGINAL_FILE_RECOVERY");
    ++RECOVERIES;
    actual=0u;
    must(fe_t3s2a_outboard_sink(p->storage[0].apx3,
         p->storage[0].apx3_bytes,p->storage[0].canonical_row,
         FE_T3S1_ROW_BYTES,&resumed,&actual)==0 &&
         actual==(size_t)p->storage[0].apx3_bytes+FE_T3S1_ROW_BYTES,
         "RESTART_EXACT_LAST_IDENTITY_IDEMPOTENCE");
    ++RECOVERIES;
    /* Actual second global Capture seq; each original APX3 local seq =1. */
    prepare(p,2u,0u,first_digest);
    atomic_store(&p->ring.head,2u);
    published(p,2u,&out);
    must(p->spool.committed==2u &&
         atomic_load(&p->ring.head)==atomic_load(&p->ring.tail),
         "COMPLETE_CONTIGUOUS_ORIGINAL_SOURCE_HANDOFF");
    negative(fe_t3s2a_outboard_sink(first_apx,
        first_apx_bytes,first_row,
        FE_T3S1_ROW_BYTES,&p->spool,&actual)!=0,
        "OLD_GLOBAL_SEQUENCE_REPLAY_NOT_CLAIMED");
    finish(p);
    free(p);
    ++PROFILES;
}
static void adverse_cases(void) {
    test_t *p=(test_t *)calloc(1,sizeof(*p));
    fe_t3s2a_spool recovered;
    fe_t3s1_drain_receipt out;
    uint8_t zero[32]={0};
    char name[FE_T3S2A_NAME_CAP];
    size_t actual=123u;
    must(p!=NULL,"NEGATIVE_TEST_MEMORY");
    setup(p,3u,48000u,1u,2u);
    prepare(p,1u,1u,zero);
    atomic_store(&p->ring.head,1u);
    negative(fe_t3s1_drain_one(&p->ring,NULL,&p->spool,&out)==
         FE_T3S1_REJECT,"FOREIGN_CALLBACK_REJECTED_BEFORE_IO");
    negative(fe_t3s1_drain_one(&p->ring,fe_t3s2a_outboard_sink,
         NULL,&out)==FE_T3S1_REJECT,"FOREIGN_CONTEXT_REJECTED");
    p->storage[0].apx3[0]^=0x5u;
    negative(fe_t3s1_drain_one(&p->ring,fe_t3s2a_outboard_sink,
         &p->spool,&out)==FE_T3S1_TAMPER,
         "ORIGINAL_S2_CRC_TAMPER_REJECTED");
    p->storage[0].apx3[0]^=0x5u;
    p->storage[0].canonical_row[104u]^=0x40u;
    negative(fe_t3s1_drain_one(&p->ring,fe_t3s2a_outboard_sink,
         &p->spool,&out)==FE_T3S1_TAMPER,
         "VALID_APX3_INVALID_FBS1_APX_HASH_REJECTED");
    p->storage[0].canonical_row[104u]^=0x40u;
    /* A forged self-consistent FBS1 SHA is not enough: persisted original
     * APX3 replay PCM must still match the original Capture FNV witness. */
    {
        uint8_t saved_witness[8],saved_sha[32];
        uint8_t *row=p->storage[0].canonical_row;
        memcpy(saved_witness,row+72u,sizeof(saved_witness));
        memcpy(saved_sha,row+FE_B1S1_ROW_DIGEST_OFFSET,sizeof(saved_sha));
        p64(row+72u,UINT64_C(0));
        must(fe_b1s1_sha256(row,FE_B1S1_ROW_DIGEST_OFFSET,
                row+FE_B1S1_ROW_DIGEST_OFFSET)==0,
             "FORGED_BUT_WELL_HASHED_ROW_FOR_REPLAY_NEGATIVE");
        actual=777u;
        negative(fe_t3s2a_outboard_sink(p->storage[0].apx3,
            p->storage[0].apx3_bytes,row,FE_T3S1_ROW_BYTES,
            &p->spool,&actual)!=0 && actual==0u,
            "FIRST_PARTY_PCM_REPLAY_REJECTS_FORGED_FNV_WITNESS");
        memcpy(row+72u,saved_witness,sizeof(saved_witness));
        memcpy(row+FE_B1S1_ROW_DIGEST_OFFSET,saved_sha,sizeof(saved_sha));
    }
    published(p,1u,&out);
    must(fe_t3s2a_record_name(1u,name)==0,"EXACT_NAME");
    {
        int fd=openat(p->fd,name,O_WRONLY|O_CLOEXEC|O_NOFOLLOW);
        must(fd>=0&&pwrite(fd,"X",1,0)==1&&close(fd)==0,
             "INDEPENDENT_HOSTED_DISK_TAMPER");
    }
    negative(fe_t3s2a_bind(&recovered,p->fd,&p->source,p->slots,2u)!=0,
         "CORRUPT_IMMUTABLE_PUBLISHED_RECORD_RESTART_REJECT");
    negative(fe_t3s2a_outboard_sink(p->storage[0].apx3,
         p->storage[0].apx3_bytes,p->storage[0].canonical_row,
         FE_T3S1_ROW_BYTES,&p->spool,&actual)!=0&&actual==0u,
         "CORRUPT_ON_DISK_BYTE_EXACT_IDENTITY_REJECT");
    finish(p);
    setup(p,0u,16000u,0u,1u);
    must(fe_t3s2a_record_name(1u,name)==0,"SYMLINK_NAME");
    must(symlinkat("/dev/null",p->fd,name)==0,"CREATE_HOSTED_SYMLINK");
    negative(fe_t3s2a_bind(&recovered,p->fd,&p->source,p->slots,2u)!=0,
         "SYMLINK_OR_FALSE_RECOVERY_REJECT");
    finish(p);
    /* A prior bind scans an empty directory. A later bind must rescan
     * from offset ZERO, not inherit the first dirfd stream at EOF. */
    setup(p,0u,16000u,0u,1u);
    prepare(p,1u,1u,zero);
    {
        int alien=openat(p->fd,"foreign-source.dat",
            O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
        must(alien>=0 && close(alien)==0,"INJECT_FOREIGN_SOURCE_FILE");
    }
    negative(fe_t3s2a_bind(&recovered,p->fd,&p->source,p->slots,2u)!=0,
         "REPEATED_DIRECTORY_SCAN_MUST_REJECT_ALIEN_FILE");
    actual=99u;
    negative(fe_t3s2a_outboard_sink(p->storage[0].apx3,
         p->storage[0].apx3_bytes,p->storage[0].canonical_row,
         FE_T3S1_ROW_BYTES,&recovered,&actual)!=0 && actual==0u,
         "REJECTED_PARTIAL_BIND_MUST_NOT_ACK_OR_PUBLISH");
    must(unlinkat(p->fd,"foreign-source.dat",0)==0,
         "REMOVE_ONLY_INJECTED_ALIEN_FILE");
    must(fe_t3s2a_bind(&recovered,p->fd,&p->source,p->slots,2u)==0,
         "INDEPENDENT_FRESH_RESCAN_AFTER_ALIEN_REMOVAL");
    finish(p);
    setup(p,0u,16000u,0u,1u);
    prepare(p,1u,1u,zero);
    must(fe_t3s2a_bind(&recovered,p->fd,&p->source,p->slots,1u)==0,
         "LOW_QUOTA_BIND");
    actual=0u;
    must(fe_t3s2a_outboard_sink(p->storage[0].apx3,
        p->storage[0].apx3_bytes,p->storage[0].canonical_row,
        FE_T3S1_ROW_BYTES,&recovered,&actual)==0,
        "LOW_QUOTA_ONE_REAL_FRAME");
    uint8_t prior[32];
    must(fe_b1s1_sha256(p->storage[0].canonical_row,
         FE_T3S1_ROW_BYTES,prior)==0,"QUOTA_ROW_SHA");
    prepare(p,2u,0u,prior);
    negative(fe_t3s2a_outboard_sink(p->storage[0].apx3,
         p->storage[0].apx3_bytes,p->storage[0].canonical_row,
         FE_T3S1_ROW_BYTES,&recovered,&actual)!=0,
         "FULL_OUTBOARD_QUOTA_FAILS_BEFORE_SOURCE_ACK");
    finish(p);free(p);
}
/* A separate post-failure bind models losing the in-memory consumer after
 * the immutable final pathname was linked but BEFORE tail ACK. The new
 * owner must reconcile the exact same-inode temp, recover source ancestry,
 * idempotently ACK only identical originals and continue the next frame.
 * This is a hosted syscall-fault replay, NEVER a real NAND powercut claim.
 */
static void crash_recovery_cases(void) {
    test_t *p=(test_t *)calloc(1,sizeof(*p));
    fe_t3s2a_spool resumed,post_next,rejected;
    uint8_t zero[32]={0}, prior[32];
    char pub[FE_T3S2A_NAME_CAP],tmp[FE_T3S2A_NAME_CAP];
    struct stat first,second;
    size_t ack=4321u;
    must(p!=NULL,"CRASH_RESTART_FIXTURE_ALLOC");
    setup(p,3u,48000u,1u,1u);
    prepare(p,1u,1u,zero);
    must(fe_t3s2a_set_test_fault(&p->spool,FE_T3S2A_FAULT_PUBLISH)==0,
         "POST_LINK_PRE_ACK_FAULT_SETUP");
    negative(fe_t3s2a_outboard_sink(p->storage[0].apx3,
       p->storage[0].apx3_bytes,p->storage[0].canonical_row,
       FE_T3S1_ROW_BYTES,&p->spool,&ack)!=0 &&
       ack==0u && p->spool.committed==0u,
       "CRASH_AFTER_LINK_MUST_WITHHOLD_SOURCE_ACK");
    must(fe_t3s2a_record_name(1u,pub)==0 &&
         snprintf(tmp,sizeof(tmp),"fbs1-%016" PRIx64 ".part",UINT64_C(1))>0 &&
         fstatat(p->fd,pub,&first,AT_SYMLINK_NOFOLLOW)==0 &&
         fstatat(p->fd,tmp,&second,AT_SYMLINK_NOFOLLOW)==0 &&
         S_ISREG(first.st_mode) && S_ISREG(second.st_mode) &&
         first.st_dev==second.st_dev && first.st_ino==second.st_ino &&
         first.st_nlink==2,
         "TWO_ORIGINAL_HARDLINKS_REMAIN_AT_INTERRUPTED_PUBLISH");
    must(fe_t3s2a_bind(&resumed,p->fd,&p->source,p->slots,2u)==0 &&
         resumed.binding_complete==1u && resumed.committed==1u &&
         resumed.restart_recovered==1u,
         "NEW_PROCESS_SOURCE_EXACT_CRASH_RECONCILIATION");
    negative(fstatat(p->fd,tmp,&second,AT_SYMLINK_NOFOLLOW)!=0,
         "POST_CRASH_REBIND_REMOVED_ONLY_SAME_INODE_TEMP_LINK");
    ack=0u;
    must(fe_t3s2a_outboard_sink(p->storage[0].apx3,
         p->storage[0].apx3_bytes,p->storage[0].canonical_row,
         FE_T3S1_ROW_BYTES,&resumed,&ack)==0 &&
         ack==(size_t)p->storage[0].apx3_bytes+FE_T3S1_ROW_BYTES,
         "POST_CRASH_ORIGINAL_APX3_EXACT_IDEMPOTENT_ACK");
    must(fe_b1s1_sha256(p->storage[0].canonical_row,
         FE_T3S1_ROW_BYTES,prior)==0,"POST_CRASH_PRIOR_FULL_ROW_SHA");
    prepare(p,2u,0u,prior);
    ack=0u;
    must(fe_t3s2a_outboard_sink(p->storage[0].apx3,
         p->storage[0].apx3_bytes,p->storage[0].canonical_row,
         FE_T3S1_ROW_BYTES,&resumed,&ack)==0 &&
         resumed.committed==2u &&
         ack==(size_t)p->storage[0].apx3_bytes+FE_T3S1_ROW_BYTES,
         "POST_CRASH_CONTINUE_SECOND_REAL_FIRST_PARTY_APX3_FRAME");
    must(fe_t3s2a_bind(&post_next,p->fd,&p->source,p->slots,2u)==0 &&
         post_next.committed==2u && post_next.binding_complete==1u,
         "SECOND_PROCESS_RESTART_REPLAY_TWO_GLOBAL_CAPTURES");
    {
        fe_b1s0_config wrong=p->source;
        ++wrong.source_generation;
        negative(fe_t3s2a_bind(&rejected,p->fd,&wrong,p->slots,2u)!=0,
                 "FOREIGN_SOURCE_GENERATION_REPLAY_REJECTED");
        ack=999u;
        negative(fe_t3s2a_outboard_sink(p->storage[0].apx3,
                 p->storage[0].apx3_bytes,p->storage[0].canonical_row,
                 FE_T3S1_ROW_BYTES,&rejected,&ack)!=0 && ack==0u,
                 "REJECTED_GENERATION_BIND_NEVER_ACKS");
    }
    finish(p);
    setup(p,0u,16000u,0u,1u);
    prepare(p,1u,1u,zero);
    must(snprintf(tmp,sizeof(tmp),"fbs1-%016" PRIx64 ".part",UINT64_C(1))>0,
         "TORN_UNPUBLISHED_FILE_NAME");
    {
        int fd=openat(p->fd,tmp,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,
                      0600);
        must(fd>=0 && write(fd,"TORN",4u)==4 && close(fd)==0,
             "SYNTHETIC_PROCESS_DIED_BEFORE_ATOMIC_PUBLICATION");
    }
    negative(fe_t3s2a_bind(&resumed,p->fd,&p->source,p->slots,2u)!=0,
         "UNPUBLISHED_PARTIAL_TEMP_QUARANTINED_ON_RESTART");
    ack=999u;
    negative(fe_t3s2a_outboard_sink(p->storage[0].apx3,
       p->storage[0].apx3_bytes,p->storage[0].canonical_row,
       FE_T3S1_ROW_BYTES,&resumed,&ack)!=0 && ack==0u,
       "PARTIAL_TEMP_REJECTED_BIND_NOT_ALLOWED_TO_ACK");
    must(unlinkat(p->fd,tmp,0)==0,"ONLY_TEST_OWNED_TORN_TEMP_CLEANUP");
    finish(p);
    free(p);
}
int main(void) {
    negative(fe_t3s2a_record_name(0u,(char[FE_T3S2A_NAME_CAP]){0})!=0,
         "ZERO_GLOBAL_SOURCE_FILE_ID");
    negative(fe_t3s2a_record_name(17u,(char[FE_T3S2A_NAME_CAP]){0})!=0,
         "UNBOUNDED_FILE_CAPACITY");
    for(uint32_t sc=0u;sc<4u;++sc)
      for(uint32_t rate=0u;rate<3u;++rate)
        for(uint32_t render=0u;render<2u;++render)
          for(uint32_t k=1u;k<=2u;++k)
            for(int f=FE_T3S2A_FAULT_CREATE;f<=FE_T3S2A_FAULT_READBACK;++f)
                matrix_case(sc,RATES[rate],render,k,(fe_t3s2a_fault)f);
    adverse_cases();
    crash_recovery_cases();
    must(PROFILES==336u&&FAULTS==336u&&NEGATIVES>=680u &&
         RECOVERIES==672u&&COMPLETE>=672u,
         "FAILURE_BOUNDARY_NEGATIVE_EXECUTION_ACCOUNTING");
    printf("{\"decision\":\"FE09_T3S2A_ATOMIC_ORIGINAL_SPOOL_RESEARCH_ONLY\","
           "\"source_role\":\"first-party-synthetic\","
           "\"profiles\":%u,\"fault_injections\":%u,"
           "\"negative_checks\":%u,\"restart_idempotence\":%u,"
           "\"completed_original_frames\":%u,"
           "\"max_files\":16,\"hardware_qualified\":false,"
           "\"durable_powerloss_qualified\":false,"
           "\"rolling_recorder_qualified\":false,"
           "\"complete_ssc305_device_memory_qualified\":false,"
           "\"public_sdk_installed\":false}\n",
           PROFILES,FAULTS,NEGATIVES,RECOVERIES,COMPLETE);
    return 0;
}
