# Failure Replay Bank

This directory is the durable, reviewable replay registry for failures and
diagnostic degradations discovered by system-robustness work. Generated PCM and
run artifacts are evidence products; the permanent source of truth is the small
committed replay contract plus deterministic generator identity.

## What an entry binds

Each replay entry binds:
- source/corpus/case identity and deterministic seeds;
- original reviewed workflow/artifact identity and SHA-256;
- expected replay-only diagnostic signature;
- first observable stage (or `null` when not proven);
- lifecycle state;
- regression assertion;
- explicit S004 blockers and authority boundaries.

The first-observable stage is not automatically a causal root cause. Release
policy PASS and a replay-only diagnostic degradation are intentionally separate.

## Lifecycle

- `OPEN_DIAGNOSTIC`: CI must reproduce the frozen signature on all registered
  seeds. If it disappears or changes, the entry must be explicitly reviewed;
  it is not silently deleted.
- `FIXED_REGRESSION`: historical evidence remains immutable and the entry
  changes to a "must not recur" assertion.

The Actions artifact referenced by an entry may expire. That does not erase the
failure: CI regenerates the case from committed generators and checks it against
the durable entry.

Current catalog: [`catalog.json`](catalog.json).

No replay entry grants S004 candidate authority, release acceptance authority,
HIL authority, or product certification.

## Public cross-source review

A durable replay may reproduce exactly on its deterministic synthetic seeds yet transfer only partially to a public source family. Such evidence is stored as a supplemental review, not by rewriting the original replay truth. A stable sub-signature does not make the broader composite signature cross-source. Raw-prefix checks are sanity evidence only when the watched metric is itself an input-to-output delta; they do not independently prove measurement-domain validity. S004 remains closed until all explicit blockers are independently satisfied.
