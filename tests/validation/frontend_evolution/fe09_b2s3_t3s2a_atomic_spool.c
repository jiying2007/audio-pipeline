/* #794 FE09 T3-S2-A: noninstalled source-pinned POSIX outboard transaction.
 * Canonical 200B FBS1 + unmodified original APX3 S2 bytes. These are
 * transport bytes, NOT a new APX3 parser/serializer/CRC implementation.
 * POSIX fsync is not board/NAND/UBIFS or physical power-loss proof.
 * All filesystem I/O is exclusively in this pinned consumer callback.
 */
#define _POSIX_C_SOURCE 200809L
#include "fe09_b2s3_t3s2a_atomic_spool.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static uint32_t le32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1]<<8u |
           (uint32_t)p[2]<<16u | (uint32_t)p[3]<<24u;
}
static uint64_t le64(const uint8_t *p) {
    return (uint64_t)le32(p) | ((uint64_t)le32(p+4u)<<32u);
}
static int same_fd(const fe_t3s2a_spool *s) {
    struct stat st;
    return s && s->binding_complete==1u &&
        s->dirfd>=0 && fstat(s->dirfd,&st)==0 &&
        S_ISDIR(st.st_mode) && st.st_dev==s->device &&
        st.st_ino==s->inode && st.st_uid==geteuid() &&
        (st.st_mode&0022)==0;
}
int fe_t3s2a_record_name(uint64_t seq,char dest[FE_T3S2A_NAME_CAP]) {
    int n;
    if (!dest || !seq || seq>FE_T3S2A_MAX_FILES) return -1;
    n=snprintf(dest,FE_T3S2A_NAME_CAP,"fbs1-%016" PRIx64 ".bin",seq);
    return n>0 && (size_t)n<FE_T3S2A_NAME_CAP ? 0 : -1;
}
static int part_name(uint64_t seq,char dest[FE_T3S2A_NAME_CAP]) {
    int n;
    if(!dest || !seq || seq>FE_T3S2A_MAX_FILES)return -1;
    n=snprintf(dest,FE_T3S2A_NAME_CAP,"fbs1-%016" PRIx64 ".part",seq);
    return n>0 && (size_t)n<FE_T3S2A_NAME_CAP ? 0 : -1;
}
static int valid_map(const fe_t3s2a_spool *s,const uint8_t row[FE_T3S1_ROW_BYTES]) {
    uint32_t seen=0u,i;
    for (i=0u;i<4u;++i) {
        uint32_t slot=le32(row+88u+i*4u);
        if (slot!=s->slots[i]) return 0;
        if (i<s->mics) {
            if (slot>=s->mics || (seen&(1u<<slot))) return 0;
            seen |= 1u<<slot;
        } else if(slot!=UINT32_MAX) return 0;
    }
    return seen==((1u<<s->mics)-1u);
}
/* Reuse the ORIGINAL S2 codec/replay, not a copied APX3 parser/CRC.
 * Recalculate original FBS1 FNV witness from decoded LE PCM on recovery;
 * a separately rehashed FBS1 row must not hide an inconsistent payload.
 */
typedef struct {
    uint64_t capture_hash, render_hash;
    uint32_t mics, render, seen;
} original_pcm_witness;
static uint64_t original_le_fnv(const uint8_t *bytes,size_t n) {
    uint64_t h=UINT64_C(14695981039346656037);
    for(size_t i=0u;i<n;++i)
        h=(h^(uint64_t)bytes[i])*UINT64_C(1099511628211);
    return h;
}
static int original_replay_witness(const fe_s2_stream *stream,
    uint32_t index,uint64_t local_sequence,
    uint32_t capture_flags,uint32_t render_flags,
    const uint8_t *capture_le,size_t capture_bytes,
    const uint8_t *render_le,size_t render_bytes,void *ctx) {
    original_pcm_witness *w=(original_pcm_witness *)ctx;
    if(!stream||!w||index||local_sequence!=UINT64_C(1)||
       capture_flags||render_flags||stream->frames!=1u||
       stream->config.physical_mics!=w->mics||
       stream->config.render_channels!=w->render||
       capture_bytes!=(size_t)stream->config.rate_hz*w->mics/50u||
       render_bytes!=(size_t)stream->config.rate_hz*w->render/50u||
       !capture_le||
       original_le_fnv(capture_le,capture_bytes)!=w->capture_hash||
       (render_bytes ? (!render_le ||
            original_le_fnv(render_le,render_bytes)!=w->render_hash) :
           (render_le!=NULL||w->render_hash!=UINT64_C(0))))
        return 1;
    w->seen=1u;
    return 0;
}
static int valid_record(const fe_t3s2a_spool *s,
     const uint8_t *row,const uint8_t *apx,size_t n,uint64_t seq) {
    uint8_t hash[32];
    fe_s2_stream d;
    original_pcm_witness witness;
    uint32_t event,has_render,i;
    if (!row||!apx||!n||n>FE_T3S1_CHUNK_BYTES ||
        le32(row)!=FE_B1S1_MANIFEST_MAGIC ||
        le32(row+4u)!=FE_B1S1_MANIFEST_VERSION ||
        le32(row+12u)!=s->rate_hz || le32(row+16u)!=s->mics ||
        le64(row+20u)!=s->generation ||
        le32(row+28u)!=s->capture_id ||
        le32(row+32u)!=s->render_id ||
        le32(row+36u)!=1u || le64(row+48u)!=seq ||
        le64(row+56u)!=UINT64_C(1) || le32(row+64u)!=1u ||
        le32(row+68u)!=(uint32_t)n || !valid_map(s,row))
        return 0;
    event=le32(row+8u);
    if(event>FE_B1S0_RENDER_ABSENT ||
       (s->render_enabled ? event==FE_B1S0_RENDER_DISABLED :
                            event!=FE_B1S0_RENDER_DISABLED))
        return 0;
    has_render=(uint32_t)(event==FE_B1S0_RENDER_PRESENT);
    if ((!s->render_enabled && le32(row+40u)!=0u) ||
        (s->render_enabled && le32(row+40u)==0u) ||
        (event==FE_B1S0_RENDER_ABSENT ?
          le32(row+44u)!=FE_B1S0_ABSENT_SOURCE_REPORTED :
          le32(row+44u)!=0u) ||
        (event!=FE_B1S0_RENDER_PRESENT && le64(row+80u)!=0u) ||
        fe_b1s1_sha256(row,FE_B1S1_ROW_DIGEST_OFFSET,hash)!=0 ||
        memcmp(hash,row+FE_B1S1_ROW_DIGEST_OFFSET,32u)!=0 ||
        fe_b1s1_sha256(apx,n,hash)!=0 ||
        memcmp(hash,row+104u,32u)!=0 ||
        fe_s2_decode(apx,n,&d)!=FE_S2_OK ||
        d.frames!=1u || d.total_bytes!=n ||
        d.config.rate_hz!=s->rate_hz ||
        d.config.physical_mics!=s->mics ||
        d.config.render_channels!=has_render ||
        d.config.capture_source_id!=s->capture_id ||
        d.config.render_source_id!=(has_render?s->render_id:0u) ||
        d.config.capture_epoch!=1u ||
        d.config.render_epoch!=(has_render?le32(row+40u):0u) ||
        d.config.clock_authority || d.config.capture_timestamp_valid ||
        d.config.render_timestamp_valid)
        return 0;
    for(i=0u;i<4u;++i)
        if(d.config.physical_to_capture_slot[i]!=s->slots[i])return 0;
    memset(&witness,0,sizeof(witness));
    witness.mics=s->mics;
    witness.render=has_render;
    witness.capture_hash=le64(row+72u);
    witness.render_hash=le64(row+80u);
    if(fe_s2_replay(apx,n,original_replay_witness,&witness,NULL)!=FE_S2_OK ||
       witness.seen!=1u)return 0;
    return 1;
}
static int read_exact(int fd,uint8_t *p,size_t n) {
    while(n) {
        ssize_t rc=read(fd,p,n);
        if(rc<0 && errno==EINTR)continue;
        if(rc<=0) return -1;
        p+=(size_t)rc;n-=(size_t)rc;
    }
    return 0;
}
static int write_exact(int fd,const uint8_t *p,size_t n) {
    while(n) {
        ssize_t rc=write(fd,p,n);
        if(rc<0 && errno==EINTR)continue;
        if(rc<=0)return -1;
        p+=(size_t)rc;n-=(size_t)rc;
    }
    return 0;
}
static int readback(fe_t3s2a_spool *s,uint64_t seq,
    const uint8_t *original_row,const uint8_t *original_apx,size_t original_n,
    uint8_t actual_row[FE_T3S1_ROW_BYTES]) {
    char name[FE_T3S2A_NAME_CAP];
    int fd,ok=-1;
    struct stat st;
    uint8_t bytes[FE_T3S1_CHUNK_BYTES];
    size_t n;
    if(fe_t3s2a_record_name(seq,name)!=0) return -1;
    fd=openat(s->dirfd,name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if(fd<0)return -1;
    if(fstat(fd,&st)!=0||!S_ISREG(st.st_mode)||st.st_nlink!=1||
       st.st_size<=(off_t)FE_T3S1_ROW_BYTES ||
       st.st_size>(off_t)FE_T3S2A_FILE_BYTES)goto done;
    n=(size_t)st.st_size-FE_T3S1_ROW_BYTES;
    if((original_row && original_n!=n) ||
       read_exact(fd,actual_row,FE_T3S1_ROW_BYTES)!=0 ||
       read_exact(fd,bytes,n)!=0 ||
       (original_row && memcmp(actual_row,original_row,FE_T3S1_ROW_BYTES)!=0)||
       (original_apx && memcmp(bytes,original_apx,n)!=0) ||
       !valid_record(s,actual_row,bytes,n,seq))goto done;
    ok=0;
done:
    if(close(fd)!=0)return -1;
    return ok;
}
/* If a crash occurred after atomic hardlink publication but before the
 * temporary pathname was removed, both names must refer to the SAME inode.
 * A foreign/modified partial object is never deleted or admitted.
 */
static int reconcile_published_temp(fe_t3s2a_spool *s,uint64_t seq) {
    char final[FE_T3S2A_NAME_CAP],tmp[FE_T3S2A_NAME_CAP];
    struct stat one,two;
    if(fe_t3s2a_record_name(seq,final)!=0||
       part_name(seq,tmp)!=0||fstatat(s->dirfd,final,&one,AT_SYMLINK_NOFOLLOW)!=0)
        return -1;
    if(fstatat(s->dirfd,tmp,&two,AT_SYMLINK_NOFOLLOW)==0) {
        if(!S_ISREG(one.st_mode)||!S_ISREG(two.st_mode)||
           one.st_dev!=two.st_dev||one.st_ino!=two.st_ino||
           one.st_nlink!=2||unlinkat(s->dirfd,tmp,0)!=0)
            return -1;
        if(fsync(s->dirfd)!=0)return -1;
    } else if(errno!=ENOENT)return -1;
    return 0;
}
static int inventory_name(const char *name,uint32_t cap) {
    uint64_t seq;
    char pub[FE_T3S2A_NAME_CAP],tmp[FE_T3S2A_NAME_CAP];
    if(!strcmp(name,".")||!strcmp(name,".."))return 1;
    for(seq=1u;seq<=(uint64_t)cap;++seq) {
        if(fe_t3s2a_record_name(seq,pub)!=0||part_name(seq,tmp)!=0)
            return 0;
        if(!strcmp(name,pub)||!strcmp(name,tmp))return 1;
    }
    return 0;
}
int fe_t3s2a_bind(fe_t3s2a_spool *s,int fd,
    const fe_b1s0_config *cfg,const uint32_t slots[4],uint32_t cap) {
    struct stat st;
    DIR *dir;
    struct dirent *entry;
    uint8_t row[FE_T3S1_ROW_BYTES],prior[32]={0};
    uint64_t seq;
    uint32_t i,mask=0u;
    int duplicate_fd,known=0;
    struct stat enumerated;
    if(!s||!cfg||!slots||fd<0||cap<1u||cap>FE_T3S2A_MAX_FILES||
       (cfg->physical_mics!=1u&&cfg->physical_mics!=2u&&
        cfg->physical_mics!=4u)||
       (cfg->depth!=2u && cfg->depth!=4u)||
       (cfg->input_hz!=16000u && cfg->input_hz!=32000u &&
        cfg->input_hz!=48000u)||
       !cfg->capture_source_id||!cfg->source_generation||
       cfg->source_generation==UINT64_MAX||cfg->render_enabled>1u||
       (cfg->render_enabled ?
          (!cfg->render_source_id || cfg->render_source_id==cfg->capture_source_id):
          cfg->render_source_id!=0u)||
       fstat(fd,&st)!=0||!S_ISDIR(st.st_mode)||
       st.st_uid!=geteuid()||(st.st_mode&0022)!=0)
        return -1;
    for(i=0u;i<4u;++i) {
        if(i<cfg->physical_mics) {
            if(slots[i]>=cfg->physical_mics||(mask&(1u<<slots[i])))return -1;
            mask |= 1u<<slots[i];
        }else if(slots[i]!=UINT32_MAX)return -1;
    }
    if(mask!=((1u<<cfg->physical_mics)-1u))return -1;
    memset(s,0,sizeof(*s));
    s->dirfd=fd;s->device=st.st_dev;s->inode=st.st_ino;
    s->generation=cfg->source_generation;
    s->capture_id=cfg->capture_source_id;s->render_id=cfg->render_source_id;
    s->rate_hz=cfg->input_hz;s->mics=cfg->physical_mics;
    s->render_enabled=cfg->render_enabled;s->maximum_files=cap;
    memcpy(s->slots,slots,sizeof(s->slots));
    /* dup(fd) shares a directory stream offset: a second bind could
     * silently miss alien files after the first fdopendir reached EOF.
     * Always open an independently offset-owned descriptor to rescan. */
    duplicate_fd=openat(fd,".",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(duplicate_fd<0)return -1;
    if(fstat(duplicate_fd,&enumerated)!=0 ||
       enumerated.st_dev!=st.st_dev || enumerated.st_ino!=st.st_ino) {
        (void)close(duplicate_fd);
        return -1;
    }
    dir=fdopendir(duplicate_fd);
    if(!dir){close(duplicate_fd);return -1;}
    errno=0;
    while((entry=readdir(dir))!=NULL) {
        if(!inventory_name(entry->d_name,cap)){known=-1;break;}
        errno=0;
    }
    if(errno!=0)known=-1;
    if(closedir(dir)!=0)known=-1;
    if(known!=0)return -1;
    for(seq=1u;seq<=(uint64_t)cap;++seq) {
        char pub[FE_T3S2A_NAME_CAP],tmp[FE_T3S2A_NAME_CAP];
        struct stat existing;
        if(fe_t3s2a_record_name(seq,pub)!=0||part_name(seq,tmp)!=0)
            return -1;
        if(fstatat(fd,pub,&existing,AT_SYMLINK_NOFOLLOW)!=0) {
            if(errno!=ENOENT)return -1;
            if(fstatat(fd,tmp,&existing,AT_SYMLINK_NOFOLLOW)==0 ||
               errno!=ENOENT)return -1; /* torn unpublished temp: quarantine */
            /* Verify later sequence does not exist: one unambiguous head. */
            for(uint64_t later=seq+1u;later<=(uint64_t)cap;++later) {
                char next[FE_T3S2A_NAME_CAP],partial[FE_T3S2A_NAME_CAP];
                if(fe_t3s2a_record_name(later,next)!=0||
                   part_name(later,partial)!=0)return -1;
                if(fstatat(fd,next,&existing,AT_SYMLINK_NOFOLLOW)==0||
                   errno!=ENOENT)return -1;
                if(fstatat(fd,partial,&existing,AT_SYMLINK_NOFOLLOW)==0||
                   errno!=ENOENT)return -1;
            }
            break;
        }
        if(reconcile_published_temp(s,seq)!=0 ||
           readback(s,seq,NULL,NULL,0u,row)!=0 ||
           memcmp(row+136u,prior,32u)!=0 ||
           fe_b1s1_sha256(row,FE_T3S1_ROW_BYTES,prior)!=0)
            return -1;
        ++s->committed;
        memcpy(s->committed_last_row,row,FE_T3S1_ROW_BYTES);
    }
    memcpy(s->prior_row_sha256,prior,32u);
    s->restart_recovered=(uint32_t)(s->committed!=0u);
    /* No callback or injected fault can treat an incompletely enumerated
     * directory/source identity as a valid pinned sink authority. */
    s->binding_complete=1u;
    return 0;
}
int fe_t3s2a_set_test_fault(fe_t3s2a_spool *s,fe_t3s2a_fault f) {
    if(!same_fd(s)||f<FE_T3S2A_FAULT_NONE||
       f>FE_T3S2A_FAULT_READBACK)return -1;
    s->failpoint=f;
    return 0;
}
int fe_t3s2a_outboard_sink(const uint8_t *apx,size_t n,
    const uint8_t *row,size_t rowlen,void *context,size_t *ack) {
    fe_t3s2a_spool *s=(fe_t3s2a_spool *)context;
    char final[FE_T3S2A_NAME_CAP],tmp[FE_T3S2A_NAME_CAP];
    struct stat st;
    uint64_t seq;
    uint8_t read_row[FE_T3S1_ROW_BYTES],next[32];
    int fd=-1,published=0;
    if(ack)*ack=0u;
    if(!same_fd(s)||!ack||!row||rowlen!=FE_T3S1_ROW_BYTES||
       !apx||!n||n>FE_T3S1_CHUNK_BYTES)return -1;
    seq=le64(row+48u);
    if(seq==s->committed && seq!=0u) {
        if(memcmp(row,s->committed_last_row,rowlen)!=0 ||
           !valid_record(s,row,apx,n,seq) ||
           reconcile_published_temp(s,seq)!=0 ||
           readback(s,seq,row,apx,n,read_row)!=0 ||
           fsync(s->dirfd)!=0)return -1;
        *ack=n+rowlen;return 0; /* ONLY identical last published frame */
    }
    if(s->committed>=(uint64_t)s->maximum_files ||
       seq!=s->committed+UINT64_C(1) ||
       memcmp(row+136u,s->prior_row_sha256,32u)!=0 ||
       !valid_record(s,row,apx,n,seq) ||
       fe_t3s2a_record_name(seq,final)!=0||
       part_name(seq,tmp)!=0)return -1;
    if(fstatat(s->dirfd,final,&st,AT_SYMLINK_NOFOLLOW)==0) {
        if(reconcile_published_temp(s,seq)!=0 ||
           readback(s,seq,row,apx,n,read_row)!=0 ||
           fsync(s->dirfd)!=0)return -1;
        /* After an interrupted prior publish, byte-exact ID is idempotent. */
    } else {
        if(errno!=ENOENT||s->failpoint==FE_T3S2A_FAULT_CREATE)
            return -1;
        fd=openat(s->dirfd,tmp,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
        if(fd<0)return -1;
        if(write_exact(fd,row,rowlen)!=0 ||
           s->failpoint==FE_T3S2A_FAULT_ROW_WRITE ||
           write_exact(fd,apx,n)!=0 ||
           s->failpoint==FE_T3S2A_FAULT_APX3_WRITE ||
           fsync(fd)!=0 ||
           s->failpoint==FE_T3S2A_FAULT_FILE_SYNC)goto failed;
        if(close(fd)!=0){fd=-1;goto failed;}
        fd=-1;
        /* POSIX linkat creates the immutable committed basename atomically
         * with no replace semantics. NEVER rename over an existing ID. */
        if(linkat(s->dirfd,tmp,s->dirfd,final,0)!=0)goto failed;
        published=1;
        if(s->failpoint==FE_T3S2A_FAULT_PUBLISH)goto failed;
        if(unlinkat(s->dirfd,tmp,0)!=0)goto failed;
        if(fsync(s->dirfd)!=0 ||
           s->failpoint==FE_T3S2A_FAULT_DIRECTORY_SYNC)goto failed;
        if(s->failpoint==FE_T3S2A_FAULT_READBACK ||
           readback(s,seq,row,apx,n,read_row)!=0)goto failed;
    }
    if(fe_b1s1_sha256(row,rowlen,next)!=0)return -1;
    memcpy(s->prior_row_sha256,next,32u);
    memcpy(s->committed_last_row,row,rowlen);
    s->committed=seq;
    *ack=n+rowlen;
    return 0;
failed:
    if(fd>=0)(void)close(fd);
    /* Before publication, no committed identity ever exists. After linkat
     * a physically visible completed record MAY already exist: preserve
     * and force exact idempotent readback on retry; NEVER lie about ACK. */
    if(!published) {
        if(unlinkat(s->dirfd,tmp,0)!=0)return -1;
        (void)fsync(s->dirfd);
    }
    ++s->process_crash_faults_rejected;
    return -1;
}
