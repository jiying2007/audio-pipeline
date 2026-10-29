# Offline PCM processor I/O contract

The offline tool `ap_process_pcm` processes raw interleaved
S16 capture and optional mono S16 render in 10 ms blocks. It is an offline
integration and validation tool; successful processing is not acoustic,
SSC305, HIL or Product Certification evidence.

Capture must contain whole 10 ms blocks for the selected sample rate and
microphone count. Empty capture is a valid zero-frame input. A nonempty partial
capture block, incomplete S16 sample, or read error returns nonzero. Render
retains the existing EOF policy: complete samples from a short or empty render
file are followed by zero samples. An incomplete S16 sample returned by a render
read or a read error is not valid EOF and returns nonzero. Processing stops when
capture ends; any unused render suffix is not validated.

PCM and optional JSONL metrics output are accepted only when all writes and
final buffered closes succeed. Errors return nonzero even if some output was
already produced; callers must discard that incomplete output. All successfully
opened streams are closed on failure. Configuration and tuning are validated
before output files are opened.

The current output files are ordinary streams, not transactional file commits.
Callers should use distinct input/output paths and publish outputs only after a
zero exit status. This contract does not make in-place processing safe.

Regression coverage uses deterministic stdio fixtures and the actual processor
translation unit. Valid complete inputs are compared byte-for-byte to direct
calls of the unchanged DSP core. Nonempty valid controls span 12 frames (120 ms)
and require nonzero PCM, covering the default reference delay and startup latency.
Frozen predecessor controls reproduce the
v2.3.60 processor's false-success I/O behavior using its exact source bytes
linked to the unchanged current core; they do not rebuild or certify a historical
release binary.

The change has no effect on DSP defaults, public C API/ABI, data roles, historical
research results, or the exact immutable v2.3.16 physical qualification program
tracked in [#58](https://github.com/jiying2007/audio-pipeline/issues/58).
