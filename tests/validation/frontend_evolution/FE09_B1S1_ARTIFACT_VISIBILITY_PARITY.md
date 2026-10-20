# FE09 B1-S1 CI Artifact visibility parity / B1-S1 同运行证据可见性保护

**Independent registration:** [#782](https://github.com/jiying2007/audio-pipeline/issues/782).
**Immutable base:** `e7b3a3c0331ed8241dc1c34ea657aae4555cc522`.
**Protected predecessor:** [B1-S1 #778](https://github.com/jiying2007/audio-pipeline/issues/778), [PR #780](https://github.com/jiying2007/audio-pipeline/pull/780), pushed-main [Verify 38997717739](https://github.com/jiying2007/audio-pipeline/actions/runs/38997717739) exact `summary=success`, same-SHA [Release 38999746084](https://github.com/jiying2007/audio-pipeline/actions/runs/38999746084) `release+convergence=success`, verified four-member [Artifact 12087427801](https://github.com/jiying2007/audio-pipeline/actions/runs/38997717739/artifacts/12087427801).

## Root behavior and narrow mitigation / 根因边界与最小改动

B1-S0 previously encountered one documented race: upload completed but immediately following same-job pinned `actions/download-artifact` returned `Artifact not found` before its exact-run member-integrity gate could execute (#779 / PR #781). The B1-S1 job inherited the same *upload → immediate download* edge, although its previous runs passed; **this is a preventative, evidence-preserving CI resilience change, not evidence of a new B1-S1 failure**. The provider's internal replication mechanism is not independently proven.

- Reuse existing stdlib-only B1-S0 visibility probe with an **explicit two-prefix allowlist**: `frontend-fe09-t2b-b1s0-owner-spsc-<run-id>` and `frontend-fe09-t2b-b1s1-source-apx3-<run-id>`. Prefixes are fixed, not caller-specified arbitrary paths.
- The pinned B1-S1 upload step now exposes GitHub's immutable `artifact-id`. Check only that **exact ID**, name and `GITHUB_RUN_ID` on the read-only GitHub Actions REST endpoint. Require correct run, nonempty bounded bytes, unexpired ZIP and strict reported sha256 syntax.
- At most 8 attempts separated by at most 2 seconds. Retry only 404/502/503 API *visibility*, never unauthorized 401/403/429, network/TLS errors, redirects, malformed JSON, wrong artifact/source identity, expired or oversized payload. Exhaustion **fails the quality job**.
- **Always retain original pinned `actions/download-artifact` and separate `--verify` of real C-generated APX3/S2, full four members `SHA256SUMS/receipt.json/collect.log/verify.log`, source SHA, Native/sanitizer/ARM32-QEMU/TSan target, negative controls and B1-S1 non-product receipt. A visible Artifact is *not* an admission verdict or a substitute for integrity.
- Deterministic offline unit tests exercise both B1 names, temporary 404→success, unrelated source/run and metadata substitution, 404 exhaustion, 403 hard failure and retry cap. Existing B1-S0 behavior is preserved.

## Scope exclusions / 禁止扩大软件或产品准入

No changes to BF/NS/VAD/AGC/AEC, first-party B1-S0/S1/S2/S3 C/DSP or frozen I025–I040 lineage; shipping `src/`, installed `include/`, CMake, codec schema, pinned real speech, HIL, public SDK and 2.x tags are untouched. This does NOT admit durable APX3 persistence, physical Capture/Render clocks, 4-mic acoustic benefit, SSC305 complete 192 KiB budget/10ms p99/thermal or certification. It does NOT resolve T2 stale-tail liveness #766 or T3 resources #767.

## Completion policy / 完整门禁

A new independent Draft PR must pass latest exact-HEAD full Verify `summary=success` under strict protected Ruleset 21804005, zero unresolved review threads, expected-HEAD squash, a **distinct** pushed-main full Verify and same-SHA Release `release+convergence=success`, and a freshly downloaded/rehashed B1-S1 four-member run Artifact before #782 can close. No stale CI/PR evidence substitutes for postmerge gates.

**Allowed decision:** `FE09_B1S1_SAME_RUN_ARTIFACT_VISIBILITY_GUARD_ONLY_NO_ACOUSTIC_PROMOTION`.
