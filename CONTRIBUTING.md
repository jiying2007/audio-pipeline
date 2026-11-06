# Contributing to audio-pipeline

[简体中文](CONTRIBUTING.zh-CN.md)

`audio-pipeline` is **technical research only**. Contributions address concrete defects, reproducibility, acoustic experiments, embedded integration and measured performance/resource problems. The current execution policy is `docs/RESEARCH_ONLY_EXECUTION.md`; commercial publication and certification are not research prerequisites. Do not add complexity merely to make the repository appear “more complete”.

## Before changing code

Read:

1. `docs/DEVELOPMENT.md` — normative engineering rules;
2. `docs/ARCHITECTURE.md` — dependency and ownership boundaries;
3. `docs/API_CONTRACT.md` for public API/lifecycle changes;
4. `validation/research-authority.json` for data/search/validation authority;
5. `docs/RESEARCH_ONLY_EXECUTION.md` for research scope, source rights and evidence boundaries.

Chinese contributors can start from `docs/README.zh-CN.md` and `docs/DEVELOPMENT.zh-CN.md`.

## Scope discipline

- Prefer one root cause or one contract change per PR.
- State scope and non-goals.
- Freeze measurement rules, data roles and acceptance thresholds before tuning.
- Never relax a gate, threshold or timeout merely to obtain green CI.
- Do not fabricate target, HIL, thermal, power, acoustic, toolchain, soak or independent research evidence.
- Document runtime/API changes and preserve applicable SemVer/CHANGELOG and compatibility checks; no commercial Release or SKU approval is required for research.

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

Development/search data may select candidates. `validation-grade` is validation/shadow only; `validation-grade-blind` never enters optimizer feedback. Preserve exact source/data/hash/seed identity and all failed candidates. A tuning result may become an `ACOUSTIC_CANDIDATE`; it cannot silently change runtime defaults or establish independent target-board results.

## Documentation

Update documentation in the same PR when changing API/lifecycle, build options/research presets, ownership/data flow, validation authority, research execution behavior, diagnostic/privacy behavior or operator commands.

Critical research/integration changes must also update the Chinese entry layer under `docs/*.zh-CN.md` where applicable. Machine schemas and explicitly canonical low-level English specifications remain the single source of truth.

## Pull requests

- Do not push directly to `main`.
- Do not force-update release tags.
- Resolve review conversations.
- Merge only through the protected squash path after exact-head required gates pass.
- Reverify exact `main` after merge.
- Allow the governed branch lifecycle workflows to retire terminal same-repository heads; do not bypass their exact-SHA/no-open-PR checks.

## Definition of Done

A change is complete when its root cause/need is documented, targeted and negative tests exist, exact-head required checks pass, relevant docs are updated, protected merge succeeds, exact-main verification succeeds, research behavior matches the stated scope, and no unclassified branch/evidence debt remains.
