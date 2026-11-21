#include "trech/core/LabSession.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <utility>

#include <nlohmann/json.hpp>

namespace trech {
namespace {

std::string normalizeAction(std::string action) {
  std::string normalized;
  normalized.reserve(action.size());
  for (char ch : action) {
    const auto uc = static_cast<unsigned char>(ch);
    if (std::isalnum(uc)) {
      normalized.push_back(static_cast<char>(std::tolower(uc)));
    }
  }
  return normalized;
}

bool parseSeed(const nlohmann::json& value, std::uint64_t& outSeed) {
  if (value.is_number_unsigned()) {
    outSeed = value.get<std::uint64_t>();
    return true;
  }
  if (value.is_number_integer()) {
    const auto v = value.get<long long>();
    if (v < 0) {
      return false;
    }
    outSeed = static_cast<std::uint64_t>(v);
    return true;
  }
  return false;
}

bool parseEventCount(const nlohmann::json& value, int& outEvents) {
  if (!value.is_number_integer()) {
    return false;
  }
  const auto count = value.get<std::uint64_t>();
  if (count == 0 || count > static_cast<std::uint64_t>(std::numeric_limits<int>::max())) {
    return false;
  }
  outEvents = static_cast<int>(count);
  return true;
}

LabCommandResult failureResult(const std::string& message) {
  LabCommandResult result;
  result.ok = false;
  result.message = message;
  return result;
}

std::string helpText(bool scriptBacked) {
  std::ostringstream out;
  out << "Lab actions: "
      << "patch({\"patch\":{...}}), simulate() [adaptive], "
      << "simulate({\"events\":N,\"seed\":S}) [override], ";
  if (scriptBacked) {
    out << "reload [re-read the scenario], params({\"values\":{name:json}}) [TRECH_VALUE], ";
  }
  out << "snapshot, help, quit";
  return out.str();
}

void enableLab(TrechConfig& cfg) {
  cfg.lab.enable = true;
  if (cfg.lab.mode.empty() || cfg.lab.mode == "scenario") {
    cfg.lab.mode = "realtime";
  }
}

} // namespace

std::string labKernelSignature(const TrechConfig& cfg) {
  auto config = nlohmann::json::parse(configToJsonString(cfg));
  if (config.contains("run") && config.at("run").is_object()) {
    config["run"].erase("nEvents");
    config["run"].erase("seed");
  }
  // Planner settings affect batch selection, not the initialized Geant4
  // detector/physics/action graph.
  config.erase("lab");
  return config.dump();
}

LabSession::LabSession(TrechConfig initialConfig, bool strictConfig, bool scriptBacked)
    : cfg_(std::move(initialConfig)), strictConfig_(strictConfig), scriptBacked_(scriptBacked) {
  enableLab(cfg_);
  roundTelemetry_.targetSeconds = 1.0 / std::max(1, cfg_.lab.targetHz);
}

const TrechConfig& LabSession::config() const {
  return cfg_;
}

std::string LabSession::configJson() const {
  return configToJsonString(cfg_);
}

const LabRoundTelemetry& LabSession::roundTelemetry() const {
  return roundTelemetry_;
}

int LabSession::planAdaptiveRounds() const {
  const int lo = std::max(1, cfg_.lab.minRoundsPerTick);
  const int hi = std::max(lo, cfg_.lab.maxRoundsPerTick);
  if (cfg_.lab.roundsPerTick > 0) {
    return std::clamp(cfg_.lab.roundsPerTick, lo, hi);
  }
  if (roundTelemetry_.secondsPerRoundEwma <= 0.0) {
    return std::clamp(cfg_.run.nEvents, lo, hi);
  }
  const double target = 1.0 / std::max(1, cfg_.lab.targetHz);
  // Clamp before converting: a very fast measured round may exceed int range.
  const double fitted = std::floor(target / roundTelemetry_.secondsPerRoundEwma);
  return static_cast<int>(std::clamp(fitted, static_cast<double>(lo), static_cast<double>(hi)));
}

std::string LabSession::roundTelemetryJson() const {
  nlohmann::json runtime = {
      {"phase", "lab_round_plan"},
      {"adaptive", roundTelemetry_.adaptive},
      {"target_hz", cfg_.lab.targetHz},
      {"target_seconds", roundTelemetry_.targetSeconds},
      {"planned_rounds", roundTelemetry_.plannedRounds},
      {"observations", roundTelemetry_.observations},
      {"last_wall_seconds", roundTelemetry_.lastWallSeconds},
      {"seconds_per_round_ewma", roundTelemetry_.secondsPerRoundEwma},
      {"achieved_hz", roundTelemetry_.achievedHz},
  };
  return runtime.dump();
}

std::string LabSession::snapshotJson() const {
  nlohmann::json snapshot = nlohmann::json::parse(configToJsonString(cfg_));
  snapshot["lab"]["roundPlanner"] = nlohmann::json::parse(roundTelemetryJson());
  if (scriptStatus_.is_object()) {
    snapshot["lab"]["script"] = scriptStatus_;
  }
  return snapshot.dump();
}

TrechConfig LabSession::rebasedConfig(const TrechConfig& scenarioConfig) const {
  auto merged = nlohmann::json::parse(configToJsonString(scenarioConfig));
  for (const auto& patch : patches_) {
    merged.merge_patch(patch);
  }
  auto candidate = configFromJsonString(merged.dump());
  candidate.run.nEvents = cfg_.run.nEvents;
  candidate.run.seed = cfg_.run.seed;
  enableLab(candidate);
  if (strictConfig_) requireNoUnknownConfigKeys(candidate);
  return candidate;
}

void LabSession::adoptConfig(TrechConfig cfg) {
  cfg_ = std::move(cfg);
  roundTelemetry_.targetSeconds = 1.0 / std::max(1, cfg_.lab.targetHz);
}

void LabSession::setScriptStatus(nlohmann::json status) {
  scriptStatus_ = std::move(status);
}

void LabSession::observeSimulation(double wallSeconds) {
  const int rounds = std::max(1, roundTelemetry_.plannedRounds);
  if (!std::isfinite(wallSeconds) || wallSeconds <= 0.0) {
    return;
  }
  const double observed = wallSeconds / static_cast<double>(rounds);
  const double gain = std::clamp(cfg_.lab.roundLearningRate, 0.01, 1.0);
  if (roundTelemetry_.observations == 0 ||
      roundTelemetry_.secondsPerRoundEwma <= 0.0) {
    roundTelemetry_.secondsPerRoundEwma = observed;
  } else {
    roundTelemetry_.secondsPerRoundEwma =
        gain * observed + (1.0 - gain) * roundTelemetry_.secondsPerRoundEwma;
  }
  roundTelemetry_.observations += 1;
  roundTelemetry_.lastWallSeconds = wallSeconds;
  roundTelemetry_.achievedHz = 1.0 / wallSeconds;
}

LabCommandResult LabSession::applyCommandJson(const std::string& commandJson) {
  nlohmann::json command;
  try {
    command = nlohmann::json::parse(commandJson);
  } catch (const std::exception& ex) {
    return failureResult(std::string("Invalid JSON command: ") + ex.what());
  }

  if (!command.is_object()) {
    return failureResult("Command must be a JSON object.");
  }

  std::string action;
  if (command.contains("action") && command.at("action").is_string()) {
    action = command.at("action").get<std::string>();
  } else if (command.contains("type") && command.at("type").is_string()) {
    action = command.at("type").get<std::string>();
  }
  action = normalizeAction(action);

  if (action.empty()) {
    return failureResult("Command is missing a string action.");
  }

  if (action == "help") {
    LabCommandResult result;
    result.message = helpText(scriptBacked_);
    return result;
  }

  if (action == "quit" || action == "exit") {
    LabCommandResult result;
    result.continueSession = false;
    result.message = "Lab session closed.";
    return result;
  }

  if (action == "snapshot") {
    LabCommandResult result;
    result.hasSnapshot = true;
    result.snapshotJson = snapshotJson();
    result.message = "Snapshot emitted.";
    return result;
  }

  if (action == "simulate") {
    auto nextRun = cfg_.run;
    bool explicitRounds = false;
    if (command.contains("events")) {
      int events = 0;
      if (!parseEventCount(command.at("events"), events)) {
        return failureResult("simulate.events must be a positive integer in range.");
      }
      nextRun.nEvents = events;
      explicitRounds = true;
    }
    if (command.contains("seed")) {
      std::uint64_t seed = 0;
      if (!parseSeed(command.at("seed"), seed)) {
        return failureResult("simulate.seed must be a non-negative integer.");
      }
      nextRun.seed = seed;
    }
    if (command.contains("run")) {
      const auto& run = command.at("run");
      if (!run.is_object()) {
        return failureResult("simulate.run must be an object.");
      }
      if (run.contains("nEvents")) {
        int events = 0;
        if (!parseEventCount(run.at("nEvents"), events)) {
          return failureResult("simulate.run.nEvents must be a positive integer in range.");
        }
        nextRun.nEvents = events;
        explicitRounds = true;
      }
      if (run.contains("seed")) {
        std::uint64_t seed = 0;
        if (!parseSeed(run.at("seed"), seed)) {
          return failureResult("simulate.run.seed must be a non-negative integer.");
        }
        nextRun.seed = seed;
      }
    }
    LabCommandResult result;
    const bool configuredOverride = cfg_.lab.roundsPerTick > 0;
    if (!explicitRounds) {
      nextRun.nEvents = planAdaptiveRounds();
    }
    cfg_.run = nextRun;
    roundTelemetry_.plannedRounds = cfg_.run.nEvents;
    roundTelemetry_.targetSeconds = 1.0 / std::max(1, cfg_.lab.targetHz);
    roundTelemetry_.adaptive = !explicitRounds && !configuredOverride;
    result.requestSimulation = true;
    result.adaptiveSimulation = roundTelemetry_.adaptive;
    result.simulationRounds = cfg_.run.nEvents;
    std::ostringstream message;
    message << "Simulation queued: " << cfg_.run.nEvents << " round(s) ["
            << (roundTelemetry_.adaptive ? "adaptive" : "override") << "].";
    result.message = message.str();
    return result;
  }

  if (action == "patch" || action == "mergeconfig" || action == "set") {
    nlohmann::json patch;
    if (command.contains("patch")) {
      patch = command.at("patch");
    } else if (command.contains("config")) {
      patch = command.at("config");
    } else {
      patch = command;
      patch.erase("action");
      patch.erase("type");
    }
    if (!patch.is_object()) {
      return failureResult("patch command requires an object payload.");
    }
    try {
      const auto before = configJson();
      auto current = nlohmann::json::parse(before);
      current.merge_patch(patch);
      auto candidate = configFromJsonString(current.dump());
      if (strictConfig_) requireNoUnknownConfigKeys(candidate);
      const bool changed = configToJsonString(candidate) != before;
      cfg_ = std::move(candidate);
      patches_.push_back(patch);
      roundTelemetry_.targetSeconds = 1.0 / std::max(1, cfg_.lab.targetHz);
      LabCommandResult result;
      result.ignoredConfigKeys = cfg_.unknownKeys;
      result.message = changed ? "Patch applied." : "Patch accepted (no changes).";
      return result;
    } catch (const std::exception& ex) {
      return failureResult(std::string("Patch failed: ") + ex.what());
    }
  }

  if (action == "reload" || action == "params" || action == "values") {
    if (!scriptBacked_) {
      return failureResult(action + " needs a scenario-backed lab: start it with "
                           "`trech lab <experiment.js>`.");
    }
    LabCommandResult result;
    result.requestScriptReload = true;
    if (action != "reload") {
      const char* key = command.contains("values") ? "values" : "params";
      if (!command.contains(key) || !command.at(key).is_object()) {
        return failureResult(action + " requires an object of TRECH_VALUE values "
                             "({\"values\":{\"name\":<json>}}).");
      }
      result.scriptParameterChanges = command.at(key);
    }
    return result;
  }

  return failureResult("Unknown lab action: " + action);
}

} // namespace trech
