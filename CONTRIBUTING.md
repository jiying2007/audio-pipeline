# Contributing to audio-pipeline

[简体中文](CONTRIBUTING.zh-CN.md)

`audio-pipeline` is in a **software-commercial-ready maintenance state**. Contributions are welcome when they address a concrete defect, regression, integration need, measured performance/resource problem, or a verified gap in the validation/release/certification control plane. Do not add complexity merely to make the repository appear “more complete”.

## Before changing code

Read:

1. `docs/DEVELOPMENT.md` — normative engineering rules;
2. `docs/ARCHITECTURE.md` — dependency and ownership boundaries;
3. `docs/API_CONTRACT.md` for public API/lifecycle changes;
4. `validation/authority.json` for data/search/validation authority;
5. `docs/PRODUCT_ASSURANCE.md` for release or certification changes.

Chinese contributors can start from `docs/README.zh-CN.md` and `docs/DEVELOPMENT.zh-CN.md`.

## Scope discipline

- Prefer one root cause or one contract change per PR.
- State scope and non-goals.
- Freeze measurement rules, data roles and acceptance thresholds before tuning.
- Never relax a gate, threshold or timeout merely to obtain green CI.
- Do not fabricate target, HIL, thermal, power, acoustic, toolchain, soak or Product Qualification evidence.
- Keep release-neutral maintenance release-neutral; release-bearing behavior follows SemVer/CHANGELOG/release governance.

## Realtime and ownership rules

Synchronous stage/core/module code must not perform heap allocation, mutex waits, file/network I/O, RPC, formatted logging or unbounded work. Architecture-specific intrinsics belong under `src/arch`; CPU/SOC names must not drive generic algorithm behavior.

Once Linux Runtime is started, the DSP worker exclusively owns the live Pipeline. Changes to ownership, queues, counters or lifecycle require ThreadSanitizer coverage.

## Public API and compatibility

The current 2.x public C API/ABI is a compatibility contract. The current line has one public surface; do not introduce parallel compatibility wrappers or reintroduce retired public names. Public floating-point inputs must reject non-finite values before range checks. Preserve precise status meanings (`AP_EINVAL`, `AP_ENOMEM`, `AP_ESTATE`). Breaking public changes require the next major version.

The API/ABI gate compares against the required published compatibility baseline and must fail closed if that baseline cannot be fetched or resolved.

## Tests

Add the smallest targeted test that proves the fix, plus negative/boundary tests when applicable. Depending on scope, expect strict GCC/Clang, ASan/UBSan, TSan, static analysis, fuzz, coverage, backend/composition, SDK consumers, RAM/ELF pruning, paired performance, Arm cross-build/QEMU, acoustic validation and public API/ABI gates.

A PR is not merge-ready until the exact PR head has the required `summary=success`. If the head moves, old CI evidence is stale.

## Data and tuning

Development/search data may select candidates. `validation-grade` is validation/shadow only; `validation-grade-blind` never enters optimizer feedback. Preserve exact source/data/hash/seed identity and all failed candidates. A tuning result may become an `ACOUSTIC_CANDIDATE`; it cannot silently change shipping defaults or grant Product Certification authority.

## Documentation

Update documentation in the same PR when changing API/lifecycle, build options/product presets, ownership/data flow, validation authority, release/certification behavior, diagnostic/privacy behavior or operator commands.

Critical commercial/integration changes must also update the Chinese entry layer under `docs/*.zh-CN.md` where applicable. Machine schemas and explicitly canonical low-level English specifications remain the single source of truth.

## Pull requests

- Do not push directly to `main`.
- Do not force-update release tags.
- Resolve review conversations.
- Merge only through the protected squash path after exact-head required gates pass.
- Reverify exact `main` after merge.
- Allow the governed branch lifecycle workflows to retire terminal same-repository heads; do not bypass their exact-SHA/no-open-PR checks.

## Definition of Done

A change is complete when its root cause/need is documented, targeted and negative tests exist, exact-head required checks pass, relevant docs are updated, protected merge succeeds, exact-main verification succeeds, release behavior matches the change class, and no unclassified branch/evidence debt remains.
