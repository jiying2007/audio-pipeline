/* #809: source-observed original S1/A0/APX3/FBS1 -> independent FRM2.
 * Test tampering/cleanup affects only mkdtemp-owned fixtures, not A1 code.
 */
#define _POSIX_C_SOURCE 200809L
#define main historical_b0_main
#include "fe09_b2s3_t3s2b0_manifest_test.c"
#undef main
#include "fe09_b2s3_t3s2b1ba1_anchor_root.h"
#include <dirent.h>
#include <sys/resource.h>
#include <time.h>

typedef struct {
    fixture original;
    fe_t3b1ba0_owner source;
    fe_t3b1ba1_owner root;
    int source_fd,root_fd,held_fd;
    char source_dir[96],root_dir[96],held_dir[96];
    char names[32][FE_T3B1BA0_NAME_CAP];
    uint8_t rows[32][FE_T3S1_ROW_BYTES];
    uint8_t source_hash[32];
    uint32_t frames;
} a1_fixture;

typedef struct {
    uint32_t scene,rate,mics,render,k;
    uint8_t anchor[32],root[32],source[32];
} a1_witness;

static a1_witness A1_WITNESS[48];
static unsigned A1_PROFILES,A1_RESTARTS,A1_FAULTS,A1_RESEALED_SOURCE;
static uint64_t A1_SOURCE_BYTES,A1_ROOT_BYTES;

static uint32_t t32(const uint8_t *p) {
    return (uint32_t)p[0]|(uint32_t)p[1]<<8u|
        (uint32_t)p[2]<<16u|(uint32_t)p[3]<<24u;
}
static uint64_t t64(const uint8_t *p) {
    return (uint64_t)t32(p)|((uint64_t)t32(p+4u)<<32u);
}
static int private_directory(char name[96],const char *stem) {
    must(snprintf(name,96u,"/tmp/%s-XXXXXX",stem)>0,"A1_TEST_DIR_NAME");
    must(mkdtemp(name)!=NULL,"A1_EXCLUSIVE_TEST_DIR");
    int fd=open(name,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    must(fd>=0,"A1_CALLER_OWNED_NOFOLLOW_DIRECTORY");return fd;
}
static unsigned directory_count(int fd) {
    int duplicate=openat(fd,".",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    must(duplicate>=0,"A1_INDEPENDENT_DIRECTORY_COUNT_FD");
    DIR *d=fdopendir(duplicate);must(d!=NULL,"A1_DIRECTORY_COUNT_STREAM");
    struct dirent *entry;unsigned count=0u;
    while((entry=readdir(d))!=NULL)
        if(strcmp(entry->d_name,".")&&strcmp(entry->d_name,".."))++count;
    must(closedir(d)==0,"A1_DIRECTORY_COUNT_CLOSE");return count;
}
static void cleanup_directory(int fd,const char *name) {
    int duplicate=openat(fd,".",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    must(duplicate>=0,"A1_FIXTURE_CLEANUP_FD");
    DIR *d=fdopendir(duplicate);must(d!=NULL,"A1_FIXTURE_CLEANUP_STREAM");
    struct dirent *entry;
    while((entry=readdir(d))!=NULL) {
        if(!strcmp(entry->d_name,".")||!strcmp(entry->d_name,".."))continue;
        must(unlinkat(fd,entry->d_name,0)==0,"A1_TEST_ONLY_FIXTURE_CLEANUP");
    }
    must(closedir(d)==0&&close(fd)==0&&rmdir(name)==0,"A1_TEST_DIR_REMOVED");
}
static size_t read_file(int dirfd,const char *name,uint8_t *out,size_t cap) {
    struct stat st;
    int fd=openat(dirfd,name,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    must(fd>=0&&fstat(fd,&st)==0&&S_ISREG(st.st_mode)&&st.st_nlink==1&&
         st.st_size>0&&(uint64_t)st.st_size<=(uint64_t)cap,"A1_TEST_READ_REAL_FILE");
    size_t size=(size_t)st.st_size,done=0u;
    while(done<size) {
        ssize_t n=read(fd,out+done,size-done);must(n>0,"A1_TEST_FULL_READ");done+=(size_t)n;
    }
    must(close(fd)==0,"A1_TEST_READ_CLOSE");return size;
}
static void write_file(int dirfd,const char *name,const uint8_t *data,size_t size,int create) {
    int fd=openat(dirfd,name,O_WRONLY|O_NOFOLLOW|O_CLOEXEC|
        (create?(O_CREAT|O_EXCL):O_TRUNC),0600);
    must(fd>=0,"A1_TEST_TAMPER_OPEN");
    size_t done=0u;
    while(done<size) {
        ssize_t n=write(fd,data+done,size-done);must(n>0,"A1_TEST_TAMPER_WRITE");done+=(size_t)n;
    }
    must(close(fd)==0,"A1_TEST_TAMPER_CLOSE");
}
static void source_fingerprint(a1_fixture *f,uint8_t digest[32],uint64_t *bytes) {
    uint8_t hashes[32][32],file[FE_T3S1_ROW_BYTES+FE_T3S1_CHUNK_BYTES];
    *bytes=0u;
    must(directory_count(f->source_fd)==f->frames,"A1_ALL_ORIGINAL_PHYSICAL_FILES_PRESENT");
    for(uint32_t i=0u;i<f->frames;++i) {
        size_t n=read_file(f->source_fd,f->names[i],file,sizeof(file));
        must(memcmp(file,f->rows[i],FE_T3S1_ROW_BYTES)==0&&
             fe_b1s1_sha256(file,n,hashes[i])==0,"A1_ORIGINAL_SOURCE_BYTES_PINNED");
        *bytes+=(uint64_t)n;
    }
    must(fe_b1s1_sha256((const uint8_t *)hashes,(size_t)f->frames*32u,digest)==0,
         "A1_INDEPENDENT_PHYSICAL_FILE_SET_SHA");
}
static void no_new_ack(const a1_fixture *f) {
    must(atomic_load_explicit(&f->original.ring.tail,memory_order_acquire)==f->frames&&
         atomic_load_explicit(&f->original.ring.head,memory_order_acquire)==f->frames&&
         f->source.committed==(uint64_t)f->frames&&
         f->original.storage_owner.committed==0u&&f->original.index.count==0u,
         "A1_NEVER_ADVANCES_ORIGINAL_ACK_OR_FROZEN_S2A_B0");
}
static void setup_a1(a1_fixture *f,uint32_t scene,uint32_t rate,
    uint32_t render,uint32_t k,uint32_t cap,uint32_t frames) {
    memset(f,0,sizeof(*f));
    setup(&f->original,scene,rate,render,k,16u);
    f->frames=frames;f->original.cap=32u;
    f->source_fd=private_directory(f->source_dir,"fe09-a1-original");
    f->root_fd=private_directory(f->root_dir,"fe09-a1-root");
    f->held_fd=private_directory(f->held_dir,"fe09-a1-negative-held");
    must(fe_t3b1ba0_bind(&f->source,f->source_fd,&f->original.config,MAPS[scene],cap)==0,
         "A1_UNCHANGED_ORIGINAL_A0_BIND");
    f->original.ring.pinned_sink=fe_t3b1ba0_outboard_sink;
    f->original.ring.pinned_sink_context=&f->source;
    for(uint64_t seq=UINT64_C(1);seq<=(uint64_t)frames;++seq) {
        uint8_t prior[32]={0},hash[32];
        if(seq>UINT64_C(1))must(fe_b1s1_sha256(f->source.last_row,
            FE_T3S1_ROW_BYTES,prior)==0,"A1_ORIGINAL_FULL_ROW_LINK");
        prepare(&f->original,seq,(int)(seq&UINT64_C(1)),prior);
        fe_t3s1_slot *slot=&f->original.slots[(seq-1u)%(uint64_t)k];
        fe_t3s1_drain_receipt receipt;
        atomic_store_explicit(&f->original.ring.head,(uint32_t)seq,memory_order_release);
        must(fe_t3s1_drain_one(&f->original.ring,fe_t3b1ba0_outboard_sink,
             &f->source,&receipt)==FE_T3S1_OK&&receipt.source_sequence==seq&&
             receipt.actually_accounted_bytes==FE_T3S1_ROW_BYTES+slot->apx3_bytes&&
             f->source.committed==seq,"A1_REAL_ORIGINAL_S1_A0_ACK");
        memcpy(f->rows[seq-1u],f->source.last_row,FE_T3S1_ROW_BYTES);
        must(fe_b1s1_sha256(f->source.last_row,FE_T3S1_ROW_BYTES,hash)==0&&
             fe_t3b1ba0_name(f->original.config.capture_source_id,
                 f->original.config.source_generation,seq,hash,
                 f->source.last_row+104u,f->names[seq-1u])==0,
             "A1_REAL_ORIGINAL_IMMUTABLE_SOURCE_FILENAME");
    }
    uint64_t bytes;source_fingerprint(f,f->source_hash,&bytes);no_new_ack(f);
    if(frames==32u)A1_SOURCE_BYTES+=bytes;
}
static void teardown_a1(a1_fixture *f) {
    uint8_t digest[32];uint64_t bytes;
    source_fingerprint(f,digest,&bytes);
    must(memcmp(digest,f->source_hash,32u)==0,"A1_NO_ORIGINAL_SOURCE_DELETION_OR_CHANGE");
    no_new_ack(f);
    cleanup_directory(f->root_fd,f->root_dir);
    cleanup_directory(f->held_fd,f->held_dir);
    cleanup_directory(f->source_fd,f->source_dir);
    f->original.cap=16u;teardown(&f->original);
}
static void rehash_root(uint8_t wire[FE_T3B1BA1_ROOT_BYTES]) {
    memset(wire+FE_T3B1BA1_DIGEST_OFFSET,0,32u);
    must(fe_b1s1_sha256(wire,FE_T3B1BA1_ROOT_BYTES,
         wire+FE_T3B1BA1_DIGEST_OFFSET)==0,"A1_NEGATIVE_REHASH_FULL_ENVELOPE");
}
static void rejected_root(a1_fixture *f,const uint8_t *wire,size_t n,const char *why) {
    reject(fe_t3b1ba1_verify_bytes(&f->root,wire,n)!=0,why);no_new_ack(f);
}
static void failed_read(a1_fixture *f,const char *why) {
    fe_t3b1ba1_receipt r,zero;
    memset(&r,0xa5,sizeof(r));memset(&zero,0,sizeof(zero));
    reject(fe_t3b1ba1_read(&f->root,&r)!=0&&memcmp(&r,&zero,sizeof(r))==0,why);
    no_new_ack(f);
}
static void field_negatives(a1_fixture *f,const uint8_t *good) {
    uint8_t bad[FE_T3B1BA1_ROOT_BYTES];
    for(unsigned mutation=0u;mutation<6u;++mutation) {
        memcpy(bad,good,sizeof(bad));
        if(mutation==0u)memset(bad+96u,0,32u);
        if(mutation==1u)bad[96]^=1u;
        if(mutation==2u)memcpy(bad+96u,f->rows[15]+168u,32u);
        if(mutation==3u)memcpy(bad+224u+8u,f->rows[16]+168u,32u);
        if(mutation==4u)p64(bad+32u,f->original.config.source_generation+UINT64_C(1));
        if(mutation==5u)p32(bad+24u,17u);
        rehash_root(bad);rejected_root(f,bad,sizeof(bad),"A1_REHASHED_ANCHOR_SOURCE_CAP_IDENTITY_REJECTED");
    }
    fe_t3b1ba0_owner smaller=f->source;smaller.cap=17u;
    fe_t3b1ba1_owner sentinel,original;
    memset(&sentinel,0xa5,sizeof(sentinel));original=sentinel;
    reject(fe_t3b1ba1_bind(&sentinel,f->root_fd,&smaller)!=0&&
           memcmp(&sentinel,&original,sizeof(sentinel))==0,"A1_CAP17_CANNOT_REFERENCE_32");
    no_new_ack(f);
}
static void extra_wire_negatives(a1_fixture *f,const uint8_t *good) {
    static const unsigned fields[]={0u,4u,8u,12u,16u,20u,28u,40u,44u,48u,52u,
        56u,60u,64u,68u,192u,196u,200u,204u,208u,212u,216u,220u};
    uint8_t bad[FE_T3B1BA1_ROOT_BYTES+1u];
    for(unsigned i=0u;i<sizeof(fields)/sizeof(fields[0]);++i) {
        memcpy(bad,good,FE_T3B1BA1_ROOT_BYTES);
        bad[fields[i]]^=1u;rehash_root(bad);
        rejected_root(f,bad,FE_T3B1BA1_ROOT_BYTES,"A1_REHASHED_SCHEMA_OWNER_SLOT_OR_RESERVED_FIELD");
    }
    static const unsigned wide[]={32u,72u,80u,88u,224u,296u};
    for(unsigned i=0u;i<sizeof(wide)/sizeof(wide[0]);++i) {
        memcpy(bad,good,FE_T3B1BA1_ROOT_BYTES);p64(bad+wide[i],UINT64_MAX);
        rehash_root(bad);rejected_root(f,bad,FE_T3B1BA1_ROOT_BYTES,"A1_EPOCH_SEQUENCE_WRAP_REJECTED");
    }
    for(unsigned mutation=0u;mutation<5u;++mutation) {
        memcpy(bad,good,FE_T3B1BA1_ROOT_BYTES);
        if(mutation==0u)p64(bad+72u,UINT64_C(16));
        if(mutation==1u)p64(bad+88u,UINT64_C(31));
        if(mutation==2u)p64(bad+296u,UINT64_C(17));
        if(mutation==3u)bad[128]^=1u;
        if(mutation==4u)bad[264]^=1u;
        rehash_root(bad);rejected_root(f,bad,FE_T3B1BA1_ROOT_BYTES,"A1_REGRESSION_DUPLICATE_HIGHWATER_OR_MEMBER_SHA");
    }
    memcpy(bad,good,FE_T3B1BA1_ROOT_BYTES);bad[160]^=1u;
    rejected_root(f,bad,FE_T3B1BA1_ROOT_BYTES,"A1_WRONG_ROOT_DIGEST");
    rejected_root(f,good,FE_T3B1BA1_ROOT_BYTES-1u,"A1_TORN_ROOT_BYTES");
    rejected_root(f,bad,sizeof(bad),"A1_EXCESS_ROOT_BYTES");
    rejected_root(f,good,SIZE_MAX,"A1_OVERSIZED_ROOT_LENGTH");
    rejected_root(f,NULL,FE_T3B1BA1_ROOT_BYTES,"A1_MISSING_ROOT_BUFFER");
}
static void source_negatives(a1_fixture *f) {
    static const unsigned seqs[]={1u,16u,17u,32u};
    uint8_t file[FE_T3S1_ROW_BYTES+FE_T3S1_CHUNK_BYTES];
    for(unsigned i=0u;i<4u;++i) {
        unsigned at=seqs[i]-1u;
        must(renameat(f->source_fd,f->names[at],f->held_fd,"held") ==0,"A1_TEST_REMOVE_EXACT_ORIGINAL_SOURCE");
        failed_read(f,"A1_MISSING_ORIGINAL_UNRETAINED_ANCHOR_OR_RETAINED_ROW");
        must(renameat(f->held_fd,"held",f->source_fd,f->names[at])==0,"A1_RESTORE_ORIGINAL_SOURCE");
        size_t n=read_file(f->source_fd,f->names[at],file,sizeof(file));
        file[0]^=1u;write_file(f->source_fd,f->names[at],file,n,0);
        failed_read(f,"A1_ALTERED_ORIGINAL_UNRETAINED_ANCHOR_OR_RETAINED_ROW");
        file[0]^=1u;write_file(f->source_fd,f->names[at],file,n,0);
    }
    size_t n=read_file(f->source_fd,f->names[16],file,sizeof(file));
    uint8_t original_row[FE_T3S1_ROW_BYTES],hash[32];
    char changed_name[FE_T3B1BA0_NAME_CAP];
    memcpy(original_row,file,sizeof(original_row));
    for(unsigned mutation=0u;mutation<3u;++mutation) {
        memcpy(file,original_row,sizeof(original_row));
        if(mutation==0u)file[136]^=1u;
        if(mutation==1u)p32(file+40u,UINT32_MAX);
        if(mutation==2u)p64(file+20u,UINT64_MAX);
        must(fe_b1s1_sha256(file,168u,file+168u)==0&&
             fe_b1s1_sha256(file,FE_T3S1_ROW_BYTES,hash)==0&&
             fe_t3b1ba0_name(f->original.config.capture_source_id,
                 f->original.config.source_generation,UINT64_C(17),hash,
                 file+104u,changed_name)==0,"A1_SOURCE_NEGATIVE_COMPLETE_ROW_REHASH");
        must(renameat(f->source_fd,f->names[16],f->held_fd,"held")==0,"A1_HOLD_ORIGINAL_ROW17");
        write_file(f->source_fd,changed_name,file,n,1);
        failed_read(f,"A1_ORIGINAL_ROW17_PRIOR_OWNER_OR_EPOCH_REJECTED_AFTER_REHASH");
        must(unlinkat(f->source_fd,changed_name,0)==0&&
             renameat(f->held_fd,"held",f->source_fd,f->names[16])==0,"A1_RESTORE_ORIGINAL_ROW17_BYTES");
    }
    int saved=dup(f->source_fd);must(saved>=0,"A1_SAVE_ORIGINAL_DIRECTORY_FD");
    must(dup2(f->held_fd,f->source_fd)==f->source_fd,"A1_INJECT_FOREIGN_SOURCE_INODE");
    failed_read(f,"A1_SOURCE_DIRECTORY_FD_REPLACEMENT_REJECTED");
    must(dup2(saved,f->source_fd)==f->source_fd&&close(saved)==0,"A1_RESTORE_ORIGINAL_DIRECTORY_FD");
}
/* Rebuild a completely valid source chain with the ORIGINAL writer/replay,
 * changing only old unretained row1 PRESENT->ABSENT. A0 independently accepts
 * it, but A1 must reject its difference from the original frozen row32 pin.
 */
static void resealed_source_negative(a1_fixture *f) {
    uint8_t *files=(uint8_t *)malloc(32u*(FE_T3S1_ROW_BYTES+FE_T3S1_CHUNK_BYTES));
    size_t lengths[32];char changed[32][FE_T3B1BA0_NAME_CAP];
    uint8_t prior[32]={0},row[FE_T3S1_ROW_BYTES],hash[32];
    must(files!=NULL&&f->original.config.render_enabled==1u,"A1_BOUNDED_RESEALED_SOURCE_FIXTURE");
    for(unsigned i=0u;i<32u;++i) {
        uint8_t *file=files+(size_t)i*(FE_T3S1_ROW_BYTES+FE_T3S1_CHUNK_BYTES);
        lengths[i]=read_file(f->source_fd,f->names[i],file,FE_T3S1_ROW_BYTES+FE_T3S1_CHUNK_BYTES);
        must(renameat(f->source_fd,f->names[i],f->held_fd,f->names[i])==0,"A1_HOLD_EACH_ORIGINAL_IMMUTABLE_FILE");
    }
    prepare(&f->original,UINT64_C(1),0,prior);
    for(unsigned i=0u;i<32u;++i) {
        uint8_t *file=files+(size_t)i*(FE_T3S1_ROW_BYTES+FE_T3S1_CHUNK_BYTES);
        if(i==0u) {
            fe_t3s1_slot *slot=&f->original.slots[0];
            memcpy(row,slot->canonical_row,sizeof(row));
            memcpy(file,row,sizeof(row));memcpy(file+sizeof(row),slot->apx3,slot->apx3_bytes);
            lengths[i]=sizeof(row)+slot->apx3_bytes;
        } else {
            memcpy(row,f->rows[i],sizeof(row));memcpy(row+136u,prior,32u);
            must(fe_b1s1_sha256(row,168u,row+168u)==0,"A1_RESEAL_ORIGINAL_ROW_PREFIX");
            memcpy(file,row,sizeof(row));
        }
        must(fe_b1s1_sha256(row,sizeof(row),hash)==0&&
             fe_t3b1ba0_name(f->original.config.capture_source_id,
                 f->original.config.source_generation,(uint64_t)i+1u,hash,row+104u,changed[i])==0,
             "A1_ORIGINAL_NAMER_FOR_RESEALED_CHAIN");
        memcpy(prior,hash,32u);write_file(f->source_fd,changed[i],file,lengths[i],1);
    }
    fe_t3b1ba0_owner rebound;
    must(fe_t3b1ba0_bind(&rebound,f->source_fd,&f->original.config,
         f->source.slots,32u)==0&&rebound.committed==UINT64_C(32)&&
         memcmp(rebound.last_row,f->source.last_row,FE_T3S1_ROW_BYTES)!=0,
         "A1_NEGATIVE_IS_VALID_ORIGINAL_A0_CHAIN_WITH_CHANGED_UNRETAINED_SOURCE");
    failed_read(f,"A1_VALID_RESEALED_OLD_SOURCE_STILL_DIFFERS_FROM_ORIGINAL_HIGHWATER");
    for(unsigned i=0u;i<32u;++i) {
        must(unlinkat(f->source_fd,changed[i],0)==0&&
             renameat(f->held_fd,f->names[i],f->source_fd,f->names[i])==0,
             "A1_RESTORE_ALL_ORIGINAL_SOURCE_BYTES_AFTER_NEGATIVE");
    }
    free(files);++A1_RESEALED_SOURCE;
}
static void root_fs_negatives(a1_fixture *f,const uint8_t *good,const char *name) {
    fe_t3b1ba1_owner candidate;
    int alias=dup(f->source_fd);must(alias>=0,"A1_DUP_SOURCE_DIR_ALIAS");
    reject(fe_t3b1ba1_bind(&candidate,alias,&f->source)!=0,"A1_DISTINCT_FD_SAME_SOURCE_INODE_REJECTED");
    must(close(alias)==0,"A1_CLOSE_SOURCE_ALIAS");
    int weak=open(f->root_dir,O_RDONLY|O_DIRECTORY|O_CLOEXEC);
    must(weak>=0,"A1_DIRECTORY_WITHOUT_NOFOLLOW_FIXTURE");
    reject(fe_t3b1ba1_bind(&candidate,weak,&f->source)!=0,"A1_ROOT_REQUIRES_NOFOLLOW_FD");
    must(close(weak)==0,"A1_CLOSE_WEAK_FD");
    int saved=dup(f->root_fd);must(saved>=0&&dup2(f->held_fd,f->root_fd)==f->root_fd,
         "A1_REPLACE_ROOT_FD_WITH_FOREIGN_INODE");
    failed_read(f,"A1_ROOT_DIRECTORY_FD_REPLACEMENT_REJECTED");
    must(dup2(saved,f->root_fd)==f->root_fd&&close(saved)==0,"A1_RESTORE_ROOT_FD");
    must(linkat(f->root_fd,name,f->held_fd,"alias",0)==0,"A1_ROOT_HARDLINK_FIXTURE");
    failed_read(f,"A1_ROOT_FOREIGN_HARDLINK_REJECTED");
    must(unlinkat(f->held_fd,"alias",0)==0,"A1_REMOVE_TEST_ALIAS");
    must(renameat(f->root_fd,name,f->held_fd,"held-root")==0&&
         symlinkat("/dev/null",f->root_fd,name)==0,"A1_ROOT_SYMLINK_FIXTURE");
    failed_read(f,"A1_ROOT_SYMLINK_REJECTED");
    must(unlinkat(f->root_fd,name,0)==0&&
         mkdirat(f->root_fd,name,0700)==0,"A1_ROOT_DIRECTORY_AS_FILE_FIXTURE");
    failed_read(f,"A1_DIRECTORY_INSTEAD_OF_IMMUTABLE_ROOT_REJECTED");
    must(unlinkat(f->root_fd,name,AT_REMOVEDIR)==0&&
         renameat(f->held_fd,"held-root",f->root_fd,name)==0,"A1_RESTORE_REAL_IMMUTABLE_ROOT");
    uint8_t bad[FE_T3B1BA1_ROOT_BYTES+1u];memcpy(bad,good,FE_T3B1BA1_ROOT_BYTES);bad[1376]=0u;
    write_file(f->root_fd,name,bad,1375u,0);failed_read(f,"A1_TORN_PUBLISHED_ROOT_REJECTED");
    write_file(f->root_fd,name,bad,1377u,0);failed_read(f,"A1_EXCESS_PUBLISHED_ROOT_REJECTED");
    write_file(f->root_fd,name,good,FE_T3B1BA1_ROOT_BYTES,0);
    write_file(f->root_fd,"orphan.part",good,21u,1);failed_read(f,"A1_ORPHAN_PART_WITHHOLDS_ROOT_ADMISSION");
    must(unlinkat(f->root_fd,"orphan.part",0)==0,"A1_REMOVE_TEST_ORPHAN");
    memcpy(bad,good,FE_T3B1BA1_ROOT_BYTES);bad[96]^=1u;rehash_root(bad);
    char other[FE_T3B1BA1_NAME_CAP];must(fe_t3b1ba1_name(bad,other)==0,"A1_COMPETING_ROOT_NAME");
    write_file(f->root_fd,other,bad,FE_T3B1BA1_ROOT_BYTES,1);
    failed_read(f,"A1_OVERLAPPING_COMPETING_ROOTS_REJECTED");
    must(unlinkat(f->root_fd,other,0)==0,"A1_REMOVE_ONLY_TEST_COMPETING_ROOT");
    no_new_ack(f);
}
static void fault_transactions(a1_fixture *f) {
    for(unsigned value=1u;value<=10u;++value) {
        char path[96];int fd=private_directory(path,"fe09-a1-root-fault");
        fe_t3b1ba1_owner root,restarted;fe_t3b1ba1_receipt r,zero;
        memset(&zero,0,sizeof(zero));
        must(fe_t3b1ba1_bind(&root,fd,&f->source)==0&&
             fe_t3b1ba1_set_test_fault(&root,(fe_t3b1ba1_fault)value)==0,
             "A1_ISOLATED_HOST_FAULT_BOUND_OWNER");
        memset(&r,0xa5,sizeof(r));
        reject(fe_t3b1ba1_publish(&root,&r)!=0&&memcmp(&r,&zero,sizeof(r))==0,
               "A1_POSIX_FAULT_WITHHOLDS_HOSTED_RECEIPT_AND_ORIGINAL_ACK");
        unsigned files=directory_count(fd);
        if(value<=2u) {
            must(files==0u&&fe_t3b1ba1_bind(&restarted,fd,&f->source)==0,
                 "A1_CREATE_FAILURE_HAS_NO_ROOT_OR_ACK");
        } else if(value<=7u) {
            must(files==(value==7u?2u:1u),"A1_PARTIAL_FORENSIC_BYTES_PRESERVED");
            reject(fe_t3b1ba1_bind(&restarted,fd,&f->source)!=0,
                   "A1_ORPHAN_OR_HALF_PUBLISHED_ROOT_RESTART_FAIL_CLOSED");
        } else {
            must(files==1u&&fe_t3b1ba1_bind(&restarted,fd,&f->source)==0&&
                 restarted.root_visible_on_bind==1u&&fe_t3b1ba1_read(&restarted,&r)==0&&
                 r.hosted_checkpoint_committed==0u&&r.source_ack_proven==0u,
                 "A1_VISIBLE_ROOT_RESTART_NEVER_PROVES_OLD_DURABILITY_OR_ACK");
            must(fe_t3b1ba1_publish(&restarted,&r)==0&&r.hosted_checkpoint_committed==1u&&
                 r.source_ack_proven==0u,"A1_EXPLICIT_RETRY_REPEATS_SYNC_READBACK_WITHOUT_SOURCE_ACK");
            ++A1_RESTARTS;
        }
        no_new_ack(f);++A1_FAULTS;cleanup_directory(fd,path);
    }
}
static void run_profile(uint32_t scene,uint32_t rate,uint32_t render,uint32_t k) {
    a1_fixture *f=(a1_fixture *)calloc(1u,sizeof(*f));
    must(f!=NULL,"A1_BOUNDED_TEST_FIXTURE");setup_a1(f,scene,rate,render,k,32u,32u);
    uint8_t wire[FE_T3B1BA1_ROOT_BYTES],independent[FE_T3B1BA1_ROOT_BYTES],hash[32];
    char name[FE_T3B1BA1_NAME_CAP];fe_t3b1ba1_receipt r;
    must(fe_t3b1ba1_bind(&f->root,f->root_fd,&f->source)==0&&
         fe_t3b1ba1_encode(&f->root,wire)==0&&fe_t3b1ba1_name(wire,name)==0,
         "A1_PRIVATE_FRM2_BOUND_TO_ALL_32_ORIGINAL_FILES");
    failed_read(f,"A1_EMPTY_ROOT_DIRECTORY_HAS_NO_INVENTED_CHECKPOINT");
    must(t32(wire)==FE_T3B1BA1_MAGIC&&t32(wire+4u)==2u&&t32(wire+8u)==224u&&
         t32(wire+12u)==72u&&t32(wire+16u)==1376u&&t32(wire+20u)==16u&&
         t64(wire+72u)==17u&&t64(wire+80u)==32u&&t64(wire+88u)==32u&&
         fe_b1s1_sha256(f->rows[15],FE_T3S1_ROW_BYTES,hash)==0&&memcmp(wire+96u,hash,32u)==0&&
         memcmp(hash,f->rows[15]+168u,32u)!=0,"A1_INDEPENDENT_FULL_ROW16_NONZERO_LEFT_ANCHOR");
    for(unsigned i=16u;i<32u;++i) {
        const uint8_t *member=wire+224u+(i-16u)*72u;
        must(t64(member)==(uint64_t)i+1u&&memcmp(f->rows[i]+136u,hash,32u)==0&&
             fe_b1s1_sha256(f->rows[i],FE_T3S1_ROW_BYTES,hash)==0&&
             memcmp(member+8u,hash,32u)==0&&memcmp(member+40u,f->rows[i]+104u,32u)==0,
             "A1_INDEPENDENT_RETAINED_ORIGINAL_ROW_AND_APX3_DIGEST_LIST");
    }
    memcpy(independent,wire,sizeof(wire));memset(independent+160u,0,32u);
    must(fe_b1s1_sha256(independent,sizeof(independent),hash)==0&&
         memcmp(hash,wire+160u,32u)==0,"A1_INDEPENDENT_IMMUTABLE_ROOT_DIGEST");
    field_negatives(f,wire);
    must(fe_t3b1ba1_publish(&f->root,&r)==0&&r.hosted_checkpoint_committed==1u&&
         r.original_files_verified==32u&&r.source_ack_proven==0u,
         "A1_FILE_DIR_SYNC_AND_INDEPENDENT_SOURCE_RECHECK_BEFORE_RECEIPT");
    struct stat before,after;
    must(fstatat(f->root_fd,name,&before,AT_SYMLINK_NOFOLLOW)==0&&
         fe_t3b1ba1_publish(&f->root,&r)==0&&
         fstatat(f->root_fd,name,&after,AT_SYMLINK_NOFOLLOW)==0&&
         before.st_ino==after.st_ino&&before.st_dev==after.st_dev&&
         directory_count(f->root_fd)==1u,"A1_IDEMPOTENT_ROOT_NO_OVERWRITE_OR_NEW_ACK");
    A1_ROOT_BYTES+=(uint64_t)after.st_size;
    fe_t3b1ba1_owner restarted;
    must(fe_t3b1ba1_bind(&restarted,f->root_fd,&f->source)==0&&
         restarted.root_visible_on_bind==1u&&fe_t3b1ba1_read(&restarted,&r)==0&&
         r.hosted_checkpoint_committed==0u&&r.source_ack_proven==0u,
         "A1_RESTART_READ_IS_VISIBLE_SOURCE_PROOF_NOT_ACK_OR_OLD_DURABILITY");
    ++A1_RESTARTS;
    if(A1_PROFILES==0u) {
        extra_wire_negatives(f,wire);source_negatives(f);root_fs_negatives(f,wire,name);fault_transactions(f);
    }
    if(scene==1u&&rate==16000u&&render==1u&&k==2u)resealed_source_negative(f);
    a1_witness *w=&A1_WITNESS[A1_PROFILES++];
    w->scene=scene;w->rate=rate;w->mics=MICS[scene];w->render=render;w->k=k;
    memcpy(w->anchor,wire+96u,32u);memcpy(w->root,wire+160u,32u);
    memcpy(w->source,f->source_hash,32u);
    teardown_a1(f);free(f);
}
static void print_hash(const uint8_t value[32]) {
    for(unsigned i=0u;i<32u;++i)printf("%02x",(unsigned)value[i]);
}
int main(void) {
    struct timespec started,ended;struct rusage usage;
    must(clock_gettime(CLOCK_MONOTONIC,&started)==0,"A1_HOST_CLOCK_MEASUREMENT");
    for(uint32_t scene=0u;scene<4u;++scene)
        for(unsigned rate=0u;rate<3u;++rate)
            for(uint32_t render=0u;render<2u;++render)
                for(uint32_t k=1u;k<=2u;++k)run_profile(scene,RATES[rate],render,k);
    a1_fixture *small=(a1_fixture *)calloc(1u,sizeof(*small));
    must(small!=NULL,"A1_CAP17_NEGATIVE_FIXTURE");setup_a1(small,0u,16000u,0u,1u,17u,17u);
    fe_t3b1ba1_owner rejected;
    reject(fe_t3b1ba1_bind(&rejected,small->root_fd,&small->source)!=0,"A1_ACTUAL_CAP17_HIGHWATER17_CANNOT_PUBLISH_17_TO_32");
    teardown_a1(small);free(small);
    must(A1_PROFILES==48u&&NEGATIVES>100u&&A1_FAULTS==10u&&A1_RESTARTS==51u&&
         A1_RESEALED_SOURCE==1u,"A1_COMPLETE_MATRIX_SOURCE_NEGATIVES_AND_RESTARTS");
    printf("{\"decision\":\"FE09_B1B_A1_FRM2_NONZERO_ORIGINAL_LEFT_ANCHOR_HOSTED_NO_PRUNE\","
        "\"source_role\":\"first-party-synthetic\",\"profiles\":48,"
        "\"matrix_original_frames\":1536,\"matrix_original_acks\":1536,"
        "\"additional_negative_fixture_frames\":17,\"logical_first\":17,\"logical_last\":32,"
        "\"physical_original_files\":1536,\"hosted_roots\":48,\"negative_checks\":%u,"
        "\"restart_verified\":%u,\"host_faults_rejected\":%u,\"valid_resealed_source_rejected\":%u,"
        "\"original_source_disk_bytes\":%" PRIu64 ",\"root_disk_bytes\":%" PRIu64 ","
        "\"original_ack_created_by_a1\":false,\"original_source_deleted\":false,"
        "\"real_rolling_retention_qualified\":false,\"physical_powerloss_qualified\":false,"
        "\"ssc305_hardware_qualified\":false,\"whole_device_memory_qualified\":false,"
        "\"public_sdk_installed\":false,\"cases\":[",
        NEGATIVES,A1_RESTARTS,A1_FAULTS,A1_RESEALED_SOURCE,A1_SOURCE_BYTES,A1_ROOT_BYTES);
    for(unsigned i=0u;i<48u;++i) {
        const a1_witness *w=&A1_WITNESS[i];
        if(i)putchar(',');
        printf("{\"scene\":%u,\"rate\":%u,\"mics\":%u,\"render\":%u,\"k\":%u,\"anchor_sha256\":\"",
            w->scene,w->rate,w->mics,w->render,w->k);
        print_hash(w->anchor);printf("\",\"root_sha256\":\"");print_hash(w->root);
        printf("\",\"original_files_sha256\":\"");print_hash(w->source);printf("\"}");
    }
    printf("]}\n");
    must(clock_gettime(CLOCK_MONOTONIC,&ended)==0&&getrusage(RUSAGE_SELF,&usage)==0,
         "A1_REAL_HOST_RESOURCE_ATTRIBUTION");
    uint64_t elapsed=(uint64_t)(ended.tv_sec-started.tv_sec)*UINT64_C(1000000000);
    if(ended.tv_nsec>=started.tv_nsec)elapsed+=(uint64_t)(ended.tv_nsec-started.tv_nsec);
    else elapsed-=(uint64_t)(started.tv_nsec-ended.tv_nsec);
    fprintf(stderr,"FE09_A1_HOST_ATTRIBUTION {\"elapsed_ns\":%" PRIu64
        ",\"max_rss_kib\":%ld,\"root_owner_bytes\":%zu,\"fixture_bytes\":%zu}\n",
        elapsed,usage.ru_maxrss,sizeof(fe_t3b1ba1_owner),sizeof(a1_fixture));
    return 0;
}
