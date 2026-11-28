# F07-LT2：联合 suppression gain / CNG 合成路径有限诊断

关联 #980 / #657。实际科学执行源码 `dac4289a4d2298367b4a9d8246f30c095f352851`；native 二进制来源 `dd7d5d8892ebe6ad767aaa1d6112638df5474207`，Frontend Research 46135692791 / artifact 15259871410。科学源码与结果发布提交分开保留。工程合同仍不授权声学执行，另行冻结的有限 admission 只允许本次两臂调用。

## 实际结果

只使用 #977 已披露开发样本 p1-ula4-70-fir33-none，16 kHz mono，主窗口 [97600,126400)，合成支撑 [1525,1976)。2 次 / 32 秒，0 重试、0 训练、0 本地编译、0 新语料。中性臂完整 final、linear、原始 selector 行与字节完全复现原件，随后只执行一次 unity-support 干预。

| 固定指标 | Neutral | Unity |
|---|---:|---:|
| double-before SI-SDR (dB) | -4.784093017112171 | 12.755829672724907 |
| normalized MSE | 0.7812664693014378 | 0.052925468812986265 |
| far-only echo/output energy ratio (dB) | 27.512950467837094 | 27.512950467837094 |
| peak | 0.03106689453125 | 0.03106689453125 |
| RMS | 0.0018599879585802885 | 0.0020037624659045876 |

主窗 SI-SDR +17.539922689837077 dB，NMSE -0.7283410004884516；原始 selector/gain 控制、已定义 CNG 和上游观测 binary32 字段在 4000 块保持相同，451 个支撑块确切干预。linear 全段相同；final 28,259 个采样点改变，只在实际 OLA 传播支持区间内（第 97,667 到 126,587 个采样点，零基）；远端各固定块指标及其他三个近端窗口完全相等。全段 RMS 增加按事前冻结的保守方向规则记录为幅值权衡，而非已证明音质损失。

**NEAR_END_GAIN_TRADEOFF_OBSERVED_NO_PROMOTION**。这支持该固定窗口中联合 gain-controlled suppression/CNG 合成路径的近端保真作用，不支持把效果单独归因 RES、CNG 或推广为默认策略。真实上部频带合成在 16 kHz 未被激活；生成器未定义的 CNG 虚部端点未读，原始 upstream 潜在未初始化端点读取没有修复或认证。OLA 历史允许变化，不声称隐藏状态全量相同。无独立数据确认、无 SSC305 实机或生产资格。

## 完整证据

- [完整机器结果](result.json) SHA-256 `b972a342299cc28099e265e742e190a402c7ec8ac4ab03db9cd0b162d9c05ffa`。
- [独立原始字节复算](independent-readback.json) SHA-256 `17c49807bcefa89ed5d88ded453c5d1fbcf30f3e99b17331a81f1b9de0960739`，所有指标容差 0；独立读回 native calls=0。
- [完整封存包回读](archive-readback.json)：95,738,949 B，99 个普通文件成员，SHA-256 `7069cabd592baefe6df7ff06b7499124afbb4390e7598a2eea917386d0fda0f9`，原始 PCM、逐块 trace、方法源码、固定 native 库、成功及失败 CI artifact、host 回执与 manifest 均保留于私有归档；历史 #977 完整归档按原身份引用，不再次发布原始语音。
- 初次工程失败 46135361436 / artifact 15259363166 不改写。原工程 Verify 46135692845 78 success / 1 skipped / 2 failed，旧官方语音数据获取超时；受保护主线资格另行核验，不借用旧检查或关闭失败。

本目录只发布已经取得的固定科学证据，不自动触发任何语音调用。合并与 fresh-main 验收尚不由本结果文件声明。
