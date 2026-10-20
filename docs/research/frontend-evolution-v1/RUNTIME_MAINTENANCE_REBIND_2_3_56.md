# v2.3.56 Runtime maintenance and historical FE09 source preflights

## Concrete reason and authority

Issue [#810](https://github.com/jiying2007/audio-pipeline/issues/810) implements
four reproduced Runtime defects and two CI defects from the audit of
`e3672ffe16e4c9d42a100e7712b9bbd3d8338545`. Runtime behavior changes require the
governed next patch release, 2.3.56. The original R2B0 and R2B2-S0 research
preflights bind the complete older CMake, Runtime and API documentation blobs;
their frozen CMake source specifically says 2.3.55. Applying them directly to
this maintenance source therefore produces a real source-drift rejection.

This separately reviewed maintenance binding preserves that rejection and the
original source contracts. It does not rewrite either historical checker,
contract JSON, original ADR, source hash, experiment outcome or qualification.

## Exact current source and reconstructed historical source

`fe09_runtime_maintenance_2_3_56.json` permits exactly three changed source files:
`CMakeLists.txt`, `src/platform/linux/ap_runtime.c` and `docs/API_CONTRACT.md`.
It lists both original and current Git blob identities. The new checker pins
the complete manifest SHA256; the manifest pins the complete inverse patch
SHA256 and both original checker/contract identities.

The patch uses zero context so its stored blank lines satisfy the repository's
ordinary whitespace gate. Reconstruction explicitly uses `--unidiff-zero`;
the complete before/after blob checks still bind every source byte.

The maintenance checker first requires the actual current files to match those
reviewed current identities. It independently checks all 34 architecture probes
against current source, with the explicit new 2.3.56 project declaration, and
all original recorder anchors across 13 files. Public microphone limits, the
2.x compatibility line, value-struct API, separate capture/render contract and
original recorder version are unchanged. These source checks supplement the
existing public API/ABI gate and Runtime tests; they do not replace them.

The checker then copies only the relevant source files into a disposable local
directory and reverses the one pinned patch. It verifies all three resulting
original blob identities before running **both original preflight self-tests
and both original full checks**, including original full-file hash requirements
on every other source. It uses no remote fetch, history-dependent checkout,
fuzzy source normalization, relaxed hash comparison or wildcard version rule.

The outer receipt identifies current maintenance source hashes separately from
the reconstructed historical preflight results, and explicitly records
`historical_source_is_current_source=false`. Historical results are never
presented as execution of the corrected Runtime. Actual current Runtime CTest,
sanitizer, ABI and exact-head CI evidence remain independent requirements.
The same outer receipt records `shipping_src_changed=true`, the actual checkout
commit and checker hash. Any original non-promotion statement nested inside a
historical preflight describes that historical experiment, not this release.

## Negative controls and scope

The 14 new controls reject changes to every admitted current file, manifest,
historical checker/contract/ADR or inverse patch (including extra paths); an
unadmitted 3.0.0 declaration; a public C4 limit; and an
otherwise harmless extra byte in an unbound source that must still fail the
original full-blob check. All original R2B0/R2B2-S0 negatives also execute.

A future source change cannot silently reuse this mapping. It requires its own
concrete reviewed maintenance or migration admission. This entry does not
authorize a public 3.x SDK, installed C4, new Flight Recorder format, scientific
promotion, full-system C4 RAM/CPU claim, SSC305 HIL or an E001 identity change.

## 中文边界

本次修复的当前源码与旧研究快照分别校验、分别报告。维护条目只接受逐文件冻结的
2.3.56 修改；未知源码变化仍拒绝。临时副本中的逆向补丁只用于重建并复验旧快照，
不会修改工作区或安装代码，也不会把旧预检冒充为修复后的执行证据。两个旧检查器、
合同、完整源码散列与所有负例原样保留。新的 Runtime 测试、sanitizer、ABI、PR/main
门禁及正式发布仍必须各自完成；四麦产品与真机资格没有因此取得。
