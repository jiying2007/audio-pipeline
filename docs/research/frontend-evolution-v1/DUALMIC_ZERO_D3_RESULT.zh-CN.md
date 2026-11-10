# D3: exact-zero upward-update intervention result

Status: CONTROLLED_DIAGNOSIS_NO_PROMOTION. This is an executed result, not NOT_RUN. No production defaults or DSP source changed.

## Prospective identity and actual evidence

- Method/input freeze: bfc066da9e95035530bace2468e5d31bdabb1a5a; issue #930.
- Independently reviewed execution source: 1a3ca400cdc62e6dd1caf98995955af5644d96da.
- First actual run: [Frontend Research 42909847688, attempt 1](https://github.com/jiying2007/audio-pipeline/actions/runs/42909847688), [job 130157384184](https://github.com/jiying2007/audio-pipeline/actions/runs/42909847688/job/130157384184), success.
- Full result artifact: frontend-research-dualmic-zero-d3-42909847688-attempt-1, ID 13807310691; ZIP 34491275 bytes; SHA256 f3dfb663804698eb3b1e981df3139655b55b71ff1ed24dc13adbaf165014c68c.
- Original D2 source cc853616685b9faf7880e6d8f8f1a89d187d342a; original artifact 13553232106/run 42321833898 attempt 1. Complete 474165229-byte original ZIP, 3551 members/861385743 unpacked bytes and unchanged D2 report were admitted in 34.291069334 seconds on this execution.
- Independent follow-up review checked exact-head job logs and artifact API metadata against upload digest/size. This was not a second downloaded-ZIP/member recomputation. The workflow's own full readback was executed and passed.

## Executed controls

Build/self-tests, all 60 continuous two-arm streams, complete state/Float32 arithmetic audit, canonical fixed-window analysis, saved-output readback, and all 15 actual-evidence mutation rejections passed. The baseline output and complete state reproduced retained original D2 evidence byte for byte, not a newly generated baseline. Both arms retained separate continuous histories, original profile/gates and eight resets.

35916 frames and 5746560 samples were replayed. There were 2766 exact-zero input frames and 2764 suppressed upward updates. Nonfinite input is refused; signed zero is zero and tiny nonzero input is not. The remaining two zero frames did not meet the upward-update condition. No other state-update formula, gate, peak limiter or final clamp was changed.

Negative controls rejected candidate/output/state/control mutations, missing trace, changed source/report, added case/output/cases-root members, jointly altered build argv, changed source tree/revision, failed run receipt, and resealed extra source. Every rejection had the intended specific reason. All 15 completed in 14.335109756 seconds, not through generic timeout failure.

Budgets remained unchanged: each subprocess at most 30 seconds, each phase 300 seconds including final writes, whole job 20 minutes. The successful job spanned approximately 76 seconds including setup/upload. No budget or compiler flags were relaxed after observing scores.

## Fixed common-span near-reference SI-SDR changes

All values below are candidate minus original baseline, in dB, on the pre-frozen common span. Each scored profile/scenario contains four correlated development views.

| Profile | Scenario | Minimum | Median | Maximum |
| --- | --- | ---: | ---: | ---: |
| call | near-only | 0.342863301 | 0.384016804 | 0.408319185 |
| assistant | near-only | 0.132407198 | 0.301445993 | 0.368218925 |
| call | silent-render | 0.342863301 | 0.384016804 | 0.408319185 |
| assistant | silent-render | 0.132407198 | 0.301445993 | 0.368218925 |
| call | doubletalk-nominal | 0.0000000158 | 0.0000003681 | 0.0000009168 |
| call | doubletalk-weak | 0.0000000158 | 0.0000005142 | 0.0000010538 |
| assistant | doubletalk-nominal | 0.0000000249 | 0.0000002951 | 0.0000007744 |
| assistant | doubletalk-weak | 0.0000000241 | 0.0000003970 | 0.0000008424 |

Far-only, path-change, render-gap and Mandarin views have no admitted clean-near reference, so no near-reference SI-SDR conclusion is supplied for them. Their streams, traces and fixed measurements were still included in the 60-case evidence. The retained report contains the complete fixed common-span and one-second-window measurements; this table is only the logged aggregate.

## Interpretation and boundary

On these fixed original isolated-AGC inputs, preventing exact-zero upward updates produced a measurable total intervention effect on the near-only/silent-render endpoint. Doubletalk changes are approximately numerical-scale (1e-8 to 1e-6 dB), not evidence of a material quality improvement. Identical near-only and silent-render summaries are correlated views, not independent replication. Later gate/peak changes caused by the different history are part of the total effect, not separately identified component contributions.

This does not establish that digital zero is acoustic silence, that the intervention explains all D2 degradation, or that higher SI-SDR means better perceptual quality. There was no new lag search, selected-case exclusion, ASR/model run, independent validation set, physical device/acoustic test or integrated 2.3.64 pipeline experiment. Original 2.3.63 AGC-input/gate replay remains the scope. Closed target/limiter/global-cap/release and D41–D49 scans remain closed.

No candidate selection or promotion is authorized by this result. Repository-wide CI/protected integration and fresh-main checks are separate from this successful research run.
