# A1 ZIP readiness transport contract

Base: 8310359974a84407630e0e5c502e24f3f1c76b56. Date: 2026-11-10.

Observed failure: [Verify 42905402342 job 130144030271](https://github.com/jiying2007/audio-pipeline/actions/runs/42905402342/job/130144030271) finalized artifact 13806055187 at 21:36:07.110 UTC, passed exact run/list identity, and the pinned downloader enumerated it, but the ZIP endpoint returned 404 at 21:36:08.554. Original artifact: 37888 bytes, SHA256 e9a96cde541d15e8df1bf74f1fae31dd42df51bb81ceb081e15e5ff4083b0258. Preserve original failure and evidence. Later connector availability does not prove that the original job token had archive access.

Hypothesis: listing visibility and archive redirect readiness are separate states. Only A1 will opt into a bounded exact-artifact ZIP endpoint readiness probe after the existing unchanged run/attempt/repository/head/execution-source/name/id/timestamp/size/digest witness. A 302 means only that the API supplies a redirect at that instant. It is not a digest, content, downstream availability, token-cause or scientific success claim.

Budget: at most eight additional GET requests, 10-second socket timeout each, seven two-second pauses, no body reads or redirect following. This is an explicit separate transport budget inside the unchanged 30-minute job deadline, not an increase to the existing eight-request metadata budget or any science timeout. Retry only 404/502/503; hard HTTP failures, network/TLS errors, malformed redirects and exhaustion fail closed. Never print or persist signed locations, bodies or credentials. Do not widen retries after a failed run.

Scope: A1-only opt-in, helper, synthetic regression tests, this contract. Other stages do not probe ZIP endpoints. Preserve pinned downloader, artifact identity, four original members, hashes, source checks, independent positive/negative scientific readback, 30-day retention and upload behavior. No DSP or acoustic change.

Acceptance: synthetic 404-to-302 and persistent absence, hard status/auth errors, no-follow/no-body/closed response, redacted malformed redirects/network errors, exact endpoint and A1-only routing, identity-failure ordering, unchanged legacy tests, workflow wiring, independent review and full exact-head required Verify including summary. Only then protected squash merge and fresh-main verification. Current passing focused tests alone are not full CI.

Data role: public transport evidence and synthetic HTTP fixtures only. No private data, physical measurement, quality promotion or retrospective PASS.

中文摘要：本变更仅修复 A1 上传清单可见但 ZIP 端点暂不可用的传输边界。保留原失败；后续连接器可下载不证明原任务令牌有效。原身份核验、固定下载器、四成员哈希及独立正负读回保持不变。新增有限无跟随重定向探测不读取归档、不泄露签名链接；持续失败保持红灯，不增加科研或任务时限。
