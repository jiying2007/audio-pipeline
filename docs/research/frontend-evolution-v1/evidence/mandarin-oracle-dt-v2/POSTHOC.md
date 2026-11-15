# Post-hoc existing-output trace (zero new DSP)

This trace was requested after the frozen four-run result. It reads only existing Float32 taps/control CSVs; it is not an additional causal experiment or a change to the measurement contract.

Both profiles first change DT at frame100, through528. At frame100, frequency_active, res_gain, noise_rms_dbfs, speech_probability, agc_allow and gain_after also diverge. AGC-allowed frames change78→507; maximum gain_after changes CALL5.71240473→7.35993099 and ASSISTANT5.71240473→7.47020197. Gain differences persist through frame628.

AEC input and reference remain byte-identical. Echo, AEC residual and NS input first differ at output sample16032. NS/AGC output first differs at sample16000. The frozen+160 sample output-alignment mapping is for waveform comparisons, not a timestamp of control application; subtracting that offset does not imply acausal behavior or establish the causal ordering of independent modules. State/control changes can affect overlap/block synthesis.

The DT override jointly changes AEC gating, frequency-domain processing, RES/noise state and AGC permission. These observed cochanges cannot attribute a fraction of the final metric change to any one module, prove an individual detector fix, or justify a new algorithm automatically. Exact source/output checks and all field counts are in existing-trace.json; trace_existing.py reproduces the read-only table. No new DSP, external models or source mutation occurred.
