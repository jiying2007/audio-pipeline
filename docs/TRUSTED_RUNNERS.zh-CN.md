# 可信 Self-hosted Runner 操作说明（中文）

本页是 `audio-validation`、`audio-builder`、`audio-target`、`certification-archive` 四类可信 runner 的中文操作入口。英文 canonical runbook 为 [`TRUSTED_RUNNERS.md`](TRUSTED_RUNNERS.md)。

> Runner label 只是路由信息，不是 READY 证据。启用长时间或发货 workflow 前，必须对 exact 40-hex source SHA 执行 **Trusted Runner Readiness** 并保留 hash-bound `runner-readiness.json`。

`READY` 只表示该机器满足本次检查的基础设施前提，不是 acoustic/HIL/Product Certification PASS。

## 角色

| 角色 | GitHub labels | 必须真实提供 | 后续用途 |
| --- | --- | --- | --- |
| `audio-validation` | `self-hosted, linux, audio-validation` | 工具、真实/授权 dataset cache、seal/catalog | Compact/Full/Extended Real |
| `audio-builder` | `self-hosted, linux, audio-builder` | exact shipping compiler/sysroot/toolchain | sealed shipping binary/provenance |
| `audio-target` | `self-hosted, linux, audio-target` | DUT、board manifest、capture/playback/far-end/power/sensor route | HIL/target benchmark/certification |
| `certification-archive` | `self-hosted, linux, certification-archive` | immutable archive command/backend | product-lifecycle receipt |

Registration token、secret、archive credential 不进入 Git。

## 推荐上线顺序

### A. audio-validation

1. 注册独立 Linux runner，label=`audio-validation`；
2. materialize 并 seal commercial data cache；
3. 对 exact release source 运行 Trusted Runner Readiness；
4. 必须得到 `READY`；
5. 运行 visible validation；
6. 运行 blind holdout；
7. 扩展到 `commercial-core` Extended Real；
8. 重复验证稳定后才允许设置 `EXTENDED_REAL_ENABLED=true`。

公开/真实数据结果不能提升为产品硬件 authority。

### B. audio-target

1. 注册独立 DUT runner，label=`audio-target`；
2. 安装 reviewed board manifest；
3. 确认真实 capture/playback/far-end、power/sensor route；
4. 对 exact SHA 运行 Trusted Runner Readiness；
5. 运行人工审核的 accelerated HIL；
6. 多次健康后才允许设置 `HIL_ENABLED=true`；
7. 累积 Nightly 1 h、post-release 8 h、Weekly 24 h 等真实证据。

### C. audio-builder

1. 安装真实量产 compiler；
2. 固定真实 sysroot；
3. 固定 toolchain root；
4. 准备 shipping CFLAGS 与 reviewed SKU CMake args；
5. 用与 Product Certification 完全相同的路径参数执行 readiness；
6. 保留 `runner-readiness.json` 与 toolchain change record。

仓库不会替 operator 下载或伪造量产工具链。

### D. certification-archive

1. 部署 reviewed immutable archive backend；
2. 安装固定 archive command；
3. readiness 必须验证 command 可执行；
4. Product Certification 结束后必须返回可验证的 `product-lifecycle` receipt。

## 命令示例

### audio-validation

```bash
python3 tools/runner_preflight.py \
  --source-revision <40-hex-source-sha> \
  --role audio-validation \
  --data-root "$HOME/audio-validation-data" \
  --seal "$HOME/audio-validation-data/datasets.seal.json" \
  --output /tmp/audio-validation-readiness.json
```

### audio-builder

```bash
python3 tools/runner_preflight.py \
  --source-revision <40-hex-source-sha> \
  --role audio-builder \
  --shipping-cc /opt/toolchain/bin/arm-linux-gnueabihf-gcc \
  --shipping-sysroot /opt/toolchain/sysroot \
  --shipping-toolchain-root /opt/toolchain \
  --output /tmp/audio-builder-readiness.json
```

### audio-target

```bash
python3 tools/runner_preflight.py \
  --source-revision <40-hex-source-sha> \
  --role audio-target \
  --board-manifest "$HOME/.config/audio-pipeline/board.json" \
  --power-input /path/to/live_power \
  --output /tmp/audio-target-readiness.json
```

### certification-archive

```bash
python3 tools/runner_preflight.py \
  --source-revision <40-hex-source-sha> \
  --role certification-archive \
  --archive-command /usr/local/bin/audio-pipeline-cert-archive \
  --output /tmp/certification-archive-readiness.json
```

## 什么时候 readiness 失效

发生以下任一变化都要重新执行：

- runner OS/image/build tools；
- compiler/sysroot/toolchain root；
- dataset lock/seal/cache；
- DUT board manifest/route/corpus/sensors；
- archive command/backend/storage configuration；
- 被 qualification 的 exact source revision 改变。

旧 readiness 不得用于改变后的机器或输入。

## 与 E001 / Certification 的衔接

四角色都真实 READY，Extended Real/HIL 已反复健康并启用对应变量后，才运行 E001 Activation Preflight。

随后真实 Product Certification 仍会在同一执行中重新检查 builder/target/archive preflight。外部 readiness 是准备证据，不是最终认证替代品。

当前 v2.3.13 的产品资格目标继续使用 exact immutable release source；main 上后续 release-neutral 文档/治理提交不能代替被认证的 release source。
