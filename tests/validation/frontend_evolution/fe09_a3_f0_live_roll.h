#ifndef FE09_A3_F0_LIVE_ROLL_H
#define FE09_A3_F0_LIVE_ROLL_H

/* #847 / FE09-A3-F0-LIVE-SOURCE-ROLL-33-49-R1. NONINSTALLED research.
 * This interface creates no execution admission. The external freeze,
 * protected-B guard and all four target gates remain outside this module.
 * A3 is finite (33..49), hosted, and requires a surviving parent and source.
 */
#include "fe09_b2s3_t3s2b1ba2_finite_retirement.h"

#define FE_A3_F0_MAGIC UINT32_C(0x31523341)
#define FE_A3_F0_ROOT_BYTES 3656u
#define FE_A3_F0_HEADER_BYTES 256u
#define FE_A3_F0_SELF_OFFSET 192u
#define FE_A3_F0_ROW_BYTES 200u
#define FE_A3_F0_RECORD_BYTES 5320u
#define FE_A3_F0_RETAINED 16u
#define FE_A3_F0_NAME_BYTES 192u
#define FE_A3_F0_WORKSPACE_BYTES 32768u
#define FE_A3_F0_CONTROL_RESERVE 8192u
#define FE_A3_F0_STACK_RESERVE 16384u
#define FE_A3_F0_RODATA_RESERVE 8192u
#define FE_A3_F0_RESOURCE_BYTES 65536u
#define FE_A3_F0_CUTPOINTS 16u
#define FE_A3_F0_IO_FAULTS 12u
#define FE_A3_F0_DATA_TEMP "fa3.pending.part"
#define FE_A3_F0_ROOT_TEMP "a3r1.pending.part"
#define FE_A3_F0_NOT_CALLED INT64_MIN

typedef struct {
    fe_b1s0_config source;
    uint32_t slots[4],physical_k;
} fe_a3_f0_profile;

typedef struct {
    fe_a3_f0_profile profile;
    uint64_t first,last,high_water,generation,left_sequence;
    uint8_t raw_sha256[32],self_sha256[32];
    uint8_t previous_raw_sha256[32],genesis_fpr1_raw_sha256[32];
} fe_a3_f0_root;

/* Metadata inventory, not another record/PCM buffer. */
typedef struct {
    char name[FE_A3_F0_NAME_BYTES];
    uint64_t device,inode,bytes,sequence;
    uint32_t links,flags;
    uint8_t reserved[8];
} fe_a3_f0_inventory_entry;

typedef enum {
    FE_A3_F0_GENESIS=1,FE_A3_F0_READONLY=2,
    FE_A3_F0_SLIDE=3,FE_A3_F0_RESUME=4
} fe_a3_f0_phase;
typedef enum {
    FE_A3_F0_IO_OPEN=1,FE_A3_F0_IO_FSTAT=2,
    FE_A3_F0_IO_FSTATAT=3,FE_A3_F0_IO_FLAGS=4,
    FE_A3_F0_IO_READ=5,FE_A3_F0_IO_WRITE=6,
    FE_A3_F0_IO_FSYNC=7,FE_A3_F0_IO_LINK=8,
    FE_A3_F0_IO_UNLINK=9,FE_A3_F0_IO_CLOSE=10,
    FE_A3_F0_IO_GETDENTS=11
} fe_a3_f0_io_operation;
typedef enum {
    FE_A3_F0_ROLE_DATA_DIR=1,FE_A3_F0_ROLE_ROOT_DIR=2,
    FE_A3_F0_ROLE_DATA_FINAL=3,FE_A3_F0_ROLE_DATA_TEMP=4,
    FE_A3_F0_ROLE_ROOT_FINAL=5,FE_A3_F0_ROLE_ROOT_TEMP=6,
    FE_A3_F0_ROLE_RETIRING_DATA=7,FE_A3_F0_ROLE_OLD_ROOT=8,
    FE_A3_F0_ROLE_DATA_ENUM=9,FE_A3_F0_ROLE_ROOT_ENUM=10
} fe_a3_f0_io_role;

/* The absent failing syscall is represented by NOT_CALLED, not a fabricated
 * actual -1. Prefix writes in F02/F06 are separate, real IO events. */
typedef struct {
    uint32_t phase,operation,role,sequence;
    uint64_t ordinal,requested_bytes;
    uint32_t syscall_called,injected,fault_id,seam; /* seam=F01..F12 or 0 */
    int64_t actual_result,reported_result;
    int32_t actual_errno,reported_errno;
    uint64_t actual_device,actual_inode,actual_bytes,actual_links;
} fe_a3_f0_io_event;

/* Exactly the preregistered 32 KiB. The readback record is also the bounded
 * scratch for root self-hash calculation; these uses never overlap. Linux
 * getdents64 reuses the four filename buffers, without fdopendir allocation.
 * No APX3 copy or extra raw-root array is hidden in the unused reserve. */
typedef struct {
    uint8_t roots[2][FE_A3_F0_ROOT_BYTES];
    uint8_t candidate_record[FE_A3_F0_RECORD_BYTES];
    uint8_t readback_record[FE_A3_F0_RECORD_BYTES];
    fe_a3_f0_inventory_entry inventory[18];
    char names[4][FE_A3_F0_NAME_BYTES];
    uint8_t digests[8][32];
    union { fe_a3_f0_root root; uint8_t bytes[512]; } metadata;
    union { fe_a3_f0_io_event event; uint8_t bytes[256]; } event;
    uint8_t unused_reserve[8704];
} fe_a3_f0_work;
typedef union {
    max_align_t alignment;
    uint8_t bytes[FE_A3_F0_WORKSPACE_BYTES];
    fe_a3_f0_work work;
} fe_a3_f0_workspace;

/* Supplied by the surviving parent on every bind. These fields are NOT
 * recovered from filenames, self-consistent disk, mtime, or an fsync guess.
 * The four *_observed flags come ONLY from the parent's ordered actual IO
 * events for this pending nonce. They retain the F10/F11 distinction even
 * when on-disk bytes/names match. Actual and reported IO remain separate.
 */
typedef struct {
    uint32_t supplied,source_pending,pending_root_accepted,current_promoted;
    uint32_t resume_permitted,retiring_data_unlink_observed;
    uint32_t data_retire_sync_observed,old_root_unlink_observed;
    uint32_t root_retire_sync_observed,ack_already_issued;
    uint64_t device[2],inode[2];
    uint64_t worker_incarnation,pending_sequence;
    uint8_t nonce[32],current_raw_sha256[32];
} fe_a3_f0_authority;

typedef struct {
    uint64_t operations[12],actual_operations[12],injected_events;
    uint64_t successful_data_unlinks,successful_old_root_unlinks;
    uint64_t successful_retirement_data_syncs,successful_old_root_syncs;
} fe_a3_f0_io_counts;

typedef struct {
    const char *classification;
    uint64_t current_sequence,pending_sequence,packet_bytes;
    uint32_t data_names,data_unique_inodes,root_names,root_unique_inodes;
    uint32_t retained_files_verified,pending_data_verified;
    uint32_t pending_root_verified,current_root_verified;
    uint32_t parent_pending_root_accepted,parent_current_promoted;
    uint32_t retiring_data_present,old_root_present;
    uint32_t data_temp_present,data_final_present;
    uint32_t root_temp_present,root_final_present;
    uint32_t retiring_data_unlink_observed,data_retire_sync_observed;
    uint32_t old_root_unlink_observed,root_retire_sync_observed;
    uint32_t current_call_data_sync,current_call_root_sync;
    uint32_t data_publication_synced,root_publication_synced;
    uint32_t final_authorized,byte_ack_issued;
    uint32_t source_ack_proven; /* always zero: only original S1 owns tail */
    uint64_t ack_bytes;
    uint8_t current_raw_sha256[32],pending_raw_sha256[32];
    fe_a3_f0_io_counts io;
} fe_a3_f0_receipt;

typedef enum {
    FE_A3_F0_PROPOSE=1,FE_A3_F0_PROMOTE=2,
    FE_A3_F0_RESUME_PROMOTED=3,FE_A3_F0_FINAL_AUTHORIZE=4
} fe_a3_f0_authorization;
typedef struct {
    /* Non-reentrant observational hooks. No callback mutates this owner,
     * workspace, namespaces or packet. Fixture/IPC storage is separate.
     * A root and a 5320-byte packet must be distinct <=8192-byte IPC messages.
     */
    void (*io)(const fe_a3_f0_io_event *event,void *context);
    /* Only the surviving parent performs SIGKILL. This call returns after
     * its continuation; a killed worker cannot create a success receipt. */
    int (*barrier)(uint32_t point,const fe_a3_f0_authority *authority,
        const fe_a3_f0_receipt *receipt,void *context);
    /* 0 means an explicit same-call parent response. For PROPOSE/PROMOTE,
     * parent independently constructs and compares the entire next root.
     * RESUME_PROMOTED is separate from a second PROMOTE. */
    int (*authorize)(uint32_t action,const fe_a3_f0_authority *authority,
        const uint8_t next_root[FE_A3_F0_ROOT_BYTES],
        const fe_a3_f0_receipt *receipt,void *context);
    void *context;
} fe_a3_f0_hooks;

typedef struct {
    int dirfd[2]; /* borrowed, independently opened in a fresh worker */
    fe_a3_f0_workspace *workspace;
    fe_a3_f0_hooks hooks;
    fe_a3_f0_profile profile;
    fe_a3_f0_authority authority;
    fe_a3_f0_io_counts io;
    const char *last_error;
    uint64_t device[2],inode[2],io_ordinal,packet_bytes,last_ack_sequence;
    uint32_t initialized,bound,phase,test_fault,fault_fired,ack_returned;
    uint32_t readonly_checked,current_call_data_sync,current_call_root_sync;
    uint32_t data_publication_synced,root_publication_synced;
    uint32_t mutation_started;
} fe_a3_f0_owner;

/* The adapter includes the locked A0 .c exactly once. Its metadata-only view
 * invokes unchanged internal source_ok/valid_record, original codec/replay
 * and original SHA. Public A0 remains capped at 32, and A2 remains unchanged.
 * No validator grants bound-owner, root, filesystem, retirement or ACK power.
 */
void fe_a3_f0_profile_init(fe_a3_f0_profile *profile,uint32_t physical_k);
const char *fe_a3_f0_validate_profile(const fe_a3_f0_profile *profile);
/* Metadata only: left seq16 is admissible here, never in record replay.
 * A NULL previous digest is allowed only for the root's external left row. */
const char *fe_a3_f0_validate_row_metadata(const fe_a3_f0_profile *profile,
    const uint8_t row[FE_A3_F0_ROW_BYTES],uint64_t expected_sequence,
    const uint8_t expected_previous_whole_row_sha256[32]);
const char *fe_a3_f0_validate_record(const fe_a3_f0_profile *profile,
    const uint8_t row[FE_A3_F0_ROW_BYTES],const uint8_t *apx,size_t apx_bytes,
    uint64_t expected_sequence,
    const uint8_t expected_previous_whole_row_sha256[32]);
const char *fe_a3_f0_validate_root(const uint8_t *bytes,size_t size,
    const fe_a3_f0_profile *expected_profile,
    const uint8_t expected_previous_raw_sha256[32],fe_a3_f0_root *decoded,
    uint8_t scratch[FE_A3_F0_RECORD_BYTES]);
const char *fe_a3_f0_next_root(const uint8_t previous[FE_A3_F0_ROOT_BYTES],
    const uint8_t original_next_row[FE_A3_F0_ROW_BYTES],
    uint8_t next[FE_A3_F0_ROOT_BYTES],
    uint8_t scratch[FE_A3_F0_RECORD_BYTES]);
int fe_a3_f0_root_name(const uint8_t root[FE_A3_F0_ROOT_BYTES],
    char name[FE_A3_F0_NAME_BYTES]);
int fe_a3_f0_record_name(const uint8_t row[FE_A3_F0_ROW_BYTES],
    char name[FE_A3_F0_NAME_BYTES]);

int fe_a3_f0_init(fe_a3_f0_owner *owner,int data_dirfd,int a3_root_dirfd,
    fe_a3_f0_workspace *workspace,const fe_a3_f0_hooks *hooks);
/* Actual original A2 is still bound/prepared after its real resume. This
 * calls its original read/parser and replays the real retained 17..32 files.
 * It publishes only R32; it fabricates no A0 count, source state, or ACK.
 * Result root bytes reside at owner->workspace->work.roots[0]. */
int fe_a3_f0_genesis(fe_a3_f0_owner *owner,
    fe_t3b1ba2_owner *actual_original_a2,
    const fe_t3b1ba2_anchor *external_original_anchor,uint32_t physical_k,
    fe_a3_f0_receipt *receipt);
/* previous is the externally retained prior root even after promotion.
 * parent_pending is required iff pending_root_accepted; otherwise NULL.
 * packet is exact FBS1(200) + APX3, required iff source_pending. A bind does
 * no filesystem mutation. Current/pending roles never come from disk order.
 */
int fe_a3_f0_bind(fe_a3_f0_owner *owner,
    const fe_a3_f0_authority *external_authority,
    const uint8_t previous[FE_A3_F0_ROOT_BYTES],
    const uint8_t parent_pending[FE_A3_F0_ROOT_BYTES],
    const uint8_t *packet,size_t packet_bytes);
int fe_a3_f0_readonly(fe_a3_f0_owner *owner,fe_a3_f0_receipt *receipt);
/* slide is the initial worker. resume requires parent resume_permitted and
 * a successful readonly in this fresh binding. Both use only the one bound
 * original packet. An incomplete temp is preserved and cannot be repaired.
 * Exact byte ACK is emitted at most once, after fresh final authorization;
 * only original S1 drain, outside this owner, advances the source tail. */
int fe_a3_f0_slide(fe_a3_f0_owner *owner,fe_a3_f0_receipt *receipt,
    size_t *actual_ack);
int fe_a3_f0_resume(fe_a3_f0_owner *owner,fe_a3_f0_receipt *receipt,
    size_t *actual_ack);
int fe_a3_f0_set_test_fault(fe_a3_f0_owner *owner,uint32_t fault_id);
const char *fe_a3_f0_error(const fe_a3_f0_owner *owner);
const char *fe_a3_f0_error_class(const char *error);
size_t fe_a3_f0_workspace_used_bytes(void);
size_t fe_a3_f0_resource_bytes(void);

#endif
