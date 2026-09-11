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

The input cohort itself has separate authority: `repository-internal-caller-selected-cohort-only`. The bundle does **not** prove that caller-selected inputs came from the same physical device, same session, chronological capture order, authoritative capture timestamps, or a shared physical root cause.

## Source binding

Each `triage.json` and `diagnosis.json` is parsed from the same raw bytes that are SHA256-hashed. Per-source evidence records:

- `algorithm=sha256`
- exact byte `sha256`
- exact `size_bytes`
- optional portable `relative_path`

Use `--source-root` to constrain all input files to one evidence tree. Every input must resolve underneath that root or the command fails closed. When a source root is supplied, the bundle records portable relative paths rather than relying on runner-local absolute paths as evidence identity.

This cryptographically binds the bundle to exact JSON bytes. It does not add provenance that the JSON/APD format itself does not contain.

## Correlation levels

Two separate cluster levels are emitted:

1. **fault-domain recurrence**: same `first_fault.family` plus same top heuristic hypothesis. This is broad recurrence evidence only.
2. **exact diagnostic pattern**: same recording trigger, fault domain, top hypothesis, runtime metadata flags, build-identity status, and replay-authority classification.

Neither level proves that two captures share the same physical root cause.

## Outputs

`incident-bundle.json` contains all normalized incidents, per-source hash evidence, source-binding coverage, caller-selected cohort authority, domain clusters, exact-pattern clusters, repeated clusters, optional unique dominant clusters, cross-dump build/replay/trigger consistency, and explicit interpretation limits.

`incident-bundle.md` is a compact human-readable rendering of the same evidence.

The tool requires at least two uniquely named incidents. Example:

```sh
python3 tests/diagnostics/apincident.py \
  --source-root fault-injection \
  --entry capture-gap fault-injection/capture-gap/triage/triage.json fault-injection/capture-gap/diagnosis/diagnosis.json \
  --entry codec-reopen fault-injection/codec-reopen/triage/triage.json fault-injection/codec-reopen/diagnosis/diagnosis.json \
  --output-dir fault-injection/incident-bundle
```
