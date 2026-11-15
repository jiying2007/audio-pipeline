# Fixed-oracle-input NS/RES DT control: conflicting metrics, no promotion

V2 completed once, outer exit0, elapsed1.173903681s within150s. Exactly four isolated NS-module processes and one private-loader dependency listing executed, no full pipeline or extra benchmark. Both CALL/ASSISTANT original-oracle NS Float32 outputs and all629frames of frequency_active/residual_gain/noise_rms_dbfs/speech_probability matched historical oracle bytes before either restored-DT arm. The historical archive and its verified private runtime were unchanged.

V1's missing observer-symbol forwarding caused a real linker failure before any loader or DSP. Its source, failed command and receipts remain in the separate original root/archive. V2's independently reviewed correction adds five pure forwarding functions to the existing *_d1_real symbols. It changes no DSP formula, input or admission rule. Aggregate executed NS process count across both attempts is four, not eight.

## Conditional intervention

The two saved oracle input lanes (NS residual and echo) are fixed. Each arm initializes original NS once and maintains continuous629frame state. Only DT is replaced with the saved original baseline DT. This affects both frequency-RES activation and inactive-bin release state. It is distinct from D40's uniform enable_frequency_res disable and from D41–49's new protection mappings. It is not a pure frequency-enable experiment or an additive attribution of total full-pipeline DT effects.

As a posthoc descriptive check, both profiles have frequency_active122→551;429frames differ. Reported residual_gain differs in441frames, while all629 noise_rms_dbfs and speech_probability Float32 values remain equal between arms. Those two public NS statistics do not prove every internal tracker/FFT/bin/OLA state equal. Historical full internal-state snapshots do not exist.

## Actual common-span NS Float32 measurements

Unchanged math.fsum/null formulas, all13windows x2arms x2profiles=52groups retained. Common physical[0,100480), fixed output[160,100640). Control statistics cover629frames; the common waveform spans628frames. Raw-near engineering-domain metrics are not finalS16, CER/MOS or isolated speech quality.

| Metric | CALL oracle DT | CALL restored DT | ASSISTANT oracle DT | ASSISTANT restored DT |
|---|---:|---:|---:|---:|
| Gain-sensitive error(dB) |0.8207008210|0.1471684860|0.8517836426|0.1775565780|
| Noncanonical projection SI-SDR(dB) |-2.3504378126|-3.7998450342|-2.3675211604|-3.8118537011|
| RMS |0.0155462898|0.0127033281|0.0155957388|0.0127633943|
| Peak |0.0956480131|0.0826014876|0.0956869051|0.0826565921|

Restored DT control reduces energy and gain-sensitive error, but worsens the projection metric on the same oracle inputs. The conflict does not establish general quality improvement, prove a single cause of end-to-end degradation, or justify reverting near protection. AEC history stays embedded in the fixed oracle input, and no new downstream AGC/final endpoint was executed.

## Timing and resource observation

One CLOCK_THREAD_CPUTIME_ID observation per629frame arm, including initialization and exported-field stores, excluding file IO/validation: CALL oracle0.029449507s, restored0.031858896s; ASSISTANT oracle0.030986441s, restored0.033079150s. These four observations are not a repeated benchmark distribution and support no robust speedup/slowdown inference. sizeof(ap_ns_state_t)=9116 bytes in this exact historical build, not total process/SSC305 memory or power. No target-device claim.

Decision: CONDITIONAL_NS_RES_DIAGNOSTIC_NO_PROMOTION. Identity, runtime binding, input and ELF checks passed around every invocation. No scientific threshold was changed; no favorable replay or compile/math strategy search. Independent result review remains separate from protected PR/main CI.
