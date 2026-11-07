# 双麦 D2：真实执行、失败保全与增益分解结果

日期：2026-11-07（Asia/Shanghai）。任务 #922，PR #923。
本记录对应 [执行前合同](DUALMIC_GAIN_D2_PLAN.zh-CN.md) 和冻结 input-lock；
合同 commit `6c5aa1ba924ba6ab7f72db3e376703e24e1f459a`，不得用后续结果修改其条件。

## 首次执行：编译失败，D2 没有音频结果

实际 source `d2a917a0311ec6d2bdc3414bc78b2d0bc2b7b49a` / tree
`d411092c0752fb3497d45ad33e467f27c78ff61e` 的
[Frontend Research 42321336440 / attempt 1](https://github.com/jiying2007/audio-pipeline/actions/runs/42321336440)
在 job `128246347231` 失败。完整 D1 60 例 run 与 verify 已成功；D2 在 build 阶段失败，
尚未进入 AGC run，没有 D2 波形、分数或质量结论。

完整保留工件 [13552927522](https://github.com/jiying2007/audio-pipeline/actions/runs/42321336440/artifacts/13552927522)：
ZIP 404994669 bytes、2870 members、解压 757296686 bytes；SHA256
`2954e524b95176c83f4be33a1650ab8765b6feee5c09440b7e5a9c5b625f3e49`。
原件下载后按完整大小/hash和安全目录成员核验，10.854325 秒，未重建或替换原件。

`gain-d2/compile/stderr.txt` 的首个真实错误：

```text
dualmic_gain_d2.c:337:66: error: expected ')' before '{' token
```

`main` 的参数校验条件漏了外层 `if` 的一个闭合括号；后续 unused 报错是语法失败
级联。实际 compiler exit=1，0.063826 秒；完整 build phase 为 FAILED，1.869667 秒。
原静态审查未识别该语法缺陷，不能把静态 PASS 当作真实构建 PASS。

修复仅补一个 `)`。原 C 算术、状态与事件处理、四视图、Python scorer/读回、输入锁、
300 秒单阶段和20分钟总预算全部不变；由新 source 重新在 Actions 构建/执行。
这次失败不重标为成功，也不被解释为算法拒绝。

## 当前状态

首次失败已定位，等待单字符修复后的实际完整执行和独立原件读回。
本文件将追加真实回执；当前未获得 `GAIN_DECOMPOSITION_VALID_NO_PROMOTION`，
更没有候选、生产默认、识别收益或听感资格。
