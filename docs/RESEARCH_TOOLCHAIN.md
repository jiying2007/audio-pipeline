# Optional research cross-compiler smoke build

`scripts/verify-research-toolchain.sh` builds and installs the public C audio
pipeline with a user-selected compiler. It does not require a GitHub Release,
certification, SKU policy, model publication, device permissions or a shipping
toolchain. It does **not** measure SSC305 acoustics, energy or actual CPU use.

The command is explicit and locally invoked from the repository root:

```sh
CC=/absolute/path/to/arm-linux-gnueabihf-gcc \
  SYSROOT=/absolute/path/to/sysroot \
  BUILD_DIR=build/research-cortex-a32 \
  sh scripts/verify-research-toolchain.sh
```

Optional `CFLAGS` is passed as one quoted CMake value. The script refuses an
unknown compiler and keeps CMake arguments distinct even when paths contain
spaces. A successful host or cross-compiler link is only a **software** result.
Separate real-device measurements require an authorized hardware runner,
physical capture/playback route, exact source identity and observed metrics.

The original product-labelled shell script remains reachable in Git history
for provenance, not as a supported execution entrypoint. Offline
`tests/test_research_toolchain_boundary.py` keeps this research boundary
under the normal documentation gate.
