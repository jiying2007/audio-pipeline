# D48 收口前 README 历史身份保全

2026-10-15。D48新增索引条目前，先排他保存当前README完整字节；本记录不是保存成功回执。当前README=ac998973955f56f63cc7e0bd73e203c595e21c71d703f001f0ba43074914ecb8，25274字节。精确历史消费者 `/tmp/audio-device-d46-review-snapshot-v1.json` SHA=74ad422a054e9ba245025b1b59dfecd9560bfb85893d29090f5934deb48b568b，其files中此README身份相同。D48正式binding本身未锁README，不能制造其曾消费该文件的说法。

冻结单一显式映射：原路径 `docs/research/frontend-evolution-v1/README.md` 的上述ac998身份，只能解析到新 `/tmp/audio-device-d48-consumed-readme-v1.bin` 完整字节，且SHA与长度必须完全一致。使用新排他intent/receipt `/tmp/audio-device-d48-readme-preservation-v1-intent.json` 与 `/tmp/audio-device-d48-readme-preservation-v1.json`。保存前后核原文件、备份、本文、writer、历史snapshot身份；独立回读实际成功后才允许追加README。

旧625af26c身份与 `/tmp/audio-device-d46-consumed-readme-v1.bin` 保持，不覆盖或合并；原D46的247项snapshot保持字节不变。不能为其他漂移提供通用fallback。新索引完成后当前README作为新身份进入D48最终快照，历史映射与当前身份分开报告。

暂存控制只写上述新/tmp路径，必须当前线程和同D48任务策略允许；失败或未知保留先对账，不重放。不会执行DSP、统计重算或改写任何旧测量根、binding、source和结果。算法与产品准入仍false。
