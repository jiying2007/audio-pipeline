# 中文下游 V1：全双工接线覆盖增补

日期：2026-11-06（Asia/Shanghai）；任何模型推理之前冻结。
原合同 `MANDARIN_DOWNSTREAM_V1_CONTRACT.zh-CN.md` 字节不改。
用户要求交互播放与对讲均推进，新增一项具体覆盖：同一真实中文近端在固定工程
播放/回声存在时，实际经过完整 CALL/ASSISTANT 后交给同一固定模型。

## 不随输出改变的唯一新增场景

- 仍只用原 AISHELL 一条录音、同一模型、唯一关键词、阈值、chunk、token、文本
  归一化、模型 flush；没有新模型/配置选择、真人标注或新增数据集下载。
- 近端：原完整录音乘 0.5，Python `round` 到 S16；放置起点为16000样点（1秒），
  末尾增加16000样点零，向下一160样点边界补齐。不裁剪原语音。
- 远端：复用当前 canonical `validation/tools/build_validation_corpus.py` 的
  `render_signal(samples, seed=20261106)`；仅前64000样点有信号，之后补零。
  它是第一方确定性多正弦/包络工程信号，**不是真人、TTS或独立声学语料**。
- 第一麦回声：`echo_from_render(render, [(800,0.25),(1280,0.10)])`。
  第二麦回声：`echo_from_render(render, [(801,0.25),(1281,0.10)])`。
  两麦近端相同，各为固定近端加对应回声；若求和超出 S16 则本场景失败，不自动
  缩放或悄悄饱和。两路组成 interleaved S16。所有生成输入在模型执行前保存 hash。
- raw_duplex 为第一麦；call_duplex / assistant_duplex 使用同一 capture/render
  逐字节输入，实际调用现有 processor 的 render/duplex 模式，不传 capture-only
  或 tuning override。其余三条 capture-only 视图保持原合同。
- 六视图每个仅一次执行，总正式模型矩阵仍为300秒预算。保存各自完整转写、事件、
  消费样点和 CER；三条新增视图仍只有同一个真人句子，不能当成独立说话人。
  KWS 事件真值、负样本暴露与词末时间仍缺失，FRR/FAR/延迟全部为null。

## 额外完成判据

两个 duplex profile 必须实际读到非零 render，调用原完整帧入口并输出等长有限
S16；报告原数据/派生输入、processor、配置与模型绑定。保存 render_activity 与
reference 相关诊断，不从工程生成器或一次识别成功推导真实播放打断、TTS误唤醒、
真人双讲质量或物理对讲效果。描述性 CER 变坏也完整保留，不重设输入增益或阈值。
