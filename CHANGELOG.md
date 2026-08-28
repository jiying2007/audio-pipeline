# Changelog

All notable changes are recorded here. The project follows semantic-version intent; before 1.0, minor releases may contain documented hard-cut API changes.

## [Unreleased]

- target-board Cortex-A7/A32/AArch64 certification records remain SKU-specific work.

## [0.7.0] - 2026-08-28

- make the bandlimited boundary resampler the formally gated production default while preserving the explicit FAST validation fallback;
- enforce fixed-ratio anti-alias/passband contracts for 8/16 kHz internal DSP paths across supported device rates;
- formalize capture/render timestamp observation and explicit echo-path-change notification as synchronization/AEC reset contracts;
- add a repository acoustic-evaluation manifest/schema/runner so private product corpora can use the same metric interface without being committed to the repository;
- add dedicated Audio Quality Gates covering bandlimited/FAST resampling, synchronization/route-change semantics and the acoustic-eval self-test.

The repository audio-quality gate is synthetic/contract validation. Real robot far-end, double-talk, motor-noise, enclosure/path-change and product microphone/speaker corpus certification remains per shipping SKU and is not inferred from hosted CI.

## [0.6.0] - 2026-08-28

- formalize compile-time geometry caps for maximum I/O/internal rate, microphone count, render delay, AEC tail and runtime queue depth;
- make LOW/TINY/RAW builds physically reduce pipeline resident RAM rather than only reducing runtime work;
- prune Linux runtime queue storage from the selected maximum I/O geometry and queue depth;
- keep standalone module adapters out of full-pipeline unity batches so the linker can drop unused public wrappers;
- add final-consumer ELF pruning verification instead of treating static-library size as a ROM claim;
- add absolute hosted GCC RAM ceilings: full <=80,000 B, LOW <=50,000 B, TINY <=28,000 B, RAW <=2,048 B; runtime full <=32,768 B and TINY <=8,192 B.

Current hosted GCC reference measurements are pipeline full=78,072 B, LOW=46,904 B, TINY=25,384 B, RAW=1,064 B and runtime full=31,824 B, TINY=4,464 B. These are CI resource-contract measurements, not target-board CPU/performance claims.

## [0.5.0] - 2026-08-28

- eliminate unsynchronized Linux runtime reads of worker-owned pipeline telemetry and require ThreadSanitizer coverage;
- add consistent finite/NaN/Inf configuration validation and negative contracts;
- tighten ERLE telemetry to valid AEC far-end-only, non-double-talk convergence epochs;
- promote Activity/DTD to a standalone reusable module shared by high-level and standalone AEC integration;
- add explicit timestamp observation and echo-path-change notification contracts;
- normalize standalone module reset/frame/lifecycle semantics;
- add build fingerprinting for backend, SIMD, fast-math and compiled-envelope diagnostics.

## [0.4.0] - 2026-08-27

- add static pipeline composition and standalone DSP module APIs;
- physically prune omitted module translation units and state;
- add RAW, voice-front-end, AEC-only and NS-only composition contracts.
