#include "trech/js/LabScriptHost.hpp"

#include "trech/core/Provenance.hpp"

#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <utility>

namespace trech {
namespace {

std::string readBytes(const std::string& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) throw std::runtime_error("cannot read scenario source " + path);
  std::ostringstream buffer;
  buffer << in.rdbuf();
  return buffer.str();
}

// Per-file SHA-256 of the bytes the evaluation read, and one digest over (path relative to
// the entry directory, digest) pairs in load order, so the identity is the same on any machine
// with the same files. TRECH_READ_JSON data files are listed apart and join the digest after
// the script sources.
nlohmann::json sourceIdentity(const std::string& entry, const std::vector<JsSourceDigest>& files) {
  const auto base = std::filesystem::absolute(entry).lexically_normal().parent_path();
  nlohmann::json sources = nlohmann::json::array();
  nlohmann::json data = nlohmann::json::array();
  std::string combined;
  for (const auto& file : files) {
    const auto relative = std::filesystem::path(file.path).lexically_relative(base).generic_string();
    (file.data ? data : sources).push_back({{"path", relative}, {"sha256", file.sha256}});
    if (file.data) combined += "data:";
    combined += relative;
    combined.push_back('\0');
    combined += file.sha256;
    combined.push_back('\n');
  }
  nlohmann::json identity = {
      {"entry", entry}, {"sources_sha256", sha256Hex(combined)}, {"sources", sources}};
  if (!data.empty()) identity["data"] = data;
  return identity;
}

nlohmann::json tallyJson(const HookInitTallies& init) {
  return {{"dispatched", init.dispatched},
          {"patch_count", init.patchCount},
          {"ignored_patch_paths", init.ignoredPatchPaths},
          {"emit_count", init.emitCount},
          {"emit_dropped_count", init.emitDroppedCount},
          {"predict_count", init.predictCount},
          {"predict_out_of_domain_count", init.outOfDomainCount}};
}

}  // namespace

LabScriptHost::LabScriptHost(std::string experimentPath,
                             const std::vector<std::string>& cliOverrides, bool strictConfig)
    : experimentPath_(std::move(experimentPath)), strictConfig_(strictConfig),
      active_(std::make_unique<JsRuntime>()) {
  // Parse the CLI's name=<json> list once with the runtime's own validation.
  JsRuntime parser;
  parser.setScriptParameterOverrides(cliOverrides);
  for (const auto& entry : cliOverrides) {
    const auto equals = entry.find('=');
    parameters_[entry.substr(0, equals)] = nlohmann::json::parse(entry.substr(equals + 1));
  }
}

LabScriptHost::~LabScriptHost() = default;

LabScriptCandidate LabScriptHost::prepare(const nlohmann::json& changes) const {
  if (!changes.is_object()) throw std::invalid_argument("TRECH_VALUE changes must be an object");
  LabScriptCandidate candidate;
  candidate.parameters = parameters_;
  for (const auto& [name, value] : changes.items()) {
    if (value.is_null()) {
      candidate.parameters.erase(name);
    } else {
      candidate.parameters[name] = value;
    }
  }
  std::vector<std::string> overrides;
  for (const auto& [name, value] : candidate.parameters.items()) {
    overrides.push_back(name + "=" + value.dump());
  }
  candidate.runtime = std::make_unique<JsRuntime>();
  candidate.runtime->setScriptParameterOverrides(overrides);
  const auto configJson = candidate.runtime->evalExperimentAndGetConfigJson(experimentPath_);
  candidate.config = configFromJsonString(configJson);
  if (strictConfig_) requireNoUnknownConfigKeys(candidate.config);

  // onInit sees the scenario's own run settings, exactly as in `trech run`.
  HookRuntimeContext context;
  context.seed = candidate.config.run.seed;
  context.nEvents = candidate.config.run.nEvents;
  context.determinismMode = candidate.config.determinism.mode;
  context.maxEmitsPerCallback = candidate.config.hooks.maxEmitsPerCallback;
  context.maxEmitPayloadBytes = candidate.config.hooks.maxEmitPayloadBytes;
  const auto report = candidate.runtime->dispatchHook("onInit", context, &candidate.config, true);
  if (strictConfig_ && !report.ignoredPatchPaths.empty()) {
    throw std::invalid_argument("--strict-config: onInit override has " +
                                std::to_string(report.ignoredPatchPaths.size()) +
                                " path(s) that were not applied");
  }
  candidate.init.dispatched = true;
  candidate.init.patchCount = report.patchApplied ? 1 : 0;
  candidate.init.ignoredPatchPaths = report.ignoredPatchPaths;
  candidate.init.emitCount = static_cast<int>(report.emitCount);
  candidate.init.emitDroppedCount = static_cast<int>(report.emitDroppedCount);
  candidate.init.predictCount = static_cast<int>(report.predictCount);
  candidate.init.outOfDomainCount = static_cast<int>(report.outOfDomainCount);
  return candidate;
}

void LabScriptHost::commit(LabScriptCandidate candidate, const std::string& trigger) {
  if (!candidate.runtime) throw std::invalid_argument("lab script candidate has no runtime");
  const auto digests = candidate.runtime->sourceDigests();
  auto identity = sourceIdentity(experimentPath_, digests);
  active_->swap(*candidate.runtime);
  parameters_ = std::move(candidate.parameters);
  registeredHooks_ = candidate.config.hooks.registered;
  init_ = std::move(candidate.init);
  initPending_ = true;
  generation_ += 1;
  identity["generation"] = generation_;
  identity["trigger"] = trigger;
  identity["parameter_overrides"] = parameters_;
  // Named only for a non-QuickJS engine, so QuickJS lab records keep their shape.
  if (active_->engine() != JsEngine::QuickJs) identity["js_engine"] = active_->engineIdentity();
  identity_ = std::move(identity);
  watched_.clear();
  for (const auto& file : digests) watched_.push_back({file.path, file.sha256, {}, -1});
  refusedFingerprint_.clear();
}

std::string LabScriptHost::changedSourceFingerprint() {
  bool changed = false;
  std::string fingerprint;
  for (auto& file : watched_) {
    std::error_code error;
    const auto stamp = std::filesystem::last_write_time(file.path, error);
    const auto size = error ? -1 : static_cast<std::intmax_t>(std::filesystem::file_size(file.path, error));
    std::string digest;
    if (error) {
      digest = "missing";
    } else if (file.size == size && file.stamp == stamp) {
      digest = file.sha256;  // untouched since the last look: skip the read
    } else {
      try {
        digest = sha256Hex(readBytes(file.path));
      } catch (const std::exception&) {
        digest = "missing";
      }
      // A touch that keeps the bytes is no change; remember the stamp so it is not re-read.
      if (digest == file.sha256) {
        file.stamp = stamp;
        file.size = size;
      }
    }
    if (digest != file.sha256) changed = true;
    fingerprint += file.path;
    fingerprint.push_back('\0');
    fingerprint += digest;
    fingerprint.push_back('\n');
  }
  if (!changed) return {};
  fingerprint = sha256Hex(fingerprint);
  return fingerprint == refusedFingerprint_ ? std::string() : fingerprint;
}

void LabScriptHost::refuseWatchedEdit(const std::string& fingerprint) {
  refusedFingerprint_ = fingerprint;
}

nlohmann::json LabScriptHost::status() const {
  nlohmann::json out = identity_;
  out["phase"] = "lab_script";
  out["parameters"] = nlohmann::json::parse(active_->scriptParametersJson());
  out["hooks_registered"] = registeredHooks_;
  out["on_init"] = tallyJson(init_);
  return out;
}

void LabScriptHost::prepareBatch(RuntimeRunMetadata& metadata) const {
  metadata.hasHookInit = true;
  metadata.hookInit = initPending_ ? init_ : HookInitTallies{};
  metadata.labScriptJson = identity_.dump();
}

void LabScriptHost::batchCompleted() {
  initPending_ = false;
}

}  // namespace trech
