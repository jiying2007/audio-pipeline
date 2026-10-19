/* #801: original-source global Capture seq16 -> seq17 boundary, NEGATIVE
 * feasibility only. No rolling, pruning, storage reuse, source clock/HIL
 * or product authority. ORIGINAL first-party S2 and S1/S2A/B0/B1a are reused.
 */
#define _POSIX_C_SOURCE 200809L
#include "fe09_b2s3_t3s2b1a_immutable_root.h"
#define main original_b0_test_entry
#include "fe09_b2s3_t3s2b0_manifest_test.c"
#undef main
#include <dirent.h>
#include <errno.h>

static uint32_t F0_PROFILES,F0_NEGATIVES,F0_BOUNDARY_NACKS;
static uint64_t F0_ORIGINAL_FRAMES,F0_ACKED,F0_SOURCE_BYTES,F0_ROOT_BYTES;
static uint64_t F0_SOURCE_FILES,F0_ROOT_FILES;
static void f0_check(int ok,const char *why) {
    if(!ok){fprintf(stderr,"FE09_B1BF0_NOT_ADMITTED %s\n",why);exit(1);}
}
static void f0_reject(int ok,const char *why) {
    f0_check(ok,why);++F0_NEGATIVES;
}
static uint64_t f0_le64(const uint8_t *p) {
    uint64_t x=UINT64_C(0);
    for(unsigned i=0u;i<8u;++i)x|=(uint64_t)p[i]<<(8u*i);
    return x;
}
typedef struct {
    fixture *source;
    fe_t3s2b1a_root root;
    int rootfd;
    char rootpath[80];
} f0_stage;
static void f0_start(f0_stage *s,uint32_t scene,uint32_t rate,
                     uint32_t render,uint32_t slots) {
    memset(s,0,sizeof(*s));
    s->rootfd=-1;
    s->source=(fixture *)calloc(1,sizeof(*s->source));
    f0_check(s->source!=NULL,"allocate-actual-first-party-source");
    setup(s->source,scene,rate,render,slots,16u);
    strcpy(s->rootpath,"/tmp/fe09-b1bf0-XXXXXX");
    f0_check(mkdtemp(s->rootpath)!=NULL,"make-owned-host-root");
    s->rootfd=open(s->rootpath,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    f0_check(s->rootfd>=0,"open-original-index-root-directory");
    f0_check(fe_t3s2b1a_bind(&s->root,s->rootfd,
        &s->source->storage_owner)==0 &&
        s->root.binding_complete==1u &&
        s->root.roots_committed==0u,"bind-original-b1a-root");
}
static void f0_end(f0_stage *s) {
    int fd=openat(s->rootfd,".",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    f0_check(fd>=0,"independent-root-enumeration");
    DIR *d=fdopendir(fd);
    f0_check(d!=NULL,"root-dir-open");
    struct dirent *e;
    while((e=readdir(d))!=NULL) {
        if(!strcmp(e->d_name,".")||!strcmp(e->d_name,".."))continue;
        f0_check(unlinkat(s->rootfd,e->d_name,0)==0,
                 "remove-only-test-owned-root-fixture");
    }
    f0_check(closedir(d)==0,"root-dir-closed");
    f0_check(close(s->rootfd)==0 && rmdir(s->rootpath)==0,
             "root-fixture-removed");
    teardown(s->source);
    free(s->source);s->source=NULL;
}
static void f0_inventory(const f0_stage *s) {
    const fixture *f=s->source;
    uint32_t count=0u;
    uint64_t root_bytes=0u,source_bytes=0u;
    for(uint64_t n=UINT64_C(1);n<=UINT64_C(16);++n) {
        char name[FE_T3S2A_NAME_CAP];
        struct stat st;
        f0_check(fe_t3s2a_record_name(n,name)==0 &&
                 fstatat(f->fd,name,&st,AT_SYMLINK_NOFOLLOW)==0 &&
                 S_ISREG(st.st_mode) && st.st_nlink==1 &&
                 st.st_size>(off_t)FE_T3S1_ROW_BYTES &&
                 st.st_size<=(off_t)FE_T3S2A_FILE_BYTES,
                 "sixteen-original-source-files-unaltered");
        source_bytes+=(uint64_t)st.st_size;
    }
    int fd=openat(s->rootfd,".",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    f0_check(fd>=0,"independent-root-count-fd");
    DIR *d=fdopendir(fd);
    f0_check(d!=NULL,"independent-root-count-open");
    struct dirent *e;
    while((e=readdir(d))!=NULL) {
        if(!strcmp(e->d_name,".")||!strcmp(e->d_name,".."))continue;
        struct stat st;
        f0_check(strncmp(e->d_name,"frm1-",5u)==0 &&
                 fstatat(s->rootfd,e->d_name,&st,AT_SYMLINK_NOFOLLOW)==0 &&
                 S_ISREG(st.st_mode) && st.st_nlink==1 &&
                 st.st_size>=(off_t)FE_T3S2B0_HEADER_BYTES &&
                 st.st_size<=(off_t)FE_T3S2B0_MAX_BYTES,
                 "all-original-immutable-roots-on-disk");
        root_bytes+=(uint64_t)st.st_size;++count;
    }
    f0_check(closedir(d)==0,"count-dir-closed");
    f0_check(count==16u && root_bytes==
        UINT64_C(16)*FE_T3S2B0_HEADER_BYTES+
        UINT64_C(136)*FE_T3S1_ROW_BYTES,
        "sixteen-original-root-byte-count");
    F0_SOURCE_BYTES+=source_bytes;F0_ROOT_BYTES+=root_bytes;
    F0_SOURCE_FILES+=UINT64_C(16);F0_ROOT_FILES+=count;
}
static void f0_negative_mutations(fixture *f,fe_t3s1_slot *slot,
                                   const uint8_t canonical[FE_T3S1_ROW_BYTES]) {
    for(uint32_t kind=0u;kind<6u;++kind) {
        uint8_t saved_apx3=slot->apx3[0u];
        fe_t3s1_drain_receipt receipt;
        memcpy(slot->canonical_row,canonical,FE_T3S1_ROW_BYTES);
        switch(kind) {
            case 0u: slot->canonical_row[136u]^=1u;break;
            case 1u: p64(slot->canonical_row+48u,UINT64_C(1));break;
            case 2u: p32(slot->canonical_row+28u,
                            f->config.capture_source_id+1u);break;
            case 3u: p64(slot->canonical_row+20u,
                            f->config.source_generation+UINT64_C(1));break;
            case 4u: slot->canonical_row[8u]^=1u;break;
            case 5u: slot->apx3[0u]^=1u;break;
            default:f0_check(0,"bounded-negative-case");break;
        }
        if(kind!=5u) {
            f0_check(fe_b1s1_sha256(slot->canonical_row,
                FE_B1S1_ROW_DIGEST_OFFSET,
                slot->canonical_row+FE_B1S1_ROW_DIGEST_OFFSET)==0,
                "recomputed-attack-row-hash");
        }
        memset(&receipt,0xA5,sizeof(receipt));
        f0_reject(fe_t3s1_drain_one(&f->ring,fe_t3s2a_outboard_sink,
                  &f->storage_owner,&receipt)==FE_T3S1_TAMPER &&
                  atomic_load_explicit(&f->ring.tail,memory_order_acquire)==16u &&
                  f->storage_owner.committed==UINT64_C(16) &&
                  f->index.count==16u &&
                  f->ring.drained_global_capture==UINT64_C(16),
                  "mutated-global-source-not-acked");
        slot->apx3[0u]=saved_apx3;
    }
    memcpy(slot->canonical_row,canonical,FE_T3S1_ROW_BYTES);
}
static void f0_conflict_and_missing_root(f0_stage *s) {
    const fixture *f=s->source;
    uint8_t otherhash[32];
    char conflicting[FE_T3S2B1A_FILENAME_BYTES],missing[FE_T3S2B1A_FILENAME_BYTES]={0};
    fe_t3s2b1a_root candidate;
    memcpy(otherhash,s->root.last_root_digest,32u);
    otherhash[0u]^=1u;
    f0_check(fe_t3s2b1a_name(f->config.source_generation,
        UINT64_C(16),otherhash,conflicting)==0,
        "independent-conflicting-root-name");
    int fd=openat(s->rootfd,conflicting,
          O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    f0_check(fd>=0 && close(fd)==0,"create-only-negative-conflicting-root");
    memset(&candidate,0,sizeof(candidate));
    f0_reject(fe_t3s2b1a_bind(&candidate,s->rootfd,
        &f->storage_owner)!=0 && candidate.binding_complete==0u,
        "foreign-conflicting-root-fails-closed");
    f0_check(unlinkat(s->rootfd,conflicting,0)==0,
             "remove-only-injected-conflict");
    memset(&candidate,0,sizeof(candidate));
    f0_check(fe_t3s2b1a_bind(&candidate,s->rootfd,
        &f->storage_owner)==0 && candidate.roots_committed==16u,
        "original-root-inventory-survives-conflict");
    int scanfd=openat(s->rootfd,".",
             O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    f0_check(scanfd>=0,"find-existing-root-no-share-offset");
    DIR *dir=fdopendir(scanfd);
    f0_check(dir!=NULL,"find-root-dir");
    struct dirent *e;
    while((e=readdir(dir))!=NULL) {
        if(strlen(e->d_name)>38u &&
           strncmp(e->d_name,"frm1-",5u)==0 &&
           strncmp(e->d_name+22u,"0000000000000008",16u)==0) {
            f0_check(strlen(e->d_name)<sizeof(missing),
                     "bounded-root-eight-name");
            strcpy(missing,e->d_name);break;
        }
    }
    f0_check(closedir(dir)==0 && missing[0]!='\0',"find-exact-root-eight");
    f0_check(unlinkat(s->rootfd,missing,0)==0,
             "test-only-missing-root-fixture");
    memset(&candidate,0,sizeof(candidate));
    f0_reject(fe_t3s2b1a_bind(&candidate,s->rootfd,
        &f->storage_owner)!=0 && candidate.binding_complete==0u,
        "missing-middle-original-root-rejected");
    /* No published source file is ever pruned or unlinked here. */
}
static void f0_case(uint32_t scene,uint32_t hz,uint32_t render,uint32_t k) {
    f0_stage *s=(f0_stage *)calloc(1,sizeof(*s));
    uint8_t prior[32],canonical[FE_T3S1_ROW_BYTES],nullhash[32]={0};
    fe_t3s1_drain_receipt received,before_receipt;
    fe_t3s2a_spool saved_owner;
    fe_t3s2b0_index saved_index,rebuilt;
    fe_t3s2b1a_root restored;
    char seq1[FE_T3S2A_NAME_CAP],forbidden_root[FE_T3S2B1A_FILENAME_BYTES];
    uint32_t tail;
    f0_check(s!=NULL,"allocate-original-source-matrix-case");
    f0_start(s,scene,hz,render,k);
    fixture *f=s->source;
    for(uint64_t n=UINT64_C(1);n<=UINT64_C(16);++n) {
        commit(f,n,(int)(n&UINT64_C(1)),0);
        f0_check(fe_t3s2b1a_publish(&s->root,&f->index)==0 &&
                 s->root.roots_committed==(uint32_t)n,
                 "original-first-party-source-index-commit");
        ++F0_ACKED;++F0_ORIGINAL_FRAMES;
    }
    f0_inventory(s);
    f0_check(fe_b1s1_sha256(f->index.rows[15u],FE_T3S1_ROW_BYTES,prior)==0,
             "full-prior-original-fbs1-row-sha");
    saved_owner=f->storage_owner;saved_index=f->index;
    tail=atomic_load_explicit(&f->ring.tail,memory_order_acquire);
    f0_check(tail==16u && f->ring.drained_global_capture==UINT64_C(16) &&
             s->root.roots_committed==16u &&
             !fe_t3s2b0_can_accept(&f->index),
             "sixteen-source-acks-no-more-storage-capacity");

    /* B0's original prepare fixture bounds itself to <=f->cap. Extend only
     * its TEST-LOCAL frame-construction bound to 17; the actual S2-A bound,
     * generation, source slots, index and root remain immutable at sixteen.
     * This produces a REAL original first-party 10ms APX3 seq17, then calls
     * the unchanged first-party S1 outboard consumer; NOT a BF/HIL sample.
     */
    f->cap=17u;
    prepare(f,UINT64_C(17),(int)(render!=0u),prior);
    f->cap=16u;
    fe_t3s1_slot *slot=&f->slots[16u%k];
    memcpy(canonical,slot->canonical_row,sizeof(canonical));
    ++F0_ORIGINAL_FRAMES;
    f0_check(f0_le64(slot->canonical_row+48u)==UINT64_C(17) &&
             f0_le64(f->index.rows[15u]+48u)==UINT64_C(16) &&
             memcmp(slot->canonical_row+136u,prior,32u)==0 &&
             f0_le64(slot->canonical_row+56u)==UINT64_C(1),
             "distinct-global-seq16-seq17-and-local-apx3-seq1");
    atomic_store_explicit(&f->ring.head,17u,memory_order_release);
    f0_negative_mutations(f,slot,canonical);
    memset(&received,0xA5,sizeof(received));
    before_receipt=received;
    for(unsigned repeat=0u;repeat<2u;++repeat) {
        f0_reject(fe_t3s1_drain_one(&f->ring,fe_t3s2a_outboard_sink,
                  &f->storage_owner,&received)==FE_T3S1_SINK_NOT_ADMITTED &&
                  memcmp(&received,&before_receipt,sizeof(received))==0 &&
                  atomic_load_explicit(&f->ring.tail,memory_order_acquire)==tail &&
                  f->ring.drained_global_capture==UINT64_C(16) &&
                  f->storage_owner.committed==UINT64_C(16),
                  "global-seq17-original-source-ack-fail-closed-full");
    }
    ++F0_BOUNDARY_NACKS;
    f0_check(memcmp(&saved_owner,&f->storage_owner,sizeof(saved_owner))==0 &&
             memcmp(&saved_index,&f->index,sizeof(saved_index))==0,
             "full-boundary-must-not-forge-owner-or-root-progress");
    f0_reject(fe_t3s2a_record_name(UINT64_C(17),seq1)!=0,
              "no-global-17-alias-to-original-file-one");
    f0_reject(fe_t3s2b1a_name(f->config.source_generation,
              UINT64_C(17),nullhash,forbidden_root)!=0,
              "no-manufactured-index-root-seventeen");
    f0_check(fe_t3s2a_record_name(UINT64_C(1),seq1)==0,
             "original-file-one-still-exists");
    int badfd=openat(f->fd,seq1,
              O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    f0_reject(badfd<0 && errno==EEXIST,
              "original-file-one-cannot-be-replaced-with-seq17");
    if(badfd>=0)(void)close(badfd);
    f0_reject(fe_t3s2b1a_publish(&s->root,&f->index)!=0 &&
              s->root.roots_committed==16u,
              "full-original-frm1-root-never-rolls");
    memset(&restored,0,sizeof(restored));
    f0_check(fe_t3s2b1a_bind(&restored,s->rootfd,
        &f->storage_owner)==0 &&
        restored.roots_committed==16u &&
        fe_t3s2b1a_rebuild_index(&rebuilt,&restored)==0 &&
        rebuilt.count==16u &&
        memcmp(rebuilt.root_sha256,f->index.root_sha256,32u)==0,
        "original-sixteen-roots-independent-restart-readback");
    f0_conflict_and_missing_root(s);
    f0_end(s);free(s);++F0_PROFILES;
}
int main(void) {
    for(uint32_t scene=0u;scene<4u;++scene)
      for(unsigned rate=0u;rate<3u;++rate)
        for(uint32_t render=0u;render<2u;++render)
          for(uint32_t k=1u;k<=2u;++k)
            f0_case(scene,RATES[rate],render,k);
    f0_check(F0_PROFILES==48u &&
             F0_ORIGINAL_FRAMES==UINT64_C(816) &&
             F0_ACKED==UINT64_C(768) &&
             F0_BOUNDARY_NACKS==48u &&
             F0_SOURCE_FILES==UINT64_C(768) &&
             F0_ROOT_FILES==UINT64_C(768) &&
             F0_ROOT_BYTES==UINT64_C(1428480) &&
             F0_SOURCE_BYTES>UINT64_C(1000000) &&
             F0_NEGATIVES>=UINT32_C(500),
             "real-original-seventeen-frame-feasibility-census");
    printf("{\"decision\":\"FE09_T3S2B1BF0_SEQ17_FAIL_CLOSED_RESEARCH_ONLY\","
           "\"source_role\":\"first-party-synthetic\","
           "\"profiles\":%u,\"actual_original_apx3_frames\":%" PRIu64 ","
           "\"actually_acked_original_frames\":%" PRIu64 ","
           "\"seq17_refused\":%u,\"negative_checks\":%u,"
           "\"original_source_files_accounted\":%" PRIu64 ","
           "\"original_root_files_accounted\":%" PRIu64 ","
           "\"original_source_disk_bytes\":%" PRIu64 ","
           "\"immutable_root_disk_bytes\":%" PRIu64 ","
           "\"global_16_to_17_source_identity_distinct\":true,"
           "\"source_owner_full_backpressure_proven\":true,"
           "\"real_rolling_retention_qualified\":false,"
           "\"original_source_deleted\":false,"
           "\"physical_powerloss_qualified\":false,"
           "\"ssc305_hardware_qualified\":false,"
           "\"whole_device_memory_qualified\":false,"
           "\"public_sdk_installed\":false}\n",
           F0_PROFILES,F0_ORIGINAL_FRAMES,F0_ACKED,F0_BOUNDARY_NACKS,
           F0_NEGATIVES,F0_SOURCE_FILES,F0_ROOT_FILES,
           F0_SOURCE_BYTES,F0_ROOT_BYTES);
    return 0;
}
