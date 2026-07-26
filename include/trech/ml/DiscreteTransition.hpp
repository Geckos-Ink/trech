#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

#include "trech/ml/ScaleCascade.hpp"

namespace trech::ml {

class GenericSurrogate;

// One integer-state transition. Delta is aligned with
// DiscreteTransitionRequest::speciesNames. The engine applies it atomically:
// either every resulting count is non-negative or no count changes.
struct TransitionChannel {
  std::string name;
  std::vector<std::int64_t> delta;
};

// A caller-declared conserved quantity (atoms, charge, packet identity, ...).
// Coefficients are aligned with speciesNames. A channel is eligible only when
// dot(coefficients, channel.delta) == 0 for every declared invariant.
struct TransitionConservation {
  std::string name;
  std::vector<std::int64_t> coefficients;
};

struct TransitionStage {
  std::string name;
  DimensionScale scale = DimensionScale::kUnscaled;
  const GenericSurrogate* model = nullptr;
};

struct TransitionStageTrace {
  std::string model;
  DimensionScale scale = DimensionScale::kUnscaled;
  bool ran = false;
  std::vector<std::string> missingInputs;
  std::vector<std::string> intermediateOutputs;
  std::vector<std::string> hazardOutputs;
  std::vector<std::string> unappliedHazardOutputs;

  bool domainMeasured = false;
  std::size_t elementsOutOfDomain = 0;
  std::size_t elementsStarved = 0;
  double maxExtrapolation = 0.0;
  double maxStandardizedDeviation = 0.0;
  std::vector<std::string> outOfDomainInputs;
  std::vector<std::string> starvedInputs;
  bool scaleMismatch = false;
  std::string trainedScale;
  bool hasHoldout = false;
  double holdoutR2 = 0.0;
  int holdoutSamples = 0;
};

struct TransitionChannelTrace {
  std::string name;
  bool valid = true;
  bool nonZero = true;
  std::vector<std::string> violatedConservation;
  std::size_t attempted = 0;
  std::size_t accepted = 0;
  std::size_t rejectedAvailability = 0;
};

// State and aux are element-major dense blocks, matching StateEvolution:
// state[e * speciesNames.size() + s], aux[e * auxNames.size() + a].
struct DiscreteTransitionRequest {
  std::vector<std::string> speciesNames;
  std::vector<std::string> auxNames;
  std::size_t elementCount = 0;
  std::vector<std::int64_t> state;
  std::vector<double> aux;
  std::unordered_map<std::string, double> shared;
  double dt = 0.0;
  std::vector<TransitionChannel> channels;
  std::vector<TransitionConservation> conservation;
  std::uint64_t seed = 0;
};

struct DiscreteTransitionResult {
  bool ran = false;
  bool transitionSchemaValid = true;
  bool hazardSchemaValid = true;
  std::string hazardMode;  // "direct" | "weighted" | ""
  std::vector<std::int64_t> state;
  std::size_t elementsEvaluated = 0;
  int stagesRun = 0;
  int stagesExtrapolating = 0;
  int stagesScaleMismatched = 0;
  int stagesStarved = 0;
  std::size_t inferenceCount = 0;
  std::size_t outOfDomainInferenceCount = 0;
  std::size_t drawCount = 0;
  std::size_t transitionAttempts = 0;
  std::size_t transitionsAccepted = 0;
  std::size_t rejectedAvailability = 0;
  std::size_t hazardsClamped = 0;
  std::size_t weightsClamped = 0;
  std::size_t hazardRenormalizedElements = 0;
  std::vector<TransitionStageTrace> stages;
  std::vector<TransitionChannelTrace> channelTrace;
};

// Physics-agnostic learned discrete transition operator.
//
// Models may expose exactly one of two output conventions:
//   hazard_<channel>               direct competing per-channel hazards
//   hazard + weight_<channel>      one event hazard + relative channel weights
//
// Hazards and weights are clamped to [0,1]. Direct hazards whose sum exceeds 1
// are renormalized deterministically. One transition may occur per element per
// call. The model never edits counts directly: the engine owns seeded draws,
// non-negative availability, atomic application, and declared conservation.
class DiscreteTransition {
 public:
  void addStage(std::string name, DimensionScale scale,
                const GenericSurrogate* model);

  DiscreteTransitionResult react(
      const DiscreteTransitionRequest& request) const;

  static std::string channelHazardOutputName(const std::string& channel);
  static std::string channelWeightOutputName(const std::string& channel);

 private:
  std::vector<TransitionStage> stages_;
};

}  // namespace trech::ml
