# 同步实施修订：保留原索引锁，改用独立worktree

2026-10-20。原计划的stash路径未执行成功，未生成stash、未移除原dirty。经实际核验，原仓`.git/index.lock`为空文件，mtime=2026-10-14T07:19:09.316704Z、inode181937933、uid1002；/proc未发现打开该锁的进程或本仓存活git进程。保留该锁，不直接修改.git或反复重试stash。

已完成完整保全：`/tmp/audio-sync-20261020-presync.tar.gz`，60750842字节，507成员逐SHA核验且源起止一致；manifest `/tmp/audio-sync-20261020-presync.json` SHA=d424f5e7587c9d4b76fae4232fd8a45b9570f868e53bb3a2e591193a132bbd66。原研究README字节另存 `/tmp/audio-sync-20261020-readme-original.bin`，SHA=0f4c9163825021798fd655bcdab6f20f0c2e9825aca0c145d24155980ae9295f；用于保留D48/D49已消费的原身份。备份核验代码初次曾将RTK格式化输出当NUL路径，因regular-file守卫拒绝且未生成archive；改为子进程原始Git NUL输出后实际成功，不隐去该静态/输入解析失败。

改用 `/tmp/audio-pipeline-sync-20261020` 独立worktree、分支 `codex/device-capture-sync-20261020-land`，精确从c416a5f8e44b36a6af5be4dc53c71456dd6ba5ef创建。原工作树的main和dirty字节不变；原目录当前临时分支codex/device-capture-sync-20261020仍指572b0e34，保留为工作上下文。用户可在新worktree审阅已同步/提交版本；不声称原目录索引已修复或原main已更新。

新worktree只复制经筛选的原始字节，手工源码/文档整合使用apply_patch；原3个与远端相同的RealMAN文件不重复引入。有效科学研究记录及offline源码可提交，机器运行handoff/context/native维护文档仍留原现场和备份。新提交说明不可移植/tmp依赖，不擅自将全部历史测试加入默认CI。原wave/session/CSV不改内容，数据角色/隐私及无push边界保持。

Runtime登记也已按用户新范围切换：旧D49本地任务aborted用于replan，保留其真实拒绝及待独立审计状态；总体native优化目标未取消。新同步任务task-550b1662f6982554f8ac4b4f active，required plan/validation/review，不能把本地任务切换当科研或产品完成。
