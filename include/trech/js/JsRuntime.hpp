#pragma once

#include "trech/core/Config.hpp"

#include <array>
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
  // Geant4 run ID of the dispatching run (G4Run::GetRunID); -1 => exposed as
  // ctx.runtime.runId = null (e.g. onInit or a host test without a run).
  int runId = -1;
  // Optional Geant4 step detail for onStep. When hasStepDetail is true the
  // runtime adds track identity, pre/post step points, global time and kinetic
  // energies to ctx.step. None of these fields enter the hook RNG seed, so
  // ctx.rng replay is identical with or without them.
  bool hasStepDetail = false;
  int trackId = -1;
  int parentTrackId = -1;
  std::string particleName;
  std::string volumeName;     // pre-step physical volume ("" => null)
  std::string processName;    // post-step defining process ("" => null)
  std::array<double, 3> prePositionMm{0.0, 0.0, 0.0};
  std::array<double, 3> postPositionMm{0.0, 0.0, 0.0};
  double preGlobalTimeNs = 0.0;
  double postGlobalTimeNs = 0.0;
  double preKineticEnergyMeV = 0.0;
  double postKineticEnergyMeV = 0.0;
  // Optional Geant4 track detail for onTrackStart/onTrackEnd (ctx.track).
  // Reuses trackId/parentTrackId/particleName/volumeName/processName above
  // (volume: where the track starts or ends; process: the creator process at
  // start, "" for a primary, or the last step's defining process at end).
  // trackId enters the hook RNG seed only for these dispatches, so every
  // track gets its own ctx.rng stream and the other hooks' seeds are unchanged.
  bool hasTrackDetail = false;
  std::array<double, 3> trackPositionMm{0.0, 0.0, 0.0};
  double trackGlobalTimeNs = 0.0;
  double trackKineticEnergyMeV = 0.0;
  double trackLengthMm = 0.0;
  int trackStepCount = 0;
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
  // Leaf paths of the returned `override` that no patchable field applied: an
  // unknown or non-patchable key, or a value of the wrong type ("run.nEvent").
  std::vector<std::string> ignoredPatchPaths;
  std::size_t emitCount = 0;
  std::size_t emitDroppedCount = 0;
  std::size_t predictCount = 0;
  // Subset of predictCount whose inputs fell outside the model's trained domain
  // (a cascade contributes its stagesExtrapolating; ctx.predict contributes 1;
  // ctx.evolve/ctx.react contribute each out-of-domain element-stage) -- the
  // auditable low-confidence run fact (workstream 3a).
  std::size_t outOfDomainCount = 0;
  // Independent subsets of predictCount: per-feature or joint starvation
  // counts an evaluation once, and declared-vs-trained scale mismatch follows
  // the same effective ancestry as cascade traces. Neither implies hull OOD.
  std::size_t starvedCount = 0;
  std::size_t scaleMismatchCount = 0;
};

// One file an evaluation read, with the SHA-256 of the bytes it read at that moment.
struct JsSourceDigest {
  std::string path;     // absolute, lexically normal
  std::string sha256;
  bool data = false;    // a TRECH_READ_JSON data file rather than a script source
};

// The JavaScript engine a JsRuntime evaluates scenarios and hooks with. Both run the same host
// (TRECH_INCLUDE, TRECH_VALUE, the hook ctx and every inference API) from one source file and
// the same deterministic Math (trech_dmath). QuickJS is always built; V8 only with
// TRECH_ENABLE_V8 (docs/engine/v8.md).
enum class JsEngine { QuickJs, V8 };

// "quickjs" / "v8"; parseJsEngine accepts the same names and throws std::invalid_argument.
const char* jsEngineName(JsEngine engine);
JsEngine parseJsEngine(const std::string& name);

class JsRuntime {
public:
  // Uses JsRuntime::defaultEngine().
  JsRuntime();
  explicit JsRuntime(JsEngine engine);
  ~JsRuntime();

  // True when this binary was built with the engine (QuickJS always; V8 with TRECH_ENABLE_V8).
  static bool engineAvailable(JsEngine engine);
  // The engine a default-constructed JsRuntime uses: the last setDefaultEngine() call, else
  // the TRECH_JS_ENGINE environment variable ("quickjs" or "v8"), else the build default
  // (TRECH_DEFAULT_JS_ENGINE, QuickJS unless configured otherwise). Throws
  // std::runtime_error when the selected engine is not built into this binary.
  static JsEngine defaultEngine();
  // Process-wide choice, e.g. from `trech --js-engine`. Every later default-constructed
  // runtime (the CLI, the live lab's re-evaluations) uses it.
  static void setDefaultEngine(JsEngine engine);

  JsEngine engine() const;
  // "quickjs 2025-09-13" or "v8 15.9.128.11": engine and version, for provenance.
  std::string engineIdentity() const;
  JsRuntime(const JsRuntime&) = delete;
  JsRuntime& operator=(const JsRuntime&) = delete;

  std::string evalExperimentAndGetConfigJson(const std::string& path);
  // Set repeatable `name=<json>` overrides before evaluating an experiment.
  // TRECH_VALUE validates each selected value against its declaration.
  void setScriptParameterOverrides(const std::vector<std::string>& overrides);
  void setPrecisionRefinement(double factor);
  // Canonical array of typed TRECH_VALUE declarations encountered during the
  // last evaluation, including resolved values and override provenance.
  std::string scriptParametersJson() const;
  // Inspection-only source inventory, optional TRECH_STUDIO UI and bundle validation metadata.
  // Kept outside the simulation config so UI edits do not change physics hashes.
  std::string authoringMetadataJson() const;
  // Absolute paths of every JavaScript source the last evaluation read (the entry file and
  // its TRECH_INCLUDE companions), in load order. The live lab hashes them for provenance.
  std::vector<std::string> sourceFiles() const;
  // The script sources (load order), then the TRECH_READ_JSON data files (read order), each
  // with the digest of the bytes the evaluation actually read. A file edited after it was read
  // keeps the digest of the version that ran.
  std::vector<JsSourceDigest> sourceDigests() const;
  // Exchange the whole engine state (engine context, hooks, models, pending emits) with
  // `other`. The live lab keeps one JsRuntime address, which the Geant4 actions hold, and
  // swaps a freshly evaluated runtime into it between batches. Never call while either
  // runtime is evaluating or dispatching.
  void swap(JsRuntime& other) noexcept;
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
  // Detached, name-sorted metadata for every scenario-declared model, including
  // failed loads and non-operator models. Hashes describe the loader snapshot.
  // Empty string when no models were declared; no inference, RNG or file IO.
  std::string modelArtifactsJson() const;
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
