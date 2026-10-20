# D46 历史消费README与当前索引版本修订

2026-10-12。本修订澄清PLAN P3的旧47快照保持与P4最终README追加的时点关系；原PLAN、SOURCE、199输入binding、正式结果、audit及D45历史快照均保持原字节，不重测，不改任何数值合同、预算、数据角色或原准入。

实际formal及首次独立audit消费的README路径为 `/vsdata/leiwenjun/work/audio_process/audio-pipeline/docs/research/frontend-evolution-v1/README.md`，SHA256=`625af26c7b9bcea99510a45217e6343cbf9de4c7e4fbbffdac7d7436b4af3cef`；该身份在D46原199输入binding及D45原47快照中一致。把所有旧路径要求永远等于当前字节会与获准的追加交付冲突；不静默跳过或替换历史输入。

固定保存顺序：

1. 追加前，经独立审查的保存控制核当前原路径和原binding/snapshot SHA，排他保存完整原字节至 `/tmp/audio-device-d46-consumed-readme-v1.bin`，验证实际备份SHA及原路径起止一致；失败保存receipt并停止追加，unknown先对账，不覆盖或重放。
2. 保存显式映射 `/tmp/audio-device-d46-readme-preservation-v1.json`：original_path/original_sha256/backup_path/backup_sha256；原SHA与备份SHA必须同为625af26c上述身份。保存intent先于备份操作，保留writer身份和实际状态。
3. 独立真实回读保存成功后，才允许按既有P4追加D46索引。后续whole review核198项其余当前输入和该唯一旧README备份，仍保留全部199历史消费身份；当前新README额外绑定新快照。
4. source_input_start_end_equal仅证明formal和首次audit实际执行时点。追加之后不得称旧199路径或旧47快照全部与当前工作树仍相同；旧snapshot和旧binding不改，旧README完整字节保留。

映射只适用于上述唯一README及精确SHA，禁止作为任意源漂移的通用fallback。未来历史复核须显式采用该受审映射，不能自动找缓存或忽略不匹配；两版README身份及保存证明都应进入新快照。本地/tmp保存是实验工件保留，不是Knowledge Provider耐久归档成功。

原D45tool及D46已冻结tool/test不改。独立审查设计方案已PASS，本文和保存控制仍须fresh复审后执行；当前没有追加README。Provider route unresolved/NEEDS_REVIEW、总体native active、D45候选拒绝和产品未批准保持，无外部发布或设备写。
