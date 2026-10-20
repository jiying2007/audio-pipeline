# D16 测量补充：拒绝后按实际候选验证重启

日期：2026-10-11；D16算法五行插入不变，原52/26/70+2验收、门限、时长与输入不变。
初次工程运行按计划停止，结果不删除或覆盖。
初次输出根 `/tmp/audio-fe-device-anchor-d16-20261011`，
engineering-result=`13967a3b3e6fcb289a868c999173c0f4310da28a9c5f19cb765b28c8a257ebba`；
engineering-binding=`cf646d8d72119f5fd0987e75b425a8d969c09f0c79ad553c33762a52f0725219`。
strict14、原D8工程/恢复、D11 oracle和D14确认性质先通过，anchor fixture在附加的后续更新断言失败，
P2–P4未执行。不得把此中止当作本候选已经工程通过。

GDB在原fixture第78行实际核：rate=8000，生成器truth=7，旧delay=320，
实际route_candidate_confirmations=1、route_candidate_delay=552、event.error=232，observed/jump=0。
故跟踪器按实际选中552重启确认；错误的是“下一次搜索必等于生成器truth7”的附加假设。
固定10 ms的三点平滑随机信号在有限coarse扫描上可能选中其他峰，不能预设该帧峰值即真值。
初次弱锚拒绝与状态保留断言已走过，但未走完两采样率和强锚正例，不据部分结果晋升。

仅修正新增fixture后续更新断言：count=1、anchor等于实际refined（old+event.error），
observed/jump仍0、旧delay保持；不要求该附加帧恢复到物理truth。
初次主弱锚/强候选以及强锚正例的truth误差断言、信号、种子、rate、门限均不改。
本改动验证“拒绝清零后按原规则重新确认”的生命周期，并保留552错误获取观察，
不豁免正常获取契约；原D9/D13仍独立按其真实固定truth验收。

初次fixture逐字节快照保存在 `device_anchor_d16-attempt0.c`；其hash必须匹配初次binding的fixture身份。
仓内fixture修正后，初次binding该路径不能被声称仍匹配当前字节，恢复用此明确快照映射。
新retry输出根 `/tmp/audio-fe-device-anchor-d16-r1-20261011`，新脚本/source/build/replay/binding单独身份。
最多两次测量修正，本次使用一次；独立复审认可合同纠正后才执行retry。
候选算法不重调、旧负结果保留；总goal保持active，Provider unresolved未正式归档。
