# Cross-dump incident bundle

`apincident.py` is a repository-internal correlation layer over per-dump `triage.json` and `diagnosis.json` artifacts. It does not parse APD files, replay audio, alter DSP/runtime behavior, or define Product Qualification evidence. APD v1 and released `tools/*` remain unchanged.

## Authority

The output authority is `repository-internal-cross-dump-correlation-only` and always keeps `causal_proof=false`.

Every input must retain these per-dump authority boundaries:

- triage: `repository-internal-diagnostic-only`
- diagnosis: `repository-internal-heuristic-diagnostic-only`
- replay interpretation: `repository-internal-replay-interpretation-only`
- build identity: `repository-internal-build-identity-subset-only`, with status `MATCH` or `MISMATCH`

The bundle fails closed if an input promotes heuristic diagnosis into causal proof, PCM-only replay into whole-incident equivalence, omits the terminal replay/build-identity authority blocks, or promotes the shared build-identity subset into exact source/config identity.

The input cohort has separate authority: `repository-internal-caller-selected-cohort-only`. The bundle does **not** prove same physical device, same session, chronological capture order, authoritative capture timestamps, or a shared physical root cause.

## Source binding

`--source-root` is mandatory for every normal invocation. Every `triage.json` and `diagnosis.json` must resolve underneath that root **before any source bytes are read**; symlink or path escapes fail closed.

Each JSON object is parsed from the same raw bytes that are SHA256-hashed. `source_evidence` is the only source identity emitted for each role and contains:

- `algorithm=sha256`
- exact-byte `sha256`
- exact `size_bytes`
- mandatory root-relative `relative_path`

The former runner-local `source.{triage,diagnosis}` path block is not emitted. Bundle construction also fails if any source lacks valid hash binding or a portable relative path.

This binds the bundle to exact JSON bytes without inventing provenance that the JSON/APD format itself does not contain.

## Correlation levels

Two separate cluster levels are emitted:

1. **fault-domain recurrence**: same `first_fault.family` plus same top heuristic hypothesis; broad recurrence evidence only.
2. **exact diagnostic pattern**: same recording trigger, fault domain, top hypothesis, runtime metadata flags, build-identity status, and replay-authority classification.

Neither level proves that captures share a physical root cause.

## Outputs

`incident-bundle.json` contains normalized incidents, per-source hash evidence, complete source-binding coverage, caller-selected cohort authority, domain clusters, exact-pattern clusters, repeated clusters, optional unique dominant clusters, cross-dump build/replay/trigger consistency, and explicit interpretation limits.

`incident-bundle.md` is a compact human-readable rendering of the same evidence.

The tool requires at least two uniquely named incidents:

```sh
python3 tests/diagnostics/apincident.py \
  --source-root fault-injection \
  --entry capture-gap fault-injection/capture-gap/triage/triage.json fault-injection/capture-gap/diagnosis/diagnosis.json \
  --entry codec-reopen fault-injection/codec-reopen/triage/triage.json fault-injection/codec-reopen/diagnosis/diagnosis.json \
  --output-dir fault-injection/incident-bundle
```
