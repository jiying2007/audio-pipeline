# S2-A 原件回读的单路径运输修复

日期：2026-11-28（北京时间）。修复基线：`4eec2329be9f2138c7ac73e8dd59026f3dc0a3ba`。
这是 [#970](https://github.com/jiying2007/audio-pipeline/pull/970) 合并后 fresh-main
实际暴露的运输失败，纳入 [#968](https://github.com/jiying2007/audio-pipeline/issues/968)
的科研平台实施。以下边界在修改运输逻辑和取得新结果之前冻结。

## 原始失败身份

- Verify run：`46049679143`，attempt `1`，push head 为上述修复基线。
- Job：[`140679755356`，`quality / frontend-s3-t3s2a`](https://github.com/jiying2007/audio-pipeline/actions/runs/46049679143/job/140679755356)。
- 原资格 step 4 成功，实际打印 `FE09_T3S2A_ORIGINAL_APX3_FBS1_POSIX_SPOOL_SOURCE_VERIFIED`。
- 原上传 step 5 成功。名称为 `frontend-fe09-t3s2a-posix-spool-46049679143-attempt-1`，
  [artifact ID `15224152314`](https://github.com/jiying2007/audio-pipeline/actions/runs/46049679143/artifacts/15224152314)。
  上传日志记录 4 个成员、原 ZIP 大小 `6026` 字节、SHA256
  `739ee7cd788e22373e0b0811e8e7488ee7f808ad149187d39b060da9fa9226fc`。
- `2026-11-27T18:35:12Z`，step 6 按上传 ID 下载失败。日志先列出相同 ID、名称、大小和摘要，
  随后报 `No artifacts found for ID: 15224152314`；原独立四成员回读 step 7 因此未执行。

该版本 workflow 的下载 `with` 仅显式传入 `artifact-ids` 和 `path`，没有显式传入
`github-token`、`repository`、`run-id`。Action 日志可打印默认 repository/run-id，不能
据此声称日志没有 run-id。现有日志证明列举后取件失败，不能单独确定 GitHub 底层服务根因。

## 冻结的最小修复和验收

1. 只处理实际失败的 S2-A 路径，保留原上传名称、上传 step ID、4 成员和 30 天保留期。
2. 复用既有 `fe09_same_run_artifact_visibility.py`，仅加入 S2-A 精确名称前缀。
   在原上传后、原下载前，核对当前 repository/run/attempt/head、execution source 和真实上传 ID。
3. 原 SHA 固定的 download-artifact v7 保持不变，显式传 token、repository、run ID 和原上传 ID，
   使有界见证与下载使用相同的 REST 身份。没有名称回退、历史产物替代或额外下载重试。
4. 保留原 helper 的共享 8 次请求上限、单请求 10 秒、间隔最多 2 秒、大小/过期/重复身份拒绝。
   原 job 的 25 分钟 timeout、科学执行、四成员 SHA256/source 复核和全部资格阈值逐字保留。
5. 复用现有离线元数据 fixture，覆盖精确身份、旧 attempt 共存、错误 ID/source/repository、
   不完整列表及请求预算；检查 S2-A 成功条件、原上传 ID、显式 REST 参数和独立回读仍相连。
6. 独立比较所有既有 helper 函数/类，以及无关 job 和 S2-A 原科学 step 的字节/结构。
   只有新 exact-head required summary 和 protected fresh-main 的实际结果才构成新的 CI 资格。

合成 HTTP 元数据只验证运输语义，不是实际产物、DSP、声学或物理设备证据。
原失败保持失败，不因新修复重写；本地不重跑原科学任务，不修改 SDK、算法或版本。

## 验证记录

本地执行下列命令，285 项离线测试通过（0.199 秒）：

```sh
python3 -m unittest discover -s tests/validation/frontend_evolution -p test_fe09_same_run_artifact_visibility.py -q
```

新增两个测试类复用原 REST 和 snapshot 矩阵，没有运行 DSP、声学 replay 或 live API fixture。

源码比较确认：原 helper 的 14 个函数/类、原测试的 22 个类/函数全部逐字不变；S2-A
以外的 workflow 字节不变；S2-A 原资格执行、上传与独立 reader 的原字节不变。
YAML 结构差异只有一个 guard 与三个显式下载输入，job timeout 保持 25 分钟。
Python 3.8 AST 检查及 `git diff --check` 通过；这不是实际 Python 3.8 解释器执行声明。
当前 `ci_impact.py` 判定全部四个修改路径为 SemVer-neutral，不改 SDK 版本。

新 exact-head/main 的实际运输和 required summary 验收仍待执行；原 fresh-main 失败
没有被本地合成测试替代或重判。后续实际 CI 身份在 #968 中登记。
