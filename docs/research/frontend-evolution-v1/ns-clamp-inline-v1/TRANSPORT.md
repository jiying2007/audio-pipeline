# Lossless transport and retained evidence

Compiler/size raw outputs and four integration disassemblies use `.b64` transport to preserve original whitespace. Decode each with `base64 --decode FILE.b64 > FILE` before checking `publication-manifest.json`. No measurement byte or existing digest is changed. The publication manifest describes all original text members; `manifest.json` additionally describes local binary executables and full NS output streams not stored in Git. The full local archive retains those payloads. No performance rerun.

The original benchmark and integration contracts have separate hashes. CMake/CTest/full pipeline remain unexecuted. This archive preserves a closed non-production candidate, not a production optimization.
