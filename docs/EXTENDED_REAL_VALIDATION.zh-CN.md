# Extended Real 独立研究验证

> **当前研究范围**：本流程只验证精确源码与已获许可数据下的声学表现，当前执行边界见 [RESEARCH_ONLY_EXECUTION.md](RESEARCH_ONLY_EXECUTION.md)。不要求商业 Release、SKU 批准或产品认证；没有真实数据时报告 BLOCKED/NOT_RUN，不影响独立的软件研究。

## 唯一当前入口与数据用途

`.github/workflows/validation-extended-real.yml` 是显式 `workflow_dispatch` 入口，要求固定 40 位 `source_sha`。不再根据 Release published 自动触发，也没有旧 commercial-core/commercial-plus 定时发布通道。

当前可选 profile 只有 `research-attribution-core`、`research-attribution-extended` 和 `research`。前两者以已审阅归属/许可的研究声源为范围；`research` 按其实际源许可使用额外研究数据。profile 名称不授予额外声音使用或再分发权，不把 NC/其他限制抹掉。具体版本、来源、用途和内容身份以 `validation/extended.datasets.lock.json` 及实际审阅为准。

数据由获准机器预先准备在 `audio-validation` runner 的绝对路径；不在清理或源码 CI 中自动下载、生成、识别或公开私人音频。`data_root` 为空时按 workflow 使用 `AUDIO_PIPELINE_LAB_DATA_ROOT` 或 `$HOME/audio-validation-extended`。

## 可复现执行链

1. `runner_preflight.py --role audio-validation` 核验工具、数据根、catalog 与可写输出位置，固定实际 source revision。
2. `extended_dataset_lock.py validate` 校验来源清单；`prepare_extended_validation.py scan/verify` 固定该 profile 的原始文件与哈希。
3. 在同一源码构建 `ap_process_pcm` 和 `ap_build_info_dump`，保留 ELF、构建身份与编译器信息。
4. `build_extended_real_corpus.py` 从已绑定的原始声源构造指定的直接/派生用例，记录来源谱系，不伪造独立说话人或盲测身份。
5. 使用既有 canonical `run_validation.py`、policy、source manifest 和精确 processor 评估；保存逐例指标、失败与原始证据。

默认预算为每数据源 24 个 source entries、direct 24、derived 16；这是当前 workflow 输入默认值，不是已完成实验或质量保证。实验可在预注册的有界设计下显式修改这些输入。

## 独立盲测

`research-attribution-core` 和 `research-attribution-extended` 使用独立的 `AP_VALIDATION_HOLDOUT_KEY` 按 scenario 做 HMAC 分层盲测切分，比例由 workflow 限定为 20% 或 30%。密钥不能写入公开结果，blind 数据不能反馈 optimizer。`research` 分支的评估范围依照实际研究 policy，不伪装成另一 profile 的独立盲测。

`validation-extended-real-core*.json`、`validation-extended-real-plus*.json` 等现存 policy 文件名是当前代码引用，不是商业放行证明。不得为得到 PASS 而修改原始数据/指标、放宽阈值、复用已暴露 holdout 或覆盖失败结果。

## 验收范围

报告必须区分来源就绪、运行成功、声学门槛通过、独立数据证据和目标板实测。此流程不证明实际 SSC305 的 CPU、RSS、温度、功耗或持续运行，也不替代最终 AFE 录音。设备维度需要独立实验；没有做就保持 NOT_RUN，不给其他研究工作附加产品认证或 72 小时门槛。

旧 profile、Release 调度与产品认证协议可在历史 Git 提交中读取，但不是当前可执行指令。公开产物只保留许可允许的脱敏元数据、来源/构建哈希和实际结果。
