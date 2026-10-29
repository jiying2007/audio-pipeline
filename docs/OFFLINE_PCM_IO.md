# Offline PCM processor I/O contract

The offline tool `ap_process_pcm` processes raw interleaved
S16 capture and optional mono S16 render in 10 ms blocks. It is an offline
integration and validation tool; successful processing is not acoustic,
SSC305, HIL or Product Certification evidence.

Capture must contain complete S16 samples and interleaved channel groups for
the selected sample rate and microphone count. Empty capture is a valid
zero-frame input. Incomplete samples, incomplete channel groups and read errors
return nonzero in every mode.

By default, a legitimate EOF tail shorter than 10 ms preserves the established
behavior: process the complete blocks and omit the final tail. The tool now
reports the omitted samples per channel and the channel count on stderr. Output
PCM and metrics contain only the complete processed frames; the tail is not
padded or processed. Arbitrary-duration PCM, including the pinned hosted real
corpus, therefore keeps its prior output bytes and frame count.

Use `--strict-capture-frames` when recording completeness is required. This mode
rejects every nonempty partial capture block with a nonzero exit status. For
example:

```sh
./build/ap_process_pcm --strict-capture-frames --sample-rate 16000 \
  --mic-channels 2 mic.pcm render.pcm out.pcm
```

Render retains the existing EOF policy: complete samples from a short or empty
render file are followed by zero samples. An incomplete S16 sample returned by a
render read or a read error is not valid EOF and returns nonzero. Processing
stops when capture ends; any unused render suffix is not validated.

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
Each of the 21 scenarios runs in default and strict modes. The default tail
compatibility control includes 12 complete frames plus a half frame and checks
the diagnostic, byte-exact nonzero output and complete-frame metrics count.
Frozen predecessor controls reproduce eight false-success error paths and the
silent whole-channel tail discard using exact v2.3.60 processor bytes linked to
the unchanged current core; they do not rebuild or certify a historical release
binary. The rejected first candidate and its hosted-real compatibility failure
remain recorded in [#866](https://github.com/jiying2007/audio-pipeline/issues/866).

The change has no effect on DSP defaults, public C API/ABI, data roles, historical
research results, or the exact immutable v2.3.16 physical qualification program
tracked in [#58](https://github.com/jiying2007/audio-pipeline/issues/58).
