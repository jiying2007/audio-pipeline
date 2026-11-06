# FE-C2-FIXED-DIRECTION-HEALTH-V1：SAFE 观察边界补充冻结

日期：2026-11-06。状态：实施前冻结；不是候选通过记录。

## 实证缺口与源码身份

本补充属于既有固定方向健康保护的状态生命周期修复，不另开声学候选或阈值搜索。
实施基线为已整合 SYNC/BF/profile 的
`9ec381e4f4fa6e6ecd1c9016d3b0711c79343a75`；其中 BF 核心与
`4f2a1c63455736c42ce72f8c7103b35b3b0f9893` 相同。
共同授权和原判据见 `DUALMIC_INTERACTION_INTERCOM_V1_PLAN.zh-CN.md`、
`DUALMIC_FIXED_HEALTH_V1_IMPLEMENTATION.zh-CN.md`。

独立审查使用 4f2a1c6 的真实库，经公开 init/set_quality/process_capture 路径复现：
先执行四帧 LITE hard0，只有第一帧形成一次待确认观察；进入 SAFE 一帧或四帧，
实际输入分别为健康或 hard1；再返回 LITE，输入分别为 hard0 或 hard1。
信号直接复用已冻结健康测试的生成器，未写私有状态。

8k/16k × SAFE 1/4 帧 × SAFE 健康/对侧污染 × 返回原/新目标，共16个组合。
返回原 hard0 目标的8个组合在首个返回LITE帧直接选中mic1；同一当前输入的
新初始化公开pipeline仍为等权混合。候选输出与所选麦误差0 S16，距等权的
最大误差4635–5021 S16。SAFE输入已健康或换目标都未终止旧arm。
返回hard1的8个组合由已有目标一致性规则重新计数，没有提前确认。
原始输出和身份记录保存在 `evidence/dualmic-fixed-health-safe-v1/`。

根因：SAFE完全旁路BF，既有fixed↔tracking私有epoch逻辑没有被调用；
set_quality也没有终止观察epoch，因而暂停前的确认或恢复证据可以跨SAFE使用。
这是新固定保护引入的可执行状态缺口，不以缩窄结果文字代替修复。

## 唯一允许的生产变化

只在 `src/core/ap_pipeline.c` 的 `ap_pipeline_set_quality()` 增加私有状态失效：

- 参数合法、BF stage已启用、quality确实变化，且进入或离开SAFE时，清
  `fallback_hard_arm_count`、`fallback_recovery_count`，并令
  `fixed_health_counter=3` 重建观察相位。
- 保留已确认hard的active/fault、目标通道、fallback lag、gain、历史及方向状态。
- 重复设置同一quality不能打断确认或恢复；非法quality仍先原子拒绝。
- 使用 `AP_BUILD_STAGE_BF` 编译guard；无BF构建不访问BF私有状态。
- 不改hard/recovery阈值、四帧节拍、两次确认、八次恢复、增益、输出公式或crossfade。
  不增加状态、公开API、metrics、PCM缓冲或分配。

新增编译源码路径只有 `src/core/ap_pipeline.c`；测试仅扩展既有
`tests/test_beamformer_health.c`，保留全部原测试。CMake/API正文和共同版本身份
由根工作包统一处理。

## 冻结回归与验收

1. 将上述16个公开CALL反例加入现有测试，先用未修生产库实际执行并保存失败。
   返回LITE的新epoch中，前四帧仍等权，第五帧的第二个有效观察才确认对应可靠麦。
2. 两采样率、CALL/ASSISTANT验证重复set_quality(LITE)不阻止两次确认或八次恢复；
   非法quality返回AP_EINVAL，按公共state_size读取的整个opaque状态字节不变。
3. 已确认hard经过SAFE（mic0旁路）再回LITE/FULL，可靠路由立即保留；
   SAFE和原fixed/tracking相位都不能借用未完成观察。不是SAFE坏mic0保护。
4. 已确认hard后先获得七次恢复观察，进入SAFE；SAFE输入分别为健康/再次污染。
   返回LITE后须重新累计八次有效观察，第七次不得退出、第八次才退出。
   使用冻结的0.75增益差正常输入，使可靠单通道与等权输出可从公开PCM直接区分。
5. 默认tracking-ON及仅tracking-OFF的完整宿主63项CTest，以及相关health/module/
   contract/realtime定向测试通过；保留before-fail/after-pass。所有既有HPF恢复
   起点勘误、原失败记录、旧threshold保持。steady-tracking旧PCM/状态对照不变。
6. 现有预算不变：每次配置/构建/测试300秒上限，无新搜索、训练、远程CI、push或PR。
   仅第一方已曝光工程回归，非真人、独立盲测、KWS或SSC305物理证据。

结果另存新文档；既有4f2a1c6结果继续保持原身份，不改写为包含本修复。
