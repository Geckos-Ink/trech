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
  double eventEdepMeV = 0.0;
  double eventTotalTrackLengthMm = 0.0;
  int eventTotalStepCount = 0;
  int eventTotalTrackCount = 0;
  int eventOpticalPhotonSteps = 0;
  int eventOpticalPhotonTracks = 0;
  double eventOpticalPhotonTrackLengthMm = 0.0;
  // Serialized Geant4 material-composition probes (JSON array). Run-constant;
  // when non-empty the runtime exposes it to hooks as ctx.materials. Empty
  // string => ctx.materials is left undefined.
  std::string materialsJson;
  // Serialized Geant4-derived optical spectra/results (JSON array). Run-
  // constant; exposed as ctx.optics and also added to the ambient cascade seed
  // so observer-scale colour/appearance models can start from the same engine
  // result Studio renders. Empty => ctx.optics is undefined.
  std::string opticsJson;
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
  std::size_t predictCount = 0;
  // Subset of predictCount whose inputs fell outside the model's trained domain
  // (a cascade contributes its stagesExtrapolating; ctx.predict contributes 1;
  // ctx.evolve/ctx.react contribute each out-of-domain element-stage) -- the
  // auditable low-confidence run fact (workstream 3a).
  std::size_t outOfDomainCount = 0;
};

class JsRuntime {
public:
  JsRuntime();
  ~JsRuntime();

  std::string evalExperimentAndGetConfigJson(const std::string& path);
  // Set repeatable `name=<json>` overrides before evaluating an experiment.
  // TRECH_VALUE validates each selected value against its declaration.
  void setScriptParameterOverrides(const std::vector<std::string>& overrides);
  // Canonical array of typed TRECH_VALUE declarations encountered during the
  // last evaluation, including resolved values and override provenance.
  std::string scriptParametersJson() const;
  HookDispatchReport dispatchHook(const std::string& hookName,
                                  const HookRuntimeContext& context,
                                  TrechConfig* cfgForPatch,
                                  bool allowPatch);
  std::vector<HookEmitRecord> takeEmittedRecords();

  // Load the scenario-declared models[] into the GenericSurrogate registry the
  // hook layer's ctx.predict uses. Called automatically after config eval;
  // exposed so a caller that mutates the config can reload the registry.
  void loadDeclaredModels();
  // Names of models that actually loaded (sorted; for provenance).
  std::vector<std::string> loadedModelNames() const;
  // Run-total learned inferences across predict/cascade/evolve/react.
  int totalPredictCount() const;
  // Run-total learned predictions made outside the model's trained domain
  // (subset of totalPredictCount; init-hook path + any direct dispatch here).
  int totalOutOfDomainCount() const;

private:
  struct Impl;
  Impl* impl_ = nullptr;
};

} // namespace trech
