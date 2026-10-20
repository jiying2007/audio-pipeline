#ifndef FE09_B2S3_T3S2B1BA1_ANCHOR_ROOT_H
#define FE09_B2S3_T3S2B1BA1_ANCHOR_ROOT_H

/* #809: noninstalled, single-owner HOSTED FRM2 v2 checkpoint. The caller
 * quiesces the original A0 owner after its 32 source ACKs. This separate
 * root transaction never updates S1, changes A0, or deletes original data.
 */
#include "fe09_b2s3_t3s2b1ba0_finite_outboard.h"

#define FE_T3B1BA1_MAGIC UINT32_C(0x324d5246)
#define FE_T3B1BA1_VERSION 2u
#define FE_T3B1BA1_HEADER_BYTES 224u
#define FE_T3B1BA1_MEMBER_BYTES 72u
#define FE_T3B1BA1_MEMBERS 16u
#define FE_T3B1BA1_ROOT_BYTES 1376u
#define FE_T3B1BA1_NAME_CAP 192u
#define FE_T3B1BA1_DIGEST_OFFSET 160u

typedef enum {
    FE_T3B1BA1_FAULT_NONE=0,
    FE_T3B1BA1_FAULT_CREATE_ENOSPC=1,
    FE_T3B1BA1_FAULT_CREATE_EROFS=2,
    FE_T3B1BA1_FAULT_WRITE_EIO=3,
    FE_T3B1BA1_FAULT_SHORT_WRITE=4,
    FE_T3B1BA1_FAULT_FILE_SYNC=5,
    FE_T3B1BA1_FAULT_LINK=6,
    FE_T3B1BA1_FAULT_UNLINK_TEMP=7,
    FE_T3B1BA1_FAULT_DIR_SYNC=8,
    FE_T3B1BA1_FAULT_READ_EIO=9,
    FE_T3B1BA1_FAULT_SHORT_READ=10
} fe_t3b1ba1_fault;

typedef struct {
    int dirfd;
    dev_t device;
    ino_t inode;
    fe_t3b1ba0_owner source; /* exact immutable A0 snapshot, never written */
    uint32_t binding_complete;
    uint32_t root_visible_on_bind; /* visibility is not a recovered ACK */
    fe_t3b1ba1_fault test_fault;
} fe_t3b1ba1_owner;

typedef struct {
    uint64_t first_sequence,last_sequence,original_high_water;
    uint32_t original_files_verified;
    uint32_t root_visible_verified;
    uint32_t hosted_checkpoint_committed;
    uint32_t root_visible_on_bind;
    uint32_t source_ack_proven; /* always zero; A1 has no ACK authority */
    uint8_t left_anchor_sha256[32],root_sha256[32];
} fe_t3b1ba1_receipt;

/* A separate exclusive O_DIRECTORY|O_NOFOLLOW directory, never A0's inode.
 * Every present root is source-verified; an empty root dir can bind too.
 * Existing visible data never manufactures a prior durability/ACK receipt.
 */
int fe_t3b1ba1_bind(fe_t3b1ba1_owner *owner,int exclusive_root_dirfd,
    const fe_t3b1ba0_owner *quiescent_original_source);

/* Original A0 replay before/after readonly canonical-row access. FRM2 is
 * fixed at original cap/high-water 32, logical retained window 17..32.
 * Export/verify use exact wire length; no alternate FRM1 interpretation.
 */
int fe_t3b1ba1_encode(const fe_t3b1ba1_owner *owner,
    uint8_t root[FE_T3B1BA1_ROOT_BYTES]);
int fe_t3b1ba1_verify_bytes(const fe_t3b1ba1_owner *owner,
    const uint8_t *root,size_t bytes);
int fe_t3b1ba1_name(const uint8_t root[FE_T3B1BA1_ROOT_BYTES],
    char name[FE_T3B1BA1_NAME_CAP]);

/* Read means visible+source-verified only (hosted_checkpoint_committed=0).
 * Publish is file fsync + no-clobber link + temp unlink + directory fsync
 * + independent reopen/readback. A same-root retry repeats file+directory
 * fsync and readback; it never overwrites a root or advances source ACK.
 * Failure clears the receipt and preserves already written forensic bytes.
 */
int fe_t3b1ba1_read(const fe_t3b1ba1_owner *owner,
    fe_t3b1ba1_receipt *receipt);
int fe_t3b1ba1_publish(fe_t3b1ba1_owner *owner,
    fe_t3b1ba1_receipt *receipt);
int fe_t3b1ba1_set_test_fault(fe_t3b1ba1_owner *owner,
    fe_t3b1ba1_fault fault);

#endif
