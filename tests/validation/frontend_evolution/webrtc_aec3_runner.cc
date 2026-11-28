// Offline WebRTC AEC3/APM research adapter. No SDK/runtime linkage or promotion.
#include "api/audio/audio_processing.h"
#include "api/audio/echo_canceller3_config.h"
#include "api/audio/echo_control.h"
#include "modules/audio_processing/aec3/echo_canceller3.h"

#include <array>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <memory>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr int kRate = 16000;
constexpr std::size_t kHop = 160;
constexpr std::size_t kMaxChannels = 4;
using Clock = std::chrono::steady_clock;
using Config = webrtc::AudioProcessing::Config;
using Apm = rtc::scoped_refptr<webrtc::AudioProcessing>;

struct Failure : std::runtime_error {
  int code;
  Failure(int value, const std::string& message)
      : std::runtime_error(message), code(value) {}
};

std::string Quote(const std::string& text) {
  std::ostringstream out;
  out << '"';
  for (unsigned char ch : text) {
    switch (ch) {
      case '"': out << "\\\""; break;
      case '\\': out << "\\\\"; break;
      case '\n': out << "\\n"; break;
      case '\r': out << "\\r"; break;
      case '\t': out << "\\t"; break;
      default:
        if (ch < 32) {
          out << "\\u" << std::hex << std::setw(4) << std::setfill('0')
              << static_cast<unsigned>(ch) << std::dec;
        } else {
          out << static_cast<char>(ch);
        }
    }
  }
  out << '"';
  return out.str();
}

std::uint64_t Number(const std::string& value, const std::string& name) {
  std::uint64_t result = 0;
  const auto parsed = std::from_chars(value.data(), value.data() + value.size(), result);
  if (value.empty() || parsed.ec != std::errc() || parsed.ptr != value.data() + value.size())
    throw Failure(2, "invalid unsigned integer: " + name);
  return result;
}

struct Options {
  std::string mode, mic, render, output, metadata, frame_times, map_text;
  // Empty preserves the original adapter path and metadata contract.
  std::string aec3_export_mode, linear_output;
  std::size_t channels = 0;
  std::vector<std::size_t> channel_map;
  std::optional<std::uint64_t> reset_before_frame;
};

Options Parse(int argc, char** argv) {
  Options options;
  std::set<std::string> seen;
  for (int i = 1; i < argc; i += 2) {
    const std::string key = argv[i];
    if (i + 1 >= argc || !seen.insert(key).second)
      throw Failure(2, "missing value or duplicate option: " + key);
    const std::string value = argv[i + 1];
    if (key == "--mode") options.mode = value;
    else if (key == "--mic") options.mic = value;
    else if (key == "--render") options.render = value;
    else if (key == "--output") options.output = value;
    else if (key == "--metadata") options.metadata = value;
    else if (key == "--frame-times") options.frame_times = value;
    else if (key == "--channel-map") options.map_text = value;
    else if (key == "--aec3-export-mode") options.aec3_export_mode = value;
    else if (key == "--linear-output") options.linear_output = value;
    else if (key == "--mic-channels") {
      const auto count = Number(value, key);
      if (count != 1 && count != 2 && count != 4)
        throw Failure(2, "mic channels must be 1, 2 or 4");
      options.channels = static_cast<std::size_t>(count);
    } else if (key == "--reset-before-frame") {
      options.reset_before_frame = Number(value, key);
    } else {
      throw Failure(2, "unknown option: " + key);
    }
  }
  if ((options.mode != "aec3" && options.mode != "apm") || options.channels == 0 ||
      options.mic.empty() || options.render.empty() || options.output.empty() ||
      options.metadata.empty() || options.frame_times.empty() || options.map_text.empty())
    throw Failure(2, "mode, geometry, channel map and all five file paths are required");
  std::size_t start = 0;
  std::set<std::size_t> mapped;
  do {
    const std::size_t end = options.map_text.find(',', start);
    const std::string token = options.map_text.substr(start, end - start);
    const auto source = Number(token, "--channel-map");
    if (source >= options.channels || !mapped.insert(static_cast<std::size_t>(source)).second)
      throw Failure(2, "channel map must be a permutation of [0, mic_channels)");
    options.channel_map.push_back(static_cast<std::size_t>(source));
    if (end == std::string::npos) break;
    start = end + 1;
  } while (true);
  if (options.channel_map.size() != options.channels)
    throw Failure(2, "channel map must contain every input channel exactly once");
  if ((seen.count("--aec3-export-mode") && options.aec3_export_mode.empty()) ||
      (seen.count("--linear-output") && options.linear_output.empty()))
    throw Failure(2, "observation options cannot have empty values");
  if (!options.aec3_export_mode.empty()) {
    if (options.aec3_export_mode != "default-off" &&
        options.aec3_export_mode != "factory-off" &&
        options.aec3_export_mode != "factory-on")
      throw Failure(2, "invalid AEC3 export observation mode");
    if (options.mode != "aec3" || options.channels != 1 || options.channel_map[0] != 0)
      throw Failure(2, "linear observation is restricted to mono AEC3 with channel map 0");
    if ((options.aec3_export_mode == "factory-on") != !options.linear_output.empty())
      throw Failure(2, "linear-output is required only for factory-on");
  } else if (!options.linear_output.empty()) {
    throw Failure(2, "linear-output requires an explicit factory-on observation mode");
  }
  return options;
}

std::uint64_t InputFrames(const std::string& path, std::size_t channels) {
  if (!std::filesystem::is_regular_file(path))
    throw Failure(2, "input is not a regular file: " + path);
  const auto bytes = std::filesystem::file_size(path);
  if (bytes == 0 || bytes % 2 != 0 || bytes % (kHop * channels * 2) != 0)
    throw Failure(2, "input must contain nonempty whole 10 ms S16LE frames: " + path);
  std::ifstream input(path, std::ios::binary);
  std::array<char, 12> signature{};
  input.read(signature.data(), static_cast<std::streamsize>(signature.size()));
  if (!input) throw Failure(2, "cannot read input: " + path);
  if (std::string(signature.data(), 4) == "RIFF" &&
      std::string(signature.data() + 8, 4) == "WAVE")
    throw Failure(2, "WAV container is not raw S16LE; materialize it before invoking the adapter");
  return bytes / (kHop * channels * 2);
}

void CheckOutputs(const Options& options) {
  std::set<std::filesystem::path> names;
  const auto mic = std::filesystem::weakly_canonical(options.mic);
  const auto render = std::filesystem::weakly_canonical(options.render);
  std::vector<std::string> outputs{options.output, options.metadata, options.frame_times};
  if (!options.linear_output.empty()) outputs.push_back(options.linear_output);
  for (const auto& value : outputs) {
    const auto path = std::filesystem::weakly_canonical(value);
    if (path == mic || path == render || !names.insert(path).second)
      throw Failure(2, "output paths must be distinct from each other and the inputs");
    if (std::filesystem::exists(std::filesystem::symlink_status(value)))
      throw Failure(2, "refusing existing output: " + value);
    if (!std::filesystem::is_directory(path.parent_path()))
      throw Failure(2, "output parent directory does not exist: " + value);
  }
}

class ExclusiveFile {
 public:
  explicit ExclusiveFile(const std::string& path) : file_(std::fopen(path.c_str(), "wbx")) {
    if (!file_) throw Failure(5, "cannot exclusively create output: " + path);
  }
  ExclusiveFile(const ExclusiveFile&) = delete;
  ExclusiveFile& operator=(const ExclusiveFile&) = delete;
  ~ExclusiveFile() { if (file_) std::fclose(file_); }
  void Write(const void* data, std::size_t bytes) {
    if (std::fwrite(data, 1, bytes, file_) != bytes)
      throw Failure(5, "output write failed");
  }
  void Text(const std::string& value) { Write(value.data(), value.size()); }
  void Close() {
    std::FILE* file = file_;
    file_ = nullptr;
    if (std::fclose(file) != 0) throw Failure(5, "output close failed");
  }
 private:
  std::FILE* file_;
};

Config MakeConfig(const std::string& mode) {
  const bool apm = mode == "apm";
  Config config;
  config.pipeline.maximum_internal_processing_rate = 48000;
  config.pipeline.multi_channel_render = false;
  config.pipeline.multi_channel_capture = true;
  config.pipeline.capture_downmix_method = Config::Pipeline::DownmixMethod::kAverageChannels;
  config.pre_amplifier.enabled = false;
  config.pre_amplifier.fixed_gain_factor = 1.0f;
  config.capture_level_adjustment.enabled = false;
  config.capture_level_adjustment.pre_gain_factor = 1.0f;
  config.capture_level_adjustment.post_gain_factor = 1.0f;
  config.capture_level_adjustment.analog_mic_gain_emulation.enabled = false;
  config.echo_canceller.enabled = true;
  config.echo_canceller.mobile_mode = false;
  config.echo_canceller.export_linear_aec_output = false;
  config.echo_canceller.enforce_high_pass_filtering = false;
  config.high_pass_filter.enabled = apm;
  config.high_pass_filter.apply_in_full_band = true;
  config.noise_suppression.enabled = apm;
  config.noise_suppression.level = Config::NoiseSuppression::kModerate;
  config.noise_suppression.analyze_linear_aec_output_when_available = false;
  config.transient_suppression.enabled = false;
  config.gain_controller1.enabled = false;
  config.gain_controller1.analog_gain_controller.enabled = false;
  config.gain_controller2.enabled = apm;
  config.gain_controller2.input_volume_controller.enabled = false;
  config.gain_controller2.adaptive_digital.enabled = apm;
  config.gain_controller2.adaptive_digital.headroom_db = 5.0f;
  config.gain_controller2.adaptive_digital.max_gain_db = 50.0f;
  config.gain_controller2.adaptive_digital.initial_gain_db = 15.0f;
  config.gain_controller2.adaptive_digital.max_gain_change_db_per_second = 6.0f;
  config.gain_controller2.adaptive_digital.max_output_noise_level_dbfs = -50.0f;
  config.gain_controller2.fixed_digital.gain_db = 0.0f;
  return config;
}

// This fixed distribution has the public EchoControlFactory interface but no
// EchoCanceller3Factory implementation. The APM export flag allocates its
// output buffer; the independent AEC3 filter flag allocates the block framer.
// Use only upstream defaults and change that one observation flag.
class LinearObservationFactory final : public webrtc::EchoControlFactory {
 public:
  explicit LinearObservationFactory(bool enabled) : enabled_(enabled) {}

  std::unique_ptr<webrtc::EchoControl> Create(int sample_rate_hz,
                                           int num_render_channels,
                                           int num_capture_channels) override {
    if (sample_rate_hz != kRate || num_render_channels != 1 || num_capture_channels != 1)
      throw Failure(3, "linear observation factory received unsupported geometry");
    webrtc::EchoCanceller3Config aec3;
    aec3.filter.export_linear_aec_output = enabled_;
    return std::make_unique<webrtc::EchoCanceller3>(
        aec3, std::nullopt, sample_rate_hz, num_render_channels, num_capture_channels);
  }

 private:
  const bool enabled_;
};

Apm MakeApm(const Config& config, std::size_t channels,
            const std::string& export_mode) {
  Apm apm;
  if (export_mode == "factory-off" || export_mode == "factory-on") {
    webrtc::AudioProcessingBuilder builder;
    builder.SetConfig(config).SetEchoControlFactory(
        std::make_unique<LinearObservationFactory>(export_mode == "factory-on"));
    apm = builder.Create();
  } else {
    apm = webrtc::AudioProcessingBuilder().SetConfig(config).Create();
  }
  if (!apm) throw Failure(3, "AudioProcessingBuilder returned no APM");
  webrtc::ProcessingConfig streams;
  streams.input_stream() = webrtc::StreamConfig(kRate, channels);
  streams.output_stream() = webrtc::StreamConfig(kRate, channels);
  streams.reverse_input_stream() = webrtc::StreamConfig(kRate, 1);
  streams.reverse_output_stream() = webrtc::StreamConfig(kRate, 1);
  const int result = apm->Initialize(streams);
  if (result != webrtc::AudioProcessing::kNoError)
    throw Failure(3, "APM Initialize rejected geometry, code " + std::to_string(result));
  if (apm->num_input_channels() != channels || apm->num_proc_channels() != channels ||
      apm->num_output_channels() != channels || apm->num_reverse_channels() != 1 ||
      apm->proc_sample_rate_hz() != kRate)
    throw Failure(3, "APM cannot preserve requested processing geometry; no downmix fallback");
  if (apm->GetConfig().ToString() != config.ToString())
    throw Failure(4, "applied APM config differs from the frozen requested config");
  apm->set_output_will_be_muted(false);
  return apm;
}

void LibraryResult(int code, const std::string& operation) {
  if (code != webrtc::AudioProcessing::kNoError)
    throw Failure(code == webrtc::AudioProcessing::kBadNumberChannelsError ? 3 : 4,
                  operation + " returned " + std::to_string(code));
}

std::uint64_t Nanoseconds(Clock::time_point start, Clock::time_point end) {
  return static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count());
}

void ReadFrame(std::ifstream& input, std::int16_t* values, std::size_t samples) {
  std::array<unsigned char, kHop * kMaxChannels * 2> bytes{};
  const auto count = static_cast<std::streamsize>(samples * 2);
  input.read(reinterpret_cast<char*>(bytes.data()), count);
  if (input.gcount() != count) throw Failure(5, "input shortened or became unreadable");
  for (std::size_t i = 0; i < samples; ++i) {
    const std::uint32_t value = static_cast<std::uint32_t>(bytes[2 * i]) |
        (static_cast<std::uint32_t>(bytes[2 * i + 1]) << 8);
    values[i] = static_cast<std::int16_t>(
        value >= 32768 ? static_cast<std::int32_t>(value) - 65536 :
                         static_cast<std::int32_t>(value));
  }
}

void WriteFrame(ExclusiveFile& output, const std::int16_t* values, std::size_t samples) {
  std::array<unsigned char, kHop * kMaxChannels * 2> bytes{};
  for (std::size_t i = 0; i < samples; ++i) {
    const auto value = static_cast<std::uint16_t>(values[i]);
    bytes[2 * i] = static_cast<unsigned char>(value & 255u);
    bytes[2 * i + 1] = static_cast<unsigned char>(value >> 8);
  }
  output.Write(bytes.data(), samples * 2);
}

void WriteLinearFrame(ExclusiveFile& output, const std::array<float, kHop>& values) {
  static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559,
                "linear export requires IEEE-754 binary32");
  std::array<unsigned char, kHop * 4> bytes{};
  for (std::size_t i = 0; i < kHop; ++i) {
    if (!std::isfinite(values[i]) || values[i] < -1.0f || values[i] > 1.0f)
      throw Failure(4, "upstream linear getter returned a nonfinite or out-of-range value");
    std::uint32_t bits;
    std::memcpy(&bits, &values[i], sizeof(bits));
    for (std::size_t byte = 0; byte < 4; ++byte)
      bytes[4 * i + byte] = static_cast<unsigned char>((bits >> (8 * byte)) & 255u);
  }
  // Preserve the getter's exact bits: no adapter scaling, quantization or clamp.
  output.Write(bytes.data(), bytes.size());
}

std::string ConfigJson(const Config& config) {
  std::ostringstream out;
  out << std::boolalpha << std::setprecision(9)
      << "{\"echo_canceller\":{\"enabled\":" << config.echo_canceller.enabled
      << ",\"mobile_mode\":" << config.echo_canceller.mobile_mode
      << ",\"export_linear_aec_output\":" << config.echo_canceller.export_linear_aec_output
      << ",\"enforce_high_pass_filtering\":" << config.echo_canceller.enforce_high_pass_filtering
      << "},\"high_pass_filter\":{\"enabled\":" << config.high_pass_filter.enabled
      << ",\"apply_in_full_band\":" << config.high_pass_filter.apply_in_full_band
      << "},\"noise_suppression\":{\"enabled\":" << config.noise_suppression.enabled
      << ",\"level\":\"moderate\",\"analyze_linear_aec_output_when_available\":"
      << config.noise_suppression.analyze_linear_aec_output_when_available
      << "},\"gain_controller1\":{\"enabled\":" << config.gain_controller1.enabled
      << "},\"gain_controller2\":{\"enabled\":" << config.gain_controller2.enabled
      << ",\"input_volume_controller_enabled\":" << config.gain_controller2.input_volume_controller.enabled
      << ",\"adaptive_digital\":{\"enabled\":" << config.gain_controller2.adaptive_digital.enabled
      << ",\"headroom_db\":" << config.gain_controller2.adaptive_digital.headroom_db
      << ",\"max_gain_db\":" << config.gain_controller2.adaptive_digital.max_gain_db
      << ",\"initial_gain_db\":" << config.gain_controller2.adaptive_digital.initial_gain_db
      << ",\"max_gain_change_db_per_second\":"
      << config.gain_controller2.adaptive_digital.max_gain_change_db_per_second
      << ",\"max_output_noise_level_dbfs\":"
      << config.gain_controller2.adaptive_digital.max_output_noise_level_dbfs
      << "},\"fixed_digital_gain_db\":" << config.gain_controller2.fixed_digital.gain_db
      << "},\"pre_amplifier_enabled\":" << config.pre_amplifier.enabled
      << ",\"capture_level_adjustment_enabled\":" << config.capture_level_adjustment.enabled
      << ",\"transient_suppression_enabled\":" << config.transient_suppression.enabled
      << ",\"multi_channel_capture\":" << config.pipeline.multi_channel_capture
      << ",\"multi_channel_render\":" << config.pipeline.multi_channel_render
      << ",\"capture_downmix_method\":\"average_channels\""
      << ",\"maximum_internal_processing_rate\":"
      << config.pipeline.maximum_internal_processing_rate << "}";
  return out.str();
}

std::string Metadata(const Options& options, const Config& config, const Apm& apm,
                     std::uint64_t frames, std::uint64_t completed,
                     const std::optional<std::uint64_t>& first_completed_ns,
                     const std::optional<std::uint64_t>& first_linear_completed_ns,
                     const std::string& status, const std::string& detail) {
  std::ostringstream out;
  out << "{\"schema_version\":1,\"adapter\":\"webrtc-aec3-offline-v1\","
      << "\"status\":" << Quote(status) << ",\"detail\":" << Quote(detail)
      << ",\"mode\":" << Quote(options.mode)
      << ",\"sample_format\":\"S16LE\",\"sample_rate_hz\":" << kRate
      << ",\"frame_samples\":" << kHop << ",\"mic_channels\":" << options.channels
      << ",\"render_channels\":1,\"output_channels\":" << options.channels
      << ",\"channel_map\":[";
  for (std::size_t i = 0; i < options.channel_map.size(); ++i)
    out << (i == 0 ? "" : ",") << options.channel_map[i];
  out << "],\"output_channel_order\":\"output[j] corresponds to input[channel_map[j]]\""
      << ",\"input_frames\":" << frames << ",\"completed_frames\":" << completed
      << ",\"output_sample_frames\":" << completed * kHop
      << ",\"stream_delay_ms\":0,\"adapter_lookahead_frames\":0,\"padded_samples\":0"
      << ",\"tail_flush_samples\":0,\"algorithmic_latency_samples\":"
      << (options.mode == "aec3" ? 128 : 224)
      << ",\"algorithmic_latency_ms\":" << (options.mode == "aec3" ? 8 : 14)
      << ",\"latency_basis\":\"predeclared upstream buffer delay; not a target-fitted lag\""
      << ",\"latency_components_samples\":{\"aec3_framing\":64,\"aec3_suppression_ola\":64,\"ns_ola\":"
      << (options.mode == "aec3" ? 0 : 96) << "}"
      << ",\"first_output_frame_input_samples_required\":160"
      << ",\"first_output_frame_input_time_ms\":10,\"first_output_frame_host_completion_ns\":";
  if (first_completed_ns) out << *first_completed_ns;
  else out << "null";
  out
      << ",\"call_order\":" << Quote(options.aec3_export_mode == "factory-on"
          ? "ProcessReverseStream,set_stream_delay_ms(0),ProcessStream,GetLinearAecOutput"
          : "ProcessReverseStream,set_stream_delay_ms(0),ProcessStream")
      << ",\"reset_semantics\":\"fresh APM instance per case and diagnostic reset\""
      << ",\"reset_before_frame\":";
  if (options.reset_before_frame) out << *options.reset_before_frame;
  else out << "null";
  out << ",\"aec3_includes_internal_residual_suppression\":true"
      << ",\"pure_linear_aec\":false,\"adapter_normalization\":false"
      << ",\"host_timing_only\":true,\"physical_target_measurement\":false"
      << ",\"acoustic_acceptance\":false,\"promotion_authority\":false"
      << ",\"requested_config\":" << ConfigJson(config)
      << ",\"applied_config\":";
  if (apm) out << ConfigJson(apm->GetConfig());
  else out << "null";
  out << ",\"applied_config_string\":";
  if (apm) out << Quote(apm->GetConfig().ToString());
  else out << "null";
  out << ",\"actual_processing_channels\":";
  if (apm) out << apm->num_proc_channels();
  else out << "null";
  out << ",\"actual_processing_sample_rate_hz\":";
  if (apm) out << apm->proc_sample_rate_hz();
  else out << "null";
  if (!options.aec3_export_mode.empty()) {
    const bool enabled = options.aec3_export_mode == "factory-on";
    out << ",\"aec3_linear_observation\":{\"mode\":" << Quote(options.aec3_export_mode)
        << ",\"enabled\":" << (enabled ? "true" : "false")
        << ",\"factory\":\""
        << (options.aec3_export_mode == "default-off" ? "upstream_default" : "explicit_default_aec3")
        << "\",\"internal_filter_export_linear_aec_output\":" << (enabled ? "true" : "false")
        << ",\"format\":\"F32LE\",\"channels\":1,\"samples_per_frame\":160"
        << ",\"output_samples\":" << (enabled ? completed * kHop : 0)
        << ",\"tap_signal_delay_samples\":64,\"final_signal_delay_samples\":128"
        << ",\"tap_lead_relative_to_final_samples\":64"
        << ",\"first_frame_input_samples_required\":160"
        << ",\"first_linear_frame_host_completion_ns\":";
    if (first_linear_completed_ns) out << *first_linear_completed_ns;
    else out << "null";
    out << ",\"upstream_getter_clamp_float_s16\":[-32768,32768]"
        << ",\"upstream_getter_divisor\":32768"
        << ",\"adapter_scaling\":false,\"adapter_clipping\":false"
        << ",\"adapter_quantization\":false,\"pure_lti\":false"
        << ",\"tap_stage\":\"FormLinearFilterOutput refined/coarse residual and transition\""
        << ",\"post_tap_joint_path\":\"output selection, residual suppression, comfort noise; final S16 conversion\""
        << ",\"capture_fixed_delay_samples\":0,\"distribution_commit\":\"846fe90a289f58b7c9303a635142aa2c7caa93e5\"}";
  }
  out << ",\"host_clock\":\"steady_clock nanoseconds relative to case start\"}\n";
  return out.str();
}

int Run(const Options& options) {
  const auto frames = InputFrames(options.mic, options.channels);
  if (InputFrames(options.render, 1) != frames)
    throw Failure(2, "capture and render must have exactly the same sample-frame duration");
  if (options.reset_before_frame && *options.reset_before_frame >= frames)
    throw Failure(2, "reset-before-frame must name an existing frame");
  CheckOutputs(options);
  std::ifstream mic(options.mic, std::ios::binary), render(options.render, std::ios::binary);
  if (!mic || !render) throw Failure(5, "cannot open inputs for processing");
  ExclusiveFile output(options.output), metadata(options.metadata), timing(options.frame_times);
  std::unique_ptr<ExclusiveFile> linear_output;
  if (!options.linear_output.empty())
    linear_output = std::make_unique<ExclusiveFile>(options.linear_output);
  Config config = MakeConfig(options.mode);
  if (options.aec3_export_mode == "factory-on")
    config.echo_canceller.export_linear_aec_output = true;
  Apm apm;
  std::uint64_t completed = 0;
  std::optional<std::uint64_t> first_completed_ns;
  std::optional<std::uint64_t> first_linear_completed_ns;
  const auto case_start = Clock::now();
  try {
    apm = MakeApm(config, options.channels, options.aec3_export_mode);
    const webrtc::StreamConfig capture_stream(kRate, options.channels), render_stream(kRate, 1);
    std::array<std::int16_t, kHop * kMaxChannels> raw_mic{}, capture{}, processed{};
    std::array<std::int16_t, kHop> reverse{}, reverse_output{};
    std::array<std::array<float, kHop>, 1> linear_frame{};
    for (std::uint64_t frame = 0; frame < frames; ++frame) {
      const bool reset = options.reset_before_frame && *options.reset_before_frame == frame;
      if (reset) apm = MakeApm(config, options.channels, options.aec3_export_mode);
      ReadFrame(mic, raw_mic.data(), kHop * options.channels);
      ReadFrame(render, reverse.data(), kHop);
      for (std::size_t sample = 0; sample < kHop; ++sample)
        for (std::size_t ch = 0; ch < options.channels; ++ch)
          capture[sample * options.channels + ch] =
              raw_mic[sample * options.channels + options.channel_map[ch]];
      const auto begin = Clock::now();
      LibraryResult(apm->ProcessReverseStream(reverse.data(), render_stream, render_stream,
                                             reverse_output.data()), "ProcessReverseStream");
      LibraryResult(apm->set_stream_delay_ms(0), "set_stream_delay_ms");
      LibraryResult(apm->ProcessStream(capture.data(), capture_stream, capture_stream,
                                      processed.data()), "ProcessStream");
      const auto end = Clock::now();
      if (frame == 0) first_completed_ns = Nanoseconds(case_start, end);
      std::optional<std::uint64_t> linear_completed_ns;
      if (linear_output) {
        if (!apm->GetLinearAecOutput(
                rtc::ArrayView<std::array<float, kHop>>(linear_frame.data(), linear_frame.size())))
          throw Failure(4, "GetLinearAecOutput returned false; no replacement samples are allowed");
        linear_completed_ns = Nanoseconds(case_start, Clock::now());
        if (frame == 0) first_linear_completed_ns = linear_completed_ns;
      }
      WriteFrame(output, processed.data(), kHop * options.channels);
      if (linear_output) WriteLinearFrame(*linear_output, linear_frame[0]);
      completed = frame + 1;
      std::ostringstream row;
      row << "{\"frame_index\":" << frame
          << ",\"input_sample_frames_available\":" << completed * kHop
          << ",\"output_sample_frames_emitted\":" << completed * kHop
          << ",\"host_processing_begin_ns\":" << Nanoseconds(case_start, begin)
          << ",\"host_processing_completed_ns\":" << Nanoseconds(case_start, end)
          << ",\"host_processing_duration_ns\":" << Nanoseconds(begin, end)
          << ",\"algorithmic_latency_samples\":" << (options.mode == "aec3" ? 128 : 224)
          << ",\"algorithmic_latency_ms\":" << (options.mode == "aec3" ? 8 : 14)
          << ",\"reset_before_frame\":" << (reset ? "true" : "false");
      if (!options.aec3_export_mode.empty()) {
        row << ",\"aec3_export_mode\":" << Quote(options.aec3_export_mode)
            << ",\"linear_output_sample_frames_emitted\":" << (linear_output ? completed * kHop : 0)
            << ",\"linear_signal_delay_samples\":64,\"linear_getter_completed_ns\":";
        if (linear_completed_ns) row << *linear_completed_ns;
        else row << "null";
      }
      row << ",\"host_timing_only\":true}\n";
      timing.Text(row.str());
    }
    if (mic.peek() != std::char_traits<char>::eof() ||
        render.peek() != std::char_traits<char>::eof() || mic.bad() || render.bad())
      throw Failure(5, "input length changed during processing");
    output.Close();
    if (linear_output) linear_output->Close();
    timing.Close();
  } catch (const Failure& failure) {
    metadata.Text(Metadata(options, config, apm, frames, completed, first_completed_ns,
                           first_linear_completed_ns,
                           failure.code == 3 ? "UNSUPPORTED" : "ERROR", failure.what()));
    metadata.Close();
    throw;
  }
  metadata.Text(Metadata(options, config, apm, frames, completed, first_completed_ns,
                         first_linear_completed_ns, "OK", ""));
  metadata.Close();
  return 0;
}
}  // namespace

int main(int argc, char** argv) {
  if (argc == 2 && std::string(argv[1]) == "--help") {
    std::cout << "webrtc-aec3-runner --mode aec3|apm --mic-channels 1|2|4 "
                 "--channel-map 0,... --mic INPUT.pcm --render RENDER.pcm "
                 "--output OUTPUT.pcm --metadata META.json --frame-times TIMES.jsonl "
                 "[--reset-before-frame N] "
                 "[--aec3-export-mode default-off|factory-off|factory-on "
                 "[--linear-output LINEAR.f32le]]\n";
    return 0;
  }
  try {
    return Run(Parse(argc, argv));
  } catch (const Failure& failure) {
    std::cerr << "{\"status\":" << Quote(failure.code == 3 ? "UNSUPPORTED" : "ERROR")
              << ",\"error\":" << Quote(failure.what())
              << ",\"exit_code\":" << failure.code << "}\n";
    return failure.code;
  } catch (const std::exception& failure) {
    std::cerr << "{\"status\":\"ERROR\",\"error\":" << Quote(failure.what())
              << ",\"exit_code\":5}\n";
    return 5;
  }
}
