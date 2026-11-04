# 关键流程图（中文）

本页把仓库已经存在的机器契约画成可读流程图。流程图**不创建新的权限**；与 workflow、schema 或 `validation/authority.json` 冲突时，以机器契约为准。

## 1. 音频数据流

```mermaid
flowchart LR
    A[S16 设备采集] --> B[采样率适配]
    B --> C[HPF]
    C --> D[双麦 BF]
    D --> E[SYNC]
    E --> F[Activity / DTD]
    F --> G[AEC]
    G --> H[RES]
    H --> I[NS]
    I --> J[AGC]
    J --> K[VAD]
    K --> L[单声道 S16 输出]

    R[Far-end render] --> E
    R --> G
    M[10 ms metadata\ntimestamp / gap / XRUN / reset] --> E
    M --> G
```

核心约束：固定 10 ms frame；同步 stage/core 不做 heap、文件/网络 I/O、mutex 或格式化日志；CPU 型号不进入算法依赖。

## 2. Runtime 所有权与线程

```mermaid
sequenceDiagram
    participant App as 调用方
    participant RT as Linux Runtime
    participant Q as 有界队列
    participant W as DSP Worker
    participant P as Pipeline

    App->>RT: ap_runtime_open(caller memory, pipeline)
    App->>RT: ap_runtime_start()
    RT->>W: 启动单 worker
    Note over W,P: started 后 worker 独占 live Pipeline
    App->>Q: ap_runtime_submit_frame()
    Q->>W: 接收 frame + metadata
    W->>P: process 10 ms
    P-->>W: output + DSP metrics
    W->>Q: 发布有界输出
    App->>RT: ap_runtime_receive()
    App->>RT: ap_runtime_read_metrics()
    App->>RT: ap_runtime_stop()
    App->>RT: ap_runtime_deinit()
```

控制面不能绕过 worker 直接修改 started 状态下的 Pipeline；ownership/queue/counter 变更必须通过 TSan 契约。

## 3. 数据集自测、调参与晋级权限

```mermaid
flowchart TD
    D[development / regression\n可用于 search] --> S[有界搜索 / tuning]
    S --> C[冻结候选\nACOUSTIC_CANDIDATE]
    C --> V[validation-grade\nvalidation / shadow]
    V --> B[validation-grade-blind\n独立 holdout]
    B --> R{独立证据通过?}
    R -- 否 --> K[KEEP BASELINE / 保留失败证据]
    R -- 是 --> P[仅形成软件候选/晋级证据]
    P --> H[可选真实 DUT/HIL 独立科研测量]

    X[research-validation] --> S
    V -.禁止反馈 optimizer.-> S
    B -.禁止进入 optimizer.-> S
```

关键规则：validation-grade/blind 不能用于挑参数；重复使用同一数据不是新的独立确认；任何搜索都不能自动修改默认算法或将开发集结果冒充独立验证。

## 4. PR → protected main → 研究证据

```mermaid
flowchart TD
    A[变更分支] --> B[精确 HEAD PR]
    B --> C[Impact + Fast Gate]
    C --> D[完整 Verify: GCC/Clang/Sanitizer/TSan/CodeQL/ARM/QEMU/Resource/Audio]
    D --> E{required summary = success?}
    E -- 否 --> X[保留失败证据 / 修复并重跑 exact-head]
    E -- 是 --> F[受保护 squash merge]
    F --> G[精确 main Full Verify]
    G --> H[冻结源码、参数、数据角色、历史审计身份]
    H --> I[可复现研究报告 / Actions Artifacts]
```

科研主线只需代码与独立数据门禁，**不得**因为 PR 或 main Verify 成功就自动发布 GitHub Release、商用 SDK 或产品认证结论。历史不可变版本与标签保留原样供审计，不是新实验准入。

## 5. 研究结果 → 可选真机实验

```mermaid
flowchart TD
    S[精确研究源码 SHA] --> R{真实 audio-target runner + 数据权利已核实?}
    R -- 否 --> N[NOT_RUN / BLOCKED，不伪造实测]
    R -- 是 --> B[手动 HIL workflow_dispatch / exact SHA]
    B --> P[真实板卡/ALSA route/AFE preflight]
    P --> H[预注册时长的 600s / 1h / 8h / 24h / 可选 72h 研究测量]
    H --> E[CPU/RSS/XRUN/温升/功耗/声学来源哈希]
    E --> F{测量及身份完整?}
    F -- 否 --> Z[FAIL / 保留原始证据]
    F -- 是 --> G[可复现独立设备研究结果]
```

`READY` 只是基础设施状态，不是 HIL、声学或整机性能 PASS。Host/QEMU 与真实板卡测量相互独立。没有固定的产品认证时长门禁，不存在发布后自动 HIL 监听；原有 E001/认证资料是历史记录，见 [研究执行边界](RESEARCH_ONLY_EXECUTION.md)。

## 6. Dump / Replay 故障闭环

```mermaid
flowchart LR
    A[Runtime fault/event] --> B[固定大小 diagnostics / Flight Recorder]
    B --> C[.apd dump]
    C --> D[apdump info]
    C --> E[apdump extract]
    C --> F[apreplay]
    E --> G[结构化证据]
    F --> H[确定性复现]
    G --> I[根因修复 + targeted test]
    H --> I
    I --> J[Full Verify / regression]
```

Realtime worker 不执行 dump 文件 I/O；dump 可能包含真实人的录音，研究者必须按数据来源的实际许可、访问控制和保留策略实施受限存储与安全删除。

## 7. 分支/证据生命周期（branch lifecycle）

```mermaid
flowchart TD
    A[研究/治理/候选分支] --> B[PR 或终态证据]
    B --> C{终态是否已保存?}
    C -- 否 --> D[禁止删除 ref]
    C -- 是 --> E[核 live SHA / open PR / program terminal]
    E --> F{全部一致?}
    F -- 否 --> G[BLOCK / 不删除]
    F -- 是 --> H[main-push GC]
    H --> I[删除 exact terminal ref]
    I --> J[保留 PR/commit/artifact/evidence 审计链]
```

任何 branch GC 都不获得 DSP、真实 HIL、研究结果准入或历史发布资料的修改权限。
