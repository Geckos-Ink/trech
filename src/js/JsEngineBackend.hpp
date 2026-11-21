// Private interface between trech::JsRuntime (the public facade) and one JavaScript engine.
// src/js/JsRuntime.cpp implements it once against the QuickJS C API; the QuickJS build
// compiles it against quickjs.h, and src/js/JsRuntimeV8.cpp compiles the same source against
// the V8 implementation of that API (src/js/V8QuickJsApi.hpp).
#pragma once

#include "trech/js/JsRuntime.hpp"

#include <memory>
#include <string>
#include <vector>

namespace trech {

class JsEngineBackend {
public:
  virtual ~JsEngineBackend() = default;
  virtual std::string evalExperimentAndGetConfigJson(const std::string& path) = 0;
  virtual void setScriptParameterOverrides(const std::vector<std::string>& overrides) = 0;
  virtual void setPrecisionRefinement(double factor) = 0;
  virtual std::string scriptParametersJson() const = 0;
  virtual std::string authoringMetadataJson() const = 0;
  virtual std::vector<std::string> sourceFiles() const = 0;
  virtual std::vector<JsSourceDigest> sourceDigests() const = 0;
  virtual HookDispatchReport dispatchHook(const std::string& hookName,
                                          const HookRuntimeContext& context,
                                          TrechConfig* cfgForPatch, bool allowPatch) = 0;
  virtual std::vector<HookEmitRecord> takeEmittedRecords() = 0;
  virtual void loadDeclaredModels() = 0;
  virtual std::vector<std::string> loadedModelNames() const = 0;
  virtual std::string modelArtifactsJson() const = 0;
  virtual int totalPredictCount() const = 0;
  virtual int totalOutOfDomainCount() const = 0;
};

std::unique_ptr<JsEngineBackend> makeQuickJsBackend();
#ifdef TRECH_HAS_V8
std::unique_ptr<JsEngineBackend> makeV8Backend();
std::string v8EngineVersion();
#endif

}  // namespace trech
