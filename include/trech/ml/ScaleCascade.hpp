#pragma once

#include <cstddef>

#include <string>
#include <unordered_map>
#include <vector>

namespace trech::ml {

// Sentinel for an operator stage that applies to EVERY element/pair, whatever
// its material kind. Shared by the batched operators (StateEvolution,
// DiscreteTransition, PairInteraction) so one scenario can mix a material-
// specific law with a law every material obeys.
constexpr std::size_t kAnyElementKind = static_cast<std::size_t>(-1);

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

// One model output's MEASURED held-out accuracy, carried out of every learned
// inference path (cascade stages and the batched operators) so a consumer can
// report the uncertainty of the quantity IT read rather than the model's worst
// output.  `rootMeanSquaredError` is a measured 1-sigma residual in that
// quantity's own units -- the honest replacement for a scenario hand-typing a
// sigma next to an inferred value.
//
// Every metric is independently optional: a model trained before a metric
// existed carries only the ones it measured, and a hand-authored illustrative
// map carries none (it is then simply absent from the reported list).  Absent
// must never be rendered as 0, which would read as a perfect model.
struct NamedOutputAccuracy {
  std::string name;
  bool hasR2 = false;
  double r2 = 0.0;
  bool hasMeanAbsoluteError = false;
  double meanAbsoluteError = 0.0;
  bool hasRootMeanSquaredError = false;
  double rootMeanSquaredError = 0.0;
};

// Collect a model's per-output held-out metrics, sorted by output name so the
// record is deterministic; empty when the model carries none.
std::vector<NamedOutputAccuracy> collectOutputAccuracy(
    const GenericSurrogate& model);

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

  // Training-domain coverage of the inputs this stage predicted on (workstream
  // 3): whether the point fell inside the region the stage's model was trained
  // on.  A stage that runs out-of-domain is EXTRAPOLATING -- its prediction (and
  // everything it feeds up the ladder) is low-confidence, and that is flagged
  // here instead of silently guessing.  `extrapolation` is how far past the
  // trained hull edge the worst input sat, in standardized (training-sigma)
  // units (0 when fully in-domain); `domainMeasured` is false when the model
  // carried no measured hull and a heuristic radius was used.
  bool inDomain = true;
  bool domainMeasured = false;
  double extrapolation = 0.0;
  double maxStandardizedDeviation = 0.0;
  std::vector<std::string> outOfDomainInputs;
  // Inputs within the trained range but in an unpopulated training bin (a hole
  // the model interpolated -- density inside the hull, not just its edge).
  std::vector<std::string> starvedInputs;
  // JOINT starvation: in range on every axis, yet far from any training point
  // (the multivariate check the per-feature ones structurally cannot make).
  // `jointMeasured` false -> the model carries no joint reference and the check
  // was NOT performed: read the other two fields as unknown, not as a pass.
  bool jointMeasured = false;
  bool jointStarved = false;
  double jointDistance = 0.0;  // standardized distance to the nearest trained region
  double jointRadius = 0.0;    // the distance that covers the training set

  // Training provenance / quality carried with the stage's model (workstream 3
  // items b + c). `scaleMismatch` is true when the stage runs at a scale NOT
  // among the dimension-scale band(s) its model was trained on (the harvester
  // tags each training run's band) -- i.e. the model is applied off the band it
  // learned. `trainedScale` is those band(s) joined (empty = unknown, do not
  // judge). `hasHoldout`/`holdoutR2`/`holdoutSamples` carry the model's held-out
  // accuracy so grade-the-gap travels with it; `hasHoldout` is false for
  // illustrative hand-authored maps that carry no metrics (then holdoutR2 is
  // meaningless and must be treated as absent, never 0 == perfect).
  bool scaleMismatch = false;
  std::string trainedScale;
  bool hasHoldout = false;
  double holdoutR2 = 0.0;
  int holdoutSamples = 0;

  // Per-OUTPUT held-out accuracy for the quantities this stage merged into the
  // context (empty when the model carries none).
  std::vector<NamedOutputAccuracy> outputAccuracy;
};

struct CascadeResult {
  // The full context after propagation: seed facts + every stage's outputs.
  // Later stages override earlier keys.
  std::unordered_map<std::string, double> context;
  std::vector<CascadeStageResult> stages;  // in executed (ascending-scale) order
  int stagesRun = 0;                        // count of stages that actually ran
  int stagesExtrapolating = 0;  // ran stages whose inputs were out-of-domain
  int stagesScaleMismatched = 0;  // ran stages applied off their trained band
  int stagesStarved = 0;  // ran stages with an input in an unpopulated training bin
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
