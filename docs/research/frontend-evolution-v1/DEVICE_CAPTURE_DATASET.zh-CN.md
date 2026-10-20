# 设备采集数据：本地提交与使用边界

2026-10-20。用户明确允许将本地有效研究数据及按需真机采集纳入本地Git提交。本轮保存 `tests/audio/` 原始119文件（114131862字节），其中68个WAV共110056280字节，另有16组session/frames/events、2份现场说明和原`.gitignore`。单个最大文件4431872字节；没有新增生成音频或重编码。Git会对相同blob去重，原目录与文件名保持。

身份以原 [119文件输入锁](../../../.github/research/frontend-evolution-v1/device-capture-d0-input-lock.json) 为准；[D3合同](../../../.github/research/frontend-evolution-v1/device-capture-d3.json) 的原字节和数据角色保持。此说明放在数据目录外，避免破坏原intake的exact119文件集合。`tests/audio/.gitignore`仍为`*.wav`；本次仅对已校验的68个明确路径强制暂存，不全仓force-add。

## 能确定与不能确定的含义

- 顶层80/100由用户确认表示音量；不作为声学质量标签或训练类别。
- 16轮schema-v2原样保存mic双通道、raw reference双通道、used reference/设备output单通道及逐帧事件元数据。采样为16kHz PCM16，文件内容未经本轮修改。
- rpm目录名、session指令与motor反馈记录是不同证据；不能从目录名推断真实运动完成、物理麦克风映射或机械状态。
- session保持`human-not-verified`和`acoustic_verdict=pending`，已查看录音只作development/regression；原D3 `training_allowed=false`、`promotion_allowed=false`不变。不能将这些录音当独立blind真值、真人ASR/KWS结论、HIL或产品资格。

## 隐私与传播

只读元数据检查未见姓名、邮箱、电话或凭据字段；WAV容器只见fmt/data，未见INFO/BWF标识。本轮没有播放或转写声音，不能据此断言声音内容不含可识别个人信息、播放素材无第三方权利或已取得再分发许可。当前仅完成用户授权的本地版本保全，未推送或对外发布；外部传播前须另行核对声音内容、播放素材和相关授权。

## 可移植入口与历史结果

在仓库根运行：

```sh
python3 -m tools.codex_assets.device_capture --root tests/audio --dry-run
python3 tests/validation/frontend_evolution/test_device_capture.py
```

第一条验证原始文件集合、119个SHA、WAV/CSV/session和16轮输入合同，不执行DSP。第二条使用合成fixture验证软件合同，包含Host C构建，要求Python>=3.10、CMake和C编译环境；它不评估真人音频效果。

其余D4–D49工具是历史离线研究资产，多数还依赖固定`/tmp/audio-*` runner、已生成波形、审计回执及快照。提交原始录音和源码并不恢复所有历史产物。部分测试含封存成果依赖或rtk进程集成依赖，本轮不将其全部接入默认CI discover。历史计划、负结果及精确身份保持，机器上下文维护文档和临时二进制保留原现场及同步备份，不加入本批。

## D49 当前终态

原184路/505944帧执行完整，原开发准入拒绝：两臂near中位约-3.191886dB、20/24改善，但no-near最大+13.404531dB及pureecho whole最大+1.164761/+1.695652dB超过原+1dB限制。尚未完成独立全量审计，不把执行成功写成独立效果通过。resultSHA=6e4b460a101131e950888c947d7210210b948c749ea5e2184e3fce182b5fe6b6，bindingSHA=db417f95db9ca6d3467fd85c7975b8de372b7c79c45c6e9ce99c9a205d67229f；这两个引用指向原本机运行记录，不声明fresh clone已包含全部生成物。
