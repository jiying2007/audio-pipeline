/* #799: hosted noninstalled immutable source-index roots.
 * Reuse unchanged first-party S2 APX3, original S1/S2A and B0 test fixture.
 * Host syscall ordering only; not physical power loss or a rolling recorder.
 */
#define _POSIX_C_SOURCE 200809L
#include "fe09_b2s3_t3s2b1a_immutable_root.h"
#define main original_b0_test_entry
#include "fe09_b2s3_t3s2b0_manifest_test.c"
#undef main
#include <dirent.h>
#include <unistd.h>

/* Original frozen B0 fixture's static FRAMES is incremented by real commit().
 * Do NOT shadow or double count it in the B1a caller. */
static uint32_t CASES,FAULTS,RESTARTS,NEGATIVE,RETRY,ROOT_BYTES;
static void check(int ok,const char *label) {
    if(!ok){fprintf(stderr,"FE09_B1A_NOT_ADMITTED %s\n",label);exit(1);}
}
static void deny(int ok,const char *label) {
    check(ok,label);++NEGATIVE;
}
typedef struct {
    fixture *old;
    int fd;
    char path[80];
    fe_t3s2b1a_root root;
} stage;
static void begin(stage *x,uint32_t scene,uint32_t hz,
                  uint32_t render,uint32_t k,uint32_t capacity) {
    memset(x,0,sizeof(*x));
    x->old=(fixture *)calloc(1,sizeof(*x->old));
    check(x->old!=NULL,"allocate-source");
    setup(x->old,scene,hz,render,k,capacity);
    strcpy(x->path,"/tmp/fe09-b1a-XXXXXX");
    check(mkdtemp(x->path)!=NULL,"make-root-directory");
    x->fd=open(x->path,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    check(x->fd>=0,"open-owned-root-directory");
    check(fe_t3s2b1a_bind(&x->root,x->fd,
          &x->old->storage_owner)==0 &&
          x->root.binding_complete==1u &&
          x->root.roots_committed==0u,"trusted-root-bind");
}
static void end(stage *x) {
    int fd=openat(x->fd,".",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    check(fd>=0,"owned-root-enumeration");
    DIR *d=fdopendir(fd);
    check(d!=NULL,"owned-root-dir");
    struct dirent *entry;
    while((entry=readdir(d))!=NULL) {
        if(strcmp(entry->d_name,".")==0 ||
           strcmp(entry->d_name,"..")==0)continue;
        check(unlinkat(x->fd,entry->d_name,0)==0,"owned-root-cleanup");
    }
    check(closedir(d)==0,"close-root-enumeration");
    check(close(x->fd)==0 && rmdir(x->path)==0,"close-root");
    teardown(x->old);
    free(x->old);x->old=NULL;
}
static void restart(stage *x,fe_t3s2b1a_root *dst,uint32_t count) {
    memset(dst,0,sizeof(*dst));
    check(fe_t3s2b1a_bind(dst,x->fd,&x->old->storage_owner)==0 &&
          dst->binding_complete==1u &&
          dst->roots_committed==count,"recovered-immutable-root");
    ++RESTARTS;
}
static void one(uint32_t scene,uint32_t hz,uint32_t render,
                uint32_t k,fe_t3s2b1a_fault fault) {
    stage *x=(stage *)calloc(1,sizeof(*x));
    fe_t3s2b1a_root recovered,again;
    fe_t3s2b0_index index,incorrect;
    check(x!=NULL,"allocate-real-test");
    begin(x,scene,hz,render,k,2u);
    deny(fe_t3s2b1a_rebuild_index(&index,&x->root)!=0,
         "empty-source-not-indexed");
    deny(fe_t3s2b1a_set_test_fault(&x->root,
         (fe_t3s2b1a_fault)99)!=0,"unknown-fault");
    commit(x->old,UINT64_C(1),1,0);
    /* first-party B0 commit() already accounts this real frame */
    check(fe_t3s2b1a_rebuild_index(&index,&x->root)==0 &&
          index.source==&x->old->storage_owner &&
          memcmp(index.root_sha256,x->old->index.root_sha256,32u)==0,
          "original-source-index-rebuild");
    check(fe_t3s2b1a_set_test_fault(&x->root,fault)==0,
          "set-posix-fault");
    deny(fe_t3s2b1a_publish(&x->root,&x->old->index)!=0,
         "injected-failure-not-root-admission");
    deny(x->root.roots_committed==0u &&
         x->old->storage_owner.committed==UINT64_C(1),
         "source-ack-and-root-publication-distinct");
    ++FAULTS;
    check(fe_t3s2b1a_set_test_fault(&x->root,
          FE_T3S2B1A_FAULT_NONE)==0,"clear-test-fault");
    check(fe_t3s2b1a_publish(&x->root,&x->old->index)==0 &&
          x->root.roots_committed==1u,"root-retry-complete");
    if(fault>=FE_T3S2B1A_FAULT_PUBLISH) {
        check(x->root.retry_after_publish==1u,
              "published-file-retry-after-interruption");
        ++RETRY;
    }
    restart(x,&recovered,1u);
    check(fe_t3s2b1a_rebuild_index(&index,&recovered)==0 &&
          index.count==1u,"recover-original-source-bytes");
    deny(fe_t3s2b1a_publish(&recovered,&x->old->index)!=0,
         "no-new-original-sequence");
    commit(x->old,UINT64_C(2),0,0);
    /* first-party B0 commit() already accounts this real frame */
    check(fe_t3s2b1a_rebuild_index(&index,&recovered)==0 &&
          index.count==2u,"source-ack-before-root-recovery");
    incorrect=x->old->index;
    ++incorrect.source_generation;
    deny(fe_t3s2b1a_publish(&recovered,&incorrect)!=0,
         "wrong-original-generation");
    check(fe_t3s2b1a_publish(&recovered,&x->old->index)==0 &&
          recovered.roots_committed==2u,"second-immutable-root");
    restart(x,&again,2u);
    deny(fe_t3s2b1a_publish(&again,&x->old->index)!=0,
         "quota-does-not-reuse-old-root");
    deny(fe_t3s2b1a_bind(&again,x->fd,
         &x->old->storage_owner)!=0,
         "do-not-rebind-live-root");
    check(x->old->storage_owner.committed==UINT64_C(2),
          "original-source-retained");
    /* Two independently published FRM1 images: header+row1, then
     * header+row1+row2. Count actual original serialized root bytes. */
    ROOT_BYTES+=(uint32_t)(2u*FE_T3S2B0_HEADER_BYTES+
                           3u*FE_T3S1_ROW_BYTES);
    end(x);free(x);++CASES;
}
static void sixteen(void) {
    stage *x=(stage *)calloc(1,sizeof(*x));
    fe_t3s2b1a_root recovered;
    check(x!=NULL,"allocate-capacity");
    begin(x,3u,48000u,1u,1u,16u);
    for(uint64_t n=UINT64_C(1);n<=UINT64_C(16);++n) {
        commit(x->old,n,(int)(n&UINT64_C(1)),0);
        /* first-party B0 commit() already accounts this real frame */
        check(fe_t3s2b1a_publish(&x->root,&x->old->index)==0 &&
              x->root.roots_committed==(uint32_t)n,
              "sixteen-original-root-checkpoints");
    }
    restart(x,&recovered,16u);
    /* Sum actual immutable root byte lengths for N=1..16. */
    ROOT_BYTES+=(uint32_t)(16u*FE_T3S2B0_HEADER_BYTES+
                           (16u*17u/2u)*FE_T3S1_ROW_BYTES);
    deny(!fe_t3s2b0_can_accept(&x->old->index),
         "source-quota-enforced");
    deny(fe_t3s2b1a_publish(&recovered,&x->old->index)!=0,
         "no-implicit-seventeenth-root");
    end(x);free(x);
}
/* Root directory and original source are different fixed trusted FDs.
 * These controls exercise real hosted filesystem state and must reject
 * any ambiguous restart without declaring successful index publication.
 */
static void filesystem_integrity_cases(void) {
    stage *x=(stage *)calloc(1,sizeof(*x));
    fe_t3s2b1a_root observed;
    uint8_t encoded[FE_T3S2B0_MAX_BYTES],hash[32]={0};
    char name[FE_T3S2B1A_FILENAME_BYTES],other[FE_T3S2B1A_FILENAME_BYTES];
    size_t length=0u;
    int fd;
    check(x!=NULL,"separate-directory-test");
    begin(x,0u,16000u,0u,1u,2u);
    commit(x->old,UINT64_C(1),0,0);
    check(fe_t3s2b1a_publish(&x->root,&x->old->index)==0,
          "baseline-source-index-root");
    check(fe_t3s2b0_encode(&x->old->index,encoded,sizeof(encoded),&length)==0 &&
          fe_b1s1_sha256(encoded,length,hash)==0 &&
          fe_t3s2b1a_name(x->old->config.source_generation,
            UINT64_C(1),hash,name)==0,
          "exact-canonical-real-root-name");
    ROOT_BYTES+=(uint32_t)length;
    fd=openat(x->fd,"unrecognized-file.bin",
              O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    check(fd>=0&&close(fd)==0,"test-foreign-file-create");
    memset(&observed,0,sizeof(observed));
    deny(fe_t3s2b1a_bind(&observed,x->fd,&x->old->storage_owner)!=0 &&
         observed.binding_complete==0u,"reject-unknown-root-file");
    check(unlinkat(x->fd,"unrecognized-file.bin",0)==0,
          "test-foreign-file-cleanup");
    hash[0]^=0x73u;
    check(fe_t3s2b1a_name(x->old->config.source_generation,
          UINT64_C(1),hash,other)==0,"alternative-same-seq-name");
    fd=openat(x->fd,other,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    check(fd>=0&&write(fd,"not-an-index",12u)==12&&close(fd)==0,
          "test-second-root-record");
    memset(&observed,0,sizeof(observed));
    deny(fe_t3s2b1a_bind(&observed,x->fd,&x->old->storage_owner)!=0 &&
         observed.binding_complete==0u,"reject-conflicting-same-seq-root");
    check(unlinkat(x->fd,other,0)==0,"cleanup-second-root");
    check(fe_t3s2b1a_name(x->old->config.source_generation,
          UINT64_C(2),hash,other)==0,"later-temporary-root-name");
    check(strlen(other)+5u<sizeof(other),"temporary-name-bounded");
    (void)strcat(other,".part");
    fd=openat(x->fd,other,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    check(fd>=0&&write(fd,"short",5u)==5&&close(fd)==0,
          "incomplete-hosted-temporary-root");
    memset(&observed,0,sizeof(observed));
    deny(fe_t3s2b1a_bind(&observed,x->fd,&x->old->storage_owner)!=0 &&
         observed.binding_complete==0u,"reject-orphan-root-file");
    check(unlinkat(x->fd,other,0)==0,"cleanup-orphan-root-file");
    check(linkat(x->fd,name,x->old->fd,"source-root-extra-link",0)==0,
          "test-root-link-boundary");
    memset(&observed,0,sizeof(observed));
    deny(fe_t3s2b1a_bind(&observed,x->fd,&x->old->storage_owner)!=0 &&
         observed.binding_complete==0u,"reject-unpaired-hardlink-root");
    check(unlinkat(x->old->fd,"source-root-extra-link",0)==0,
          "cleanup-only-test-created-link");
    check(fe_t3s2b1a_name(x->old->config.source_generation,
          UINT64_C(2),hash,other)==0,"later-root-canonical-path");
    check(symlinkat("/dev/null",x->fd,other)==0,"test-root-nofollow");
    memset(&observed,0,sizeof(observed));
    deny(fe_t3s2b1a_bind(&observed,x->fd,&x->old->storage_owner)!=0 &&
         observed.binding_complete==0u,"reject-symlink-root");
    check(unlinkat(x->fd,other,0)==0,"cleanup-only-test-symlink");
    fd=openat(x->fd,name,O_RDWR|O_NOFOLLOW|O_CLOEXEC);
    check(fd>=0 && pwrite(fd,"X",1u,0)==1 && close(fd)==0,
          "simulate-corrupted-hosted-index");
    memset(&observed,0,sizeof(observed));
    deny(fe_t3s2b1a_bind(&observed,x->fd,&x->old->storage_owner)!=0 &&
         observed.binding_complete==0u,"reject-corrupted-full-root");
    end(x);
    begin(x,1u,32000u,1u,2u,2u);
    commit(x->old,UINT64_C(1),1,0);
    check(fe_t3s2b1a_publish(&x->root,&x->old->index)==0,
          "new-source-root-before-missing-original-test");
    check(fe_t3s2b0_encode(&x->old->index,
          encoded,sizeof(encoded),&length)==0,
          "second-source-root-size");
    ROOT_BYTES+=(uint32_t)length;
    {
        char original[FE_T3S2A_NAME_CAP];
        check(fe_t3s2a_record_name(UINT64_C(1),original)==0 &&
              unlinkat(x->old->fd,original,0)==0,
              "simulate-lost-original-apx3");
    }
    memset(&observed,0,sizeof(observed));
    deny(fe_t3s2b1a_bind(&observed,x->fd,&x->old->storage_owner)!=0 &&
         observed.binding_complete==0u,
         "reject-index-with-missing-original-apx3");
    end(x);free(x);
}
int main(void) {
    uint8_t hash[32]={0};
    char name[FE_T3S2B1A_FILENAME_BYTES];
    deny(fe_t3s2b1a_name(UINT64_C(0),UINT64_C(1),hash,name)!=0,
         "zero-source-epoch");
    deny(fe_t3s2b1a_name(UINT64_C(1),UINT64_C(0),hash,name)!=0,
         "zero-global-sequence");
    deny(fe_t3s2b1a_name(UINT64_C(1),UINT64_C(17),hash,name)!=0,
         "quota-name");
    for(uint32_t scene=0u;scene<4u;++scene)
      for(unsigned rate=0u;rate<3u;++rate)
        for(uint32_t render=0u;render<2u;++render)
          for(uint32_t k=1u;k<=2u;++k)
            for(int fault=FE_T3S2B1A_FAULT_CREATE;
                fault<=FE_T3S2B1A_FAULT_READBACK;++fault)
                one(scene,RATES[rate],render,k,(fe_t3s2b1a_fault)fault);
    sixteen();
    filesystem_integrity_cases();
    check(CASES==336u&&FAULTS==336u&&RESTARTS==673u &&
          FRAMES==690u&&NEGATIVE>=2000u&&RETRY==192u &&
          ROOT_BYTES>10000u,
          "real-hosted-root-qualification-counts");
    printf("{\"decision\":\"FE09_T3S2B1A_IMMUTABLE_FRM1_ROOT_RESEARCH_ONLY\","
           "\"source_role\":\"first-party-synthetic\","
           "\"profiles\":%u,\"fault_injections\":%u,"
           "\"negative_checks\":%u,\"restart_recoveries\":%u,"
           "\"original_frames\":%u,\"link_retry_cases\":%u,"
           "\"root_file_bytes_accounted\":%u,"
           "\"original_apx3_codec_reused\":true,"
           "\"immutable_root_published\":true,"
           "\"rolling_retention_qualified\":false,"
           "\"original_source_deleted\":false,"
           "\"physical_powerloss_qualified\":false,"
           "\"ssc305_hardware_qualified\":false,"
           "\"whole_device_memory_qualified\":false,"
           "\"public_sdk_installed\":false}\n",
           CASES,FAULTS,NEGATIVE,RESTARTS,FRAMES,RETRY,ROOT_BYTES);
    return 0;
}
