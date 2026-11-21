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

// Per-source SHA-256 and one digest over (path relative to the entry directory, digest)
// pairs in load order, so the identity is the same on any machine with the same files.
nlohmann::json sourceIdentity(const std::string& entry, const std::vector<std::string>& sources) {
  const auto base = std::filesystem::absolute(entry).lexically_normal().parent_path();
  nlohmann::json files = nlohmann::json::array();
  std::string combined;
  for (const auto& source : sources) {
    const auto relative = std::filesystem::path(source).lexically_relative(base).generic_string();
    const auto digest = sha256Hex(readBytes(source));
    files.push_back({{"path", relative}, {"sha256", digest}});
    combined += relative;
    combined.push_back('\0');
    combined += digest;
    combined.push_back('\n');
  }
  return {{"entry", entry}, {"sources_sha256", sha256Hex(combined)}, {"sources", files}};
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

void LabScriptHost::commit(LabScriptCandidate candidate) {
  if (!candidate.runtime) throw std::invalid_argument("lab script candidate has no runtime");
  auto identity = sourceIdentity(experimentPath_, candidate.runtime->sourceFiles());
  active_->swap(*candidate.runtime);
  parameters_ = std::move(candidate.parameters);
  registeredHooks_ = candidate.config.hooks.registered;
  init_ = std::move(candidate.init);
  initPending_ = true;
  generation_ += 1;
  identity["generation"] = generation_;
  identity["parameter_overrides"] = parameters_;
  identity_ = std::move(identity);
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
