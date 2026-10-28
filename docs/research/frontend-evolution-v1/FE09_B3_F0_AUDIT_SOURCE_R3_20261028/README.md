# FE09 B3/F0 audit-source R3 registration

This is a source-only registration for the reviewed 2.3.59 audit changes.
It preserves the original R1/R2 plans, source locks, scientific functions,
negative controls, budgets and results. It does not establish an R3 B3 or F0
measurement, shipping authority, a public four-microphone SDK or device/HIL
qualification.

## Exact source boundary

The immutable [registration](PREREGISTRATION.json) records the proposal PR #861
head `69711e6c009ac62fd66ce9131f140fcf57912625` as provenance. It does not require
that head to remain an ancestor after protected squash merges. Each execution
must instead prove its actual clean committed head and the exact reviewed
source bytes, Git blobs and SHA-256 identities.

The B3 predecessor has 77 members: 66 checked against current source and 11
reference-only historical members. Exactly nine of the 66 current members
have separately reviewed changes; the other 57 remain byte-identical. F0's
88-member lock shares those same 66 live members and has 22 additional
members. All 22 additional F0 members remain unchanged. The B3 77-member set
is not a subset of the F0 88-member set.

| Reviewed member | Audit change |
| --- | --- |
| `CMakeLists.txt` | Version, package paths and deterministic test registration |
| `cmake/audio-pipeline.pc.in` | Absolute GNUInstallDirs paths |
| `cmake/audio-pipeline-runtime.pc.in` | Absolute GNUInstallDirs paths |
| `include/audio_pipeline/audio_modules.h` | Comments for resampler and BF capability contracts |
| `include/audio_pipeline/audio_runtime.h` | Comments for lifecycle and ownership contracts |
| `src/modules/ap_beamformer_module.c` | Reject unavailable direction tracking before mutation |
| `src/modules/ap_resampler_module.c` | Validate direction, channel and compiled geometry |
| `src/platform/linux/ap_runtime.c` | Worker ownership through completed stop |
| `src/sync/ap_sync.c` | Reject timestamp conversion overflow before arithmetic |

The nine-file delta is separately pinned. The source gate reads the complete
old locks and their historical Git objects, checks every reviewed before and
after identity, applies the delta, then reverses it and requires identical
original bytes. Unknown, missing or duplicated delta paths fail. Current
source is never replaced by the historical copy for a measurement.

The plan's `source_delta` byte count, Git blob and SHA-256 describe the decoded
patch bytes. The `.patch.b64` file transports those bytes in one base64 line;
its encoded-file Git blob is a different identity.

The existing R2 admission script is pinned before its immutable helper code
is imported. Its thirteen negative controls, including rejection of 2.3.59
under the old R2 profile, remain unchanged. The R3 source tests add 27 fixed
negative controls for reviewed and unchanged source drift, version/checkout
identity, encoding, patch integrity, path scope and registration drift.

## Source-only commands

On the independently reviewed qualifier branch, and later on a source
candidate, run:

```sh
python3 tests/validation/frontend_evolution/fe09_b3_f0_r3_source_admission.py \
  --self-test --check-current
```

`--check-current` delegates 2.3.56, 2.3.57 and 2.3.58 to the original R2
admission and returns its original receipt unchanged. Only 2.3.59 uses the
new R3 receipt. Unknown versions still fail. `--check` requires 2.3.59 and
is the strict source boundary used by the new R3 collectors.

The self-test reconstructs source fixtures and checks metadata only. It does
not compile or launch B3/F0 DSP processes. An R3 source receipt explicitly
reports `science_executed=false`, `r1_or_r2_result_inherited=false` and
`shipping_authority=false`.

## R3 collectors and independent source review

The separate executor derivation is implemented in these files:

- [B3 R3 collector](../../../../tests/validation/frontend_evolution/fe09_b3_f0_deadline_r3_qualification.py)
- [F0 R3 collector](../../../../tests/validation/frontend_evolution/fe09_t3s3_f0_call_resource_r3_qualification.py)
- [Independent R3 derivation contract](../../../../tests/validation/frontend_evolution/fe09_b3_f0_r3_derivation_contract.py)

The derivation contract binds the old and new source identities and preserves
the original scientific functions, fixed coverage and timing/resource rules.
Its source and metadata controls do not constitute an executed R3 result.

## Execution and evidence authority

R3 DSP execution must wait until the independent source-only qualifier
PR #862 has passed protected merge and its independent exact-main gates.
The previously observed 2.3.58 main Verify/Release receipts in the plan are
baseline provenance; they are not R3 qualifier or execution results.

After that prerequisite, the independently reviewed R3 collectors must run
all original fixed targets and cases on the actual new execution head and
use distinct R3 receipt and artifact identities. B3 retains 3 targets,
11 trajectories per target and 600 frames per trajectory; F0 retains
36 processes, 600 frames per process and 144 statistic groups. All original
time, archive, error and resource rules remain unchanged. Historical R1/R2
PASS results cannot serve as results for these nine changed source members.

中文边界：本登记只确认 2.3.59 的九项精确源码变化与可逆历史身份，旧 R1/R2
计划、锁、负例和测量结果保持原身份。B3 的 77 项与 F0 的 88 项共享 66 项，
F0 另有 22 项保持原字节；不得把旧结果当作新源码的测量结果。必须先完成
独立资格 PR #862 的保护合并和独立主线门禁，再以新 R3 身份运行原定完整
target/case 集合；当前源码自测不执行 DSP，也不代表真机、HIL 或产品资格。
