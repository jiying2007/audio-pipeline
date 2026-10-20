# D38 待用收口脚本的审查修正

2026-10-11。独立 whole 审查核验30项原快照身份全部匹配，诊断/数值/披露部分PASS；待用控制脚本发现MAJOR-1，整批放行暂FAIL。没有执行原finalcheck或closeout，没有实际未知请求重发或数据破坏证据。

问题：旧closeout先执行Runtime写命令，再用x写回执；旧回执或执行后中断时，重启可能先重发再拒绝。旧writer与snapshot保持。新增 /tmp/audio-device-d38-closeout-v2.py 与 finalcheck-v2.py；closeout在任何Runtime写前检查整批receipt/intent和旧操作文件均不存在，每命令发送前x写intent，绑定command/thread/writer/time。已有intent或receipt拒绝未知重发；异常先写null/部分输出/elapsed再传播，不自动重试。finalcheck在检查命令之前检查整批回执均不存在。

v2仅抽取已锁旧脚本的commands赋值表达式，未执行旧脚本；原完整快照仍保留。新 /tmp/audio-device-d38-snapshot-v2.py 延伸旧30项快照，加入旧snapshot、新控制脚本、本补充与HANDOFF，建立新review-snapshot-v2.json；不重跑主测量/独立audit。

MAJOR-1须fresh定向/whole复审闭合；当前上下文维护仍required，v2尚未执行。HANDOFF与checkpoint2已持久化，D38 localgoal仍active/open3，native总体目标active。只有维护解除且审查通过后才写REVIEW并执行v2；不能以数值PASS替代Runtime门禁或产品资格。
