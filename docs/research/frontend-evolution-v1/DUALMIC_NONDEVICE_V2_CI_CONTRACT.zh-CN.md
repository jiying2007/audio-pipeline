# 非真机 V2 的 CI 接入合同

日期：2026-11-06（Asia/Shanghai）。本记录在新 CI 执行之前固定接入方式。
父合同见 [V2 实施前合同](DUALMIC_NONDEVICE_V2_PLAN.zh-CN.md)，远程冻结为
`7f486b6f48e2ecfe33310f589c2dd98595d324a5` / [PR #920](https://github.com/jiying2007/audio-pipeline/pull/920)。

复用已有 `audio-quality / validation-smoke` 执行原 42 例及新 B/C 软件集成，
复用 `quality / frontend-speech` 的原 46 文件来源取得/校验后执行 A。原历史
回放、科学门槛、失败退出、main 完整图和 required summary 保持；不另建一次性 workflow。

`validation-smoke` 固定 `ubuntu-24.04`，使来源锁中的 CPython 3.12 Linux wheel
与明确宿主 ABI 配套。这是新外部模型适配的预先配置，不因看到失败而换 runner；
ARM/QEMU/其他作业预设与版本不改。checkout 不保留 Git 凭据，模型执行不传入 token。
Opus 使用宿主 `libopus0`，回读版本和实体 hash，不能把 host 库混入固定内存 SDK。

新增 `validation/tools/downstream_metrics.py` 仅作文本/事件测量，明确列入现有
SemVer-neutral 精确文件清单；未知 canonical helper 与生产代码依旧受原版本规则
约束，新文件仍触发保守完整 Verify。SDK/source 版本保持 2.3.63，没有发布或 tag。

每个新本地/CI 测量阶段设 300 秒上限，失败 stdout/stderr 和已生成记录先保留。
A 复用已经完成来源验证的相同 job 数据，不另放宽原来源阶段的预算或改变来源。
新产物以 run 与 attempt 命名；包含实际 source SHA、构建/运行时/数据 hash、逐例
记录与明确未测项。合并前及新 main 分别核对各自原件，不把 PR 产物重标为 main。

56 例真实英文录音及 8 类网络模拟的执行完整性，与中文单片段真实模型集成，
均不赋予独立效果晋升、真人 MOS、真实网络延迟或物理目标资格。
