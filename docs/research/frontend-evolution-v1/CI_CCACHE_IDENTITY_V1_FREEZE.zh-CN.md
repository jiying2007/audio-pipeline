# CI ccache 工作目录与源码身份修复：冻结合同 V1

冻结日期：2026-11-06。执行授权来自双麦识别交互与语音对讲集成任务的定向 CI 审查。

## 精确基线与根因

- 基线：`9a9202eca32cfa03d92644f5735bfc2c2429efbc`。
- `setup-ccache` 使用工作树内 `.ccache/` 恢复/保存编译缓存，现有 `.gitignore`
  只忽略 `.cache/`。当 `.ccache/` 含未忽略文件时，CMake 默认读取整个工作树的
  `git status --porcelain`，向 `AP_BUILD_SOURCE_REVISION` 附加 `-dirty`。
- 新 profile replay 严格比较 build-info 的 source revision 与调用方传入的
  40 位 revision；上述工作缓存可使它拒绝本来没有源码变更的构建。
- 这是可达工作树条件的接线缺口。当前环境未提供 ccache，不宣称实际运行了
  ccache、恢复了 Actions cache 或观察到远端 workflow 失败。

## 唯一候选与不变边界

只向 `.gitignore` 增加精确目录规则 `.ccache/`，与实际工作缓存路径一致。
不忽略普通未跟踪文件，不忽略任何已跟踪修改；不改 CMake 身份生成、runner、
profile source gate、`source_revision` 参数、DSP、声学阈值或现有测试超时。
不得通过显式设置 `AP_BUILD_SOURCE_REVISION` 绕过自动检测。

此冻结文档先单独提交。候选 `.gitignore` 随后单独提交，使 after 配置读取
干净候选提交的真实 HEAD；原始日志及结果在测量完成后另行提交，不污染被测身份。

## 测量方法与预先固定的验收

使用实际 CMake 可执行文件，对隔离工作树执行 `-S <worktree> -B <external-build>`，
参数固定为 `-DCMAKE_BUILD_TYPE=Release -DAP_BUILD_BENCH=OFF -DAP_STRICT_WARNINGS=ON`。
只配置，不编译、不跑 DSP。每个情景使用新的外部构建目录，解析生成文件
`generated/audio_pipeline/audio_pipeline_build.h` 中的 `AP_BUILD_SOURCE_REVISION`。
保留每次真实命令、HEAD、status、check-ignore、configure stdout/stderr、退出码、
耗时及生成头文件；记录相关文件 SHA-256。

| 情景 | 工作树变化 | 预期生成 revision |
| --- | --- | --- |
| before-clean | 冻结提交，干净工作树 | 冻结提交 HEAD |
| before-cache | 只添加人工 `.ccache/identity-probe.txt` | 冻结提交 HEAD + `-dirty` |
| after-cache | 候选提交，保留相同人工缓存文件 | 候选提交 HEAD |
| after-untracked-source | 缓存外添加 `src/ci_identity_untracked_probe.c` | 候选提交 HEAD + `-dirty` |
| after-tracked-source | 撤销上例，再向已跟踪 `src/ap_build_info.c` 追加无行为注释 | 候选提交 HEAD + `-dirty` |

后两项逐项清理，缓存文件最后删除；最终检查工作树源码和候选提交逐字节一致。
全部五项必须满足预期；任何缺失、超时、配置失败或身份不符均为 FAIL，不降级为 PASS。
人工 cache 内容只模拟工作缓存的文件存在性，不模拟编译器、设备、计时或 CI 结果。

## 预算与证据边界

五次 CMake 配置及相关检查累计预算 **300 秒**；分阶段脚本累计实耗并把剩余预算
作为配置 subprocess 的 timeout。没有 DSP/完整测试矩阵或新声学实验。
原始 before/after/负例日志和测量脚本写入独立证据目录；结果只说明本地默认
源码身份行为。远端 Verify、真实 ccache、物理 SSC305 均不由本记录取得 PASS。
