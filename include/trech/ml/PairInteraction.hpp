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
// Pair / neighbour inference: the engine-side INTERACTION operator.
//
// `StateEvolution` (`ctx.evolve`) answers "given THIS element's state, how does
// it change over dt?".  That covers a per-element rate law, but it cannot
// express the other large family of hand-written scenario physics: what one
// element does TO ANOTHER.  Every remaining authored solver in the tree is of
// that shape -- the LJ + Coulomb force loop in `trech_water_md.js`, the bonded
// growth/creep/failure network in `trech_foam_solver.js`, the PBF density and
// viscosity/cohesion neighbourhood sums in `glass_of_water_shaken.js`, the
// parcel cohesion/collision terms in `lava_lamp.js`.
//
// PairInteraction is the physics-agnostic mechanism that lets such a law be a
// *trained model the engine evaluates over pairs* instead.  The scenario
// declares:
//   * N elements with positions and named state fields that RECEIVE pair
//     contributions (velocity, heat, density, damage, ...),
//   * read-only per-element aux facts and a run-constant shared context,
//   * a neighbour cutoff and/or an explicit persistent pair list (bonds, which
//     are evaluated whether or not they are within the cutoff, because a
//     stretched bond is exactly the interesting case),
//   * optional per-pair state fields carried BY the pair (a bond's rest length,
//     its accumulated damage),
//   * a bounded dt,
// and the engine builds a deterministic neighbour list, evaluates the declared
// scale-tagged surrogates over every canonical `(a,b)` pair (a < b), and
// accumulates their outputs back onto the two members.
//
// What the engine owns (numerics and invariants, never material physics):
//   * the cell list and the canonical, implementation-independent pair order
//     (pairs are enumerated, then sorted by `(a,b)`, so the floating-point
//     accumulation order cannot change with a hash-map layout or a cell size),
//   * equal-and-opposite application, so an antisymmetric field's pair
//     contribution cancels EXACTLY (`a += v`, `b -= v` with the same double),
//   * the caller's declared bounds, the single integration of accumulated rates
//     over dt, and honest accounting: `pairs x stages` inferences, with the
//     same per-stage training-domain trust profile every other inference path
//     reports.
//
// Naming convention (the whole domain interface -- no domain name enters C++).
// For an element field `f` and a pair field `p`, a stage output named:
//   * `d_f_dt`  -> a RATE contribution to both members, integrated once over dt
//                  as `f += (sum of contributions) * dt` and then clamped.
//   * `add_f`   -> a DIRECT increment contribution to both members (no dt): the
//                  neighbourhood-sum form (a density/coordination/overlap sum,
//                  where the caller pre-loads the field with its self term).
//   * `d_p_dt`  -> a rate on the PAIR's own state, integrated over dt.
//   * `set_p`   -> an assignment on the pair's own state, visible to
//                  higher-scale stages within the same call.
//   * anything else -> an INTERMEDIATE merged into the per-pair context for
//                  higher-scale stages, exactly like a cascade stage output.
// Each member's own facts are read with the reserved `a_`/`b_` prefixes
// (`a_temperature_k`, `b_mass`), and the pair geometry through the reserved
// inputs `r`, `dx`/`dy`/`dz` and `ux`/`uy`/`uz` (b - a, and its unit vector)
// plus the reserved `dt`.
//
// Whether a field's contribution is equal-and-opposite (a force, a heat
// exchange: what a gains, b loses) or shared (a density sum: both gain) is the
// CALLER's declared invariant, exactly like the bounds -- the engine enforces
// it, it does not decide it.
//
// Deterministic: a pure function of the loaded weights, the numeric state,
// positions and dt.  Non-owning: the caller keeps each GenericSurrogate alive.
// Strict-mode gating and inference counting live at the JS boundary, like
// `ctx.predict` / `ctx.cascade` / `ctx.evolve` / `ctx.react`.
// ---------------------------------------------------------------------------

// How a pair's contribution to an element field is applied to the two members.
enum class PairSymmetry {
  // `a += v`, `b -= v`.  Exactly equal and opposite, so the pair conserves the
  // field's total in the strictest floating-point sense (the same double is
  // added and subtracted).  Forces/impulses, heat and mass exchange.
  kAntisymmetric,
  // `a += v`, `b += v`.  A shared neighbourhood contribution: density,
  // coordination count, overlap, pair energy attributed to both members.
  kSymmetric
};

// One named per-element field that RECEIVES pair contributions, with the
// symmetry and bounds the caller declares as physical for it.
struct PairElementField {
  std::string name;
  PairSymmetry symmetry = PairSymmetry::kAntisymmetric;
  double minValue = -std::numeric_limits<double>::infinity();
  double maxValue = std::numeric_limits<double>::infinity();
};

// One named state field carried by a persistent pair (a bond's rest length, its
// accumulated damage).  Only meaningful for declared links, which are the pairs
// that persist across calls.
struct PairStateField {
  std::string name;
  double minValue = -std::numeric_limits<double>::infinity();
  double maxValue = std::numeric_limits<double>::infinity();
};

// A declared persistent pair (a bond).  Always evaluated, cutoff or not.
struct PairLink {
  std::size_t a = 0;
  std::size_t b = 0;
};

struct PairStage {
  std::string name;
  DimensionScale scale = DimensionScale::kUnscaled;
  const GenericSurrogate* model = nullptr;
  // Which PAIR kind this stage serves (kAnyElementKind = every pair). A pair
  // kind is the canonical unordered combination of the two members' material
  // kinds -- `sand|sand`, `sand|melt`, `melt|melt` -- because what happens
  // between two grains of the same solid, a grain and its melt, and two melt
  // cells are three different interactions, and a run that creates a new
  // material has to switch between them as its cells transform.
  std::size_t pairKindIndex = kAnyElementKind;
};

// What one stage did, aggregated over the pairs it ran on (per-pair traces
// would be P times the run output for no added signal).
struct PairStageTrace {
  std::string model;
  DimensionScale scale = DimensionScale::kUnscaled;
  bool ran = false;
  std::string pairKind;          // "" = every pair
  std::size_t pairsMatched = 0;  // pairs this stage actually evaluated
  // Declared inputs absent from the whole per-pair context (pair state, member
  // fields/aux, geometry, dt, shared, lower-stage intermediates).  Defaulted to
  // 0 by the surrogate and surfaced here so missing signal is never hidden.
  std::vector<std::string> missingInputs;
  // Outputs by what they DID.
  std::vector<std::string> ratedElementFields;      // `d_f_dt`  -> members
  std::vector<std::string> incrementedElementFields;  // `add_f`  -> members
  std::vector<std::string> ratedPairFields;         // `d_p_dt`  -> pair state
  std::vector<std::string> assignedPairFields;      // `set_p`   -> pair state
  std::vector<std::string> intermediateOutputs;
  // Outputs that follow a field-directed pattern for a field the caller never
  // declared (including `set_<element field>`, which a many-to-one pair sum
  // cannot apply meaningfully).  They still enter the per-pair context under
  // their literal name, but they update NO state -- reported rather than
  // silently dropped.
  std::vector<std::string> unappliedFieldOutputs;

  // Training-domain trust profile, aggregated over pairs (same metric as
  // CascadeStageResult / EvolutionStageTrace, evaluated per pair).
  bool domainMeasured = false;
  std::size_t pairsOutOfDomain = 0;
  std::size_t pairsStarved = 0;
  double maxExtrapolation = 0.0;
  double maxStandardizedDeviation = 0.0;
  std::vector<std::string> outOfDomainInputs;  // union over pairs, sorted
  std::vector<std::string> starvedInputs;      // union over pairs, sorted

  // Carried training provenance, identical in meaning to the cascade's.
  bool scaleMismatch = false;
  std::string trainedScale;
  bool hasHoldout = false;
  double holdoutR2 = 0.0;
  int holdoutSamples = 0;
};

// The caller's request.  `state`/`aux` are element-major dense blocks
// (state[e * fields.size() + f]); `positions` is 3 doubles per element;
// `pairState` is link-major (pairState[l * pairFields.size() + p]).
struct PairInteractionRequest {
  std::size_t elementCount = 0;
  std::vector<PairElementField> fields;
  std::vector<std::string> auxNames;
  std::vector<double> state;
  std::vector<double> aux;
  std::vector<double> positions;  // 3 * elementCount; empty -> no neighbours

  // Dynamic neighbours: every pair closer than `cutoff` (<= 0 disables the
  // search).  `maxNeighborPairs` bounds the search so a collapsed/dense
  // configuration degrades visibly (reported `neighborPairsSkipped`) instead of
  // silently costing quadratic time; 0 means unbounded.
  double cutoff = 0.0;
  std::size_t maxNeighborPairs = 0;

  // Persistent topology: always evaluated, and the only pairs that carry state.
  std::vector<PairLink> links;
  std::vector<PairStateField> pairFields;
  std::vector<double> pairState;

  std::unordered_map<std::string, double> shared;
  double dt = 0.0;

  // Optional material kinds. `elementKindNames`/`elementKindIndex` give each
  // element its material class; `pairKindNames` is the caller's declared
  // vocabulary of canonical pair kinds (see PairInteraction::pairKindName), and
  // a stage's `pairKindIndex` points into it. Leave empty for a single-material
  // call -- every stage then evaluates every pair, exactly as before.
  std::vector<std::string> elementKindNames;
  std::vector<std::size_t> elementKindIndex;
  std::vector<std::string> pairKindNames;
};

struct PairInteractionResult {
  bool ran = false;
  // Element state after the accumulated contributions were applied, and the
  // evolved per-link state.  Both unchanged when !ran.
  std::vector<double> state;
  std::vector<double> pairState;

  std::size_t pairCount = 0;          // pairs actually evaluated
  std::size_t linkPairCount = 0;      // declared persistent pairs among them
  std::size_t neighborPairCount = 0;  // cutoff pairs among them
  std::size_t neighborPairsSkipped = 0;  // dropped by maxNeighborPairs
  bool neighborPairsTruncated = false;
  // Declared links the engine refused: a self-pair or an out-of-range index
  // (`invalidLinks`), or the same pair declared twice (`duplicateLinks`, kept
  // once).  Reported rather than silently dropped, so a broken topology shows
  // up here instead of as quietly missing physics.
  std::size_t invalidLinks = 0;
  std::size_t duplicateLinks = 0;

  int stagesRun = 0;
  int stagesExtrapolating = 0;
  int stagesScaleMismatched = 0;
  int stagesStarved = 0;
  // Model evaluations performed = stagesRun * pairCount.  The honest inference
  // count the run reports: a batched pair operator does not hide P predictions
  // behind one call.
  std::size_t inferenceCount = 0;
  std::size_t outOfDomainInferenceCount = 0;
  std::vector<PairStageTrace> stages;  // executed (ascending-scale) order
};

// The operator.  Register stages (any order), then interact.
class PairInteraction {
 public:
  void addStage(std::string name, DimensionScale scale,
                const GenericSurrogate* model,
                std::size_t pairKindIndex = kAnyElementKind);

  bool empty() const { return stages_.empty(); }
  std::size_t size() const { return stages_.size(); }

  // Evaluate every canonical pair once and apply the accumulated contributions.
  // Returns the request's state untouched when nothing could run.
  PairInteractionResult interact(const PairInteractionRequest& request) const;

  // The naming convention, exposed so callers/tests/trainers agree with the
  // engine.
  static std::string rateOutputName(const std::string& field);       // d_f_dt
  static std::string incrementOutputName(const std::string& field);  // add_f
  static std::string assignOutputName(const std::string& field);     // set_f
  // Member-qualified input name: memberInputName(0, "mass") == "a_mass".
  static std::string memberInputName(int member, const std::string& name);
  // Canonical (unordered) pair-kind name: pairKindName("melt", "sand") ==
  // pairKindName("sand", "melt") == "melt|sand". Exposed so scenarios, trainers
  // and tests compose the same string the engine looks up.
  static std::string pairKindName(const std::string& a, const std::string& b);

 private:
  std::vector<PairStage> stages_;
};

}  // namespace trech::ml
