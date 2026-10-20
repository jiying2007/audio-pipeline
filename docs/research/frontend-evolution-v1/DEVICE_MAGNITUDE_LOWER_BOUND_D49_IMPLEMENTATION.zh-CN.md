# D49 幅度下界保护实现冻结

2026-10-15，experiment=FE_DEVICE_MAGNITUDE_LOWER_BOUND_D49，primary=adk-planning-execution-loop。本文件冻结新 C、正式矩阵入口及已完成前置验证；正式执行控制尚待独立审查和 CP4 verified 后唯一执行。不是正式结果或声学通过声明。原 PLAN=e8ffa4a9db2165b80f036c4791fdf1af6b7ca5215a7cc2daec47d8e8d2cbb119、AMENDMENT=9e7ddaa0e82d434f3d2addc631d878562c35719a21bb03e98dcf7a810ec87a65、PLAN_REVIEW=772cfe8f5328eee065fcb47ccf0d13b19c750c0ca9eb262d68569e8576d0d06d共同有效，不改原文或门槛。

## 唯一算法变化与冻结身份

更新前复数拟合、原有序 P/J/finite guards 保留，仅将保护门控和归一化量 J 替换为 L：double rmag=sqrt(P)、pmag=hypot(pr,pi)、d=rmag-pmag；d允许负，只有d>0时L=d*d，否则正零；严格 P>1e-12 且 L>2N 时按原 float sqrt(clamp(L/P)) 输出。原 model valid、raw J、P0/J正与 overshoot 不被抹去。该量相对模型预测定义，可能误保或漏保，不是近端真值。

新 NS fork 只替换 include/函数名称及 floor 调用，逐字对照已核；EMA/count/warmup/reset/noise、RES smoothing、post-NS max、FFT/OLA/AGC/VAD 时序不变，不新增状态、频带、系数、平滑或标签输入。预测操作数重算带来额外double sqrt/hypot及运算，目标板成本未知。

| 源码（tests/validation/frontend_evolution 或 tools/codex_assets） | SHA256 |
|---|---|
| device_magnitude_lower_bound_d49.c | fbcb151d7543fdb3e2d006aa9670ffc8233cb331d0da75c2d6aa1da10fae0dd9 |
| device_magnitude_lower_bound_d49.h | 727c80d5474ad1d73504a4ae71ac8249ad2e8707d01a8cdd4ec6d25f83d0e4e4 |
| device_magnitude_lower_bound_ns_d49.c | 92d142c7a409412937f5bf5266e1b9c495460ae7079754377f56889d0bad5618 |
| device_magnitude_lower_bound.py | 7d2845003b3a107e41b3a582d0ab77648508b8b6cd06f77dde5d1d68c2b74a1e |
| test_device_magnitude_lower_bound.py | af1318f929adbed5a44ff52d007c4524396889cce8eab78e90831e600647637b |
| device_magnitude_lower_bound_matrix.py | 1d2add266cd1381d7dcb68892e4e60ef240d1654b777f4f8c1656bb87aa7c3bd |
| test_device_magnitude_lower_bound_matrix.py | fdce266393b58dd8d262b7a5187edfe62aa504e496149fee741f9dc97f110d90 |

## 继承的测量合同与前置证据

matrix 直接调用冻结 D48 observe/common_observation 与原 D42 development_admission，未改评分函数。D48 tool=27b5ae3e00d9e74e2cbbc1c8b37a185119d493e295243236ff1b1e936a6c3fed、test=4f9a5a536bdb699119d72ef62c5b3691611bf91c7b08d0596ac6376010bc5c85。D47 C/NS/header仍原固定身份。原21列power、25列bins保持；baseline_trace明确将原 current P/J/overshoot 排除在允许变化字段之外，要求与D48 monitor逐行exact；floor派生与candidate自然下游独立。monitor四输出byteexact、candidate bypass、普通NS/RES控制与状态、repeat七输出、future前1247帧保持。

内部preflight先literal pin source/真实链，再执行完整D48语义preflight，保留11744输入、1884工件与13671最终快照并冲突拒绝，当前返回13687项锁定身份。正式外层控制另将本IMPLEMENTATION、新执行控制及全部新proof/intent纳入source_sha256起止冻结；最终独立审计和快照须合并内外两层映射，不得只审内部13687就宣称完整新阶段闭包。D48真实基线decision明确为MEASUREMENT_CONTRACT_VERIFIED_NO_PROMOTION、measurement_only=true、两臂accepted=false，未套旧算法decision文本。

已有实际验证：

- [C前置记录](DEVICE_MAGNITUDE_LOWER_BOUND_D49_C_PREFLIGHT.zh-CN.md) SHA=db88a55d3b78501759bfbdfa25bdfff9db3dacb2cd23a74f307f68e1d7aa8cf1：私有唯一compile/selftest/invalid-argc实际0/0/2；receipt930ff37d927d11862411d8a2739d00611a9c5b1224a0584e8341319d2a916019，intent9e0f47e10d0aaefade22d011dad684ce6a38664f9e970be7d8db742c7d9ee538，runner053b5201657075098d2814d7559c72b8fbf36b466ae9b9f5a0722d7c313bed1e。已独立实际附核，无旧成功套件重跑。
- 新matrix 8项边界单测678056 exit0，0.068秒，覆盖基线decision/role/approval、缺case/input/artifact、SHA冲突、非法root/symlink和raw P/J/overshoot漂移；非仓help e2a08b exit0。原公式相关测试未为本轮收口重复执行。
- 唯一只读deepdry控制 `/tmp/audio-device-d49-deepdry-v1.py`=fc2f0b9e1256d5584753b177d156fa8ba93342ce03123d26f5cef05975612c5c；session3814/6eae31实际exit0，44.30301367864013秒，46cases/13687locks，source起止true、无DSP/无formalroot。receiptcea8c55128a0e53e74047cfed61834935a431dd7724caf1a7f0a6c42946ea2fb；intenta36f4017d76c0439e6bd25b55178e714827ebb0cb376cc1e506a528721a9ee48。独立实际附核PASS。初稿遗漏末处理的120秒成功断言属执行前MINOR，修复并复审闭合后才运行；未放宽预算。
- 唯一新C非法输入控制 `/tmp/audio-device-d49-c-negative-v1.py`=4d4e61e77c7b0b6d61f7fe758aceb49afe6a5c38bab066db110a3551f733cde0；session78143/193ae9实际exit0/PASS，0.8917173333466053秒，14新命令、91合成fixture文件。frame/mode/gate、残差/echo长度、残差NaN/echoInf七变体分别在empty/sentinel目录验证，确切退出码2/4、全terminaltrue/nottimeout、目录前后SHA相等，source起止true/formalabsent。空目录配对避免把已存在输出导致的4误当成输入校验成功。receipt4acba9868da43e1537bacb36677c48bad4e0413ca5853b033a3bc5e7cb72f9e7；intent370c09f7c1eb1d48ad89e82e7475c06bc13544ea6e16810dc6111fad0795023d。实际附核另行返回；本文件不预称已独立通过。

## 正式执行条件、准入和退出

正式新root仅 `/tmp/audio-fe-device-magnitude-lower-bound-d49-20261015`。外层控制须独立审查通过，固定当前task-75650e5ed8a898573e753fb7、fresh policy允许且maintenance=false、CP4 verified并绑定本文件，source/proof/intent精确pins及新root/intent/receipt全absent后才唯一启动。未知状态按同handle/精确PID和已有receipt对账，不重放。controller必须保存实际child终态、超时/partial、source起止及结果/binding SHA；异常不抹原退出，算法拒绝仍是有效测量结果。

原46来源/184路/505944帧、960组whole/fixed、160点OLA及D39比较对象不变。每臂24near中位<=-3dB且至少18改善、72no-near最大<=+1dB、4pureecho whole最大<=+1dB，全部满足才DEVELOPMENT_CANDIDATE_ONLY，否则DEVELOPMENT_REJECTED。32已看field无near真值；12合成return、repeat/future保持development-and-synthetic-engineering/adaptive reuse，repeat不独立，4future不评分。80/100为音量；rpm真实运动、mic物理映射及真人标签unknown。

单命令120、矩阵1800、独立审计1800、whole180秒；scoped22000B、observer26728B、measurement<=65536B及加D30 71224B<=131072B；单工件4MiB/root1536MiB/free>=3GiB不变。正式矩阵中的新编译/自检为绑定该正式制品身份，未重跑旧D0–48。结果后独立审计不得import生产helper或执行DSP，须复算原评分及原P/J/新L/strictfloor/postmax、AGC/VAD binary32、state/repeat/future；完整FFT/全帧bin/EMA/noise历史重建仍false，容差不变。

shipping默认/API/ABI/第三方库/设备不改；promotion_allowed=false、shipping_approved=false。无commit/push/PR/merge/release/设备写。Provider仍WORKSPACE_UNBOUND，知识NEEDS_REVIEW、未归档成功。AISpeech产品链、真人ASR/KWS、目标板成本、HIL/E001及至少72小时PQ另行验收。总体目标active，正式结果和最终审查仍未完成，不以本地实现或Runtime conformance推导产品放行。
