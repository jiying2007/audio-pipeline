# Repository-internal diagnostics

These helpers extend engineering diagnosis without changing the released `tools/*` surface, APD v1, shipping DSP, presets, public API/ABI, or Product Qualification authority.

- `aptriage.py` extracts/replays an APD and produces structured anomaly evidence.
- `apdiagnose.py` ranks evidence-backed hypotheses, identifies the first non-trigger anomaly, clusters nearby anomalies, recognizes temporal candidate chains, and can compare a failing triage result with a separately triaged reference.

`apdiagnose.py` is deliberately heuristic. `heuristic_score` is an evidence-ranking score rather than a probability, every candidate chain is marked `temporal-association-only`, and all outputs set `causal_proof=false`. These artifacts are diagnostic aids only and cannot claim HIL, Product Qualification, Product Certification, or shipping authority.
