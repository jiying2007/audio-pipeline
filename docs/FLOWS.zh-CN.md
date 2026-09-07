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
    P --> H[真实 DUT/HIL/Product Certification]

    X[research-validation] --> S
    V -.禁止反馈 optimizer.-> S
    B -.禁止进入 optimizer.-> S
```

关键规则：validation-grade/blind 不能用于挑参数；重复使用同一数据不是新的独立确认；任何搜索都不能自动改 shipping defaults。

## 4. PR → main → Release

```mermaid
flowchart TD
    A[变更分支] --> B[精确 HEAD PR]
    B --> C[Impact + Fast Gate]
    C --> D[Full Verify\nGCC/Clang/Sanitizer/TSan/CodeQL\nArm/QEMU/Resource/Perf/Audio/Lab]
    D --> E[required summary = success]
    E --> F[protected squash merge]
    F --> G[exact main Full Verify]
    G --> H[main summary = success]
    H --> I{版本是否已存在 immutable Release?}
    I -- 否 --> J[构建/测试/SBOM/attestation\ntag + publish + immutable]
    I -- 是 --> K[EXISTING_RELEASE_IDENTITY_PASS\n不重新 build/tag/publish]
```

Release-neutral descendant 不应为了治理/文档变化制造新 SemVer；release-bearing 变化必须按 SemVer/CHANGELOG 契约发布。

## 5. 软件商用就绪 → 真实产品认证

```mermaid
flowchart TD
    S[software-commercial-ready] --> R1[audio-validation READY]
    S --> R2[audio-builder READY]
    S --> R3[audio-target READY]
    S --> R4[certification-archive READY]

    R1 --> ER[真实 Extended Real\nvisible + blind + repeatability]
    R3 --> HIL[真实 DUT HIL\n1h / 8h / 24h]
    ER --> E1[EXTENDED_REAL_ENABLED=true]
    HIL --> E2[HIL_ENABLED=true]
    R2 --> E3[E001 Activation Preflight]
    R4 --> E3
    E1 --> E3
    E2 --> E3
    E3 --> READY[E001_TRUSTED_INFRASTRUCTURE_READY]
    READY --> PC[Product Certification\nshipping-approved policy\n>=72 h]
    PC --> ARC[immutable product-lifecycle receipt]
    ARC --> PASS[product-certified / PQ authority]
```

`READY` 只是基础设施 readiness，不是 HIL/PQ/Product Certification PASS。Hosted CI、QEMU、公开数据或较短 soak 均不能替代最终物理证据。

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

Realtime worker 不执行 dump 文件 I/O；dump 可能包含用户语音，产品必须定义访问控制、保留周期和安全删除。

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

任何 branch GC 都不获得 DSP、HIL、Release、Product Certification 或 PQ 权限。
