#!/usr/bin/env python3
"""Exact-source research derivation for AEC3 synthesis-selection observation.

The admitted distribution and historical adapter are never modified. Two
upstream files and a generated adapter are derived with checked complete input
digests. The observer does not change arithmetic; the conditional intervention
changes only the E/Y input of the existing synthesis filter.
"""
from __future__ import annotations

import difflib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import math

import webrtc_aec3_source as pristine
from contracts import ROOT, require, sha256

EXPERIMENT = "FE04-WEBRTC-AEC3-SYNTHESIS-SELECTION-V1"
CONFIG = "webrtc/api/audio/echo_canceller3_config.h"
REMOVER = "webrtc/modules/audio_processing/aec3/echo_remover.cc"
RUNNER = "tests/validation/frontend_evolution/webrtc_aec3_runner.cc"
ORIGINAL_HASHES = {
    CONFIG: "6b94c6061644f3d55365dd79e6c26534296efd66b11b25f6d291338364429e75",
    REMOVER: "c17b624242ab5f2bfce16a0324fae81d22e175f2e7761b150b5ed665974bb4da",
    RUNNER: "d6d8f2b14b2d9fa424c732238852539b3bbb4252e07972fc27258eafbec9c603",
}
TRACE_KEYS = {"kind", "block_index", "source_linear", "applied_linear",
              "forced", "capture_output_used", "gain_bits",
              "high_bands_gain_bits", "dominant_nearend_after_gain"}
TRACE_KIND = "aec3_synthesis_selection"


def replace_once(text: str, before: str, after: str) -> str:
    require(text.count(before) == 1, "selection source anchor missing or duplicated")
    return text.replace(before, after, 1)


def transform(relative: str, original: bytes) -> bytes:
    require(relative in ORIGINAL_HASHES and sha256(original) == ORIGINAL_HASHES[relative],
            "selection source complete original digest mismatch: " + relative)
    text = original.decode("utf-8")
    if relative == CONFIG:
        text = replace_once(text, "  struct Buffering {\n", """  // Isolated research build only; not part of pristine upstream or AP SDK.
  struct ResearchSynthesisSelection {
    bool observe = false;
    bool force_linear = false;
  } research_synthesis_selection;

  struct Buffering {
""")
    elif relative == REMOVER:
        text = replace_once(text, "#include <cmath>\n",
                            "#include <cmath>\n#include <cstdio>\n#include <cstdint>\n#include <cstring>\n#include <limits>\n#include <stdexcept>\n")
        text = replace_once(text,
            "  const auto& Y_fft = aec_state_.UseLinearFilterOutput() ? E : Y;\n", """  const bool research_source_linear = aec_state_.UseLinearFilterOutput();
  const bool research_applied_linear =
      research_source_linear || config_.research_synthesis_selection.force_linear;
  const auto& Y_fft = research_applied_linear ? E : Y;
  if (config_.research_synthesis_selection.observe && !capture_output_used_)
    throw std::runtime_error("research selection requires capture output used");
""")
        text = replace_once(text,
            "    suppression_filter_.ApplyGain(comfort_noise, high_band_comfort_noise, G,\n", """    if (config_.research_synthesis_selection.observe) {
      static_assert(sizeof(float) == sizeof(std::uint32_t) &&
                        std::numeric_limits<float>::is_iec559,
                    "selection trace requires binary32");
      if (block_counter_ == 0 || block_counter_ > 4000 ||
          std::fprintf(stderr,
              "{\\"kind\\":\\"aec3_synthesis_selection\\",\\"block_index\\":%zu,"
              "\\"source_linear\\":%s,\\"applied_linear\\":%s,\\"forced\\":%s,"
              "\\"capture_output_used\\":%s,\\"gain_bits\\":[",
              block_counter_ - 1, research_source_linear ? "true" : "false",
              research_applied_linear ? "true" : "false",
              (config_.research_synthesis_selection.force_linear &&
               !research_source_linear) ? "true" : "false",
              capture_output_used_ ? "true" : "false") < 0)
        throw std::runtime_error("research synthesis selection trace failed");
      for (size_t bin = 0; bin < G.size(); ++bin) {
        std::uint32_t bits = 0;
        std::memcpy(&bits, &G[bin], sizeof(bits));
        if (std::fprintf(stderr, "%s%lu", bin ? "," : "",
                         static_cast<unsigned long>(bits)) < 0)
          throw std::runtime_error("research synthesis gain trace failed");
      }
      std::uint32_t high_bits = 0;
      std::memcpy(&high_bits, &high_bands_gain, sizeof(high_bits));
      if (std::fprintf(stderr,
              "],\\"high_bands_gain_bits\\":%lu,\\"dominant_nearend_after_gain\\":%s}\\n",
              static_cast<unsigned long>(high_bits),
              suppression_gain_.IsDominantNearend() ? "true" : "false") < 0)
        throw std::runtime_error("research synthesis nearend trace failed");
    }
    suppression_filter_.ApplyGain(comfort_noise, high_band_comfort_noise, G,
""")
    else:
        text = replace_once(text, "  std::string aec3_export_mode, linear_output;\n",
                            "  std::string aec3_export_mode, linear_output;\n  std::string synthesis_selection;\n")
        text = replace_once(text, '    else if (key == "--linear-output") options.linear_output = value;\n',
                            '    else if (key == "--linear-output") options.linear_output = value;\n'
                            '    else if (key == "--aec3-synthesis-selection") options.synthesis_selection = value;\n')
        text = replace_once(text, "  return options;\n", """  if (seen.count("--aec3-synthesis-selection")) {
    if ((options.synthesis_selection != "observe" &&
         options.synthesis_selection != "force-linear") ||
        options.aec3_export_mode != "factory-on" || options.mode != "aec3" ||
        options.channels != 1 || options.channel_map[0] != 0 ||
        options.reset_before_frame)
      throw Failure(2, "synthesis selection requires observe or force-linear, mono factory-on, no reset");
  }
  return options;
""")
        text = replace_once(text,
            "  explicit LinearObservationFactory(bool enabled) : enabled_(enabled) {}\n",
            "  LinearObservationFactory(bool enabled, const std::string& selection)\n"
            "      : enabled_(enabled), selection_(selection) {}\n")
        text = replace_once(text, "    aec3.filter.export_linear_aec_output = enabled_;\n",
            "    aec3.filter.export_linear_aec_output = enabled_;\n"
            '    aec3.research_synthesis_selection.observe = !selection_.empty();\n'
            '    aec3.research_synthesis_selection.force_linear = selection_ == "force-linear";\n')
        text = replace_once(text, "  const bool enabled_;\n", "  const bool enabled_;\n  const std::string selection_;\n")
        text = replace_once(text, "            const std::string& export_mode) {\n",
                            "            const std::string& export_mode, const std::string& selection) {\n")
        text = replace_once(text,
            '        std::make_unique<LinearObservationFactory>(export_mode == "factory-on"));\n',
            '        std::make_unique<LinearObservationFactory>(export_mode == "factory-on", selection));\n')
        anchor = "MakeApm(config, options.channels, options.aec3_export_mode)"
        require(text.count(anchor) == 2, "selection factory invocation anchors")
        text = text.replace(anchor, "MakeApm(config, options.channels, options.aec3_export_mode, options.synthesis_selection)")
        text = replace_once(text, "  CheckOutputs(options);\n", """  if (!options.synthesis_selection.empty() && frames > 1600)
    throw Failure(2, "synthesis selection is bounded to at most 16 seconds");
  CheckOutputs(options);
""")
        text = replace_once(text,
            '  out << ",\\"host_clock\\":\\"steady_clock nanoseconds relative to case start\\"}\\n";\n',
            """  if (!options.synthesis_selection.empty()) {
    out << ",\\"aec3_synthesis_selection\\":{\\"mode\\":" << Quote(options.synthesis_selection)
        << ",\\"trace_stream\\":\\"stderr-jsonl\\",\\"trace_kind\\":\\"aec3_synthesis_selection\\""
        << ",\\"block_samples\\":64,\\"block_index_origin\\":0,\\"max_blocks\\":4000"
        << ",\\"linear_signal_delay_samples\\":64,\\"final_signal_delay_samples\\":128"
        << ",\\"force_affects_only_synthesis_input\\":true,\\"upstream_pristine\\":false"
        << ",\\"promotion_allowed\\":false}";
  }
  out << ",\\"host_clock\\":\\"steady_clock nanoseconds relative to case start\\"}\\n";
""")
        text = replace_once(text,
            '  metadata.Text(Metadata(options, config, apm, frames, completed, first_completed_ns,\n'
            '                         first_linear_completed_ns, "OK", ""));\n',
            '  if (!options.synthesis_selection.empty() && std::fflush(stderr) != 0)\n'
            '    throw Failure(5, "synthesis selection stderr flush failed");\n'
            '  metadata.Text(Metadata(options, config, apm, frames, completed, first_completed_ns,\n'
            '                         first_linear_completed_ns, "OK", ""));\n')
        text = replace_once(text, '                 "[--linear-output LINEAR.f32le]]\\n";\n',
                            '                 "[--linear-output LINEAR.f32le]] "\n'
                            '                 "[--aec3-synthesis-selection observe|force-linear]\\n";\n')
    return text.encode("utf-8")


def parse_trace(data: bytes, samples: int, mode: str) -> list:
    """Read saved native observation; no process, score or DSP execution."""
    require(mode in ("observe", "force-linear") and type(samples) is int and
            samples > 0 and samples <= 256000 and samples % 160 == 0,
            "invalid selector trace input contract")
    rows = []
    require(len(data) <= 16 * 1024 * 1024, "selector trace size bound")
    for line in data.decode("utf-8").splitlines():
        if TRACE_KIND not in line:
            continue
        def distinct(items):
            result = {}
            for key, value in items:
                require(key not in result, "duplicate selector trace field")
                result[key] = value
            return result
        row = json.loads(line, object_pairs_hook=distinct)
        require(set(row) == TRACE_KEYS and row["kind"] == TRACE_KIND, "selector trace schema")
        require(type(row["block_index"]) is int and row["block_index"] == len(rows),
                "selector block index missing, duplicated, reordered or reset")
        require(all(type(row[key]) is bool for key in
                    ("source_linear", "applied_linear", "forced", "capture_output_used", "dominant_nearend_after_gain")),
                "selector trace booleans")
        require(isinstance(row["gain_bits"], list) and len(row["gain_bits"]) == 65,
                "selector gain spectrum cardinality")
        for bits in row["gain_bits"] + [row["high_bands_gain_bits"]]:
            require(type(bits) is int and 0 <= bits <= 0xffffffff,
                    "selector gain bits invalid")
            value = struct.unpack("<f", struct.pack("<I", bits))[0]
            require(math.isfinite(value) and 0 <= value <= 1,
                    "selector gain bits invalid or nonfinite")
        require(row["forced"] == (mode == "force-linear" and not row["source_linear"]) and row["capture_output_used"] and
                row["applied_linear"] == (row["source_linear"] or mode == "force-linear"),
                "selector mode or actual source mismatch")
        rows.append(row)
    require(len(rows) == samples // 64, "selector block coverage mismatch")
    return rows


def manifest(root: Path) -> dict:
    root = pristine.safe_path(root)
    result, total = {}, 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        require(all(not (Path(directory) / n).is_symlink() for n in dirs), "derived directory link")
        for name in files:
            path = Path(directory) / name
            info = path.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "derived file link/special")
            total += info.st_size
            require(len(result) < 5000 and total < 128 * 1024 * 1024 and info.st_size < 16 * 1024 * 1024,
                    "derived source size bound")
            result[path.relative_to(root).as_posix()] = pristine.file_record(path.read_bytes(), bool(info.st_mode & 0o111))
    return result


def prepare(prepared: Path, derived: Path, evidence: Path) -> dict:
    """Create one checked derivation outside the checkout; no compiler or DSP."""
    admitted = pristine.admitted(prepared)
    derived, evidence = pristine.safe_path(derived), pristine.safe_path(evidence)
    require(not derived.exists() and not evidence.exists() and
            all(pristine.separate(a, b) for a, b in ((ROOT, derived), (prepared, derived),
                                                     (derived, evidence), (ROOT, evidence))),
            "fresh disjoint source derivation paths required")
    shutil.copytree(prepared / "source", derived)
    evidence.mkdir(parents=True)
    changes, diff = {}, []
    for relative in (CONFIG, REMOVER, RUNNER):
        original = (ROOT / relative if relative == RUNNER else prepared / "source" / relative).read_bytes()
        modified = transform(relative, original)
        for role, payload in (("original", original), ("modified", modified)):
            path = evidence / role / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        if relative != RUNNER:
            (derived / relative).write_bytes(modified)
        changes[relative] = {"original_sha256": sha256(original), "modified_sha256": sha256(modified),
                             "original_bytes": len(original), "modified_bytes": len(modified)}
        diff.extend(difflib.unified_diff(original.decode().splitlines(True), modified.decode().splitlines(True),
                                         fromfile="pristine/" + relative, tofile="derived/" + relative))
    patch = "".join(diff).encode()
    (evidence / "changes.patch").write_bytes(patch)
    derived_manifest = manifest(derived)
    pristine.write_json(evidence / "derived-files.json", derived_manifest)
    receipt = {"schema_version": 1, "experiment_id": EXPERIMENT,
               "status": "EXACT_SOURCE_DERIVATION_NOT_BUILT", "pristine_receipt": admitted,
               "generator_sha256": sha256(Path(__file__).read_bytes()), "changes": changes,
               "patch_sha256": sha256(patch),
               "derived_manifest_sha256": sha256(pristine.encoded(derived_manifest)),
               "default_processing_change": False, "intervention": "only-synthesis-E-Y-selection",
               "acoustic_measurement": "NOT_RUN", "promotion_allowed": False}
    pristine.write_json(evidence / "source-transform.json", receipt)
    verify(prepared, evidence, derived)
    return receipt


def verify(prepared: Path, evidence: Path, derived: Path = None) -> dict:
    admitted = pristine.admitted(prepared)
    receipt = json.loads((evidence / "source-transform.json").read_text())
    require(receipt["experiment_id"] == EXPERIMENT and receipt["status"] == "EXACT_SOURCE_DERIVATION_NOT_BUILT"
            and receipt["pristine_receipt"] == admitted and receipt["generator_sha256"] == sha256(Path(__file__).read_bytes())
            and set(receipt["changes"]) == set(ORIGINAL_HASHES), "source transform identity")
    expected_manifest = json.loads((prepared / "files.json").read_text())
    diff = []
    for relative in (CONFIG, REMOVER, RUNNER):
        row = receipt["changes"][relative]
        original = (evidence / "original" / relative).read_bytes()
        modified = (evidence / "modified" / relative).read_bytes()
        expected_original = (ROOT / relative if relative == RUNNER else prepared / "source" / relative).read_bytes()
        require(original == expected_original and modified == transform(relative, original), "source derivation bytes changed")
        require(row == {"original_sha256": sha256(original), "modified_sha256": sha256(modified),
                        "original_bytes": len(original), "modified_bytes": len(modified)}, "source transform receipt drift")
        diff.extend(difflib.unified_diff(original.decode().splitlines(True), modified.decode().splitlines(True),
                                         fromfile="pristine/" + relative, tofile="derived/" + relative))
        if relative != RUNNER:
            expected_manifest[relative] = pristine.file_record(modified, False)
    patch = "".join(diff).encode()
    require((evidence / "changes.patch").read_bytes() == patch and sha256(patch) == receipt["patch_sha256"],
            "source patch bytes changed")
    recorded = json.loads((evidence / "derived-files.json").read_text())
    require(recorded == expected_manifest and sha256(pristine.encoded(recorded)) == receipt["derived_manifest_sha256"],
            "derived manifest differs from exact two-file patch")
    if derived is not None:
        require(manifest(derived) == recorded, "derived source tree drift")
    return receipt
