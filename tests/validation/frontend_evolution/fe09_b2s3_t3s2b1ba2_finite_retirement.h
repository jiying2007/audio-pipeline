#ifndef FE09_B2S3_T3S2B1BA2_FINITE_RETIREMENT_H
#define FE09_B2S3_T3S2B1BA2_FINITE_RETIREMENT_H

/* #825, noninstalled HOSTED finite 32 -> 16 retirement.  This owner has
 * neither an S1 pointer nor a source ACK callback.  Directory descriptors
 * are borrowed, never inherited from a previous recovery process.  The
 * caller holds the three directories exclusively and stops the producer.
 */
#include "fe09_b2s3_t3s2b1ba1_anchor_root.h"

#define FE_T3B1BA2_MAGIC UINT32_C(0x31525046)
#define FE_T3B1BA2_VERSION 1u
#define FE_T3B1BA2_HEADER_BYTES 192u
#define FE_T3B1BA2_CHECKPOINT_BYTES 4768u
#define FE_T3B1BA2_SELF_OFFSET 120u
#define FE_T3B1BA2_RETIRED_OFFSET 1568u
#define FE_T3B1BA2_NAME_CAP 192u
#define FE_T3B1BA2_WORKSPACE_BYTES 32768u
#define FE_T3B1BA2_LOCAL_STACK_RESERVE 12288u
#define FE_T3B1BA2_READONLY_RESERVE 8192u
#define FE_T3B1BA2_RESOURCE_LIMIT 65536u
#define FE_T3B1BA2_BARRIERS 57u

typedef enum {
    FE_T3B1BA2_DATA_DIR=0,
    FE_T3B1BA2_A1_DIR=1,
    FE_T3B1BA2_CONTROL_DIR=2
} fe_t3b1ba2_directory;

typedef struct {
    uint32_t capture_source_id;
    uint64_t source_generation;
    uint64_t device[3],inode[3];
    uint8_t checkpoint_raw_sha256[32];
} fe_t3b1ba2_anchor;

/* Metadata only.  No original PCM, owner or file descriptor is an anchor. */
typedef struct {
    fe_b1s0_config source;
    uint32_t slots[4];
    uint64_t original_logical_bytes,retained_logical_bytes;
    uint64_t retired_logical_bytes;
    uint8_t checkpoint_raw_sha256[32],checkpoint_self_sha256[32];
    uint8_t original_frm2_raw_sha256[32];
} fe_t3b1ba2_checkpoint;

typedef union {
    max_align_t alignment;
    uint8_t bytes[FE_T3B1BA2_WORKSPACE_BYTES];
} fe_t3b1ba2_workspace;

typedef enum {
    FE_T3B1BA2_PREPARE=1,FE_T3B1BA2_PUBLISH=2,
    FE_T3B1BA2_READ=3,FE_T3B1BA2_RESUME=4
} fe_t3b1ba2_phase;
typedef enum {
    FE_T3B1BA2_IO_OPEN=1,FE_T3B1BA2_IO_FSTAT=2,
    FE_T3B1BA2_IO_FSTATAT=3,FE_T3B1BA2_IO_FLAGS=4,
    FE_T3B1BA2_IO_READ=5,FE_T3B1BA2_IO_WRITE=6,
    FE_T3B1BA2_IO_FSYNC=7,FE_T3B1BA2_IO_LINK=8,
    FE_T3B1BA2_IO_UNLINK=9,FE_T3B1BA2_IO_CLOSE=10,
    FE_T3B1BA2_IO_READDIR=11,FE_T3B1BA2_IO_CLOSEDIR=12
} fe_t3b1ba2_io_operation;
typedef enum {
    FE_T3B1BA2_ROLE_DATA_DIR=1,FE_T3B1BA2_ROLE_A1_DIR=2,
    FE_T3B1BA2_ROLE_CONTROL_DIR=3,FE_T3B1BA2_ROLE_RECORD=4,
    FE_T3B1BA2_ROLE_A1_FILE=5,FE_T3B1BA2_ROLE_CHECKPOINT=6,
    FE_T3B1BA2_ROLE_TEMP=7,FE_T3B1BA2_ROLE_DATA_ENUM=8,
    FE_T3B1BA2_ROLE_A1_ENUM=9,FE_T3B1BA2_ROLE_CONTROL_ENUM=10
} fe_t3b1ba2_io_role;

/* Every completed wrapper emits an event.  Ordinary events may be reduced
 * to ordered counters/digest by the fixture; each injected event preserves
 * both actual and reported outcomes.  A synthetic uid/dev follows a real
 * successful fstat.  An injected close error follows exactly one real close.
 */
typedef struct {
    uint32_t phase,operation,role,sequence;
    uint64_t ordinal,matching_ordinal,requested_bytes;
    uint32_t syscall_called,injected,fault_id;
    int64_t actual_result,reported_result;
    int actual_errno,reported_errno;
    uint64_t actual_device,observed_device,actual_uid,observed_uid;
} fe_t3b1ba2_io_event;

typedef struct {
    /* Observational, non-reentrant hooks: they do not mutate this owner or
     * its three namespaces, and do not call an A2 API from a callback.
     * Their own fixture/IPC storage is separately attributed.
     */
    void (*io)(const fe_t3b1ba2_io_event *event,void *context);
    /* P01..P57: callback returns only after the surviving parent authorizes
     * continuation, or never returns because that parent kills this worker.
     */
    void (*barrier)(uint32_t point,void *context);
    void *context;
} fe_t3b1ba2_hooks;

typedef struct {
    uint64_t operations[13];
    uint64_t actual_operations[13];
    uint64_t data_unlinks,successful_data_unlinks;
    uint64_t data_dir_syncs,successful_data_dir_syncs;
    uint64_t injected_events;
} fe_t3b1ba2_io_counts;

typedef struct {
    uint32_t missing_prefix_known,missing_prefix;
    uint32_t retained_files_verified,remaining_retired_files_verified;
    uint32_t checkpoint_visible_verified;
    uint32_t hosted_checkpoint_committed,hosted_retirement_committed;
    uint32_t source_ack_proven; /* always zero */
    uint32_t live_source_observation; /* always zero for A2 itself */
    uint32_t new_data_unlinks;
    uint64_t original_logical_bytes,retained_logical_bytes;
    uint64_t retained_capture_fnv[16],retained_render_fnv[16];
    uint8_t checkpoint_raw_sha256[32],original_frm2_raw_sha256[32];
    uint8_t retained_rows_sha256[32];
    fe_t3b1ba2_io_counts io;
} fe_t3b1ba2_receipt;

typedef struct {
    uint32_t quiescent;
    uint64_t source_head,source_tail;
    uint64_t requested_sequence; /* exactly original high-water 32 */
    uint64_t requested_first,requested_last,requested_high_water;
    uint64_t requested_generation;
    uint32_t requested_retired_count,requested_retained_count;
    uint32_t second_retirement;
} fe_t3b1ba2_request;

typedef struct {
    int dirfd[3];
    fe_t3b1ba2_workspace *workspace;
    fe_t3b1ba2_hooks hooks;
    fe_t3b1ba2_anchor anchor;
    fe_t3b1ba2_io_counts io;
    const char *last_error;
    uint32_t initialized,prepared,anchor_bound,phase;
    uint32_t test_fault,fault_fired;
    uint64_t io_ordinal,fault_matching_ordinal;
} fe_t3b1ba2_owner;

/* Returns 0 on success and -1 on refusal.  last_error is an immutable
 * predicate name, never an assertion about an unobserved historical cause.
 * init takes no ownership of directory fds and does not copy an old owner.
 */
int fe_t3b1ba2_init(fe_t3b1ba2_owner *owner,int data_dirfd,
    int original_a1_dirfd,int control_dirfd,
    fe_t3b1ba2_workspace *workspace,const fe_t3b1ba2_hooks *hooks);
int fe_t3b1ba2_prepare(fe_t3b1ba2_owner *owner,
    const fe_t3b1ba0_owner *original_a0,
    const fe_t3b1ba1_owner *original_a1,
    const fe_t3b1ba2_request *request,fe_t3b1ba2_anchor *pending_anchor);
int fe_t3b1ba2_acknowledge(fe_t3b1ba2_owner *owner,
    const fe_t3b1ba2_anchor *parent_expected_anchor);
int fe_t3b1ba2_publish(fe_t3b1ba2_owner *owner,
    const fe_t3b1ba2_anchor *parent_expected_anchor,
    fe_t3b1ba2_receipt *receipt);
/* Fresh-process binding accepts only a separately supplied parent anchor.
 * It cannot establish the identity of a parent value it was never given.
 */
int fe_t3b1ba2_bind(fe_t3b1ba2_owner *owner,
    const fe_t3b1ba2_anchor *parent_expected_anchor);
int fe_t3b1ba2_read(fe_t3b1ba2_owner *owner,
    const fe_t3b1ba2_anchor *parent_expected_anchor,
    fe_t3b1ba2_receipt *receipt);
int fe_t3b1ba2_resume(fe_t3b1ba2_owner *owner,
    const fe_t3b1ba2_anchor *parent_expected_anchor,
    fe_t3b1ba2_receipt *receipt);
const char *fe_t3b1ba2_error(const fe_t3b1ba2_owner *owner);
const char *fe_t3b1ba2_error_class(const char *error);

/* The production validators are exposed only for isolated registered
 * metadata controls.  Success grants no filesystem/retirement authority.
 * Record validation runs the unchanged original codec and replay callback.
 */
const char *fe_t3b1ba2_validate_checkpoint(const uint8_t *bytes,size_t size,
    fe_t3b1ba2_checkpoint *decoded);
const char *fe_t3b1ba2_validate_record(const fe_b1s0_config *source,
    const uint32_t slots[4],const uint8_t row[FE_T3S1_ROW_BYTES],
    const uint8_t *apx,size_t apx_bytes,uint64_t expected_sequence,
    const uint8_t expected_previous_whole_row_sha256[32]);
int fe_t3b1ba2_name(const uint8_t checkpoint[FE_T3B1BA2_CHECKPOINT_BYTES],
    char name[FE_T3B1BA2_NAME_CAP]);
const uint8_t *fe_t3b1ba2_prepared_bytes(const fe_t3b1ba2_owner *owner);
/* 0 disables.  Only the preregistered seam controls 108,114,121..144
 * are accepted.  Faults affect only this new module's wrappers.
 */
int fe_t3b1ba2_set_test_fault(fe_t3b1ba2_owner *owner,uint32_t negative_id);
size_t fe_t3b1ba2_resource_bytes(void);
size_t fe_t3b1ba2_workspace_used_bytes(void);

#endif
