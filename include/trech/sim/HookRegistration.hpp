#pragma once

// Geant4-free classification of `hooks.registered` names, shared by RunAction
// (which counts callbacks during a run) and the geometry-refusal provenance
// record (written before any event runs). Keeping one classifier means a
// refused run reports `hooks_enabled` and `hook_unknown_registered_count` the
// way a normal run_start record would for the same config.

#include "trech/core/Config.hpp"
#include "trech/core/Provenance.hpp"
#include "trech/core/RunOptions.hpp"

#include <algorithm>
#include <cctype>
#include <string>
#include <vector>

namespace trech::sim {

// Lower-case alphanumerics only: "onStep", "on_step" and "ON-STEP" are one hook.
inline std::string normalizeHookName(const std::string& hook) {
  std::string normalized;
  normalized.reserve(hook.size());
  for (char ch : hook) {
    const auto uc = static_cast<unsigned char>(ch);
    if (std::isalnum(uc)) {
      normalized.push_back(static_cast<char>(std::tolower(uc)));
    }
  }
  return normalized;
}

struct HookRegistration {
  bool onInit = false;
  bool onRunStart = false;
  bool onEventStart = false;
  bool onStep = false;
  bool onEventEnd = false;
  bool onRunEnd = false;
  bool onTrackStart = false;
  bool onTrackEnd = false;
  // Non-empty names that match no recognised hook.
  int unknownCount = 0;

  bool any() const {
    return onInit || onRunStart || onEventStart || onStep || onEventEnd || onRunEnd ||
           onTrackStart || onTrackEnd;
  }
  bool trackCallbacks() const { return onTrackStart || onTrackEnd; }
};

inline HookRegistration classifyRegisteredHooks(const std::vector<std::string>& registered) {
  HookRegistration hooks;
  for (const auto& raw : registered) {
    const auto name = normalizeHookName(raw);
    if (name == "oninit") {
      hooks.onInit = true;
    } else if (name == "onrunstart") {
      hooks.onRunStart = true;
    } else if (name == "oneventstart") {
      hooks.onEventStart = true;
    } else if (name == "onstep") {
      hooks.onStep = true;
    } else if (name == "oneventend") {
      hooks.onEventEnd = true;
    } else if (name == "onrunend") {
      hooks.onRunEnd = true;
    } else if (name == "ontrackstart") {
      hooks.onTrackStart = true;
    } else if (name == "ontrackend") {
      hooks.onTrackEnd = true;
    } else if (!name.empty()) {
      ++hooks.unknownCount;
    }
  }
  return hooks;
}

// Hook fields of a provenance record written before any event runs (the
// geometry_refused phase). onInit was already dispatched by the CLI before
// Geant4 construction (in a lab, only when it is scenario-backed), so its count, patch, emit and
// predict tallies are real; every per-run/per-event callback count stays 0 because none ran.
// Guardrails are the clamped config values RunAction would have applied.
inline void fillPreRunHookProvenance(ProvenanceRecord& record, const TrechConfig& cfg,
                                     const RunOptions& options) {
  const auto hooks = classifyRegisteredHooks(cfg.hooks.registered);
  record.hooksEnabled = hooks.any();
  record.hooksRegistered = cfg.hooks.registered;
  record.hookUnknownRegisteredCount = hooks.unknownCount;
  record.hooksGuardrailMaxStepCallbacks = std::max(0, cfg.hooks.maxStepCallbacks);
  record.hooksGuardrailMaxEmitsPerCallback = std::max(0, cfg.hooks.maxEmitsPerCallback);
  record.hooksGuardrailMaxEmitPayloadBytes = std::max(0, cfg.hooks.maxEmitPayloadBytes);
  record.hookTrackCallbacksActive = hooks.trackCallbacks();
  if (record.hookTrackCallbacksActive) {
    record.hooksGuardrailMaxTrackCallbacks = std::max(0, cfg.hooks.maxTrackCallbacks);
  }
  // A config-only lab runs no JavaScript: a registered onInit did not run there.
  record.hookOnInitCount = hooks.onInit && options.hookInitDispatched ? 1 : 0;
  record.hookPatchCount = options.hookInitPatchCount;
  record.hookPatchIgnoredPaths = options.hookInitIgnoredPatchPaths;
  record.hookEmitCount = options.hookInitEmitCount;
  record.hookEmitDroppedCount = options.hookInitEmitDroppedCount;
  record.hookPredictCount = options.hookInitPredictCount;
  record.hookOutOfDomainCount = options.hookInitOutOfDomainCount;
}

}  // namespace trech::sim
