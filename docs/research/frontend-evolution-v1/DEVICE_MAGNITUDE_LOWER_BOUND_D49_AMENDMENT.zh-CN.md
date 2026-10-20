# D49 有符号幅度差的数值合同澄清

2026-10-15。原PLAN=e8ffa4a9db2165b80f036c4791fdf1af6b7ca5215a7cc2daec47d8e8d2cbb119保持原字节。独立计划审查发现1项MINOR：P2“所有新值须finite且非负”若作用于中间差d，会错误拒绝合法的预测幅度大于当前幅度案例。实际尚未实施或执行，不制造运行时失败。

本修订只澄清数值合同，不改变公式、严格门槛或验收：rmag=sqrt(P)、pmag=hypot(pr,pi)、L必须finite且非负；d=rmag-pmag必须finite，但允许为负或零。仅d>0时计算L=d*d并检查有限非负；d<=0时直接设L=0.0（正零），不先平方负数。预测幅度过大和P0/J正等已计划known-answer均按此定义输出L0/floor0，模型valid与原raw J不被抹去。

原H/pr/pi/P/J全计算及finite检查保持，不因新floor关闭跳过或把原J改成L。原count/warmup、P>1e-12、严格L>2N、post-NS max、libm binary64顺序、binary32输出、状态与诊断schema、独立审计及原960评分/24near/72no-near/4pureecho准入均保持。没有新增容差、系数、数据选择或超时调整。

实施、独立计划复审和后续preflight/writer必须同时消费原PLAN与本AMENDMENT的精确身份；该MINOR需fresh独立复审闭合，当前不自批。D48已完成证据不改，D49尚未登记/实施，promotion_allowed=false、shipping_approved=false，总体目标active。
