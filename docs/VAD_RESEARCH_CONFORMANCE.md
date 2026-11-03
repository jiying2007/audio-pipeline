# VAD frame-exact research conformance

The active VAD workflow is `.github/workflows/vad-research-conformance.yml`.
It tests an existing C/DSP runtime against six deterministic synthetic source
partitions (seeds 1307, 2307, 3307, 4307, 5307 and 6307). The test is a
**scientific regression**, not product, shipping, or commercial approval.

Both `vad-isolated` and `ns-isolated` profiles are required. The
`tests/validation/vad_research_policy_conformance.py` evaluator uses the
processor's emitted `vad_probability` to replay the frozen, frame-exact
strong/weak hangover rule and compare it against the emitted `vad_active`:
local threshold 0.45, NS threshold 0.35, strong threshold 0.50, strong hold
8 frames and weak refresh 6 frames without shortening an active strong hold.
All active mismatches must be zero and independent per-case VAD statistical
gates must pass. The evaluator and workflow retain their pinned corpus hashing,
case identities and failure evidence under normal, `-O` and `-OO` Python
self-test modes.

The former shipping-named workflow and evaluator are removed from active
execution. Their original bytes and historic job results remain in Git/Actions
history. Any old `shipping-vad-policy-conformance` receipt belongs to that
older format; it is not silently upgraded into a new research receipt.

These fixtures do not measure real human speech, final microphone/AFE
conditioning, SSC305 timing, continuous FAR or field FRR. Those require
independently acquired and source-bound recordings, targets and honest
NOT_RUN/FAIL outcomes. Third-party audio/model licenses and source
permissions remain fully applicable.
