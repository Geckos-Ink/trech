#pragma once

#include <cstddef>
#include <limits>
#include <string>
#include <unordered_map>
#include <vector>

#include "trech/ml/ScaleCascade.hpp"  // DimensionScale (shared band ordering)

namespace trech::ml {

class GenericSurrogate;

// ---------------------------------------------------------------------------
// Per-element state evolution: the engine-side INFERENCE OPERATOR.
//
// `ScaleCascade` answers "given this context, what are the properties?" in one
// shot.  That leaves the scenario holding the other half of the physics: the
// per-element, per-step *operation* that turns those properties into motion --
// a reaction rate law, a relaxation law, a transfer law.  Today those laws are
// hand-written JavaScript loops inside scenarios (the reduced foaming kinetics
// in `polyurethane_foam.js`, the parcel chemistry in `elephants_toothpaste.js`,
// ...), which is exactly the "hardcoded physics the engine should have
// inferred" gap the multi-scale doctrine exists to close.
//
// StateEvolution is the general mechanism that lets that law be a *trained
// model the engine evaluates* instead.  The scenario declares:
//   * a set of NAMED state fields carried by N elements (parcels, cells,
//     voxels, molecules -- the engine does not care what they are),
//   * read-only per-element aux facts, and a run-constant shared context
//     (Geant4-derived facts + whatever a `ctx.cascade` already inferred),
//   * a bounded timestep dt,
// and the engine chains the declared scale-tagged surrogates over EVERY element
// in one deterministic pass, integrates the rates they predict, and writes the
// state back.
//
// The engine stays physics-agnostic: it knows only names and a naming
// convention for what an output DOES.  For a state field `f`, a stage output
// named:
//   * `d_f_dt`  -> a RATE: accumulated across stages, integrated once per call
//                  as f += (sum of rates) * dt (explicit Euler at the bounded
//                  step the caller already chose), then clamped to the field's
//                  declared bounds.
//   * `set_f`   -> an ASSIGNMENT: applied immediately, so a higher stage (and
//                  the caller) sees the assigned value.
//   * anything else -> an INTERMEDIATE: merged into the per-element context so
//                  higher-scale stages consume it, exactly like a cascade stage
//                  output, but never written back to the caller's state.
// Which fields exist, what they mean, and which bounds are physical are the
// SCENARIO's declarations -- no domain name enters C++.
//
// Rates accumulate rather than overwrite, so two stages may each contribute to
// the same field (a heat field fed by two competing reactions) without the
// scenario sequencing them.  Every rate is evaluated against the state at the
// start of the step, so the result does not depend on stage order beyond the
// declared scale ordering.
//
// Deterministic: a pure function of the loaded weights, the numeric state, and
// dt.  Non-owning: the caller keeps each GenericSurrogate alive (the JsRuntime
// owns them in its model registry).  Strict-mode gating and inference counting
// live at the JS boundary, like `ctx.predict`/`ctx.cascade`.
// ---------------------------------------------------------------------------

// One named per-element state field, with the bounds the scenario declares as
// physical for it (a conversion cannot exceed 1, a temperature cannot go
// negative).  Bounds are the caller's invariants, not engine physics; the
// default is unbounded.
struct EvolutionField {
  std::string name;
  double minValue = -std::numeric_limits<double>::infinity();
  double maxValue = std::numeric_limits<double>::infinity();
};

// A stage registered on the operator, in the same shape a cascade stage takes.
//
// `elementKindIndex` is what makes one call able to evolve SEVERAL materials at
// once: elements carry a kind (wax vs carrier, membrane vs cytosol, tissue A vs
// tissue B) and a stage runs only on the elements of its kind. A run is then no
// longer locked to one fixed operator for one fixed material; the same batched
// pass applies whichever trained operator each material's context selected, and
// elements whose kind selected nothing are simply left untouched (and reported).
struct EvolutionStage {
  std::string name;
  DimensionScale scale = DimensionScale::kUnscaled;
  const GenericSurrogate* model = nullptr;
  std::size_t elementKindIndex = kAnyElementKind;
};

// What one stage did, aggregated over the elements it ran on.  Per-element
// traces would be N times the run output for no added signal; the aggregate
// keeps the honest parts: how many elements fell outside the trained domain and
// how far the worst one was past the hull edge.
struct EvolutionStageTrace {
  std::string model;
  DimensionScale scale = DimensionScale::kUnscaled;
  bool ran = false;
  // The element kind this stage was bound to ("" = every element), and how many
  // elements it actually evaluated. With several materials in one call, these
  // two say which operator touched which population.
  std::string elementKind;
  std::size_t elementsMatched = 0;
  // Declared inputs absent from the whole context (shared + aux + fields + the
  // intermediates lower stages produce).  Defaulted to 0 by the surrogate and
  // surfaced here so missing signal is never hidden.
  std::vector<std::string> missingInputs;
  // Outputs by what they DID, so a reader can see the operator's effect without
  // decoding the naming convention.
  std::vector<std::string> integratedFields;   // `d_f_dt` -> f
  std::vector<std::string> assignedFields;     // `set_f`  -> f
  std::vector<std::string> intermediateOutputs;
  // Outputs that follow the `d_f_dt` / `set_f` pattern for a field the caller
  // never declared.  They still enter the context under their literal name (a
  // higher stage may legitimately consume them), but they update NO state --
  // reported rather than silently dropped, so a stale model run against a
  // changed scenario shows up here instead of as quietly frozen physics.
  std::vector<std::string> unappliedFieldOutputs;

  // Training-domain trust profile, aggregated over elements (same metric as
  // CascadeStageResult, evaluated per element).
  bool domainMeasured = false;
  std::size_t elementsOutOfDomain = 0;
  std::size_t elementsStarved = 0;
  double maxExtrapolation = 0.0;           // worst element, training-sigma units
  double maxStandardizedDeviation = 0.0;   // worst element
  std::vector<std::string> outOfDomainInputs;  // union over elements, sorted
  std::vector<std::string> starvedInputs;      // union over elements, sorted

  // Carried training provenance, identical in meaning to the cascade's.
  bool scaleMismatch = false;
  std::string trainedScale;
  bool hasHoldout = false;
  double holdoutR2 = 0.0;
  int holdoutSamples = 0;
};

// The caller's request.  `state` and `aux` are element-major dense blocks:
// state[e * fields.size() + f], aux[e * auxNames.size() + a].
struct EvolutionRequest {
  std::vector<EvolutionField> fields;
  std::vector<std::string> auxNames;
  std::size_t elementCount = 0;
  std::vector<double> state;
  std::vector<double> aux;
  std::unordered_map<std::string, double> shared;
  double dt = 0.0;
  // Optional per-element kind (material/species class): `elementKindNames` is
  // the declared vocabulary and `elementKindIndex[e]` indexes into it. Leave
  // both empty for a single-population call -- every stage then runs on every
  // element, exactly as before.
  std::vector<std::string> elementKindNames;
  std::vector<std::size_t> elementKindIndex;
};

struct EvolutionResult {
  bool ran = false;  // at least one stage ran on at least one element
  // The evolved state, same layout as the request's (unchanged when !ran).
  std::vector<double> state;
  std::size_t elementsEvolved = 0;
  int stagesRun = 0;
  int stagesExtrapolating = 0;    // stages with >=1 out-of-domain element
  int stagesScaleMismatched = 0;
  int stagesStarved = 0;
  // Model evaluations performed = stagesRun * elementCount.  This is the honest
  // inference count the run reports; a batched operator does not get to hide N
  // predictions behind one call.
  std::size_t inferenceCount = 0;
  std::size_t outOfDomainInferenceCount = 0;
  std::vector<EvolutionStageTrace> stages;  // executed (ascending-scale) order
};

// The operator.  Register stages (any order), then evolve.
class StateEvolution {
 public:
  void addStage(std::string name, DimensionScale scale,
                const GenericSurrogate* model,
                std::size_t elementKindIndex = kAnyElementKind);

  bool empty() const { return stages_.empty(); }
  std::size_t size() const { return stages_.size(); }

  // Evolve every element by one bounded step.  Stages run in ascending scale
  // order (registration order breaks ties), each predicting from the current
  // per-element context; rates accumulate and integrate once at the end.
  // Returns the request's state untouched when nothing could run.
  EvolutionResult evolve(const EvolutionRequest& request) const;

  // The naming convention, exposed so callers/tests agree with the engine:
  // rateOutputName("gel") == "d_gel_dt", assignOutputName("gel") == "set_gel".
  static std::string rateOutputName(const std::string& field);
  static std::string assignOutputName(const std::string& field);

 private:
  std::vector<EvolutionStage> stages_;
};

}  // namespace trech::ml
