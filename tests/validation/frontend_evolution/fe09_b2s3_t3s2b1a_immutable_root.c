/* #799: first-party ORIGINAL S2 APX3 / original S1-S2A / original B0
 * FRM1 immutable index-root, POSIX HOSTED research only. All source files
 * remain preserved: no rolling, prune, BF-side I/O, power-cut or device claim.
 */
#define _POSIX_C_SOURCE 200809L
#include "fe09_b2s3_t3s2b1a_immutable_root.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int apart(const void *a,size_t na,const void *b,size_t nb) {
    uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
    if(!a||!b||!na||!nb||x>UINTPTR_MAX-na||y>UINTPTR_MAX-nb)return 0;
    return x+na<=y||y+nb<=x;
}
static uint32_t le32(const uint8_t *p) {
    uint32_t x=0u;
    for(unsigned i=0u;i<4u;++i)x|=(uint32_t)p[i]<<(8u*i);
    return x;
}
static int source_ok(const fe_t3s2a_spool *s) {
    fe_t3s2b0_index probe;
    struct stat st;
    return s && s->binding_complete==1u && s->dirfd>=0 &&
        s->generation>UINT64_C(0) && s->generation!=UINT64_MAX &&
        s->maximum_files>=1u && s->maximum_files<=FE_T3S2B1A_MAX_ROOTS &&
        s->committed<=(uint64_t)s->maximum_files &&
        fstat(s->dirfd,&st)==0 && S_ISDIR(st.st_mode) &&
        st.st_dev==s->device && st.st_ino==s->inode &&
        st.st_uid==geteuid() && (st.st_mode&0022)==0 &&
        fe_t3s2b0_bind(&probe,s,s->maximum_files)==0;
}
static int root_ok(const fe_t3s2b1a_root *r,int require_bound) {
    struct stat st;
    return r && (!require_bound || r->binding_complete==1u) &&
        r->root_dirfd>=0 && source_ok(r->original_source) &&
        r->source_generation==r->original_source->generation &&
        r->capacity==r->original_source->maximum_files &&
        r->roots_committed<=r->capacity &&
        r->original_source->committed>=(uint64_t)r->roots_committed &&
        r->original_source->committed<=(uint64_t)r->roots_committed+UINT64_C(1) &&
        fstat(r->root_dirfd,&st)==0 && S_ISDIR(st.st_mode) &&
        st.st_dev==r->root_device && st.st_ino==r->root_inode &&
        st.st_uid==geteuid() && (st.st_mode&0022)==0 &&
        (st.st_dev!=r->original_source->device ||
         st.st_ino!=r->original_source->inode) &&
        apart(r,sizeof(*r),r->original_source,sizeof(*r->original_source));
}
static int read_exact(int fd,uint8_t *p,size_t n) {
    while(n) {
        ssize_t count=read(fd,p,n);
        if(count<0 && errno==EINTR)continue;
        if(count<=0)return -1;
        p+=(size_t)count;n-=(size_t)count;
    }
    return 0;
}
static int write_exact(int fd,const uint8_t *p,size_t n) {
    while(n) {
        ssize_t count=write(fd,p,n);
        if(count<0 && errno==EINTR)continue;
        if(count<=0)return -1;
        p+=(size_t)count;n-=(size_t)count;
    }
    return 0;
}
static int nibble(char c) {
    if(c>='0'&&c<='9')return (int)(c-'0');
    if(c>='a'&&c<='f')return (int)(c-'a')+10;
    return -1;
}
int fe_t3s2b1a_name(uint64_t generation,uint64_t seq,
    const uint8_t hash[32],char dst[FE_T3S2B1A_FILENAME_BYTES]) {
    int n;
    if(!dst||!hash||generation==UINT64_C(0)||!seq||
       seq>FE_T3S2B1A_MAX_ROOTS)return -1;
    n=snprintf(dst,FE_T3S2B1A_FILENAME_BYTES,
               "frm1-%016" PRIx64 "-%016" PRIx64 "-",
               generation,seq);
    if(n<=0||(size_t)n+64u+4u>=FE_T3S2B1A_FILENAME_BYTES)return -1;
    for(size_t i=0u;i<32u;++i) {
        static const char hex[]="0123456789abcdef";
        dst[(size_t)n+i*2u]=hex[hash[i]>>4u];
        dst[(size_t)n+i*2u+1u]=hex[hash[i]&15u];
    }
    memcpy(dst+(size_t)n+64u,".bin",5u);
    return 0;
}
/* Original immutable basename, optionally with its exact .part hardlink.
 * Reject any noncanonical character, path, foreign source generation, or
 * multiple distinct digests with the same original global sequence.
 */
static int parse_name(const fe_t3s2b1a_root *r,const char *name,
    uint32_t *seq,uint8_t hash[32],int *partial) {
    size_t len=strlen(name);
    uint64_t gen=UINT64_C(0),s=UINT64_C(0);
    char canonical[FE_T3S2B1A_FILENAME_BYTES];
    const size_t full=5u+16u+1u+16u+1u+64u+4u;
    if(!r||!name||!seq||!hash||!partial||
       (len!=full && len!=full+5u)||
       memcmp(name,"frm1-",5u)!=0||name[21u]!='-'||
       name[38u]!='-'||memcmp(name+103u,".bin",4u)!=0)
        return -1;
    *partial=(int)(len==full+5u);
    if(*partial && memcmp(name+full,".part",5u)!=0)return -1;
    for(size_t i=0u;i<16u;++i) {
        int v=nibble(name[5u+i]);
        if(v<0)return -1;
        gen=(gen<<4u)|(uint64_t)(unsigned)v;
        v=nibble(name[22u+i]);
        if(v<0)return -1;
        s=(s<<4u)|(uint64_t)(unsigned)v;
    }
    if(gen!=r->source_generation || s==UINT64_C(0) ||
       s>(uint64_t)r->capacity)return -1;
    for(size_t i=0u;i<32u;++i) {
        int a=nibble(name[39u+i*2u]),b=nibble(name[40u+i*2u]);
        if(a<0||b<0)return -1;
        hash[i]=(uint8_t)((unsigned)(a<<4u)|(unsigned)b);
    }
    if(fe_t3s2b1a_name(gen,s,hash,canonical)!=0 ||
       memcmp(name,canonical,full)!=0)return -1;
    *seq=(uint32_t)s;
    return 0;
}
/* A full original S2-A recovered filesystem row is read, not reconstructed
 * from the FRM1 root being verified. B0 independently verifies original
 * fe_s2_decode/replay CRC+FNV, FBS1 exact row SHA and previous full row
 * SHA. We do not generate a fake BF/S1 live-ACK when restoring from disk:
 * the following synthetic receipt is a LOCAL HOSTED REPLAY WITNESS only.
 */
static int source_record(const fe_t3s2a_spool *s,uint32_t seq,
                         fe_t3s1_slot *slot) {
    struct stat st;
    char name[FE_T3S2A_NAME_CAP];
    int fd,ok=-1;
    size_t n;
    if(!s||!slot||fe_t3s2a_record_name((uint64_t)seq,name)!=0)
        return -1;
    fd=openat(s->dirfd,name,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    if(fd<0)return -1;
    if(fstat(fd,&st)!=0||!S_ISREG(st.st_mode)||st.st_nlink!=1||
       st.st_uid!=geteuid()||st.st_size<=(off_t)FE_T3S1_ROW_BYTES||
       st.st_size>(off_t)FE_T3S2A_FILE_BYTES)goto done;
    n=(size_t)st.st_size-FE_T3S1_ROW_BYTES;
    if(read_exact(fd,slot->canonical_row,FE_T3S1_ROW_BYTES)!=0 ||
       read_exact(fd,slot->apx3,n)!=0)goto done;
    slot->apx3_bytes=(uint32_t)n;
    ok=0;
done:
    if(close(fd)!=0)return -1;
    return ok;
}
static int source_image(const fe_t3s2a_spool *source,uint32_t upto,
       fe_t3s2b0_index *index,uint8_t *bytes,size_t *length) {
    fe_t3s2a_spool copy;
    fe_t3s1_slot slot;
    fe_t3s1_drain_receipt ack;
    uint8_t digest[32];
    if(!source||!index||!bytes||!length||!source_ok(source)||
       upto>source->maximum_files || (uint64_t)upto>source->committed)
        return -1;
    copy=*source;
    copy.committed=UINT64_C(0);
    memset(copy.committed_last_row,0,sizeof(copy.committed_last_row));
    memset(copy.prior_row_sha256,0,sizeof(copy.prior_row_sha256));
    if(fe_t3s2b0_bind(index,&copy,copy.maximum_files)!=0)return -1;
    for(uint32_t j=1u;j<=upto;++j) {
        if(source_record(source,j,&slot)!=0 ||
           fe_b1s1_sha256(slot.canonical_row,FE_T3S1_ROW_BYTES,digest)!=0)
            return -1;
        copy.committed=(uint64_t)j;
        memcpy(copy.committed_last_row,slot.canonical_row,FE_T3S1_ROW_BYTES);
        memcpy(copy.prior_row_sha256,digest,sizeof(digest));
        memset(&ack,0,sizeof(ack));
        ack.source_sequence=(uint64_t)j;
        ack.source_capture_id=source->capture_id;
        ack.source_render_id=source->render_id;
        ack.render_event=le32(slot.canonical_row+8u);
        ack.apx3_bytes=slot.apx3_bytes;
        ack.canonical_row_bytes=FE_T3S1_ROW_BYTES;
        ack.actually_accounted_bytes=
            (size_t)slot.apx3_bytes+FE_T3S1_ROW_BYTES;
        if(fe_t3s2b0_observe_acked(index,&slot,&ack)!=0)return -1;
    }
    if(fe_t3s2b0_encode(index,bytes,FE_T3S2B0_MAX_BYTES,length)!=0)
        return -1;
    /* The original source has been verified frame by frame from disk.
     * Rebind the in-memory owner pointer before returning; no dangling
     * pointer to the temporary trusted replay view.
     */
    index->source=source;
    return 0;
}
static int root_bytes(const fe_t3s2b1a_root *r,uint32_t seq,
      const char *filename,const uint8_t named_hash[32],
      uint8_t bytes[FE_T3S2B0_MAX_BYTES],size_t *length,
      struct stat *info) {
    fe_t3s2b0_index expected_index,decoded;
    fe_t3s2a_spool old_source;
    uint8_t expected[FE_T3S2B0_MAX_BYTES],filehash[32];
    size_t need=0u;
    int fd,ok=-1;
    if(!r||!filename||!named_hash||!bytes||!length||
       source_image(r->original_source,seq,&expected_index,
                    expected,&need)!=0)return -1;
    fd=openat(r->root_dirfd,filename,O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
    if(fd<0)return -1;
    struct stat st;
    if(fstat(fd,&st)!=0 || !S_ISREG(st.st_mode) ||
       st.st_uid!=geteuid() || (st.st_mode&0022)!=0 ||
       (st.st_nlink!=1 && st.st_nlink!=2) ||
       st.st_size!=(off_t)need)goto done;
    if(read_exact(fd,bytes,need)!=0 ||
       memcmp(bytes,expected,need)!=0 ||
       fe_b1s1_sha256(bytes,need,filehash)!=0 ||
       memcmp(filehash,named_hash,32u)!=0)goto done;
    /* Original B0 decoder independently validates complete LE+FRM1 root,
     * original full-row source chain and original S2-A last row for this
     * exact historic source high-water. */
    old_source=*r->original_source;
    old_source.committed=(uint64_t)seq;
    memcpy(old_source.committed_last_row,
           expected_index.rows[seq-1u],FE_T3S1_ROW_BYTES);
    if(fe_b1s1_sha256(old_source.committed_last_row,
          FE_T3S1_ROW_BYTES,old_source.prior_row_sha256)!=0 ||
       fe_t3s2b0_decode(&decoded,&old_source,bytes,need)!=0||
       decoded.count!=seq ||
       memcmp(decoded.root_sha256,expected_index.root_sha256,32u)!=0)
        goto done;
    *length=need;
    if(info)*info=st;
    ok=0;
done:
    if(close(fd)!=0)return -1;
    return ok;
}
static int trusted_temp_reconcile(fe_t3s2b1a_root *r,
        const char *final,const char *partial,const struct stat *committed) {
    struct stat temp;
    if(fstatat(r->root_dirfd,partial,&temp,AT_SYMLINK_NOFOLLOW)==0) {
        if(!S_ISREG(temp.st_mode) || !committed ||
           temp.st_dev!=committed->st_dev ||
           temp.st_ino!=committed->st_ino ||
           temp.st_nlink!=2 || committed->st_nlink!=2 ||
           unlinkat(r->root_dirfd,partial,0)!=0 ||
           fsync(r->root_dirfd)!=0)return -1;
    }else if(errno!=ENOENT)return -1;
    (void)final;
    return 0;
}
static int read_inventory(fe_t3s2b1a_root *r,
    uint32_t *root_count,uint8_t last_hash[32]) {
    char names[FE_T3S2B1A_MAX_ROOTS+1u][FE_T3S2B1A_FILENAME_BYTES];
    char parts[FE_T3S2B1A_MAX_ROOTS+1u][FE_T3S2B1A_FILENAME_BYTES];
    uint8_t names_hash[FE_T3S2B1A_MAX_ROOTS+1u][32];
    DIR *dir;
    struct dirent *entry;
    int scanfd,failed=0;
    unsigned found=0u;
    if(!r||!root_count||!last_hash)return -1;
    memset(names,0,sizeof(names));memset(parts,0,sizeof(parts));
    memset(names_hash,0,sizeof(names_hash));
    scanfd=openat(r->root_dirfd,".",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(scanfd<0)return -1;
    struct stat dir_stat;
    if(fstat(scanfd,&dir_stat)!=0 ||
       dir_stat.st_dev!=r->root_device ||
       dir_stat.st_ino!=r->root_inode) {
        (void)close(scanfd);
        return -1;
    }
    dir=fdopendir(scanfd);
    if(!dir){(void)close(scanfd);return -1;}
    errno=0;
    while((entry=readdir(dir))!=NULL) {
        uint8_t hash[32];
        uint32_t seq=0u;
        int partial=0;
        if(!strcmp(entry->d_name,".")||!strcmp(entry->d_name,"..")){
            errno=0;continue;
        }
        if(parse_name(r,entry->d_name,&seq,hash,&partial)!=0){
            failed=1;break;
        }
        if(partial) {
            if(parts[seq][0]!='\0'){failed=1;break;}
            (void)strcpy(parts[seq],entry->d_name);
        }else{
            if(names[seq][0]!='\0'){failed=1;break;}
            (void)strcpy(names[seq],entry->d_name);
            memcpy(names_hash[seq],hash,32u);
            ++found;
        }
        errno=0;
    }
    if(errno!=0)failed=1;
    if(closedir(dir)!=0)failed=1;
    if(failed)return -1;
    for(uint32_t seq=1u;seq<=r->capacity;++seq){
        uint8_t actual[FE_T3S2B0_MAX_BYTES];
        size_t bytes=0u;
        struct stat st;
        if(!names[seq][0]){
            if(parts[seq][0])return -1;
            for(uint32_t later=seq+1u;later<=r->capacity;++later)
                if(names[later][0]||parts[later][0])return -1;
            break;
        }
        if((uint64_t)seq>r->original_source->committed||
           root_bytes(r,seq,names[seq],names_hash[seq],
                      actual,&bytes,&st)!=0)return -1;
        /* A root with no matching canonical .part must have exactly ONE
         * link: a foreign hardlink alias must not be admitted as immutable. */
        if(!parts[seq][0] && st.st_nlink!=1)return -1;
        if(parts[seq][0]){
            char expected[FE_T3S2B1A_FILENAME_BYTES];
            size_t n=strlen(names[seq]);
            if(n+5u>=sizeof(expected))return -1;
            memcpy(expected,names[seq],n);
            memcpy(expected+n,".part",6u);
            if(strcmp(expected,parts[seq])!=0 ||
               trusted_temp_reconcile(r,names[seq],parts[seq],&st)!=0)
                return -1;
        }
        memcpy(last_hash,names_hash[seq],32u);
    }
    if(found>r->capacity)return -1;
    *root_count=found;
    if(!found)memset(last_hash,0,32u);
    return 0;
}
int fe_t3s2b1a_bind(fe_t3s2b1a_root *r,int fd,
                    const fe_t3s2a_spool *source) {
    struct stat st;
    uint32_t n=0u;
    uint8_t last[32]={0};
    if(!r||r->binding_complete||!source_ok(source)||
       fd<0||fstat(fd,&st)!=0||!S_ISDIR(st.st_mode)||
       st.st_uid!=geteuid()||(st.st_mode&0022)!=0 ||
       (st.st_dev==source->device && st.st_ino==source->inode)||
       !apart(r,sizeof(*r),source,sizeof(*source)))return -1;
    memset(r,0,sizeof(*r));
    r->original_source=source;r->root_dirfd=fd;
    r->root_device=st.st_dev;r->root_inode=st.st_ino;
    r->source_generation=source->generation;
    r->capacity=source->maximum_files;
    if(read_inventory(r,&n,last)!=0 ||
       source->committed<(uint64_t)n ||
       source->committed>(uint64_t)n+UINT64_C(1))return -1;
    r->roots_committed=n;
    memcpy(r->last_root_digest,last,32u);
    r->binding_complete=1u;
    r->restart_recovered=(uint32_t)(n!=0u);
    return 0;
}
int fe_t3s2b1a_set_test_fault(fe_t3s2b1a_root *r,fe_t3s2b1a_fault f) {
    if(!root_ok(r,1) || f<FE_T3S2B1A_FAULT_NONE ||
       f>FE_T3S2B1A_FAULT_READBACK)return -1;
    r->fault=f;return 0;
}
int fe_t3s2b1a_rebuild_index(fe_t3s2b0_index *result,
                             const fe_t3s2b1a_root *r) {
    fe_t3s2b0_index temp;
    uint8_t bytes[FE_T3S2B0_MAX_BYTES];
    size_t n=0u;
    if(!root_ok(r,1)||!result||
       !apart(result,sizeof(*result),r,sizeof(*r))||
       !apart(result,sizeof(*result),r->original_source,
              sizeof(*r->original_source)) ||
       r->original_source->committed==UINT64_C(0) ||
       source_image(r->original_source,
           (uint32_t)r->original_source->committed,&temp,bytes,&n)!=0)
        return -1;
    *result=temp;
    return 0;
}
int fe_t3s2b1a_publish(fe_t3s2b1a_root *r,
                        const fe_t3s2b0_index *index) {
    uint8_t data[FE_T3S2B0_MAX_BYTES],origin[FE_T3S2B0_MAX_BYTES],hash[32];
    uint8_t last[32]={0},verify_data[FE_T3S2B0_MAX_BYTES];
    fe_t3s2b0_index replay_index;
    char final[FE_T3S2B1A_FILENAME_BYTES],part[FE_T3S2B1A_FILENAME_BYTES];
    uint32_t inventory=0u,seq;
    size_t len=0u,expected=0u,read_len=0u;
    struct stat st;
    int fd=-1,linked=0;
    if(!root_ok(r,1)||!index||
       !apart(r,sizeof(*r),index,sizeof(*index))||
       !apart(r->original_source,sizeof(*r->original_source),
              index,sizeof(*index)) ||
       r->original_source->committed!=
           (uint64_t)r->roots_committed+UINT64_C(1) ||
       index->source!=r->original_source ||
       index->count!=r->roots_committed+1u ||
       index->maximum_rows!=r->capacity ||
       fe_t3s2b0_encode(index,data,sizeof(data),&len)!=0 ||
       source_image(r->original_source,index->count,
                    &replay_index,origin,&expected)!=0 ||
       expected!=len || memcmp(origin,data,len)!=0 ||
       fe_b1s1_sha256(data,len,hash)!=0 ||
       fe_t3s2b1a_name(r->source_generation,(uint64_t)index->count,
                        hash,final)!=0)
        return -1;
    seq=index->count;
    if(read_inventory(r,&inventory,last)!=0 ||
       (inventory!=r->roots_committed && inventory!=seq) ||
       (inventory==r->roots_committed &&
        memcmp(last,r->last_root_digest,32u)!=0))return -1;
    if(inventory==seq) {
        if(root_bytes(r,seq,final,hash,verify_data,&read_len,&st)!=0 ||
           read_len!=len || memcmp(verify_data,data,len)!=0 ||
           fsync(r->root_dirfd)!=0)return -1;
        r->roots_committed=seq;
        memcpy(r->last_root_digest,hash,32u);
        ++r->retry_after_publish;
        return 0;
    }
    if(strlen(final)+5u>=sizeof(part))return -1;
    (void)strcpy(part,final);
    (void)strcat(part,".part");
    if(r->fault==FE_T3S2B1A_FAULT_CREATE)return -1;
    fd=openat(r->root_dirfd,part,
        O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);
    if(fd<0)return -1;
    if(write_exact(fd,data,len)!=0||
       r->fault==FE_T3S2B1A_FAULT_WRITE ||
       fsync(fd)!=0||
       r->fault==FE_T3S2B1A_FAULT_FILE_SYNC)goto failed;
    if(close(fd)!=0){fd=-1;goto failed;}
    fd=-1;
    if(linkat(r->root_dirfd,part,r->root_dirfd,final,0)!=0)goto failed;
    linked=1;
    if(r->fault==FE_T3S2B1A_FAULT_PUBLISH)goto failed;
    if(unlinkat(r->root_dirfd,part,0)!=0)goto failed;
    if(r->fault==FE_T3S2B1A_FAULT_UNLINK)goto failed;
    if(fsync(r->root_dirfd)!=0||
       r->fault==FE_T3S2B1A_FAULT_DIRECTORY_SYNC)goto failed;
    if(r->fault==FE_T3S2B1A_FAULT_READBACK ||
       root_bytes(r,seq,final,hash,verify_data,&read_len,&st)!=0 ||
       read_len!=len||memcmp(verify_data,data,len)!=0)return -1;
    r->roots_committed=seq;
    memcpy(r->last_root_digest,hash,32u);
    return 0;
failed:
    if(fd>=0)(void)close(fd);
    if(!linked){
        if(unlinkat(r->root_dirfd,part,0)!=0)return -1;
        (void)fsync(r->root_dirfd);
    }
    /* After linkat, an immutable root may already exist: do NOT delete or
     * claim successful publication. Next bind/explicit retry must rehash
     * the original root+source. No original S1/source ACK is manufactured.
     */
    return -1;
}
