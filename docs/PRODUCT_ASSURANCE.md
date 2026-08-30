# Product Assurance Closure

This document defines the current repository/product assurance boundary. It does not expand DSP architecture and never treats hosted CI as product evidence.

## Software release gate

A software release requires all of the following:

- the exact `main` SHA passed required `Verify/summary`;
- the release SHA is attributable to a merged pull request targeting `main`;
- live repository governance passes `scripts/github_governance.py` using the read-only administration credential supplied as `REPOSITORY_GOVERNANCE_TOKEN`;
- the active main Ruleset requires pull requests, squash-only merging, resolved review conversations and strict `summary` from the GitHub Actions App, blocks deletion/non-fast-forward updates and has no bypass actors;
- the active `v*` tag Ruleset blocks deletion/non-fast-forward updates and has no bypass actors;
- repository Immutable Releases are enabled before publication.

Routine workflow `GITHUB_TOKEN` is not proof of repository administration state. Governance read and bootstrap write credentials stay separate and minimum-scope.

## Governance bootstrap

`scripts/bootstrap_github_governance.py` is the idempotent desired-state installer for the named main/tag Rulesets and Immutable Releases. `.github/workflows/repository-governance-bootstrap.yml` exposes it only as an explicit administrative operation. Untrusted PR code never receives the administration write credential.

## v2 hard-cut assurance

Version 2.0.0 intentionally removes the 1.x compatibility surface rather than carrying migration aliases. Current assurance therefore requires:

- one `ap_build_info()` surface;
- one runtime lifecycle (`ap_runtime_open`, `ap_runtime_submit_frame`, `ap_runtime_read_metrics`);
- no removed 1.x exported symbols/types or shadow compatibility headers;
- a v2 hard-cut ABI gate for the initial release, followed by `v2.0.0` as the 2.x compatibility baseline;
- certification schema v4 only.

Historical 1.x facts remain in `CHANGELOG.md`, but current API/CI/documentation must not re-enable them.

## Shipping certification gate

A `product-certified` schema-v4 record requires a shipping-approved SKU policy and the following trust chain:

```text
reviewed source SHA
  -> audio-builder
     exact shipping compiler + sysroot + CFLAGS + SKU CMake arguments
  -> sealed shipping binary artifact
  -> audio-target DUT
     deployed digest == built digest
     executed digest == deployed digest
     real route + real corpus + thermal/power + policy soak
  -> attested certification bundle
  -> certification-archive
     immutable product-lifecycle archive receipt
```

The builder must not resolve target libraries, headers or CMake packages from the host filesystem. Builder and DUT must be distinct runners. Missing builder, DUT, sensors, real acoustic files, archive backend or lifecycle receipt is failed/incomplete certification, never a synthetic pass.

## HIL and maturity

Scheduled/Weekly/post-release HIL is fail-visible once policy requires it. If required hardware is disabled, availability fails rather than silently looking healthy.

Historical trend reports expose independent regression and maturity states. A short history may pass current regression checks while remaining `WARMING_UP`; `MATURE` requires at least 30 comparable successful points for every reported metric.

## Acoustic complexity policy

The low-compute DSP baseline remains default. Fractional beamforming, microphone calibration, wind/clipping/microphone-health handling or more advanced drift control become eligible only when real shipping acoustic evidence fails an approved threshold and the proposed change addresses that measured failure.

A passing product corpus is evidence to retain the simpler implementation.

## Product-final claim

A successful immutable software release closes the repository-side release mechanism only. A shipping-product-final claim additionally requires live enforced governance, real SKU public/private validation as applicable, HIL operating history and a passing 72-hour shipping certification under the applicable approved policy.
