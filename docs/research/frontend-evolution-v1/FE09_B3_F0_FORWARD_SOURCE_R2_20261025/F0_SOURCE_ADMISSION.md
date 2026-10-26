# FE09-T3S3-F0 R2 — Independent 88-member source admission

This is **source-only code**, not a fresh F0 host experiment, R2 audio quality result, downstream product permission or evidence of SSC305 72-hour endurance.

The original F0 [T3S3 source lock](../FE09_T3S3_F0_RESOURCE_PREREGISTRATION_20261024/source-lock.json) independently freezes **88** source/authority members at commit `5187c5e59526d4047b3965b44c770ab21edbde9f`. Its source lock Git blob is `54278f28e9e61c2714d0fc0581b9f6e915c9f368`. This is **not** the B3 R1 77-member lock; exactly 66 member identities are shared and byte-equal, with another 22 F0-only rows.

The new `fe09_t3s3_f0_r2_source_admission.py` first executes the separately protected B3 T1 source checks. It then independently reads all 88 F0 historical rows, verifies all same-path B3/F0 original identities, checks the exact original baseline byte content and requires every current source to match, permitting only:

- v2.3.57: exact `CMakeLists.txt` and `src/platform/linux/ap_runtime.c` forward-patched preimages.
- v2.3.58: those two plus the exact deterministic `pkg-config` `.pc.in` token-only transformations, compared byte-for-byte to patches and the protected registration.
- v2.3.56: original sources only; this is a historical predecessor check, not an R2 experiment.

All unknown versions, changes to the 22 F0-only files, altered member sets/hashes, changed forward patch bytes, unsafe paths and unsupported promotions must reject. The original F0 88-row lock and its resource collector remain unmodified.

To verify source-only constraints:

```sh
python3 tests/validation/frontend_evolution/fe09_t3s3_f0_r2_source_admission.py --self-test
python3 tests/validation/frontend_evolution/fe09_t3s3_f0_r2_source_admission.py --check
```

The eventual **T2 actual F0 experiment is separate**: a newly reviewed runner must execute 36 actual processes and 21,600 distinct frames with 144 metric groups using the frozen resource/time limits, exact compiler/library provenance, per-run SHA256 receipts and full negative controls. The original R1 F0 archive cannot be re-labelled into a new R2 PASS.

This source-only change is stacked behind protected B3 T1 [#856](https://github.com/jiying2007/audio-pipeline/pull/856), and must go through its own exact-head PR checks, protected squash and fresh-main Verify/Release before any R2 F0 DSP run.
