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
The objects-only ZIP probe is 470086444 bytes; the final complete transport must
be measured separately. Neither number measures GitHub wire traffic or billing.

Two prior Activity outputs were rejected by the unchanged verifier: one retained
a truncated final CSV row; another contained a final-case file outside the sealed
manifest. Both failed trees and receipts remain negative evidence. Changing only
the output directory to a fresh /tmp directory produced a complete original
run/verify/negative PASS. Workspace synchronization was observed but has not been
proven to cause the two earlier failures. No failed tree qualifies the transport.

## Representation and mandatory readback

One run-scoped bundle stores a canonical manifest plus one compressed object per
SHA256. The manifest enumerates every original relative file path, size, SHA256,
permission and directory, and binds the scientific source SHA, run identity and
first-party transport tool SHA256. Original source, compiler/binary receipts,
manifests, notices, PCM, results and failure files remain ordinary preserved
bytes; this manifest does not replace their independent authority.

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
