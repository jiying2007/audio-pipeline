# 语音作业依赖获取的 Ubuntu 来源范围修正

日期：2026-11-28（北京时间）。本独立修正以公开 source
`38e1a85d0d41ded8fa44b4f278f1a3d39a599274` 为基线，只处理已经观察到的依赖获取失败；
不修改语音来源、评分、DSP、科学预算或历史结论。

## 原失败与执行边界

[Verify46057329715 / attempt1](https://github.com/jiying2007/audio-pipeline/actions/runs/46057329715)
的 [frontend-speech job140704415306](https://github.com/jiying2007/audio-pipeline/actions/runs/46057329715/job/140704415306)
已完成原九项方法 tests、实际 C 构建及 source identity 检查。随后在
`2026-11-27T19:37:48.094Z`，无范围限制的 `apt-get update -qq` 请求运行器预配置的
`https://packages.microsoft.com/ubuntu/24.04/prod/dists/noble/InRelease`，得到 HTTP403，
APT 以100退出。未进入 protected speech source 获取、实际声学或完整双麦回放。
这是观察到的软件源响应，不是已经确定的服务端根因或算法失败。

原始完整 job 日志与六成员构建阶段 ZIP 均已取回；artifact15227367516，1,947B，
SHA256 `9dd395794240d4d958b5113f7d449e7c0639ce2cae0023441339079d73ac5e30`。
后续声学产物保留 step 因尚无科学输出而报缺文件，也保持失败事实，未制造空 PASS。

## 执行前冻结的最小改动

仅将这个 `frontend-speech` step 的两条 FFmpeg APT 命令限定到运行器已有的
`/etc/apt/sources.list.d/ubuntu.sources`。先要求该文件非空，并把它的 SHA256 写入
原 job 日志；`Dir::Etc::sourcelist` 指向该原文件，`Dir::Etc::sourceparts=-` 不读
其他独立软件源片段。update 与 install 使用完全相同的范围。

不删除或改写运行器的软件源，不添加镜像，不允许 unsigned/untrusted packages，
不更改 `Signed-By`、TLS、签名、日期有效性或摘要验证。Ubuntu 源本身不可用时仍失败。
包名保持 `ffmpeg`，安装选项保持 `-y --no-install-recommends`，不增加重试或超时。
原 source/hash/PCM 验证、评分、独立 reader、其他 jobs 和所有原 artifact 成员保持。
这也不把当前依赖版本描述为固定编译工具链；实际 decoder 身份仍由原来源流程记录。

依据：[Ubuntu 24.04 来源格式](https://documentation.ubuntu.com/release-notes/24.04/#deb822-sources-management)、
[APT 来源配置路径](https://manpages.ubuntu.com/manpages/noble/man8/apt-get.8.html#files)、
[APT 配置选项](https://manpages.ubuntu.com/manpages/noble/man5/apt.conf.5.html#directories)。

## 本地验证与后续实际验收

使用本地主机真实 APT 的 `--print-uris update` 和两个仅含 URI 的临时来源 fixture，
原范围列出 Ubuntu 与 Microsoft，限定范围只列出 Ubuntu。此验证零网络请求、
零安装；它只证明本地 APT 的来源选择语义，不冒充 Ubuntu runner 的真实安装成功。
另检查完整 YAML、该 step 的 shell 语法及改动块之外的 workflow 逐字身份。

最终集成必须以新公开精确 source 执行原 `frontend-speech` 全链及全部适用门禁；
保留原失败，不能用本地解析检查替代实际原始语音读取、回放或受保护 main 复验。
