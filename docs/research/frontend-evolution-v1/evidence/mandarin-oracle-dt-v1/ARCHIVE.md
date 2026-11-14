# Oracle failure archive

Actual outcome is BASELINE_IDENTITY_FAILED, one baseline CALL process and no candidate execution. No promotion, threshold relaxation or successful scientific matrix claimed. See RESULT.md. This is an offline research diagnostic, not a deployable oracle or production code.

The complete local evidence bundle audio-mandarin-oracle-dt-failure-evidence.tar.gz is 2800675 bytes, SHA256020dc5dc6bec94dc672c475dd9981278f983a91c4690c0ecfcc7e64289c8a8ee. It includes107 individually hashed source/input/library/binary/output/receipt files; this public archive intentionally keeps only text source/metadata, not repeated audio or binaries. The preserved run.py needs the exact original D2 ZIP and separately admitted known-near reference at the original paths; it refuses to overwrite a prior run-state. Reproduction is not an ordinary CI operation.

All historical source/baseline identities are retained; current archive-base is not a new target or current-main waveform run. The later read-only failure diagnosis did not run DSP. Full historical libm/libc/loader identity is unavailable from the retained D2 ZIP, so the environment mismatch is unresolved rather than hidden by tolerances.

compiler.stdout is transported losslessly as compiler.stdout.b64 to preserve the raw trailing blank line without weakening whitespace checks. Decode base64 before using original receipts; expected decoded SHA256 is 4dc9a4e32fd9e06d42fb307688c59d6d889f0ff90ce034cbefed21b0d451fd81.
