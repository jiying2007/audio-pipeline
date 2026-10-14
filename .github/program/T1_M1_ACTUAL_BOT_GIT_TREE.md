# T1-M1: read-only GitHub bot-tree classification / 真实 Git 对象准入预检

**Research CI governance only. No product, DSP, science or release authority.**

Independent preregistration: [#748](https://github.com/jiying2007/audio-pipeline/issues/748), parent [#746](https://github.com/jiying2007/audio-pipeline/issues/746). First eligible main: `e30c1e5e0619f02554077ed81dac312245aa4a31` after #747, fresh-main Verify `38520308205` 64 success + 1 expected skip and exact-SHA Release `38523634207` 2/2 success.

## Trust boundary / 信任边界

The only executable Python logic comes from this independently reviewed PR and the **unchanged protected-main** `.github/program/workflow_pin_only_scope.py` (T0 classifier). The bot PR is untrusted **data**, never checked out, sourced, imported or used as a workflow/action definition. The program uses a canonical, hardcoded same-repo HTTPS URL and read-only public GitHub REST metadata, and fetches immutable Git object IDs without changing any remote ref, default action permissions, workflow structure or release path.

For #714, verify the actual open GitHub PR author `dependabot[bot]`, `main` base, same-repository bot head branch, exact full 40-hex base/head, canonical `ls-remote` heads, current protected main and an intact trusted T0 classifier. A PR source mismatch, stale main/head, fork, unexpected actor or unknown/refused Git object returns **NOT_ADMITTED**.

Only when both refs and frozen #714 witness are unchanged, fetch exact Git objects as data and invoke unchanged T0 `classify_repo(base,head)`. That independently rejects file modes/symlinks, unknown actions/pins, YAML fake `uses:`, mixed source/science edits, extra files, malformed revisions and base/head ancestry drift. Re-read both bot PR metadata and real branch refs after classification to catch in-flight rebase. A passing classification is **non-measurement dependency maintenance only**, not a supply-chain attestation or an automatic science waiver.

## Current known negative (expected)

At registration, new protected main is `e30c1e5e0619f02554077ed81dac312245aa4a31`, while #714's GitHub PR reports `base.sha=626fd6a9d29ad5d5f61bc4b643c983f9546327d1` and head `3e29c6cc81000741844ecc47962ba43e18e7e502`. That bot pair is 55 workflow files / 108 reviewed Action SHA replacement lines, but it **diverged from the current main**, so live probe must report `BOT_BASE_NOT_CURRENT_MAIN`; do not promote a cached green old-source result. Following bot rebase, the frozen M0 witness SHA/count may change and **must be independently refreshed/qualified** before any M1 positive authority.

## Execution & evidence / 执行和证据

- `python3 .github/program/workflow_pin_only_actual_tree_t1m1.py --self-test`: offline validation of bot identity/race/sha rejection and real local Git mode-change negative. Required via the **existing** Docs/Verify gate.
- `python3 .github/program/workflow_pin_only_actual_tree_t1m1.py --probe-real`: read-only live GitHub PR + main/bot SHA source test. The existing gate only calls this when the M1 qualifier file itself changes in a pull request, avoiding a new permanent external dependency for unrelated CI. A legitimate rejection emits a structured **nonadmitted receipt** with an exit code of zero because this probe is **observational**, not a scientific validation gate. Missing network/source also means **no authority**.
- Offline tests run without web, paid resources or sound data. Existing Verify must still achieve full required `summary=success`, followed by protected expected-HEAD squash and **distinct** fresh-main Verify + matching Release. There is no automatic artifact collector or unattended approval here.

The only future positive M1 observation is `T1_ACTUAL_BOT_TREE_CLASSIFIED_NON_MEASUREMENT_ONLY_NO_WORKFLOW_SKIP`, with actual Git base/head/tree digests, diff SHA, current-main source anchors and immutable T0 blob. **This DOES NOT authorize consuming the result from the three PR scientific-scope workflows**, or skipping dEchorate's separate push research gate (M2/M3 independent registration and tests).

**Fail closed:** `T1_ACTUAL_BOT_TREE_NOT_ADMITTED`. Original failed AEC/dEchorate/PCR02 checks for #714 remain failed; #714 must not merge on M1 alone. `src/`, `include/`, CMake, 2.x/3.x SDK, frozen I025–I040, ADC clock, SSC305 HIL, BF/AEC benefit and product release all remain untouched.
