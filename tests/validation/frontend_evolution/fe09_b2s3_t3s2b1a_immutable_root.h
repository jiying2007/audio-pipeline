#ifndef FE09_B2S3_T3S2B1A_IMMUTABLE_ROOT_H
#define FE09_B2S3_T3S2B1A_IMMUTABLE_ROOT_H
/* #799 NONINSTALLED POSIX-hosted first-party B0/FRM1 index-root transaction.
 * Actual original S2 APX3, original canonical FBS1 and original B0 index
 * are REUSED unchanged. NO source/producer/BF worker I/O, no delete/GC,
 * no physical NAND/UBIFS powercut, real SSC305 fit or shipping SDK claims.
 */
#include "fe09_b2s3_t3s2b0_manifest.h"
#include <stdint.h>
#include <stddef.h>
#include <sys/types.h>

#define FE_T3S2B1A_MAX_ROOTS FE_T3S2B0_MAX_ROWS
#define FE_T3S2B1A_FILENAME_BYTES 128u

typedef enum {
    FE_T3S2B1A_FAULT_NONE=0,
    FE_T3S2B1A_FAULT_CREATE=1,
    FE_T3S2B1A_FAULT_WRITE=2,
    FE_T3S2B1A_FAULT_FILE_SYNC=3,
    FE_T3S2B1A_FAULT_PUBLISH=4,
    FE_T3S2B1A_FAULT_UNLINK=5,
    FE_T3S2B1A_FAULT_DIRECTORY_SYNC=6,
    FE_T3S2B1A_FAULT_READBACK=7
} fe_t3s2b1a_fault;

typedef struct {
    const fe_t3s2a_spool *original_source; /* already trusted, consumer-only */
    int root_dirfd;                  /* caller-owned, NOT original data dirfd */
    dev_t root_device;
    ino_t root_inode;
    uint64_t source_generation;
    uint32_t capacity,roots_committed;
    uint8_t last_root_digest[32];    /* SHA256 original full FRM1 file bytes */
    uint32_t binding_complete;
    fe_t3s2b1a_fault fault;          /* injected hosted syscall failure */
    uint32_t retry_after_publish;
    uint32_t restart_recovered;
} fe_t3s2b1a_root;

/* Fresh and exclusive owner. Root directory must be separately bound,
 * trusted mode/uid, O_DIRECTORY|O_NOFOLLOW, not the S2-A data directory.
 * Inventories ALL immutable roots, strict 1..N sequence and exact source
 * file replays. Reject alien, duplicate, symlink and orphan/torn temp.
 * At most ONE extra fully stored APX3 source record may be pending root
 * publication; no false advance of an unrooted source epoch.
 */
int fe_t3s2b1a_bind(fe_t3s2b1a_root *root,int exclusive_root_dirfd,
               const fe_t3s2a_spool *original_source);

/* Original full canonical B0 source index is read-only. This is an
 * OUTBOARD-ONLY POSIX transaction, never called from original BF/SPSC.
 * Rebuild and compare exact FRM1 directly from already stored ORIGINAL
 * first-party S2 APX3 file+200B FBS1 before publishing.
 * O_EXCL temp -> bounded exact write -> file fsync -> linkat NO REPLACE
 * -> unlink temp -> directory fsync -> reopen/full re-read and original
 * source replay. Existing exactly identical immutable root may recover
 * ONLY after verified readback; successful return is HOSTED root receipt,
 * not original S1 ACK/power-loss safety or rolling retention.
 */
int fe_t3s2b1a_publish(fe_t3s2b1a_root *root,
                       const fe_t3s2b0_index *original_index);

/* Original last source record may already have been outboard ACKed before
 * a process dies without an index root. Reconstruct its B0 index only
 * from actually persisted original S2-A APX3 files (never fabricate
 * source ACK or BF/Render history). Caller must then publish/validate
 * the pending immutable root explicitly. No automatic fast-forward.
 */
int fe_t3s2b1a_rebuild_index(fe_t3s2b0_index *result,
                             const fe_t3s2b1a_root *root);

/* Test-only bounded fault injection; fail closed without lying about
 * index root publication status, no power-loss certification.
 */
int fe_t3s2b1a_set_test_fault(fe_t3s2b1a_root *root,
                             fe_t3s2b1a_fault boundary);

/* Canonical basename binds original generation, global Capture high-water
 * and exact SHA256 of unmodified serialized FRM1 bytes. No path traversal.
 */
int fe_t3s2b1a_name(uint64_t generation,uint64_t seq,
              const uint8_t index_file_sha[32],
              char dest[FE_T3S2B1A_FILENAME_BYTES]);
#endif
