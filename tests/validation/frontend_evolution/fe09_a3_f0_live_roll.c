#define _GNU_SOURCE
#include "fe09_a3_f0_live_roll.h"

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

_Static_assert(sizeof(fe_a3_f0_inventory_entry)==240u,"A3 inventory entry");
_Static_assert(sizeof(fe_a3_f0_root)<=512u,"A3 metadata slice");
_Static_assert(sizeof(fe_a3_f0_io_event)<=256u,"A3 IO event slice");
_Static_assert(sizeof(fe_a3_f0_work)==FE_A3_F0_WORKSPACE_BYTES,"A3 exact workspace");
_Static_assert(sizeof(fe_a3_f0_workspace)==FE_A3_F0_WORKSPACE_BYTES,"A3 alignment");
_Static_assert(sizeof(fe_a3_f0_owner)+sizeof(fe_a3_f0_receipt)<
    FE_A3_F0_CONTROL_RESERVE,"A3 owner/receipt leave proxy/control reserve");
_Static_assert(FE_A3_F0_WORKSPACE_BYTES+FE_A3_F0_CONTROL_RESERVE+
    FE_A3_F0_STACK_RESERVE+FE_A3_F0_RODATA_RESERVE==FE_A3_F0_RESOURCE_BYTES,
    "A3 declared private resource envelope");

#define A3_DATA 0u
#define A3_ROOT 1u
#define A3_FINAL 1u
#define A3_TEMP 2u
#define A3_OLD 4u
#define A3_PENDING 8u

static uint32_t a3_u32(const uint8_t *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8u)|
        ((uint32_t)p[2]<<16u)|((uint32_t)p[3]<<24u);
}
static uint64_t a3_u64(const uint8_t *p) {
    return (uint64_t)a3_u32(p)|((uint64_t)a3_u32(p+4u)<<32u);
}
static void a3_p32(uint8_t *p,uint32_t v) {
    for(unsigned i=0u;i<4u;++i)p[i]=(uint8_t)(v>>(8u*i));
}
static void a3_p64(uint8_t *p,uint64_t v) {
    for(unsigned i=0u;i<8u;++i)p[i]=(uint8_t)(v>>(8u*i));
}
static int a3_nonzero(const uint8_t *p,size_t n) {
    for(size_t i=0u;i<n;++i)if(p[i])return 1;
    return 0;
}
static int a3_apart(const void *a,size_t an,const void *b,size_t bn) {
    const uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    if(!a||!b||x>UINTPTR_MAX-an||y>UINTPTR_MAX-bn)return 0;
    return x+an<=y||y+bn<=x;
}
static void a3_hex(const uint8_t *p,char *out) {
    static const char alphabet[]="0123456789abcdef";
    for(unsigned i=0u;i<32u;++i) {
        out[2u*i]=alphabet[p[i]>>4u];out[2u*i+1u]=alphabet[p[i]&15u];
    }
    out[64]='\0';
}
static int a3_same_profile(const fe_a3_f0_profile *a,
    const fe_a3_f0_profile *b) {
    return a->source.depth==b->source.depth&&
        a->source.physical_mics==b->source.physical_mics&&
        a->source.input_hz==b->source.input_hz&&
        a->source.render_enabled==b->source.render_enabled&&
        a->source.capture_source_id==b->source.capture_source_id&&
        a->source.render_source_id==b->source.render_source_id&&
        a->source.source_generation==b->source.source_generation&&
        a->physical_k==b->physical_k&&memcmp(a->slots,b->slots,sizeof(a->slots))==0;
}
static int a3_fail(fe_a3_f0_owner *s,const char *error) {
    if(s)s->last_error=error;
    return -1;
}
static int a3_io_fail(fe_a3_f0_owner *s) {
    return a3_fail(s,s&&s->fault_fired?"REGISTERED_IO_FAULT":"HOSTED_IO_ERROR");
}
static fe_a3_f0_work *a3_work(fe_a3_f0_owner *s) {
    return &s->workspace->work;
}
static const uint8_t *a3_selected(const fe_a3_f0_owner *s) {
    return s->workspace->work.roots[s->authority.current_promoted?1u:0u];
}

const char *fe_a3_f0_validate_root(const uint8_t *b,size_t n,
    const fe_a3_f0_profile *expected,const uint8_t prev[32],
    fe_a3_f0_root *out,uint8_t scratch[FE_A3_F0_RECORD_BYTES]) {
    fe_a3_f0_root v;
    uint8_t digest[32];
    const char *error;
    if(!b||n!=FE_A3_F0_ROOT_BYTES||!scratch||
       !a3_apart(b,n,scratch,FE_A3_F0_RECORD_BYTES)||
       (out&&(!a3_apart(b,n,out,sizeof(*out))||
              !a3_apart(scratch,FE_A3_F0_RECORD_BYTES,out,sizeof(*out)))))
        return "A3_FORMAT_REJECT";
    if(a3_u32(b)!=FE_A3_F0_MAGIC||a3_u32(b+4u)!=1u||
       a3_u32(b+8u)!=256u||a3_u32(b+12u)!=FE_A3_F0_ROOT_BYTES||
       a3_u32(b+16u)!=16u||a3_u32(b+20u)!=200u||a3_u32(b+24u)||
       a3_u32(b+104u)!=16u||a3_u32(b+108u)!=17u||
       a3_nonzero(b+224u,32u))return "A3_FORMAT_REJECT";
    memset(&v,0,sizeof(v));
    v.profile.source.physical_mics=a3_u32(b+28u);
    v.profile.source.source_generation=a3_u64(b+32u);
    v.profile.source.capture_source_id=a3_u32(b+40u);
    v.profile.source.render_source_id=a3_u32(b+44u);
    v.profile.source.input_hz=a3_u32(b+48u);
    v.profile.source.render_enabled=a3_u32(b+52u);
    v.profile.source.depth=a3_u32(b+56u);v.profile.physical_k=a3_u32(b+60u);
    for(unsigned i=0u;i<4u;++i)v.profile.slots[i]=a3_u32(b+112u+4u*i);
    error=fe_a3_f0_validate_profile(&v.profile);if(error)return error;
    if(expected) {
        error=fe_a3_f0_validate_profile(expected);if(error)return error;
        if(!a3_same_profile(expected,&v.profile))return "ORIGINAL_SOURCE_MISMATCH";
    }
    v.first=a3_u64(b+64u);v.last=a3_u64(b+72u);v.high_water=a3_u64(b+80u);
    v.generation=a3_u64(b+88u);v.left_sequence=a3_u64(b+96u);
    if(v.last<32u||v.last>49u||v.high_water!=v.last||
       v.first!=v.last-15u||v.left_sequence!=v.first-1u||
       v.generation!=v.last-32u)
        return "ROOT_GENERATION_OR_WINDOW_MISMATCH";
    if((v.generation==0u)==(a3_nonzero(b+128u,32u)!=0)||
       !a3_nonzero(b+160u,32u))return "PREVIOUS_ROOT_RAW_SHA_MISMATCH";
    if(prev&&memcmp(prev,b+128u,32u)!=0)
        return "PREVIOUS_ROOT_RAW_SHA_MISMATCH";
    memcpy(scratch,b,n);memset(scratch+FE_A3_F0_SELF_OFFSET,0,32u);
    if(fe_b1s1_sha256(scratch,n,digest)!=0||
       memcmp(digest,b+FE_A3_F0_SELF_OFFSET,32u)!=0)
        return "A3_ROOT_SELF_SHA_REJECT";
    error=fe_a3_f0_validate_row_metadata(&v.profile,b+256u,v.left_sequence,NULL);
    if(error)return error;
    if(fe_b1s1_sha256(b+256u,200u,digest)!=0)return "ORIGINAL_SHA_REJECT";
    for(unsigned i=0u;i<16u;++i) {
        const uint8_t *row=b+456u+200u*i;
        error=fe_a3_f0_validate_row_metadata(&v.profile,row,v.first+i,digest);
        if(error)return error;
        if(fe_b1s1_sha256(row,200u,digest)!=0)return "ORIGINAL_SHA_REJECT";
    }
    if(fe_b1s1_sha256(b,n,v.raw_sha256)!=0)return "ORIGINAL_SHA_REJECT";
    memcpy(v.self_sha256,b+192u,32u);memcpy(v.previous_raw_sha256,b+128u,32u);
    memcpy(v.genesis_fpr1_raw_sha256,b+160u,32u);
    if(out)*out=v;
    return NULL;
}

const char *fe_a3_f0_next_root(const uint8_t previous[FE_A3_F0_ROOT_BYTES],
    const uint8_t row[FE_A3_F0_ROW_BYTES],uint8_t next[FE_A3_F0_ROOT_BYTES],
    uint8_t scratch[FE_A3_F0_RECORD_BYTES]) {
    fe_a3_f0_root v;
    uint8_t digest[32];
    const char *error;
    if(!previous||!row||!next||!scratch||
       !a3_apart(previous,FE_A3_F0_ROOT_BYTES,next,FE_A3_F0_ROOT_BYTES)||
       !a3_apart(row,200u,next,FE_A3_F0_ROOT_BYTES)||
       !a3_apart(next,FE_A3_F0_ROOT_BYTES,scratch,FE_A3_F0_RECORD_BYTES))
        return "A3_ROOT_BUFFER_ALIAS_REJECT";
    error=fe_a3_f0_validate_root(previous,FE_A3_F0_ROOT_BYTES,NULL,NULL,&v,scratch);
    if(error)return error;
    if(v.last>=49u)return "NEW_VALIDATOR_DOMAIN_REJECT";
    if(fe_b1s1_sha256(previous+3456u,200u,digest)!=0)return "ORIGINAL_SHA_REJECT";
    error=fe_a3_f0_validate_row_metadata(&v.profile,row,v.last+1u,digest);
    if(error)return error;
    memcpy(next,previous,256u);
    memcpy(next+256u,previous+456u,3200u);memcpy(next+3456u,row,200u);
    a3_p64(next+64u,v.first+1u);a3_p64(next+72u,v.last+1u);
    a3_p64(next+80u,v.last+1u);a3_p64(next+88u,v.generation+1u);
    a3_p64(next+96u,v.left_sequence+1u);
    memcpy(next+128u,v.raw_sha256,32u);memset(next+192u,0,32u);
    if(fe_b1s1_sha256(next,FE_A3_F0_ROOT_BYTES,digest)!=0)return "ORIGINAL_SHA_REJECT";
    memcpy(next+192u,digest,32u);
    return fe_a3_f0_validate_root(next,FE_A3_F0_ROOT_BYTES,&v.profile,
        v.raw_sha256,NULL,scratch);
}

int fe_a3_f0_root_name(const uint8_t root[FE_A3_F0_ROOT_BYTES],char name[192]) {
    uint8_t digest[32];char hex[65];
    if(!root||!name||a3_u32(root)!=FE_A3_F0_MAGIC||
       fe_b1s1_sha256(root,FE_A3_F0_ROOT_BYTES,digest)!=0)return -1;
    a3_hex(digest,hex);
    const int written=snprintf(name,192u,"a3r1-%08" PRIx32 "-%016" PRIx64
        "-%016" PRIx64 "-%s.bin",a3_u32(root+40u),a3_u64(root+32u),
        a3_u64(root+88u),hex);
    return written==116?0:-1;
}
int fe_a3_f0_record_name(const uint8_t row[200],char name[192]) {
    uint8_t digest[32];char row_hex[65],apx_hex[65];
    if(!row||!name)return -1;
    const uint64_t seq=a3_u64(row+48u);
    if(seq<17u||seq>49u||fe_b1s1_sha256(row,200u,digest)!=0)return -1;
    if(seq<=32u)return fe_t3b1ba0_name(a3_u32(row+28u),a3_u64(row+20u),
        seq,digest,row+104u,name);
    a3_hex(digest,row_hex);a3_hex(row+104u,apx_hex);
    const int written=snprintf(name,192u,"fa3-%08" PRIx32 "-%016" PRIx64
        "-%016" PRIx64 "-%s-%s.bin",a3_u32(row+28u),a3_u64(row+20u),
        seq,row_hex,apx_hex);
    return written==180?0:-1;
}

static fe_a3_f0_io_event *a3_event(fe_a3_f0_owner *s,uint32_t op,
    uint32_t role,uint64_t seq,size_t requested,uint32_t seam) {
    fe_a3_f0_io_event *e=&a3_work(s)->event.event;
    memset(e,0,sizeof(*e));e->phase=s->phase;e->operation=op;e->role=role;
    e->sequence=(uint32_t)seq;e->ordinal=++s->io_ordinal;
    e->requested_bytes=(uint64_t)requested;e->seam=seam;
    e->syscall_called=1u;e->actual_result=FE_A3_F0_NOT_CALLED;
    return e;
}
static int a3_inject(fe_a3_f0_owner *s,fe_a3_f0_io_event *e) {
    if(!e->seam||s->test_fault!=e->seam||s->fault_fired)return 0;
    s->fault_fired=1u;e->syscall_called=0u;e->injected=1u;e->fault_id=e->seam;
    e->actual_result=FE_A3_F0_NOT_CALLED;e->actual_errno=0;
    e->reported_result=-1;e->reported_errno=e->seam==1u?ENOSPC:EIO;
    return 1;
}
static void a3_emit(fe_a3_f0_owner *s,fe_a3_f0_io_event *e,int saved_errno) {
    if(e->operation<12u) {
        ++s->io.operations[e->operation];
        if(e->syscall_called)++s->io.actual_operations[e->operation];
    }
    if(e->injected)++s->io.injected_events;
    if(s->hooks.io)s->hooks.io(e,s->hooks.context);
    errno=saved_errno;
}
static void a3_result(fe_a3_f0_io_event *e,int64_t result,int saved_errno) {
    e->actual_result=result;e->reported_result=result;
    e->actual_errno=result<0?saved_errno:0;e->reported_errno=e->actual_errno;
}
static int a3_open(fe_a3_f0_owner *s,unsigned dir,const char *name,int flags,
    uint32_t role,uint64_t seq,uint32_t seam) {
    fe_a3_f0_io_event *e=a3_event(s,FE_A3_F0_IO_OPEN,role,seq,0u,seam);
    int result,saved;
    if(a3_inject(s,e)){result=-1;saved=e->reported_errno;}
    else {result=openat(s->dirfd[dir],name,flags,0600);saved=errno;
        a3_result(e,(int64_t)result,saved);}
    a3_emit(s,e,result<0?saved:0);return result;
}
static int a3_close(fe_a3_f0_owner *s,int fd,uint32_t role,uint64_t seq) {
    fe_a3_f0_io_event *e=a3_event(s,FE_A3_F0_IO_CLOSE,role,seq,0u,0u);
    const int result=close(fd),saved=errno;
    a3_result(e,(int64_t)result,saved);a3_emit(s,e,result<0?saved:0);return result;
}
static int a3_stat(fe_a3_f0_owner *s,int fd,struct stat *st,
    uint32_t role,uint64_t seq) {
    fe_a3_f0_io_event *e=a3_event(s,FE_A3_F0_IO_FSTAT,role,seq,0u,0u);
    const int result=fstat(fd,st),saved=errno;
    a3_result(e,(int64_t)result,saved);
    if(result==0) {e->actual_device=(uint64_t)st->st_dev;
        e->actual_inode=(uint64_t)st->st_ino;e->actual_links=(uint64_t)st->st_nlink;
        e->actual_bytes=st->st_size<0?0u:(uint64_t)st->st_size;}
    a3_emit(s,e,result<0?saved:0);return result;
}
static int a3_statat(fe_a3_f0_owner *s,unsigned dir,const char *name,
    struct stat *st,uint32_t role,uint64_t seq) {
    fe_a3_f0_io_event *e=a3_event(s,FE_A3_F0_IO_FSTATAT,role,seq,0u,0u);
    const int result=fstatat(s->dirfd[dir],name,st,AT_SYMLINK_NOFOLLOW),saved=errno;
    a3_result(e,(int64_t)result,saved);
    if(result==0) {e->actual_device=(uint64_t)st->st_dev;
        e->actual_inode=(uint64_t)st->st_ino;e->actual_links=(uint64_t)st->st_nlink;
        e->actual_bytes=st->st_size<0?0u:(uint64_t)st->st_size;}
    a3_emit(s,e,result<0?saved:0);return result;
}
static int a3_flags(fe_a3_f0_owner *s,int fd,uint32_t role) {
    fe_a3_f0_io_event *e=a3_event(s,FE_A3_F0_IO_FLAGS,role,0u,0u,0u);
    const int result=fcntl(fd,F_GETFL),saved=errno;
    a3_result(e,(int64_t)result,saved);a3_emit(s,e,result<0?saved:0);return result;
}
static ssize_t a3_read(fe_a3_f0_owner *s,int fd,uint8_t *p,size_t n,
    uint32_t role,uint64_t seq) {
    fe_a3_f0_io_event *e=a3_event(s,FE_A3_F0_IO_READ,role,seq,n,0u);
    const ssize_t result=read(fd,p,n);const int saved=errno;
    a3_result(e,(int64_t)result,saved);
    e->actual_bytes=result>0?(uint64_t)result:0u;
    a3_emit(s,e,result<0?saved:0);return result;
}
static ssize_t a3_write(fe_a3_f0_owner *s,int fd,const uint8_t *p,size_t n,
    uint32_t role,uint64_t seq,uint32_t seam) {
    fe_a3_f0_io_event *e=a3_event(s,FE_A3_F0_IO_WRITE,role,seq,n,seam);
    ssize_t result;int saved;
    if(a3_inject(s,e)){result=-1;saved=e->reported_errno;}
    else {result=write(fd,p,n);saved=errno;a3_result(e,(int64_t)result,saved);
        e->actual_bytes=result>0?(uint64_t)result:0u;}
    a3_emit(s,e,result<0?saved:0);return result;
}
static int a3_sync(fe_a3_f0_owner *s,int fd,uint32_t role,uint64_t seq,
    uint32_t seam) {
    fe_a3_f0_io_event *e=a3_event(s,FE_A3_F0_IO_FSYNC,role,seq,0u,seam);
    int result,saved;
    if(a3_inject(s,e)){result=-1;saved=e->reported_errno;}
    else {result=fsync(fd);saved=errno;a3_result(e,(int64_t)result,saved);}
    if(result==0&&seam==10u) {
        s->authority.data_retire_sync_observed=1u;
        s->current_call_data_sync=1u;++s->io.successful_retirement_data_syncs;
    }
    if(result==0&&seam==12u) {
        s->authority.root_retire_sync_observed=1u;
        s->current_call_root_sync=1u;++s->io.successful_old_root_syncs;
    }
    if(result==0&&seam==5u)s->data_publication_synced=1u;
    if(result==0&&seam==8u)s->root_publication_synced=1u;
    a3_emit(s,e,result<0?saved:0);return result;
}
static int a3_link(fe_a3_f0_owner *s,unsigned dir,const char *temp,
    const char *final,uint32_t role,uint64_t seq,uint32_t seam) {
    fe_a3_f0_io_event *e=a3_event(s,FE_A3_F0_IO_LINK,role,seq,0u,seam);
    int result,saved;
    if(a3_inject(s,e)){result=-1;saved=e->reported_errno;}
    else {result=linkat(s->dirfd[dir],temp,s->dirfd[dir],final,0);saved=errno;
        a3_result(e,(int64_t)result,saved);}
    a3_emit(s,e,result<0?saved:0);return result;
}
static int a3_unlink(fe_a3_f0_owner *s,unsigned dir,const char *name,
    uint32_t role,uint64_t seq,uint32_t seam) {
    fe_a3_f0_io_event *e=a3_event(s,FE_A3_F0_IO_UNLINK,role,seq,0u,seam);
    int result,saved;
    if(a3_inject(s,e)){result=-1;saved=e->reported_errno;}
    else {result=unlinkat(s->dirfd[dir],name,0);saved=errno;
        a3_result(e,(int64_t)result,saved);}
    if(result==0&&seam==9u) {
        s->authority.retiring_data_unlink_observed=1u;
        ++s->io.successful_data_unlinks;
    }
    if(result==0&&seam==11u) {
        s->authority.old_root_unlink_observed=1u;++s->io.successful_old_root_unlinks;
    }
    a3_emit(s,e,result<0?saved:0);return result;
}
static ssize_t a3_getdents(fe_a3_f0_owner *s,int fd,uint32_t role) {
    fe_a3_f0_io_event *e=a3_event(s,FE_A3_F0_IO_GETDENTS,role,0u,768u,0u);
    const long raw=syscall(SYS_getdents64,fd,a3_work(s)->names,(size_t)768u);
    const int saved=errno;
    a3_result(e,(int64_t)raw,saved);e->actual_bytes=raw>0?(uint64_t)raw:0u;
    a3_emit(s,e,raw<0?saved:0);return (ssize_t)raw;
}
static int a3_read_all(fe_a3_f0_owner *s,int fd,uint8_t *p,size_t n,
    uint32_t role,uint64_t seq) {
    size_t done=0u;
    while(done<n) {
        const ssize_t got=a3_read(s,fd,p+done,n-done,role,seq);
        if(got<0) {if(errno==EINTR)continue;return a3_io_fail(s);}
        if(got==0)return a3_fail(s,"OBSERVABLE_FILE_TRUNCATION");
        done+=(size_t)got;
    }
    return 0;
}
static int a3_write_all(fe_a3_f0_owner *s,int fd,const uint8_t *p,size_t n,
    uint32_t role,uint64_t seq,uint32_t partial_seam) {
    const int partial=partial_seam&&s->test_fault==partial_seam&&!s->fault_fired;
    const size_t limit=partial?(partial_seam==2u?201u:256u):n;
    size_t done=0u;
    if(limit>n)return a3_fail(s,"REGISTERED_PREFIX_OUT_OF_RANGE");
    while(done<limit) {
        const ssize_t put=a3_write(s,fd,p+done,limit-done,role,seq,0u);
        if(put<0) {if(errno==EINTR)continue;return a3_io_fail(s);}
        if(put==0)return a3_fail(s,"HOSTED_ZERO_WRITE");
        done+=(size_t)put;
    }
    if(partial) {
        (void)a3_write(s,fd,p+done,n-done,role,seq,partial_seam);
        return a3_io_fail(s);
    }
    return 0;
}

static int a3_same_stat(const struct stat *a,const struct stat *b) {
    return a->st_dev==b->st_dev&&a->st_ino==b->st_ino&&
        a->st_mode==b->st_mode&&a->st_uid==b->st_uid&&a->st_gid==b->st_gid&&
        a->st_nlink==b->st_nlink&&a->st_size==b->st_size&&
        a->st_mtim.tv_sec==b->st_mtim.tv_sec&&
        a->st_mtim.tv_nsec==b->st_mtim.tv_nsec&&
        a->st_ctim.tv_sec==b->st_ctim.tv_sec&&a->st_ctim.tv_nsec==b->st_ctim.tv_nsec;
}
static const char *a3_regular(const fe_a3_f0_owner *s,unsigned dir,
    const struct stat *st,size_t maximum) {
    if(!S_ISREG(st->st_mode))return "NOFOLLOW_OR_NONREGULAR_REJECT";
    if(st->st_uid!=geteuid()||(st->st_mode&07777)!=0600)
        return "FILE_OWNER_OR_MODE_REJECT";
    if((uint64_t)st->st_dev!=s->device[dir])return "DIRECTORY_IDENTITY_MISMATCH";
    if(st->st_nlink<1u||st->st_nlink>2u)return "UNEXPECTED_LINK_ALIAS_REJECT";
    if(st->st_size<0||(uint64_t)st->st_size>(uint64_t)maximum)
        return "BOUNDED_OBJECT_SIZE_REJECT";
    return NULL;
}
static int a3_directories(fe_a3_f0_owner *s,const fe_a3_f0_authority *a) {
    for(unsigned i=0u;i<2u;++i) {
        struct stat st;
        const uint32_t role=i==A3_DATA?FE_A3_F0_ROLE_DATA_DIR:FE_A3_F0_ROLE_ROOT_DIR;
        if(a3_stat(s,s->dirfd[i],&st,role,0u)!=0)return a3_io_fail(s);
        const int flags=a3_flags(s,s->dirfd[i],role);
        if(flags<0)return a3_io_fail(s);
        if(!S_ISDIR(st.st_mode)||st.st_uid!=geteuid()||
           (st.st_mode&07777)!=0700||(flags&O_DIRECTORY)==0||(flags&O_NOFOLLOW)==0||
           (flags&O_ACCMODE)!=O_RDONLY)return a3_fail(s,"EXCLUSIVE_DIRECTORY_REQUIRED");
        if(s->initialized&&((uint64_t)st.st_dev!=s->device[i]||
           (uint64_t)st.st_ino!=s->inode[i]))
            return a3_fail(s,"DIRECTORY_IDENTITY_MISMATCH");
        if(a&&((uint64_t)st.st_dev!=a->device[i]||(uint64_t)st.st_ino!=a->inode[i]))
            return a3_fail(s,"DIRECTORY_IDENTITY_MISMATCH");
        s->device[i]=(uint64_t)st.st_dev;s->inode[i]=(uint64_t)st.st_ino;
    }
    if(s->device[0]==s->device[1]&&s->inode[0]==s->inode[1])
        return a3_fail(s,"DISTINCT_NAMESPACES_REQUIRED");
    return 0;
}
static int a3_load(fe_a3_f0_owner *s,unsigned dir,const char *name,
    uint8_t *bytes,size_t n,uint32_t links,uint32_t role,uint64_t seq) {
    struct stat before,opened,after,path_after;
    const char *error;
    int bad=0;
    if(!bytes||n>FE_A3_F0_RECORD_BYTES)return a3_fail(s,"BOUNDED_OBJECT_SIZE_REJECT");
    if(a3_statat(s,dir,name,&before,role,seq)!=0)return a3_io_fail(s);
    error=a3_regular(s,dir,&before,n);
    if(error)return a3_fail(s,error);
    if((uint64_t)before.st_size!=(uint64_t)n||(uint64_t)before.st_nlink!=links)
        return a3_fail(s,"OBSERVABLE_FILE_METADATA_MISMATCH");
    const int fd=a3_open(s,dir,name,O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC,role,seq,0u);
    if(fd<0)return a3_io_fail(s);
    if(a3_stat(s,fd,&opened,role,seq)!=0)bad=1;
    else if(!a3_same_stat(&before,&opened)) {
        error="OBSERVABLE_FILE_REPLACEMENT";bad=1;
    }
    if(!bad&&a3_read_all(s,fd,bytes,n,role,seq)!=0)bad=1;
    if(!bad&&a3_stat(s,fd,&after,role,seq)!=0)bad=1;
    if(!bad&&!a3_same_stat(&opened,&after)) {error="OBSERVABLE_FILE_REPLACEMENT";bad=1;}
    if(!bad&&a3_statat(s,dir,name,&path_after,role,seq)!=0)bad=1;
    if(!bad&&!a3_same_stat(&opened,&path_after)) {error="OBSERVABLE_FILE_REPLACEMENT";bad=1;}
    const char *prior=s->last_error;
    if(a3_close(s,fd,role,seq)!=0&&!bad)bad=1;
    if(bad) {
        if(error)return a3_fail(s,error);
        if(prior&&strcmp(prior,"OK")!=0)return a3_fail(s,prior);
        return a3_io_fail(s);
    }
    return 0;
}
static int a3_hex_value(const char *p,size_t n,uint64_t *out) {
    uint64_t value=0u;
    for(size_t i=0u;i<n;++i) {
        const unsigned char c=(unsigned char)p[i];
        uint64_t digit;
        if(c>=(unsigned char)'0'&&c<=(unsigned char)'9')digit=(uint64_t)(c-(unsigned char)'0');
        else if(c>=(unsigned char)'a'&&c<=(unsigned char)'f')digit=(uint64_t)(c-(unsigned char)'a')+10u;
        else return -1;
        if(n<=16u)value=(value<<4u)|digit;
    }
    if(out)*out=value;
    return 0;
}
static int a3_parse_name(fe_a3_f0_owner *s,unsigned dir,const char *name,
    size_t len,uint64_t *seq,uint32_t *flags) {
    uint64_t id=0u,generation=0u,value=0u;
    const char *temp=dir==A3_DATA?FE_A3_F0_DATA_TEMP:FE_A3_F0_ROOT_TEMP;
    if(strcmp(name,temp)==0) {
        if(!s->authority.source_pending)return a3_fail(s,"UNREGISTERED_PENDING_OBJECT");
        if(dir==A3_ROOT&&!s->authority.pending_root_accepted)
            return a3_fail(s,"PENDING_ROOT_NOT_EXTERNALLY_ACCEPTED");
        *seq=s->authority.pending_sequence;*flags=A3_TEMP|A3_PENDING;return 0;
    }
    *flags=A3_FINAL;
    if(dir==A3_DATA) {
        if(len!=180u||(memcmp(name,"fa0-",4u)!=0&&memcmp(name,"fa3-",4u)!=0)||
           name[12]!='-'||name[29]!='-'||name[46]!='-'||name[111]!='-'||
           memcmp(name+176u,".bin",4u)!=0||
           a3_hex_value(name+4u,8u,&id)||a3_hex_value(name+13u,16u,&generation)||
           a3_hex_value(name+30u,16u,&value)||a3_hex_value(name+47u,64u,NULL)||
           a3_hex_value(name+112u,64u,NULL))
            return a3_fail(s,"UNKNOWN_DATA_NAMESPACE_ENTRY");
        if(value<17u||value>49u||((value<=32u)!=(name[2]=='0')))
            return a3_fail(s,"NEW_VALIDATOR_DOMAIN_REJECT");
    } else {
        if(len!=116u||memcmp(name,"a3r1-",5u)!=0||name[13]!='-'||
           name[30]!='-'||name[47]!='-'||memcmp(name+112u,".bin",4u)!=0||
           a3_hex_value(name+5u,8u,&id)||a3_hex_value(name+14u,16u,&generation)||
           a3_hex_value(name+31u,16u,&value)||a3_hex_value(name+48u,64u,NULL))
            return a3_fail(s,"UNKNOWN_ROOT_NAMESPACE_ENTRY");
        if(value>17u)return a3_fail(s,"ROOT_GENERATION_OR_WINDOW_MISMATCH");
        value+=32u;
    }
    if(id!=(uint64_t)s->profile.source.capture_source_id||
       generation!=s->profile.source.source_generation)
        return a3_fail(s,"ORIGINAL_SOURCE_MISMATCH");
    *seq=value;
    if(s->authority.source_pending&&value==s->authority.pending_sequence)*flags|=A3_PENDING;
    return 0;
}

/* A Linux dirent64's first 19 bytes have fixed ABI fields on the registered
 * native and ARM32 Linux targets. Access reclen with memcpy, not an unaligned
 * struct cast. File data is never accepted on d_type or d_ino alone. */
static int a3_inventory(fe_a3_f0_owner *s,unsigned dir,
    uint32_t *count,uint32_t *unique) {
    fe_a3_f0_work *w=a3_work(s);
    const uint32_t role=dir==A3_DATA?FE_A3_F0_ROLE_DATA_ENUM:FE_A3_F0_ROLE_ROOT_ENUM;
    const uint32_t maximum=dir==A3_DATA?18u:3u;
    uint32_t used=0u;
    int bad=0;
    const int fd=a3_open(s,dir,".",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC,role,0u,0u);
    if(fd<0)return a3_io_fail(s);
    memset(w->inventory,0,sizeof(w->inventory));
    for(;;) {
        const ssize_t got=a3_getdents(s,fd,role);
        if(got<0) {if(errno==EINTR)continue;bad=a3_io_fail(s);break;}
        if(got==0)break;
        if((size_t)got>sizeof(w->names)) {bad=a3_fail(s,"BOUNDED_DIRECTORY_READ_REJECT");break;}
        size_t offset=0u;
        while(offset<(size_t)got) {
            const uint8_t *entry=(const uint8_t *)w->names+offset;
            uint16_t reclen=0u;
            if((size_t)got-offset<20u) {bad=a3_fail(s,"DIRECTORY_ENTRY_FORMAT_REJECT");break;}
            memcpy(&reclen,entry+16u,sizeof(reclen));
            if(reclen<20u||(size_t)reclen>(size_t)got-offset) {
                bad=a3_fail(s,"DIRECTORY_ENTRY_FORMAT_REJECT");break;
            }
            const char *name=(const char *)entry+19u;
            const char *end=memchr(name,0,(size_t)reclen-19u);
            if(!end) {bad=a3_fail(s,"DIRECTORY_ENTRY_FORMAT_REJECT");break;}
            const size_t length=(size_t)(end-name);
            offset+=(size_t)reclen;
            if(strcmp(name,".")==0||strcmp(name,"..")==0)continue;
            if(length==0u||length>=192u||used>=maximum) {
                bad=a3_fail(s,"BOUNDED_DIRECTORY_CAPACITY_REJECT");break;
            }
            fe_a3_f0_inventory_entry *v=&w->inventory[used];
            memcpy(v->name,name,length+1u);
            struct stat st;
            if(a3_statat(s,dir,v->name,&st,role,0u)!=0) {bad=a3_io_fail(s);break;}
            const char *error=a3_regular(s,dir,&st,
                dir==A3_DATA?FE_A3_F0_RECORD_BYTES:FE_A3_F0_ROOT_BYTES);
            if(error) {bad=a3_fail(s,error);break;}
            if(st.st_nlink>1u&&!s->authority.source_pending) {
                bad=a3_fail(s,"UNEXPECTED_LINK_ALIAS_REJECT");break;
            }
            if(a3_parse_name(s,dir,v->name,length,&v->sequence,&v->flags)!=0) {
                bad=st.st_nlink>1u?a3_fail(s,"UNEXPECTED_LINK_ALIAS_REJECT"):-1;break;
            }
            if(st.st_nlink>1u&&v->sequence!=s->authority.pending_sequence) {
                bad=a3_fail(s,"UNEXPECTED_LINK_ALIAS_REJECT");break;
            }
            v->device=(uint64_t)st.st_dev;v->inode=(uint64_t)st.st_ino;
            v->bytes=(uint64_t)st.st_size;v->links=(uint32_t)st.st_nlink;
            ++used;
        }
        if(bad)break;
    }
    const char *prior=s->last_error;
    if(a3_close(s,fd,role,0u)!=0&&!bad)bad=a3_io_fail(s);
    if(bad)return a3_fail(s,prior&&strcmp(prior,"OK")!=0?prior:s->last_error);
    uint32_t distinct=0u;
    for(uint32_t i=0u;i<used;++i) {
        uint32_t aliases=0u;int prior_inode=0;
        const fe_a3_f0_inventory_entry *a=&w->inventory[i];
        for(uint32_t j=0u;j<used;++j) {
            const fe_a3_f0_inventory_entry *b=&w->inventory[j];
            const int same=a->device==b->device&&a->inode==b->inode;
            if(same){++aliases;if(j<i)prior_inode=1;}
            if(i==j)continue;
            if(strcmp(a->name,b->name)==0)return a3_fail(s,"DUPLICATE_DIRECTORY_NAME_REJECT");
            if(a->sequence==b->sequence&&!same)
                return a3_fail(s,dir==A3_DATA?"DUPLICATE_ABSOLUTE_SEQUENCE_REJECT":"AMBIGUOUS_ROOT_GENERATION_REJECT");
            if(same&&(!s->authority.source_pending||
               a->sequence!=s->authority.pending_sequence||a->sequence!=b->sequence||
               ((a->flags&A3_TEMP)!=0u)==((b->flags&A3_TEMP)!=0u)))
                return a3_fail(s,"UNEXPECTED_LINK_ALIAS_REJECT");
        }
        if(aliases!=a->links)return a3_fail(s,"UNEXPECTED_LINK_ALIAS_REJECT");
        if(!prior_inode)++distinct;
    }
    if(dir==A3_DATA&&distinct>17u)return a3_fail(s,"BOUNDED_DIRECTORY_CAPACITY_REJECT");
    if(dir==A3_ROOT&&distinct>2u)return a3_fail(s,"BOUNDED_DIRECTORY_CAPACITY_REJECT");
    *count=used;*unique=distinct;return 0;
}
static int a3_find(const fe_a3_f0_work *w,uint32_t count,uint64_t seq,uint32_t flag) {
    for(uint32_t i=0u;i<count;++i)
        if(w->inventory[i].sequence==seq&&(w->inventory[i].flags&flag)!=0u)return (int)i;
    return -1;
}
static void a3_receipt_state(fe_a3_f0_owner *s,fe_a3_f0_receipt *r) {
    r->current_sequence=a3_u64(a3_selected(s)+72u);
    r->pending_sequence=s->authority.source_pending?s->authority.pending_sequence:0u;
    r->packet_bytes=s->packet_bytes;
    r->parent_pending_root_accepted=s->authority.pending_root_accepted;
    r->parent_current_promoted=s->authority.current_promoted;
    r->retiring_data_unlink_observed=s->authority.retiring_data_unlink_observed;
    r->data_retire_sync_observed=s->authority.data_retire_sync_observed;
    r->old_root_unlink_observed=s->authority.old_root_unlink_observed;
    r->root_retire_sync_observed=s->authority.root_retire_sync_observed;
    r->current_call_data_sync=s->current_call_data_sync;
    r->current_call_root_sync=s->current_call_root_sync;
    r->data_publication_synced=s->data_publication_synced;
    r->root_publication_synced=s->root_publication_synced;
    memcpy(r->current_raw_sha256,s->authority.current_raw_sha256,32u);
    if(s->authority.source_pending)
        (void)fe_b1s1_sha256(a3_work(s)->roots[1],FE_A3_F0_ROOT_BYTES,r->pending_raw_sha256);
    r->io=s->io;
}

int fe_a3_f0_init(fe_a3_f0_owner *s,int datafd,int rootfd,
    fe_a3_f0_workspace *workspace,const fe_a3_f0_hooks *hooks) {
    if(!s||!workspace||datafd<0||rootfd<0||
       !a3_apart(s,sizeof(*s),workspace,sizeof(*workspace)))return -1;
    memset(s,0,sizeof(*s));memset(workspace,0,sizeof(*workspace));
    s->dirfd[0]=datafd;s->dirfd[1]=rootfd;s->workspace=workspace;s->last_error="OK";
    if(hooks)s->hooks=*hooks;
    s->phase=FE_A3_F0_READONLY;
    if(a3_directories(s,NULL)!=0)return -1;
    s->initialized=1u;return 0;
}
static int a3_authority_shape(fe_a3_f0_owner *s,const fe_a3_f0_authority *a) {
    if(!a||a->supplied!=1u)return a3_fail(s,"EXTERNAL_AUTHORITY_REQUIRED");
    if(a->source_pending>1u||a->pending_root_accepted>1u||a->current_promoted>1u||
       a->resume_permitted>1u||a->retiring_data_unlink_observed>1u||
       a->data_retire_sync_observed>1u||a->old_root_unlink_observed>1u||
       a->root_retire_sync_observed>1u||a->ack_already_issued>1u)
        return a3_fail(s,"EXTERNAL_AUTHORITY_SHAPE_REJECT");
    if(a->ack_already_issued)return a3_fail(s,"ACK_ALREADY_ISSUED");
    if(a->source_pending) {
        if(!a->worker_incarnation||!a3_nonzero(a->nonce,32u))
            return a3_fail(s,"PENDING_NONCE_AND_INCARNATION_REQUIRED");
    } else if(a->pending_sequence||a->pending_root_accepted||a->current_promoted||
              a->resume_permitted||a->retiring_data_unlink_observed||
              a->data_retire_sync_observed||a->old_root_unlink_observed||
              a->root_retire_sync_observed)
        return a3_fail(s,"EXTERNAL_AUTHORITY_SHAPE_REJECT");
    if((a->current_promoted&&!a->pending_root_accepted)||
       (a->retiring_data_unlink_observed&&!a->current_promoted)||
       (a->data_retire_sync_observed&&!a->retiring_data_unlink_observed)||
       (a->old_root_unlink_observed&&!a->data_retire_sync_observed)||
       (a->root_retire_sync_observed&&!a->old_root_unlink_observed))
        return a3_fail(s,"EXTERNAL_IO_PROVENANCE_ORDER_REJECT");
    return 0;
}
int fe_a3_f0_bind(fe_a3_f0_owner *s,const fe_a3_f0_authority *external,
    const uint8_t previous[FE_A3_F0_ROOT_BYTES],
    const uint8_t parent_pending[FE_A3_F0_ROOT_BYTES],const uint8_t *packet,size_t n) {
    if(!s||!s->initialized||!s->workspace)return a3_fail(s,"UNINITIALIZED_A3_OWNER");
    if(s->bound&&s->mutation_started&&!s->ack_returned)
        return a3_fail(s,"FRESH_WORKER_REQUIRED_AFTER_INCOMPLETE_CALL");
    if(a3_authority_shape(s,external)!=0)return -1;
    fe_a3_f0_authority authority=*external;
    fe_a3_f0_work *w=a3_work(s);
    const int prior_ack=s->ack_returned!=0u;
    if(prior_ack&&authority.source_pending&&memcmp(s->authority.nonce,authority.nonce,32u)==0)
        return a3_fail(s,"PENDING_NONCE_REUSE_REJECT");
    s->bound=0u;s->readonly_checked=0u;s->last_error="OK";s->phase=FE_A3_F0_READONLY;
    if(!previous)return a3_fail(s,"EXTERNAL_AUTHORITY_REQUIRED");
    if(parent_pending&&!a3_apart(parent_pending,FE_A3_F0_ROOT_BYTES,w,sizeof(*w)))
        return a3_fail(s,"PARENT_PENDING_BUFFER_ALIAS_REJECT");
    if(packet&&packet!=w->candidate_record&&!a3_apart(packet,n,w,sizeof(*w)))
        return a3_fail(s,"PENDING_PACKET_BUFFER_ALIAS_REJECT");
    if(a3_directories(s,&authority)!=0)return -1;
    memmove(w->roots[0],previous,FE_A3_F0_ROOT_BYTES);
    const char *error=fe_a3_f0_validate_root(w->roots[0],FE_A3_F0_ROOT_BYTES,
        NULL,NULL,&w->metadata.root,w->readback_record);
    if(error)return a3_fail(s,error);
    s->profile=w->metadata.root.profile;
    if(s->last_ack_sequence&&w->metadata.root.last!=s->last_ack_sequence)
        return a3_fail(s,"EXTERNAL_CURRENT_SEQUENCE_REGRESSION");
    if(authority.source_pending) {
        if(!packet||n<200u||n>FE_A3_F0_RECORD_BYTES||w->metadata.root.last>=49u||
           authority.pending_sequence!=w->metadata.root.last+1u)
            return a3_fail(s,"SINGLE_NEXT_ORIGINAL_PACKET_REQUIRED");
        if(fe_b1s1_sha256(w->roots[0]+3456u,200u,w->digests[0])!=0)
            return a3_fail(s,"ORIGINAL_SHA_REJECT");
        error=fe_a3_f0_validate_record(&s->profile,packet,packet+200u,n-200u,
            authority.pending_sequence,w->digests[0]);
        if(error)return a3_fail(s,error);
        memmove(w->candidate_record,packet,n);
        error=fe_a3_f0_next_root(w->roots[0],w->candidate_record,w->roots[1],w->readback_record);
        if(error)return a3_fail(s,error);
        if(authority.pending_root_accepted) {
            if(!parent_pending||memcmp(parent_pending,w->roots[1],FE_A3_F0_ROOT_BYTES)!=0)
                return a3_fail(s,"PARENT_EXPECTED_NEXT_ROOT_MISMATCH");
        } else if(parent_pending)return a3_fail(s,"UNACCEPTED_PENDING_ROOT_SUPPLIED");
    } else if(packet||n||parent_pending)return a3_fail(s,"UNREGISTERED_PENDING_PACKET");
    const uint8_t *current=w->roots[authority.current_promoted?1u:0u];
    if(fe_b1s1_sha256(current,FE_A3_F0_ROOT_BYTES,w->digests[0])!=0)
        return a3_fail(s,"ORIGINAL_SHA_REJECT");
    if(memcmp(w->digests[0],authority.current_raw_sha256,32u)!=0)
        return a3_fail(s,"EXTERNAL_RAW_ROOT_MISMATCH");
    s->authority=authority;s->packet_bytes=(uint64_t)n;s->ack_returned=0u;
    s->current_call_data_sync=0u;s->current_call_root_sync=0u;
    s->data_publication_synced=0u;s->root_publication_synced=0u;
    s->mutation_started=0u;
    s->bound=1u;return 0;
}

static int a3_verify_record_file(fe_a3_f0_owner *s,
    const fe_a3_f0_inventory_entry *v,const uint8_t row[200],
    const uint8_t previous_whole[32]) {
    fe_a3_f0_work *w=a3_work(s);
    const uint64_t seq=a3_u64(row+48u);
    const size_t bytes=200u+(size_t)a3_u32(row+68u);
    if(bytes>FE_A3_F0_RECORD_BYTES||v->bytes!=(uint64_t)bytes)
        return a3_fail(s,"ORIGINAL_RECORD_SIZE_REJECT");
    if(fe_a3_f0_record_name(row,w->names[0])!=0||strcmp(v->name,w->names[0])!=0)
        return a3_fail(s,"CANONICAL_RECORD_NAME_MISMATCH");
    if(a3_load(s,A3_DATA,v->name,w->readback_record,bytes,v->links,
        FE_A3_F0_ROLE_DATA_FINAL,seq)!=0)return -1;
    if(memcmp(w->readback_record,row,200u)!=0)return a3_fail(s,"ORIGINAL_ROW_BYTES_MISMATCH");
    const char *error=fe_a3_f0_validate_record(&s->profile,w->readback_record,
        w->readback_record+200u,bytes-200u,seq,previous_whole);
    return error?a3_fail(s,error):0;
}
static int a3_data_snapshot(fe_a3_f0_owner *s,fe_a3_f0_receipt *r,
    const char **hold) {
    fe_a3_f0_work *w=a3_work(s);
    if(a3_inventory(s,A3_DATA,&r->data_names,&r->data_unique_inodes)!=0)return -1;
    const uint8_t *current=a3_selected(s);
    const uint64_t first=a3_u64(current+64u),last=a3_u64(current+72u);
    const uint64_t old_first=a3_u64(w->roots[0]+64u);
    if(fe_b1s1_sha256(current+256u,200u,w->digests[0])!=0)
        return a3_fail(s,"ORIGINAL_SHA_REJECT");
    for(unsigned i=0u;i<16u;++i) {
        const uint8_t *row=current+456u+i*200u;
        const int index=a3_find(w,r->data_names,first+i,A3_FINAL);
        if(index<0)return a3_fail(s,"RETAINED_SET_INCOMPLETE");
        if(a3_verify_record_file(s,&w->inventory[(unsigned)index],row,w->digests[0])!=0)
            return -1;
        if(s->authority.source_pending&&first+i==s->authority.pending_sequence&&
           memcmp(w->readback_record,w->candidate_record,(size_t)s->packet_bytes)!=0)
            return a3_fail(s,"PENDING_ORIGINAL_PACKET_MISMATCH");
        if(fe_b1s1_sha256(row,200u,w->digests[0])!=0)return a3_fail(s,"ORIGINAL_SHA_REJECT");
        ++r->retained_files_verified;
    }
    for(uint32_t i=0u;i<r->data_names;++i) {
        const fe_a3_f0_inventory_entry *v=&w->inventory[i];
        const int in_current=v->sequence>=first&&v->sequence<=last;
        const int retiring=s->authority.source_pending&&s->authority.current_promoted&&
            v->sequence==old_first&&(v->flags&A3_FINAL)!=0u;
        const int pending=s->authority.source_pending&&v->sequence==s->authority.pending_sequence;
        if(!in_current&&!retiring&&!pending)return a3_fail(s,"UNREGISTERED_DATA_ENTRY");
        if((v->flags&A3_TEMP)!=0u&&!pending)return a3_fail(s,"UNREGISTERED_PENDING_OBJECT");
        if(retiring) {
            if(fe_b1s1_sha256(w->roots[0]+256u,200u,w->digests[0])!=0)
                return a3_fail(s,"ORIGINAL_SHA_REJECT");
            if(a3_verify_record_file(s,v,w->roots[0]+456u,w->digests[0])!=0)return -1;
        }
        if(pending) {
            const int temp=(v->flags&A3_TEMP)!=0u;
            if(temp)r->data_temp_present=1u;else r->data_final_present=1u;
            if(v->bytes!=s->packet_bytes) {
                if(!temp||v->bytes>s->packet_bytes)return a3_fail(s,"ORIGINAL_RECORD_SIZE_REJECT");
                if(a3_load(s,A3_DATA,v->name,w->readback_record,(size_t)v->bytes,
                    v->links,FE_A3_F0_ROLE_DATA_TEMP,v->sequence)!=0)return -1;
                *hold="INCOMPLETE_PENDING_DATA";
            } else if(!in_current||temp) {
                if(!temp&&fe_a3_f0_record_name(w->candidate_record,w->names[0])!=0)
                    return a3_fail(s,"CANONICAL_RECORD_NAME_MISMATCH");
                if(!temp&&strcmp(v->name,w->names[0])!=0)
                    return a3_fail(s,"CANONICAL_RECORD_NAME_MISMATCH");
                if(a3_load(s,A3_DATA,v->name,w->readback_record,(size_t)s->packet_bytes,
                    v->links,temp?FE_A3_F0_ROLE_DATA_TEMP:FE_A3_F0_ROLE_DATA_FINAL,v->sequence)!=0)
                    return -1;
                if(memcmp(w->readback_record,w->candidate_record,(size_t)s->packet_bytes)!=0)
                    return a3_fail(s,"PENDING_ORIGINAL_PACKET_MISMATCH");
                if(fe_b1s1_sha256(w->roots[0]+3456u,200u,w->digests[0])!=0)
                    return a3_fail(s,"ORIGINAL_SHA_REJECT");
                const char *error=fe_a3_f0_validate_record(&s->profile,w->readback_record,
                    w->readback_record+200u,(size_t)s->packet_bytes-200u,v->sequence,w->digests[0]);
                if(error)return a3_fail(s,error);
                r->pending_data_verified=1u;
            } else r->pending_data_verified=1u;
        }
    }
    if(s->authority.source_pending) {
        r->retiring_data_present=(uint32_t)(a3_find(w,r->data_names,old_first,A3_FINAL)>=0);
        if(s->authority.current_promoted) {
            if(r->data_temp_present)return a3_fail(s,"PROMOTED_PENDING_ALIAS_REJECT");
            if(r->retiring_data_present==s->authority.retiring_data_unlink_observed)
                return a3_fail(s,"EXTERNAL_IO_PROVENANCE_MISMATCH");
        } else if(!r->retiring_data_present)return a3_fail(s,"RETAINED_SET_INCOMPLETE");
    }
    return 0;
}
static int a3_root_snapshot(fe_a3_f0_owner *s,fe_a3_f0_receipt *r,
    const char **hold) {
    fe_a3_f0_work *w=a3_work(s);
    if(a3_inventory(s,A3_ROOT,&r->root_names,&r->root_unique_inodes)!=0)return -1;
    if(fe_a3_f0_root_name(w->roots[0],w->names[0])!=0)return a3_fail(s,"A3_FORMAT_REJECT");
    if(s->authority.source_pending&&fe_a3_f0_root_name(w->roots[1],w->names[1])!=0)
        return a3_fail(s,"A3_FORMAT_REJECT");
    uint32_t prior_present=0u;
    for(uint32_t i=0u;i<r->root_names;++i) {
        const fe_a3_f0_inventory_entry *v=&w->inventory[i];
        const uint8_t *expected=NULL;
        const int temp=(v->flags&A3_TEMP)!=0u;
        if(!temp&&strcmp(v->name,w->names[0])==0) {
            expected=w->roots[0];prior_present=1u;
        } else if(s->authority.source_pending&&
                  (temp||strcmp(v->name,w->names[1])==0)) {
            if(!s->authority.pending_root_accepted)
                return a3_fail(s,"PENDING_ROOT_NOT_EXTERNALLY_ACCEPTED");
            expected=w->roots[1];
            if(temp)r->root_temp_present=1u;else r->root_final_present=1u;
        } else return a3_fail(s,"UNREGISTERED_ROOT_ENTRY");
        if(v->bytes!=FE_A3_F0_ROOT_BYTES) {
            if(!temp||v->bytes>FE_A3_F0_ROOT_BYTES)return a3_fail(s,"A3_FORMAT_REJECT");
            if(a3_load(s,A3_ROOT,v->name,w->readback_record,(size_t)v->bytes,
                v->links,FE_A3_F0_ROLE_ROOT_TEMP,v->sequence)!=0)return -1;
            if(!*hold)*hold="INCOMPLETE_PENDING_ROOT";
            continue;
        }
        if(a3_load(s,A3_ROOT,v->name,w->readback_record,FE_A3_F0_ROOT_BYTES,
            v->links,temp?FE_A3_F0_ROLE_ROOT_TEMP:FE_A3_F0_ROLE_ROOT_FINAL,v->sequence)!=0)
            return -1;
        if(memcmp(w->readback_record,expected,FE_A3_F0_ROOT_BYTES)!=0)
            return a3_fail(s,"EXTERNAL_RAW_ROOT_MISMATCH");
        if(expected==w->roots[1])r->pending_root_verified=1u;
        if(expected==a3_selected(s)&&!temp)r->current_root_verified=1u;
    }
    if(!r->current_root_verified)return a3_fail(s,"EXTERNALLY_SELECTED_ROOT_MISSING");
    if(s->authority.source_pending) {
        r->old_root_present=prior_present;
        if(s->authority.current_promoted) {
            if(r->root_temp_present)return a3_fail(s,"PROMOTED_PENDING_ALIAS_REJECT");
            if(prior_present==s->authority.old_root_unlink_observed)
                return a3_fail(s,"EXTERNAL_IO_PROVENANCE_MISMATCH");
        } else if(!prior_present)return a3_fail(s,"EXTERNALLY_SELECTED_ROOT_MISSING");
        if((r->root_temp_present||r->root_final_present)&&
           (!r->data_final_present||r->data_temp_present||!r->pending_data_verified))
            return a3_fail(s,"ROOT_BEFORE_DATA_PUBLICATION_REJECT");
    }
    return 0;
}
static const char *a3_classification(const fe_a3_f0_owner *s,const fe_a3_f0_receipt *r) {
    if(!s->authority.source_pending)return "CURRENT_ROOT_ONLY_NO_PENDING_SOURCE";
    if(!s->authority.current_promoted) {
        if(r->root_final_present)return "VISIBLE_PENDING_ROOT_NOT_PROMOTED";
        if(r->root_temp_present)return "VISIBLE_COMPLETE_ROOT_TEMP";
        if(r->data_final_present)return "VISIBLE_PENDING_DATA_FINAL";
        if(r->data_temp_present)return "VISIBLE_COMPLETE_DATA_TEMP";
        return "CURRENT_ROOT_ONLY_PENDING_SOURCE";
    }
    if(r->retiring_data_present)return "PROMOTED_ROOT_RETIREMENT_PENDING";
    if(!s->authority.data_retire_sync_observed)return "DATA_UNLINK_VISIBLE_SYNC_UNPROVEN";
    if(r->old_root_present)return "PROMOTED_ROOT_OLD_ROOT_STILL_VISIBLE";
    if(!s->authority.root_retire_sync_observed)return "OLD_ROOT_UNLINK_VISIBLE_SYNC_UNPROVEN";
    return "PROMOTED_ROOT_CURRENT_READBACK_COMPLETE";
}
static int a3_snapshot(fe_a3_f0_owner *s,fe_a3_f0_receipt *r) {
    const char *hold=NULL;
    memset(r,0,sizeof(*r));r->classification="UNVALIDATED";
    if(a3_directories(s,&s->authority)!=0)goto fail;
    if(a3_data_snapshot(s,r,&hold)!=0)goto fail;
    if(a3_root_snapshot(s,r,&hold)!=0)goto fail;
    a3_receipt_state(s,r);
    if(hold) {r->classification=hold;return a3_fail(s,hold);}
    r->classification=a3_classification(s,r);return 0;
fail:
    r->classification=s->last_error;a3_receipt_state(s,r);return -1;
}
int fe_a3_f0_readonly(fe_a3_f0_owner *s,fe_a3_f0_receipt *r) {
    if(!s||!s->initialized||!s->bound)return a3_fail(s,"EXTERNAL_AUTHORITY_REQUIRED");
    if(!r)return a3_fail(s,"RECEIPT_REQUIRED");
    s->phase=FE_A3_F0_READONLY;s->last_error="OK";s->readonly_checked=0u;
    const int result=a3_snapshot(s,r);
    if(result==0)s->readonly_checked=1u;
    /* No filesystem mutator, authorize callback or source ACK occurs here. */
    return result;
}

static int a3_barrier(fe_a3_f0_owner *s,fe_a3_f0_receipt *r,uint32_t point) {
    if(point<1u||point>16u||!s->hooks.barrier)
        return a3_fail(s,"PARENT_CUTPOINT_OBSERVER_REQUIRED");
    a3_receipt_state(s,r);
    r->classification=point==2u?"INCOMPLETE_PENDING_DATA":
        (point==8u?"INCOMPLETE_PENDING_ROOT":a3_classification(s,r));
    if(s->hooks.barrier(point,&s->authority,r,s->hooks.context)!=0)
        return a3_fail(s,"PARENT_CONTINUATION_REJECT");
    return 0;
}
static int a3_authorize(fe_a3_f0_owner *s,fe_a3_f0_receipt *r,uint32_t action) {
    if(!s->hooks.authorize)return a3_fail(s,"EXPLICIT_PARENT_AUTHORIZATION_REQUIRED");
    a3_receipt_state(s,r);r->classification=a3_classification(s,r);
    if(s->hooks.authorize(action,&s->authority,a3_work(s)->roots[1],r,
        s->hooks.context)!=0)return a3_fail(s,"PARENT_AUTHORIZATION_REJECT");
    return 0;
}
static int a3_check_alias(fe_a3_f0_owner *s,unsigned dir,const char *temp,
    const char *final,size_t n,uint32_t role,uint64_t seq) {
    struct stat a,b;
    if(a3_statat(s,dir,temp,&a,role,seq)!=0||a3_statat(s,dir,final,&b,role,seq)!=0)
        return a3_io_fail(s);
    const char *error=a3_regular(s,dir,&a,n);
    if(!error)error=a3_regular(s,dir,&b,n);
    if(error)return a3_fail(s,error);
    if(a.st_dev!=b.st_dev||a.st_ino!=b.st_ino||a.st_nlink!=2u||b.st_nlink!=2u||
       (uint64_t)a.st_size!=(uint64_t)n||(uint64_t)b.st_size!=(uint64_t)n)
        return a3_fail(s,"UNEXPECTED_LINK_ALIAS_REJECT");
    return 0;
}
static int a3_close_preserving(fe_a3_f0_owner *s,int fd,uint32_t role,uint64_t seq,int bad) {
    const char *prior=s->last_error;
    const int result=a3_close(s,fd,role,seq);
    if(bad)return a3_fail(s,prior&&strcmp(prior,"OK")!=0?prior:"HOSTED_IO_ERROR");
    return result==0?0:a3_io_fail(s);
}

/* No-clobber link+unlink is deliberate. rename would overwrite a final
 * name and would erase the registered same-inode C05/C11 alias window. */
static int a3_publish_pending(fe_a3_f0_owner *s,fe_a3_f0_receipt *r,unsigned dir,
    int cuts) {
    fe_a3_f0_work *w=a3_work(s);
    const int root=dir==A3_ROOT;
    const uint8_t *bytes=root?w->roots[1]:w->candidate_record;
    const size_t n=root?FE_A3_F0_ROOT_BYTES:(size_t)s->packet_bytes;
    const uint64_t seq=s->authority.pending_sequence;
    const char *temp=root?FE_A3_F0_ROOT_TEMP:FE_A3_F0_DATA_TEMP;
    const uint32_t role=root?FE_A3_F0_ROLE_ROOT_TEMP:FE_A3_F0_ROLE_DATA_TEMP;
    const uint32_t final_role=root?FE_A3_F0_ROLE_ROOT_FINAL:FE_A3_F0_ROLE_DATA_FINAL;
    uint32_t *has_temp=root?&r->root_temp_present:&r->data_temp_present;
    uint32_t *has_final=root?&r->root_final_present:&r->data_final_present;
    uint32_t *names=root?&r->root_names:&r->data_names;
    uint32_t *unique=root?&r->root_unique_inodes:&r->data_unique_inodes;
    if(root?fe_a3_f0_root_name(bytes,w->names[0]):fe_a3_f0_record_name(bytes,w->names[0]))
        return a3_fail(s,"CANONICAL_OBJECT_NAME_REJECT");
    const char *final=w->names[0];
    int fd=-1,bad=0;
    if(!*has_temp&&!*has_final) {
        if(*unique>=(root?2u:17u)||*names>=(root?3u:18u))
            return a3_fail(s,"RESERVE_CAPACITY_REQUIRED_BEFORE_PRUNE");
        fd=a3_open(s,dir,temp,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,
            role,seq,root?0u:1u);
        if(fd<0)return a3_io_fail(s);
        *has_temp=1u;++*names;++*unique;
        struct stat st;
        if(a3_stat(s,fd,&st,role,seq)!=0)bad=a3_io_fail(s);
        else {
            const char *error=a3_regular(s,dir,&st,0u);
            if(error)bad=a3_fail(s,error);
            else if(st.st_nlink!=1u||st.st_size!=0)bad=a3_fail(s,"EXCLUSIVE_EMPTY_TEMP_REQUIRED");
        }
        if(!bad&&cuts&&a3_barrier(s,r,root?8u:2u)!=0)bad=-1;
        if(!bad&&a3_write_all(s,fd,bytes,n,role,seq,root?6u:2u)!=0)bad=-1;
        if(!bad&&cuts&&a3_barrier(s,r,root?9u:3u)!=0)bad=-1;
    } else {
        const char *path=*has_temp?temp:final;
        const uint32_t fd_role=*has_temp?role:final_role;
        struct stat before,opened;
        if(a3_statat(s,dir,path,&before,fd_role,seq)!=0)return a3_io_fail(s);
        const char *error=a3_regular(s,dir,&before,n);
        if(error)return a3_fail(s,error);
        if((uint64_t)before.st_size!=(uint64_t)n||
           (uint64_t)before.st_nlink!=(uint64_t)(*has_temp&&*has_final?2u:1u))
            return a3_fail(s,"INCOMPLETE_PENDING_OBJECT");
        fd=a3_open(s,dir,path,O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC,fd_role,seq,0u);
        if(fd<0)return a3_io_fail(s);
        if(a3_stat(s,fd,&opened,fd_role,seq)!=0)bad=a3_io_fail(s);
        else if(!a3_same_stat(&before,&opened))bad=a3_fail(s,"OBSERVABLE_FILE_REPLACEMENT");
    }
    if(!bad&&a3_sync(s,fd,*has_temp?role:final_role,seq,root?7u:3u)!=0)
        bad=a3_io_fail(s);
    if(a3_close_preserving(s,fd,*has_temp?role:final_role,seq,bad)!=0)return -1;
    if(*has_temp&&!*has_final&&cuts&&a3_barrier(s,r,root?10u:4u)!=0)return -1;
    if(*has_temp&&!*has_final) {
        if(a3_link(s,dir,temp,final,final_role,seq,root?0u:4u)!=0)return a3_io_fail(s);
        *has_final=1u;++*names;
    }
    if(*has_temp) {
        if(a3_check_alias(s,dir,temp,final,n,role,seq)!=0)return -1;
        if(cuts&&a3_barrier(s,r,root?11u:5u)!=0)return -1;
        if(a3_unlink(s,dir,temp,role,seq,0u)!=0)return a3_io_fail(s);
        *has_temp=0u;--*names;
    }
    if(a3_sync(s,s->dirfd[dir],root?FE_A3_F0_ROLE_ROOT_DIR:FE_A3_F0_ROLE_DATA_DIR,
        seq,root?8u:5u)!=0)return a3_io_fail(s);
    if(a3_load(s,dir,final,w->readback_record,n,1u,final_role,seq)!=0)return -1;
    if(memcmp(w->readback_record,bytes,n)!=0)
        return a3_fail(s,root?"EXTERNAL_RAW_ROOT_MISMATCH":"PENDING_ORIGINAL_PACKET_MISMATCH");
    if(root)r->pending_root_verified=1u;
    else {
        if(fe_b1s1_sha256(w->roots[0]+3456u,200u,w->digests[0])!=0)
            return a3_fail(s,"ORIGINAL_SHA_REJECT");
        const char *error=fe_a3_f0_validate_record(&s->profile,w->readback_record,
            w->readback_record+200u,n-200u,seq,w->digests[0]);
        if(error)return a3_fail(s,error);
        r->pending_data_verified=1u;
    }
    return cuts?a3_barrier(s,r,root?12u:6u):0;
}
static int a3_retire_data(fe_a3_f0_owner *s,fe_a3_f0_receipt *r) {
    fe_a3_f0_work *w=a3_work(s);
    const uint8_t *row=w->roots[0]+456u;
    const uint64_t seq=a3_u64(row+48u);
    if(!s->authority.current_promoted||!r->pending_root_verified||
       !s->root_publication_synced)return a3_fail(s,"PROMOTED_PUBLISHED_ROOT_REQUIRED");
    if(r->retiring_data_present) {
        fe_a3_f0_inventory_entry v;
        struct stat st;
        memset(&v,0,sizeof(v));
        if(fe_a3_f0_record_name(row,v.name)!=0)return a3_fail(s,"CANONICAL_RECORD_NAME_MISMATCH");
        if(a3_statat(s,A3_DATA,v.name,&st,FE_A3_F0_ROLE_RETIRING_DATA,seq)!=0)
            return a3_io_fail(s);
        const char *error=a3_regular(s,A3_DATA,&st,FE_A3_F0_RECORD_BYTES);
        if(error)return a3_fail(s,error);
        if(st.st_nlink!=1u)return a3_fail(s,"UNEXPECTED_LINK_ALIAS_REJECT");
        v.bytes=(uint64_t)st.st_size;v.links=1u;v.sequence=seq;
        if(fe_b1s1_sha256(w->roots[0]+256u,200u,w->digests[0])!=0)
            return a3_fail(s,"ORIGINAL_SHA_REJECT");
        if(a3_verify_record_file(s,&v,row,w->digests[0])!=0)return -1;
        if(a3_unlink(s,A3_DATA,v.name,FE_A3_F0_ROLE_RETIRING_DATA,seq,9u)!=0)
            return a3_io_fail(s);
        r->retiring_data_present=0u;--r->data_names;--r->data_unique_inodes;
        if(a3_barrier(s,r,14u)!=0)return -1;
    } else if(!s->authority.retiring_data_unlink_observed)
        return a3_fail(s,"EXTERNAL_IO_PROVENANCE_REQUIRED");
    if(a3_sync(s,s->dirfd[A3_DATA],FE_A3_F0_ROLE_DATA_DIR,
        s->authority.pending_sequence,10u)!=0)return a3_io_fail(s);
    /* An observed unlink is not rolled back on error, and retired PCM is
     * never fabricated or replayed after this point. Only current16 remain. */
    return a3_snapshot(s,r);
}
static int a3_retire_root(fe_a3_f0_owner *s,fe_a3_f0_receipt *r) {
    fe_a3_f0_work *w=a3_work(s);
    if(!s->current_call_data_sync||r->retained_files_verified!=16u||
       r->data_unique_inodes!=16u||r->data_names!=16u)
        return a3_fail(s,"CURRENT_DATA_RETIREMENT_BARRIER_REQUIRED");
    if(r->old_root_present) {
        if(fe_a3_f0_root_name(w->roots[0],w->names[0])!=0)return a3_fail(s,"A3_FORMAT_REJECT");
        if(a3_load(s,A3_ROOT,w->names[0],w->readback_record,FE_A3_F0_ROOT_BYTES,
            1u,FE_A3_F0_ROLE_OLD_ROOT,a3_u64(w->roots[0]+72u))!=0)return -1;
        if(memcmp(w->readback_record,w->roots[0],FE_A3_F0_ROOT_BYTES)!=0)
            return a3_fail(s,"EXTERNAL_RAW_ROOT_MISMATCH");
        if(a3_unlink(s,A3_ROOT,w->names[0],FE_A3_F0_ROLE_OLD_ROOT,
            a3_u64(w->roots[0]+72u),11u)!=0)return a3_io_fail(s);
        r->old_root_present=0u;--r->root_names;--r->root_unique_inodes;
        if(a3_barrier(s,r,15u)!=0)return -1;
    } else if(!s->authority.old_root_unlink_observed)
        return a3_fail(s,"EXTERNAL_IO_PROVENANCE_REQUIRED");
    if(a3_sync(s,s->dirfd[A3_ROOT],FE_A3_F0_ROLE_ROOT_DIR,
        s->authority.pending_sequence,12u)!=0)return a3_io_fail(s);
    if(a3_snapshot(s,r)!=0)return -1;
    if(r->data_names!=16u||r->data_unique_inodes!=16u||
       r->root_names!=1u||r->root_unique_inodes!=1u||
       r->retained_files_verified!=16u||!r->current_root_verified)
        return a3_fail(s,"FINAL_CURRENT_WINDOW_REJECT");
    return a3_barrier(s,r,16u);
}
static int a3_mutate(fe_a3_f0_owner *s,fe_a3_f0_receipt *r,size_t *ack,int resume) {
    if(ack)*ack=0u;
    if(!s||!s->initialized||!s->bound||!s->authority.source_pending)
        return a3_fail(s,"SINGLE_NEXT_ORIGINAL_PACKET_REQUIRED");
    if(!r||!ack)return a3_fail(s,"RECEIPT_AND_ACK_OUTPUT_REQUIRED");
    if(s->ack_returned||s->authority.ack_already_issued)return a3_fail(s,"ACK_ALREADY_ISSUED");
    if(s->mutation_started)return a3_fail(s,"FRESH_WORKER_REQUIRED_AFTER_INCOMPLETE_CALL");
    if(!s->hooks.io||!s->hooks.barrier||!s->hooks.authorize)
        return a3_fail(s,"SURVIVING_PARENT_PROTOCOL_REQUIRED");
    if(resume) {
        if(!s->authority.resume_permitted||!s->readonly_checked||s->test_fault)
            return a3_fail(s,"EXPLICIT_READONLY_THEN_RESUME_REQUIRED");
    } else if(s->authority.resume_permitted||s->authority.pending_root_accepted||
              s->authority.current_promoted)
        return a3_fail(s,"FRESH_EXPLICIT_RESUME_REQUIRED");
    if(s->test_fault&&(s->profile.physical_k!=1u||s->authority.pending_sequence!=33u))
        return a3_fail(s,"REGISTERED_IO_FAULT_DOMAIN_REJECT");
    s->mutation_started=1u;s->phase=resume?FE_A3_F0_RESUME:FE_A3_F0_SLIDE;
    s->last_error="OK";
    if(a3_snapshot(s,r)!=0)goto failed;
    if(!resume&&(r->data_temp_present||r->data_final_present||
       r->root_temp_present||r->root_final_present)) {
        (void)a3_fail(s,"INITIAL_CALL_REQUIRES_EMPTY_PENDING_NAMES");goto failed;
    }
    const int promoted=s->authority.current_promoted!=0u;
    if(promoted&&a3_authorize(s,r,FE_A3_F0_RESUME_PROMOTED)!=0)goto failed;
    if(!r->data_temp_present&&!r->data_final_present&&a3_barrier(s,r,1u)!=0)goto failed;
    if(a3_publish_pending(s,r,A3_DATA,!promoted)!=0)goto failed;
    if(!s->authority.pending_root_accepted) {
        if(a3_authorize(s,r,FE_A3_F0_PROPOSE)!=0)goto failed;
        s->authority.pending_root_accepted=1u;
    }
    if(!r->root_temp_present&&!r->root_final_present&&a3_barrier(s,r,7u)!=0)goto failed;
    if(a3_publish_pending(s,r,A3_ROOT,!promoted)!=0)goto failed;
    if(!promoted) {
        if(!s->data_publication_synced||!s->root_publication_synced||
           !r->pending_data_verified||!r->pending_root_verified||
           r->data_temp_present||r->root_temp_present) {
            (void)a3_fail(s,"PARENT_PROMOTION_PRECONDITIONS_REJECT");goto failed;
        }
        if(a3_authorize(s,r,FE_A3_F0_PROMOTE)!=0)goto failed;
        s->authority.current_promoted=1u;
        if(fe_b1s1_sha256(a3_work(s)->roots[1],FE_A3_F0_ROOT_BYTES,
            s->authority.current_raw_sha256)!=0) {
            (void)a3_fail(s,"ORIGINAL_SHA_REJECT");goto failed;
        }
        r->current_root_verified=1u;r->retained_files_verified=0u;
        if(a3_barrier(s,r,13u)!=0)goto failed;
    }
    if(a3_retire_data(s,r)!=0||a3_retire_root(s,r)!=0)goto failed;
    if(!s->current_call_data_sync||!s->current_call_root_sync||
       !s->authority.current_promoted||!s->authority.retiring_data_unlink_observed||
       !s->authority.old_root_unlink_observed) {
        (void)a3_fail(s,"FINAL_SAME_CALL_COMMIT_BARRIERS_REQUIRED");goto failed;
    }
    if(a3_authorize(s,r,FE_A3_F0_FINAL_AUTHORIZE)!=0)goto failed;
    r->final_authorized=1u;s->ack_returned=1u;s->authority.ack_already_issued=1u;
    s->last_ack_sequence=s->authority.pending_sequence;
    *ack=(size_t)s->packet_bytes;r->ack_bytes=s->packet_bytes;r->byte_ack_issued=1u;
    /* Returning exact bytes is the sole worker ACK. It does NOT prove the
     * original S1 drain received it or advanced its tail; that owner alone
     * supplies the eventual source-ACK observation in the driver. */
    r->source_ack_proven=0u;a3_receipt_state(s,r);return 0;
failed:
    r->classification=s->last_error;r->final_authorized=0u;
    r->byte_ack_issued=0u;r->source_ack_proven=0u;r->ack_bytes=0u;
    a3_receipt_state(s,r);return -1;
}
int fe_a3_f0_slide(fe_a3_f0_owner *s,fe_a3_f0_receipt *r,size_t *ack) {
    return a3_mutate(s,r,ack,0);
}
int fe_a3_f0_resume(fe_a3_f0_owner *s,fe_a3_f0_receipt *r,size_t *ack) {
    return a3_mutate(s,r,ack,1);
}

static void a3_genesis_header(uint8_t root[FE_A3_F0_ROOT_BYTES],
    const fe_a3_f0_profile *p,const uint8_t original_fpr1_raw[32]) {
    memset(root,0,FE_A3_F0_ROOT_BYTES);
    a3_p32(root,FE_A3_F0_MAGIC);a3_p32(root+4u,1u);a3_p32(root+8u,256u);
    a3_p32(root+12u,FE_A3_F0_ROOT_BYTES);a3_p32(root+16u,16u);
    a3_p32(root+20u,200u);a3_p32(root+28u,p->source.physical_mics);
    a3_p64(root+32u,p->source.source_generation);
    a3_p32(root+40u,p->source.capture_source_id);a3_p32(root+44u,p->source.render_source_id);
    a3_p32(root+48u,p->source.input_hz);a3_p32(root+52u,p->source.render_enabled);
    a3_p32(root+56u,p->source.depth);a3_p32(root+60u,p->physical_k);
    a3_p64(root+64u,17u);a3_p64(root+72u,32u);a3_p64(root+80u,32u);
    a3_p64(root+96u,16u);a3_p32(root+104u,16u);a3_p32(root+108u,17u);
    for(unsigned i=0u;i<4u;++i)a3_p32(root+112u+4u*i,p->slots[i]);
    memcpy(root+160u,original_fpr1_raw,32u);
}
static int a3_publish_genesis(fe_a3_f0_owner *s) {
    fe_a3_f0_work *w=a3_work(s);
    if(fe_a3_f0_root_name(w->roots[0],w->names[0])!=0)return a3_fail(s,"A3_FORMAT_REJECT");
    const int fd=a3_open(s,A3_ROOT,FE_A3_F0_ROOT_TEMP,
        O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,FE_A3_F0_ROLE_ROOT_TEMP,32u,0u);
    if(fd<0)return a3_io_fail(s);
    int bad=0;
    struct stat st;
    if(a3_stat(s,fd,&st,FE_A3_F0_ROLE_ROOT_TEMP,32u)!=0)bad=a3_io_fail(s);
    else {
        const char *error=a3_regular(s,A3_ROOT,&st,0u);
        if(error)bad=a3_fail(s,error);
        else if(st.st_nlink!=1u||st.st_size!=0)bad=a3_fail(s,"EXCLUSIVE_EMPTY_TEMP_REQUIRED");
    }
    if(!bad&&a3_write_all(s,fd,w->roots[0],FE_A3_F0_ROOT_BYTES,
        FE_A3_F0_ROLE_ROOT_TEMP,32u,0u)!=0)bad=-1;
    if(!bad&&a3_sync(s,fd,FE_A3_F0_ROLE_ROOT_TEMP,32u,0u)!=0)bad=a3_io_fail(s);
    if(a3_close_preserving(s,fd,FE_A3_F0_ROLE_ROOT_TEMP,32u,bad)!=0)return -1;
    if(a3_link(s,A3_ROOT,FE_A3_F0_ROOT_TEMP,w->names[0],
        FE_A3_F0_ROLE_ROOT_FINAL,32u,0u)!=0)return a3_io_fail(s);
    if(a3_check_alias(s,A3_ROOT,FE_A3_F0_ROOT_TEMP,w->names[0],
        FE_A3_F0_ROOT_BYTES,FE_A3_F0_ROLE_ROOT_TEMP,32u)!=0)return -1;
    if(a3_unlink(s,A3_ROOT,FE_A3_F0_ROOT_TEMP,FE_A3_F0_ROLE_ROOT_TEMP,32u,0u)!=0)
        return a3_io_fail(s);
    if(a3_sync(s,s->dirfd[A3_ROOT],FE_A3_F0_ROLE_ROOT_DIR,32u,0u)!=0)return a3_io_fail(s);
    if(a3_load(s,A3_ROOT,w->names[0],w->readback_record,FE_A3_F0_ROOT_BYTES,
        1u,FE_A3_F0_ROLE_ROOT_FINAL,32u)!=0)return -1;
    if(memcmp(w->roots[0],w->readback_record,FE_A3_F0_ROOT_BYTES)!=0)
        return a3_fail(s,"GENESIS_ROOT_READBACK_MISMATCH");
    return 0;
}
int fe_a3_f0_genesis(fe_a3_f0_owner *s,fe_t3b1ba2_owner *original,
    const fe_t3b1ba2_anchor *anchor,uint32_t k,fe_a3_f0_receipt *r) {
    fe_t3b1ba2_receipt original_receipt;
    fe_t3b1ba2_checkpoint checkpoint;
    const char *error;
    if(!s||!s->initialized||!s->workspace)return a3_fail(s,"UNINITIALIZED_A3_OWNER");
    if(!r)return a3_fail(s,"RECEIPT_REQUIRED");
    memset(r,0,sizeof(*r));r->classification="UNVALIDATED_GENESIS";
    if(s->bound||s->test_fault||s->ack_returned||s->mutation_started)
        return a3_fail(s,"FRESH_GENESIS_OWNER_REQUIRED");
    if(!original||!anchor||!original->workspace||!original->initialized||
       !original->prepared||!original->anchor_bound||
       original->phase!=FE_T3B1BA2_RESUME||
       strcmp(fe_t3b1ba2_error(original),"OK")!=0||
       original->io.successful_data_unlinks!=16u||
       !a3_apart(s->workspace,sizeof(*s->workspace),original->workspace,sizeof(*original->workspace)))
        return a3_fail(s,"ACTUAL_ORIGINAL_A2_RESUME_REQUIRED");
    s->phase=FE_A3_F0_GENESIS;s->last_error="OK";s->mutation_started=1u;
    if(a3_directories(s,NULL)!=0)goto failed;
    if(anchor->device[0]!=s->device[A3_DATA]||anchor->inode[0]!=s->inode[A3_DATA]||
       (anchor->device[1]==s->device[A3_ROOT]&&anchor->inode[1]==s->inode[A3_ROOT])||
       (anchor->device[2]==s->device[A3_ROOT]&&anchor->inode[2]==s->inode[A3_ROOT])) {
        (void)a3_fail(s,"DIRECTORY_IDENTITY_MISMATCH");goto failed;
    }
    /* The original A2 read traverses its ORIGINAL FRM2/FPR1 namespaces,
     * validates the external anchor and replays actual retained PCM. */
    if(fe_t3b1ba2_read(original,anchor,&original_receipt)!=0) {
        (void)a3_fail(s,fe_t3b1ba2_error(original));goto failed;
    }
    if(original_receipt.retained_files_verified!=16u||
       original_receipt.remaining_retired_files_verified!=0u||
       !original_receipt.missing_prefix_known||original_receipt.missing_prefix!=16u||
       original_receipt.source_ack_proven||original_receipt.live_source_observation) {
        (void)a3_fail(s,"ACTUAL_ORIGINAL_RETIREMENT_REQUIRED");goto failed;
    }
    const uint8_t *fpr1=fe_t3b1ba2_prepared_bytes(original);
    if(!fpr1) {(void)a3_fail(s,"ORIGINAL_FPR1_BYTES_REQUIRED");goto failed;}
    error=fe_t3b1ba2_validate_checkpoint(fpr1,FE_T3B1BA2_CHECKPOINT_BYTES,&checkpoint);
    if(error) {(void)a3_fail(s,error);goto failed;}
    if(memcmp(checkpoint.checkpoint_raw_sha256,anchor->checkpoint_raw_sha256,32u)!=0) {
        (void)a3_fail(s,"ORIGINAL_FPR1_EXTERNAL_RAW_SHA_MISMATCH");goto failed;
    }
    s->profile.source=checkpoint.source;memcpy(s->profile.slots,checkpoint.slots,sizeof(checkpoint.slots));
    s->profile.physical_k=k;
    error=fe_a3_f0_validate_profile(&s->profile);
    if(error) {(void)a3_fail(s,error);goto failed;}
    fe_a3_f0_work *w=a3_work(s);
    if(a3_inventory(s,A3_ROOT,&r->root_names,&r->root_unique_inodes)!=0)goto failed;
    if(r->root_names!=0u) {(void)a3_fail(s,"EMPTY_GENESIS_ROOT_NAMESPACE_REQUIRED");goto failed;}
    if(a3_inventory(s,A3_DATA,&r->data_names,&r->data_unique_inodes)!=0)goto failed;
    if(r->data_names!=16u||r->data_unique_inodes!=16u) {
        (void)a3_fail(s,"ACTUAL_ORIGINAL_RETAINED_SET_REQUIRED");goto failed;
    }
    a3_genesis_header(w->roots[0],&s->profile,checkpoint.checkpoint_raw_sha256);
    memcpy(w->roots[0]+256u,fpr1+4568u,200u);
    if(fe_b1s1_sha256(w->roots[0]+256u,200u,w->digests[0])!=0) {
        (void)a3_fail(s,"ORIGINAL_SHA_REJECT");goto failed;
    }
    for(unsigned i=0u;i<16u;++i) {
        const uint64_t seq=(uint64_t)i+17u;
        const uint8_t *member=fpr1+192u+224u+72u*i;
        const int index=a3_find(w,r->data_names,seq,A3_FINAL);
        if(index<0||a3_u64(member)!=seq) {
            (void)a3_fail(s,"ACTUAL_ORIGINAL_RETAINED_SET_REQUIRED");goto failed;
        }
        const fe_a3_f0_inventory_entry *v=&w->inventory[(unsigned)index];
        if(fe_t3b1ba0_name(s->profile.source.capture_source_id,
            s->profile.source.source_generation,seq,member+8u,member+40u,w->names[0])!=0||
           strcmp(w->names[0],v->name)!=0||v->bytes!=1960u||v->links!=1u) {
            (void)a3_fail(s,"ORIGINAL_FRM2_MEMBER_MISMATCH");goto failed;
        }
        if(a3_load(s,A3_DATA,v->name,w->readback_record,1960u,1u,
            FE_A3_F0_ROLE_DATA_FINAL,seq)!=0)goto failed;
        error=fe_a3_f0_validate_record(&s->profile,w->readback_record,
            w->readback_record+200u,1760u,seq,w->digests[0]);
        if(error) {(void)a3_fail(s,error);goto failed;}
        if(fe_b1s1_sha256(w->readback_record,200u,w->digests[0])!=0||
           memcmp(w->digests[0],member+8u,32u)!=0||
           memcmp(w->readback_record+104u,member+40u,32u)!=0) {
            (void)a3_fail(s,"ORIGINAL_FRM2_MEMBER_MISMATCH");goto failed;
        }
        memcpy(w->roots[0]+456u+200u*i,w->readback_record,200u);
        ++r->retained_files_verified;
    }
    if(fe_b1s1_sha256(w->roots[0],FE_A3_F0_ROOT_BYTES,w->digests[0])!=0) {
        (void)a3_fail(s,"ORIGINAL_SHA_REJECT");goto failed;
    }
    memcpy(w->roots[0]+192u,w->digests[0],32u);
    error=fe_a3_f0_validate_root(w->roots[0],FE_A3_F0_ROOT_BYTES,&s->profile,
        NULL,&w->metadata.root,w->readback_record);
    if(error) {(void)a3_fail(s,error);goto failed;}
    if(a3_publish_genesis(s)!=0)goto failed;
    if(a3_inventory(s,A3_ROOT,&r->root_names,&r->root_unique_inodes)!=0)goto failed;
    if(r->root_names!=1u||r->root_unique_inodes!=1u) {
        (void)a3_fail(s,"GENESIS_ROOT_NAMESPACE_REJECT");goto failed;
    }
    r->current_sequence=32u;r->current_root_verified=1u;
    memcpy(r->current_raw_sha256,w->metadata.root.raw_sha256,32u);
    r->classification="GENESIS_FROM_ACTUAL_ORIGINAL_A2";r->io=s->io;
    /* Initial R32 is only metadata. Parent must supply its separate current
     * authority in bind before any source33 packet is considered. */
    s->mutation_started=0u;return 0;
failed:
    r->classification=s->last_error;r->io=s->io;return -1;
}
int fe_a3_f0_set_test_fault(fe_a3_f0_owner *s,uint32_t fault) {
    if(!s||!s->initialized||fault>12u||s->fault_fired||s->mutation_started)
        return a3_fail(s,"REGISTERED_IO_FAULT_DOMAIN_REJECT");
    if(fault&&s->bound&&(s->profile.physical_k!=1u||
       s->authority.pending_sequence!=33u||!s->authority.source_pending))
        return a3_fail(s,"REGISTERED_IO_FAULT_DOMAIN_REJECT");
    s->test_fault=fault;return 0;
}
const char *fe_a3_f0_error(const fe_a3_f0_owner *s) {
    return s&&s->last_error?s->last_error:"UNINITIALIZED_A3_OWNER";
}
const char *fe_a3_f0_error_class(const char *error) {
    if(!error)return "OK";
    if(strcmp(error,"INCOMPLETE_PENDING_DATA")==0||
       strcmp(error,"INCOMPLETE_PENDING_ROOT")==0)
        return "INCOMPLETE_PENDING_OBJECT";
    return error;
}
size_t fe_a3_f0_workspace_used_bytes(void) {return sizeof(fe_a3_f0_work);}
size_t fe_a3_f0_resource_bytes(void) {return FE_A3_F0_RESOURCE_BYTES;}
