# T1-M1: read-only GitHub bot-tree classification / 真实 Git 对象准入预检

**Research CI governance only. No product, DSP, science or release authority.**

Independent preregistration: [#748](https://github.com/jiying2007/audio-pipeline/issues/748), parent [#746](https://github.com/jiying2007/audio-pipeline/issues/746). First eligible main: `e30c1e5e0619f02554077ed81dac312245aa4a31` after #747, fresh-main Verify `38520308205` 64 success + 1 expected skip and exact-SHA Release `38523634207` 2/2 success.

## Trust boundary / 信任边界

The only executable Python logic comes from this independently reviewed PR and the **unchanged protected-main** `.github/program/workflow_pin_only_scope.py` (T0 classifier). The bot PR is untrusted **data**, never checked out, sourced, imported or used as a workflow/action definition. The program uses a canonical, hardcoded same-repo HTTPS URL and read-only public GitHub REST metadata, and fetches immutable Git object IDs without changing any remote ref, default action permissions, workflow structure or release path.

For #714, verify the actual open GitHub PR author `dependabot[bot]`, `main` base, same-repository bot head branch, exact full 40-hex base/head, canonical `ls-remote` heads, current protected main and an intact trusted T0 classifier. A PR source mismatch, stale main/head, fork, unexpected actor or unknown/refused Git object returns **NOT_ADMITTED**.

Only when live base/head refs match current protected main, fetch exact Git objects as data and invoke unchanged trusted T0 `classify_repo(base,head)`. Derive a **canonical ordered per-workflow SHA256 content-diff fingerprint** from the original immutable, protected-main M0 55-workflow/108-pin witness, then require the *actual* bot Git object's T0 fingerprint to match it exactly. This permits **content-identical** Dependabot rebases without trusting a stale OID: all path names, changed Actions identities and old/new SHA pins must remain identical. T0 independently rejects file modes/symlinks, unknown Actions/pins, YAML fake `uses:`, changed permissions, mixed source/science edits, extra files and ancestry drift. Re-read both bot PR metadata and real branch refs after classification to detect in-flight rebase. A passing classification is **non-measurement dependency maintenance only**, not a supply-chain attestation or an automatic science waiver.

## Current known negative (expected)

At registration, protected main `e30c1e5e0619f02554077ed81dac312245aa4a31` and #714 base `626fd6a9d29ad5d5f61bc4b643c983f9546327d1` diverged; the live probe **correctly rejected** the stale base. After protected #753 landed, main is `41b626f9018e99bcd9b4769f60511b2d1f898f5f` and Dependabot #714 rebased to current base with bot HEAD `bd69c86b727dafdceee194f6fa6094529b6b56d6`. A review of its real GitHub diff found **the same 55 workflow paths / 108 SHA-only changes**. M1 now compares its actual T0 canonical diff digest to the independently frozen protected-main M0 **content** witness, while binding and double-checking the **new exact Git commit IDs** and ref identity. Any different path, pin pair, count, permissions/logic change, stale or changed source ref, or missing/unknown Git object remains **NOT_ADMITTED**. When this PR itself merges, the bot may rebase again; old positive receipts are not automatically authority for that newer main. Future M2/M3 require another exact-current-source readback.

## Execution & evidence / 执行和证据

- `python3 .github/program/workflow_pin_only_actual_tree_t1m1.py --self-test`: offline validation of bot identity/race/sha rejection and real local Git mode-change negative. Required via the **existing** Docs/Verify gate.
- `python3 .github/program/workflow_pin_only_actual_tree_t1m1.py --probe-real`: read-only live GitHub PR + main/bot SHA source test. The existing gate only calls this when the M1 qualifier file itself changes in a pull request, avoiding a new permanent external dependency for unrelated CI. A legitimate rejection emits a structured **nonadmitted receipt** with an exit code of zero because this probe is **observational**, not a scientific validation gate. Missing network/source also means **no authority**.
- Offline tests run without web, paid resources or sound data. Existing Verify must still achieve full required `summary=success`, followed by protected expected-HEAD squash and **distinct** fresh-main Verify + matching Release. There is no automatic artifact collector or unattended approval here.

The only future positive M1 observation is `T1_ACTUAL_BOT_TREE_CLASSIFIED_NON_MEASUREMENT_ONLY_NO_WORKFLOW_SKIP`, with actual Git base/head/tree digests, diff SHA, current-main source anchors and immutable T0 blob. **This DOES NOT authorize consuming the result from the three PR scientific-scope workflows**, or skipping dEchorate's separate push research gate (M2/M3 independent registration and tests).

**Fail closed:** `T1_ACTUAL_BOT_TREE_NOT_ADMITTED`. Original failed AEC/dEchorate/PCR02 checks for #714 remain failed; #714 must not merge on M1 alone. `src/`, `include/`, CMake, 2.x/3.x SDK, frozen I025–I040, ADC clock, SSC305 HIL, BF/AEC benefit and product release all remain untouched.

## Later reviewed proposal

The historical M1/55-workflow/108-pin contract above remains its original
evidence identity. [The 2026-10-20 source review](T1_20261020_PIN_REVIEW.md)
adds a separately selected exact pin policy and a complete current protected-base
transition. Its 55/125 observation is not a permanent count or permission for
future candidate code. Use the explicit `--review 2026-10-20` probe only after
that policy is independently protected-main content.
