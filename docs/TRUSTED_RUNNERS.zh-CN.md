# 可信科研 Self-hosted Runner 操作说明

当前只用于**纯技术研究**。本页与 [英文规范](TRUSTED_RUNNERS.md)、[研究执行边界](RESEARCH_ONLY_EXECUTION.md) 和 [真机 HIL](../hil/README.md) 一致。活动 `Research Runner Readiness` 只检查设备/环境是否具备运行条件，不能授予商用发布、产品认证、真人录音权限或声学 PASS。

## 精确源码与三种科研角色

每次显式提交 40 位源码 SHA；只能对该提交做本次准备检查，不能静默替换成最新 main、历史 Release tag 或其他分支。源码、工具链、设备路由、音频数据来源或传感器变化后必须重新验证。

| 角色 | 隔离 Runner 标签 | 检查内容 | 禁止推断 |
| --- | --- | --- | --- |
| 公开数据验证 | `self-hosted, linux, audio-validation` | 来源合法的数据缓存和封存清单、工具链 | 真人或实机性能 |
| 目标交叉构建研究 | `self-hosted, linux, audio-builder` | 真实研究编译器、sysroot 和 toolchain root | 发货 SDK/签名/量产资格 |
| 真机音频实验 | `self-hosted, linux, audio-target` | 板卡配置、ALSA/codec、route 和实际传感器 | 未执行的 CPU/声学/温度/功耗结果 |

旧的 `certification-archive` 产品证据归档角色与 Shipping 工具链准入已退出活动工作流。历史记录仍可在 Git/Actions 中追溯，不能作为新的科研准入或认证批准。

## 可执行的独立预检

```sh
python3 tools/runner_preflight.py --self-test

# 公开语音数据来源、许可和冻结清单必须另行核实
python3 tools/runner_preflight.py --role audio-validation \
  --source-revision "$SOURCE_SHA" --data-root /srv/audio-validation \
  --seal /srv/audio-validation/datasets.seal.json \
  --writable-path /srv/audio-validation --output /tmp/research-validation-readiness.json

# AArch32 科研交叉构建，不是商用发货构建
python3 tools/runner_preflight.py --role audio-builder \
  --source-revision "$SOURCE_SHA" \
  --target-cc /opt/toolchain/bin/arm-linux-gnueabihf-gcc \
  --target-sysroot /opt/toolchain/sysroot \
  --target-toolchain-root /opt/toolchain \
  --writable-path /tmp --output /tmp/research-builder-readiness.json

# 真实隔离板卡，私有配置不可上传到公开仓库
python3 tools/hil_board.py preflight \
  --board /etc/audio-pipeline/board.json --output /tmp/hil-preflight.json
python3 tools/runner_preflight.py --role audio-target \
  --source-revision "$SOURCE_SHA" \
  --board-manifest /etc/audio-pipeline/board.json \
  --writable-path /tmp --output /tmp/research-target-readiness.json
```

`READY` 仅说明基础设施可用，不表示声音算法或真机测试 PASS。实际 HIL 只能手动提交精确 SHA、真实 `audio-target`、私有板卡与 `HIL_ENABLED=true`；600 秒、1/8/24/可选 72 小时仅是预注册科研时长，不是固定产品认证门槛。设备缺失要记录 `NOT_RUN`、`BLOCKED_RUNNER` 或 `BLOCKED_CONFIG`，测量失败要保留 FAIL。Extended Real 则使用独立合法数据集与 `EXTENDED_REAL_ENABLED` 门禁。

## 失效与重验

源码 SHA、编译器/sysroot、麦克风/扬声器布局、板卡/codec、采集/播放 route、数据许可、封存哈希、CPU governor、温度/功耗传感器、可写路径或私有挂载变化，均需重新预检。旧认证归档与 Release 标签收据仅保留为历史来源，不向当前科研授予任何权限。
