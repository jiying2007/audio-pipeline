/* #825: real original first-party writer/S1/A0 fixtures and an external
 * Python parent.  This executable never forks or execs itself.  Its crash
 * hook reports then blocks until the parent actually sends SIGKILL.
 * All mutation/cleanup below is test-only, inside the parent's owned ROOT.
 */
#define _POSIX_C_SOURCE 200809L
#define main historical_b0_main
#include "fe09_b2s3_t3s2b0_manifest_test.c"
#undef main
#include "fe09_b2s3_t3s2b1ba2_finite_retirement.h"
#include <dirent.h>
#include <errno.h>
#include <limits.h>
#include <signal.h>

#define A2_FILE_BYTES (FE_T3S1_ROW_BYTES+FE_T3S1_CHUNK_BYTES)
#define A2_PATH_BYTES 160u

typedef struct {
    uint32_t active,stop_point,negative_id;
    uint64_t events,unlinks,syncs,injected;
    uint8_t digest[32];
    fe_t3b1ba2_io_event last_injected;
} a2_audit;

typedef struct {
    fixture original;
    fe_t3b1ba0_owner source;
    fe_t3b1ba1_owner a1;
    fe_t3b1ba2_owner owner;
    fe_t3b1ba2_workspace workspace;
    fe_t3b1ba2_anchor anchor;
    a2_audit audit;
    int parent_fd,data_fd,a1_fd,control_fd,helper_fd;
    int saved_fd,replaced_fd;
    char root[A2_PATH_BYTES];
    char names[32][FE_T3B1BA0_NAME_CAP];
    char a1_name[FE_T3B1BA1_NAME_CAP],control_name[FE_T3B1BA2_NAME_CAP];
    uint8_t rows[32][FE_T3S1_ROW_BYTES];
    uint8_t frm[FE_T3B1BA1_ROOT_BYTES];
    uint8_t fpr[FE_T3B1BA2_CHECKPOINT_BYTES+1u];
    size_t fpr_bytes;
    uint32_t profile,scene,rate,render,k;
    uint32_t codec_ok,old_a0_rejected,old_a1_rejected;
    uint32_t observed_capture_flags,observed_render_flags;
    uint64_t observed_capture_fnv,observed_render_fnv;
    uint64_t source_calls;
} a2_fixture;

static uint8_t A2_BATCH_DIGEST[32];
static uint64_t A2_BATCH_EVENTS;

static void a2_must(int condition,const char *why) {
    if(!condition) {
        fprintf(stderr,"FE09_A2F0_NOT_ADMITTED reason=%s errno=%d\n",why,errno);
        exit(1);
    }
}
static uint32_t a2_u32(const uint8_t *p) {
    return (uint32_t)p[0]|(uint32_t)p[1]<<8u|
        (uint32_t)p[2]<<16u|(uint32_t)p[3]<<24u;
}
static uint64_t a2_u64(const uint8_t *p) {
    return (uint64_t)a2_u32(p)|((uint64_t)a2_u32(p+4u)<<32u);
}
static void a2_hash(const uint8_t *p,size_t n,uint8_t out[32]) {
    a2_must(fe_b1s1_sha256(p,n,out)==0,"TEST_SHA256");
}
static void a2_hex(const uint8_t h[32]) {
    for(unsigned i=0u;i<32u;++i)printf("%02x",(unsigned)h[i]);
}
static void a2_hex_string(const uint8_t h[32],char out[65]) {
    static const char hex[]="0123456789abcdef";
    for(unsigned i=0u;i<32u;++i) {
        out[i*2u]=hex[h[i]>>4u];out[i*2u+1u]=hex[h[i]&15u];
    }
    out[64]='\0';
}
static void a2_parse_hash(const char *s,uint8_t out[32]) {
    a2_must(strlen(s)==64u,"ANCHOR_HASH_LENGTH");
    for(unsigned i=0u;i<32u;++i) {
        unsigned v=0u;
        for(unsigned j=0u;j<2u;++j) {
            char c=s[2u*i+j];
            a2_must((c>='0'&&c<='9')||(c>='a'&&c<='f'),"ANCHOR_HASH_HEX");
            v=16u*v+(unsigned)(c<='9'?c-'0':c-'a'+10);
        }
        out[i]=(uint8_t)v;
    }
}
static uint64_t a2_number(const char *s) {
    char *end=NULL;
    a2_must(s[0]>='0'&&s[0]<='9',"ARGUMENT_UNSIGNED_DECIMAL");
    errno=0;unsigned long long v=strtoull(s,&end,10);
    a2_must(errno==0&&end!=s&&*end=='\0',"ARGUMENT_INTEGER_RANGE");
    return (uint64_t)v;
}
static void a2_wait(const char *command) {
    char line[512];
    a2_must(fflush(stdout)==0,"IPC_FLUSH");
    a2_must(fgets(line,sizeof(line),stdin)!=NULL&&strcmp(line,command)==0,
            "EXPLICIT_PARENT_COMMAND_REQUIRED");
}
static void a2_audit_digest(a2_audit *a,const fe_t3b1ba2_io_event *e) {
    uint8_t bytes[32u+18u*8u];
    uint64_t fields[18]={e->phase,e->operation,e->role,e->sequence,
        e->ordinal,e->matching_ordinal,e->requested_bytes,e->syscall_called,
        e->injected,e->fault_id,(uint64_t)e->actual_result,
        (uint64_t)e->reported_result,(uint64_t)e->actual_errno,
        (uint64_t)e->reported_errno,e->actual_device,e->observed_device,
        e->actual_uid,e->observed_uid};
    memcpy(bytes,a->digest,32u);
    for(unsigned i=0u;i<18u;++i)p64(bytes+32u+(size_t)i*8u,fields[i]);
    a2_hash(bytes,sizeof(bytes),a->digest);
    memcpy(bytes,A2_BATCH_DIGEST,32u);
    a2_hash(bytes,sizeof(bytes),A2_BATCH_DIGEST);
    ++a->events;++A2_BATCH_EVENTS;
}
static void a2_io_hook(const fe_t3b1ba2_io_event *e,void *context) {
    a2_audit *a=(a2_audit *)context;
    if(!a->active)return;
    a2_audit_digest(a,e);
    if(e->operation==FE_T3B1BA2_IO_UNLINK&&e->role==FE_T3B1BA2_ROLE_RECORD&&
       e->syscall_called&&e->actual_result==0)++a->unlinks;
    if(e->operation==FE_T3B1BA2_IO_FSYNC&&e->role==FE_T3B1BA2_ROLE_DATA_DIR&&
       e->syscall_called&&e->actual_result==0)++a->syncs;
    if(e->injected) {
        ++a->injected;a->last_injected=*e;
        printf("{\"e\":\"inj\",\"v\":[%u,%u,%u,%u,%" PRIu64 ",%" PRIu64
            ",%" PRIu64 ",%u,%u,%" PRId64 ",%" PRId64 ",%d,%d,%" PRIu64
            ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 "]}\n",
            e->phase,e->operation,e->role,e->sequence,e->ordinal,
            e->matching_ordinal,e->requested_bytes,e->syscall_called,e->fault_id,
            e->actual_result,e->reported_result,e->actual_errno,e->reported_errno,
            e->actual_device,e->observed_device,e->actual_uid,e->observed_uid);
    }
    if(e->operation==FE_T3B1BA2_IO_FSYNC||
       (e->operation==FE_T3B1BA2_IO_UNLINK&&e->role==FE_T3B1BA2_ROLE_RECORD)) {
        printf("{\"e\":\"io\",\"v\":[%u,%u,%u,%u,%u,%" PRId64 ",%" PRId64 "]}\n",
            e->phase,e->operation,e->role,e->sequence,e->syscall_called,
            e->actual_result,e->reported_result);
    }
}
static void a2_barrier(uint32_t point,void *context) {
    a2_audit *a=(a2_audit *)context;
    if(!a->active)return;
    a2_must(point>=1u&&point<=57u,"REGISTERED_BARRIER_RANGE");
    printf("{\"e\":\"p\",\"p\":%u}\n",point);
    a2_must(fflush(stdout)==0,"BARRIER_FLUSH");
    if(point==a->stop_point)for(;;)(void)pause();
}
static fe_t3b1ba2_hooks a2_hooks(a2_audit *a) {
    fe_t3b1ba2_hooks h;
    h.io=a2_io_hook;h.barrier=a2_barrier;h.context=a;return h;
}
static int a2_directory(int parent,const char *name,int create) {
    if(create)a2_must(mkdirat(parent,name,0700)==0,"OWNED_FIXTURE_MKDIR");
    int fd=openat(parent,name,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    struct stat st;
    a2_must(fd>=0&&fstat(fd,&st)==0&&S_ISDIR(st.st_mode)&&
        st.st_uid==geteuid()&&(st.st_mode&0777)==0700,"OWNED_FIXTURE_DIRECTORY");
    return fd;
}
static int a2_root_open(const char *root) {
    a2_must(strlen(root)<A2_PATH_BYTES&&strncmp(root,"/tmp/",5u)==0,
            "SHORT_OWNED_TEMPORARY_ROOT");
    int fd=open(root,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    struct stat st;
    a2_must(fd>=0&&fstat(fd,&st)==0&&st.st_uid==geteuid()&&
        (st.st_mode&0777)==0700,"PARENT_OWNED_ROOT");return fd;
}
static size_t a2_read_file(int dirfd,const char *name,uint8_t *out,size_t cap) {
    int fd=openat(dirfd,name,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    struct stat st;
    a2_must(fd>=0&&fstat(fd,&st)==0&&S_ISREG(st.st_mode)&&st.st_size>=0&&
        (uint64_t)st.st_size<=(uint64_t)cap,"FIXTURE_READ_OPEN");
    size_t n=(size_t)st.st_size,done=0u;
    while(done<n) {
        ssize_t got=read(fd,out+done,n-done);
        if(got<0&&errno==EINTR)continue;
        a2_must(got>0,"FIXTURE_READ_COMPLETE");done+=(size_t)got;
    }
    a2_must(close(fd)==0,"FIXTURE_READ_CLOSE");return n;
}
static void a2_write_file(int dirfd,const char *name,const uint8_t *data,
                          size_t n,int create) {
    int fd=openat(dirfd,name,O_WRONLY|O_NOFOLLOW|O_CLOEXEC|
        (create?(O_CREAT|O_EXCL):O_TRUNC),0600);
    a2_must(fd>=0,"FIXTURE_WRITE_OPEN");
    size_t done=0u;
    while(done<n) {
        ssize_t wrote=write(fd,data+done,n-done);
        if(wrote<0&&errno==EINTR)continue;
        a2_must(wrote>0,"FIXTURE_WRITE_COMPLETE");done+=(size_t)wrote;
    }
    a2_must(close(fd)==0,"FIXTURE_WRITE_CLOSE");
}
static void a2_cleanup_dir(int fd) {
    int copy=openat(fd,".",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    a2_must(copy>=0,"CLEANUP_DIRECTORY_FD");
    DIR *dir=fdopendir(copy);a2_must(dir!=NULL,"CLEANUP_DIRECTORY_STREAM");
    struct dirent *entry;
    while((entry=readdir(dir))!=NULL) {
        if(!strcmp(entry->d_name,".")||!strcmp(entry->d_name,".."))continue;
        struct stat st;
        a2_must(fstatat(fd,entry->d_name,&st,AT_SYMLINK_NOFOLLOW)==0,
                "CLEANUP_OBSERVABLE_ENTRY");
        a2_must(unlinkat(fd,entry->d_name,S_ISDIR(st.st_mode)?AT_REMOVEDIR:0)==0,
                "TEST_ONLY_CLEANUP_AFTER_PARENT_OBSERVATION");
    }
    a2_must(closedir(dir)==0,"CLEANUP_STREAM_CLOSE");
}
static void a2_owner_witness(const a2_fixture *f,uint64_t out[3]) {
    out[0]=atomic_load_explicit(&f->original.ring.head,memory_order_acquire);
    out[1]=atomic_load_explicit(&f->original.ring.tail,memory_order_acquire);
    out[2]=f->source.committed;
}
static void a2_print_owner(const uint64_t o[3]) {
    printf("[%" PRIu64 ",%" PRIu64 ",%" PRIu64 "]",o[0],o[1],o[2]);
}
static void a2_same_owner(const a2_fixture *f,const uint64_t before[3]) {
    uint64_t after[3];a2_owner_witness(f,after);
    a2_must(memcmp(before,after,sizeof(after))==0&&
        f->original.storage_owner.committed==0u&&f->original.index.count==0u,
        "NO_NEW_ORIGINAL_ACK_OR_PRODUCER_PROGRESS");
}
static void a2_setup(a2_fixture *f,const char *root,uint32_t profile) {
    memset(f,0,sizeof(*f));f->saved_fd=-1;f->replaced_fd=-1;
    a2_must(profile<48u,"REGISTERED_PROFILE");f->profile=profile;
    uint32_t q=profile;f->k=q%2u+1u;q/=2u;f->render=q%2u;q/=2u;
    f->rate=RATES[q%3u];f->scene=q/3u;
    a2_must(strlen(root)<sizeof(f->root),"ROOT_PATH_BOUND");strcpy(f->root,root);
    f->parent_fd=a2_root_open(root);
    f->data_fd=a2_directory(f->parent_fd,"data",1);
    f->a1_fd=a2_directory(f->parent_fd,"a1",1);
    f->control_fd=a2_directory(f->parent_fd,"control",1);
    f->helper_fd=a2_directory(f->parent_fd,"helper",1);
    fixture *o=&f->original;
    o->fd=a2_directory(f->parent_fd,"legacy",1);o->k=f->k;o->cap=32u;
    o->config.depth=f->k==1u?2u:4u;o->config.physical_mics=MICS[f->scene];
    o->config.input_hz=f->rate;o->config.render_enabled=f->render;
    o->config.capture_source_id=301u+MICS[f->scene];
    o->config.render_source_id=f->render?401u+MICS[f->scene]:0u;
    o->config.source_generation=UINT64_C(1234509876);
    a2_must(fe_t3s2a_bind(&o->storage_owner,o->fd,&o->config,MAPS[f->scene],16u)==0&&
        fe_t3s2b0_bind(&o->index,&o->storage_owner,16u)==0,"ORIGINAL_EMPTY_S2A_B0_BIND");
    o->slots=(fe_t3s1_slot *)calloc(f->k,sizeof(*o->slots));
    a2_must(o->slots!=NULL,"ORIGINAL_BOUNDED_PHYSICAL_SLOTS");
    o->ring.pinned_cfg=o->config;o->ring.pinned_sink=fe_t3b1ba0_outboard_sink;
    o->ring.pinned_sink_context=&f->source;o->ring.slot=o->slots;
    o->ring.slot_count=f->k;o->ring.slot_allocation_bytes=(size_t)f->k*sizeof(*o->slots);
    memcpy(o->ring.physical_to_slot,MAPS[f->scene],sizeof(o->ring.physical_to_slot));
    atomic_init(&o->ring.head,0u);atomic_init(&o->ring.tail,0u);
    a2_must(fe_t3b1ba0_bind(&f->source,f->data_fd,&o->config,MAPS[f->scene],32u)==0,
            "ORIGINAL_REAL_A0_BIND");
    for(uint64_t seq=1u;seq<=32u;++seq) {
        uint8_t prior[32]={0},hash[32];
        if(seq>1u)a2_hash(f->source.last_row,FE_T3S1_ROW_BYTES,prior);
        prepare(o,seq,(int)(seq&1u),prior);++f->source_calls;
        fe_t3s1_slot *slot=&o->slots[(seq-1u)%(uint64_t)f->k];
        fe_t3s1_drain_receipt receipt;
        atomic_store_explicit(&o->ring.head,(unsigned)seq,memory_order_release);
        a2_must(fe_t3s1_drain_one(&o->ring,fe_t3b1ba0_outboard_sink,&f->source,&receipt)==
            FE_T3S1_OK&&receipt.source_sequence==seq&&
            receipt.actually_accounted_bytes==FE_T3S1_ROW_BYTES+slot->apx3_bytes&&
            f->source.committed==seq,"REAL_ORIGINAL_S1_A0_ACK");
        ++f->source_calls;
        memcpy(f->rows[seq-1u],f->source.last_row,FE_T3S1_ROW_BYTES);
        a2_hash(f->source.last_row,FE_T3S1_ROW_BYTES,hash);
        a2_must(fe_t3b1ba0_name(o->config.capture_source_id,o->config.source_generation,
            seq,hash,f->source.last_row+104u,f->names[seq-1u])==0,"ORIGINAL_CANONICAL_FILENAME");
    }
    fe_t3b1ba1_receipt receipt;
    a2_must(fe_t3b1ba1_bind(&f->a1,f->a1_fd,&f->source)==0&&
        fe_t3b1ba1_publish(&f->a1,&receipt)==0&&receipt.hosted_checkpoint_committed==1u&&
        fe_t3b1ba1_encode(&f->a1,f->frm)==0&&fe_t3b1ba1_name(f->frm,f->a1_name)==0,
        "REAL_P0_BOUND_ORIGINAL_A1");
    fe_t3b1ba2_hooks hooks=a2_hooks(&f->audit);
    a2_must(fe_t3b1ba2_init(&f->owner,f->data_fd,f->a1_fd,f->control_fd,
        &f->workspace,&hooks)==0,"A2_INITIALIZE");
}
static fe_t3b1ba2_request a2_request(const a2_fixture *f) {
    fe_t3b1ba2_request r;
    memset(&r,0,sizeof(r));r.quiescent=1u;
    r.source_head=atomic_load_explicit(&f->original.ring.head,memory_order_acquire);
    r.source_tail=atomic_load_explicit(&f->original.ring.tail,memory_order_acquire);
    r.requested_sequence=32u;r.requested_first=17u;r.requested_last=32u;r.requested_high_water=32u;
    r.requested_generation=f->source.source.source_generation;
    r.requested_retired_count=16u;r.requested_retained_count=16u;return r;
}
static void a2_prepare(a2_fixture *f) {
    fe_t3b1ba2_request r=a2_request(f);
    a2_must(fe_t3b1ba2_prepare(&f->owner,&f->source,&f->a1,&r,&f->anchor)==0,
            "FULL_ORIGINAL_P0_ADMISSION");
    const uint8_t *bytes=fe_t3b1ba2_prepared_bytes(&f->owner);
    a2_must(bytes!=NULL,"PREPARED_METADATA_ONLY_BYTES");
    memcpy(f->fpr,bytes,FE_T3B1BA2_CHECKPOINT_BYTES);
    f->fpr_bytes=FE_T3B1BA2_CHECKPOINT_BYTES;
    a2_must(fe_t3b1ba2_name(f->fpr,f->control_name)==0,"FPR1_CANONICAL_NAME");
}
static void a2_publish_setup(a2_fixture *f) {
    fe_t3b1ba2_receipt r;
    a2_must(fe_t3b1ba2_acknowledge(&f->owner,&f->anchor)==0&&
        fe_t3b1ba2_publish(&f->owner,&f->anchor,&r)==0,"LEGAL_CONTROL_FIXTURE_PUBLICATION");
}
static void a2_cleanup(a2_fixture *f) {
    if(f->saved_fd>=0) {
        a2_must(dup2(f->saved_fd,f->replaced_fd)==f->replaced_fd&&close(f->saved_fd)==0,
                "RESTORE_TEST_DESCRIPTOR_ONLY_AFTER_PARENT_OBSERVATION");
        f->saved_fd=-1;
    }
    int fds[]={f->data_fd,f->a1_fd,f->control_fd,f->original.fd,f->helper_fd};
    const char *names[]={"data","a1","control","legacy","helper"};
    for(unsigned i=0u;i<5u;++i) {
        a2_cleanup_dir(fds[i]);a2_must(close(fds[i])==0&&
            unlinkat(f->parent_fd,names[i],AT_REMOVEDIR)==0,"TEST_OWNED_SUBDIRECTORY_CLEANUP");
    }
    a2_must(close(f->parent_fd)==0,"TEST_PARENT_FD_CLOSE");
    free(f->original.slots);f->original.slots=NULL;
}
static void a2_close_live_fixture(a2_fixture *f) {
    int fds[]={f->data_fd,f->a1_fd,f->control_fd,f->original.fd,f->helper_fd,f->parent_fd};
    for(unsigned i=0u;i<6u;++i)a2_must(close(fds[i])==0,"TRANSACTION_CLOSE_NOT_CLEANUP");
    free(f->original.slots);f->original.slots=NULL;
}
static void a2_anchor_line(const fe_t3b1ba2_anchor *a,char line[512]) {
    char hash[65];a2_hex_string(a->checkpoint_raw_sha256,hash);
    int n=snprintf(line,512u,"ACK %u %" PRIu64 " %" PRIu64 " %" PRIu64
        " %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64 " %s\n",
        a->capture_source_id,a->source_generation,a->device[0],a->inode[0],
        a->device[1],a->inode[1],a->device[2],a->inode[2],hash);
    a2_must(n>0&&n<512,"CANONICAL_ANCHOR_CONFIRMATION");
}
static void a2_resource_layout(void) {
    printf("[%zu,%zu,%zu,%zu,%u,%u]",sizeof(fe_t3b1ba2_workspace),
        fe_t3b1ba2_workspace_used_bytes(),sizeof(fe_t3b1ba2_owner),
        sizeof(fe_t3b1ba2_receipt),FE_T3B1BA2_LOCAL_STACK_RESERVE,
        FE_T3B1BA2_READONLY_RESERVE);
}
static void a2_fixture_layout(void) {
    printf("[%zu,%zu,%zu,%zu]",sizeof(a2_fixture),sizeof(fixture),
        sizeof(fe_t3b1ba0_owner),sizeof(fe_t3b1ba1_owner));
}
static void a2_emit_anchor(const a2_fixture *f) {
    const fe_t3b1ba2_anchor *a=&f->anchor;uint64_t o[3];a2_owner_witness(f,o);
    printf("{\"e\":\"anchor\",\"a\":[%u,%" PRIu64 ",%" PRIu64 ",%" PRIu64
        ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 "],\"h\":\"",
        a->capture_source_id,a->source_generation,a->device[0],a->inode[0],
        a->device[1],a->inode[1],a->device[2],a->inode[2]);
    a2_hex(a->checkpoint_raw_sha256);printf("\",\"o\":");a2_print_owner(o);
    printf(",\"r\":");a2_resource_layout();
    printf(",\"z\":");a2_fixture_layout();puts("}");
}
static void a2_result(const char *event,int rc,const char *error,
    const fe_t3b1ba2_receipt *r,const a2_audit *audit,
    const uint64_t *original,const uint32_t rebound[4],const int parent_reset[2]) {
    const char *c=error;
    printf("{\"e\":\"%s\",\"rc\":%d,\"c\":\"%s\",\"k\":",event,rc,c?c:"OK");
    if(r->missing_prefix_known)printf("%u",r->missing_prefix);else printf("null");
    printf(",\"u\":%u,\"commit\":%s,\"o\":",r->new_data_unlinks,
        r->hosted_retirement_committed?"true":"false");
    if(original)a2_print_owner(original);else printf("null");
    printf(",\"f\":%s,\"m\":%zu,\"io\":[%" PRIu64 ",%" PRIu64 ",%" PRIu64
        ",%" PRIu64 "],\"d\":\"",original?"null":"[0,0,0,0,0]",fe_t3b1ba2_resource_bytes(),
        audit->events,audit->unlinks,audit->syncs,audit->injected);
    a2_hex(audit->digest);
    printf("\",\"v\":[%u,%u,%u,%u],\"b\":[%" PRIu64 ",%" PRIu64 "],\"h\":\"",
        r->retained_files_verified,r->remaining_retired_files_verified,
        r->checkpoint_visible_verified,r->source_ack_proven,
        r->original_logical_bytes,r->retained_logical_bytes);
    a2_hex(r->checkpoint_raw_sha256);printf("\",\"cf\":[");
    for(unsigned i=0u;i<16u;++i)printf("%s%" PRIu64,i?",":"",r->retained_capture_fnv[i]);
    printf("],\"rf\":[");
    for(unsigned i=0u;i<16u;++i)printf("%s%" PRIu64,i?",":"",r->retained_render_fnv[i]);
    putchar(']');
    if(!strcmp(event,"td"))printf(",\"old\":[1,1]");
    if(rebound)printf(",\"rb\":[%u,%u,%u,%u]",rebound[0],rebound[1],rebound[2],rebound[3]);
    if(parent_reset)printf(",\"pc\":[%d,%d]",parent_reset[0],parent_reset[1]);
    puts("}");a2_must(fflush(stdout)==0,"RESULT_FLUSH");
}
static int a2_transaction(const char *root,uint32_t profile,uint32_t stop) {
    a2_fixture *f=(a2_fixture *)calloc(1u,sizeof(*f));
    a2_must(f!=NULL,"BOUNDED_TRANSACTION_FIXTURE");a2_setup(f,root,profile);a2_prepare(f);
    uint64_t before[3],after[3];a2_owner_witness(f,before);
    a2_must(before[0]==32u&&before[1]==32u&&before[2]==32u,"LIVE_ORIGINAL_STOPPED_AT32");
    a2_emit_anchor(f);char ack[512];a2_anchor_line(&f->anchor,ack);a2_wait(ack);
    f->audit.active=1u;f->audit.stop_point=stop;
    a2_must(fe_t3b1ba2_acknowledge(&f->owner,&f->anchor)==0,"PARENT_FIXED_ANCHOR_ACK");
    fe_t3b1ba2_receipt r;memset(&r,0,sizeof(r));
    a2_must(fe_t3b1ba2_publish(&f->owner,&f->anchor,&r)==0,"REAL_FPR1_PUBLICATION");
    int rc=fe_t3b1ba2_resume(&f->owner,&f->anchor,&r);
    a2_same_owner(f,before);a2_owner_witness(f,after);
    a2_must(rc==0&&r.missing_prefix_known&&r.missing_prefix==16u&&
        r.new_data_unlinks==16u&&r.hosted_retirement_committed&&r.source_ack_proven==0u&&
        f->audit.unlinks==16u,"NORMAL_REAL_FINITE_RETIREMENT");
    fe_t3b1ba0_owner old_reopen;fe_t3b1ba1_receipt old_receipt;
    f->old_a0_rejected=(uint32_t)(fe_t3b1ba0_bind(&old_reopen,f->source.dirfd,
        &f->source.source,f->source.slots,f->source.cap)!=0);
    f->old_a1_rejected=(uint32_t)(fe_t3b1ba1_read(&f->a1,&old_receipt)!=0);
    a2_must(f->old_a0_rejected&&f->old_a1_rejected,"ACTUAL_P0_BOUND_OLD_READERS_STILL_REJECT_MISSING_PREFIX");
    printf("{\"e\":\"old\",\"a0\":%u,\"a1\":%u,\"pre\":",f->old_a0_rejected,f->old_a1_rejected);
    a2_print_owner(before);printf(",\"post\":");a2_print_owner(after);puts("}");
    a2_result("td",rc,fe_t3b1ba2_error(&f->owner),&r,&f->audit,after,NULL,NULL);
    a2_close_live_fixture(f);memset(f,0,sizeof(*f));free(f);return 0;
}
static int a2_recovery(const char *root,const fe_t3b1ba2_anchor *anchor) {
    fe_t3b1ba2_workspace *workspace=(fe_t3b1ba2_workspace *)calloc(1u,sizeof(*workspace));
    a2_must(workspace!=NULL,"BOUNDED_FRESH_RECOVERY_WORKSPACE");
    fe_t3b1ba2_owner owner;fe_t3b1ba2_receipt r;a2_audit audit;
    memset(&owner,0,sizeof(owner));memset(&audit,0,sizeof(audit));audit.active=1u;
    fe_t3b1ba2_hooks hooks=a2_hooks(&audit);
    int parent=a2_root_open(root);
    int data=a2_directory(parent,"data",0),a1=a2_directory(parent,"a1",0),control=a2_directory(parent,"control",0);
    a2_must(fe_t3b1ba2_init(&owner,data,a1,control,workspace,&hooks)==0,"FRESH_READ_INIT");
    memset(&r,0,sizeof(r));int rc=fe_t3b1ba2_bind(&owner,anchor);
    if(rc==0)rc=fe_t3b1ba2_read(&owner,anchor,&r);
    a2_must(audit.unlinks==0u&&r.new_data_unlinks==0u&&
        !r.hosted_checkpoint_committed&&!r.hosted_retirement_committed&&
        r.source_ack_proven==0u&&!r.live_source_observation,"FRESH_READ_HAS_NO_ACK_OWNER_OR_COMMIT");
    a2_result("rd",rc,fe_t3b1ba2_error(&owner),&r,&audit,NULL,NULL,NULL);
    a2_wait("RESUME\n");
    uint32_t rebound[4]={0u,0u,0u,0u};
    int read_fds[]={data,a1,control};
    for(unsigned i=0u;i<3u;++i) {
        a2_must(close(read_fds[i])==0,"CLOSE_ALL_READ_PHASE_DIRECTORY_FDS");++rebound[0];
    }
    int parent_reset[2]={close(parent),0};
    a2_must(parent_reset[0]==0,"CLOSE_READ_PHASE_ROOT_DIRECTORY_FD");parent=-1;
    memset(&owner,0,sizeof(owner));memset(workspace,0,sizeof(*workspace));
    const uint8_t *owner_bytes=(const uint8_t *)&owner;
    rebound[1]=1u;rebound[2]=1u;
    for(size_t i=0u;i<sizeof(owner);++i)if(owner_bytes[i])rebound[1]=0u;
    for(size_t i=0u;i<sizeof(*workspace);++i)if(workspace->bytes[i])rebound[2]=0u;
    a2_must(rebound[1]&&rebound[2],"READ_OWNER_AND_WORKSPACE_ACTUALLY_CLEARED");
    memset(&r,0,sizeof(r));memset(&audit,0,sizeof(audit));audit.active=1u;
    parent=a2_root_open(root);parent_reset[1]=parent>=0;
    data=a2_directory(parent,"data",0);a1=a2_directory(parent,"a1",0);control=a2_directory(parent,"control",0);
    a2_must(fe_t3b1ba2_init(&owner,data,a1,control,workspace,&hooks)==0,"FRESH_RESUME_REINITIALIZE");
    ++rebound[3];rc=fe_t3b1ba2_bind(&owner,anchor);
    if(rc==0)rc=fe_t3b1ba2_resume(&owner,anchor,&r);
    a2_must(r.source_ack_proven==0u&&!r.live_source_observation&&
        r.new_data_unlinks==audit.unlinks,"FRESH_RESUME_HAS_NO_ORIGINAL_ACK_AUTHORITY");
    a2_result("rs",rc,fe_t3b1ba2_error(&owner),&r,&audit,NULL,rebound,parent_reset);
    a2_must(close(data)==0&&close(a1)==0&&close(control)==0&&close(parent)==0,"FRESH_RECOVERY_CLOSE");
    memset(&owner,0,sizeof(owner));memset(workspace,0,sizeof(*workspace));free(workspace);return 0;
}

typedef struct {
    uint32_t seen,capture_flags,render_flags;
    uint64_t capture_fnv,render_fnv;
} a2_codec_visit;
static uint64_t a2_fnv_le(const uint8_t *p,size_t bytes) {
    if(!p)return 0u;
    uint64_t value=UINT64_C(14695981039346656037);
    for(size_t i=0u;i<bytes;++i)value=(value^p[i])*UINT64_C(1099511628211);
    return value;
}
static int a2_permissive_visit(const fe_s2_stream *stream,uint32_t index,
    uint64_t sequence,uint32_t capture_flags,uint32_t render_flags,
    const uint8_t *capture,size_t capture_bytes,const uint8_t *render,
    size_t render_bytes,void *context) {
    a2_codec_visit *v=(a2_codec_visit *)context;
    a2_must(stream!=NULL&&index==0u&&sequence==1u&&capture!=NULL&&capture_bytes>0u&&
        ((render==NULL&&render_bytes==0u)||(render!=NULL&&render_bytes>0u)),
        "PERMISSIVE_ORIGINAL_CODEC_RECORDING_VISITOR");
    ++v->seen;v->capture_flags=capture_flags;v->render_flags=render_flags;
    v->capture_fnv=a2_fnv_le(capture,capture_bytes);
    v->render_fnv=a2_fnv_le(render,render_bytes);return 0;
}
static void a2_codec_ok(a2_fixture *f,uint32_t sequence) {
    uint8_t file[A2_FILE_BYTES];a2_codec_visit v;fe_s2_stream decoded;
    size_t n=a2_read_file(f->data_fd,f->names[sequence-1u],file,sizeof(file));
    a2_must(n>FE_T3S1_ROW_BYTES,"ORIGINAL_APX3_PRESENT");memset(&v,0,sizeof(v));
    a2_must(fe_s2_decode(file+FE_T3S1_ROW_BYTES,n-FE_T3S1_ROW_BYTES,&decoded)==FE_S2_OK&&
        fe_s2_replay(file+FE_T3S1_ROW_BYTES,n-FE_T3S1_ROW_BYTES,
            a2_permissive_visit,&v,&decoded)==FE_S2_OK&&v.seen==1u,
        "ORIGINAL_CODEC_ACCEPTS_CONTROLLED_MUTANT");
    f->codec_ok=1u;f->observed_capture_flags=v.capture_flags;
    f->observed_render_flags=v.render_flags;
    f->observed_capture_fnv=v.capture_fnv;f->observed_render_fnv=v.render_fnv;
}
/* Original writer is the only CRC/format authority.  The deterministic
 * original feeder regenerates this still-present record in bounded scratch;
 * no retired PCM is kept for recovery, and no alternate codec is linked.
 */
static void a2_reencode(a2_fixture *f,uint32_t sequence,uint32_t sample_xor,
    uint32_t capture_flags,uint32_t render_flags,uint32_t repair_apx_digest) {
    uint8_t file[A2_FILE_BYTES],prior[32]={0};
    size_t n=a2_read_file(f->data_fd,f->names[sequence-1u],file,sizeof(file));
    if(sequence>1u)a2_hash(f->rows[sequence-2u],FE_T3S1_ROW_BYTES,prior);
    prepare(&f->original,sequence,(int)(sequence&1u),prior);
    fe_s2_stream original;
    a2_must(fe_s2_decode(file+FE_T3S1_ROW_BYTES,n-FE_T3S1_ROW_BYTES,&original)==FE_S2_OK,
            "MUTATOR_STARTS_FROM_REAL_ORIGINAL_CODEC");
    if(sample_xor)f->original.capture[0]=(int16_t)((uint16_t)f->original.capture[0]^1u);
    fe_s2_frame frame;memset(&frame,0,sizeof(frame));
    frame.sequence=1u;frame.capture_flags=capture_flags;frame.render_flags=render_flags;
    frame.capture_epoch=capture_flags?2u:1u;
    frame.render_epoch=original.config.render_channels?(render_flags?2u:1u):0u;
    frame.capture=f->original.capture;
    frame.capture_count=(size_t)f->rate*f->original.config.physical_mics/100u;
    frame.render=original.config.render_channels?f->original.render:NULL;
    frame.render_count=original.config.render_channels?(size_t)f->rate/100u:0u;
    fe_s2_writer writer;size_t written=0u;
    a2_must(fe_s2_writer_begin(&writer,file+FE_T3S1_ROW_BYTES,
        sizeof(file)-FE_T3S1_ROW_BYTES,&original.config,1u)==FE_S2_OK&&
        fe_s2_writer_append(&writer,&frame)==FE_S2_OK&&
        fe_s2_writer_finish(&writer,&written)==FE_S2_OK&&
        written==n-FE_T3S1_ROW_BYTES,"MUTATION_USES_FROZEN_WRITER_AND_CRC");
    if(repair_apx_digest) {
        a2_hash(file+FE_T3S1_ROW_BYTES,written,f->rows[sequence-1u]+104u);
        memcpy(file,f->rows[sequence-1u],FE_T3S1_ROW_BYTES);
    }
    a2_write_file(f->data_fd,f->names[sequence-1u],file,n,0);
    a2_codec_ok(f,sequence);
    memset(file,0,sizeof(file));
}
static void a2_test_control_name(const a2_fixture *f,char out[FE_T3B1BA2_NAME_CAP]) {
    char self[65];a2_hex_string(f->fpr+FE_T3B1BA2_SELF_OFFSET,self);
    int n=snprintf(out,FE_T3B1BA2_NAME_CAP,"fpr1-%08" PRIx32 "-%016" PRIx64 "-%s.bin",
        f->source.source.capture_source_id,f->source.source.source_generation,self);
    a2_must(n==99,"EXACT_TEST_CANONICAL_FPR1_NAME");
}
static void a2_reseal_control(a2_fixture *f,uint32_t repair_self,uint32_t repair_anchor) {
    if(repair_self) {
        memset(f->fpr+FE_T3B1BA2_SELF_OFFSET,0,32u);
        a2_hash(f->fpr,f->fpr_bytes,f->fpr+FE_T3B1BA2_SELF_OFFSET);
    }
    char name[FE_T3B1BA2_NAME_CAP];a2_test_control_name(f,name);
    a2_must(unlinkat(f->control_fd,f->control_name,0)==0,"TEST_RESEAL_CONTROL_OLD_NAME");
    a2_write_file(f->control_fd,name,f->fpr,f->fpr_bytes,1);strcpy(f->control_name,name);
    if(repair_anchor)a2_hash(f->fpr,f->fpr_bytes,f->anchor.checkpoint_raw_sha256);
}
static void a2_reseal_chain(a2_fixture *f,uint32_t negative_id) {
    uint8_t prior[32]={0},hash[32],file[A2_FILE_BYTES];
    uint64_t original_bytes=0u,retained_bytes=0u;
    for(uint32_t sequence=1u;sequence<=32u;++sequence) {
        uint8_t *row=f->rows[sequence-1u];
        size_t n=a2_read_file(f->data_fd,f->names[sequence-1u],file,sizeof(file));
        if(!(negative_id==103u&&sequence==1u)&&!(negative_id==101u&&sequence==32u))
            memcpy(row+136u,prior,32u);
        if(!(negative_id==102u&&sequence==32u))a2_hash(row,168u,row+168u);
        a2_hash(row,FE_T3S1_ROW_BYTES,hash);
        char name[FE_T3B1BA0_NAME_CAP];
        a2_must(fe_t3b1ba0_name(f->source.source.capture_source_id,
            f->source.source.source_generation,sequence,hash,row+104u,name)==0,
            "RESEAL_USES_ORIGINAL_RECORD_NAMER");
        if(strcmp(name,f->names[sequence-1u])) {
            struct stat st;errno=0;
            a2_must(fstatat(f->data_fd,name,&st,AT_SYMLINK_NOFOLLOW)!=0&&errno==ENOENT&&
                renameat(f->data_fd,f->names[sequence-1u],f->data_fd,name)==0,
                "TEST_RESEAL_RENAME_WITHOUT_PCM_BACKUP");
            strcpy(f->names[sequence-1u],name);
        }
        if(memcmp(file,row,FE_T3S1_ROW_BYTES)) {
            memcpy(file,row,FE_T3S1_ROW_BYTES);
            a2_write_file(f->data_fd,name,file,n,0);
        }
        memcpy(prior,hash,32u);original_bytes+=(uint64_t)n;
        if(sequence>=17u) {
            retained_bytes+=(uint64_t)n;
            uint8_t *member=f->frm+224u+(size_t)(sequence-17u)*72u;
            p64(member,sequence);memcpy(member+8u,hash,32u);memcpy(member+40u,row+104u,32u);
        }
        if(sequence==16u)memcpy(f->frm+96u,hash,32u);
    }
    memcpy(f->frm+128u,prior,32u);memset(f->frm+160u,0,32u);
    a2_hash(f->frm,sizeof(f->frm),f->frm+160u);
    char root_name[FE_T3B1BA1_NAME_CAP];
    a2_must(fe_t3b1ba1_name(f->frm,root_name)==0,"RESEALED_ORIGINAL_FRM2_NAME");
    a2_must(unlinkat(f->a1_fd,f->a1_name,0)==0,"TEST_RESEAL_FRM2_OLD_NAME");
    a2_write_file(f->a1_fd,root_name,f->frm,sizeof(f->frm),1);strcpy(f->a1_name,root_name);
    memcpy(f->fpr+192u,f->frm,sizeof(f->frm));
    a2_hash(f->frm,sizeof(f->frm),f->fpr+88u);
    memcpy(f->fpr+FE_T3B1BA2_RETIRED_OFFSET,f->rows,16u*FE_T3S1_ROW_BYTES);
    p64(f->fpr+152u,original_bytes);p64(f->fpr+160u,retained_bytes);
    p64(f->fpr+168u,original_bytes-retained_bytes);
    a2_reseal_control(f,1u,1u);memset(file,0,sizeof(file));
}
static void a2_new_owner(a2_fixture *f) {
    memset(&f->owner,0,sizeof(f->owner));memset(&f->workspace,0,sizeof(f->workspace));
    fe_t3b1ba2_hooks hooks=a2_hooks(&f->audit);
    a2_must(fe_t3b1ba2_init(&f->owner,f->data_fd,f->a1_fd,f->control_fd,
        &f->workspace,&hooks)==0,"INDEPENDENT_NEGATIVE_OWNER_INIT");
}
static uint32_t a2_initial_k(uint32_t n) {
    return ((n>=57u&&n<=88u)||(n>=105u&&n<=120u)||
            (n>=134u&&n<=144u)||n==153u)?8u:0u;
}
static uint32_t a2_empty_control(uint32_t n) {
    return (n>=25u&&n<=56u)||(n>=121u&&n<=128u)||(n>=145u&&n<=152u);
}
static void a2_retire_fixture_prefix(a2_fixture *f,uint32_t k) {
    for(uint32_t sequence=1u;sequence<=k;++sequence)
        a2_must(unlinkat(f->data_fd,f->names[sequence-1u],0)==0,
                "TEST_INITIAL_PREFIX_REMOVAL_WITHOUT_BACKUP");
    if(k)a2_must(fsync(f->data_fd)==0,"TEST_INITIAL_PREFIX_DIRECTORY_SYNC");
}
static void a2_mutate_fpr(a2_fixture *f,uint32_t n) {
    switch(n) {
    case 5u:f->fpr[0]^=1u;break;
    case 6u:p32(f->fpr+4u,2u);break;
    case 7u:p32(f->fpr+8u,191u);break;
    case 8u:f->fpr_bytes=4767u;break;
    case 9u:f->fpr[4768u]=0u;f->fpr_bytes=4769u;break;
    case 10u:p32(f->fpr+16u,1375u);break;
    case 11u:p32(f->fpr+20u,15u);break;
    case 12u:p32(f->fpr+24u,15u);break;
    case 13u:p32(f->fpr+28u,31u);break;
    case 14u:p64(f->fpr+48u,2u);break;
    case 15u:p64(f->fpr+56u,15u);break;
    case 16u:p64(f->fpr+64u,18u);break;
    case 17u:p64(f->fpr+72u,31u);break;
    case 18u:p64(f->fpr+80u,33u);break;
    case 19u:f->fpr[176u]=1u;break;
    case 20u:f->fpr[120u]^=1u;break;
    case 21u:f->fpr[88u]^=1u;break;
    case 22u:p64(f->fpr+152u,UINT64_MAX);p64(f->fpr+160u,UINT64_MAX);p64(f->fpr+168u,1u);break;
    case 24u:f->fpr[176u]=1u;break;
    default:a2_must(0,"EXACT_FPR_MUTATION_ID");
    }
    a2_reseal_control(f,(uint32_t)(n!=20u),(uint32_t)(n!=24u));
}
static void a2_mutate_record(a2_fixture *f,uint32_t n) {
    uint8_t *row=f->rows[n==103u?0u:31u];
    switch(n) {
    case 89u:p32(row+28u,f->source.source.capture_source_id+1u);break;
    case 90u:p64(row+20u,f->source.source.source_generation+1u);break;
    case 91u:p32(row+12u,44100u);break;
    case 92u:p32(row+16u,3u);break;
    case 93u:p32(row+8u,FE_B1S0_RENDER_DISABLED);break;
    case 94u:p32(row+32u,f->source.source.render_source_id+1u);break;
    case 95u:p32(row+36u,2u);break;
    case 96u:p32(row+44u,0u);break;
    case 97u:p32(row+92u,a2_u32(row+88u));break;
    case 98u:p64(row+48u,31u);break;
    case 99u:p64(row+56u,2u);break;
    case 100u:p32(row+64u,2u);break;
    case 101u:a2_hash(f->rows[30u],168u,row+136u);break;
    case 102u:row[168u]^=1u;break;
    case 103u:row[136u]=1u;break;
    case 104u:p64(row+80u,1u);break;
    default:a2_must(0,"EXACT_RECORD_MUTATION_ID");
    }
    a2_reseal_chain(f,n);a2_codec_ok(f,n==103u?1u:32u);
    fe_t3b1ba0_owner rebound;
    f->old_a0_rejected=(uint32_t)(fe_t3b1ba0_bind(&rebound,f->data_fd,
        &f->source.source,f->source.slots,32u)!=0);
    a2_must(f->old_a0_rejected!=0u,"ORIGINAL_A0_REJECTS_SAME_COMPLETE_SOURCE_SEMANTIC_MUTANT");
}
static void a2_negative_mutation(a2_fixture *f,uint32_t n,fe_t3b1ba2_request *request) {
    a2_retire_fixture_prefix(f,a2_initial_k(n));
    if(n==2u)memset(f->anchor.checkpoint_raw_sha256,0,32u);
    else if(n==3u||n==4u)f->anchor.checkpoint_raw_sha256[0]^=1u;
    else if((n>=5u&&n<=22u)||n==24u)a2_mutate_fpr(f,n);
    else if(n==23u)memcpy(f->anchor.checkpoint_raw_sha256,f->fpr+120u,32u);
    else if(n>=25u&&n<=40u)
        a2_must(unlinkat(f->data_fd,f->names[n-25u],0)==0,"TEST_REMOVE_EXACT_PRE_ADMISSION_SOURCE");
    else if(n>=41u&&n<=56u)a2_reencode(f,n-40u,1u,0u,0u,0u);
    else if(n>=57u&&n<=72u)
        a2_must(unlinkat(f->data_fd,f->names[n-41u],0)==0,"TEST_REMOVE_EXACT_RETAINED_SOURCE");
    else if(n>=73u&&n<=88u)a2_reencode(f,n-56u,1u,0u,0u,0u);
    else if(n>=89u&&n<=104u)a2_mutate_record(f,n);
    else if(n>=109u&&n<=111u) {
        int fd=n==109u?f->data_fd:n==110u?f->a1_fd:f->control_fd;
        f->saved_fd=dup(fd);f->replaced_fd=fd;
        a2_must(f->saved_fd>=0&&dup2(f->helper_fd,fd)==fd,"TEST_BOUND_DESCRIPTOR_REPLACEMENT");
    } else if(n==112u) {
        a2_must(unlinkat(f->data_fd,f->names[8u],0)==0&&
            symlinkat(f->names[9u],f->data_fd,f->names[8u])==0,"TEST_SYMLINK_RECORD");
    } else if(n==113u) {
        a2_must(linkat(f->data_fd,f->names[8u],f->helper_fd,"alias",0)==0,"TEST_RECORD_HARDLINK");
    } else if(n==115u) {
        a2_must(fchmodat(f->data_fd,f->names[8u],0640,0)==0,"TEST_RECORD_MODE_MUTATION");
    } else if(n==116u) {
        const uint8_t one=1u;a2_write_file(f->data_fd,"unexpected.bin",&one,1u,1);
    } else if(n==117u) {
        char competing[FE_T3B1BA2_NAME_CAP];strcpy(competing,f->control_name);
        competing[31u]=competing[31u]=='0'?'1':'0';
        a2_write_file(f->control_fd,competing,f->fpr,f->fpr_bytes,1);
    } else if(n==118u) {
        a2_must(unlinkat(f->data_fd,f->names[9u],0)==0,"TEST_NONPREFIX_HOLE_SEQ10");
    } else if(n==119u) {
        const uint8_t one=1u;a2_write_file(f->control_fd,"unknown.part",&one,1u,1);
    } else if(n==120u) {
        a2_must(unlinkat(f->data_fd,f->names[8u],0)==0&&
            mkfifoat(f->data_fd,f->names[8u],0600)==0,"TEST_OWNED_FIFO_RECORD");
    } else if(n==145u)request->quiescent=0u;
    else if(n==146u) {
        atomic_store_explicit(&f->original.ring.tail,31u,memory_order_release);
        request->source_tail=atomic_load_explicit(&f->original.ring.tail,memory_order_acquire);
    } else if(n==147u)request->requested_sequence=0u;
    else if(n==148u)request->requested_sequence=33u;
    else if(n==149u){request->requested_first=1u;request->requested_last=16u;}
    else if(n==150u)request->requested_first=18u;
    else if(n==151u)request->requested_generation+=1u;
    else if(n==152u)request->second_retirement=1u;
    else if(n>=161u&&n<=164u) {
        if(n==161u||n==162u)a2_reencode(f,17u,0u,n==161u?FE_S2_XRUN:0u,
            n==162u?FE_S2_XRUN:0u,1u);
        else {size_t offset=n==163u?72u:80u;p64(f->rows[16u]+offset,a2_u64(f->rows[16u]+offset)^1u);}
        a2_reseal_chain(f,n);a2_codec_ok(f,17u);
        a2_must(f->observed_capture_flags==(n==161u?FE_S2_XRUN:0u)&&
            f->observed_render_flags==(n==162u?FE_S2_XRUN:0u)&&
            a2_u64(f->rows[16u]+72u)==(f->observed_capture_fnv^(n==163u?1u:0u))&&
            a2_u64(f->rows[16u]+80u)==(f->observed_render_fnv^(n==164u?1u:0u)),
            "ONLY_REGISTERED_CALLBACK_CONSTRAINT_CHANGED");
        fe_t3b1ba0_owner rebound;
        f->old_a0_rejected=(uint32_t)(fe_t3b1ba0_bind(&rebound,f->data_fd,
            &f->source.source,f->source.slots,32u)!=0);
        a2_must(f->old_a0_rejected!=0u,"OLD_A0_REJECTS_CODEC_VALID_CALLBACK_MUTANT");
    }
    if(n==108u||n==114u||(n>=121u&&n<=144u))
        a2_must(fe_t3b1ba2_set_test_fault(&f->owner,n)==0,"EXACT_REGISTERED_A2_SEAM");
}
static void a2_short_anchor(const fe_t3b1ba2_anchor *a) {
    printf(",\"ah\":\"");a2_hex(a->checkpoint_raw_sha256);
    printf("\",\"a\":[%u,%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64
        ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 "]",a->capture_source_id,
        a->source_generation,a->device[0],a->inode[0],a->device[1],a->inode[1],
        a->device[2],a->inode[2]);
}
static void a2_request_wire(const fe_t3b1ba2_request *r) {
    printf(",\"x\":[%u,%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64
        ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%u,%u,%u]",r->quiescent,
        r->source_head,r->source_tail,r->requested_sequence,r->requested_first,
        r->requested_last,r->requested_high_water,r->requested_generation,
        r->requested_retired_count,r->requested_retained_count,r->second_retirement);
}
static int a2_invoke_negative(a2_fixture *f,uint32_t n,
    const fe_t3b1ba2_request *request,fe_t3b1ba2_receipt *receipt,
    const char **error,uint32_t *independent_read_rejected) {
    int rc=-1;*error=NULL;*independent_read_rejected=0u;
    if(n>=5u&&n<=22u) {
        fe_t3b1ba2_checkpoint decoded;
        *error=fe_t3b1ba2_validate_checkpoint(f->fpr,f->fpr_bytes,&decoded);
        return *error?-1:0;
    }
    if((n>=25u&&n<=56u)||(n>=145u&&n<=152u)) {
        fe_t3b1ba2_anchor candidate;
        rc=fe_t3b1ba2_prepare(&f->owner,&f->source,&f->a1,request,&candidate);
    } else if(n>=89u&&n<=104u) {
        uint32_t seq=n==103u?1u:32u;uint8_t prior[32]={0},file[A2_FILE_BYTES];
        size_t bytes=a2_read_file(f->data_fd,f->names[seq-1u],file,sizeof(file));
        if(seq>1u)a2_hash(f->rows[seq-2u],FE_T3S1_ROW_BYTES,prior);
        *error=fe_t3b1ba2_validate_record(&f->source.source,f->source.slots,file,
            file+FE_T3S1_ROW_BYTES,bytes-FE_T3S1_ROW_BYTES,seq,prior);
        memset(file,0,sizeof(file));return *error?-1:0;
    } else if(n>=105u&&n<=107u) {
        int data=f->data_fd,a1=f->a1_fd,control=f->control_fd;
        if(n==105u)data=a1;
        if(n==106u)data=control;
        if(n==107u)a1=control;
        fe_t3b1ba2_hooks hooks=a2_hooks(&f->audit);
        rc=fe_t3b1ba2_init(&f->owner,data,a1,control,&f->workspace,&hooks);
        if(rc==0)rc=fe_t3b1ba2_bind(&f->owner,&f->anchor);
    } else if(n>=121u&&n<=128u) {
        rc=fe_t3b1ba2_publish(&f->owner,&f->anchor,receipt);
    } else if(n>=129u&&n<=131u) {
        rc=fe_t3b1ba2_read(&f->owner,&f->anchor,receipt);
    } else if(n==132u||n==133u) {
        rc=fe_t3b1ba2_resume(&f->owner,&f->anchor,receipt);
    } else if(n==153u) {
        a2_new_owner(f);rc=fe_t3b1ba2_bind(&f->owner,NULL);
    } else if(n>=161u&&n<=164u) {
        a2_new_owner(f);rc=fe_t3b1ba2_bind(&f->owner,&f->anchor);
        if(rc==0)rc=fe_t3b1ba2_read(&f->owner,&f->anchor,receipt);
        const char *read_error=fe_t3b1ba2_error(&f->owner);
        a2_must(rc!=0&&read_error!=NULL&&!receipt->new_data_unlinks,
                "INDEPENDENT_CALLBACK_READ_ACTUALLY_REJECTS");
        *independent_read_rejected=1u;
        a2_new_owner(f);memset(receipt,0,sizeof(*receipt));
        rc=fe_t3b1ba2_bind(&f->owner,&f->anchor);
        if(rc==0)rc=fe_t3b1ba2_resume(&f->owner,&f->anchor,receipt);
        const char *resume_error=fe_t3b1ba2_error(&f->owner);
        a2_must(rc!=0&&resume_error!=NULL&&strcmp(read_error,resume_error)==0,
                "INDEPENDENT_CALLBACK_RESUME_REACHES_SAME_PREDICATE");
    } else {
        if(n==2u||n==3u||n==23u||n==24u) {
            a2_new_owner(f);rc=fe_t3b1ba2_bind(&f->owner,&f->anchor);
            if(rc!=0){*error=fe_t3b1ba2_error(&f->owner);return rc;}
        }
        rc=fe_t3b1ba2_resume(&f->owner,n==1u?NULL:&f->anchor,receipt);
    }
    *error=fe_t3b1ba2_error(&f->owner);return rc;
}

typedef struct { uint32_t n,profile,known,k;const char *expected; } a2_negative_case;
/* Exact target-C IDs copied from the immutable #825 machine contract. */
static const a2_negative_case A2_NEGATIVE_CASES[]={
    {1u,0u,0u,0u,"MISSING_EXTERNAL_ANCHOR"},
    {2u,0u,0u,0u,"ZERO_EXTERNAL_FILE_DIGEST"},
    {3u,0u,0u,0u,"WRONG_EXTERNAL_FILE_DIGEST"},
    {4u,0u,0u,0u,"BOUND_OWNER_EXPECTED_ANCHOR_CHANGED"},
    {5u,0u,0u,0u,"FPR1_INVALID_FPR1_MAGIC"},
    {6u,0u,0u,0u,"FPR1_UNSUPPORTED_FPR1_VERSION"},
    {7u,0u,0u,0u,"FPR1_INVALID_FPR1_HEADER_SIZE"},
    {8u,0u,0u,0u,"FPR1_TRUNCATED_FPR1"},
    {9u,0u,0u,0u,"FPR1_TRAILING_FPR1_BYTES"},
    {10u,0u,0u,0u,"FPR1_INVALID_EMBEDDED_FRM2_SIZE"},
    {11u,0u,0u,0u,"FPR1_RETIRED_COUNT_NOT_16"},
    {12u,0u,0u,0u,"FPR1_RETAINED_COUNT_NOT_16"},
    {13u,0u,0u,0u,"FPR1_ORIGINAL_COUNT_NOT_32"},
    {14u,0u,0u,0u,"FPR1_RETIRED_FIRST_NOT_1"},
    {15u,0u,0u,0u,"FPR1_RETIRED_LAST_NOT_16"},
    {16u,0u,0u,0u,"FPR1_RETAINED_FIRST_NOT_17"},
    {17u,0u,0u,0u,"FPR1_RETAINED_LAST_NOT_32"},
    {18u,0u,0u,0u,"FPR1_ORIGINAL_HIGH_WATER_NOT_32"},
    {19u,0u,0u,0u,"FPR1_NONZERO_RESERVED_BYTES"},
    {20u,0u,0u,0u,"FPR1_INVALID_CHECKPOINT_SELF_DIGEST"},
    {21u,0u,0u,0u,"FPR1_INVALID_EMBEDDED_FRM2_RAW_DIGEST"},
    {22u,0u,0u,0u,"FPR1_BYTE_TOTAL_OVERFLOW_OR_INCONSISTENT_SUM"},
    {23u,0u,0u,0u,"SELF_DIGEST_SUBSTITUTED_FOR_EXTERNAL_RAW_FILE_DIGEST"},
    {24u,0u,0u,0u,"EXTERNAL_CHECKPOINT_RAW_DIGEST_MISMATCH"},
    {25u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {26u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {27u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {28u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {29u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {30u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {31u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {32u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {33u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {34u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {35u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {36u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {37u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {38u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {39u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {40u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {41u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {42u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {43u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {44u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {45u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {46u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {47u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {48u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {49u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {50u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {51u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {52u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {53u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {54u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {55u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {56u,0u,0u,0u,"ORIGINAL_A0_FULL_ADMISSION_FAILED"},
    {57u,47u,0u,0u,"RETAINED_SEQUENCE_MISSING"},
    {58u,47u,0u,0u,"RETAINED_SEQUENCE_MISSING"},
    {59u,47u,0u,0u,"RETAINED_SEQUENCE_MISSING"},
    {60u,47u,0u,0u,"RETAINED_SEQUENCE_MISSING"},
    {61u,47u,0u,0u,"RETAINED_SEQUENCE_MISSING"},
    {62u,47u,0u,0u,"RETAINED_SEQUENCE_MISSING"},
    {63u,47u,0u,0u,"RETAINED_SEQUENCE_MISSING"},
    {64u,47u,0u,0u,"RETAINED_SEQUENCE_MISSING"},
    {65u,47u,0u,0u,"RETAINED_SEQUENCE_MISSING"},
    {66u,47u,0u,0u,"RETAINED_SEQUENCE_MISSING"},
    {67u,47u,0u,0u,"RETAINED_SEQUENCE_MISSING"},
    {68u,47u,0u,0u,"RETAINED_SEQUENCE_MISSING"},
    {69u,47u,0u,0u,"RETAINED_SEQUENCE_MISSING"},
    {70u,47u,0u,0u,"RETAINED_SEQUENCE_MISSING"},
    {71u,47u,0u,0u,"RETAINED_SEQUENCE_MISSING"},
    {72u,47u,0u,0u,"RETAINED_SEQUENCE_MISSING"},
    {73u,47u,0u,0u,"RETAINED_ORIGINAL_APX3_DIGEST_MISMATCH"},
    {74u,47u,0u,0u,"RETAINED_ORIGINAL_APX3_DIGEST_MISMATCH"},
    {75u,47u,0u,0u,"RETAINED_ORIGINAL_APX3_DIGEST_MISMATCH"},
    {76u,47u,0u,0u,"RETAINED_ORIGINAL_APX3_DIGEST_MISMATCH"},
    {77u,47u,0u,0u,"RETAINED_ORIGINAL_APX3_DIGEST_MISMATCH"},
    {78u,47u,0u,0u,"RETAINED_ORIGINAL_APX3_DIGEST_MISMATCH"},
    {79u,47u,0u,0u,"RETAINED_ORIGINAL_APX3_DIGEST_MISMATCH"},
    {80u,47u,0u,0u,"RETAINED_ORIGINAL_APX3_DIGEST_MISMATCH"},
    {81u,47u,0u,0u,"RETAINED_ORIGINAL_APX3_DIGEST_MISMATCH"},
    {82u,47u,0u,0u,"RETAINED_ORIGINAL_APX3_DIGEST_MISMATCH"},
    {83u,47u,0u,0u,"RETAINED_ORIGINAL_APX3_DIGEST_MISMATCH"},
    {84u,47u,0u,0u,"RETAINED_ORIGINAL_APX3_DIGEST_MISMATCH"},
    {85u,47u,0u,0u,"RETAINED_ORIGINAL_APX3_DIGEST_MISMATCH"},
    {86u,47u,0u,0u,"RETAINED_ORIGINAL_APX3_DIGEST_MISMATCH"},
    {87u,47u,0u,0u,"RETAINED_ORIGINAL_APX3_DIGEST_MISMATCH"},
    {88u,47u,0u,0u,"RETAINED_ORIGINAL_APX3_DIGEST_MISMATCH"},
    {89u,47u,0u,0u,"ORIGINAL_RECORD_CAPTURE_ID_CHANGED"},
    {90u,47u,0u,0u,"ORIGINAL_RECORD_GENERATION_CHANGED"},
    {91u,47u,0u,0u,"ORIGINAL_RECORD_UNSUPPORTED_OR_CHANGED_RATE"},
    {92u,47u,0u,0u,"ORIGINAL_RECORD_PHYSICAL_MIC_COUNT_CHANGED"},
    {93u,47u,0u,0u,"ORIGINAL_RECORD_RENDER_OWNER_ENABLED_CHANGED"},
    {94u,47u,0u,0u,"ORIGINAL_RECORD_RENDER_SOURCE_ID_CHANGED"},
    {95u,47u,0u,0u,"ORIGINAL_RECORD_CAPTURE_OR_RENDER_EPOCH_CHANGED"},
    {96u,47u,0u,0u,"ORIGINAL_RECORD_ABSENT_REASON_CHANGED"},
    {97u,47u,0u,0u,"ORIGINAL_RECORD_DUPLICATE_OR_CHANGED_PHYSICAL_SLOT_MAP"},
    {98u,47u,0u,0u,"ORIGINAL_RECORD_GLOBAL_SEQUENCE_CHANGED"},
    {99u,47u,0u,0u,"ORIGINAL_RECORD_LOCAL_APX3_SEQUENCE_NOT_1"},
    {100u,47u,0u,0u,"ORIGINAL_RECORD_LOCAL_FRAME_COUNT_NOT_1"},
    {101u,47u,0u,0u,"ORIGINAL_RECORD_ROW_PREFIX_DIGEST_SUBSTITUTED_FOR_WHOLE_ROW_ANCHOR"},
    {102u,47u,0u,0u,"ORIGINAL_RECORD_LAST_ROW_DIGEST_CHANGED"},
    {103u,47u,0u,0u,"ORIGINAL_RECORD_FIRST_RETIRED_ROW_PRIOR_NONZERO"},
    {104u,47u,0u,0u,"ORIGINAL_RECORD_RENDER_FNV_NONZERO_WHEN_ABSENT"},
    {105u,0u,0u,0u,"DIRECTORY_ALIAS"},
    {106u,0u,0u,0u,"DIRECTORY_ALIAS"},
    {107u,0u,0u,0u,"DIRECTORY_ALIAS"},
    {108u,0u,0u,0u,"CROSS_DEVICE_DIRECTORY_TUPLE"},
    {109u,0u,0u,0u,"DATA_DIRECTORY_IDENTITY_CHANGED"},
    {110u,0u,0u,0u,"A1_DIRECTORY_IDENTITY_CHANGED"},
    {111u,0u,0u,0u,"A2_DIRECTORY_IDENTITY_CHANGED"},
    {112u,0u,0u,0u,"SYMLINK_RECORD"},
    {113u,0u,0u,0u,"HARDLINK_RECORD"},
    {114u,0u,0u,0u,"FOREIGN_UID_RECORD"},
    {115u,0u,0u,0u,"RECORD_MODE_NOT_0600"},
    {116u,0u,0u,0u,"UNEXPECTED_DATA_ENTRY"},
    {117u,0u,0u,0u,"MULTIPLE_CONTROL_ROOTS"},
    {118u,0u,0u,0u,"NONPREFIX_MISSING_RETIRED_SEQUENCE"},
    {119u,0u,0u,0u,"ORPHAN_OR_UNKNOWN_CONTROL_TEMP"},
    {120u,0u,0u,0u,"NONREGULAR_RECORD"},
    {121u,0u,0u,0u,"INJECTED_IO_FAILURE"},
    {122u,0u,0u,0u,"INJECTED_IO_FAILURE"},
    {123u,0u,0u,0u,"INJECTED_IO_FAILURE"},
    {124u,0u,0u,0u,"INJECTED_IO_FAILURE"},
    {125u,0u,0u,0u,"INJECTED_IO_FAILURE"},
    {126u,0u,0u,0u,"INJECTED_IO_FAILURE"},
    {127u,0u,0u,0u,"INJECTED_IO_FAILURE"},
    {128u,0u,0u,0u,"INJECTED_IO_FAILURE"},
    {129u,0u,0u,0u,"INJECTED_IO_FAILURE"},
    {130u,0u,0u,0u,"INJECTED_IO_FAILURE"},
    {131u,0u,0u,0u,"INJECTED_IO_FAILURE"},
    {132u,0u,0u,0u,"INJECTED_IO_FAILURE"},
    {133u,0u,0u,0u,"INJECTED_IO_FAILURE"},
    {134u,0u,0u,0u,"INJECTED_IO_FAILURE"},
    {135u,0u,0u,0u,"INJECTED_IO_FAILURE"},
    {136u,0u,0u,0u,"INJECTED_IO_FAILURE"},
    {137u,0u,0u,0u,"INJECTED_IO_FAILURE"},
    {138u,0u,0u,0u,"INJECTED_IO_FAILURE"},
    {139u,0u,1u,8u,"INJECTED_IO_FAILURE"},
    {140u,0u,1u,8u,"INJECTED_IO_FAILURE"},
    {141u,0u,1u,9u,"PARTIAL_RETIREMENT_NOT_COMMITTED"},
    {142u,0u,0u,0u,"INJECTED_IO_FAILURE"},
    {143u,0u,0u,0u,"INJECTED_IO_FAILURE"},
    {144u,0u,0u,0u,"INJECTED_IO_FAILURE"},
    {145u,0u,0u,0u,"QUIESCENCE_DECLARATION_REQUIRED"},
    {146u,0u,0u,0u,"ORIGINAL_SOURCE_NOT_STOPPED_AND_DRAINED_AT32"},
    {147u,0u,0u,0u,"OUTSIDE_FIXED_FINITE_STAGE"},
    {148u,0u,0u,0u,"OUTSIDE_FIXED_FINITE_STAGE"},
    {149u,0u,0u,0u,"OUTSIDE_FIXED_FINITE_STAGE"},
    {150u,0u,0u,0u,"OUTSIDE_FIXED_FINITE_STAGE"},
    {151u,0u,0u,0u,"OUTSIDE_FIXED_FINITE_STAGE"},
    {152u,0u,0u,0u,"OUTSIDE_FIXED_FINITE_STAGE"},
    {153u,0u,0u,0u,"RECOVERY_EXTERNAL_ANCHOR_REQUIRED"},
    {161u,0u,0u,0u,"CAPTURE_FLAGS_NONZERO"},
    {162u,47u,0u,0u,"RENDER_FLAGS_NONZERO"},
    {163u,0u,0u,0u,"CAPTURE_PCM_FNV_MISMATCH"},
    {164u,47u,0u,0u,"RENDER_PCM_FNV_MISMATCH"},
};

static int a2_negative_batch(const char *root) {
    size_t total=sizeof(A2_NEGATIVE_CASES)/sizeof(A2_NEGATIVE_CASES[0]);
    a2_must(total==157u,"EXACT_157_TARGET_C_IDS");
    for(size_t i=0u;i<total;++i) {
        const a2_negative_case *test=&A2_NEGATIVE_CASES[i];uint32_t n=test->n;
        a2_fixture *f=(a2_fixture *)calloc(1u,sizeof(*f));
        a2_must(f!=NULL,"ONE_BOUNDED_NEGATIVE_FIXTURE");a2_setup(f,root,test->profile);
        uint32_t p0=(uint32_t)((n>=25u&&n<=56u)||(n>=145u&&n<=152u));
        uint32_t legal_reader_control=0u;
        if(!p0) {
            a2_prepare(f);
            if(a2_empty_control(n))
                a2_must(fe_t3b1ba2_acknowledge(&f->owner,&f->anchor)==0,"NEGATIVE_EMPTY_CONTROL_PREPARED");
            else a2_publish_setup(f);
            if((n>=89u&&n<=104u)||(n>=161u&&n<=164u)) {
                fe_t3b1ba2_receipt legal;
                a2_must(fe_t3b1ba2_read(&f->owner,&f->anchor,&legal)==0&&
                    legal.retained_files_verified==16u&&!legal.new_data_unlinks,
                    "ORIGINAL_LEGAL_CONTROL_ACCEPTED_BY_NEW_READER");legal_reader_control=1u;
            }
        }
        uint64_t original[3];a2_owner_witness(f,original);
        printf("{\"e\":\"nb\",\"n\":%u,\"q\":%u,\"o\":",n,test->profile);
        a2_print_owner(original);
        if(n==3u||n==24u)a2_short_anchor(&f->anchor);
        puts("}");a2_wait("MUTATE\n");
        fe_t3b1ba2_request request=a2_request(f);
        a2_negative_mutation(f,n,&request);
        a2_owner_witness(f,original);
        printf("{\"e\":\"nr\",\"n\":%u,\"o\":",n);a2_print_owner(original);
        if(n==3u||n==24u)a2_short_anchor(&f->anchor);
        else if(n==2u||n==4u||n==23u) {
            printf(",\"ah\":\"");a2_hex(f->anchor.checkpoint_raw_sha256);putchar('"');
        }
        if(n>=145u&&n<=152u)a2_request_wire(&request);
        else if(n==1u||n==153u)printf(",\"x\":null");
        else if(n>=105u&&n<=107u) {
            int d=n==105u?f->a1_fd:n==106u?f->control_fd:f->data_fd;
            int a=n==107u?f->control_fd:f->a1_fd;
            printf(",\"x\":[%d,%d,%d]",d,a,f->control_fd);
        } else if(n>=109u&&n<=111u) {
            struct stat st;a2_must(fstat(f->replaced_fd,&st)==0,"ACTUAL_REPLACED_DESCRIPTOR_STAT");
            printf(",\"x\":[%d,%d,%" PRIu64 ",%" PRIu64 "]",f->replaced_fd,
                f->helper_fd,(uint64_t)st.st_dev,(uint64_t)st.st_ino);
        } else if(n==108u||n==114u||(n>=121u&&n<=144u))
            printf(",\"x\":%u",f->owner.test_fault);
        if(n>=161u&&n<=164u)
            printf(",\"cv\":[%u,%u,%" PRIu64 ",%" PRIu64 "]",
                f->observed_capture_flags,f->observed_render_flags,
                f->observed_capture_fnv,f->observed_render_fnv);
        puts("}");a2_wait("RUN\n");
        fe_t3b1ba2_anchor caller_before=f->anchor;
        uint64_t source_calls_before=f->source_calls;
        fe_t3b1ba2_receipt receipt;memset(&receipt,0,sizeof(receipt));
        f->audit.active=1u;f->audit.negative_id=n;
        const char *error=NULL;uint32_t read_rejected=0u;
        int rc=a2_invoke_negative(f,n,&request,&receipt,&error,&read_rejected);
        uint64_t after[3];a2_owner_witness(f,after);
        a2_same_owner(f,original);
        a2_must(f->source_calls==source_calls_before&&
            memcmp(&caller_before,&f->anchor,sizeof(caller_before))==0,
            "CANDIDATE_DID_NOT_MUTATE_CALLER_ANCHOR_OR_CALL_SOURCE_FEEDER");
        printf("{\"e\":\"nd\",\"n\":%u,\"rc\":%d,\"c\":\"%s\",\"k\":",n,rc,error?error:"OK");
        if(receipt.missing_prefix_known)printf("%u",receipt.missing_prefix);else printf("null");
        printf(",\"u\":%u,\"commit\":%s,\"o\":",receipt.new_data_unlinks,
            receipt.hosted_retirement_committed?"true":"false");a2_print_owner(after);
        printf(",\"io\":[%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64
            "],\"v\":[%u,%u,%u,%u],\"ack\":%u}\n",f->audit.events,
            f->audit.unlinks,f->audit.syncs,f->audit.injected,f->codec_ok,
            f->old_a0_rejected,legal_reader_control,read_rejected,receipt.source_ack_proven);
        a2_must(fflush(stdout)==0,"NEGATIVE_RESULT_FLUSH");
        const char *expected=n==3u?"EXTERNAL_CHECKPOINT_RAW_DIGEST_MISMATCH":test->expected;
        if(rc==0||!error||strcmp(error,expected)) {
            fprintf(stderr,"FE09_A2F0_NOT_ADMITTED N%03u expected=%s actual=%s rc=%d\n",
                    n,expected,error?error:"OK",rc);exit(1);
        }
        a2_must(receipt.missing_prefix_known==test->known&&
            (!test->known||receipt.missing_prefix==test->k)&&
            receipt.new_data_unlinks==(n==141u?1u:0u)&&
            f->audit.unlinks==receipt.new_data_unlinks&&
            !receipt.hosted_retirement_committed&&!receipt.hosted_checkpoint_committed&&
            !receipt.source_ack_proven,"EXACT_NEGATIVE_SIDE_EFFECT_AND_RUNTIME_KNOWLEDGE");
        if(n==108u||n==114u||(n>=121u&&n<=144u))
            a2_must(f->audit.injected>0u&&f->audit.last_injected.fault_id==n,
                    "REGISTERED_FAULT_ACTUALLY_INJECTED");
        a2_wait("CONTINUE\n");
        f->audit.active=0u;a2_cleanup(f);memset(f,0,sizeof(*f));free(f);
    }
    printf("{\"e\":\"nb_done\",\"count\":157,\"m\":%zu,\"io\":%" PRIu64 ",\"d\":\"",
        fe_t3b1ba2_resource_bytes(),A2_BATCH_EVENTS);a2_hex(A2_BATCH_DIGEST);
    printf("\",\"r\":");a2_resource_layout();
    printf(",\"z\":");a2_fixture_layout();puts("}");
    a2_must(fflush(stdout)==0,"NEGATIVE_BATCH_COMPLETE_FLUSH");return 0;
}
int main(int argc,char **argv) {
    a2_must(fe_t3b1ba2_resource_bytes()<=FE_T3B1BA2_RESOURCE_LIMIT,
            "EXPLICIT_A2_STATE_AND_WORKSPACE_LIMIT");
    a2_must(argc>=3,"EXPLICIT_PARENT_CLI_REQUIRED");
    if(!strcmp(argv[1],"transaction")) {
        a2_must(argc==5,"TRANSACTION_ARGUMENT_COUNT");
        uint64_t profile=a2_number(argv[3]),point=a2_number(argv[4]);
        a2_must(profile<48u&&point<=57u,"REGISTERED_TRANSACTION_CASE");
        return a2_transaction(argv[2],(uint32_t)profile,(uint32_t)point);
    }
    if(!strcmp(argv[1],"recovery")) {
        a2_must(argc==12,"RECOVERY_METADATA_ONLY_ARGUMENT_COUNT");
        fe_t3b1ba2_anchor anchor;memset(&anchor,0,sizeof(anchor));
        uint64_t capture=a2_number(argv[3]);
        a2_must(capture>0u&&capture<=UINT32_MAX,"EXTERNAL_CAPTURE_ID");
        anchor.capture_source_id=(uint32_t)capture;anchor.source_generation=a2_number(argv[4]);
        for(unsigned i=0u;i<3u;++i) {
            anchor.device[i]=a2_number(argv[5u+i*2u]);
            anchor.inode[i]=a2_number(argv[6u+i*2u]);
        }
        a2_parse_hash(argv[11],anchor.checkpoint_raw_sha256);
        return a2_recovery(argv[2],&anchor);
    }
    if(!strcmp(argv[1],"negative-batch")) {
        a2_must(argc==3,"EXACT_FULL_NEGATIVE_BATCH_CLI");return a2_negative_batch(argv[2]);
    }
    a2_must(0,"UNKNOWN_PARENT_COMMAND");return 1;
}
