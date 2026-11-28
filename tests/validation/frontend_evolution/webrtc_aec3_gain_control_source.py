#!/usr/bin/env python3
"""Exact second-stage derivation of the pinned selector, without DSP execution.

Only the gain arguments at ApplyGain, their local observation, the private
configuration flags, and the corresponding existing adapter options change.
All three complete preimages are pinned to the already qualified observer.
"""
from __future__ import annotations

import difflib
import json
from pathlib import Path

import webrtc_aec3_selection_source as predecessor
from contracts import require, sha256

EXPERIMENT = "F07-LT2-AEC3-JOINT-GAIN-CONTROLLED-SYNTHESIS-V1"
CONFIG, REMOVER, RUNNER = predecessor.CONFIG, predecessor.REMOVER, predecessor.RUNNER
TARGETS = (CONFIG, REMOVER, RUNNER)
SELECTED_HASHES = {
    CONFIG: "33c0534938744f9b2d7c007f3423ca791c3efa74e1682d4ae334fadbea940ae2",
    REMOVER: "ee8aed41e88f96ae115536e74cf6dc9ff128ea6576293b93a22a8ad30bf60c2a",
    RUNNER: "2526a28f4b92a73489eec0c9c13ecbd5c26b72b4c68482b26b36beac0b8b56e8",
}
SUPPORT = (1525, 1976)
TRACE_KIND = "aec3_joint_gain_control"
MODES = ("gain-observe", "gain-unity")
APPLY = ("    suppression_filter_.ApplyGain(comfort_noise, high_band_comfort_noise, G,\n"
         "                                  high_bands_gain, Y_fft, y);\n")
APPLIED = r"""    // Research-only intervention at the final synthesis arguments.
    // Estimated G, generator inputs and all earlier arithmetic stay untouched.
    // Gain-dependent CNG mixing and OLA output history intentionally may differ.
    const auto& gain_research = config_.research_synthesis_selection;
    const size_t gain_block = block_counter_ - 1;
    const bool gain_support = gain_block >= 1525 && gain_block < 1976;
    const bool gain_forced = gain_research.force_unity_gain && gain_support;
    std::array<float, kFftLengthBy2Plus1> unity_gain;
    unity_gain.fill(1.f);
    const auto& applied_gain = gain_forced ? unity_gain : G;
    const float applied_high_gain = gain_forced ? 1.f : high_bands_gain;
    if (gain_research.gain_control_observe) {
      if (num_capture_channels_ != 1 || comfort_noise.size() != 1 ||
          high_band_comfort_noise.size() != 1 || block_counter_ == 0 ||
          block_counter_ > 4000 || !capture_output_used_ ||
          research_applied_linear != research_source_linear)
        throw std::runtime_error("gain-control mono block contract failed");
      static_assert(sizeof(float) == sizeof(std::uint32_t) &&
                        std::numeric_limits<float>::is_iec559,
                    "gain-control trace requires binary32");
      const auto bits_of = [](float value) {
        std::uint32_t bits = 0;
        std::memcpy(&bits, &value, sizeof(bits));
        return static_cast<unsigned long>(bits);
      };
      const auto write_words = [&](const char* key, const auto& values) {
        if (std::fprintf(stderr, ",\"%s\":[", key) < 0)
          throw std::runtime_error("gain-control trace write failed");
        for (size_t i = 0; i < values.size(); ++i) {
          if (std::fprintf(stderr, "%s%lu", i ? "," : "",
                           bits_of(values[i])) < 0)
            throw std::runtime_error("gain-control trace write failed");
        }
        if (std::fprintf(stderr, "]") < 0)
          throw std::runtime_error("gain-control trace write failed");
      };
      if (std::fprintf(stderr,
              "{\"kind\":\"aec3_joint_gain_control\",\"block_index\":%zu,"
              "\"support\":%s,\"forced\":%s,\"estimated_high_bits\":%lu,"
              "\"applied_high_bits\":%lu",
              gain_block, gain_support ? "true" : "false",
              gain_forced ? "true" : "false",
              bits_of(high_bands_gain), bits_of(applied_high_gain)) < 0)
        throw std::runtime_error("gain-control trace write failed");
      write_words("estimated_low_bits", G);
      write_words("applied_low_bits", applied_gain);
      write_words("cng_low_re", comfort_noise[0].re);
      write_words("cng_low_im", comfort_noise[0].im);
      write_words("cng_high_re", high_band_comfort_noise[0].re);
      write_words("cng_high_im", high_band_comfort_noise[0].im);
      write_words("residual_power", R2[0]);
      write_words("unbounded_residual_power", R2_unbounded[0]);
      write_words("nearend_spectrum", nearend_spectrum[0]);
      write_words("echo_spectrum", echo_spectrum[0]);
      write_words("cng_noise_spectrum", cng_.NoiseSpectrum()[0]);
      write_words("selected_input_re", Y_fft[0].re);
      write_words("selected_input_im", Y_fft[0].im);
      if (std::fprintf(stderr, "}\n") < 0)
        throw std::runtime_error("gain-control trace write failed");
    }
    suppression_filter_.ApplyGain(comfort_noise, high_band_comfort_noise, applied_gain,
                                  applied_high_gain, Y_fft, y);
"""


def transform(relative: str, selected: bytes) -> bytes:
    require(relative in SELECTED_HASHES and sha256(selected) == SELECTED_HASHES[relative],
            "gain-control exact selector preimage mismatch: " + relative)
    text = selected.decode("utf-8")
    replace = predecessor.replace_once
    if relative == CONFIG:
        text = replace(text, "    bool force_linear = false;\n",
                       "    bool force_linear = false;\n"
                       "    bool gain_control_observe = false;\n"
                       "    bool force_unity_gain = false;\n")
    elif relative == REMOVER:
        text = replace(text, APPLY, APPLIED)
    else:
        text = replace(text,
            '         options.synthesis_selection != "force-linear") ||\n',
            '         options.synthesis_selection != "gain-observe" &&\n'
            '         options.synthesis_selection != "gain-unity") ||\n')
        text = replace(text,
            'throw Failure(2, "synthesis selection requires observe or force-linear, mono factory-on, no reset");',
            'throw Failure(2, "gain-control requires observe, gain-observe or gain-unity, mono factory-on, no reset");')
        text = replace(text,
            '    aec3.research_synthesis_selection.force_linear = selection_ == "force-linear";\n',
            '    aec3.research_synthesis_selection.force_linear = false;\n'
            '    aec3.research_synthesis_selection.gain_control_observe = selection_ == "gain-observe" || selection_ == "gain-unity";\n'
            '    aec3.research_synthesis_selection.force_unity_gain = selection_ == "gain-unity";\n')
        text = replace(text, "  CheckOutputs(options);\n", r"""  if ((options.synthesis_selection == "gain-observe" ||
       options.synthesis_selection == "gain-unity") &&
      frames != 800 && frames != 1600)
    throw Failure(2, "gain-control requires exactly 800 engineering or 1600 scientific frames");
  CheckOutputs(options);
""")
        text = replace(text, "  if (!options.synthesis_selection.empty()) {\n", r"""  if (options.synthesis_selection == "gain-observe" || options.synthesis_selection == "gain-unity") {
    out << ",\"aec3_joint_gain_control\":{\"mode\":" << Quote(options.synthesis_selection)
        << ",\"support_blocks\":[1525,1976],\"block_samples\":64"
        << ",\"gain_controlled_cng_and_ola_may_change\":true,\"promotion_allowed\":false}";
  }
  if (!options.synthesis_selection.empty()) {
""")
        text = replace(text,
            "[--aec3-synthesis-selection observe|force-linear]",
            "[--aec3-synthesis-selection observe|gain-observe|gain-unity]")
    return text.encode("utf-8")


def _record(prepared: Path, evidence: Path, derived: Path | None, writing: bool) -> dict:
    prior = predecessor.verify(prepared, evidence / "selection")
    old_manifest = json.loads((evidence / "selection/derived-files.json").read_text())
    expected_manifest = dict(old_manifest)
    changes, diff = {}, []
    for path in TARGETS:
        selected = (evidence / "selection/modified" / path).read_bytes()
        changed = transform(path, selected)
        for role, payload in (("original", selected), ("modified", changed)):
            file = evidence / role / path
            if writing:
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(payload)
            require(file.read_bytes() == payload, "gain-control transformation evidence drift: " + path)
        if path != RUNNER:
            if writing:
                require((derived / path).read_bytes() == selected, "unexpected pre-transform tree")
                (derived / path).write_bytes(changed)
            expected_manifest[path] = predecessor.pristine.file_record(changed, False)
        changes[path] = {"original_sha256": sha256(selected), "modified_sha256": sha256(changed),
                         "original_bytes": len(selected), "modified_bytes": len(changed)}
        diff.extend(difflib.unified_diff(selected.decode().splitlines(True), changed.decode().splitlines(True),
                                         fromfile="selection/" + path, tofile="gain-control/" + path))
    patch = "".join(diff).encode()
    if writing:
        (evidence / "changes.patch").write_bytes(patch)
        predecessor.pristine.write_json(evidence / "derived-files.json", expected_manifest)
    require((evidence / "changes.patch").read_bytes() == patch and
            json.loads((evidence / "derived-files.json").read_text()) == expected_manifest,
            "gain-control exact patch or complete file manifest drift")
    if derived is not None:
        require(predecessor.manifest(derived) == expected_manifest,
                "gain-control source tree differs outside exact allowed transformation")
    return {"schema_version": 1, "experiment_id": EXPERIMENT,
            "status": "EXACT_GAIN_CONTROL_DERIVATION_NOT_BUILT",
            "predecessor_receipt": prior,
            "generator_sha256": sha256(Path(__file__).read_bytes()),
            "changes": changes, "patch_sha256": sha256(patch),
            "derived_manifest_sha256": sha256(predecessor.pristine.encoded(expected_manifest)),
            "support_blocks": list(SUPPORT), "intervention": "joint-gain-controlled-suppression-cng-synthesis",
            "ola_history_expected_to_diverge": True, "acoustic_measurement": "NOT_RUN",
            "promotion_allowed": False}


def prepare(prepared: Path, derived: Path, evidence: Path) -> dict:
    derived, evidence = predecessor.pristine.safe_path(derived), predecessor.pristine.safe_path(evidence)
    require(not derived.exists() and not evidence.exists() and
            all(predecessor.pristine.separate(a, b) for a, b in
                ((prepared, evidence), (derived, evidence), (predecessor.ROOT, evidence))),
            "fresh disjoint gain-control source derivation required")
    predecessor.prepare(prepared, derived, evidence / "selection")
    receipt = _record(prepared, evidence, derived, True)
    predecessor.pristine.write_json(evidence / "source-transform.json", receipt)
    return verify(prepared, evidence, derived)


def verify(prepared: Path, evidence: Path, derived: Path | None = None) -> dict:
    expected = _record(prepared, evidence, derived, False)
    require(json.loads((evidence / "source-transform.json").read_text()) == expected,
            "gain-control receipt changed")
    return expected
