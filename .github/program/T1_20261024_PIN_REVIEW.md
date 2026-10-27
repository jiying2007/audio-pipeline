# T1 Actions source review — 2026-10-24 CodeQL 4.39.1

Status: `OFFICIAL_SOURCE_REVIEW_COMPLETE_PENDING_PROTECTED_SOURCE_AND_LIVE_GATES`.
The independent official-source and bundled-code review is complete. This
registers the exact new source transition for its separate protected review; it
does not qualify a live M1 proposal, connect another workflow consumer, or
replace any prior negative. The protected-core and hosted gates below remain.

## Observed cause and frozen inputs

- Integration checkout: `92a7546a75cfe0d8aca132c7ee5996dcf0005c74` (resource-only
  main; its distinct main Verify/Release is still running at registration).
- Actual reviewed proposal epoch B:
  `7138b17acd6246cc779efa7597d25771ddfc8c7a`.
- Actual Dependabot proposal H:
  `e2c8685fb8492c2ef724932abe6bc5553c9abb66`, sole parent B, tree
  `862f91b781fd4db779de4f4fff42049497d598d1`.
- Actual Dependabot recreation run: `40110453798`, attempt 1, success. The
  proposal has 56 modified existing workflows and 131 exact use-site pairs.
- The unchanged protected-B M1 ran at
  `2026-10-24T16:17:47.182362Z` through `16:17:48.505855Z` and returned
  `T1_ACTUAL_BOT_TREE_NOT_ADMITTED / BOT_ACTUAL_GIT_DIFF_NOT_PIN_ONLY`.
  Its original stdout SHA-256 is
  `bd05cc45a2a7749d024512fa37ac2fff349be6959bc10d8aaa13320a8ae95876`.
- All 129 upload-artifact replacements remain the independently reviewed
  `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` →
  `cf430e030ddbb5b0abf93d22962f4752f3646cd9` transition.
- The two CodeQL init/analyze replacements propose
  `9b3254085494b55a0f7c4c2b3d2d52cc712ce370`, while the immutable 2026-10-20
  review selects `6f2ac81f5cd81fe351a197ba0b00d91d03cd2aee`. Both replace
  the existing `2892aa5e19bbd11bc0cff5427e3b750a04d9e3c2` base pin.

The rejection is correct. A later official target requires its own source
review, exact transition identity and protected qualification. A matching edit
count cannot authorize an unreviewed target.

## Proposed independent review and permitted implementation

The proposed selector is `2026-10-24`; the identity is
`T1_PIN_REVIEW_20261024_CODEQL_4391`. Historical T0 and the explicit 2026-10-20
selector, witness bytes, results and failure records remain independently
addressable. This proposal must not widen either older selector.

Before implementing the new selector, independently establish:

1. Official repository, actual commit, tag/release correspondence and the actual
   provider-reported signature status for each object, using full OIDs.
2. Complete `6f2ac81...9b325408` Git delta and object identities, including
   `init/action.yml`, `analyze/action.yml`, shared bundled entry points,
   defaults, package/lock files and every changed runtime source file.
3. Runtime, input, token/authentication, network/upload, cache/cleanup and
   default-behavior effects against this repository's exact CodeQL call sites.
   A release-note summary alone is insufficient. Published bundle/source
   inspection does not constitute an independent reproducible-build claim.
4. No change to the existing repository workflow permissions, triggers,
   commands, corpus, science, timeout or dependency-update source identity.
   The source-review PR changes no `.github/workflows/*.yml` Action pins.

The permitted source-only implementation is one causal policy extension:

- Add the new exact three-entry selector and a new complete actual-proposal
  witness. Retain both old selector maps and both old witnesses.
- Select the new review in protected M1 and its documentation gate. Preserve
  every actor/ref/tree/mode/diff/current-base/race check and all existing bounds.
- Preserve the existing M2 consumer source; it reads the protected M1's current
  selector and remains responsible for a fresh live M1 result.
- Refresh the dormant dEchorate source-only M2 closure to the new four-file
  protected core. Keep the old closure as historical evidence, bind the new
  core's real commit, and retain all original science blobs and all existing
  exact workflow templates. This is necessary because changing the core while
  retaining its former hashes would leave the closure false.
- Record the official-source review in a small new machine-readable review
  record. No downloaded upstream code is executed or vendored into the project.

Expected paths are the two new review records/witness, this document,
`workflow_pin_only_scope.py`, `workflow_pin_only_actual_tree_t1m1.py`, the
existing dormant `dechorate_event_source_t1m3.py` and its plan/test, and
`.github/scripts/verify-docs-gate.sh`. Any added path needs a causal explanation.

## Completed official-source review

The independently retained full review has SHA-256
`a28c96c119740e051a43f2495693bf0b4fbcb48218cd4279f395da64a1b7e938`;
its Chinese analysis has SHA-256
`1651598a34b0f5431fc2bd99e6c166bc3743faf7dead07eacd1fecedbca2ddc4`.
The root reviewer also rechecked all 279 original Git blobs (17,939,287 bytes),
the complete 64-file diff, the package/lock comparison, the unchanged analyze
metadata and every retained evidence hash without executing upstream code.
The small machine record is `codeql_action_4391_review_20261024.json`.

- [Official v4.39.1 commit](https://github.com/github/codeql-action/commit/9b3254085494b55a0f7c4c2b3d2d52cc712ce370):
  GitHub reports commit signature `verified=true / valid`. Its annotated tag
  `8498dc4c2b27cdd99baf0f87955b29ebbf30c78d` is **unsigned**. Those are different
  objects; no independent GPG trust verification is claimed.
- [Official release](https://github.com/github/codeql-action/releases/tag/v4.39.1):
  release419751066, immutable, published `2026-10-21T15:48:42Z`.
- [Complete source delta](https://github.com/github/codeql-action/compare/6f2ac81f5cd81fe351a197ba0b00d91d03cd2aee...9b3254085494b55a0f7c4c2b3d2d52cc712ce370):
  62 ancestry commits / 64 changed files. Both actions still use Node24;
  analyze/action.yml is byte-identical and init only changes TRAP documentation.
  Package and lock dependencies, URLs and integrity remain unchanged; only their
  own 4.39.0→4.39.1 fields change. All 54 bundle hunks were inspected; the four
  dependency hunks rename a generated symbol, and the others match first-party
  runtime source. This is static inspection, not a rebuilt-bundle attestation.

The relevant runtime differences are explicitly part of this review:

| Area | Actual behavior and current caller implication |
| --- | --- |
| Authentication | An internal explicit empty external token suppresses fallback authentication. The unchanged optional-input helper normalizes the current caller's unset/empty/whitespace input to undefined, preserving its path. Database uploads now use the same explicit API-details object for URL and token. |
| Toolcache | The earlier cleanup feature gate is removed. Eligible first setup/download on GitHub-hosted runners can delete unused CodeQL bundles on the shared filesystem; existing directory and symlink guards remain. Actual cache/download failures still count as failures. |
| TRAP / overlay | Overlay analysis now disables TRAP caching by default without the earlier feature gate. Explicit input remains authoritative. |
| SARIF | Failed-SARIF generation, test-mode controls, configuration propagation and artifact roots change. The actual caller sets none of the test/skip controls. Successful analysis, upload/processing and post steps must be observed in the real hosted job. |
| CodeQL CLI | Published defaults move 2.27.2→2.27.3. Existing feature flags or tool selection can choose the actual CLI; preserve the version that the real job used. |

The exact current caller still has only `contents: read` and
`security-events: write`, `languages: c-cpp`, `build-mode: manual`, and its
unchanged CMake build. No blocking source incompatibility was found for this
caller. Existing database upload capability is not new, and a green job alone
does not prove its optional warning-only upload path succeeded. Source review
does not substitute for the final actual CodeQL regression or repository gates.

## Real core source identity

The independently reviewed first-stage core is the real repository commit
`74ac99649916f441d3674602fb4a8aff5c79da00`, tree
`2655ba19ec43ed89a98a3a9d418cca6585374ad5`, sole parent
`92a7546a75cfe0d8aca132c7ee5996dcf0005c74`. The remote Git objects and all
five reviewed file blobs were read back exactly. This is a source commit on the
review branch, not a protected-main or hosted qualification.

The dormant dEchorate contract now records that commit's exact four-file M2/M1
closure, including the unchanged M2 consumer and the new 2026-10-24 witness.
Its former complete registration is retained under
`historical_m2_source_closures`; it grants no current authority. Both prerequisite
observation flags remain false. The six original/upload-only workflow templates
retain their existing bytes and names: their `reviewed-2026-10-20-pins` suffix
identifies the unchanged upload transition, not the current CodeQL selector.

## Qualification and failure preservation

The targeted source suite must demonstrate all of the following before a PR:

- Both older selectors retain exactly their original mappings; the old
  2026-10-20 selector still rejects the actual new H and its two new CodeQL pins.
- The new selector recognizes only the exact reviewed targets and independently
  derives a complete expected matrix from each actual protected base. The
  observed 56/131 pair count is historical input, never a future constant.
- Real Git controls reject an incomplete update, wrong or floating target,
  earlier-review target under the new selector, mixed command/permission edit,
  changed mode/path, misleading YAML scalar and changed actor/ref/OID.
- Both earlier witness digests remain valid under their own selectors. A
  witness mixed across reviews fails closed.
- The dormant dEchorate closure admits only the newly registered four-file
  identities; the former or mixed core cannot be presented as the new closure.
- Original scientific blobs, authority fields, seven diagnostic science steps,
  six original/upload-only templates, ruleset semantics, network/time/output
  bounds, release identity and SDK/HIL boundaries remain unchanged.

Run only the relevant existing T0/M1/M2, dEchorate source and docs-gate suites,
plus the precise new cross-review controls. Then consume the existing exact-head
Verify gates. A source PR can print a real safe-negative M1 observation because
its candidate policy is not yet protected; that is not a live positive.

After expected-head protected squash, independently close that new main's
Verify and matching Release/convergence. Request a real Dependabot recreation
onto that protected main using a standalone command, retain the original bot
history, and run the unchanged protected CLI with the new explicit selector.
Only a real current B/H positive permits the still-separate consumer hookup.
Subsequent main changes require new current-base qualification at their proper
stage. Do not manufacture a Dependabot branch or reuse an obsolete base result.

All decisions remain nonmeasurement. An exact pin classification is not an
Action-security attestation, acoustic pass, release, hardware result or shipping
authorization. Existing E001 and I025–I040 records remain unchanged.
