#ifndef FE09_B2S3_T2B_B1S1_SOURCE_CHUNKS_H
#define FE09_B2S3_T2B_B1S1_SOURCE_CHUNKS_H
/* #778 NONINSTALLED research-only APX3 S2 codec integration. One real 10ms
 * Capture frame per actual first-party APX3 file; high overhead/hosted only.
 * Not a rolling recorder, on-disk durability protocol, shipping SDK,
 * physical source attestation, authenticated provenance or SSC305 budget.
 */
#include "fe09_b2s3_t2b_b1s0_owner_spsc.h"
#include "fe09_b2s2_private_apd.h"
#include "fe09_b2s3_t2b_b1s1_chunk_sha256.h"
#include <stddef.h>
#include <stdint.h>

#define FE_B1S1_MAX_CHUNKS 24u
#define FE_B1S1_MAX_CHUNK_BYTES 5120u
#define FE_B1S1_ROW_BYTES 200u
#define FE_B1S1_ROW_DIGEST_OFFSET 168u
#define FE_B1S1_MANIFEST_MAGIC UINT32_C(0x31534246) /* "FBS1" */
#define FE_B1S1_MANIFEST_VERSION 1u

typedef enum {
    FE_B1S1_OK = 0, FE_B1S1_REJECT = -1,
    FE_B1S1_PENDING = -2, FE_B1S1_ORIGINAL_CODEC = -3,
    FE_B1S1_SOURCE = -4, FE_B1S1_CORE = -5,
    FE_B1S1_TAMPER = -6
} fe_b1s1_status;

/* One exact canonical LE 200B row PER real S2 file:
 * [0] magic u32, [4] schema u32, [8] logical Render event u32,
 * [12] source rate, [16] mic count, [20] generation u64,
 * [28] capture source ID, [32] render source ID, [36] capture epoch,
 * [40] owner Render epoch, [44] owner reported-absence reason,
 * [48] global Capture seq u64, [56] local APX3 seq u64 (always 1),
 * [64] local APX3 frame count u32 (=1), [68] file byte count u32,
 * [72] Capture FNV64, [80] actual Render FNV64 or 0,
 * [88..104) physical→PCM slot 4*u32,
 * [104..136) SHA256(exact complete original S2 APX3 file),
 * [136..168) SHA256(previous canonical row) / all zeros for first,
 * [168..200) SHA256(this canonical row bytes [0..168)).
 * Manifest is NOT a signed or durable on-disk transaction.
 */
typedef struct {
    fe_b1s0_state *source; /* exclusive worker; not mutable rebind */
    uint32_t physical_to_slot[4];
    uint32_t committed;
    uint64_t last_global_capture;
    uint32_t chunk_bytes[FE_B1S1_MAX_CHUNKS];
    uint8_t manifest[FE_B1S1_MAX_CHUNKS][FE_B1S1_ROW_BYTES];
    uint8_t chunks[FE_B1S1_MAX_CHUNKS][FE_B1S1_MAX_CHUNK_BYTES];
} fe_b1s1_store;

/* Fresh queue+B0. No producer/worker running at init. Source slots must form
 * a real C1/C2/C4 bijection; immutable during source-owner threads.
 */
fe_b1s1_status fe_b1s1_init(fe_b1s1_store *sink,
     fe_b1s0_state *source, const uint32_t slots[4]);

/* Worker only: before SPSC tail commit snapshot exact source PCM, verify hash,
 * make a real ORIGINAL S2 one-frame APX3 in isolated scratch and hash row.
 * ONLY after all codec/hash/capacity checks succeed may frozen first-party
 * B1-S0 consume source and emit actual BF. After that there are no fallible
 * recorder operations: bounded memcopies to caller-owned in-memory sink.
 * Failed preflight or B1-S0 returns do not commit sink/queue/BF/output.
 * Does NOT claim durability against process crash/power loss.
 */
fe_b1s1_status fe_b1s1_append_one(fe_b1s1_store *sink,
     float *beam,size_t beam_count,float *render_ref,size_t ref_count,
     void *work,size_t work_bytes,fe_b1s0_receipt *result);

/* Original first-party fe_s2_decode/fe_s2_replay per chunk, strict LE
 * global-local bijection and original source FNV witness, plus exact SHA256
 * file digest and canonical 200B manifest hash chain. No writes on failure.
 */
fe_b1s1_status fe_b1s1_verify(const fe_b1s1_store *sink,
                              uint32_t *verified_count);

#endif
