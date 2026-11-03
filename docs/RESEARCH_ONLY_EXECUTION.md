# Technical-research execution boundary

**Status: research-only target, migration in progress.** See [issue #882](https://github.com/jiying2007/audio-pipeline/issues/882) for the live dependency audit and retirement checklist. This document deliberately does not claim that historical certification and commercial publication entrypoints have all been removed.

## Active research authority

The subject of this repository is reproducible low-resource speech DSP and audio front-end engineering: BF (1/2/4 microphones), AEC, RES, NS, AGC, VAD, transport/runtime timing, fixed-memory pipelines, acoustic regressions and ARM/SSC305-class resource experiments. Research runs are admitted by recorded sources/rights, roles and immutable measurements, not by sales readiness, shipping SKU approval, a GitHub Release, product certification or a 72-hour physical board soak.

The normal PR/main `Verify` gate is for code correctness, sanitizers, resource/performance diagnostics, cross-architecture build portability, reproducibility and validation. It must not execute or require `certification/` policy assertions, commercial signing credentials, `shipping_approved` or a release/tag prerequisite. `tests/test_research_ci_boundary.py` checks this contract on each docs gate. This is a *necessary first step*, not sufficient evidence that all obsolete launch surfaces are retired.

## Evidence that remains valuable

- Preserve existing immutable scientific results, regression replay, data rights and source/hash receipts; never manufacture or silently upgrade real-person, final AFE, hardware, thermal or power evidence.
- Keep experimental SSC305-style build and CPU/RSS/latency/energy measurements as research resource profiles. QEMU/host estimates must be distinguished from physical DUT data.
- Maintain blind and independent evaluation roles and truthful NOT_RUN/FAIL signals. An empty or skipped target experiment must never be recast as PASS.
- Historical `release.yml` and `post-release-qualification-summary.yml` have been retired from the active workflow directory in this change. Their source and previous results remain available in Git history and GitHub Actions history. `certification/` and `product-certification.yml` remain legacy qualification paths awaiting separate dependency-checked migration under #882, never as research-admission authority. No historical audit payload is rewritten.

## Pending cleanup, not claimed complete

Source-root product certificates, VAD shipping-policy naming, lab and SKU-specific tools, other EN/ZH guides, test helpers and archived product-doc terminology still need separate atomic migration. Remove consumers before deleting their old files, preserve applicable third-party licenses (including noncommercial conditions), and verify exact-head CI plus fresh protected main. Retain Python 3.8 compatibility where used.
