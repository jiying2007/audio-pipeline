# 可信 Self-hosted Runner 操作说明（中文）

本页是 `audio-validation`、`audio-builder`、`audio-target`、`certification-archive` 四类可信 runner 的中文操作入口。英文 canonical runbook 为 [`TRUSTED_RUNNERS.md`](TRUSTED_RUNNERS.md)。

> Runner label 只是路由信息，不是 READY 证据。启用长时间或发货 workflow 前，必须对 exact 40-hex source SHA 执行 **Trusted Runner Readiness** 并保留 hash-bound `runner-readiness.json`。

`READY` 只表示该机器满足本次检查的基础设施前提，不是 acoustic/HIL/Product Certification PASS。

## 上线前先绑定资格版本

为指定 Release 收集资格证据时，应从 live external-evidence tracker 或已审核的资格请求取得获准的不可变 tag 与 exact source SHA，并先核对 tag 实际指向该提交。历史说明中的版本号、最新软件 Release 和当前 `main` 都不能代替这组已审核身份。请求与发行身份不一致时，先解决差异，不得默认选择较新的提交继续执行。

四类角色的 readiness、量产工具链、产品输入、HIL 历史和 Product Certification 必须对应目标资格源码及已审核输入。后续维护提交不会自动替换该源码；即使机器和路径未变，只要 readiness 对应的源码版本变化，也必须重新检查。

### 定时维护不等于固定 Release 资格验证

实际源码路由由 [HIL 工作流](../.github/workflows/hil-soak.yml) 和 [Extended Real 自动化](../.github/workflows/extended-real-automation.yml) 定义：

| 入口 | 工作流实际选用的源码 |
| --- | --- |
| HIL 手动触发 | 显式 `inputs.source_sha` |
| HIL 发布后触发 | `client_payload.release_ref`，使用 `release-8h` tier |
| HIL 定时 1 h / 24 h 维护 | 该次定时运行的 main 提交 `github.sha` |
| Extended Real 发布后自动化 | `release_ref`，与传入的 release tag 核对；`commercial-core` |
| Extended Real 定时或手动自动化 | 拉取后的 `origin/main`；`commercial-plus` |

定时 main 运行成功，只能作为其记录源码的回归证据，不能自动计入另一个获准 Release 的 HIL/Extended Real 资格历史。固定版本取证应使用已审核的 exact-source 入口，并核验结果中的源码和输入。Extended Real 的手动自动化入口不是固定版本选择器；canonical `validation-extended-real.yml` 接受显式 `source_sha`。不得为了检查基础设施重跑已消费的 blind 或研究验证。

`HIL_ENABLED` 或 `EXTENDED_REAL_ENABLED` 不为 `true` 时，对应定时工作流会输出 `HIL_SCHEDULE_SKIPPED_DISABLED` 或 `EXTENDED_REAL_SCHEDULE_SKIPPED_DISABLED` 并正常退出，不执行实机工作；必需的发布后事件仍会报错停止。HIL 手动入口允许在开关启用前进行已审核的 exact-SHA 接入验证，但仍需要真实 target 和 preflight；Extended Real 手动自动化在未启用时仍被阻止。控制器绿色跳过或已有发布后汇总，不代表 `READY`、HIL 或 Product Certification 通过。

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
7. 为获准源码和输入累积所需的 1 h、8 h、24 h 真实证据；定时 main 回归不能代替固定 Release 的资格历史。

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

产品资格继续绑定上述已审核的不可变 Release 与 exact source；main 上后续 release-neutral 文档/治理提交不能代替被认证的 release source。
