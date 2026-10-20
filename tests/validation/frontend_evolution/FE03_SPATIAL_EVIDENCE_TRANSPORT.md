# FE03 spatial evidence: lossless run-scoped transport

## Cause, baseline and scope

This implements the first-party byte-transport part of #754. The frozen science
source is e3672ffe16e4c9d42a100e7712b9bbd3d8338545. No DSP, source selection,
decoder, role, scientific step, validator, threshold, negative control or job
deadline changes are permitted by this contract.

The internal CI entry point is `.github/scripts/ci_evidence_transport.py`.

The historical main Artifact API reported 531633408 bytes for spatial evidence.
Two attempted full historical ZIP downloads did not complete; no historical ZIP
digest verification is claimed. The current baseline instead replays the exact
original source/48 spatial cases/BF-AEC order/Activity commands, including
ArmHF and all original verification and resealed negatives. The offset-8 source
is the independently revalidated original source-preflight ZIP
eb780ba093e19b21f2753048018c05ef0467ba6ebbe6c03d4372fd3ed0e0c8e1.
Current-host GCC 13.3 / QEMU 8.2 are not the historical runner identity.

The successful current tree contains 3488 files / 936076535 logical bytes,
1350 distinct SHA256 blobs / 779157330 unique bytes. Its 406 duplicate groups
contain 156919205 redundant bytes (16.7635% of logical bytes). An actual ordinary
ZIP using independent DEFLATE level 6 streams is 531400873 bytes, SHA256
8147ddefc752bba0270e13066e6c63508701866e6cbd18f8e2e7db34a1430d05.
The objects-only ZIP probe is 470086444 bytes; the final complete transport is
measured separately below. Neither number measures GitHub wire traffic or billing.

Two prior Activity outputs were rejected by the unchanged verifier: one retained
a truncated final CSV row; another contained a final-case file outside the sealed
manifest. Both failed trees and receipts remain negative evidence. Changing only
the output directory to a fresh /tmp directory produced a complete original
run/verify/negative PASS. Workspace synchronization was observed but has not been
proven to cause the two earlier failures. No failed tree qualifies the transport.

## Limited historical ZIP inventory

On 2026-10-20, two bounded HTTP 206 responses with the same ETag retrieved 405312
bytes from the original #753 PR artifact
[11886976787, run 38549257207](https://github.com/jiying2007/audio-pipeline/actions/runs/38549257207).
The 339755-byte central directory describes 3486 members / 936010640 uncompressed
bytes. This artifact's API size is 531633473 bytes; it is distinct from the
historical main artifact and from the current-host replay.

| Historical member group | Members | Uncompressed bytes | Compressed payload bytes |
| --- | ---: | ---: | ---: |
| effects | 2472 | 216625253 | 171027177 |
| order | 556 | 461109210 | 203749297 |
| activity | 451 | 258266799 | 156174215 |
| toolchain | 7 | 9378 | 3252 |

Only the central-directory inventory was read. The historical member payloads
and whole-archive SHA256 were not independently verified; the two earlier full
downloads remain unsuccessful. This inventory does not prove identical-content
groups. The SHA256 duplicate measurements and compression comparison use the
separate current-host tree, including its actual toolchain receipts.

## Complete current-tree roundtrip, 2026-10-20

The byte-identical internal tool at commit
343174e0f2318f7c4fc89ab0f4fc61349058d655 completed the full pack/unpack path with
run identity `local-20261020-spatial-audit` and scientific source e3672ffe16e4c9d42a100e7712b9bbd3d8338545.
The tool SHA256 is
caef42bc30521fe56fb7020549c5ba30450f37ed7cb49628dd06694cbc1b061b.
An independent full-tree readback confirmed all 3488 file paths, file bytes,
file modes and 335 relative directory paths/modes, before and after executing
all three unchanged original validators on the restored tree.

| Stage | Elapsed seconds | Result |
| --- | ---: | --- |
| Pack | 44.758 | PASS; peak RSS 30772 KiB |
| Unpack | 9.465 | PASS; peak RSS 23376 KiB |
| Original spatial verification | 22.193 | PASS |
| Original BF/AEC verification with `--require-arm` | 30.734 | PASS |
| Original Activity verification | 72.178 | PASS |

The complete `evidence.zip` is 470181719 bytes, SHA256
81b7dacef0972168f057aa203ae20a29610347fa3e8d871c16056b840215e7f2.
Its canonical manifest SHA256 is
4b3059f311d4b5d3daade4468b8e86b827cad53b856848b9b72507ec86ce827c.
Including the 536-byte sidecar gives 470182255 bytes: 61218618 bytes (11.520233%)
smaller than the independently constructed ordinary ZIP of these same files.
The size formula also matched that actual ordinary ZIP exactly. The RSS values
are Linux per-process `wait4` observations; the enforced 256 MiB limit concerns
virtual address space. Timing was not a matched CPU-performance experiment.

This proves the local byte roundtrip and continued passage of the original
validators. Existing protected PR and distinct post-merge CI, all four downstream
consumers and actual Artifact API/readback remain the required integration gates.
No historical runner identity, CI wire reduction or billing result follows from
these local observations.

## Representation and mandatory readback

One run-scoped bundle stores a canonical manifest plus one compressed object per
SHA256. The manifest enumerates every original relative file path, size, SHA256,
permission and directory, and binds the scientific source SHA, run identity and
first-party transport tool SHA256. Original source, compiler/binary receipts,
manifests, notices, PCM, results and failure files remain ordinary preserved
bytes; this manifest does not replace their independent authority.

The permission contract covers relative files and subdirectories. The containing
root directory's own mode is outside this contract. Ownership, timestamps and
pre-existing hardlink topology are not preserved. Both roots in the complete
replay were mode 0755. Duplicate member paths always restore to separate files.

The unpacker verifies the whole ZIP hash, bounded canonical manifest, exact ZIP
membership, object sizes/hashes, run/source binding, safe relative paths and file
types. It creates separate regular files for duplicate paths, never hardlinks or
symlinks. It then independently hashes the entire restored tree before publishing
a fresh output directory. Original scientific validators execute on the restored
paths with unchanged arguments and tolerances. Unpacking is byte validation only,
never an acoustic PASS, source admission, HIL proof or shipping qualification.

## Frozen resource and regression limits

- Linux CLI stage deadline: 180 seconds per pack or unpack; no retries.
- CLI virtual-address-space ceiling: 256 MiB; streaming chunks: 1 MiB.
- At most 24000 regular files and 24000 directories, 64 MiB per file,
  2000000000 logical bytes, 8 MiB manifest and 32 KiB sidecar receipt.
- The complete compressed package must be no larger than the equivalent ordinary
  ZIP of these same files. The latter size is derived from the actually measured
  per-object DEFLATE sizes and the ordinary per-path ZIP headers; it is a local
  representation calculation, not a wire or billing measurement. The initial
  acceptance comparison also constructs the ordinary ZIP independently.
- Preserve the existing 45-minute producer and 15-minute consumer job budgets.

Packing executes after the existing science steps. If it cannot complete, the
job remains failed and the existing raw evidence is uploaded, including any
source/transport failure receipt. No failed pack may suppress a scientific gate.
The bundle is uploaded with outer compression disabled because its objects are
already compressed; downstream jobs restore it before their original commands.

## Acceptance and 中文边界

Run bounded parser/roundtrip negatives, compare every real baseline/restored
path, file byte, mode and original manifest, then execute the original spatial,
BF/AEC --require-arm and Activity validators. The actual protected CI matrix must
also execute downstream correlation, Speex AEC, SYNC and their original controls,
required summary, and distinct post-merge main verification. Publish the exact
new Artifact API size/membership/digest and independent bundle readback.

本变更只改变相同运行内的字节传输。裸文件重复率不当作网络节省；本地主机回放不当作
历史 runner 或 SSC305 实测。原始数据、完整路径、文件内容、原校验器、失败证据与
科学判定全部保留。小清单或 unpack 成功不代替声学实验，不合成来源，不延长门限，
不通过减少样本、删除报告或复用旧科学成绩取得较小 Artifact。
