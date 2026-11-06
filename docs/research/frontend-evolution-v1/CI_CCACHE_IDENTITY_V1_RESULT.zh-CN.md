# CI ccache 工作目录与源码身份修复：结果 V1

**结论：五项实际 CMake 配置均满足预先冻结的身份预期。** 唯一生产改动是在
`.gitignore` 中增加 `.ccache/`。人工缓存文件不再使干净源码身份带上 `-dirty`，
缓存外未跟踪源码和已跟踪源码修改仍产生 `-dirty`。身份生成和严格比较均未改动。

## 精确身份与实测

- 基线：`9a9202eca32cfa03d92644f5735bfc2c2429efbc`。
- 先提交的冻结合同：`a0e83e2bbfca4577697efe15e2683adf87118755`。
- 单行候选：`f6206a2e30ebe45bcba4972afeca560ba62130fb`。
- CMake：本机实际 `3.31.6`；只配置，不编译或运行 DSP。
- 五次配置及相关检查累计 `1.4203091800009133` 秒，冻结预算为 `300` 秒。

下表 `F` 指冻结提交完整 SHA，`C` 指单行候选完整 SHA。每个配置命令均 exit 0；
“身份相等”表示生成 revision 是否严格等于该阶段的 40 位 HEAD，并非执行了完整 replay。

| 情景 | 配置前真实 status | 生成 revision | 与 40 位 HEAD 身份相等 | 预期核对 |
| --- | --- | --- | --- | --- |
| before-clean | 空 | F | 是 | PASS |
| before-cache | `?? .ccache/` | F + `-dirty` | **否** | 已复现缺口 |
| after-cache | 空 | C | **是** | PASS |
| after-untracked-source | `?? src/ci_identity_untracked_probe.c` | C + `-dirty` | 否 | PASS，保持拒绝 |
| after-tracked-source | ` M src/ap_build_info.c` | C + `-dirty` | 否 | PASS，保持拒绝 |

before 和 after 使用同一个人工 cache 文件，SHA-256 为
`8de74c4d5b253d5686a3910c38d73ac2a611ba7681d91965b575d5eaf2bbd05a`。
before 的 `git check-ignore` exit 1；after exit 0，实际命中
`.gitignore:4:.ccache/`。普通未跟踪源文件的 check-ignore 仍 exit 1。
测试结束已恢复已跟踪源码原字节，并删除两个探针文件和空 cache 目录；最终
`git status --porcelain` 为空。CMake、runner、source gate 和 `src/include` 均未修改。

## 原始执行命令

脚本在外部 scratch 中执行，字节一致的副本保存在本记录的证据目录。首先在干净
冻结提交执行 before；随后仅提交 `.gitignore` 候选，再对同一人工 cache 执行 after。

```sh
PYTHONDONTWRITEBYTECODE=1 python3 /workspace/scratch/b74ab3415ba4/ci-ccache-identity-v1/run_identity_probe.py --phase before --source /workspace/scratch/b74ab3415ba4/audio-dualmic-cache --output /workspace/scratch/b74ab3415ba4/ci-ccache-identity-v1/evidence --build-root /workspace/scratch/b74ab3415ba4/ci-ccache-identity-v1/build --cmake /workspace/scratch/b74ab3415ba4/build-tools/cmake/data/bin/cmake
PYTHONDONTWRITEBYTECODE=1 python3 /workspace/scratch/b74ab3415ba4/ci-ccache-identity-v1/run_identity_probe.py --phase after --source /workspace/scratch/b74ab3415ba4/audio-dualmic-cache --output /workspace/scratch/b74ab3415ba4/ci-ccache-identity-v1/evidence --build-root /workspace/scratch/b74ab3415ba4/ci-ccache-identity-v1/build --cmake /workspace/scratch/b74ab3415ba4/build-tools/cmake/data/bin/cmake
```

每个 case 的 `command.json` 保存完整实际 CMake 参数。可迁移重放使用脚本的
`--source`、`--output`、`--build-root` 和 `--cmake` 参数；before 源需为干净冻结提交，
after 源需应用精确候选，输出和各 case 构建目录必须新建。

## 原始证据与边界

[证据目录](evidence/ci-ccache-identity-v1/README.md) 保留脚本、五次配置的 stdout/stderr、
退出码、配置命令、生成头文件、status、check-ignore、实际 tracked diff、文件哈希和
累计时间。`manifest.json` 为目录内文件逐一记录 SHA-256 和字节数，不把自身纳入自身。

人工文件仅复现工作缓存存在这一条件；未运行 ccache、未恢复 Actions cache、未观察
远端 workflow 失败或成功。未运行新 DSP/完整矩阵，未调整声学阈值、300 秒预算或
既有测试超时，未显式设置 `AP_BUILD_SOURCE_REVISION`。本记录不替代最终精确提交的
远端 Verify；真实设备与声学结论不在此范围。
