# SSC305-low ARM GNU static preflight

Actual sources: base `438fe09d79ff768306c00573849517bcd91cbc6e` and candidate `9a9202eca32cfa03d92644f5735bfc2c2429efbc`.

This is a local cross-compilation and static ELF measurement, not CI, QEMU, physical SSC305, audio quality or runtime execution evidence. No ARM executable was run. Repository source, thresholds and admission registrations were not changed. Toolchain packages were downloaded from the official Debian HTTPS pool and extracted here; no global installation or synthetic /usr/bin tool was used.

| Metric | Base | Candidate | Existing ceiling |
|---|---:|---:|---:|
| `.text` | 27,560 B | 32,864 B | — |
| `.rodata` | 3,292 B | 3,292 B | — |
| `.text + .rodata` | 30,852 B | 36,156 B | 40,960 B |
| Pipeline arena | 38,832 B | 38,864 B | — |
| Runtime arena | 6,424 B | 6,424 B | — |
| Caller-owned arenas sum | 45,256 B | 45,288 B | 50,000 B |

The candidate adds 5,304 B ROM and 32 B caller-owned arena in this identical-toolchain comparison. Remaining headroom is 4,804 B ROM and 4,712 B arenas. These values remain inside the existing envelopes for this preflight; fixed CI remains authoritative.

The original `ssc305-cortex-a32-low` preset and original `tests/rom_probe.c` were used. Flags are `-O3 -mcpu=cortex-a32 -mfpu=neon-fp-armv8 -mfloat-abi=hard -ffunction-sections -fdata-sections`; linking uses `--gc-sections`. The only tool-location settings are an explicit actual compiler path and the extracted sysroot. Effective compilation flags and generated build macros are in `report.json`. Caps are 16k/16k, two microphones, delay 60 ms, AEC tail 64 ms, queue 4, direction tracking OFF, NEON, Linux runtime ON.

The delivery-profile collector counts `.text` plus `.rodata` sections; this is the same convention used here. It is distinct from the older generic `size` summary text+data check elsewhere in CI. Arena values were read from the actual cross-compiled `ap_pipeline_state_size` and `ap_runtime_state_size` constant-return disassembly, not copied from native host sizes and not obtained by running ARM code. In particular, ARM runtime size 6,424 B differs from the earlier native host 6,456 B.

`report.json` contains actual results, compiler/tool hashes, effective configuration, binary/library hashes and original getter disassembly. `toolchain-packages.json` contains official download URLs, byte sizes and SHA-256 for all eight packages. `base-*.log` and `candidate-*.log` preserve configure, build, link, section-size and getter outputs. `evidence-manifest.json` covers these compact records; full package archives, source exports, build outputs and ELF files remain in this scratch directory and are excluded from that compact manifest.

The initial extracted GNU size invocation lacked its extracted libbfd search path and exited 127. That bootstrap failure is recorded in `report.json`; the final unmodified tools ran with the extracted host library directory in LD_LIBRARY_PATH. Both actual builds and static measurements then completed successfully. No A3 fixed-toolchain requirement was relaxed or qualified by this local preflight.
