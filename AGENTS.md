# audio-pipeline agent execution contract

[简体中文](AGENTS.zh-CN.md)

The repository is currently in a **software-commercial-ready maintenance state**. The software/public-data program has no READY task; E001 remains external/deferred and the remaining Product Qualification work is real-lab/physical evidence tracked by the live external-evidence issue/tracker.

Before acting, re-read live `main`, open PRs/issues and current GitHub checks/artifacts. Do not infer current state from chat history. Start from `docs/README.zh-CN.md` for the Chinese operator map or the task-specific canonical documents (`docs/ARCHITECTURE.md`, `docs/DEVELOPMENT.md`, `validation/authority.json`, `docs/PRODUCT_ASSURANCE.md`, `docs/TRUSTED_RUNNERS.md`). Read `docs/program/*` when historical software-research evidence is actually relevant; it is no longer the default source of a new task.

Do not create software work merely to make the repository look more complete. Open a change only for a concrete defect, regression, integration requirement, measured resource/performance issue, documentation/contract drift, or a verified failure exposed when real external infrastructure is brought online. If the only missing evidence is physical, preserve the external/deferred truth and stop changing software.

For a software or algorithm change, freeze the exact base, hypothesis/root cause, measurement contract, acceptance rules, budgets and data roles before search. Work on one causal change at a time. A measurement change and a shipping algorithm change must not approve each other in one experiment. Never change acceptance thresholds, timeouts or evidence requirements merely to obtain green CI. Preserve failures.

Use the canonical validation authority. Development/search data may select candidates; validation-grade and blind data must not feed optimizer selection. A candidate is not shipping authority. Hosted CI, QEMU and public data are not real-SKU performance, HIL, thermal/power or Product Certification evidence.

Implement the smallest justified change, run targeted/self/negative tests, then consume the existing exact-head gates. Only merge after the live expected head/base and all required applicable checks, including required `summary`, are independently verified. If HEAD moves, earlier CI is stale. Reverify exact `main` after protected squash merge.

Release only through the governed release chain when release-bearing. Release-neutral maintenance must not manufacture a new version. Clean branches only after evidence preservation and exact-live-SHA/no-open-PR checks; use the existing fail-closed lifecycle workflows. Never directly push main, force-update tags or delete unclassified refs.

Documentation is part of the commercial integration surface. Changes to API/lifecycle, product presets, ownership/data flow, validation authority, Release/Certification behavior, diagnostics/privacy or operator commands must check the critical Chinese entry layer under `docs/*.zh-CN.md` as applicable. Low-level machine schemas and explicitly canonical specifications remain the single source of truth.

Never mock or synthesize runner availability, DUT routes, sensors, licensed/real corpora, shipping toolchain identity, soak duration, archive receipts, HIL/PQ results or Product Certification evidence. E001 readiness is infrastructure readiness only. The real product path remains: trusted runners -> real Extended Real/HIL -> E001 activation -> HIL history -> >=72 h Product Certification -> immutable product-lifecycle receipt.

When main gates are green, no software task/PR is open, and only real external evidence remains, stop generating software changes until a new verified input or failure exists.
