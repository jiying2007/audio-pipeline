# 设备SYNC D4：拒绝直接套用唯一性检查

日期：2026-10-10；实验依据：[冻结计划](DEVICE_SYNC_D4_PLAN.zh-CN.md)。
结果：**REJECTED_REAL_ROUTE_RECOVERY_REGRESSION**；promotion_allowed=false；data_role=development。

原产品源码未改。仅在临时第一方快照的大跳变路径前增加原有ap_sync_peak_is_unique检查，
阈值/三次确认/其它算法保持原值。严格Host构建通过；14项CTest中13通过、1失败。
失败是test_clock_drift_and_route_jump要求真实路径改变后delay_jumps增加的断言。
因此该直接移植破坏了原有路径切换恢复，候选拒绝，不能用设备误跳减少抵销该回归。

16轮设备数据以tracked1/fixed1各执行一次，共32诊断回放完成；配置/样本/有限metrics核验。
其中10个D3已有fixed1对照输出逐点相同；其它场景新执行fixed1，不伪称已有旧对照。
结果哈希：9f070dee7f160935a5141046e7861f940f7378c0f848d814e8130825e059da2a。
工件：/tmp/audio-fe-device-sync-d4-20261010/result.json；候选源码/库/运行器/PCM和原CTest失败保留。
首轮编排因错误使用不存在的PCM.digest属性而退出，首轮case-01原样保留；
修正临时脚本为sha256(pcm.data)，另建rerun-case目录，不覆盖失败。
失败不属于AP运行器或采集损坏；不能借此宣称第一次回放成功。

远端运动诊断延迟集合：
[
  {
    "case": "vocaltest_rpm240/runs/run-2908630469-2466",
    "delay": [
      1,
      2
    ],
    "baseline": [
      1,
      2
    ]
  },
  {
    "case": "vocaltest_rpm480/runs/run-4823498871-2661",
    "delay": [
      1,
      2,
      3
    ],
    "baseline": [
      1,
      2,
      3,
      172
    ]
  }
]

本轮结论限定为：短窗唯一性检查直接用于大路由跳变不满足已有恢复契约。
后续先测多帧相关证据和粗搜歧义，再冻结另一项因果假设；不得为通过已知80ms路径测试
而直接调大跳变阈值，或更换接受规则洗绿。输出能量/172ms变化不等于ERLE/近端保真/KWS通过。

最新核对main=39a445d4c21d2f716e6602450a0bf944f248383b，新增A2元数据涉及共享docs gate。
本地原基线和dirty保持；后续整合必须保留新main的A2门禁入口。
Git2.25.1维护子进程测试、独立review、Provider unresolved、设备/独立声学仍待闭环。
本轮未提交、推送、合并或部署。
