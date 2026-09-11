# Cross-dump incident bundle

`apincident.py` is a repository-internal correlation layer over existing per-dump `triage.json` and `diagnosis.json` artifacts.

It does not parse APD files, replay audio, alter DSP/runtime behavior, or define new Product Qualification evidence. APD v1 and released `tools/*` remain unchanged.

## Authority

The output authority is `repository-internal-cross-dump-correlation-only` and always keeps `causal_proof=false`.

Each input must retain the existing per-dump authority boundaries:

- triage: `repository-internal-diagnostic-only`
- diagnosis: `repository-internal-heuristic-diagnostic-only`
- replay interpretation, when present: `repository-internal-replay-interpretation-only`
- build identity, when present: `repository-internal-build-identity-subset-only`

The bundle fails closed if an input tries to promote heuristic diagnosis into causal proof, PCM-only replay into whole-incident equivalence, or the shared build-identity subset into exact source/config identity.

## Correlation levels

Two separate cluster levels are emitted:

1. **fault-domain recurrence**: same `first_fault.family` plus same top heuristic hypothesis. This is broad recurrence evidence only.
2. **exact diagnostic pattern**: same recording trigger, fault domain, top hypothesis, runtime metadata flags, build-identity status, and replay-authority classification.

Neither level proves that two captures share the same physical root cause.

## Outputs

`incident-bundle.json` contains all normalized incidents, domain clusters, exact-pattern clusters, repeated clusters, optional unique dominant clusters, cross-dump build/replay/trigger consistency, and explicit interpretation limits.

`incident-bundle.md` is a compact human-readable rendering of the same evidence.

The tool requires at least two uniquely named incidents. Example:

```sh
python3 tests/diagnostics/apincident.py \
  --entry capture-gap capture/triage/triage.json capture/diagnosis/diagnosis.json \
  --entry codec-reopen codec/triage/triage.json codec/diagnosis/diagnosis.json \
  --output-dir incident-bundle
```
