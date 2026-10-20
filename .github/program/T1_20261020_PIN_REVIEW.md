# T1 reviewed Actions proposal 2026-10-20

## Frozen defect and source

Base: e3672ffe16e4c9d42a100e7712b9bbd3d8338545.
Actual same-repository Dependabot PR #714:
5f7de70cfad0fb5fbf50d53c55d4431dc5c012c2.
The full Git-tree delta is 55 existing regular 100644 workflow files and
125 pin replacements: 123 upload-artifact, one CodeQL init, one CodeQL analyze.

The historical 108-pin witness and its CodeQL 4.38.3 target remain immutable.
They cannot authorize this later proposal. The new 55/125 witness is an
immutable observation of these exact Git objects, not a perpetual limit on the
number of upload sites in protected main. No range/wildcard Action pin is
admitted.

A second defect is the historical offline replay's dependency on today's
workflow pin state. A later correctly reviewed CodeQL target is neither the
historical old nor new target. The historical replay now constructs only its
explicit synthetic fixture from the unchanged frozen line pairs. It continues
to test the same 55/108 Git diff and adversarial cases; it never claims the
actual bot tree or current workflow logic was executed.

## Reviewed upstream identities and compatibility

- actions/upload-artifact v7.0.2 resolves directly to
  cf430e030ddbb5b0abf93d22962f4752f3646cd9.
  GitHub's commit verification is valid. The old-to-new comparison changes the
  bundled artifact dependency from 6.2.0 to 6.3.1 and matching distribution/lock
  metadata; it does not change action.yml or src/ upload input handling.
  Both endpoints use Node 24. Existing archive, retention, no-files and digest
  interfaces remain available.
- github/codeql-action v4.39.0 annotated tag object
  48870fdd6b42ee6474ec4207209ff87609271a5e resolves to
  6f2ac81f5cd81fe351a197ba0b00d91d03cd2aee.
  The tag is unsigned; the resolved GitHub merge commit is verified. This is
  resolved source provenance, not a claim of a signed release or independent
  supply-chain attestation.
- CodeQL 4.39.0 requires bundle >=2.20.7 and defaults to CLI/bundle 2.27.2.
  The local workflow uses c-cpp with manual CMake build, no custom tools bundle
  and the default workspace checkout; the new checkout_path validation matches
  this layout. Init and analyze both remain Node 24. Existing contents:read and
  security-events:write permissions are unchanged.

Primary sources:

- https://api.github.com/repos/actions/upload-artifact/git/ref/tags/v7.0.2
- https://api.github.com/repos/actions/upload-artifact/git/commits/cf430e030ddbb5b0abf93d22962f4752f3646cd9
- https://github.com/actions/upload-artifact/compare/043fb46d1a93c77aae656e7c1c64a875d1fc6a0a...cf430e030ddbb5b0abf93d22962f4752f3646cd9
- https://api.github.com/repos/github/codeql-action/git/tags/48870fdd6b42ee6474ec4207209ff87609271a5e
- https://api.github.com/repos/github/codeql-action/git/commits/6f2ac81f5cd81fe351a197ba0b00d91d03cd2aee
- https://github.com/github/codeql-action/blob/6f2ac81f5cd81fe351a197ba0b00d91d03cd2aee/CHANGELOG.md
- https://github.com/github/codeql-action/blob/6f2ac81f5cd81fe351a197ba0b00d91d03cd2aee/src/defaults.json

## Acceptance and rollout

T0 retains its historical default. The explicit 2026-10-20 review can accept
only the three fully enumerated source/target transitions. M1 loads the chosen
observation, its own qualifier and T0 classifier from an exact protected base,
requires the actual Git objects and full content digest, and reads live
main/bot metadata twice. Bot login, immutable user ID 49699333 and Bot type
must all match.

The new current-base contract explicitly replaces a constant-count admission
rule for this review. From the exact protected base tree, independently enumerate
every existing regular 100644 workflow's real step-level `uses` of the three
reviewed old pins. This defines the complete expected per-file action/old/new
list and its canonical SHA256. The actual bot Git diff must equal that entire
list. Omitting an old site, updating an unknown pin, adding a workflow/step,
editing source or changing permissions/modes still denies admission.

Thus a separately protected maintenance change may add a legitimate upload
site without making a historical 125-pin count into authority for future code.
The current expectation is freshly derived from that new protected Git tree;
the bot must rebase to it and the double live snapshot must remain stable.
The previous 55/125 source observation and the older 55/108 M0 witness remain
unchanged. Their fingerprints are reported separately from the current expected
fingerprint. Only the three exact reviewed transitions carry forward; any new
target SHA requires a new source review and protected policy change.

The new witness is source-review data. Before any PR research consumer may
use it, its code/witness must be independently protected-merged and the live
bot tree requalified from that base. Mixed source, unknown pin, permissions,
run/steps, fake YAML uses, mode, path, actor, fork and stale/racing ref changes
continue to deny maintenance admission. Old negative runs remain negative.

This stage does not install M2/M3 science consumers, skip measurements, push
branches or merge #714. Root must separately qualify the PR/push consumers,
rerun actual #714 Verify/CodeQL and artifact upload/readback at its final head,
then use strict expected-head protected merge and distinct main verification.
No workflow pin review is an acoustic score, product qualification, new release,
HIL result or proof that third-party code has no vulnerabilities.

中文边界：本阶段审查同一 bot 的新精确提案，不回写旧 108-pin 证据，不扩大 Actions
域名或目标 SHA。当前 125-pin 实际 Git 对象检查和上游来源审查不能替代托管运行、
artifact 下载散列复核、独立 M2/M3 消费者资格和合并后的 main 门禁。

## Operator sequence

1. Preserve the old failed #714 research runs. Protected-merge this independent
   source-qualification change through the existing exact-head Verify summary.
2. Verify the distinct new-main gates. Wait for Dependabot's actual same-repo
   proposal to rebase to that protected main; do not manufacture its branch.
3. From that exact clean protected checkout run
   `python3 .github/program/workflow_pin_only_actual_tree_t1m1.py --probe-real --review 2026-10-20`.
   Independently read the bounded JSON, exact base/head, complete Git diff and
   current expected fingerprint. Exit zero with NOT_ADMITTED is an observation,
   never a successful qualification. A candidate copy of this policy must emit
   `PR_SUPPLIED_TRUSTED_POLICY_DRIFT` until the policy is protected-main content.
4. Only then integrate and independently qualify the separate M2 PR consumer
   and M3 push consumer before adopting #714. If main or bot changes, redo the
   exact current-base proof. This source review does not grant a workflow skip.
