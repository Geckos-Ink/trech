#pragma once

#include "trech/core/Config.hpp"

#include <cstdint>
#include <string>
#include <vector>

namespace trech {

struct HookRuntimeContext {
  std::uint64_t seed = 0;
  int nEvents = 0;
  std::string determinismMode = "strict";
  int eventId = -1;
  int stepIndex = -1;
  double stepEdepMeV = 0.0;
  double stepLengthMm = 0.0;
  int maxEmitsPerCallback = 0;
  int maxEmitPayloadBytes = 0;
};

struct HookEmitRecord {
  std::string hook;
  std::string tag;
  std::string payloadJson;
  int eventId = -1;
  int stepIndex = -1;
};

struct HookDispatchReport {
  bool invoked = false;
  bool patchApplied = false;
  std::vector<std::string> patchedPaths;
  std::size_t emitCount = 0;
  std::size_t emitDroppedCount = 0;
};

class JsRuntime {
public:
  JsRuntime();
  ~JsRuntime();

  std::string evalExperimentAndGetConfigJson(const std::string& path);
  HookDispatchReport dispatchHook(const std::string& hookName,
                                  const HookRuntimeContext& context,
                                  TrechConfig* cfgForPatch,
                                  bool allowPatch);
  std::vector<HookEmitRecord> takeEmittedRecords();

private:
  struct Impl;
  Impl* impl_ = nullptr;
};

} // namespace trech
