/* #825: HOSTED finite prefix retirement; no source ACK or production API.
 * All original codec, FBS1, A0 and A1 inputs remain unchanged.  This module
 * independently opens the anchored directories, validates original bytes,
 * and unlinks only the proven remaining prefix in ascending sequence order.
 */
#define _POSIX_C_SOURCE 200809L
#include "fe09_b2s3_t3s2b1ba2_finite_retirement.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define A2_NAME_LEN 99u
#define A2_TEMP "fpr1.part"
#define A2_ROW FE_T3S1_ROW_BYTES
#define A2_APX FE_T3S1_CHUNK_BYTES

typedef struct {
    uint8_t wire[FE_T3B1BA2_CHECKPOINT_BYTES];
    uint8_t root[FE_T3B1BA1_ROOT_BYTES];
    uint8_t rows[32][A2_ROW];
    uint8_t apx[A2_APX];
    char names[33][FE_T3B1BA0_NAME_CAP];
    struct stat records[33];
    uint8_t seen[33];
    char checkpoint_name[FE_T3B1BA2_NAME_CAP];
    char root_name[FE_T3B1BA1_NAME_CAP];
    fe_t3b1ba2_checkpoint decoded;
} a2_work;

_Static_assert(sizeof(a2_work)<=FE_T3B1BA2_WORKSPACE_BYTES,
    "A2 workspace exceeds its explicit reservation");
/* Includes a conservative local stack reservation for the pure 4768-byte
 * self-digest parser and this module's bounded temporaries, plus explicit
 * readonly tables/predicate-string space.  Compiler stack/section reports
 * must validate these conservative reservations.  Original codec/A0/A1,
 * test fixtures and sanitizer instrumentation are separately attributed.
 */
_Static_assert(sizeof(fe_t3b1ba2_workspace)+sizeof(fe_t3b1ba2_owner)+
    sizeof(fe_t3b1ba2_receipt)+FE_T3B1BA2_LOCAL_STACK_RESERVE+
    FE_T3B1BA2_READONLY_RESERVE<=FE_T3B1BA2_RESOURCE_LIMIT,
    "A2 new owner, workspace and local stack exceed 64 KiB");

static a2_work *a2w(fe_t3b1ba2_owner *s) {
    return (a2_work *)(void *)s->workspace->bytes;
}
static uint32_t g32(const uint8_t *p) {
    return (uint32_t)p[0]|(uint32_t)p[1]<<8u|
        (uint32_t)p[2]<<16u|(uint32_t)p[3]<<24u;
}
static uint64_t g64(const uint8_t *p) {
    return (uint64_t)g32(p)|((uint64_t)g32(p+4u)<<32u);
}
static void p32(uint8_t *p,uint32_t x) {
    for(unsigned i=0u;i<4u;++i)p[i]=(uint8_t)(x>>(8u*i));
}
static void p64(uint8_t *p,uint64_t x) {
    for(unsigned i=0u;i<8u;++i)p[i]=(uint8_t)(x>>(8u*i));
}
static int nz(const uint8_t *p,size_t n) {
    uint8_t x=0u;
    for(size_t i=0u;i<n;++i)x=(uint8_t)(x|p[i]);
    return x!=0u;
}
static int sha(const uint8_t *p,size_t n,uint8_t h[32]) {
    return fe_b1s1_sha256(p,n,h);
}
static int fail(fe_t3b1ba2_owner *s,const char *e) {
    if(s)s->last_error=e;
    return -1;
}
const char *fe_t3b1ba2_error(const fe_t3b1ba2_owner *s) {
    return s&&s->last_error?s->last_error:"OK";
}
const char *fe_t3b1ba2_error_class(const char *e) {
    if(!e||strcmp(e,"OK")==0)return "OK";
    if(strstr(e,"INJECTED_IO")||strstr(e,"PARTIAL_RETIREMENT"))return "IO";
    if(strstr(e,"FPR1_"))return "FPR1";
    if(strstr(e,"FRM2_"))return "FRM2";
    if(strstr(e,"FLAGS_")||strstr(e,"PCM_FNV_"))return "A0_CALLBACK";
    if(strstr(e,"ORIGINAL_RECORD_"))return "ORIGINAL_RECORD";
    if(strstr(e,"APX3")||strstr(e,"CODEC"))return "ORIGINAL_CODEC";
    if(strstr(e,"ANCHOR")||strstr(e,"EXTERNAL_")||strstr(e,"SELF_DIGEST_"))
        return "EXTERNAL_ANCHOR";
    if(strstr(e,"DIRECTORY"))return "DIRECTORY";
    if(strstr(e,"ADMISSION"))return "ORIGINAL_A0_ADMISSION";
    if(strstr(e,"FINITE_STAGE")||strstr(e,"QUIESCENCE")||strstr(e,"STOPPED"))
        return "SCOPE";
    return "FILESYSTEM_NAMESPACE";
}
size_t fe_t3b1ba2_resource_bytes(void) {
    return sizeof(fe_t3b1ba2_workspace)+sizeof(fe_t3b1ba2_owner)+
        sizeof(fe_t3b1ba2_receipt)+FE_T3B1BA2_LOCAL_STACK_RESERVE+
        FE_T3B1BA2_READONLY_RESERVE;
}
size_t fe_t3b1ba2_workspace_used_bytes(void) {return sizeof(a2_work);}
static int source_ok(const fe_b1s0_config *c,const uint32_t slots[4]) {
    uint32_t seen=0u;
    if(!c||!slots||(c->depth!=2u&&c->depth!=4u)||
       (c->physical_mics!=1u&&c->physical_mics!=2u&&c->physical_mics!=4u)||
       (c->input_hz!=16000u&&c->input_hz!=32000u&&c->input_hz!=48000u)||
       c->render_enabled>1u||!c->capture_source_id||!c->source_generation||
       c->source_generation==UINT64_MAX||
       (c->render_enabled?(!c->render_source_id||
        c->render_source_id==c->capture_source_id):c->render_source_id!=0u))
        return 0;
    for(unsigned i=0u;i<4u;++i) {
        if(i>=c->physical_mics) {
            if(slots[i]!=UINT32_MAX)return 0;
        } else {
            if(slots[i]>=c->physical_mics||(seen&(1u<<slots[i])))return 0;
            seen|=1u<<slots[i];
        }
    }
    return seen==((1u<<c->physical_mics)-1u);
}
static const char *row_metadata(const fe_b1s0_config *c,
    const uint32_t slots[4],const uint8_t row[A2_ROW],
    uint64_t seq,const uint8_t prev[32]) {
    uint8_t h[32];
    uint32_t event;
    if(!c||!slots||!row||!prev||!source_ok(c,slots))
        return "ORIGINAL_RECORD_OWNER_INVALID";
    if(g32(row)!=FE_B1S1_MANIFEST_MAGIC||
       g32(row+4u)!=FE_B1S1_MANIFEST_VERSION)
        return "ORIGINAL_RECORD_FORMAT_INVALID";
    if(g32(row+28u)!=c->capture_source_id)
        return "ORIGINAL_RECORD_CAPTURE_ID_CHANGED";
    if(g64(row+20u)!=c->source_generation)
        return "ORIGINAL_RECORD_GENERATION_CHANGED";
    if(g32(row+12u)!=c->input_hz)
        return "ORIGINAL_RECORD_UNSUPPORTED_OR_CHANGED_RATE";
    if(g32(row+16u)!=c->physical_mics)
        return "ORIGINAL_RECORD_PHYSICAL_MIC_COUNT_CHANGED";
    event=g32(row+8u);
    if(event>FE_B1S0_RENDER_ABSENT||
       (c->render_enabled?event==FE_B1S0_RENDER_DISABLED:
        event!=FE_B1S0_RENDER_DISABLED))
        return "ORIGINAL_RECORD_RENDER_OWNER_ENABLED_CHANGED";
    if(g32(row+32u)!=c->render_source_id)
        return "ORIGINAL_RECORD_RENDER_SOURCE_ID_CHANGED";
    if(g32(row+36u)!=1u||
       (c->render_enabled?g32(row+40u)==0u:g32(row+40u)!=0u))
        return "ORIGINAL_RECORD_CAPTURE_OR_RENDER_EPOCH_CHANGED";
    if(event==FE_B1S0_RENDER_ABSENT?
       g32(row+44u)!=FE_B1S0_ABSENT_SOURCE_REPORTED:g32(row+44u)!=0u)
        return "ORIGINAL_RECORD_ABSENT_REASON_CHANGED";
    for(unsigned i=0u;i<4u;++i)
        if(g32(row+88u+4u*i)!=slots[i])
            return "ORIGINAL_RECORD_DUPLICATE_OR_CHANGED_PHYSICAL_SLOT_MAP";
    if(!seq||seq>32u||g64(row+48u)!=seq)
        return "ORIGINAL_RECORD_GLOBAL_SEQUENCE_CHANGED";
    if(g64(row+56u)!=UINT64_C(1))
        return "ORIGINAL_RECORD_LOCAL_APX3_SEQUENCE_NOT_1";
    if(g32(row+64u)!=1u)return "ORIGINAL_RECORD_LOCAL_FRAME_COUNT_NOT_1";
    if(!g32(row+68u)||g32(row+68u)>A2_APX)
        return "ORIGINAL_RECORD_APX3_LENGTH_INVALID";
    if(memcmp(row+136u,prev,32u)!=0)
        return seq==1u?"ORIGINAL_RECORD_FIRST_RETIRED_ROW_PRIOR_NONZERO":
            "ORIGINAL_RECORD_ROW_PREFIX_DIGEST_SUBSTITUTED_FOR_WHOLE_ROW_ANCHOR";
    if(event!=FE_B1S0_RENDER_PRESENT&&g64(row+80u)!=UINT64_C(0))
        return "ORIGINAL_RECORD_RENDER_FNV_NONZERO_WHEN_ABSENT";
    if(sha(row,168u,h)!=0||memcmp(h,row+168u,32u)!=0)
        return "ORIGINAL_RECORD_LAST_ROW_DIGEST_CHANGED";
    return NULL;
}
typedef struct {
    uint64_t capture_hash,render_hash;
    uint32_t rate,mics,render,seen;
    const char *error;
} a2_pcm_witness;
static uint64_t fnv(const uint8_t *p,size_t n) {
    uint64_t h=UINT64_C(14695981039346656037);
    for(size_t i=0u;i<n;++i)h=(h^(uint64_t)p[i])*UINT64_C(1099511628211);
    return h;
}
static int pcm(const fe_s2_stream *stream,uint32_t index,
    uint64_t seq,uint32_t capture_flags,uint32_t render_flags,
    const uint8_t *capture,size_t nc,const uint8_t *render,size_t nr,
    void *context) {
    a2_pcm_witness *w=(a2_pcm_witness *)context;
    if(!stream||!w)return 1;
    if(capture_flags)w->error="CAPTURE_FLAGS_NONZERO";
    else if(render_flags)w->error="RENDER_FLAGS_NONZERO";
    else if(index||seq!=UINT64_C(1)||stream->frames!=1u||
        stream->config.rate_hz!=w->rate||
        stream->config.physical_mics!=w->mics||
        stream->config.render_channels!=w->render||
        nc!=(size_t)w->rate*w->mics/50u||
        nr!=(size_t)w->rate*w->render/50u||!capture||
        (nr?!render:render!=NULL))
        w->error="ORIGINAL_CODEC_CALLBACK_SHAPE_INVALID";
    else if(fnv(capture,nc)!=w->capture_hash)
        w->error="CAPTURE_PCM_FNV_MISMATCH";
    else if(nr?fnv(render,nr)!=w->render_hash:w->render_hash!=UINT64_C(0))
        w->error="RENDER_PCM_FNV_MISMATCH";
    else {w->seen=1u;return 0;}
    return 1;
}
const char *fe_t3b1ba2_validate_record(const fe_b1s0_config *c,
    const uint32_t slots[4],const uint8_t row[A2_ROW],
    const uint8_t *apx,size_t n,uint64_t seq,const uint8_t prev[32]) {
    uint8_t h[32];
    fe_s2_stream stream;
    a2_pcm_witness w;
    const char *e=row_metadata(c,slots,row,seq,prev);
    if(e)return e;
    if(!apx||n==0u||n>A2_APX||g32(row+68u)!=(uint32_t)n)
        return "ORIGINAL_RECORD_APX3_LENGTH_INVALID";
    if(sha(apx,n,h)!=0||memcmp(h,row+104u,32u)!=0)
        return seq>=17u?"RETAINED_ORIGINAL_APX3_DIGEST_MISMATCH":
            "REMAINING_RETIRED_ORIGINAL_APX3_DIGEST_MISMATCH";
    if(fe_s2_decode(apx,n,&stream)!=FE_S2_OK)
        return "ORIGINAL_CODEC_DECODE_REJECTED";
    uint32_t with_render=(uint32_t)(g32(row+8u)==FE_B1S0_RENDER_PRESENT);
    if(stream.frames!=1u||stream.total_bytes!=n||
       stream.config.rate_hz!=c->input_hz||
       stream.config.physical_mics!=c->physical_mics||
       stream.config.render_channels!=with_render||
       stream.config.capture_source_id!=c->capture_source_id||
       stream.config.render_source_id!=(with_render?c->render_source_id:0u)||
       stream.config.capture_epoch!=1u||
       stream.config.render_epoch!=(with_render?g32(row+40u):0u)||
       stream.config.clock_authority||stream.config.capture_timestamp_valid||
       stream.config.render_timestamp_valid)
        return "ORIGINAL_CODEC_OWNER_OR_STREAM_CHANGED";
    for(unsigned i=0u;i<4u;++i)
        if(stream.config.physical_to_capture_slot[i]!=slots[i])
            return "ORIGINAL_RECORD_DUPLICATE_OR_CHANGED_PHYSICAL_SLOT_MAP";
    memset(&w,0,sizeof(w));
    w.rate=c->input_hz;w.mics=c->physical_mics;w.render=with_render;
    w.capture_hash=g64(row+72u);w.render_hash=g64(row+80u);
    if(fe_s2_replay(apx,n,pcm,&w,NULL)!=FE_S2_OK||w.seen!=1u)
        return w.error?w.error:"ORIGINAL_CODEC_REPLAY_REJECTED";
    return NULL;
}
static const char *frm2(const uint8_t *r,fe_t3b1ba2_checkpoint *v) {
    uint8_t copy[FE_T3B1BA1_ROOT_BYTES],h[32];
    if(g32(r)!=FE_T3B1BA1_MAGIC||g32(r+4u)!=2u||g32(r+8u)!=224u||
       g32(r+12u)!=72u||g32(r+16u)!=1376u||g32(r+20u)!=16u||
       g32(r+24u)!=32u||g64(r+72u)!=17u||g64(r+80u)!=32u||
       g64(r+88u)!=32u||g32(r+196u)!=10u||g32(r+200u)!=1u||
       g32(r+204u)!=200u||g32(r+208u)!=32u||nz(r+212u,12u))
        return "FRM2_FORMAT_OR_FINITE_WINDOW_INVALID";
    memset(v,0,sizeof(*v));
    v->source.capture_source_id=g32(r+28u);
    v->source.source_generation=g64(r+32u);
    v->source.input_hz=g32(r+40u);
    v->source.physical_mics=g32(r+44u);
    v->source.render_enabled=g32(r+48u);
    v->source.render_source_id=g32(r+52u);
    v->source.depth=g32(r+192u);
    for(unsigned i=0u;i<4u;++i)v->slots[i]=g32(r+56u+4u*i);
    if(!source_ok(&v->source,v->slots))return "FRM2_ORIGINAL_OWNER_INVALID";
    memcpy(copy,r,sizeof(copy));memset(copy+160u,0,32u);
    if(sha(copy,sizeof(copy),h)!=0||memcmp(h,r+160u,32u)!=0)
        return "FRM2_SELF_DIGEST_MISMATCH";
    for(unsigned i=0u;i<16u;++i)
        if(g64(r+224u+72u*i)!=(uint64_t)i+17u)
            return "FRM2_MEMBER_SEQUENCE_INVALID";
    if(memcmp(r+128u,r+224u+15u*72u+8u,32u)!=0)
        return "FRM2_LAST_ROW_ANCHOR_MISMATCH";
    return NULL;
}
const char *fe_t3b1ba2_validate_checkpoint(const uint8_t *b,size_t n,
    fe_t3b1ba2_checkpoint *out) {
    uint8_t copy[FE_T3B1BA2_CHECKPOINT_BYTES],h[32],prior[32]={0};
    fe_t3b1ba2_checkpoint v;
    const char *e;
    uint64_t retired=0u;
    if(!b||n<FE_T3B1BA2_CHECKPOINT_BYTES)return "FPR1_TRUNCATED_FPR1";
    if(n>FE_T3B1BA2_CHECKPOINT_BYTES)return "FPR1_TRAILING_FPR1_BYTES";
    if(g32(b)!=FE_T3B1BA2_MAGIC)return "FPR1_INVALID_FPR1_MAGIC";
    if(g32(b+4u)!=1u)return "FPR1_UNSUPPORTED_FPR1_VERSION";
    if(g32(b+8u)!=192u)return "FPR1_INVALID_FPR1_HEADER_SIZE";
    if(g32(b+12u)!=4768u)return "FPR1_INVALID_FPR1_TOTAL_SIZE";
    if(g32(b+16u)!=1376u)return "FPR1_INVALID_EMBEDDED_FRM2_SIZE";
    if(g32(b+20u)!=16u)return "FPR1_RETIRED_COUNT_NOT_16";
    if(g32(b+24u)!=16u)return "FPR1_RETAINED_COUNT_NOT_16";
    if(g32(b+28u)!=32u)return "FPR1_ORIGINAL_COUNT_NOT_32";
    if(g64(b+48u)!=1u)return "FPR1_RETIRED_FIRST_NOT_1";
    if(g64(b+56u)!=16u)return "FPR1_RETIRED_LAST_NOT_16";
    if(g64(b+64u)!=17u)return "FPR1_RETAINED_FIRST_NOT_17";
    if(g64(b+72u)!=32u)return "FPR1_RETAINED_LAST_NOT_32";
    if(g64(b+80u)!=32u)return "FPR1_ORIGINAL_HIGH_WATER_NOT_32";
    if(nz(b+176u,16u))return "FPR1_NONZERO_RESERVED_BYTES";
    memcpy(copy,b,sizeof(copy));memset(copy+120u,0,32u);
    if(sha(copy,sizeof(copy),h)!=0||memcmp(h,b+120u,32u)!=0)
        return "FPR1_INVALID_CHECKPOINT_SELF_DIGEST";
    if(sha(b+192u,1376u,h)!=0||memcmp(h,b+88u,32u)!=0)
        return "FPR1_INVALID_EMBEDDED_FRM2_RAW_DIGEST";
    e=frm2(b+192u,&v);if(e)return e;
    if(g32(b+32u)!=v.source.capture_source_id||
       g32(b+36u)!=v.source.input_hz||g64(b+40u)!=v.source.source_generation)
        return "FPR1_ORIGINAL_OWNER_MISMATCH";
    for(unsigned i=0u;i<16u;++i) {
        const uint8_t *row=b+FE_T3B1BA2_RETIRED_OFFSET+i*A2_ROW;
        e=row_metadata(&v.source,v.slots,row,(uint64_t)i+1u,prior);
        if(e)return e;
        if(sha(row,A2_ROW,prior)!=0)return "FPR1_RETIRED_ROW_SHA_FAILED";
        uint64_t bytes=(uint64_t)A2_ROW+g32(row+68u);
        if(retired>UINT64_MAX-bytes)
            return "FPR1_BYTE_TOTAL_OVERFLOW_OR_INCONSISTENT_SUM";
        retired+=bytes;
    }
    if(memcmp(prior,b+192u+96u,32u)!=0)
        return "FPR1_RETIRED_CHAIN_LEFT_ANCHOR_MISMATCH";
    v.original_logical_bytes=g64(b+152u);
    v.retained_logical_bytes=g64(b+160u);
    v.retired_logical_bytes=g64(b+168u);
    if(v.retired_logical_bytes!=retired||
       v.retained_logical_bytes<16u*(A2_ROW+1u)||
       v.retained_logical_bytes>16u*(A2_ROW+A2_APX)||
       v.retired_logical_bytes>UINT64_MAX-v.retained_logical_bytes||
       v.original_logical_bytes!=v.retired_logical_bytes+v.retained_logical_bytes||
       v.original_logical_bytes>32u*(A2_ROW+A2_APX))
        return "FPR1_BYTE_TOTAL_OVERFLOW_OR_INCONSISTENT_SUM";
    if(sha(b,n,v.checkpoint_raw_sha256)!=0)return "FPR1_SHA_FAILED";
    memcpy(v.checkpoint_self_sha256,b+120u,32u);
    memcpy(v.original_frm2_raw_sha256,b+88u,32u);
    if(out)*out=v;
    return NULL;
}
static void hex32(const uint8_t h[32],char out[65]) {
    static const char hex[]="0123456789abcdef";
    for(unsigned i=0u;i<32u;++i) {
        out[2u*i]=hex[h[i]>>4u];out[2u*i+1u]=hex[h[i]&15u];
    }
    out[64u]='\0';
}
int fe_t3b1ba2_name(const uint8_t b[FE_T3B1BA2_CHECKPOINT_BYTES],
    char out[FE_T3B1BA2_NAME_CAP]) {
    char digest[65];
    if(!b||!out||g32(b)!=FE_T3B1BA2_MAGIC||!g32(b+32u)||
       !g64(b+40u)||g64(b+40u)==UINT64_MAX)return -1;
    hex32(b+120u,digest);
    int n=snprintf(out,FE_T3B1BA2_NAME_CAP,
        "fpr1-%08" PRIx32 "-%016" PRIx64 "-%s.bin",
        g32(b+32u),g64(b+40u),digest);
    return n==(int)A2_NAME_LEN?0:-1;
}
const uint8_t *fe_t3b1ba2_prepared_bytes(const fe_t3b1ba2_owner *s) {
    if(!s||!s->workspace||!s->prepared)return NULL;
    return ((const a2_work *)(const void *)s->workspace->bytes)->wire;
}

/* Only wrappers below have a fault seam.  Original A0/A1/codec calls are
 * never interposed.  The wrapper reports what really ran and what the
 * candidate observed; this distinction is essential for short I/O/close.
 */
static void event_start(fe_t3b1ba2_owner *s,fe_t3b1ba2_io_event *e,
    uint32_t op,uint32_t role,uint32_t seq,size_t bytes) {
    memset(e,0,sizeof(*e));e->phase=s->phase;e->operation=op;
    e->role=role;e->sequence=seq;e->requested_bytes=(uint64_t)bytes;
    e->ordinal=++s->io_ordinal;
}
static void event_done(fe_t3b1ba2_owner *s,fe_t3b1ba2_io_event *e,
    int64_t actual,int actual_errno,int64_t reported,int reported_errno) {
    e->actual_result=actual;e->actual_errno=actual_errno;
    e->reported_result=reported;e->reported_errno=reported_errno;
    ++s->io.operations[e->operation];
    if(e->syscall_called)++s->io.actual_operations[e->operation];
    if(e->injected) {++s->io.injected_events;s->fault_fired=1u;}
    if(e->operation==FE_T3B1BA2_IO_UNLINK&&e->role==FE_T3B1BA2_ROLE_RECORD) {
        ++s->io.data_unlinks;
        if(e->syscall_called&&actual==0)++s->io.successful_data_unlinks;
    }
    if(e->operation==FE_T3B1BA2_IO_FSYNC&&e->role==FE_T3B1BA2_ROLE_DATA_DIR) {
        ++s->io.data_dir_syncs;
        if(e->syscall_called&&actual==0)++s->io.successful_data_dir_syncs;
    }
    if(s->hooks.io)s->hooks.io(e,s->hooks.context);
    if(reported<0)errno=reported_errno;
}
static int fault_match(fe_t3b1ba2_owner *s,fe_t3b1ba2_io_event *e) {
    uint32_t f=s->test_fault,op=e->operation,r=e->role,q=e->sequence;
    int match=0;
    if(f==108u)match=op==FE_T3B1BA2_IO_FSTAT&&r==FE_T3B1BA2_ROLE_A1_DIR;
    else if(f==114u)match=op==FE_T3B1BA2_IO_FSTAT&&r==FE_T3B1BA2_ROLE_RECORD&&q==9u;
    else if(f==121u||f==122u)match=op==FE_T3B1BA2_IO_OPEN&&r==FE_T3B1BA2_ROLE_TEMP;
    else if(f==123u||f==124u)match=op==FE_T3B1BA2_IO_WRITE&&r==FE_T3B1BA2_ROLE_TEMP;
    else if(f==125u)match=op==FE_T3B1BA2_IO_FSYNC&&r==FE_T3B1BA2_ROLE_TEMP;
    else if(f==126u)match=op==FE_T3B1BA2_IO_LINK;
    else if(f==127u)match=op==FE_T3B1BA2_IO_UNLINK&&r==FE_T3B1BA2_ROLE_TEMP;
    else if(f==128u)match=op==FE_T3B1BA2_IO_FSYNC&&r==FE_T3B1BA2_ROLE_CONTROL_DIR;
    else if(f==129u||f==130u)match=op==FE_T3B1BA2_IO_READ&&r==FE_T3B1BA2_ROLE_CHECKPOINT;
    else if(f==131u)match=op==FE_T3B1BA2_IO_CLOSE&&r==FE_T3B1BA2_ROLE_CHECKPOINT;
    else if(f==132u)match=op==FE_T3B1BA2_IO_FSYNC&&r==FE_T3B1BA2_ROLE_A1_FILE;
    else if(f==133u)match=op==FE_T3B1BA2_IO_FSYNC&&r==FE_T3B1BA2_ROLE_A1_DIR;
    else if(f==134u||f==143u)match=op==FE_T3B1BA2_IO_OPEN&&r==FE_T3B1BA2_ROLE_RECORD&&q==9u;
    else if(f==135u)match=op==FE_T3B1BA2_IO_FSTAT&&r==FE_T3B1BA2_ROLE_RECORD&&q==9u;
    else if(f==136u||f==137u)match=op==FE_T3B1BA2_IO_READ&&r==FE_T3B1BA2_ROLE_RECORD&&q==9u;
    else if(f==138u)match=op==FE_T3B1BA2_IO_CLOSE&&r==FE_T3B1BA2_ROLE_RECORD&&q==9u;
    else if(f==139u||f==140u)match=op==FE_T3B1BA2_IO_UNLINK&&r==FE_T3B1BA2_ROLE_RECORD&&q==9u;
    else if(f==141u)match=op==FE_T3B1BA2_IO_FSYNC&&r==FE_T3B1BA2_ROLE_DATA_DIR&&q==9u;
    else if(f==142u)match=op==FE_T3B1BA2_IO_READDIR&&r==FE_T3B1BA2_ROLE_DATA_ENUM;
    else if(f==144u)match=op==FE_T3B1BA2_IO_OPEN&&r==FE_T3B1BA2_ROLE_RECORD&&q==17u;
    if(match) {
        e->matching_ordinal=++s->fault_matching_ordinal;
        e->fault_id=f;
    }
    return match;
}
static int inject_before(fe_t3b1ba2_owner *s,fe_t3b1ba2_io_event *e) {
    if(!fault_match(s,e))return 0;
    uint32_t f=s->test_fault;
    if(f==108u||f==114u||f==131u||f==138u)return 0;
    if((f==124u||f==130u||f==137u)&&e->matching_ordinal==1u)return 0;
    e->injected=1u;
    int error=(f==121u)?ENOSPC:(f==122u||f==140u)?EROFS:
        f==143u?EMFILE:f==144u?ENOENT:EIO;
    if((f==130u||f==137u)&&e->matching_ordinal==2u) {
        event_done(s,e,0,0,0,0);return 1;
    }
    event_done(s,e,-1,0,-1,error);return 1;
}
static int io_open(fe_t3b1ba2_owner *s,int directory,const char *name,
    int flags,mode_t mode,uint32_t role,uint32_t seq) {
    fe_t3b1ba2_io_event e;
    event_start(s,&e,FE_T3B1BA2_IO_OPEN,role,seq,0u);
    if(inject_before(s,&e))return (int)e.reported_result;
    errno=0;int fd=openat(directory,name,flags,mode),error=fd<0?errno:0;
    e.syscall_called=1u;event_done(s,&e,fd,error,fd,error);return fd;
}
static int io_stat(fe_t3b1ba2_owner *s,int fd,struct stat *st,
    uint32_t role,uint32_t seq) {
    fe_t3b1ba2_io_event e;
    event_start(s,&e,FE_T3B1BA2_IO_FSTAT,role,seq,0u);
    if(inject_before(s,&e))return -1;
    errno=0;int result=fstat(fd,st),error=result<0?errno:0;
    e.syscall_called=1u;
    if(result==0) {
        e.actual_device=e.observed_device=(uint64_t)st->st_dev;
        e.actual_uid=e.observed_uid=(uint64_t)st->st_uid;
        if(e.matching_ordinal&&s->test_fault==108u) {
            st->st_dev=(dev_t)((uint64_t)st->st_dev^UINT64_C(1));
            e.observed_device=(uint64_t)st->st_dev;e.injected=1u;
        }
        if(e.matching_ordinal&&s->test_fault==114u) {
            st->st_uid=geteuid()==(uid_t)0?(uid_t)1:(uid_t)0;
            e.observed_uid=(uint64_t)st->st_uid;e.injected=1u;
        }
    }
    event_done(s,&e,result,error,result,error);return result;
}
static int io_statat(fe_t3b1ba2_owner *s,int directory,const char *name,
    struct stat *st,uint32_t role,uint32_t seq) {
    fe_t3b1ba2_io_event e;
    event_start(s,&e,FE_T3B1BA2_IO_FSTATAT,role,seq,0u);
    errno=0;int r=fstatat(directory,name,st,AT_SYMLINK_NOFOLLOW),er=r<0?errno:0;
    e.syscall_called=1u;
    if(r==0) {
        e.actual_device=e.observed_device=(uint64_t)st->st_dev;
        e.actual_uid=e.observed_uid=(uint64_t)st->st_uid;
    }
    event_done(s,&e,r,er,r,er);return r;
}
static int io_flags(fe_t3b1ba2_owner *s,int fd,uint32_t role) {
    fe_t3b1ba2_io_event e;
    event_start(s,&e,FE_T3B1BA2_IO_FLAGS,role,0u,0u);
    errno=0;int r=fcntl(fd,F_GETFL),er=r<0?errno:0;
    e.syscall_called=1u;event_done(s,&e,r,er,r,er);return r;
}
static ssize_t io_read(fe_t3b1ba2_owner *s,int fd,uint8_t *b,size_t n,
    uint32_t role,uint32_t seq) {
    fe_t3b1ba2_io_event e;
    event_start(s,&e,FE_T3B1BA2_IO_READ,role,seq,n);
    if(inject_before(s,&e))return (ssize_t)e.reported_result;
    if(e.matching_ordinal==1u&&s->test_fault==130u) {n=2384u;e.injected=1u;}
    if(e.matching_ordinal==1u&&s->test_fault==137u) {n=100u;e.injected=1u;}
    errno=0;ssize_t r=read(fd,b,n);int er=r<0?errno:0;
    e.syscall_called=1u;event_done(s,&e,r,er,r,er);return r;
}
static ssize_t io_write(fe_t3b1ba2_owner *s,int fd,const uint8_t *b,size_t n) {
    fe_t3b1ba2_io_event e;
    event_start(s,&e,FE_T3B1BA2_IO_WRITE,FE_T3B1BA2_ROLE_TEMP,0u,n);
    if(inject_before(s,&e))return (ssize_t)e.reported_result;
    if(e.matching_ordinal==1u&&s->test_fault==124u) {n=2384u;e.injected=1u;}
    errno=0;ssize_t r=write(fd,b,n);int er=r<0?errno:0;
    e.syscall_called=1u;event_done(s,&e,r,er,r,er);return r;
}
static int io_sync(fe_t3b1ba2_owner *s,int fd,uint32_t role,uint32_t seq) {
    fe_t3b1ba2_io_event e;
    event_start(s,&e,FE_T3B1BA2_IO_FSYNC,role,seq,0u);
    if(inject_before(s,&e))return -1;
    errno=0;int r=fsync(fd),er=r<0?errno:0;
    e.syscall_called=1u;event_done(s,&e,r,er,r,er);return r;
}
static int io_close(fe_t3b1ba2_owner *s,int fd,uint32_t role,uint32_t seq) {
    fe_t3b1ba2_io_event e;
    event_start(s,&e,FE_T3B1BA2_IO_CLOSE,role,seq,0u);
    (void)fault_match(s,&e);
    errno=0;int r=close(fd),er=r<0?errno:0;
    e.syscall_called=1u;
    if(r==0&&e.matching_ordinal&&(s->test_fault==131u||s->test_fault==138u)) {
        e.injected=1u;event_done(s,&e,r,er,-1,EIO);return -1;
    }
    event_done(s,&e,r,er,r,er);return r;
}
static int io_link(fe_t3b1ba2_owner *s,const char *final_name) {
    fe_t3b1ba2_io_event e;
    event_start(s,&e,FE_T3B1BA2_IO_LINK,FE_T3B1BA2_ROLE_TEMP,0u,0u);
    if(inject_before(s,&e))return -1;
    errno=0;int r=linkat(s->dirfd[2],A2_TEMP,s->dirfd[2],final_name,0),er=r<0?errno:0;
    e.syscall_called=1u;event_done(s,&e,r,er,r,er);return r;
}
static int io_unlink(fe_t3b1ba2_owner *s,int directory,const char *name,
    uint32_t role,uint32_t seq) {
    fe_t3b1ba2_io_event e;
    event_start(s,&e,FE_T3B1BA2_IO_UNLINK,role,seq,0u);
    if(inject_before(s,&e))return -1;
    errno=0;int r=unlinkat(directory,name,0),er=r<0?errno:0;
    e.syscall_called=1u;event_done(s,&e,r,er,r,er);return r;
}
static struct dirent *io_readdir(fe_t3b1ba2_owner *s,DIR *d,uint32_t role) {
    fe_t3b1ba2_io_event e;
    event_start(s,&e,FE_T3B1BA2_IO_READDIR,role,0u,0u);
    if(inject_before(s,&e))return NULL;
    errno=0;struct dirent *entry=readdir(d);int er=entry?0:errno;
    e.syscall_called=1u;
    event_done(s,&e,entry?1:er?-1:0,er,entry?1:er?-1:0,er);
    errno=er;return entry;
}
static int io_closedir(fe_t3b1ba2_owner *s,DIR *d,uint32_t role) {
    fe_t3b1ba2_io_event e;
    event_start(s,&e,FE_T3B1BA2_IO_CLOSEDIR,role,0u,0u);
    errno=0;int r=closedir(d),er=r<0?errno:0;
    e.syscall_called=1u;event_done(s,&e,r,er,r,er);return r;
}
static int read_all(fe_t3b1ba2_owner *s,int fd,uint8_t *p,size_t n,
    uint32_t role,uint32_t seq) {
    while(n) {
        ssize_t r=io_read(s,fd,p,n,role,seq);
        if(r<0&&errno==EINTR)continue;
        if(r<=0||(size_t)r>n)return -1;
        p+=(size_t)r;n-=(size_t)r;
    }
    return 0;
}
static int write_all(fe_t3b1ba2_owner *s,int fd,const uint8_t *p,size_t n) {
    while(n) {
        ssize_t r=io_write(s,fd,p,n);
        if(r<0&&errno==EINTR)continue;
        if(r<=0||(size_t)r>n)return -1;
        p+=(size_t)r;n-=(size_t)r;
    }
    return 0;
}
static void barrier(fe_t3b1ba2_owner *s,uint32_t p) {
    if(s->hooks.barrier)s->hooks.barrier(p,s->hooks.context);
}
int fe_t3b1ba2_set_test_fault(fe_t3b1ba2_owner *s,uint32_t id) {
    if(!s||!s->initialized||
       !(id==0u||id==108u||id==114u||(id>=121u&&id<=144u)))return -1;
    s->test_fault=id;s->fault_fired=0u;s->fault_matching_ordinal=0u;return 0;
}

static int io_failure(fe_t3b1ba2_owner *s) {
    return fail(s,s->fault_fired?"INJECTED_IO_FAILURE":"HOSTED_IO_FAILURE");
}
static int same_stat(const struct stat *a,const struct stat *b) {
    return a->st_dev==b->st_dev&&a->st_ino==b->st_ino&&
        a->st_uid==b->st_uid&&a->st_mode==b->st_mode&&
        a->st_nlink==b->st_nlink&&a->st_size==b->st_size;
}
static int directories(fe_t3b1ba2_owner *s,
    const fe_t3b1ba2_anchor *expected,fe_t3b1ba2_anchor *observed) {
    static const char *const changed[3]={"DATA_DIRECTORY_IDENTITY_CHANGED",
        "A1_DIRECTORY_IDENTITY_CHANGED","A2_DIRECTORY_IDENTITY_CHANGED"};
    struct stat st[3];
    for(unsigned i=0u;i<3u;++i) {
        if(io_stat(s,s->dirfd[i],&st[i],i+1u,0u)!=0)return io_failure(s);
        if(!S_ISDIR(st[i].st_mode)||st[i].st_uid!=geteuid()||
           (st[i].st_mode&0022)!=0)return fail(s,"DIRECTORY_OWNER_OR_MODE_INVALID");
        int flags=io_flags(s,s->dirfd[i],i+1u);
        if(flags<0)return io_failure(s);
        if(!(flags&O_DIRECTORY)||!(flags&O_NOFOLLOW))
            return fail(s,"DIRECTORY_OPEN_FLAGS_INVALID");
    }
    for(unsigned i=0u;i<3u;++i)for(unsigned j=i+1u;j<3u;++j)
        if(st[i].st_dev==st[j].st_dev&&st[i].st_ino==st[j].st_ino)
            return fail(s,"DIRECTORY_ALIAS");
    if(st[0].st_dev!=st[1].st_dev||st[0].st_dev!=st[2].st_dev)
        return fail(s,"CROSS_DEVICE_DIRECTORY_TUPLE");
    for(unsigned i=0u;i<3u;++i) {
        if(expected&&((uint64_t)st[i].st_dev!=expected->device[i]||
           (uint64_t)st[i].st_ino!=expected->inode[i]))return fail(s,changed[i]);
        if(observed) {
            observed->device[i]=(uint64_t)st[i].st_dev;
            observed->inode[i]=(uint64_t)st[i].st_ino;
        }
    }
    return 0;
}
static int anchor_equal(const fe_t3b1ba2_anchor *a,const fe_t3b1ba2_anchor *b) {
    if(!a||!b||a->capture_source_id!=b->capture_source_id||
       a->source_generation!=b->source_generation||
       memcmp(a->checkpoint_raw_sha256,b->checkpoint_raw_sha256,32u)!=0)
        return 0;
    for(unsigned i=0u;i<3u;++i)
        if(a->device[i]!=b->device[i]||a->inode[i]!=b->inode[i])return 0;
    return 1;
}
static int expected_anchor(fe_t3b1ba2_owner *s,const fe_t3b1ba2_anchor *a) {
    if(!a)return fail(s,s->anchor_bound?"MISSING_EXTERNAL_ANCHOR":
        "RECOVERY_EXTERNAL_ANCHOR_REQUIRED");
    if(!nz(a->checkpoint_raw_sha256,32u))return fail(s,"ZERO_EXTERNAL_FILE_DIGEST");
    if(!s->anchor_bound)return fail(s,"RECOVERY_EXTERNAL_ANCHOR_REQUIRED");
    if(!anchor_equal(&s->anchor,a))return fail(s,"BOUND_OWNER_EXPECTED_ANCHOR_CHANGED");
    return directories(s,a,NULL);
}
static DIR *open_directory(fe_t3b1ba2_owner *s,unsigned index,uint32_t role) {
    int duplicate=io_open(s,s->dirfd[index],".",
        O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC,0,role,0u);
    if(duplicate<0){(void)io_failure(s);return NULL;}
    DIR *d=fdopendir(duplicate);
    if(!d) {
        (void)io_close(s,duplicate,role,0u);(void)io_failure(s);return NULL;
    }
    return d;
}
/* Empty control is accepted only by prepare/publication.  Read and resume
 * never repair an incomplete namespace, even if final bytes are readable.
 */
static int root_namespace(fe_t3b1ba2_owner *s,unsigned index,
    int require_empty,char name[FE_T3B1BA2_NAME_CAP]) {
    uint32_t role=index==2u?FE_T3B1BA2_ROLE_CONTROL_ENUM:FE_T3B1BA2_ROLE_A1_ENUM;
    DIR *d=open_directory(s,index,role);
    if(!d)return -1;
    unsigned count=0u,unknown=0u;
    const char *problem=NULL;
    for(;;) {
        struct dirent *de=io_readdir(s,d,role);
        if(!de) {if(errno)problem="IO";break;}
        const char *n=de->d_name;
        if(strcmp(n,".")==0||strcmp(n,"..")==0)continue;
        ++count;
        size_t len=strlen(n);
        int canonical=index==2u?
            (len==A2_NAME_LEN&&strncmp(n,"fpr1-",5u)==0&&strcmp(n+len-4u,".bin")==0):
            (len==149u&&strncmp(n,"fr2-",4u)==0&&strcmp(n+len-4u,".bin")==0);
        if(!canonical){unknown=1u;break;}
        if(count==1u&&len<FE_T3B1BA2_NAME_CAP)memcpy(name,n,len+1u);
        if(require_empty||count>1u)break; /* ambiguity is already proven */
    }
    if(io_closedir(s,d,role)!=0)problem="IO";
    if(problem)return io_failure(s);
    if(require_empty)
        return count?fail(s,unknown?"ORPHAN_OR_UNKNOWN_CONTROL_TEMP":"MULTIPLE_CONTROL_ROOTS"):0;
    if(unknown)return fail(s,index==2u?"ORPHAN_OR_UNKNOWN_CONTROL_TEMP":"FRM2_UNKNOWN_ROOT_ENTRY");
    if(count>1u)return fail(s,index==2u?"MULTIPLE_CONTROL_ROOTS":"FRM2_MULTIPLE_ROOTS");
    if(count!=1u)return fail(s,index==2u?"MISSING_CONTROL_ROOT":"FRM2_ROOT_MISSING");
    return 0;
}
static const char *file_metadata(const struct stat *st,uint32_t role,
    size_t min_bytes,size_t max_bytes) {
    int record=role==FE_T3B1BA2_ROLE_RECORD;
    if(S_ISLNK(st->st_mode))return record?"SYMLINK_RECORD":"SYMLINK_CONTROL_ROOT";
    if(!S_ISREG(st->st_mode))return record?"NONREGULAR_RECORD":"NONREGULAR_CONTROL_ROOT";
    if(st->st_uid!=geteuid())return record?"FOREIGN_UID_RECORD":"FOREIGN_UID_CONTROL_ROOT";
    if(st->st_nlink!=1)return record?"HARDLINK_RECORD":"HARDLINK_CONTROL_ROOT";
    if((st->st_mode&07777)!=0600)return record?"RECORD_MODE_NOT_0600":"CONTROL_ROOT_MODE_NOT_0600";
    if(st->st_size<0||(uint64_t)st->st_size<(uint64_t)min_bytes||
       (uint64_t)st->st_size>(uint64_t)max_bytes)
        return record?"ORIGINAL_RECORD_FILE_SIZE_INVALID":"CONTROL_ROOT_FILE_SIZE_INVALID";
    return NULL;
}
static int load_fixed(fe_t3b1ba2_owner *s,unsigned directory,const char *name,
    uint32_t role,uint8_t *bytes,size_t n,int synchronize) {
    struct stat before,opened,after,path_after;
    const char *problem=NULL;
    if(io_statat(s,s->dirfd[directory],name,&before,role,0u)!=0)return io_failure(s);
    problem=file_metadata(&before,role,n,n);
    if(problem)return fail(s,problem);
    int fd=io_open(s,s->dirfd[directory],name,O_RDONLY|O_NOFOLLOW|O_CLOEXEC,0,role,0u);
    if(fd<0)return io_failure(s);
    int bad=0;
    if(io_stat(s,fd,&opened,role,0u)!=0)bad=1;
    else if((problem=file_metadata(&opened,role,n,n))!=NULL)bad=1;
    else if(!same_stat(&before,&opened)){problem="OBSERVABLE_FILE_REPLACEMENT";bad=1;}
    if(!bad&&synchronize&&io_sync(s,fd,role,0u)!=0)bad=1;
    if(!bad&&read_all(s,fd,bytes,n,role,0u)!=0)bad=1;
    if(!bad&&io_stat(s,fd,&after,role,0u)!=0)bad=1;
    if(!bad&&(!same_stat(&opened,&after)||
       io_statat(s,s->dirfd[directory],name,&path_after,role,0u)!=0))bad=1;
    if(!bad&&!same_stat(&opened,&path_after)){problem="OBSERVABLE_FILE_REPLACEMENT";bad=1;}
    if(io_close(s,fd,role,0u)!=0)bad=1;
    if(bad)return problem?fail(s,problem):io_failure(s);
    return 0;
}
static int roots(fe_t3b1ba2_owner *s,int synchronize) {
    a2_work *w=a2w(s);
    uint8_t raw[32];
    char expected[FE_T3B1BA2_NAME_CAP];
    if(directories(s,&s->anchor,NULL)!=0)return -1;
    if(root_namespace(s,2u,0,w->checkpoint_name)!=0)return -1;
    if(load_fixed(s,2u,w->checkpoint_name,FE_T3B1BA2_ROLE_CHECKPOINT,
        w->wire,sizeof(w->wire),synchronize)!=0)return -1;
    if(sha(w->wire,sizeof(w->wire),raw)!=0)return fail(s,"FPR1_SHA_FAILED");
    if(memcmp(raw,s->anchor.checkpoint_raw_sha256,32u)!=0) {
        if(memcmp(w->wire+120u,s->anchor.checkpoint_raw_sha256,32u)==0)
            return fail(s,"SELF_DIGEST_SUBSTITUTED_FOR_EXTERNAL_RAW_FILE_DIGEST");
        return fail(s,"EXTERNAL_CHECKPOINT_RAW_DIGEST_MISMATCH");
    }
    const char *problem=fe_t3b1ba2_validate_checkpoint(w->wire,sizeof(w->wire),&w->decoded);
    if(problem)return fail(s,problem);
    if(w->decoded.source.capture_source_id!=s->anchor.capture_source_id||
       w->decoded.source.source_generation!=s->anchor.source_generation)
        return fail(s,"FPR1_EXTERNAL_OWNER_IDENTITY_MISMATCH");
    if(fe_t3b1ba2_name(w->wire,expected)!=0||strcmp(expected,w->checkpoint_name)!=0)
        return fail(s,"FPR1_CANONICAL_NAME_MISMATCH");
    if(synchronize&&io_sync(s,s->dirfd[2],FE_T3B1BA2_ROLE_CONTROL_DIR,0u)!=0)
        return io_failure(s);
    if(root_namespace(s,1u,0,w->root_name)!=0)return -1;
    if(load_fixed(s,1u,w->root_name,FE_T3B1BA2_ROLE_A1_FILE,
        w->root,sizeof(w->root),synchronize)!=0)return -1;
    if(memcmp(w->root,w->wire+192u,sizeof(w->root))!=0)
        return fail(s,"FRM2_ORIGINAL_BYTES_CHANGED");
    if(fe_t3b1ba1_name(w->root,expected)!=0||strcmp(expected,w->root_name)!=0)
        return fail(s,"FRM2_CANONICAL_NAME_MISMATCH");
    if(synchronize&&io_sync(s,s->dirfd[1],FE_T3B1BA2_ROLE_A1_DIR,0u)!=0)
        return io_failure(s);
    return 0;
}
static int parse_sequence(const char *name,uint32_t *sequence) {
    uint64_t seq=0u;
    static const char hex[]="0123456789abcdef";
    if(strlen(name)!=180u||strncmp(name,"fa0-",4u)!=0||
       name[12]!='-'||name[29]!='-'||name[46]!='-'||name[111]!='-'||
       strcmp(name+176u,".bin")!=0)return -1;
    for(size_t i=30u;i<46u;++i) {
        const char *h=strchr(hex,name[i]);
        if(!h)return -1;
        seq=(seq<<4u)|(uint64_t)(h-hex);
    }
    if(seq<1u||seq>32u)return -1;
    *sequence=(uint32_t)seq;return 0;
}
static int load_record(fe_t3b1ba2_owner *s,uint32_t sequence,const uint8_t prior[32],
    int anchored) {
    a2_work *w=a2w(s);
    uint8_t *row=w->rows[sequence-1u],whole[32];
    const char *name=w->names[sequence],*problem=NULL;
    struct stat before,opened,after,path_after;
    uint32_t role=FE_T3B1BA2_ROLE_RECORD;
    if(io_statat(s,s->dirfd[0],name,&before,role,sequence)!=0)return io_failure(s);
    problem=file_metadata(&before,role,A2_ROW+1u,A2_ROW+A2_APX);
    if(problem)return fail(s,problem);
    int fd=io_open(s,s->dirfd[0],name,O_RDONLY|O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK,0,role,sequence);
    if(fd<0)return io_failure(s);
    int bad=0;
    size_t bytes=0u;
    if(io_stat(s,fd,&opened,role,sequence)!=0)bad=1;
    else if((problem=file_metadata(&opened,role,A2_ROW+1u,A2_ROW+A2_APX))!=NULL)bad=1;
    else if(!same_stat(&before,&opened)){problem="OBSERVABLE_FILE_REPLACEMENT";bad=1;}
    if(!bad&&read_all(s,fd,row,A2_ROW,role,sequence)!=0)bad=1;
    if(!bad) {
        bytes=(size_t)g32(row+68u);
        if(!bytes||bytes>A2_APX||opened.st_size!=(off_t)(A2_ROW+bytes)) {
            problem="ORIGINAL_RECORD_FILE_SIZE_INVALID";bad=1;
        }
    }
    if(!bad&&read_all(s,fd,w->apx,bytes,role,sequence)!=0)bad=1;
    if(!bad&&io_stat(s,fd,&after,role,sequence)!=0)bad=1;
    if(!bad&&!same_stat(&opened,&after)){problem="OBSERVABLE_FILE_REPLACEMENT";bad=1;}
    if(!bad&&io_statat(s,s->dirfd[0],name,&path_after,role,sequence)!=0)bad=1;
    if(!bad&&!same_stat(&opened,&path_after)){problem="OBSERVABLE_FILE_REPLACEMENT";bad=1;}
    if(io_close(s,fd,role,sequence)!=0)bad=1;
    if(bad)return problem?fail(s,problem):io_failure(s);
    problem=fe_t3b1ba2_validate_record(&w->decoded.source,w->decoded.slots,
        row,w->apx,bytes,sequence,prior);
    if(problem)return fail(s,problem);
    if(sha(row,A2_ROW,whole)!=0)return fail(s,"ORIGINAL_RECORD_SHA_FAILED");
    if(anchored) {
        if(sequence<=16u) {
            if(memcmp(row,w->wire+FE_T3B1BA2_RETIRED_OFFSET+(sequence-1u)*A2_ROW,A2_ROW)!=0)
                return fail(s,"REMAINING_RETIRED_ROW_NOT_ORIGINAL");
        } else {
            const uint8_t *member=w->wire+192u+224u+(sequence-17u)*72u;
            if(memcmp(whole,member+8u,32u)!=0)
                return fail(s,"RETAINED_ORIGINAL_WHOLE_ROW_DIGEST_MISMATCH");
            if(memcmp(row+104u,member+40u,32u)!=0)
                return fail(s,"RETAINED_ORIGINAL_APX3_DIGEST_MISMATCH");
        }
    }
    char canonical[FE_T3B1BA0_NAME_CAP];
    if(fe_t3b1ba0_name(w->decoded.source.capture_source_id,
        w->decoded.source.source_generation,sequence,whole,row+104u,canonical)!=0||
        strcmp(name,canonical)!=0)return fail(s,"ORIGINAL_RECORD_CANONICAL_NAME_MISMATCH");
    w->records[sequence]=opened;
    return 0;
}
static int inventory(fe_t3b1ba2_owner *s,int anchored,fe_t3b1ba2_receipt *receipt) {
    a2_work *w=a2w(s);
    uint8_t prior[32]={0};
    uint64_t retained=0u,retired=0u;
    memset(w->seen,0,sizeof(w->seen));
    if(directories(s,s->anchor_bound?&s->anchor:NULL,NULL)!=0)return -1;
    DIR *d=open_directory(s,0u,FE_T3B1BA2_ROLE_DATA_ENUM);
    if(!d)return -1;
    const char *problem=NULL;
    for(;;) {
        struct dirent *de=io_readdir(s,d,FE_T3B1BA2_ROLE_DATA_ENUM);
        if(!de){if(errno)problem="IO";break;}
        if(strcmp(de->d_name,".")==0||strcmp(de->d_name,"..")==0)continue;
        uint32_t sequence=0u;
        if(parse_sequence(de->d_name,&sequence)!=0||w->seen[sequence]) {
            problem="UNEXPECTED_DATA_ENTRY";break;
        }
        w->seen[sequence]=1u;
        strcpy(w->names[sequence],de->d_name);
    }
    if(io_closedir(s,d,FE_T3B1BA2_ROLE_DATA_ENUM)!=0)problem="IO";
    if(problem)return strcmp(problem,"IO")==0?io_failure(s):fail(s,problem);
    for(uint32_t sequence=17u;sequence<=32u;++sequence)
        if(!w->seen[sequence])return fail(s,"RETAINED_SEQUENCE_MISSING");
    uint32_t k=0u;
    while(k<16u&&!w->seen[k+1u])++k;
    for(uint32_t sequence=k+1u;sequence<=16u;++sequence)
        if(!w->seen[sequence])return fail(s,"NONPREFIX_MISSING_RETIRED_SEQUENCE");
    if(!anchored&&k)return fail(s,"ORIGINAL_A0_FULL_ADMISSION_FAILED");
    for(uint32_t sequence=1u;sequence<=32u;++sequence) {
        uint8_t *row=w->rows[sequence-1u];
        if(sequence<=k)memcpy(row,w->wire+FE_T3B1BA2_RETIRED_OFFSET+(sequence-1u)*A2_ROW,A2_ROW);
        else if(load_record(s,sequence,prior,anchored)!=0)return -1;
        if(sha(row,A2_ROW,prior)!=0)return fail(s,"ORIGINAL_RECORD_SHA_FAILED");
        uint64_t bytes=(uint64_t)A2_ROW+g32(row+68u);
        uint64_t *sum=sequence<=16u?&retired:&retained;
        if(*sum>UINT64_MAX-bytes)
            return fail(s,"FPR1_BYTE_TOTAL_OVERFLOW_OR_INCONSISTENT_SUM");
        *sum+=bytes;
    }
    if(anchored&&(retired!=w->decoded.retired_logical_bytes||
       retained!=w->decoded.retained_logical_bytes||
       retired>UINT64_MAX-retained||retired+retained!=w->decoded.original_logical_bytes))
        return fail(s,"FPR1_BYTE_TOTAL_OVERFLOW_OR_INCONSISTENT_SUM");
    if(!anchored) {
        w->decoded.original_logical_bytes=retired+retained;
        w->decoded.retained_logical_bytes=retained;
        w->decoded.retired_logical_bytes=retired;
    }
    if(receipt) {
        receipt->missing_prefix_known=1u;receipt->missing_prefix=k;
        receipt->retained_files_verified=16u;
        receipt->remaining_retired_files_verified=16u-k;
        receipt->original_logical_bytes=retired+retained;
        receipt->retained_logical_bytes=retained;
        for(unsigned i=0u;i<16u;++i) {
            receipt->retained_capture_fnv[i]=g64(w->rows[16u+i]+72u);
            receipt->retained_render_fnv[i]=g64(w->rows[16u+i]+80u);
        }
        if(sha(w->rows[16u],16u*A2_ROW,receipt->retained_rows_sha256)!=0)
            return fail(s,"ORIGINAL_RECORD_SHA_FAILED");
    }
    return 0;
}

int fe_t3b1ba2_init(fe_t3b1ba2_owner *s,int data_fd,int a1_fd,int control_fd,
    fe_t3b1ba2_workspace *workspace,const fe_t3b1ba2_hooks *hooks) {
    if(!s||!workspace||data_fd<0||a1_fd<0||control_fd<0)return -1;
    memset(s,0,sizeof(*s));memset(workspace,0,sizeof(*workspace));
    s->dirfd[0]=data_fd;s->dirfd[1]=a1_fd;s->dirfd[2]=control_fd;
    s->workspace=workspace;if(hooks)s->hooks=*hooks;
    s->initialized=1u;s->last_error="OK";return 0;
}
static int same_source(const fe_t3b1ba0_owner *a,const fe_t3b1ba0_owner *b) {
    return a->binding_complete==1u&&b->binding_complete==1u&&
        a->dirfd==b->dirfd&&a->device==b->device&&a->inode==b->inode&&
        a->cap==32u&&b->cap==32u&&a->committed==32u&&b->committed==32u&&
        a->source.depth==b->source.depth&&
        a->source.input_hz==b->source.input_hz&&
        a->source.physical_mics==b->source.physical_mics&&
        a->source.render_enabled==b->source.render_enabled&&
        a->source.capture_source_id==b->source.capture_source_id&&
        a->source.render_source_id==b->source.render_source_id&&
        a->source.source_generation==b->source.source_generation&&
        memcmp(a->slots,b->slots,sizeof(a->slots))==0&&
        memcmp(a->last_row,b->last_row,A2_ROW)==0;
}
int fe_t3b1ba2_prepare(fe_t3b1ba2_owner *s,const fe_t3b1ba0_owner *a0,
    const fe_t3b1ba1_owner *a1,const fe_t3b1ba2_request *request,
    fe_t3b1ba2_anchor *pending) {
    fe_t3b1ba0_owner replayed;
    fe_t3b1ba1_owner original;
    fe_t3b1ba1_receipt old_receipt;
    fe_t3b1ba2_anchor candidate;
    const char *problem;
    if(!s||!s->initialized||!s->workspace)return fail(s,"UNINITIALIZED_A2_OWNER");
    s->last_error="OK";s->phase=FE_T3B1BA2_PREPARE;
    if(!request||request->quiescent!=1u)return fail(s,"QUIESCENCE_DECLARATION_REQUIRED");
    if(request->source_head!=32u||request->source_tail!=32u||
       !a0||a0->binding_complete!=1u||a0->cap!=32u||a0->committed!=32u)
        return fail(s,"ORIGINAL_SOURCE_NOT_STOPPED_AND_DRAINED_AT32");
    if(s->prepared||s->anchor_bound||!pending||request->requested_sequence!=32u||
       request->requested_first!=17u||request->requested_last!=32u||
       request->requested_high_water!=32u||request->requested_retired_count!=16u||
       request->requested_retained_count!=16u||request->second_retirement||
       request->requested_generation!=a0->source.source_generation)
        return fail(s,"OUTSIDE_FIXED_FINITE_STAGE");
    memset(&candidate,0,sizeof(candidate));
    if(directories(s,NULL,&candidate)!=0)return -1;
    if(a0->dirfd!=s->dirfd[0]||a0->device!=(dev_t)candidate.device[0]||
       a0->inode!=(ino_t)candidate.inode[0]||
       fe_t3b1ba0_bind(&replayed,a0->dirfd,&a0->source,a0->slots,32u)!=0||
       !same_source(a0,&replayed))return fail(s,"ORIGINAL_A0_FULL_ADMISSION_FAILED");
    if(!a1||a1->binding_complete!=1u||a1->dirfd!=s->dirfd[1]||
       a1->device!=(dev_t)candidate.device[1]||a1->inode!=(ino_t)candidate.inode[1]||
       !same_source(a0,&a1->source))return fail(s,"ORIGINAL_A1_FULL_ADMISSION_FAILED");
    a2_work *w=a2w(s);
    if(root_namespace(s,2u,1,w->checkpoint_name)!=0)return -1;
    original=*a1;
    if(fe_t3b1ba1_publish(&original,&old_receipt)!=0||
       old_receipt.hosted_checkpoint_committed!=1u||
       fe_t3b1ba1_read(&original,&old_receipt)!=0||
       fe_t3b1ba1_encode(&original,w->root)!=0||
       fe_t3b1ba1_verify_bytes(&original,w->root,sizeof(w->root))!=0)
        return fail(s,"ORIGINAL_A1_FULL_ADMISSION_FAILED");
    w->decoded.source=a0->source;memcpy(w->decoded.slots,a0->slots,sizeof(a0->slots));
    if(inventory(s,0,NULL)!=0)return -1;
    /* A second unchanged original admission brackets the metadata copy.
     * Neither old owner is retained in this A2 owner after this call.
     */
    if(fe_t3b1ba0_bind(&replayed,a0->dirfd,&a0->source,a0->slots,32u)!=0||
       !same_source(a0,&replayed)||
       fe_t3b1ba1_verify_bytes(&original,w->root,sizeof(w->root))!=0)
        return fail(s,"ORIGINAL_A0_FULL_ADMISSION_FAILED");
    memset(w->wire,0,sizeof(w->wire));
    p32(w->wire,FE_T3B1BA2_MAGIC);p32(w->wire+4u,1u);
    p32(w->wire+8u,192u);p32(w->wire+12u,4768u);p32(w->wire+16u,1376u);
    p32(w->wire+20u,16u);p32(w->wire+24u,16u);p32(w->wire+28u,32u);
    p32(w->wire+32u,a0->source.capture_source_id);p32(w->wire+36u,a0->source.input_hz);
    p64(w->wire+40u,a0->source.source_generation);p64(w->wire+48u,1u);
    p64(w->wire+56u,16u);p64(w->wire+64u,17u);p64(w->wire+72u,32u);
    p64(w->wire+80u,32u);
    if(sha(w->root,sizeof(w->root),w->wire+88u)!=0)return fail(s,"FPR1_SHA_FAILED");
    p64(w->wire+152u,w->decoded.original_logical_bytes);
    p64(w->wire+160u,w->decoded.retained_logical_bytes);
    p64(w->wire+168u,w->decoded.retired_logical_bytes);
    memcpy(w->wire+192u,w->root,sizeof(w->root));
    memcpy(w->wire+FE_T3B1BA2_RETIRED_OFFSET,w->rows,16u*A2_ROW);
    if(sha(w->wire,sizeof(w->wire),w->wire+120u)!=0)return fail(s,"FPR1_SHA_FAILED");
    problem=fe_t3b1ba2_validate_checkpoint(w->wire,sizeof(w->wire),&w->decoded);
    if(problem)return fail(s,problem);
    candidate.capture_source_id=a0->source.capture_source_id;
    candidate.source_generation=a0->source.source_generation;
    memcpy(candidate.checkpoint_raw_sha256,w->decoded.checkpoint_raw_sha256,32u);
    if(directories(s,&candidate,NULL)!=0)return -1;
    s->anchor=candidate;s->prepared=1u;*pending=candidate;return 0;
}
int fe_t3b1ba2_acknowledge(fe_t3b1ba2_owner *s,const fe_t3b1ba2_anchor *a) {
    if(!s||!s->initialized||!s->prepared)return fail(s,"ORIGINAL_A0_FULL_ADMISSION_REQUIRED");
    s->last_error="OK";s->phase=FE_T3B1BA2_PREPARE;
    if(!a)return fail(s,"MISSING_EXTERNAL_ANCHOR");
    if(!nz(a->checkpoint_raw_sha256,32u))return fail(s,"ZERO_EXTERNAL_FILE_DIGEST");
    if(!anchor_equal(&s->anchor,a))return fail(s,"BOUND_OWNER_EXPECTED_ANCHOR_CHANGED");
    if(s->anchor_bound)return fail(s,"PARENT_ANCHOR_ALREADY_ACKNOWLEDGED");
    if(directories(s,a,NULL)!=0)return -1;
    s->anchor_bound=1u;barrier(s,1u);return 0;
}
int fe_t3b1ba2_bind(fe_t3b1ba2_owner *s,const fe_t3b1ba2_anchor *a) {
    if(!s||!s->initialized||!s->workspace)return fail(s,"UNINITIALIZED_A2_OWNER");
    s->last_error="OK";s->phase=FE_T3B1BA2_READ;
    if(!a)return fail(s,"RECOVERY_EXTERNAL_ANCHOR_REQUIRED");
    if(!nz(a->checkpoint_raw_sha256,32u))return fail(s,"ZERO_EXTERNAL_FILE_DIGEST");
    if(s->anchor_bound) {
        if(!anchor_equal(&s->anchor,a))return fail(s,"BOUND_OWNER_EXPECTED_ANCHOR_CHANGED");
        return directories(s,a,NULL);
    }
    if(s->prepared)return fail(s,"PARENT_ANCHOR_ACKNOWLEDGEMENT_REQUIRED");
    if(!a->capture_source_id||!a->source_generation||a->source_generation==UINT64_MAX)
        return fail(s,"EXTERNAL_ANCHOR_OWNER_INVALID");
    if(directories(s,a,NULL)!=0)return -1;
    s->anchor=*a;s->anchor_bound=1u;return 0;
}
static void receipt_start(fe_t3b1ba2_receipt *r) {
    if(r)memset(r,0,sizeof(*r));
}
static void receipt_roots(fe_t3b1ba2_owner *s,fe_t3b1ba2_receipt *r) {
    if(!r)return;
    r->checkpoint_visible_verified=1u;
    memcpy(r->checkpoint_raw_sha256,a2w(s)->decoded.checkpoint_raw_sha256,32u);
    memcpy(r->original_frm2_raw_sha256,a2w(s)->decoded.original_frm2_raw_sha256,32u);
}
static int receipt_end(fe_t3b1ba2_owner *s,fe_t3b1ba2_receipt *r,
    uint64_t prior_unlinks,int result) {
    if(r&&s) {
        r->io=s->io;
        r->new_data_unlinks=(uint32_t)(s->io.successful_data_unlinks-prior_unlinks);
        if(result!=0) {
            r->hosted_checkpoint_committed=0u;r->hosted_retirement_committed=0u;
        }
    }
    return result;
}
int fe_t3b1ba2_publish(fe_t3b1ba2_owner *s,const fe_t3b1ba2_anchor *a,
    fe_t3b1ba2_receipt *r) {
    receipt_start(r);
    if(!s||!s->initialized||!s->workspace)return fail(s,"UNINITIALIZED_A2_OWNER");
    uint64_t prior_unlinks=s->io.successful_data_unlinks;
    s->last_error="OK";s->phase=FE_T3B1BA2_PUBLISH;
    int result=-1;
    if(!r){(void)fail(s,"RECEIPT_REQUIRED");goto done;}
    if(!s->prepared){(void)fail(s,"ORIGINAL_A0_FULL_ADMISSION_REQUIRED");goto done;}
    if(expected_anchor(s,a)!=0)goto done;
    a2_work *w=a2w(s);
    uint8_t raw[32];
    if(sha(w->wire,sizeof(w->wire),raw)!=0||memcmp(raw,a->checkpoint_raw_sha256,32u)!=0) {
        (void)fail(s,"EXTERNAL_CHECKPOINT_RAW_DIGEST_MISMATCH");goto done;
    }
    if(root_namespace(s,2u,1,w->checkpoint_name)!=0)goto done;
    if(fe_t3b1ba2_name(w->wire,w->checkpoint_name)!=0) {
        (void)fail(s,"FPR1_CANONICAL_NAME_MISMATCH");goto done;
    }
    int fd=io_open(s,s->dirfd[2],A2_TEMP,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,
        0600,FE_T3B1BA2_ROLE_TEMP,0u);
    if(fd<0){(void)io_failure(s);goto done;}
    barrier(s,2u);
    if(write_all(s,fd,w->wire,sizeof(w->wire))!=0) {
        (void)io_close(s,fd,FE_T3B1BA2_ROLE_TEMP,0u);(void)io_failure(s);goto done;
    }
    barrier(s,3u);
    if(io_sync(s,fd,FE_T3B1BA2_ROLE_TEMP,0u)!=0) {
        (void)io_close(s,fd,FE_T3B1BA2_ROLE_TEMP,0u);(void)io_failure(s);goto done;
    }
    barrier(s,4u);
    if(io_close(s,fd,FE_T3B1BA2_ROLE_TEMP,0u)!=0){(void)io_failure(s);goto done;}
    if(io_link(s,w->checkpoint_name)!=0){(void)io_failure(s);goto done;}
    barrier(s,5u);
    if(io_unlink(s,s->dirfd[2],A2_TEMP,FE_T3B1BA2_ROLE_TEMP,0u)!=0) {
        (void)io_failure(s);goto done;
    }
    barrier(s,6u);
    if(io_sync(s,s->dirfd[2],FE_T3B1BA2_ROLE_CONTROL_DIR,0u)!=0) {
        (void)io_failure(s);goto done;
    }
    barrier(s,7u);
    if(roots(s,0)!=0||roots(s,1)!=0||roots(s,0)!=0||inventory(s,1,r)!=0)goto done;
    receipt_roots(s,r);r->hosted_checkpoint_committed=1u;
    barrier(s,8u);result=0;
done:
    return receipt_end(s,r,prior_unlinks,result);
}
int fe_t3b1ba2_read(fe_t3b1ba2_owner *s,const fe_t3b1ba2_anchor *a,
    fe_t3b1ba2_receipt *r) {
    receipt_start(r);
    if(!s||!s->initialized||!s->workspace)return fail(s,"UNINITIALIZED_A2_OWNER");
    uint64_t prior_unlinks=s->io.successful_data_unlinks;
    s->last_error="OK";s->phase=FE_T3B1BA2_READ;
    int result=-1;
    if(!r){(void)fail(s,"RECEIPT_REQUIRED");goto done;}
    if(expected_anchor(s,a)!=0||roots(s,0)!=0||inventory(s,1,r)!=0)goto done;
    receipt_roots(s,r);result=0;
done:
    return receipt_end(s,r,prior_unlinks,result);
}
int fe_t3b1ba2_resume(fe_t3b1ba2_owner *s,const fe_t3b1ba2_anchor *a,
    fe_t3b1ba2_receipt *r) {
    receipt_start(r);
    if(!s||!s->initialized||!s->workspace)return fail(s,"UNINITIALIZED_A2_OWNER");
    uint64_t prior_unlinks=s->io.successful_data_unlinks;
    s->last_error="OK";s->phase=FE_T3B1BA2_RESUME;
    int result=-1;
    if(!r){(void)fail(s,"RECEIPT_REQUIRED");goto done;}
    if(expected_anchor(s,a)!=0||roots(s,0)!=0||roots(s,1)!=0)goto done;
    /* These are current hosted barriers, even at an already complete k16.
     * A read in a preceding process/owner cannot supply these observations.
     */
    if(io_sync(s,s->dirfd[0],FE_T3B1BA2_ROLE_DATA_DIR,0u)!=0) {
        (void)io_failure(s);goto done;
    }
    if(roots(s,0)!=0)goto done;
    barrier(s,9u);
    if(inventory(s,1,r)!=0)goto done;
    receipt_roots(s,r);
    a2_work *w=a2w(s);
    for(uint32_t sequence=r->missing_prefix+1u;sequence<=16u;++sequence) {
        struct stat current;
        if(directories(s,&s->anchor,NULL)!=0)goto done;
        if(io_statat(s,s->dirfd[0],w->names[sequence],&current,
            FE_T3B1BA2_ROLE_RECORD,sequence)!=0){(void)io_failure(s);goto done;}
        if(!same_stat(&current,&w->records[sequence])) {
            (void)fail(s,"OBSERVABLE_FILE_REPLACEMENT");goto done;
        }
        barrier(s,10u+3u*(sequence-1u));
        if(io_unlink(s,s->dirfd[0],w->names[sequence],
            FE_T3B1BA2_ROLE_RECORD,sequence)!=0){(void)io_failure(s);goto done;}
        /* Own successful unlink establishes this new prefix.  This fact
         * survives a following fsync error, but grants no commit receipt.
         */
        r->missing_prefix_known=1u;r->missing_prefix=sequence;
        r->remaining_retired_files_verified=16u-sequence;
        barrier(s,11u+3u*(sequence-1u));
        if(io_sync(s,s->dirfd[0],FE_T3B1BA2_ROLE_DATA_DIR,sequence)!=0) {
            (void)fail(s,"PARTIAL_RETIREMENT_NOT_COMMITTED");goto done;
        }
        barrier(s,12u+3u*(sequence-1u));
        if(roots(s,0)!=0||inventory(s,1,r)!=0)goto done;
        if(r->missing_prefix!=sequence) {
            (void)fail(s,"OBSERVABLE_RETIREMENT_PREFIX_CHANGED");goto done;
        }
    }
    r->hosted_checkpoint_committed=1u;r->hosted_retirement_committed=1u;
    result=0;
done:
    return receipt_end(s,r,prior_unlinks,result);
}
