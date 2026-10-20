#ifndef FE09_B2S3_T2B_B1S1_CHUNK_SHA256_H
#define FE09_B2S3_T2B_B1S1_CHUNK_SHA256_H
/* #778: private research integrity ONLY. Not signing/authentication or
 * a shipping cryptographic primitive. SHA-256 FIPS 180-4 one-shot with
 * exact byte boundaries, bounded maximum 1 MiB, no external dependency.
 * Independent Python hashlib rehash of emitted chunk/manifest is mandatory.
 */
#include <stddef.h>
#include <stdint.h>
#define FE_B1S1_SHA256_BYTES 32u
int fe_b1s1_sha256(const uint8_t *data, size_t bytes,
                   uint8_t digest[FE_B1S1_SHA256_BYTES]);
#endif
