# Archive and reproduction boundary

Full original evidence: `audio-oracle-agc-isolation-v1-evidence.tar.gz`, SHA256 `f6a5c0c61ea66182ce4940f0ed2061a9e53732139c4581949bf69f0b88d25c39`.
The separately preserved archive contains raw input/output Float32, gain states, control CSVs, allow arrays, original native executable and all receipts. The full manifest here binds every original file; executable/audio bytes are not duplicated in Git. `execution-receipts.json` losslessly base64-encodes the other text/JSON execution files with their original hashes and byte counts, including compiler blank lines. Decode before comparing with the full manifest.

Scripts and source copies are archival research material, not a CI hook or production change. Reproduction needs the full archive at the paths identified by the frozen contract; this PR does not rerun it. Both oracle output/state byte gates must pass before any restored-allow arm. Do not adjust math/compiler strategies to force admission. Historical private-runtime and full-pipeline execution counts are zero for this experiment.

Independent read-only review recomputed all 52 metric groups and 28 timing observations exactly, verified 17 input locks, 267 manifest entries and both sequential replay gates. That scientific review does not replace protected exact-head CI. No raw-near metric is a CER/MOS or isolated speech-quality claim; reduced error and worsened projection are both retained. Hosted timing spread does not support robust acceleration or target-device claims.
