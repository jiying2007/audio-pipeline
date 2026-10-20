# FE03 original speech reacquisition / 同字节原始语音回源

## Frozen cause and scope

Base: e3672ffe16e4c9d42a100e7712b9bbd3d8338545.

The original protected speech Artifact used by #792 has finite retention. Its
expiry makes the only source path fail even though the independently admitted
official archive is still the source authority. This is a transport dependency
defect. Extending retention does not provide a source recovery path.

This contract extends
[the protected original-source recovery](FE03_PINNED_ORIGINAL_SPEECH_SOURCE_RECOVERY.md).
Its failed historical runs, source identity and acoustic admission remain
unchanged. It introduces no new corpus, speaker, role, window, URL, threshold,
decoder fallback, DSP implementation, shipping default or public API.

## Same-byte authority

- Original URL: https://www.openslr.org/resources/12/dev-clean.tar.gz
- Original size: 337926286 bytes.
- Original MD5: 42e2234ba48799c1f50f24a7926300a1.
- Original archive SHA256:
  76f87d090650617fca0cac8f88b9416e0ebf80350acb97b343a85fa903728ab3.
- Original selected-source binding:
  7c4d711d4cb69121ccbbcb9a596d7ea26ca141a325add2dc8f5ff7421b9154c1.
- Original offset 0, 32 FLAC members and eight fixed four-second PCM windows.

The unchanged speech-admission-v1.json, speech_source.acquire and
speech_spatial.source_check remain the independent authority. A transport
receipt or successful downloader exit cannot replace source admission. The
offset-8 spatial source has a different selection and role contract and cannot
be substituted for this offset-0 source.

## Execution and receipts

1. Require the current checkout's exact source SHA and the existing frozen
   admission. Reject existing, symlink or overlapping destinations.
2. Try the same protected Artifact cache. Enforce the original repository,
   main/run/event/conclusion, Artifact ID/name/origin/size/digest and independently
   hash the ZIP before source extraction. Existing safe ZIP and original
   selected-byte checks stay in force.
3. Cache absence, expiry, transport failure or identity rejection writes a
   compact source-cache-failure.json with a specific negative reason. Keep it
   even if official reacquisition succeeds. Do not save API bodies, credentials,
   stderr or redirected signed URLs.
4. Only the original official URL may recover the cache failure. Use the
   unchanged at-most-three full-download attempt policy, require original size
   and SHA256 before decoding, then invoke the original acquisition at offset 0.
   Do not inherit GitHub tokens in the download/decoder worker.
5. Independently verify the selected source tree before publishing it into a
   fresh destination. Keep the source-transfer.json with exact current SHA,
   original archive identity, acquisition path and selected-file hashes. On the
   official path, bind the retained cache failure receipt by SHA256.
6. Execute fresh current-version speech and FIR effects, independent readback
   and all existing evidence negatives. No old scientific score is reused.
   Retain new effects, FIR and receipts with the existing always-upload step.

source-transfer.json schema 2 distinguishes protected-artifact-cache from
official-original-archive. It separately records whether the original full
archive was rehashed and actually downloaded in this run. The explicit
--reacquire-official --original-archive path is a local replay of the same
full-size, SHA256-checked original archive, not permission for another URL.
The public replay command requires an explicit local archive. To request a
network acquisition, use --acquire and its cache/failure/source-stage contract.
Local replay also runs in a single supervised worker with the same 1800-second
total budget, original hashing/decoding and independent source readback. Its
receipt states that the archive was rehashed, not downloaded by the replay.

The direct replay entry originally called the official worker inline. Independent
offline review of 64e49e7bda8029a54f5a67b674d65a464e92b366 showed that this
public entry could bypass the outer budget and pass inherited GitHub tokens to
the downloader or decoder. This correction closes that command boundary. It
also removes both tokens at the official callable boundary, including explicit
local decoding, and restores the caller's environment after completion/failure.
The hidden worker entry is an internal implementation of the supervisor; it
does not start another supervisor or grant a new source/download policy.

## Budgets and failure

The protected cache transfer ceiling is 600 seconds. The source-stage budget
remains 1800 seconds in total. One parent supervises a single worker containing
cache access, ZIP hashing/extraction, independent source readback, and any
original-archive reacquisition and decoding. Cache success cannot return outside
this deadline. The worker never recursively starts another budget supervisor;
gh and FFmpeg stay in its process group for the existing termination policy.
The parent also rejects a completed receipt received after the total deadline.
There is no additive original-source budget. The original 45-minute job ceiling
and at-most-three transfer attempts remain unchanged.

If no source passes the independent contract inside the existing budget, fail
closed and retain source-failure.json. Keep a prior, more specific source failure;
never overwrite preexisting output evidence. Preserve cache failure receipts
regardless of the later source outcome. Missing/expired cache is infrastructure
state, not acoustic failure or product qualification.

## Acceptance / 中文验收边界

定向测试覆盖缓存命中、过期/缺失、错误 run/artifact 身份、真实错误字节散列、
解码前拒绝、路径冲突、伪成功、错误源 SHA、授权环境隔离、失败收据保留、
单个总预算、缓存命中晚到成功、真实延迟缓存 worker 超时终止及失败收据。离线测试中的 transport/verifier double 仅证明控制流，
不会被当作真实语音准入或声学成绩。
直接 CLI 另覆盖缺少本地 archive 的拒绝、两种官方调用的 token 隔离、单个受监督
worker、扣除已耗预算、晚到成功拒绝、archive 符号链接拒绝，以及通过 IPC 明确到达
解码停点后对真实父子进程组的超时终止。该负例不依赖机器导入速度，不放宽生产预算。

真实回源必须取得上述相同完整归档，重算固定 selected-source binding，再在当前
提交上重跑原 speech/FIR 用例、独立 verify 和重新封存负例。所有原准入、来源、
角色和科学代码保持。候选还必须通过适用的 exact-head Verify/summary；合并后
独立验证 exact main 和现有 Release 身份链。本契约不制造新 SDK 版本，不取得
HIL、真实设备、第三方再许可或产品资格。
