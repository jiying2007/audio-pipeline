# D7观测存储修订

日期：2026-10-10；状态：FROZEN_MEASUREMENT_AMENDMENT。
原计划DEVICE_MULTIFRAME_D7_PLAN.zh-CN.md保留不改。首次严格build exit2：
`pipeline resident state exceeded public ceiling`。原configure/build日志位于
`/tmp/audio-fe-device-multiframe-d7-20261010`，没有算法输出可批准。

不放宽state上限，不改变pipeline state或公共ABI。观测历史改为临时ap_sync.c内部
Host-only线程局部旁路表：16个state指针槽、每槽2048点，原init时明确清零该slot。
超过16槽立即中止测量，不伪造结果；不用于shipping、资源测量或多线程资格。
原历史完整性、三个固定窗口、单次固定执行集、算法决策不改和等价验收均保持。
临时header恢复原字节；唯一源码差异必须为src/sync/ap_sync.c。
新目录build-v2及新的日志后缀保留初始失败，不覆盖已有build/命令日志。

CMake3.16的CTest用实际build cwd执行；显式核14项、100%通过且0失败，
禁止把零测试exit0当成功。这是执行环境修正，不改测试或接受要求。
