/* #809: private FRM2 v2 source-bound immutable left-anchor root, no pruning.
 * Original A0 owns APX3/FBS1 validation, parser/CRC/replay, and original ACKs.
 * This code reads canonical rows only after and before unchanged A0 replay.
 */
#define _POSIX_C_SOURCE 200809L
#include "fe09_b2s3_t3s2b1ba1_anchor_root.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define A1_NAME_LEN 149u

static uint32_t a1_g32(const uint8_t *p) {
    return (uint32_t)p[0]|(uint32_t)p[1]<<8u|
           (uint32_t)p[2]<<16u|(uint32_t)p[3]<<24u;
}
static uint64_t a1_g64(const uint8_t *p) {
    return (uint64_t)a1_g32(p)|((uint64_t)a1_g32(p+4u)<<32u);
}
static void a1_p32(uint8_t *p,uint32_t value) {
    for(unsigned i=0u;i<4u;++i)p[i]=(uint8_t)(value>>(8u*i));
}
static void a1_p64(uint8_t *p,uint64_t value) {
    for(unsigned i=0u;i<8u;++i)p[i]=(uint8_t)(value>>(8u*i));
}
static int a1_nonzero(const uint8_t h[32]) {
    uint8_t x=0u;
    for(unsigned i=0u;i<32u;++i)x=(uint8_t)(x|h[i]);
    return x!=0u;
}
static int a1_directory(int fd,dev_t device,ino_t inode) {
    struct stat st;
    int flags;
    return fd>=0&&fstat(fd,&st)==0&&S_ISDIR(st.st_mode)&&
        st.st_uid==geteuid()&&(st.st_mode&0022)==0&&
        st.st_dev==device&&st.st_ino==inode&&
        (flags=fcntl(fd,F_GETFL))>=0&&(flags&O_DIRECTORY)!=0&&
        (flags&O_NOFOLLOW)!=0;
}
static int a1_owner(const fe_t3b1ba1_owner *s) {
    return s&&s->binding_complete==1u&&
        s->source.binding_complete==1u&&
        s->source.cap==32u&&s->source.committed==UINT64_C(32)&&
        a1_directory(s->dirfd,s->device,s->inode)&&
        a1_directory(s->source.dirfd,s->source.device,s->source.inode)&&
        (s->device!=s->source.device||s->inode!=s->source.inode);
}
static int a1_source_replay(const fe_t3b1ba1_owner *s) {
    fe_t3b1ba0_owner replayed;
    if(!a1_owner(s)||fe_t3b1ba0_bind(&replayed,s->source.dirfd,
        &s->source.source,s->source.slots,s->source.cap)!=0||
        replayed.device!=s->source.device||replayed.inode!=s->source.inode||
        replayed.committed!=UINT64_C(32)||
        memcmp(replayed.last_row,s->source.last_row,FE_T3S1_ROW_BYTES)!=0)
        return -1;
    return 0;
}
static int a1_read_all(int fd,uint8_t *p,size_t n) {
    while(n) {
        ssize_t got=read(fd,p,n);
        if(got<0&&errno==EINTR)continue;
        if(got<=0)return -1;
        p+=(size_t)got;n-=(size_t)got;
    }
    return 0;
}
static int a1_write_all(int fd,const uint8_t *p,size_t n) {
    while(n) {
        ssize_t done=write(fd,p,n);
        if(done<0&&errno==EINTR)continue;
        if(done<=0)return -1;
        p+=(size_t)done;n-=(size_t)done;
    }
    return 0;
}
/* Strictly readonly FBS1 access, with the original A0 filename function.
 * APX3 is not parsed or rewritten here; A0 bind performs original replay.
 */
static int a1_row(const fe_t3b1ba1_owner *s,const char *name,
    uint8_t row[FE_T3S1_ROW_BYTES],uint64_t *sequence) {
    struct stat st;
    uint8_t hash[32];
    char expected[FE_T3B1BA0_NAME_CAP];
    int fd=openat(s->source.dirfd,name,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    if(fd<0)return -1;
    int valid=fstat(fd,&st)==0&&S_ISREG(st.st_mode)&&
        st.st_uid==geteuid()&&st.st_nlink==1&&
        (st.st_mode&07777)==0600&&
        st.st_size>(off_t)FE_T3S1_ROW_BYTES&&
        st.st_size<=(off_t)(FE_T3S1_ROW_BYTES+FE_T3S1_CHUNK_BYTES)&&
        a1_read_all(fd,row,FE_T3S1_ROW_BYTES)==0;
    if(close(fd)!=0||!valid)return -1;
    uint64_t seq=a1_g64(row+48u);
    uint32_t bytes=a1_g32(row+68u);
    if(seq<UINT64_C(1)||seq>UINT64_C(32)||!bytes||
       bytes>FE_T3S1_CHUNK_BYTES||
       st.st_size!=(off_t)(FE_T3S1_ROW_BYTES+(size_t)bytes)||
       fe_b1s1_sha256(row,FE_T3S1_ROW_BYTES,hash)!=0||
       fe_t3b1ba0_name(s->source.source.capture_source_id,
           s->source.source.source_generation,seq,hash,row+104u,expected)!=0||
       strcmp(name,expected)!=0)return -1;
    *sequence=seq;return 0;
}
int fe_t3b1ba1_encode(const fe_t3b1ba1_owner *s,
    uint8_t result[FE_T3B1BA1_ROOT_BYTES]) {
    uint8_t rows[32][FE_T3S1_ROW_BYTES],seen[32]={0},prior[32]={0};
    uint8_t wire[FE_T3B1BA1_ROOT_BYTES]={0};
    int failure=0;
    if(!result||a1_source_replay(s)!=0)return -1;
    int duplicate=openat(s->source.dirfd,".",
        O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(duplicate<0)return -1;
    DIR *directory=fdopendir(duplicate);
    if(!directory){(void)close(duplicate);return -1;}
    for(;;) {
        struct dirent *entry;
        uint64_t seq;
        uint8_t row[FE_T3S1_ROW_BYTES];
        errno=0;entry=readdir(directory);
        if(!entry){if(errno)failure=1;break;}
        if(strcmp(entry->d_name,".")==0||strcmp(entry->d_name,"..")==0)
            continue;
        if(a1_row(s,entry->d_name,row,&seq)!=0||seen[seq-1u]) {
            failure=1;break;
        }
        seen[seq-1u]=1u;memcpy(rows[seq-1u],row,sizeof(row));
    }
    if(closedir(directory)!=0)failure=1;
    if(failure||a1_source_replay(s)!=0)return -1;
    a1_p32(wire,FE_T3B1BA1_MAGIC);a1_p32(wire+4u,FE_T3B1BA1_VERSION);
    a1_p32(wire+8u,FE_T3B1BA1_HEADER_BYTES);
    a1_p32(wire+12u,FE_T3B1BA1_MEMBER_BYTES);
    a1_p32(wire+16u,FE_T3B1BA1_ROOT_BYTES);a1_p32(wire+20u,16u);
    a1_p32(wire+24u,32u);a1_p32(wire+28u,s->source.source.capture_source_id);
    a1_p64(wire+32u,s->source.source.source_generation);
    a1_p32(wire+40u,s->source.source.input_hz);
    a1_p32(wire+44u,s->source.source.physical_mics);
    a1_p32(wire+48u,s->source.source.render_enabled);
    a1_p32(wire+52u,s->source.source.render_source_id);
    for(unsigned i=0u;i<4u;++i)a1_p32(wire+56u+4u*i,s->source.slots[i]);
    a1_p64(wire+72u,UINT64_C(17));a1_p64(wire+80u,UINT64_C(32));
    a1_p64(wire+88u,UINT64_C(32));
    a1_p32(wire+192u,s->source.source.depth);a1_p32(wire+196u,10u);
    a1_p32(wire+200u,1u);a1_p32(wire+204u,FE_T3S1_ROW_BYTES);
    a1_p32(wire+208u,32u);
    for(unsigned i=0u;i<32u;++i) {
        if(!seen[i]||memcmp(rows[i]+136u,prior,32u)!=0||
           fe_b1s1_sha256(rows[i],FE_T3S1_ROW_BYTES,prior)!=0)return -1;
        if(i==15u)memcpy(wire+96u,prior,32u);
        if(i>=16u) {
            uint8_t *member=wire+FE_T3B1BA1_HEADER_BYTES+
                (i-16u)*FE_T3B1BA1_MEMBER_BYTES;
            a1_p64(member,(uint64_t)i+UINT64_C(1));
            memcpy(member+8u,prior,32u);memcpy(member+40u,rows[i]+104u,32u);
        }
    }
    memcpy(wire+128u,prior,32u);
    if(!a1_nonzero(wire+96u)||memcmp(rows[31],s->source.last_row,
        FE_T3S1_ROW_BYTES)!=0||
       fe_b1s1_sha256(wire,sizeof(wire),wire+FE_T3B1BA1_DIGEST_OFFSET)!=0)
        return -1;
    memcpy(result,wire,sizeof(wire));return 0;
}
int fe_t3b1ba1_verify_bytes(const fe_t3b1ba1_owner *s,
    const uint8_t *root,size_t bytes) {
    uint8_t expected[FE_T3B1BA1_ROOT_BYTES];
    if(!root||bytes!=sizeof(expected)||fe_t3b1ba1_encode(s,expected)!=0||
       memcmp(root,expected,sizeof(expected))!=0||a1_source_replay(s)!=0)
        return -1;
    return 0;
}
int fe_t3b1ba1_name(const uint8_t root[FE_T3B1BA1_ROOT_BYTES],
    char name[FE_T3B1BA1_NAME_CAP]) {
    static const char hex[]="0123456789abcdef";
    char digest[65];
    if(!root||!name||a1_g32(root)!=FE_T3B1BA1_MAGIC||
       a1_g32(root+4u)!=FE_T3B1BA1_VERSION||!a1_g32(root+28u)||
       !a1_g64(root+32u)||a1_g64(root+32u)==UINT64_MAX||
       a1_g64(root+72u)!=UINT64_C(17)||a1_g64(root+80u)!=UINT64_C(32)||
       a1_g64(root+88u)!=UINT64_C(32)||!a1_nonzero(root+160u))return -1;
    for(unsigned i=0u;i<32u;++i) {
        digest[2u*i]=hex[root[160u+i]>>4u];
        digest[2u*i+1u]=hex[root[160u+i]&15u];
    }
    digest[64]='\0';
    int n=snprintf(name,FE_T3B1BA1_NAME_CAP,
        "fr2-%08" PRIx32 "-%016" PRIx64 "-%016" PRIx64
        "-%016" PRIx64 "-%016" PRIx64 "-%s.bin",
        a1_g32(root+28u),a1_g64(root+32u),a1_g64(root+72u),
        a1_g64(root+80u),a1_g64(root+88u),digest);
    return n==(int)A1_NAME_LEN?0:-1;
}
static int a1_load_root(const fe_t3b1ba1_owner *s,const char *name,
    const uint8_t expected[FE_T3B1BA1_ROOT_BYTES]) {
    struct stat st;
    uint8_t wire[FE_T3B1BA1_ROOT_BYTES];
    int fd=openat(s->dirfd,name,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    if(fd<0)return -1;
    int valid=fstat(fd,&st)==0&&S_ISREG(st.st_mode)&&st.st_uid==geteuid()&&
        st.st_nlink==1&&(st.st_mode&07777)==0600&&st.st_size==(off_t)sizeof(wire);
    if(valid&&s->test_fault==FE_T3B1BA1_FAULT_SHORT_READ) {
        (void)a1_read_all(fd,wire,sizeof(wire)/2u);valid=0;errno=EIO;
    } else if(valid&&s->test_fault==FE_T3B1BA1_FAULT_READ_EIO) {
        valid=0;errno=EIO;
    } else if(valid)valid=a1_read_all(fd,wire,sizeof(wire))==0;
    if(close(fd)!=0||!valid||memcmp(wire,expected,sizeof(wire))!=0||
       a1_source_replay(s)!=0)return -1;
    return 0;
}
static int a1_inventory(const fe_t3b1ba1_owner *s,
    const uint8_t expected[FE_T3B1BA1_ROOT_BYTES],int *present) {
    char name[FE_T3B1BA1_NAME_CAP];
    int failed=0,count=0;
    if(!a1_owner(s)||fe_t3b1ba1_name(expected,name)!=0)return -1;
    int duplicate=openat(s->dirfd,".",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(duplicate<0)return -1;
    DIR *directory=fdopendir(duplicate);
    if(!directory){(void)close(duplicate);return -1;}
    for(;;) {
        struct dirent *entry;
        errno=0;entry=readdir(directory);
        if(!entry){if(errno)failed=1;break;}
        if(strcmp(entry->d_name,".")==0||strcmp(entry->d_name,"..")==0)continue;
        if(count||strcmp(entry->d_name,name)!=0) {failed=1;break;}
        ++count;
    }
    if(closedir(directory)!=0)failed=1;
    if(failed||(count&&a1_load_root(s,name,expected)!=0))return -1;
    *present=count;return 0;
}
int fe_t3b1ba1_bind(fe_t3b1ba1_owner *result,int fd,
    const fe_t3b1ba0_owner *source) {
    fe_t3b1ba1_owner candidate;
    uint8_t wire[FE_T3B1BA1_ROOT_BYTES];
    struct stat st;
    int present;
    if(!result||!source||fd<0||fstat(fd,&st)!=0)return -1;
    memset(&candidate,0,sizeof(candidate));
    candidate.dirfd=fd;candidate.device=st.st_dev;candidate.inode=st.st_ino;
    candidate.source=*source;candidate.binding_complete=1u;
    if(fe_t3b1ba1_encode(&candidate,wire)!=0||
       a1_inventory(&candidate,wire,&present)!=0)return -1;
    candidate.root_visible_on_bind=(uint32_t)present;
    *result=candidate;return 0;
}
static void a1_receipt(const fe_t3b1ba1_owner *s,const uint8_t *wire,
    fe_t3b1ba1_receipt *r) {
    r->first_sequence=UINT64_C(17);r->last_sequence=UINT64_C(32);
    r->original_high_water=UINT64_C(32);r->original_files_verified=32u;
    r->root_visible_verified=1u;r->root_visible_on_bind=s->root_visible_on_bind;
    memcpy(r->left_anchor_sha256,wire+96u,32u);
    memcpy(r->root_sha256,wire+160u,32u);
}
int fe_t3b1ba1_read(const fe_t3b1ba1_owner *s,fe_t3b1ba1_receipt *r) {
    uint8_t wire[FE_T3B1BA1_ROOT_BYTES];
    int present;
    if(!r)return -1;
    memset(r,0,sizeof(*r));
    if(fe_t3b1ba1_encode(s,wire)!=0||a1_inventory(s,wire,&present)!=0||!present)
        return -1;
    a1_receipt(s,wire,r);return 0;
}
int fe_t3b1ba1_set_test_fault(fe_t3b1ba1_owner *s,fe_t3b1ba1_fault fault) {
    if(!a1_owner(s)||(unsigned)fault>(unsigned)FE_T3B1BA1_FAULT_SHORT_READ)return -1;
    s->test_fault=fault;return 0;
}
int fe_t3b1ba1_publish(fe_t3b1ba1_owner *s,fe_t3b1ba1_receipt *r) {
    uint8_t wire[FE_T3B1BA1_ROOT_BYTES];
    char final[FE_T3B1BA1_NAME_CAP],part[FE_T3B1BA1_NAME_CAP];
    int fd,present;
    if(!r)return -1;
    memset(r,0,sizeof(*r));
    if(fe_t3b1ba1_encode(s,wire)!=0||a1_inventory(s,wire,&present)!=0||
       fe_t3b1ba1_name(wire,final)!=0)return -1;
    if(present) {
        fd=openat(s->dirfd,final,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
        if(fd<0)return -1;
        int synced=s->test_fault!=FE_T3B1BA1_FAULT_FILE_SYNC&&fsync(fd)==0;
        if(close(fd)!=0||!synced)return -1;
    } else {
        memcpy(part,final,A1_NAME_LEN+1u);memcpy(part+A1_NAME_LEN-4u,".part",6u);
        if(s->test_fault==FE_T3B1BA1_FAULT_CREATE_ENOSPC){errno=ENOSPC;return -1;}
        if(s->test_fault==FE_T3B1BA1_FAULT_CREATE_EROFS){errno=EROFS;return -1;}
        fd=openat(s->dirfd,part,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
        if(fd<0)return -1;
        int valid=1;
        if(s->test_fault==FE_T3B1BA1_FAULT_SHORT_WRITE) {
            (void)a1_write_all(fd,wire,sizeof(wire)/2u);valid=0;errno=EIO;
        } else if(s->test_fault==FE_T3B1BA1_FAULT_WRITE_EIO) {
            valid=0;errno=EIO;
        } else valid=a1_write_all(fd,wire,sizeof(wire))==0;
        if(valid)valid=s->test_fault!=FE_T3B1BA1_FAULT_FILE_SYNC&&fsync(fd)==0;
        if(close(fd)!=0||!valid)return -1;
        if(s->test_fault==FE_T3B1BA1_FAULT_LINK||
           linkat(s->dirfd,part,s->dirfd,final,0)!=0)return -1;
        if(s->test_fault==FE_T3B1BA1_FAULT_UNLINK_TEMP||
           unlinkat(s->dirfd,part,0)!=0)return -1;
    }
    if(s->test_fault==FE_T3B1BA1_FAULT_DIR_SYNC||fsync(s->dirfd)!=0||
       fe_t3b1ba1_read(s,r)!=0)return -1;
    r->hosted_checkpoint_committed=1u;return 0;
}
