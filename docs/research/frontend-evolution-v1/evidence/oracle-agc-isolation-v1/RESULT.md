# Fixed-oracle-input AGC allow isolation: conditional effect, no promotion

The independently reviewed frozen run completed once, exit0, elapsed4.301251269s within180s. It used the current native runtime, not the historical private loader. No full pipeline, new oracle-DT run, audio generation, external model, paid compute or production change occurred.

## Identity and intervention

The unchanged original AGC source was compiled once with GCC/O3/ffp-contract=off. On each profile's saved oracle NS Float32 output, the oracle-allow module replay exactly reproduced every saved AGC Float32 sample and every gain_before/gain_after Float32 state across629 sequential frames. Both profiles passed before either counterfactual. Initial state came only from original ap_agc_init (CALL−20/ASSISTANT−18dBFS, limiter−2dBFS), not injected recorded per-frame gains.

Only the allow sequence was replaced with the saved original-baseline allow sequence. The upstream input, profile initialization, AGC equations and complete sequential recurrence remained fixed. This is distinct from D2/D5/D6/D9 interventions and isolates a conditional AGC permission effect on the new V2 oracle inputs. It is not an additive decomposition of the full DT override's effects, and does not justify removing AGC protection in production.

## Common-span Float32 results

Fixed physical[0,100480), output[160,100640); all13windows×2arms×2profiles=52groups retained with the unchanged math.fsum metric functions and null rules. These are raw-near-domain descriptive measures, not finalS16, CER/MOS or isolated speech quality.

| Metric | CALL oracle allow | CALL restored allow | ASSISTANT oracle allow | ASSISTANT restored allow |
|---|---:|---:|---:|---:|
| Gain-sensitive error(dB) |11.0805405944|0.8207008210|12.9894253708|0.8517836426|
| Noncanonical projection SI-SDR(dB) |-0.9253804032|-2.3504378126|-1.0887946973|-2.3675211604|
| RMS |0.0474963758|0.0155462898|0.0576047825|0.0155957388|
| Peak |0.4015535414|0.0956480131|0.4719556570|0.0956869051|

Restoring original permissions reduces energy and gain-sensitive error on these fixed inputs, but worsens the projection metric. Therefore the permission change contributes to amplification, not an established general audio improvement or a complete explanation of V2's degradation. Earlier AEC/NS changes remain fixed in this experiment, and cross-stage/source effects are not independently decomposed.

## Actual native performance evidence

Seven paired repetitions per profile, alternating order; each timed invocation executes100 reset+629frame sequences. CLOCK_THREAD_CPUTIME_ID timing excludes file IO and validation but includes identical memcpy, original initialization and gain trace stores. All28 timed invocations' final outputs/states exactly equal their corresponding first replay. Total4 replay+28benchmark invocations,0 full pipelines,0 historical-runtime executions.

CALL CPU medians per100sequences: oracle0.100542891s, restored0.100958429s; median paired ratio1.023125842, pair range0.957911966–1.236775706. ASSISTANT medians0.101084777s and0.096441755s; median paired ratio0.968668645, range0.799462747–1.045337491. No affinity control or confidence inference; the spread does not support a robust efficiency improvement claim. These are native hosted microbenchmarks, not SSC305 CPU/p99/power measurements.

## Boundary

CONDITIONAL_SINGLE_MODULE_DIAGNOSTIC_NO_PROMOTION. All source/input/ELF identities were checked before/after each invocation and at completion; LD_*/GLIBC_TUNABLES were absent. Analysis had a separate30s hard alarm, in addition to the180s outer cap. No retry, compile strategy search, metric threshold change or production recommendation was used to obtain these results. Original baseline failures and V2 joint-oracle results remain unchanged.
