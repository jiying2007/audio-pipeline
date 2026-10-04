# SSC305 conservative SDK delivery

[简体中文](SSC305_DELIVERY.zh-CN.md)

The governed software release has three distinct identities. The ordinary SDK
is the native hosted build; `reference-armhf-sdk` is the exact
`ssc305-cortex-a32-low` preset built with the pinned CI reference toolchain;
a shipping BSP SDK must instead use the approved product compiler/sysroot and
complete the existing product certification path. A reference SDK is not proof
that its libc/loader/ABI matches an SSC305 firmware image.

## One build, multiple bound proofs

The existing required Resource Gates job builds the conservative preset once,
installs that same SDK into a clean prefix, and tests CMake, pkg-config, runtime
and build-info consumption under AArch32 QEMU. The offline processor links the
same installed core library; it does not rebuild a default host configuration.
Resource qualification and the installed probe must agree exactly, including
source revision and configuration digest. The SDK manifest records library,
ELF, launcher, generated-header, compiler/package, policy and evidence hashes.
The pinned image and reference sysroot path identify the reference environment,
not a vendor BSP. SDK tar packaging is repeated and hash-compared; this is not
an independent clean-build reproducibility claim.

Canonical generator v3 seeds 1307/2307/3307 each supply 27 cases. The existing
validator enforces the unchanged `validation-smoke.json` policy and original
case assertions. Every case is additionally processed twice and the actual PCM
SHA-256 values must match. The QEMU launcher hash in canonical reports and the
actual processor ELF hash are both bound in the delivery manifest. Case-level
metrics and failures are retained. No parameter, threshold, corpus selection or
shipping DSP change is selected by these reports.

This is **regression evidence**, not public-data or real-enclosure quality
certification. Cases outside the conservative physical envelope remain stress
observations, not an expanded supported envelope. Public validation, moving
sources, actual motor noise and hardware route evidence retain their separate
existing authorities. Missing dimensions are explicitly unmeasured.

## Resource budget and probe semantics

`ci/ssc305-resource-profiles.json` is the policy source. The conservative sum of
pipeline and runtime caller-owned state must be at most **50,000 bytes** in
addition to the separate public limits. This sum does not include thread stacks,
application/libc RSS, ALSA/kernel buffers, external PCM queues or optional Flight
Recorder memory. Those remain separate product budget items. The effect-first
profile stays research-only and does not inherit conservative shipping authority.

Resource-probe `qemu_probe_repeat_identical` means raw metadata stdout is
identical; only the acoustic snapshot claims PCM repeat equality. Resource spec
v3 and measurement/qualification v2 reject the retired live field/schema rather
than accepting a compatibility fallback. Immutable historical records are not
rewritten. Algorithmic latency is neither adaptive convergence time nor CPU time.

## Non-DUT engineering endurance

The existing extended runtime test has an opt-in `--endurance FRAMES CYCLES`
mode. Required Resource Gates execute **2,000,000 frames over 64 lifecycles** on
a native SCALAR projection of the conservative preset, with ASan, UBSan and leak
detection. Its runtime/control/realtime/build-info test selection is explicit:
generic 100 ms delay fixtures stay in the normal full CI matrix, not the 60 ms
SKU lane. Existing queue saturation/backpressure and command validation tests
are reused; the long stream adds discontinuities, timestamp jumps, missing
render, XRUN/codec reopen metadata, path changes and monotonic counter checks.

The repeated stream fingerprint is FNV-1a for diagnostic cycle comparison, not
a cryptographic PCM identity claim. Independent acoustic repeats use SHA-256.
Host elapsed time is recorded separately from processed audio duration; neither
is 72-hour product route soak or silicon performance. Source/build identity,
executable, selected tests, configuration, sanitizer log and hashes are retained.
Failure artifacts are uploaded; a failed or incomplete result cannot be sealed
as passing delivery evidence. Other full CI sanitizers and TSan remain required.

## Release consumption

Beginning with v2.3.55, Release downloads only its triggering exact-main Verify
run's resource and engineering artifacts, checks complete file/hash sets and
source identities, then includes reference SDK, SPDX and sealed evidence in the
ordinary release manifest/checksums/attestations. Existing immutable releases
before v2.3.55 retain their historical eight-asset contract; new releases require
twelve assets and cannot fall back to the old set. Actions artifacts are
transport; accepted release evidence survives in the immutable release.

After extracting `reference-armhf-evidence.tar.gz` into a clean directory,
verification from the matching source checkout is:

```bash
python3 scripts/ssc305_delivery.py verify --output extracted-reference \
  --source-revision <exact-40-hex-release-source> \
  --artifact-class reference-armhf-sdk-not-shipping-bsp
```

The same command accepts the extracted engineering evidence with
`--artifact-class host-engineering-not-product-soak`. Build with the official
BSP before device deployment; never copy a native hosted library into an Arm
image. CPU/p99/RSS/stack/thermal/power and Product Certification remain governed
by [PERFORMANCE](PERFORMANCE.md), [PORTING](PORTING.md) and `certification/`.
