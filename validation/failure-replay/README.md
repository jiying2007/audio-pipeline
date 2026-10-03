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

## Multiple public-family evidence

A blocker may be closed for a narrowly identified sub-signature without closing it for every failure in the bank. The current second-family SLR31 review closes the multiple-public-dataset repetition prerequisite only for `FR-S003-MIC-GAIN-DELAY-MISMATCH-V1` → `severe-near-reference-degradation`. Capture clipping did not reproduce that sub-signature on SLR31 and remains independently blocked. This evidence never grants root-cause, candidate, release, HIL, or product-certification authority.

## Measurement-domain oracle review

For a candidate-relevant sub-signature, measurement-domain exclusion must be based on source/reference controls that do not depend on the same output-vs-input delta that raised the diagnostic. The mic gain/delay mismatch line now has a reviewed SLR31 source-domain oracle: both fresh seeds pass 8/8 fixed utterances using absolute clipping, component SNR, correlation, lag and gain controls with no pipeline output. This closes only the measurement-domain blocker for that narrow sub-signature; it does not identify a DSP root cause or grant S004 authority.

## Downstream-transfer exclusion

A stage-prefix review may prove that later stages are not necessary for a diagnostic symptom to appear. This is weaker than a root-cause claim. For the mic-gain/delay-mismatch severe sub-signature, observation at an HPF-only capture prefix excludes BF, NS, AGC, VAD and final/full-pipeline transfer as necessary causes of appearance, while HPF causality remains unproven. Such evidence can close the downstream-transfer blocker without granting candidate authority.

## Metric/reference-domain rejection

Source-domain validity is necessary but not sufficient when a diagnostic metric compares outputs after an intentional stage transform against a raw reference. The mic gain/delay mismatch line is a concrete example: the raw-clean SI-SDR improvement watch remained severe at an HPF-only prefix, but the severe score disappeared when the clean reference was passed through the same HPF; changing only the right mismatch channel had no bitwise effect at that prefix. The candidate line is therefore terminally rejected as a metric/reference-target artifact. Historical replay evidence remains reproducible, but it no longer grants a path toward S004 candidate design.


## Supplemental mechanism-signature replays

Some durable diagnostic signatures do not share the same source generator or
stage-attribution authority as the core replay entries. They are registered in
`catalog.json -> supplemental_replays` and validated by dedicated replay
workflows while remaining under the same replay-only authority boundary.

The first supplemental replay,
`SR-S003-AEC-ECHO-PATH-GEOMETRY-V1`, captures the terminal AEC echo-path
diagnostic mechanism at stage AEC: deterministic seeds reproduce the current
100w-50s recovery timing and a physically admissible `G=R/M` freeze returns
recovery to 0 ms. It exists to detect shipping drift and trigger explicit
lifecycle review. It does not reopen the retired internal mechanism search,
grant release acceptance, or authorize a candidate.
