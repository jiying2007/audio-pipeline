/* #803: FE09 A0 isolated immutable finite original first-party APX3/FBS1
 * HOSTED POSIX sink. Deliberately not a rolling recorder or product code.
 * S1 consumer already validates original APX3/SHA/FBS1 before the callback;
 * independent restart/readback must re-run original S2 parser/replayer.
 */
#define _POSIX_C_SOURCE 200809L
#include "fe09_b2s3_t3s2b1ba0_finite_outboard.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define A0_FILENAME_LEN 180u
#define A0_FNV0 UINT64_C(14695981039346656037)
#define A0_FNV1 UINT64_C(1099511628211)

static uint32_t g32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1]<<8u |
           (uint32_t)p[2]<<16u | (uint32_t)p[3]<<24u;
}
static uint64_t g64(const uint8_t *p) {
    return (uint64_t)g32(p) | ((uint64_t)g32(p+4u)<<32u);
}
static void hex32(const uint8_t raw[32],char out[65]) {
    static const char lut[]="0123456789abcdef";
    for(size_t i=0u;i<32u;++i) {
        out[2u*i]=lut[raw[i]>>4u];
        out[2u*i+1u]=lut[raw[i]&15u];
    }
    out[64u]='\0';
}
int fe_t3b1ba0_name(uint32_t id,uint64_t gen,uint64_t seq,
    const uint8_t row_sha[32],const uint8_t apx_sha[32],
    char out[FE_T3B1BA0_NAME_CAP]) {
    char r[65],a[65];
    int n;
    if(!id||!gen||gen==UINT64_MAX||!seq||seq>FE_T3B1BA0_MAX_RECORDS||
       !row_sha||!apx_sha||!out)return -1;
    hex32(row_sha,r);hex32(apx_sha,a);
    n=snprintf(out,FE_T3B1BA0_NAME_CAP,
      "fa0-%08" PRIx32 "-%016" PRIx64 "-%016" PRIx64 "-%s-%s.bin",
      id,gen,seq,r,a);
    return n==(int)A0_FILENAME_LEN ? 0:-1;
}
static int source_ok(const fe_b1s0_config *c,const uint32_t slots[4]) {
    uint32_t seen=0u;
    if(!c||!slots||(c->depth!=2u&&c->depth!=4u)||
       (c->physical_mics!=1u&&c->physical_mics!=2u&&
        c->physical_mics!=4u)||
       (c->input_hz!=16000u&&c->input_hz!=32000u&&
        c->input_hz!=48000u)||c->render_enabled>1u||
       !c->capture_source_id||!c->source_generation||
       c->source_generation==UINT64_MAX||
       (c->render_enabled?
          (!c->render_source_id||
           c->render_source_id==c->capture_source_id):
          c->render_source_id!=0u))return 0;
    for(unsigned i=0u;i<4u;++i) {
        if(i>=c->physical_mics) {
            if(slots[i]!=UINT32_MAX)return 0;
        } else {
            if(slots[i]>=c->physical_mics||(seen&(1u<<slots[i])))
                return 0;
            seen|=1u<<slots[i];
        }
    }
    return seen==((1u<<c->physical_mics)-1u);
}
static int same_fd(const fe_t3b1ba0_owner *s) {
    struct stat st;
    int flags;
    if(!s||s->binding_complete!=1u||s->dirfd<0||
       fstat(s->dirfd,&st)!=0||!S_ISDIR(st.st_mode)||
       st.st_uid!=geteuid()||(st.st_mode&0022)!=0||
       st.st_dev!=s->device||st.st_ino!=s->inode ||
       (flags=fcntl(s->dirfd,F_GETFL))<0)
        return 0;
    return (flags&O_DIRECTORY)!=0;
}
static int read_all(int fd,uint8_t *p,size_t size) {
    while(size) {
        ssize_t n=read(fd,p,size);
        if(n<0&&errno==EINTR)continue;
        if(n<=0)return -1;
        size-=(size_t)n;p+=(size_t)n;
    }
    return 0;
}
static int write_all(int fd,const uint8_t *p,size_t size) {
    while(size) {
        ssize_t n=write(fd,p,size);
        if(n<0&&errno==EINTR)continue;
        if(n<=0)return -1;
        size-=(size_t)n;p+=(size_t)n;
    }
    return 0;
}
typedef struct {
    uint64_t capture_hash,render_hash;
    uint32_t rate,mics,render,seen;
} a0_witness;
static uint64_t fnv_le(const uint8_t *p,size_t n) {
    uint64_t h=A0_FNV0;
    for(size_t i=0u;i<n;++i)h=(h^(uint64_t)p[i])*A0_FNV1;
    return h;
}
static int original_pcm(const fe_s2_stream *stream,uint32_t index,
    uint64_t local_seq,uint32_t capture_flags,uint32_t render_flags,
    const uint8_t *pcm,size_t count,const uint8_t *render,size_t nref,
    void *context) {
    a0_witness *w=(a0_witness *)context;
    if(!stream||!w||index||local_seq!=UINT64_C(1)||
       capture_flags||render_flags||stream->frames!=1u||
       stream->config.rate_hz!=w->rate||
       stream->config.physical_mics!=w->mics||
       stream->config.render_channels!=w->render||
       count!=(size_t)w->rate*w->mics/50u||
       nref!=(size_t)w->rate*w->render/50u||!pcm||
       fnv_le(pcm,count)!=w->capture_hash||
       (nref?(!render||fnv_le(render,nref)!=w->render_hash):
              (render!=NULL||w->render_hash!=UINT64_C(0))))
        return 1;
    w->seen=1u;
    return 0;
}
static int valid_record(const fe_t3b1ba0_owner *s,
    const uint8_t row[FE_T3S1_ROW_BYTES],const uint8_t *apx,size_t n,
    uint64_t seq,const uint8_t prev[32]) {
    uint8_t h[32];
    uint32_t event,with_render,epoch;
    fe_s2_stream decoded;
    a0_witness w;
    if(!s||!row||!apx||!prev||!seq||n==0u||
       n>FE_T3S1_CHUNK_BYTES||
       g32(row)!=FE_B1S1_MANIFEST_MAGIC||
       g32(row+4u)!=FE_B1S1_MANIFEST_VERSION||
       g32(row+12u)!=s->source.input_hz||
       g32(row+16u)!=s->source.physical_mics||
       g64(row+20u)!=s->source.source_generation||
       g32(row+28u)!=s->source.capture_source_id||
       g32(row+32u)!=s->source.render_source_id||
       g32(row+36u)!=1u||g64(row+48u)!=seq||
       g64(row+56u)!=UINT64_C(1)||
       g32(row+64u)!=1u||g32(row+68u)!=(uint32_t)n||
       memcmp(row+136u,prev,32u)!=0)
        return 0;
    event=g32(row+8u);
    if(event>FE_B1S0_RENDER_ABSENT||
       (s->source.render_enabled?
          event==FE_B1S0_RENDER_DISABLED:
          event!=FE_B1S0_RENDER_DISABLED))
        return 0;
    epoch=g32(row+40u);
    if((s->source.render_enabled&&epoch==0u)||
       (!s->source.render_enabled&&epoch!=0u)||
       (event==FE_B1S0_RENDER_ABSENT?
          g32(row+44u)!=FE_B1S0_ABSENT_SOURCE_REPORTED:
          g32(row+44u)!=0u))
        return 0;
    with_render=(uint32_t)(event==FE_B1S0_RENDER_PRESENT);
    if((!with_render&&g64(row+80u)!=UINT64_C(0))||
       fe_b1s1_sha256(row,FE_B1S1_ROW_DIGEST_OFFSET,h)!=0||
       memcmp(h,row+FE_B1S1_ROW_DIGEST_OFFSET,32u)!=0||
       fe_b1s1_sha256(apx,n,h)!=0||memcmp(h,row+104u,32u)!=0||
       fe_s2_decode(apx,n,&decoded)!=FE_S2_OK||
       decoded.frames!=1u||decoded.total_bytes!=n||
       decoded.config.rate_hz!=s->source.input_hz||
       decoded.config.physical_mics!=s->source.physical_mics||
       decoded.config.render_channels!=with_render||
       decoded.config.capture_source_id!=s->source.capture_source_id||
       decoded.config.render_source_id!=(with_render?
           s->source.render_source_id:0u)||
       decoded.config.capture_epoch!=1u||
       decoded.config.render_epoch!=(with_render?epoch:0u)||
       decoded.config.clock_authority||
       decoded.config.capture_timestamp_valid||
       decoded.config.render_timestamp_valid)
        return 0;
    for(unsigned i=0u;i<4u;++i)
        if(g32(row+88u+4u*i)!=s->slots[i]||
           decoded.config.physical_to_capture_slot[i]!=s->slots[i])
            return 0;
    memset(&w,0,sizeof(w));
    w.rate=s->source.input_hz;
    w.mics=s->source.physical_mics;
    w.render=with_render;
    w.capture_hash=g64(row+72u);
    w.render_hash=g64(row+80u);
    return fe_s2_replay(apx,n,original_pcm,&w,NULL)==FE_S2_OK&&
           w.seen==1u;
}
static int expected_name(const fe_t3b1ba0_owner *s,uint64_t seq,
    const uint8_t row[FE_T3S1_ROW_BYTES],
    const uint8_t *apx,size_t n,
    char name[FE_T3B1BA0_NAME_CAP]) {
    uint8_t row_sha[32],apx_sha[32];
    if(fe_b1s1_sha256(row,FE_T3S1_ROW_BYTES,row_sha)!=0||
       fe_b1s1_sha256(apx,n,apx_sha)!=0)return -1;
    return fe_t3b1ba0_name(s->source.capture_source_id,
        s->source.source_generation,seq,row_sha,apx_sha,name);
}
static int load_record(const fe_t3b1ba0_owner *s,const char *name,
    uint64_t seq,const uint8_t prev[32],
    uint8_t returned_row[FE_T3S1_ROW_BYTES]) {
    uint8_t row[FE_T3S1_ROW_BYTES],apx[FE_T3S1_CHUNK_BYTES];
    char derived[FE_T3B1BA0_NAME_CAP];
    struct stat st;
    uint32_t n;
    int fd;
    if(!name||strlen(name)!=A0_FILENAME_LEN||
       !same_fd(s))return -1;
    fd=openat(s->dirfd,name,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    if(fd<0)return -1;
    if(fstat(fd,&st)!=0||!S_ISREG(st.st_mode)||st.st_uid!=geteuid()||
       st.st_nlink!=1||st.st_size<=(off_t)FE_T3S1_ROW_BYTES||
       st.st_size>(off_t)(FE_T3S1_ROW_BYTES+FE_T3S1_CHUNK_BYTES)||
       (st.st_mode&07777)!=0600||
       read_all(fd,row,sizeof(row))!=0) {
        (void)close(fd);return -1;
    }
    n=g32(row+68u);
    if(!n||n>FE_T3S1_CHUNK_BYTES||
       st.st_size!=(off_t)((size_t)n+sizeof(row))||
       read_all(fd,apx,n)!=0) {
        (void)close(fd);return -1;
    }
    if(close(fd)!=0)return -1;
    if(!valid_record(s,row,apx,n,seq,prev)||
       expected_name(s,seq,row,apx,n,derived)!=0||
       strcmp(name,derived)!=0)
        return -1;
    memcpy(returned_row,row,sizeof(row));
    return 0;
}
/* Canonical immutable name has fixed offsets; the recomputed original
 * file and complete row SHA are checked separately by load_record.
 */
static int parse_sequence(const char *name,uint64_t *seq) {
    uint64_t x=UINT64_C(0);
    const char *hex="0123456789abcdef";
    if(!name||!seq||strlen(name)!=A0_FILENAME_LEN||
       strncmp(name,"fa0-",4u)!=0||
       name[12]!='-'||name[29]!='-'||name[46]!='-'||
       name[111]!='-'||strcmp(name+176u,".bin")!=0)return -1;
    for(size_t i=30u;i<46u;++i) {
        const char *p=strchr(hex,name[i]);
        if(!p)return -1;
        x=(x<<4u)|(uint64_t)(p-hex);
    }
    if(x<UINT64_C(1)||x>FE_T3B1BA0_MAX_RECORDS)return -1;
    *seq=x;return 0;
}
static int inventory(fe_t3b1ba0_owner *s) {
    uint8_t seen[FE_T3B1BA0_MAX_RECORDS+1u]={0};
    char names[FE_T3B1BA0_MAX_RECORDS+1u][FE_T3B1BA0_NAME_CAP];
    uint8_t row[FE_T3S1_ROW_BYTES],prior[32]={0};
    uint64_t high=UINT64_C(0),seq;
    int duplicate=openat(s->dirfd,".",
        O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(duplicate<0)return -1;
    DIR *d=fdopendir(duplicate);
    if(!d){(void)close(duplicate);return -1;}
    errno=0;
    struct dirent *entry;
    int failure=0;
    while((entry=readdir(d))!=NULL) {
        const char *name=entry->d_name;
        if(strcmp(name,".")==0||strcmp(name,"..")==0)continue;
        if(parse_sequence(name,&seq)!=0||seq>s->cap||seen[seq]||
           strlen(name)>=FE_T3B1BA0_NAME_CAP) {
            failure=1;break;
        }
        seen[seq]=1u;
        strcpy(names[seq],name);
        if(seq>high)high=seq;
    }
    if(errno!=0)failure=1;
    if(closedir(d)!=0)failure=1;
    if(failure)return -1;
    for(uint64_t n=UINT64_C(1);n<=high;++n) {
        if(!seen[n]||load_record(s,names[n],n,prior,row)!=0)return -1;
        if(fe_b1s1_sha256(row,FE_T3S1_ROW_BYTES,prior)!=0)return -1;
        memcpy(s->last_row,row,sizeof(row));
    }
    s->committed=high;
    s->restart_recovered=high?1u:0u;
    return 0;
}
int fe_t3b1ba0_bind(fe_t3b1ba0_owner *result,int fd,
    const fe_b1s0_config *source,const uint32_t slots[4],uint32_t cap) {
    fe_t3b1ba0_owner candidate;
    struct stat st;
    int flags;
    if(!result||fd<0||cap<FE_T3B1BA0_MIN_RECORDS||
       cap>FE_T3B1BA0_MAX_RECORDS||!source_ok(source,slots)||
       fstat(fd,&st)!=0||!S_ISDIR(st.st_mode)||st.st_uid!=geteuid()||
       (st.st_mode&0022)!=0||(flags=fcntl(fd,F_GETFL))<0||
       (flags&O_DIRECTORY)==0)
        return -1;
    memset(&candidate,0,sizeof(candidate));
    candidate.dirfd=fd;candidate.device=st.st_dev;candidate.inode=st.st_ino;
    candidate.source=*source;candidate.cap=cap;
    memcpy(candidate.slots,slots,sizeof(candidate.slots));
    candidate.binding_complete=1u;
    if(inventory(&candidate)!=0)return -1;
    *result=candidate;
    return 0;
}
static int temp_name(const char final[FE_T3B1BA0_NAME_CAP],
                     char temp[FE_T3B1BA0_NAME_CAP]) {
    if(strlen(final)!=A0_FILENAME_LEN)return -1;
    memcpy(temp,final,A0_FILENAME_LEN+1u);
    memcpy(temp+A0_FILENAME_LEN-4u,".part",6u);
    return 0;
}
int fe_t3b1ba0_set_test_fault(fe_t3b1ba0_owner *s,
    fe_t3b1ba0_fault f) {
    if(!same_fd(s)||(unsigned)f>(unsigned)FE_T3B1BA0_FAULT_READBACK)
        return -1;
    s->test_fault=f;return 0;
}
int fe_t3b1ba0_outboard_sink(const uint8_t *apx,size_t n,
    const uint8_t *row,size_t row_bytes,
    void *context,size_t *actual_ack) {
    fe_t3b1ba0_owner *s=(fe_t3b1ba0_owner *)context;
    uint8_t prior[32]={0},readback[FE_T3S1_ROW_BYTES];
    char final[FE_T3B1BA0_NAME_CAP],part[FE_T3B1BA0_NAME_CAP];
    int fd;
    uint64_t next;
    if(actual_ack)*actual_ack=0u;
    if(!actual_ack||!same_fd(s)||!apx||!row||
       row_bytes!=FE_T3S1_ROW_BYTES||!n||n>FE_T3S1_CHUNK_BYTES||
       s->committed>=s->cap||s->committed==UINT64_MAX)
        return -1;
    next=s->committed+UINT64_C(1);
    if(s->committed &&
       fe_b1s1_sha256(s->last_row,FE_T3S1_ROW_BYTES,prior)!=0)
        return -1;
    if(!valid_record(s,row,apx,n,next,prior)||
       expected_name(s,next,row,apx,n,final)!=0||
       temp_name(final,part)!=0)return -1;
    if(s->test_fault==FE_T3B1BA0_FAULT_CREATE)return -1;
    fd=openat(s->dirfd,part,
        O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(fd<0)return -1;
    /* On a hosted fault, preserve partial forensic bytes; no ACK.
     * An ambiguous orphan .part blocks future bind/restart until reviewed.
     */
    if(s->test_fault==FE_T3B1BA0_FAULT_ROW_WRITE||
       write_all(fd,row,FE_T3S1_ROW_BYTES)!=0||
       s->test_fault==FE_T3B1BA0_FAULT_APX3_WRITE||
       write_all(fd,apx,n)!=0||
       s->test_fault==FE_T3B1BA0_FAULT_FILE_SYNC||
       fsync(fd)!=0) {
        (void)close(fd);return -1;
    }
    if(close(fd)!=0)return -1;
    if(s->test_fault==FE_T3B1BA0_FAULT_PUBLISH||
       linkat(s->dirfd,part,s->dirfd,final,0)!=0)return -1;
    if(s->test_fault==FE_T3B1BA0_FAULT_UNLINK_TEMP||
       unlinkat(s->dirfd,part,0)!=0)return -1;
    if(s->test_fault==FE_T3B1BA0_FAULT_DIR_SYNC||
       fsync(s->dirfd)!=0)return -1;
    if(s->test_fault==FE_T3B1BA0_FAULT_READBACK||
       load_record(s,final,next,prior,readback)!=0||
       memcmp(readback,row,FE_T3S1_ROW_BYTES)!=0)
        return -1;
    memcpy(s->last_row,row,FE_T3S1_ROW_BYTES);
    s->committed=next;
    *actual_ack=FE_T3S1_ROW_BYTES+n;
    return 0;
}
