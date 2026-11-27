# F05 来源准备的可移植回读补充

原 F05 数据准备记录、失败历史、32 个包成员和全部测量字节保持不变。原封包 SHA256 为 a35e8f660de6cfe2b33d48dbeb0bb47c1e31e61faff534de73fd42406d8d08d2。

原回读器会核验实际本地提交 ad7075464953162f21cd95a35e640032a4ca2634 与公开 cbddb82cb849e9fa454227f1995efb07ad4a7bf5 的相同 tree。为了让新的检出也能复验这一真实映射，本包另外携带最小 Git bundle，保留本地提交对象，不把它改写成远端执行身份。

先在新检出的 audio-pipeline 仓库取得公开提交，再导入 bundle（不移动当前分支）：

```sh
git fetch origin cbddb82cb849e9fa454227f1995efb07ad4a7bf5
git bundle verify /absolute/unpacked/f05-source-lineage/f05-local-source.bundle
git fetch /absolute/unpacked/f05-source-lineage/f05-local-source.bundle refs/heads/research/aec3-measurement-20261128
python3 /absolute/unpacked/f05-readiness-20261128/verify_preparation.py   --package /absolute/unpacked/f05-readiness-20261128   --repo /absolute/audio-pipeline   --output /absolute/fresh/f05-readback.json
```

原两份 WAV 必须是仓库中的精确原件。新扫描的 Git refs/本地物料范围发生变化时，生成的是新盘点，不能声称逐字重建旧852commit扫描。

本补充已在只取得公开 cbddb82 的独立 bare repository 中实际验证：导入前没有 ad707；bundle verify/import 成功后，原未改动回读器返回 PREPARATION_READBACK_PASS_NO_ACOUSTIC_EVIDENCE。没有重新生成音频、调用DSP或改变角色。独立验证回执和补充 manifest 位于 f05-source-lineage。

本包含两份头修正衍生 WAV，仅作为用户的私有审查材料。training、promotion 与新音频公开再发布许可均未增加。
