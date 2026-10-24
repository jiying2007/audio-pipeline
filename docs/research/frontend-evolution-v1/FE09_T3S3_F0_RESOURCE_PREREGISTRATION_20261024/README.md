# FE09 T3-S3 F0: actual CALL resource characterization

## Frozen before measurement / 测量前固定

This is [leaf #841](https://github.com/jiying2007/audio-pipeline/issues/841)
under #767 / #733 / #657. Source
baseline: `5187c5e59526d4047b3965b44c770ab21edbde9f`, after #840. The original
B3-F0 remains unchanged. `source-lock.json` fixes 88 original build, DSP,
driver, verifier and input-authority files. `test-contract.json` fixes the
schedule, measurement boundaries and budgets before the first execution.
Root must independently confirm this baseline's own Verify and matching
Release/convergence before hosted research qualification; a candidate cannot
qualify its own predecessor. Local toolchain diagnostics remain separately
labelled and cannot supply hosted or AArch32 evidence.

The published CI image is
`ghcr.io/jiying2007/audio-pipeline-ci@sha256:69d38c66e09885b78eb3abba3f8b7dcc92363b71430dc39fc7f74978ffae2e57`.
Local compiler/CMake identity is recorded honestly; it is not that image.

## One question

What resources does the already-qualified C4 ULA105mm / 16kHz / FULL actual
CALL composition consume in this finite hosted driver? This changes no DSP,
gate, parameter, codec, public ABI, source ownership or reference PCM.

Each target runs exactly ALL_P then PAP, each three times, each reference
followed by measured: 12 processes/target, 36 for Native + ASan/UBSan + ARM32
under QEMU. Every process executes all 600 frames. No warmup trimming,
fastest-run selection, hidden retries or threshold adjustment is permitted.
The original plain binary is the reference. A separately linked probe
includes the unchanged original driver and wraps only source publication,
the B3 worker and bind calls. The same original library/configuration and
unchanged B3 verifier establish raw PCM, beam and per-frame public-metric
equivalence. The original B3 qualification remains a separate prerequisite
regression, not a result rewritten by this experiment.

## Measurement boundary / 测量口径

- Capture publication, Render PRESENT/ABSENT publication and complete
  `fe_b3_f0_process_one` calls each record monotonic wall and thread CPU
  nanoseconds. Their sum is the disjoint API-call cost; fixture copies,
  validation, sample storage after the final clock reads and evidence I/O are
  excluded and labelled.
- Bind is timed separately, including its two temporary reference arenas.
  This is not complete initialization or operating-system cold-start timing.
- Every frame's raw times, clock resolution, nearest-rank p50/p95/p99/max,
  CPU milliseconds per audio second, and frames 201/241 are retained for
  every repetition. Each wrapped call uses four clock reads: wall-start,
  CPU-start, CPU-end, wall-end. Clock-helper conversion and call-return costs
  within an interval are included, with no overhead subtraction; only sample
  storage after the final clock reads remains outside. Native is hosted
  timing; sanitized and QEMU timing are descriptive tool overhead only.
- Parent `wait4` records the exact child PID's peak RSS through exit and
  user/system CPU. Linux ru_maxrss KiB is converted to bytes. This includes
  all compiled test fixtures, PCM/log arrays, libc and loader; QEMU also
  includes the host emulator. It is not a device process or a deployable
  minimum. Child evidence I/O is included in process CPU, not frame timing.
- Reuse the original resource ledger, add timing storage and disclose final
  ELF sections, compiler identity, build/link recipes and per-function `.su`.
  Timing storage counts all measurement-global arrays, bind sample, error flag
  and clock-resolution scalars; linker padding remains in the ELF section total.
  Actual state/work demand and fixture allocation are separate quantities;
  do not sum overlapping entries. The B3 driver contains three full fixtures,
  a fresh mono reference, full input/output/beam arrays and all frame logs.
- Complete thread-stack high-water/cumulative bound, heap high-water,
  scheduler/real-time behavior, physical clocks, SSC305 RSS/CPU/thermal/power,
  cold-system boot and recorder costs remain explicitly unmeasured.

The C4 192KiB suggested state/work screening budget and B0's existing 50,000B
definition are not changed. No new numeric hosted speed/RSS admission limit
is invented. A descriptive high cost is a valid measurement, not permission
to rename the scope or to change the threshold.

## Finite execution and independent readback

180 seconds total stage budget, 60 seconds per build/tool command, 30 seconds
per child. In CI the original 900-second frontend-reference job start is
reused and 60 seconds remain reserved for archival. The stage does not reset
that clock or increase the job timeout. Metadata self-tests run inside the
same 180-second collector budget. The existing first workflow step retains
the exact Jobs API endpoint, bounded original response bytes, request times
and original deadline file. Before any build or target process, the collector
independently selects the job from those response bytes and binds its ID,
name, run, attempt, start and event head to the deadline and execution context.
Readback repeats the same comparison; final independent review also checks
that tuple against Actions itself. No additional API query or permission is
needed. Final artifact <=32MiB; one raw
temporary case <=8MiB; each process log and timing file <=1MiB. All failures
and partial current-case bytes are preserved. No retry is hidden.

Full source/config/input/build identity, raw outputs checked before success
compression, original B3 semantic checks, raw timing and exact process usage
are retained. Original-source drift, absent/reordered/duplicated frames,
bool/negative time values, missing calls/repeats, mutated PCM/public metrics,
missing RSS, image drift and forbidden promotion are rejected. Meaningful
mutations use complete actual evidence and require no extra DSP execution.
Readonly verification recomputes every summary and checks every sealed member.

Success means only
`FE09_T3S3_F0_ACTUAL_CALL_RESOURCE_CHARACTERIZATION_NO_DEVICE_PROMOTION`.
Local partial targets remain partial; missing evidence is not success.
Protected PR/main Verify, matching Release/convergence and independent
original-artifact readback are still required for final stage closure.
I025-I040, A2 fixed 1..32->17..32 retirement, continuous rolling, public C4 SDK,
and E001 `v2.3.16 / 57e4c64adc1cf06819e46e24e275ecd746d5f17f` stay separate.
