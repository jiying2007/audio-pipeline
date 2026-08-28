# Changelog

All notable changes are recorded here. The project follows semantic-version intent; before 1.0, minor releases may contain documented hard-cut API changes.

## [Unreleased]

- target-board Cortex-A7/A32/AArch64 certification records remain SKU-specific work.

## [0.5.0] - 2026-08-28

- harden runtime ownership and eliminate unsynchronized pipeline-metrics reads from the runtime control plane;
- add fast-math-safe finite parameter validation and stricter ERLE/convergence telemetry;
- add explicit timestamp observation and echo-path-change notification;
- promote Activity/DTD to a standalone reusable module;
- add build-time IO/internal-rate, microphone, delay, AEC-tail and runtime-queue envelopes for physical RAM pruning;
- add band-limited boundary resampling with explicit FAST fallback and filter-delay reporting;
- make standalone module lifecycle contracts consistently resettable and fixed-frame;
- separate standalone adapters from full-pipeline unity compilation for linker/ROM pruning;
- export CMake package targets and pkg-config metadata and validate real downstream consumption;
- add QEMU Arm execution, TSan, coverage, static analysis, SKU RAM/ELF gates and acoustic-eval contracts;
- add nightly fuzzing, release packaging/checksums, security policy and certification templates.

## [0.4.0] - 2026-08-27

- add static pipeline composition and standalone DSP module APIs;
- physically prune omitted module translation units and state;
- add RAW, voice-front-end, AEC-only and NS-only composition contracts.
