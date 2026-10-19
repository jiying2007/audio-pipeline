#ifndef FE09_B2S3_T3S2B1BA0_FINITE_OUTBOARD_H
#define FE09_B2S3_T3S2B1BA0_FINITE_OUTBOARD_H

/* #803: original first-party FE09 S1 callback, independent HOSTED POSIX
 * finite outboard identity (1..17 through 1..32, NO rolling or overwrite).
 * No changes to the original S2/APX3 codec, FBS1, frozen 16-file S2A, B0,
 * B1a, source/BF threads, public SDK or production code. A successful
 * hosted fsync is NOT physical NAND/UBIFS sudden-power-loss evidence.
 */
#include "fe09_b2s3_t3s1_compact_handoff.h"
#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>

#define FE_T3B1BA0_MIN_RECORDS 17u
#define FE_T3B1BA0_MAX_RECORDS 32u
#define FE_T3B1BA0_NAME_CAP 192u

typedef enum {
    FE_T3B1BA0_FAULT_NONE=0,
    FE_T3B1BA0_FAULT_CREATE=1,
    FE_T3B1BA0_FAULT_ROW_WRITE=2,
    FE_T3B1BA0_FAULT_APX3_WRITE=3,
    FE_T3B1BA0_FAULT_FILE_SYNC=4,
    FE_T3B1BA0_FAULT_PUBLISH=5,
    FE_T3B1BA0_FAULT_UNLINK_TEMP=6,
    FE_T3B1BA0_FAULT_DIR_SYNC=7,
    FE_T3B1BA0_FAULT_READBACK=8
} fe_t3b1ba0_fault;

typedef struct {
    int dirfd;                /* exact exclusive caller-owned dirfd */
    dev_t device;
    ino_t inode;
    fe_b1s0_config source;   /* exact immutable original owner identity */
    uint32_t slots[4];       /* physical microphone -> original PCM slot */
    uint32_t cap;            /* caller bounded to 17..32, never modulo */
    uint64_t committed;      /* original global Capture seq, not APX3 local */
    uint8_t last_row[FE_T3S1_ROW_BYTES]; /* entire original 200B FBS1 */
    uint32_t binding_complete;
    uint32_t restart_recovered;
    fe_t3b1ba0_fault test_fault; /* host fault injection, not physical */
} fe_t3b1ba0_owner;

/* New isolated sink MUST bind before S1 starts. Reopen enumerates every
 * immutable file, requires exact contiguous 1..N global sequences and
 * full previous-row SHA chain. No ACK is manufactured from recovered files.
 * Never points to the original S2-A source directory.
 */
int fe_t3b1ba0_bind(fe_t3b1ba0_owner *owner,int exclusive_dirfd,
    const fe_b1s0_config *original_source,const uint32_t slots[4],
    uint32_t cap);

/* Strict fe_t3s1_outboard_sink callback on the separate consumer ONLY.
 * 0 + exact original row+APX3 byte accounting happens only after O_EXCL,
 * full bounded write, file fsync, no-clobber link, directory fsync,
 * independent readback, original S2 decode/replay/CRC/FNV and full FBS1
 * SHA/owner/prev-row chain. A full or ambiguous store withholds S1 ACK.
 * Never unlinks published original source files.
 */
int fe_t3b1ba0_outboard_sink(const uint8_t *original_apx3,size_t apx3_bytes,
    const uint8_t *original_fbs1,size_t row_bytes,
    void *bound_context,size_t *actual_ack);

/* Canonical immutable name includes original capture ID, source generation,
 * UINT64 global Capture sequence, full original FBS1 SHA and APX3 SHA.
 * Does not reuse file slots or infer global sequence from APX3-local 1.
 */
int fe_t3b1ba0_name(uint32_t source_id,uint64_t generation,uint64_t sequence,
    const uint8_t full_row_sha256[32],const uint8_t apx3_sha256[32],
    char name[FE_T3B1BA0_NAME_CAP]);

/* Only fault injection for this noninstalled hosted research stage. */
int fe_t3b1ba0_set_test_fault(fe_t3b1ba0_owner *owner,
    fe_t3b1ba0_fault fault);

#endif
