# Product Assurance Closure

This document defines the v1.6 product-assurance boundary. It intentionally does not expand the DSP architecture or treat hosted CI as product evidence.

## Software release gate

A software release requires all of the following:

- the exact `main` SHA passed `Verify/summary`;
- the release SHA is attributable to a merged pull request targeting `main`;
- live repository governance passes `scripts/github_governance.py` using a read-only administration credential supplied as `REPOSITORY_GOVERNANCE_TOKEN`;
- the active main Ruleset requires pull requests, strict `summary`, blocks deletion and non-fast-forward updates, and has no bypass actors;
- the active `v*` tag Ruleset blocks deletion and non-fast-forward updates and has no bypass actors;
- repository immutable releases are enabled before publication.

The normal workflow `GITHUB_TOKEN` is deliberately not treated as proof of repository administration state. The governance token should be a fine-grained read-only credential with the minimum Administration metadata permission needed to read Rulesets and immutable-release state.

## Shipping certification gate

A `product-certified` v4 record requires a shipping-approved SKU policy and the following trust chain:

```text
reviewed source SHA
  -> audio-builder
     exact shipping compiler + sysroot + CFLAGS + SKU CMake arguments
     libraries/includes/packages resolved only from the shipping sysroot
  -> sealed shipping binary artifact
  -> audio-target DUT
     deployed digest == built digest
     executed digest == deployed digest
     real route + real corpus + thermal/power + policy soak
  -> attested certification bundle
  -> certification-archive
     immutable product-lifecycle archive receipt
```

The builder must not resolve target libraries, headers or CMake packages from the host filesystem. Programs used during configuration are host tools; target libraries/includes/packages are restricted to the declared sysroot.

The builder and DUT must be distinct runners. Missing builder, DUT, sensors, real acoustic files, archive backend or lifecycle receipt is a failed/incomplete certification, never a synthetic pass.

## HIL and maturity

Scheduled Nightly/Weekly and post-release HIL are required once enabled for the shipping lab. If required HIL is disabled, the workflow emits an explicit failure rather than silently looking healthy.

Historical trend results expose two independent states:

- regression result: `PASS` or `FAIL`;
- evidence maturity: `WARMING_UP` or `MATURE`.

A short history can pass regression checks but cannot be represented as mature. The current maturity target is 30 comparable successful history points per reported metric.

## Acoustic complexity policy

The low-compute DSP baseline remains the default. Fractional beamforming, microphone gain/phase calibration, wind/clipping/microphone-health handling or more advanced drift control are eligible only when real shipping acoustic evidence fails an approved policy threshold and the proposed change addresses the measured failure.

A passing product corpus is evidence to keep the simpler implementation, not a reason to add algorithmic complexity.

## Product-final claim

`v1.6.0` can close the repository-side assurance mechanisms, but a shipping-product-final claim additionally requires live enforced GitHub governance and real SKU evidence, including the required HIL/certification history and a passing 72-hour shipping certification for the applicable policy.
