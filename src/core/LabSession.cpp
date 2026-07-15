#include "trech/core/LabSession.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
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
  outEvents = value.get<int>();
  return outEvents > 0;
}

bool mergeJsonObject(nlohmann::json& target, const nlohmann::json& patch) {
  if (!patch.is_object()) {
    return false;
  }

  bool changed = false;
  for (auto it = patch.begin(); it != patch.end(); ++it) {
    const auto& key = it.key();
    const auto& value = it.value();

    if (value.is_null()) {
      changed = target.erase(key) > 0 || changed;
      continue;
    }

    if (target.contains(key) && target.at(key).is_object() && value.is_object()) {
      changed = mergeJsonObject(target[key], value) || changed;
      continue;
    }

    if (!target.contains(key) || target.at(key) != value) {
      target[key] = value;
      changed = true;
    }
  }
  return changed;
}

LabCommandResult failureResult(const std::string& message) {
  LabCommandResult result;
  result.ok = false;
  result.message = message;
  return result;
}

std::string helpText() {
  std::ostringstream out;
  out << "Lab actions: "
      << "patch({\"patch\":{...}}), simulate() [adaptive], "
      << "simulate({\"events\":N,\"seed\":S}) [override], "
      << "snapshot, help, quit";
  return out.str();
}

} // namespace

LabSession::LabSession(TrechConfig initialConfig) : cfg_(std::move(initialConfig)) {
  cfg_.lab.enable = true;
  if (cfg_.lab.mode.empty() || cfg_.lab.mode == "scenario") {
    cfg_.lab.mode = "realtime";
  }
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
  const auto fitted = static_cast<int>(std::floor(target /
      roundTelemetry_.secondsPerRoundEwma));
  return std::clamp(std::max(1, fitted), lo, hi);
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
  return snapshot.dump();
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
    result.message = helpText();
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
    bool explicitRounds = false;
    if (command.contains("events")) {
      int events = 0;
      if (!parseEventCount(command.at("events"), events)) {
        return failureResult("simulate.events must be a positive integer.");
      }
      cfg_.run.nEvents = events;
      explicitRounds = true;
    }
    if (command.contains("seed")) {
      std::uint64_t seed = 0;
      if (!parseSeed(command.at("seed"), seed)) {
        return failureResult("simulate.seed must be a non-negative integer.");
      }
      cfg_.run.seed = seed;
    }
    if (command.contains("run") && command.at("run").is_object()) {
      const auto& run = command.at("run");
      if (run.contains("nEvents")) {
        int events = 0;
        if (!parseEventCount(run.at("nEvents"), events)) {
          return failureResult("simulate.run.nEvents must be a positive integer.");
        }
        cfg_.run.nEvents = events;
        explicitRounds = true;
      }
      if (run.contains("seed")) {
        std::uint64_t seed = 0;
        if (!parseSeed(run.at("seed"), seed)) {
          return failureResult("simulate.run.seed must be a non-negative integer.");
        }
        cfg_.run.seed = seed;
      }
    }
    LabCommandResult result;
    const bool configuredOverride = cfg_.lab.roundsPerTick > 0;
    if (!explicitRounds) {
      cfg_.run.nEvents = planAdaptiveRounds();
    }
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
      nlohmann::json current = nlohmann::json::parse(configToJsonString(cfg_));
      const bool changed = mergeJsonObject(current, patch);
      cfg_ = configFromJsonString(current.dump());
      roundTelemetry_.targetSeconds = 1.0 / std::max(1, cfg_.lab.targetHz);
      LabCommandResult result;
      result.message = changed ? "Patch applied." : "Patch accepted (no changes).";
      return result;
    } catch (const std::exception& ex) {
      return failureResult(std::string("Patch failed: ") + ex.what());
    }
  }

  return failureResult("Unknown lab action: " + action);
}

} // namespace trech
