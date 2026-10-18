#ifndef FE09_B2S3_T3S2A_ATOMIC_SPOOL_H
#define FE09_B2S3_T3S2A_ATOMIC_SPOOL_H
/* #794 NONINSTALLED POSIX-hosted research: real first-party S2 APX3 raw bytes
 * plus its original 200-byte FBS1 canonical manifest row. One dedicated
 * consumer/owner. No BF-worker I/O, other serializer/CRC, rolling GC,
 * physical NAND/UBIFS durability, complete-device budget or public SDK.
 */
#include "fe09_b2s3_t3s1_compact_handoff.h"
#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>

#define FE_T3S2A_MAX_FILES 16u
#define FE_T3S2A_FILE_BYTES (FE_T3S1_ROW_BYTES + FE_T3S1_CHUNK_BYTES)
#define FE_T3S2A_NAME_CAP 48u
#define FE_T3S2A_VERSION 1u

typedef enum {
    FE_T3S2A_FAULT_NONE=0,
    FE_T3S2A_FAULT_CREATE=1,
    FE_T3S2A_FAULT_ROW_WRITE=2,
    FE_T3S2A_FAULT_APX3_WRITE=3,
    FE_T3S2A_FAULT_FILE_SYNC=4,
    FE_T3S2A_FAULT_PUBLISH=5,
    FE_T3S2A_FAULT_DIRECTORY_SYNC=6,
    FE_T3S2A_FAULT_READBACK=7
} fe_t3s2a_fault;

typedef struct {
    int dirfd;                /* caller-owned exclusive pre-opened directory */
    dev_t device;
    ino_t inode;              /* pinned to detect a reused fd */
    uint64_t generation;
    uint32_t capture_id,render_id,rate_hz,mics,render_enabled;
    uint32_t slots[4];
    uint32_t maximum_files;   /* caller-chosen hard cap 1..16, no GC */
    uint64_t committed;       /* contiguous original Capture sequences */
    uint8_t prior_row_sha256[32];
    uint8_t committed_last_row[FE_T3S1_ROW_BYTES];
    fe_t3s2a_fault failpoint; /* test fault injection; consumer-owned */
    uint32_t restart_recovered;
    uint32_t binding_complete; /* set ONLY after full source/disk inventory passes */
    uint32_t process_crash_faults_rejected;
} fe_t3s2a_spool;

/* Validate directory authority and inventory. Only previously published
 * contiguous exact source-bound originals are admitted on restart. A torn
 * uncommitted temp alone fails closed without falsely advancing Capture.
 */
int fe_t3s2a_bind(fe_t3s2a_spool *state,int exclusive_directory_fd,
                   const fe_b1s0_config *source,
                   const uint32_t physical_slots[4],
                   uint32_t maximum_files);

/* Exact fe_t3s1_outboard_sink type. Must bind at fe_t3s1_init BEFORE
 * source/worker/consumer threads start. This calls POSIX I/O ONLY on the
 * separate outboard consumer thread. Return 0 plus full actual byte ACK
 * ONLY after no-overwrite atomic publication, file+directory fsync and
 * exact fresh readback+original first-party APX3/row verification.
 */
int fe_t3s2a_outboard_sink(const uint8_t *original_apx3,size_t n,
                          const uint8_t *canonical_fbs1,size_t row_bytes,
                          void *pinned_context,size_t *actual_ack);

/* Test-only explicit fault injection on the exclusively owned consumer.
 * Never changes immutable source, row, APX3 or expected sequence.
 */
int fe_t3s2a_set_test_fault(fe_t3s2a_spool *state,fe_t3s2a_fault fault);

/* Deterministic canonical POSIX basename for original global seq.
 * NOT the first-party APX3 local frame sequence (always one).
 */
int fe_t3s2a_record_name(uint64_t sequence,char dest[FE_T3S2A_NAME_CAP]);
#endif
