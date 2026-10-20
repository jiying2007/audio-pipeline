#ifndef FE09_B2S3_T3S2B0_MANIFEST_H
#define FE09_B2S3_T3S2B0_MANIFEST_H
/* #797: NONINSTALLED, source-anchored original FBS1 manifest CONTRACT ONLY.
 * NO on-disk index commit, GC, pruning, rolling recorder, physical powercut,
 * SSC305 target, public API or shipping audio integration.
 */
#include "fe09_b2s3_t3s2a_atomic_spool.h"
#include <stddef.h>
#include <stdint.h>

#define FE_T3S2B0_MAGIC UINT32_C(0x314d5246) /* FRM1 little-endian */
#define FE_T3S2B0_VERSION 1u
#define FE_T3S2B0_HEADER_BYTES 160u
#define FE_T3S2B0_MAX_ROWS FE_T3S2A_MAX_FILES
#define FE_T3S2B0_MAX_BYTES \
    (FE_T3S2B0_HEADER_BYTES+FE_T3S2B0_MAX_ROWS*FE_T3S1_ROW_BYTES)

typedef struct {
    const fe_t3s2a_spool *source; /* exact prebound S2-A source */
    uint64_t source_generation,first_seq,last_seq,high_water;
    uint32_t rate_hz,physical_mics,render_enabled;
    uint32_t capture_id,render_id,physical_to_slot[4];
    uint32_t maximum_rows,count;
    uint8_t left_anchor_sha256[32]; /* zero until independently qualified prune */
    uint8_t rows[FE_T3S2B0_MAX_ROWS][FE_T3S1_ROW_BYTES];
    uint8_t root_sha256[32];
} fe_t3s2b0_index;

/* Bind an already completely admitted original S2-A POSIX owner.
 * May bind a recovered owner, but a nonempty prior index must be decoded
 * and verified before more ACKs are observed. B0 never deletes any file.
 */
int fe_t3s2b0_bind(fe_t3s2b0_index *index,
                    const fe_t3s2a_spool *source,
                    uint32_t maximum_rows);

/* Call before outboard S2-A consumption: a positive result means ONLY
 * the in-memory manifest has room, not that a filesystem ACK is durable.
 */
int fe_t3s2b0_can_accept(const fe_t3s2b0_index *index);

/* Observe one ALREADY fully ACKed original first-party S1 drain. This
 * validates and copies the exact canonical original FBS1 row. No file I/O,
 * heap, source/BF mutation or atomic coupling between ACK and index yet.
 * A separate B1 persistent root transaction is mandatory for rolling.
 */
int fe_t3s2b0_observe_acked(fe_t3s2b0_index *index,
                     const fe_t3s1_slot *original_slot,
                     const fe_t3s1_drain_receipt *original_ack);

/* Encode strict little-endian outer source INDEX, not an APX3 codec. Root
 * SHA256 covers header (with root bytes zeroed) plus complete original
 * canonical rows. Caller output/written unchanged if any check fails.
 */
int fe_t3s2b0_encode(const fe_t3s2b0_index *index,
                       uint8_t *destination,size_t capacity,size_t *written);

/* Decode using a freshly trusted original S2-A owner recovered from its
 * own exact files; rejects index ahead/behind or stale-source identity,
 * gaps, extra bytes, forged original FBS1 row chain or root SHA.
 * Never invent a left anchor: B0 supports only complete 1..N lineage.
 */
int fe_t3s2b0_decode(fe_t3s2b0_index *result,
              const fe_t3s2a_spool *recovered_owner,
              const uint8_t *serialized,size_t exact_bytes);
#endif
