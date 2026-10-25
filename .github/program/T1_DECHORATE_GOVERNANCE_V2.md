# dEchorate governance transport v2 — source-only qualification

## Frozen replacement plan, 2026-10-24

Identity: `DECHORATE_GOVERNANCE_TRANSPORT_V2_F0`.
Base: `5187c5e59526d4047b3965b44c770ab21edbde9f`.

This is the candidate's planning and offline-fixture base, not a fixed runtime
D or B. Rebasing the source-only change over a separate evidence-index update
does not expand this scope: hosted execution still binds the actual full Git
source commit and checks the same complete dependency and science closure.

The old #833 source failure is preserved: run 40013222347, attempt 1, artifact
12526094926, reason `MAIN_RULESET_IDENTITY_OR_BYPASS_DRIFT`. Anonymous GitHub
ruleset responses omit `bypass_actors`; the authenticated connector and the
existing Release governance credential can observe its explicit empty array.
Missing is not empty. The original strict ruleset validator is not relaxed.

The earlier unpublished local candidate (reported as 89b3f7d9 and 23 offline
rejections) could not be recovered. Its code and execution are not borrowed as
evidence for this replacement. An initial PR-only design was reviewed, then
expanded **before implementation or measurements** to cover the same measured
main-push defect. Neither design permits M3 maintenance skipping.

The finite change is nine files: this note, the v2 plan, v2 transport helper and
tests, one protected-main producer workflow, the canonical docs-gate invocation,
and the existing source helper/contract/test solely to register the complete
new consumer template. The scientific workflow itself is unchanged in this
source-only PR. All existing science files, seven original steps, source
inventories, thresholds and historical failures remain immutable.

## Source dependency re-registration, 2026-10-24

The reviewed source-only candidate
`8cd2b425fbf283b6f4ce67470901dde3700adaa0` predates the separately reviewed
2026-10-24 pin policy. This re-registration integrates its same nine-file
protocol into reviewed C2 `cf94cae9d6e36fa536f6b6d4398c916703130186` and retains
the original planning/offline-fixture base above as historical context. Runtime
D and B still come from the actual protected event, not either planning commit.

The current four-file M2 source registration remains bound to real core commit
`74ac99649916f441d3674602fb4a8aff5c79da00` and review `2026-10-24`. Its complete
2026-10-20 predecessor stays in the legacy contract's historical registration;
neither it nor mixed old core blobs qualify as current source. The v2 closure
uses `workflow_pin_only_bot714_20261024.json` and freezes all seven existing
dependency hashes from the integrated source. The transport changes only that
witness path; producer permissions, PRE/POST authority, PR/push attempt budgets,
seven science steps, six legacy templates and both v2 templates are unchanged.

The legacy suite retains the six C2 old-registration/core refusals and all
original v2 template controls. The transport suite additionally checks that
the prior witness-path registration and each changed old core digest cannot
authorize the current exact source checkout. These are offline engineering
fixtures; no fresh bot M1, hosted consumer or scientific result is claimed.

Publishing this source-only update still requires #846's own protected-main
Verify/Release closure and a fresh final integration base. The separate #833
workflow hookup still requires current protected M1 qualification and its own
measured protocol. The original pending decision and false authority flags
below remain unchanged.

## Two independent, finite executions

Each exact consumer run has attempts **1 and 2 only**. PR and measured push have
separate budgets. No third attempt, implicit retry, arbitrary PR or dispatch
consumer is admitted. The canonical PR is #833.

1. Consumer attempt 1 executes protected-base source code, checks actual event
   Git ancestry/range and frozen science, and writes an immutable challenge from
   its real event and environment. It binds B/H/event-merge/run/attempt, source
   closure and public observations, then fails with `PENDING_AUTHENTICATED_PRE`.
   The old negative receipt, mutable `run.pull_requests[]`, and current PR base
   cannot substitute for this challenge.
2. The default-branch producer is triggered by that exact workflow completion.
   A read-only preflight checks repository IDs, workflow path and ID, target
   run/attempt, challenge provenance, live refs, source closure and Git objects
   **before** the authenticated acquisition step. It checks out only its own
   trusted D, never PR code. The governance secret exists only in acquisition.
3. PRE reuses `scripts/github_governance.py` and the original strict source
   ruleset validator. Successful evidence contains an explicitly empty bypass
   array. A nonempty or unreadable list yields a refusal; private actor identities
   are never uploaded. A nonempty-list refusal retains only the public ruleset
   ID, actor count, redacted status and hash of that public refusal projection.
   It publishes no actor-specific digest that could expose a small candidate
   list through guessing. PRE targets the same run's attempt 2.
4. Attempt 2 must begin after the real PRE producer completed successfully. It
   checks actual producer API run/job/artifact/source identity, downloads and
   rehashes the ZIP, rechecks the public projection, and executes the unchanged
   seven scientific steps. Its source receipt remains pending independent POST.
5. Completion triggers POST. The final verifier independently acquires both
   producer artifacts and both consumer attempts and checks the complete chain.
   No JSON self-description or standalone hash proves authenticated acquisition.

For PR, D = B = live main, H is the same-repository #833 head, and the real
synthetic merge has ordered parents B/H and the H tree. For measured push,
D = H = event.after = live main; the sole parent is event.before B, the unique
associated merged PR is #833, and its head tree equals H. The consumer executes
from B; all protocol source dependencies must be byte-identical at B and D.
Only the registered dEchorate workflow transition may differ. Push attempt 2
still runs the original corpus. This is not maintenance push admission.

## Source and evidence authority

Every executed dependency is bound by ordinary Git mode, blob, byte length and
SHA256 at the exact source commit. The plan contains fixed existing dependency
hashes; new source/plan/workflow files bind to exact Git D without a circular
self-hash. The four existing M2 dependencies remain part of the closure.

`github_governance.fetch_live()` returns parsed objects. Their hashes are named
`canonical_json_sha256`, not original HTTP-body hashes. Canonical main and tag
ruleset objects are retained only after explicit empty bypass validation.
Authenticated PRE/POST demonstrate two recorded observations, not continuous
monitoring of every intervening instant. Public projection and timestamp
equality detect observed changes; the final artifact chain supplies provenance.

Actual run/job/attempt/head/workflow identity and completed step status are
independently checked. Local acquisition timestamps must lie inside the actual
acquisition step's interval. API timestamps retain their original offset and
precision; a second-resolution completion represents that whole second for
interval membership. PRE-to-consumer and consumer-to-POST order must be
unambiguous across those intervals. Overlapping displayed timestamps remain
unqualified, without enlarging the attempt or download budgets.
`created_at` is retained as API identity metadata, without assuming it precedes
`run_started_at`: a real attempt-2 response can be created later. A copied
previously successful job with old start/completion times cannot substitute for
the actual failed diagnostic job's execution in attempt 2.

The producer has only read permissions and no production secrets other than the
existing governance credential in its acquisition step. It has no PR-head
checkout, PR-head imports, shell input interpolation, release operation, ref
mutation, `pull_request_target`, or measurement skip. It preserves failures
without printing credentials, environment dumps, private bypass actors or
temporary download URLs.

Source-protocol success remains
`DECHORATE_GOVERNANCE_PROTOCOL_VERIFIED_NO_PRODUCTION_ADMISSION`.
`production_admission_enabled`, `scientific_experiment_executed`, `acoustic_pass`,
`skip_measurement`, `maintenance_push_admitted` and `shipping_authority` remain
false in protocol receipts. Source permission before measurement is explicitly
pending POST. Scientific results and M1/M2/M3 closure retain their separate
existing gates. The source-only PR and subsequent #833 integration each require
their own exact-head Verify, protected merge and distinct main verification.

## Verification

The offline suite uses explicit metadata/ZIP fixtures and real local Git source
objects. It checks nonvacuous PR and push paths, missing/nonempty bypass,
event/attempt/source/producer/artifact drift, malformed archives, old-receipt
replay, premature attempt 2, credential isolation and failure preservation.
Offline fixtures are not live acquisition, hosted qualification or science.

```sh
python3 .github/program/test_dechorate_governance_v2.py
python3 .github/program/dechorate_governance_v2.py verify --consumer-run-id RUN --output NEW.json
```

The verifier requires actual GitHub read access and original artifacts. Its CLI
does not accept arbitrary local JSON as live evidence. Original external/HIL,
E001, public ABI and I025–I040 authorities are unchanged.

References:

- https://github.com/jiying2007/audio-pipeline/issues/759
- https://github.com/jiying2007/audio-pipeline/pull/833
- https://docs.github.com/en/rest/repos/rules#get-a-repository-ruleset
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run
