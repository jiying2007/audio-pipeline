# dEchorate 实测 RIR 有限支撑差距：2026-11-28

固定方法的单次真实测量和独立复验已经完成。科研集成
[#973](https://github.com/jiying2007/audio-pipeline/pull/973) 仍须完成最后head的适用CI、
受保护合并及新的main核验；`VERIFIED_DESCRIPTIVE_RIR_SUPPORT_GAP`不是CI、算法晋级或物理校准资格。

**主要发现：** 在预声明c=343 m/s模型族的1677-sample、约34.94 ms oracle支撑窗下，
22条相关视图的未覆盖有限记录能量下界最小0.975639%、中位2.348868%、最大32.336418%。
它不是模型全拟合误差或纯物理混响份额。数据仍是一个已披露物理房间的11个相关状态，
不构成11个独立房间或22个独立样本，绝对物理t0保持UNKNOWN。

## 公开结果与冻结方法

- [完整报告及22行主结果](RESULT.zh-CN.md)。
- [原始result.json](result.json)：原封字节，包含原件/方法哈希、22行数值、全部metadata和实际runtime。
- [科学摘要](scientific-summary.json)：从原JSON逐项提取，保留完整22行和所有六窗。
- [实际独立复验原回执](independent-receipt.json)。
- [科学图SVG](figure/rir-support-gap.svg)、[22行图数据](figure/plot-data.json)、[图源码](figure/plot_rir_support_gap.py)。
- [执行前方法说明](../DECHORATE_RIR_GAP_V1.zh-CN.md)、[冻结机器合同](../../../../.github/research/frontend-evolution-v1/dechorate-rir-gap-v1.json)、[运行手册](../LONG_TERM_RESEARCH_PLATFORM.zh-CN.md)。

真实执行源码是
[`a058b02582962875ac10e6bb42b928c46c405213`](https://github.com/jiying2007/audio-pipeline/commit/a058b02582962875ac10e6bb42b928c46c405213)，
不是后续报告提交。仅执行一次run，0重试、0产品DSP、0候选、0参数拟合、0晋级。
独立verify原样重算固定22行，不替代原单次执行。

## 完整证据包

[archive-identity.json](archive-identity.json)记录完整包身份：
`audio-pipeline-dechorate-rir-evidence-final-20261128.tar.gz`，**18,833,929 B**，53个普通文件，
SHA256 **`00572fed7173170c118ef723c7e1839015c6e6452961a9491a0287b5ab65b20d`**。
已从成包的tar中逐成员回读，53项SHA全部匹配。

完整包内含原12对象（19,403,164 B）、冻结测量代码10文件、原sealed result/manifest、
来源恢复/许可归属、唯一run命令和stdout/stderr、实际独立复验及图源码/数据。
`sealed/`、`execution/`、`independent-verify/`、`source-recovery/`与`ATTRIBUTION.zh-CN.md`
都是**完整包内部路径**。本公开目录保留可审查的结果，不复制原12个数据对象。
归档位置与取回记录由[#968](https://github.com/jiying2007/audio-pipeline/issues/968)维护；
取得任意副本都必须先核对上面的完整archive SHA及包内manifest，不能以重新打包副本替代原身份。

数据来自Diego Di Carlo、Pinchas Tandeitnik、Cédric Foy、Nancy Bertin、Antoine Deleforge、Sharon Gannot：
[dEchorate论文](https://doi.org/10.1186/s13636-021-00229-0)、
[固定Zenodo记录5562386](https://zenodo.org/records/5562386)、
[官方SOFA镜像](https://sofacoustics.org/data/database/dechorate/)。
按原CC-BY-4.0声明保留署名、来源和修改说明；SOFA内嵌MIT notice也在原对象和包内完整保留。
原数据未修改，新建的是测量结果和图表。不据此推导WSJ语音、训练或其它录音的许可。

## 只复验原结果或重绘图

在精确公开源码a058b025的checkout中、已有NumPy/h5py的环境使用：

```sh
python3 -B tests/validation/frontend_evolution/dechorate_rir_gap.py verify \
  --output /absolute/extracted-package/sealed
```

本次实际Python3.12.14、NumPy2.3.5、h5py3.15.1、HDF5 1.14.6及native模块SHA均载于原result。
完整包记录环境身份，但不声称封装整个操作系统。不要用单独复制的code文件创建不同Git历史冒充原source SHA。

从本公开目录重绘已保存的图（只需已有Matplotlib；不读取RIR、不运行DSP）：

```sh
python3 -B figure/plot_rir_support_gap.py
```

公开图脚本将输入路径改为本目录result.json，并去掉Matplotlib生成SVG的行末空白；
其余绘图代码与完整包一致，固定result SHA仍强制核验。图数据逐字保存；公开SVG只清理行末空白，
XML路径、坐标、文字和图中数值与原图完全相同。原SVG字节仍保存在完整包中，图源码不能执行测量或新增候选。

日期标签使用北京时间2026-11-28；命令原回执的UTC时间为2026-11-27。
