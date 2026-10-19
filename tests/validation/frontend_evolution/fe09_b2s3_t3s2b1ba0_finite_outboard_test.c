/* #803: actual original first-party S2 APX3 and 200B FBS1 across global
 * Capture seq16 -> seq17 -> seq32, with no old source file deletion.
 * NONSHIPPING Linux POSIX test; not HIL, real ADC clock or rolling storage.
 */
#define _POSIX_C_SOURCE 200809L
#define main historical_b0_main
#include "fe09_b2s3_t3s2b0_manifest_test.c"
#undef main
#include "fe09_b2s3_t3s2b1ba0_finite_outboard.h"
#include <dirent.h>
#include <errno.h>

static uint32_t A0_PROFILES,A0_NEGATIVES,A0_BOUNDARY_NACKS;
static uint64_t A0_FRAMES,A0_ACKED,A0_SOURCE_FILES,A0_SOURCE_BYTES;
static uint64_t A0_RECOVERED,A0_FAULTS;
static void a0_must(int ok,const char *reason) {
    if(!ok){fprintf(stderr,"FE09_A0_FINITE_NOT_ADMITTED %s\n",reason);exit(1);}
}
static void a0_reject(int ok,const char *reason) {
    a0_must(ok,reason);++A0_NEGATIVES;
}
typedef struct {
    fixture *source;
    fe_t3b1ba0_owner store;
    int fd;
    char dir[96];
    uint32_t cap;
} a0_stage;
static void a0_start(a0_stage *s,uint32_t scene,uint32_t rate,
                     uint32_t render,uint32_t slots,uint32_t cap) {
    memset(s,0,sizeof(*s));
    s->fd=-1;s->cap=cap;
    s->source=(fixture *)calloc(1,sizeof(*s->source));
    a0_must(s->source!=NULL,"ALLOC_ORIGINAL_FIRST_PARTY_SOURCE");
    /* Original B0 fixture binds frozen S2A strictly to <=16; A0 callback
     * instead consumes the original S1 ring to a different fresh directory.
     */
    setup(s->source,scene,rate,render,slots,16u);
    s->source->cap=cap+1u; /* only test-only original S2/FBS1 frame builder */
    strcpy(s->dir,"/tmp/fe09-a0-outboard-XXXXXX");
    a0_must(mkdtemp(s->dir)!=NULL,"OWN_FRESH_DIR");
    s->fd=open(s->dir,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    a0_must(s->fd>=0,"OWN_EXCLUSIVE_DIRECTORY_FD");
    a0_must(fe_t3b1ba0_bind(&s->store,s->fd,&s->source->config,
               MAPS[scene],cap)==0&&s->store.committed==0u&&
            s->store.binding_complete==1u,"BIND_NONROLLING_FRESH_OWNER");
    s->source->ring.pinned_sink=fe_t3b1ba0_outboard_sink;
    s->source->ring.pinned_sink_context=&s->store;
}
static void a0_clear_private(a0_stage *s) {
    int fd=openat(s->fd,".",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    a0_must(fd>=0,"OPEN_ISOLATED_DIR_FOR_FINAL_TEARDOWN");
    DIR *d=fdopendir(fd);
    a0_must(d!=NULL,"OPEN_DIR_STREAM");
    struct dirent *entry;
    while((entry=readdir(d))!=NULL) {
        if(!strcmp(entry->d_name,".")||!strcmp(entry->d_name,".."))
            continue;
        a0_must(unlinkat(s->fd,entry->d_name,0)==0,
                "UNLINK_ONLY_TEST_OWNED_FINITE_FILE");
    }
    a0_must(closedir(d)==0&&close(s->fd)==0&&
            rmdir(s->dir)==0,"TEARDOWN_NO_A0_RESIDUE");
    s->source->cap=16u;
    teardown(s->source); /* unchanged original S2A directory was EMPTY */
    free(s->source);s->source=NULL;s->fd=-1;
}
static int a0_find(a0_stage *s,uint64_t seq,
                   char found[FE_T3B1BA0_NAME_CAP]) {
    int fd=openat(s->fd,".",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(fd<0)return -1;
    DIR *d=fdopendir(fd);
    if(!d){(void)close(fd);return -1;}
    char needle[25],search[FE_T3B1BA0_NAME_CAP]={0};
    int n=snprintf(needle,sizeof(needle),"-%016" PRIx64 "-",seq);
    if(n!=18){(void)closedir(d);return -1;}
    unsigned matched=0u;
    struct dirent *entry;
    while((entry=readdir(d))!=NULL) {
        if(strncmp(entry->d_name,"fa0-",4u)==0 &&
           strlen(entry->d_name)==180u &&
           memcmp(entry->d_name+29u,needle,18u)==0) {
            if(++matched!=1u)break;
            strcpy(search,entry->d_name);
        }
    }
    if(closedir(d)!=0||matched!=1u)return -1;
    strcpy(found,search);return 0;
}
static void a0_original_ack(a0_stage *s,uint64_t seq) {
    uint8_t prior[32]={0};
    fe_t3s1_drain_receipt ack;
    fixture *f=s->source;
    fe_t3s1_slot *slot;
    uint64_t before=f->storage_owner.committed;
    if(s->store.committed)
        a0_must(fe_b1s1_sha256(s->store.last_row,
          FE_T3S1_ROW_BYTES,prior)==0,"HASH_COMPLETE_PREVIOUS_200B_FBS1");
    prepare(f,seq,(int)(seq&1u),prior);
    slot=&f->slots[(seq-1u)%(uint64_t)f->k];
    atomic_store_explicit(&f->ring.head,(uint32_t)seq,memory_order_release);
    memset(&ack,0,sizeof(ack));
    a0_must(fe_t3s1_drain_one(&f->ring,fe_t3b1ba0_outboard_sink,
          &s->store,&ack)==FE_T3S1_OK&&
          ack.source_sequence==seq&&ack.canonical_row_bytes==200u&&
          ack.actually_accounted_bytes==(size_t)slot->apx3_bytes+200u&&
          f->ring.drained_global_capture==seq&&
          s->store.committed==seq&&f->storage_owner.committed==before&&
          f->index.count==0u,"ACTUAL_ORIGINAL_S1_SOURCE_ACK_FROZEN_S2A_UNCHANGED");
    ++A0_ACKED;++A0_FRAMES;
}
static void a0_inventory_all(a0_stage *s) {
    uint64_t bytes=UINT64_C(0);
    for(uint64_t n=1u;n<=(uint64_t)s->cap;++n) {
        char name[FE_T3B1BA0_NAME_CAP];
        struct stat st;
        a0_must(a0_find(s,n,name)==0&&
            fstatat(s->fd,name,&st,AT_SYMLINK_NOFOLLOW)==0&&
            S_ISREG(st.st_mode)&&st.st_nlink==1&&
            st.st_size>(off_t)FE_T3S1_ROW_BYTES&&
            st.st_size<=(off_t)(FE_T3S1_ROW_BYTES+
                               FE_T3S1_CHUNK_BYTES),
            "ORIGINAL_APX3_BYTES_PRESENT_PER_UNIQUE_GLOBAL_SEQUENCE");
        bytes+=(uint64_t)st.st_size;
    }
    A0_SOURCE_FILES+=s->cap;A0_SOURCE_BYTES+=bytes;
}
static void a0_rebind(a0_stage *s) {
    fe_t3b1ba0_owner recovered;
    memset(&recovered,0xA5,sizeof(recovered));
    a0_must(fe_t3b1ba0_bind(&recovered,s->fd,&s->source->config,
        s->source->ring.physical_to_slot,s->cap)==0&&
        recovered.committed==(uint64_t)s->cap&&
        recovered.restart_recovered==1u&&
        recovered.binding_complete==1u&&
        memcmp(recovered.last_row,s->store.last_row,200u)==0,
        "EXACT_POST_RESTART_ORIGINAL_SOURCE_HASH_INVENTORY");
    ++A0_RECOVERED;
}
static void a0_negative_inventory(a0_stage *s) {
    fe_t3b1ba0_owner candidate;
    char name[FE_T3B1BA0_NAME_CAP],other[FE_T3B1BA0_NAME_CAP];
    uint8_t b;
    int fd;
    struct stat st;
    a0_must(a0_find(s,17u,name)==0,"SEQ17_IMMUTABLE_NAME_EXISTS");
    fd=openat(s->fd,name,O_RDWR|O_NOFOLLOW|O_CLOEXEC);
    a0_must(fd>=0&&fstat(fd,&st)==0&&S_ISREG(st.st_mode),
         "TEST_OWNED_ORIGINAL_SEQ17_OPEN");
    a0_must(pread(fd,&b,1,168)==1,"LOAD_ORIGINAL_FBS1_HASH_BYTE");
    uint8_t corrupt=(uint8_t)(b^1u);
    a0_must(pwrite(fd,&corrupt,1,168)==1&&fsync(fd)==0,
         "INJECT_TAMPERED_ORIGINAL_ROW");
    memset(&candidate,0,sizeof(candidate));
    a0_reject(fe_t3b1ba0_bind(&candidate,s->fd,&s->source->config,
        s->source->ring.physical_to_slot,s->cap)!=0&&
        candidate.binding_complete==0u,"TAMPERED_ROW_NOT_REBOUND");
    a0_must(pwrite(fd,&b,1,168)==1&&fsync(fd)==0&&close(fd)==0,
         "RESTORE_ONLY_TEST_OWNED_BYTES");
    a0_rebind(s);
    a0_must(symlinkat(name,s->fd,"foreign-symlink") ==0,
         "CREATE_FOREIGN_SYMLINK_NEGATIVE");
    memset(&candidate,0,sizeof(candidate));
    a0_reject(fe_t3b1ba0_bind(&candidate,s->fd,&s->source->config,
        s->source->ring.physical_to_slot,s->cap)!=0,
        "SYMLINK_IN_OUTBOARD_DIR_REJECTED");
    a0_must(unlinkat(s->fd,"foreign-symlink",0)==0,
         "REMOVE_ONLY_TEST_OWNED_SYMLINK");
    a0_must(a0_find(s,16u,other)==0,"ORIGINAL_SEQ16_NAME_EXISTS");
    a0_must(snprintf(name,sizeof(name),"%s",other)>0,
         "SAVE_FULL_SEQ16_NAME");
    a0_must(renameat(s->fd,other,s->fd,".hidden-source") ==0,
        "INJECT_MISSING_SEQ16_AND_FOREIGN_NAME");
    memset(&candidate,0,sizeof(candidate));
    a0_reject(fe_t3b1ba0_bind(&candidate,s->fd,&s->source->config,
        s->source->ring.physical_to_slot,s->cap)!=0,
        "MISSING_MIDDLE_ORIGINAL_SOURCE_REJECTED");
    a0_must(renameat(s->fd,".hidden-source",s->fd,name)==0,
         "RESTORE_ONLY_TEST_OWNED_SEQ16");
    a0_rebind(s);
    fe_b1s0_config wrong=s->source->config;
    wrong.source_generation++;
    memset(&candidate,0,sizeof(candidate));
    a0_reject(fe_t3b1ba0_bind(&candidate,s->fd,&wrong,
         s->source->ring.physical_to_slot,s->cap)!=0,
         "ALIEN_GENERATION_REJECTED");
}
static void a0_capacity_nack(a0_stage *s) {
    fixture *f=s->source;
    uint8_t prior[32];
    fe_t3s1_drain_receipt ack;
    uint32_t tail=atomic_load_explicit(&f->ring.tail,memory_order_acquire);
    a0_must(fe_b1s1_sha256(s->store.last_row,200u,prior)==0,
         "EXACT_CAPACITY_BOUND_PRIOR");
    prepare(f,(uint64_t)s->cap+1u,1,prior);
    atomic_store_explicit(&f->ring.head,s->cap+1u,memory_order_release);
    memset(&ack,0xA5,sizeof(ack));
    a0_reject(fe_t3s1_drain_one(&f->ring,fe_t3b1ba0_outboard_sink,
         &s->store,&ack)==FE_T3S1_SINK_NOT_ADMITTED&&
         s->store.committed==s->cap&&
         atomic_load_explicit(&f->ring.tail,memory_order_acquire)==tail&&
         f->ring.drained_global_capture==s->cap,
         "CAPACITY_PLUS_ONE_REFUSED_WITH_NO_FALSE_S1_ACK");
    ++A0_BOUNDARY_NACKS;
}
static void a0_case(uint32_t scene,uint32_t hz,uint32_t render,uint32_t k) {
    a0_stage *s=(a0_stage *)calloc(1,sizeof(*s));
    a0_must(s!=NULL,"ALLOC_A0_PROFILE");
    a0_start(s,scene,RATES[hz],render,k,32u);
    for(uint64_t seq=1u;seq<=32u;++seq)
        a0_original_ack(s,seq);
    a0_inventory_all(s);
    a0_rebind(s);
    a0_negative_inventory(s);
    a0_capacity_nack(s);
    a0_clear_private(s);
    ++A0_PROFILES;free(s);
}
static void a0_fault_boundary(fe_t3b1ba0_fault fault) {
    a0_stage *s=(a0_stage *)calloc(1,sizeof(*s));
    uint8_t zero[32]={0};
    fe_t3b1ba0_owner recovered;
    fe_t3s1_drain_receipt ack,sentinel;
    a0_must(s!=NULL,"ALLOC_FAULT_PROFILE");
    a0_start(s,0u,RATES[0],0u,1u,17u);
    a0_must(fe_t3b1ba0_set_test_fault(&s->store,fault)==0,
            "HOST_ONLY_EXPLICIT_FAULT_BOUNDARY_ARMED");
    prepare(s->source,1u,0,zero);
    atomic_store_explicit(&s->source->ring.head,1u,memory_order_release);
    memset(&sentinel,0xA5,sizeof(sentinel));
    ack=sentinel;
    a0_reject(fe_t3s1_drain_one(&s->source->ring,
        fe_t3b1ba0_outboard_sink,&s->store,&ack)==
        FE_T3S1_SINK_NOT_ADMITTED&&
        memcmp(&ack,&sentinel,sizeof(ack))==0&&
        s->store.committed==0u&&
        s->source->ring.drained_global_capture==0u&&
        atomic_load_explicit(&s->source->ring.tail,
             memory_order_acquire)==0u,
        "HOST_FAULT_WITHHELD_EXACT_ORIGINAL_SOURCE_ACK");
    memset(&recovered,0,sizeof(recovered));
    int status=fe_t3b1ba0_bind(&recovered,s->fd,&s->source->config,
        s->source->ring.physical_to_slot,s->cap);
    if(fault==FE_T3B1BA0_FAULT_CREATE) {
        a0_reject(status==0&&recovered.committed==0u,
                  "CREATE_FAILED_NO_RECORDED_SOURCE_OR_ACK");
    } else if(fault<=FE_T3B1BA0_FAULT_UNLINK_TEMP) {
        a0_reject(status!=0&&recovered.binding_complete==0u,
                  "ORPHAN_OR_UNPUBLISHED_SOURCE_NOT_ADMITTED");
    } else {
        /* A later fully published byte sequence may be validated on host
         * restart, but S1 tail is NOT retrospectively acknowledged.
         * The missing directory barrier is NOT power-loss certification.
         */
        a0_reject(status==0&&recovered.committed==1u&&
             recovered.restart_recovered==1u,
             "HOST_BYTES_ONLY_NOT_S1_ACK_OR_POWERLOSS_CLAIM");
    }
    ++A0_FAULTS;
    a0_clear_private(s);
    free(s);
}
static void a0_name_negative(void) {
    char name[FE_T3B1BA0_NAME_CAP];
    uint8_t sha[32]={0};
    a0_reject(fe_t3b1ba0_name(1u,1u,0u,sha,sha,name)!=0,
              "GLOBAL_SEQUENCE_ZERO_DENIED");
    a0_reject(fe_t3b1ba0_name(1u,1u,33u,sha,sha,name)!=0,
              "GLOBAL_SEQUENCE_OVER_32_DENIED");
    a0_reject(fe_t3b1ba0_name(0u,1u,1u,sha,sha,name)!=0,
              "NO_SOURCE_CAPTURE_ID_DENIED");
}
int main(void) {
    a0_name_negative();
    for(unsigned fault=1u;fault<=8u;++fault)
        a0_fault_boundary((fe_t3b1ba0_fault)fault);
    for(uint32_t scene=0u;scene<4u;++scene)
        for(uint32_t hz=0u;hz<3u;++hz)
            for(uint32_t render=0u;render<2u;++render)
                for(uint32_t slots=1u;slots<=2u;++slots)
                    a0_case(scene,hz,render,slots);
    a0_must(A0_PROFILES==48u&&A0_ACKED==UINT64_C(1536)&&
            A0_FRAMES==UINT64_C(1536)&&
            A0_SOURCE_FILES==UINT64_C(1536)&&
            A0_BOUNDARY_NACKS==48u&&A0_RECOVERED>=96u&&
            A0_NEGATIVES>=216u&&A0_FAULTS==8u&&
            A0_SOURCE_BYTES>2000000u,
            "ORIGINAL_48_PROFILE_FINITE_32_FRAME_EVIDENCE_INCOMPLETE");
    printf("{\"decision\":\"FE09_B1B_A0_ORIGINAL_SEQ17_PLUS_FINITE_NONROLLING_OUTBOARD_HOSTED_ONLY\","
           "\"source_role\":\"first-party-synthetic\","
           "\"profiles\":%u,\"actual_original_apx3_frames\":%" PRIu64 ","
           "\"actually_acked_original_frames\":%" PRIu64 ","
           "\"bounded_original_source_files\":%" PRIu64 ","
           "\"global_17_to_32_continuity_verified\":true,"
           "\"capacity_plus_one_refused\":%u,\"negative_checks\":%u,"
           "\"restart_verified\":%" PRIu64 ","
           "\"host_faults_rejected\":%" PRIu64 ","
           "\"original_source_disk_bytes\":%" PRIu64 ","
           "\"real_rolling_retention_qualified\":false,"
           "\"original_source_deleted\":false,"
           "\"physical_powerloss_qualified\":false,"
           "\"ssc305_hardware_qualified\":false,"
           "\"whole_device_memory_qualified\":false,"
           "\"public_sdk_installed\":false}\n",
           A0_PROFILES,A0_FRAMES,A0_ACKED,A0_SOURCE_FILES,
           A0_BOUNDARY_NACKS,A0_NEGATIVES,A0_RECOVERED,A0_FAULTS,
           A0_SOURCE_BYTES);
    return 0;
}
