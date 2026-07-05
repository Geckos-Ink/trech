#pragma once

#include <string>
#include <unordered_map>
#include <vector>

namespace trech::ml {

class GenericSurrogate;

// Ordered dimension-scale bands, smallest characteristic length first.  These
// mirror the bands the Python harvester (tools/torch/trech_torch/dataset.py)
// tags runs with, so a model trained/valid at one scale is only ever chained in
// the right order.  `kUnscaled` sorts LAST (after macro): a model with no
// declared scale runs at the top of the cascade, where it can consume every
// lower-scale prediction.
enum class DimensionScale {
  kAtomic = 0,  // < 1 nm       (molecular MD, bonds)
  kNano,        // 1 nm - 1 um  (CNT channels, devices)
  kMicro,       // 1 um - 1 mm  (cells, membranes)
  kMeso,        // 1 mm - 1 m   (lab bench: cups, slabs, droplets)
  kMacro,       // > 1 m        (bulk / observer)
  kUnscaled     // no declared band -> runs last
};

// Parse a band name ("atomic"/"nano"/"micro"/"meso"/"macro"); anything else
// (incl. empty) maps to kUnscaled.
DimensionScale parseDimensionScale(const std::string& name);

// Canonical lower-case band name; kUnscaled -> "unscaled".
const char* dimensionScaleName(DimensionScale scale);

// One executed stage of a cascade run, retained for provenance / debugging.
struct CascadeStageResult {
  std::string model;
  DimensionScale scale = DimensionScale::kUnscaled;
  bool ran = false;  // model was loaded and produced outputs
  // Declared inputs that were absent from the context at run time (defaulted to
  // 0 by the surrogate) -- surfaced so a cascade never hides missing signal.
  std::vector<std::string> missingInputs;
  // Names of the outputs the stage merged into the context.
  std::vector<std::string> outputs;
};

struct CascadeResult {
  // The full context after propagation: seed facts + every stage's outputs.
  // Later stages override earlier keys.
  std::unordered_map<std::string, double> context;
  std::vector<CascadeStageResult> stages;  // in executed (ascending-scale) order
  int stagesRun = 0;                        // count of stages that actually ran
};

// Multi-scale statistical-inference cascade: chains scenario-declared,
// scale-tagged surrogates from the Geant4/particle base up to the observer
// scale.  Each stage reads named facts already in the context (Geant4-derived
// seeds + lower-scale predictions) and writes its named outputs back, so the
// next-higher scale can consume them WITHOUT the scenario hand-wiring each
// prediction.  This is the general-purpose realization of the engine's
// multi-scale doctrine (see AGENTS.md "Multi-scale statistical inference").
//
// Deterministic: a pure function of the loaded weights + the numeric seed.
// Non-owning: the caller keeps each GenericSurrogate alive for the cascade's
// lifetime (the JsRuntime owns them in its model registry).
class ScaleCascade {
 public:
  // Register a model at a scale band.  `model` may be null or unloaded; such a
  // stage is recorded but simply does not run (graceful degradation).
  void addStage(std::string name, DimensionScale scale,
                const GenericSurrogate* model);

  bool empty() const { return stages_.empty(); }
  std::size_t size() const { return stages_.size(); }

  // Run the cascade: copy `seed` into the context, then evaluate every stage in
  // ascending scale order (stable within a band, i.e. registration order is the
  // tie-breaker).  A loaded stage predicts from the current context (missing
  // inputs default to 0 and are recorded), and its outputs merge into the
  // context for the next-higher stage.
  CascadeResult run(const std::unordered_map<std::string, double>& seed) const;

 private:
  struct Stage {
    std::string name;
    DimensionScale scale = DimensionScale::kUnscaled;
    const GenericSurrogate* model = nullptr;
    std::size_t order = 0;  // registration order, the stable tie-breaker
  };
  std::vector<Stage> stages_;
};

}  // namespace trech::ml
