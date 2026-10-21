# D6：独立审查发现的失败回执修复

日期：2026-10-10；状态：IMPLEMENTED / VALIDATION_AND_REVIEW_PENDING。

授权：提高总预算至12000000 tokens并继续；仅本地修复、验证及既有独立审查者复审。
基线：本地HEAD 572b0e34a8a8e5663397ce16e378209ba9058d4d，D5冻结23文件快照
SHA256 1dc71a47c178606ef2654f6a575b10f1e8ed76732698489d172f22a267534185。
独立审查发现blocker=0、major=0、minor=1；Spec/Quality均PASS WITH MINOR。

## 冻结缺陷、边界与验收

缺陷：run_logged在超时及stdout/stderr超过1Mi字符时，在保存命令回执前抛错。
外围failure.json不能替代该命令的参数、退出或超时身份及已有输出。
仅修复命令失败取证，保持失败传播和成功判定；不改变输入锁、研究计划、算法、配置或验收阈值。
回执记录timeout_seconds、timed_out、execution_error、output_truncated及原输出字符数，
保存的stdout+stderr最多1Mi字符。此上限约束回执文本，不宣称子进程capture_output内存有界。
TimeoutExpired部分输出可能是bytes，UTF-8替换解码；未知退出码明确为null，不能伪造成功。
启动OSError也先记录再传播。旧D3/D4/D5制品原样保留，新源码必须使用新回放身份。

验收：超量、超时、启动失败三类负例保留命令回执并拒绝成功；19项工具/运行器测试通过；
完整docs gate通过；新身份16例70固定+2复跑回执验证通过，PCM/metrics逐字节等于旧D3；
既有独立审查者复审修复及新快照。预算：1次完整回放、1次完整docs gate、定向测试及复审；
同类失败两次后重规划，不覆盖失败目录。数据仍为已查看development，不能升级blind或独立声学证据。

## 保留结论

D4候选保持REJECTED_REAL_ROUTE_RECOVERY_REGRESSION；D5仅测量，不批准算法候选。
设备声学、shipping、E001、owner和Provider归档资格独立。本次未授权SCM写或设备操作。
