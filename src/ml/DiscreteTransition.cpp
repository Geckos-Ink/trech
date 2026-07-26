#include "trech/ml/DiscreteTransition.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <set>
#include <unordered_map>

#include "trech/ml/GenericSurrogate.hpp"

namespace trech::ml {
namespace {

struct InputSource {
  bool constant = true;
  std::size_t slot = 0;
  double value = 0.0;
};

struct OutputTarget {
  std::size_t slot = 0;
};

struct PlannedStage {
  const TransitionStage* stage = nullptr;
  std::vector<InputSource> inputs;
  std::vector<OutputTarget> outputs;
};

constexpr const char* kStepInputName = "dt";
constexpr const char* kGlobalHazardOutput = "hazard";

std::uint64_t nextRandom(std::uint64_t* state) {
  // xorshift64* with a fixed non-zero escape for a caller seed of zero.
  if (*state == 0) {
    *state = 0x9e3779b97f4a7c15ull;
  }
  std::uint64_t x = *state;
  x ^= x >> 12;
  x ^= x << 25;
  x ^= x >> 27;
  *state = x;
  return x * 2685821657736338717ull;
}

double uniform01(std::uint64_t* state) {
  const std::uint64_t bits = nextRandom(state) >> 11;
  return static_cast<double>(bits) / 9007199254740992.0;  // 2^53
}

double boundedUnit(double value, std::size_t* clampCount) {
  if (!std::isfinite(value)) {
    ++(*clampCount);
    return 0.0;
  }
  if (value < 0.0) {
    ++(*clampCount);
    return 0.0;
  }
  if (value > 1.0) {
    ++(*clampCount);
    return 1.0;
  }
  return value;
}

bool startsWith(const std::string& value, const char* prefix) {
  return value.rfind(prefix, 0) == 0;
}

bool checkedMultiply(std::int64_t a, std::int64_t b, std::int64_t* out) {
  if (a == 0 || b == 0) {
    *out = 0;
    return true;
  }
  constexpr std::int64_t kMin = std::numeric_limits<std::int64_t>::min();
  constexpr std::int64_t kMax = std::numeric_limits<std::int64_t>::max();
  if ((a == -1 && b == kMin) || (b == -1 && a == kMin)) {
    return false;
  }
  if (a > 0) {
    if ((b > 0 && a > kMax / b) || (b < 0 && b < kMin / a)) {
      return false;
    }
  } else {
    if ((b > 0 && a < kMin / b) || (b < 0 && a < kMax / b)) {
      return false;
    }
  }
  *out = a * b;
  return true;
}

bool checkedAdd(std::int64_t a, std::int64_t b, std::int64_t* out) {
  constexpr std::int64_t kMin = std::numeric_limits<std::int64_t>::min();
  constexpr std::int64_t kMax = std::numeric_limits<std::int64_t>::max();
  if ((b > 0 && a > kMax - b) || (b < 0 && a < kMin - b)) {
    return false;
  }
  *out = a + b;
  return true;
}

}  // namespace

std::string DiscreteTransition::channelHazardOutputName(
    const std::string& channel) {
  return "hazard_" + channel;
}

std::string DiscreteTransition::channelWeightOutputName(
    const std::string& channel) {
  return "weight_" + channel;
}

void DiscreteTransition::addStage(std::string name, DimensionScale scale,
                                  const GenericSurrogate* model) {
  TransitionStage stage;
  stage.name = std::move(name);
  stage.scale = scale;
  stage.model = model;
  stages_.push_back(std::move(stage));
}

DiscreteTransitionResult DiscreteTransition::react(
    const DiscreteTransitionRequest& request) const {
  DiscreteTransitionResult result;
  result.state = request.state;

  const std::size_t speciesCount = request.speciesNames.size();
  const std::size_t auxCount = request.auxNames.size();
  const std::size_t elementCount = request.elementCount;
  result.channelTrace.resize(request.channels.size());
  for (std::size_t c = 0; c < request.channels.size(); ++c) {
    result.channelTrace[c].name = request.channels[c].name;
  }

  // ---- validate the declarative integer transition topology ---------------
  if (speciesCount == 0 || elementCount == 0 ||
      request.state.size() != speciesCount * elementCount ||
      request.aux.size() != auxCount * elementCount ||
      request.channels.empty()) {
    result.transitionSchemaValid = false;
    return result;
  }
  std::set<std::string> speciesSeen;
  for (const std::string& name : request.speciesNames) {
    if (name.empty() || !speciesSeen.insert(name).second) {
      result.transitionSchemaValid = false;
    }
  }
  std::set<std::string> channelSeen;
  for (std::size_t c = 0; c < request.channels.size(); ++c) {
    const TransitionChannel& channel = request.channels[c];
    TransitionChannelTrace& trace = result.channelTrace[c];
    if (channel.name.empty() || !channelSeen.insert(channel.name).second ||
        channel.delta.size() != speciesCount) {
      trace.valid = false;
      result.transitionSchemaValid = false;
      continue;
    }
    trace.nonZero = std::any_of(
        channel.delta.begin(), channel.delta.end(),
        [](std::int64_t delta) { return delta != 0; });
    if (!trace.nonZero) {
      trace.valid = false;
      result.transitionSchemaValid = false;
    }
  }
  std::set<std::string> conservationSeen;
  for (const TransitionConservation& invariant : request.conservation) {
    if (invariant.name.empty() ||
        !conservationSeen.insert(invariant.name).second ||
        invariant.coefficients.size() != speciesCount) {
      result.transitionSchemaValid = false;
      continue;
    }
    for (std::size_t c = 0; c < request.channels.size(); ++c) {
      if (request.channels[c].delta.size() != speciesCount) {
        continue;
      }
      std::int64_t balance = 0;
      bool exact = true;
      for (std::size_t s = 0; s < speciesCount; ++s) {
        std::int64_t term = 0;
        std::int64_t next = 0;
        if (!checkedMultiply(invariant.coefficients[s],
                             request.channels[c].delta[s], &term) ||
            !checkedAdd(balance, term, &next)) {
          exact = false;
          break;
        }
        balance = next;
      }
      if (!exact || balance != 0) {
        result.channelTrace[c].valid = false;
        result.channelTrace[c].violatedConservation.push_back(invariant.name);
        result.transitionSchemaValid = false;
      }
    }
  }
  if (std::any_of(request.state.begin(), request.state.end(),
                  [](std::int64_t value) { return value < 0; })) {
    result.transitionSchemaValid = false;
  }
  if (!result.transitionSchemaValid) {
    return result;  // invalid topology never evaluates, draws, or mutates
  }

  // ---- order and plan learned stages --------------------------------------
  std::vector<const TransitionStage*> ordered;
  ordered.reserve(stages_.size());
  for (const TransitionStage& stage : stages_) {
    ordered.push_back(&stage);
  }
  std::stable_sort(ordered.begin(), ordered.end(),
                   [](const TransitionStage* a, const TransitionStage* b) {
                     return static_cast<int>(a->scale) <
                            static_cast<int>(b->scale);
                   });

  std::unordered_map<std::string, std::size_t> slotOf;
  slotOf.reserve(speciesCount + auxCount + 16);
  for (std::size_t s = 0; s < speciesCount; ++s) {
    slotOf.emplace(request.speciesNames[s], s);
  }
  for (std::size_t a = 0; a < auxCount; ++a) {
    slotOf.emplace(request.auxNames[a], speciesCount + a);
  }
  std::size_t workingSize = speciesCount + auxCount;

  std::vector<PlannedStage> planned;
  std::set<std::string> declaredHazards;
  std::set<std::string> declaredWeights;
  bool hasGlobalHazard = false;
  for (const TransitionStage* stage : ordered) {
    TransitionStageTrace trace;
    trace.model = stage->name;
    trace.scale = stage->scale;
    if (!stage->model || !stage->model->loaded() ||
        stage->model->inputNames().empty() ||
        stage->model->outputNames().empty()) {
      result.stages.push_back(std::move(trace));
      continue;
    }

    PlannedStage plan;
    plan.stage = stage;
    for (const std::string& input : stage->model->inputNames()) {
      InputSource source;
      const auto slot = slotOf.find(input);
      if (slot != slotOf.end()) {
        source.constant = false;
        source.slot = slot->second;
      } else if (input == kStepInputName) {
        source.value = request.dt;
      } else {
        const auto shared = request.shared.find(input);
        if (shared != request.shared.end()) {
          source.value = shared->second;
        } else {
          trace.missingInputs.push_back(input);
        }
      }
      plan.inputs.push_back(source);
    }

    for (const std::string& output : stage->model->outputNames()) {
      auto [slot, inserted] = slotOf.emplace(output, workingSize);
      if (inserted) {
        ++workingSize;
      }
      plan.outputs.push_back({slot->second});

      bool recognized = false;
      if (output == kGlobalHazardOutput) {
        hasGlobalHazard = true;
        recognized = true;
      }
      for (const TransitionChannel& channel : request.channels) {
        if (output == channelHazardOutputName(channel.name)) {
          declaredHazards.insert(channel.name);
          recognized = true;
        } else if (output == channelWeightOutputName(channel.name)) {
          declaredWeights.insert(channel.name);
          recognized = true;
        }
      }
      if (recognized) {
        trace.hazardOutputs.push_back(output);
      } else {
        trace.intermediateOutputs.push_back(output);
        if (startsWith(output, "hazard_") ||
            startsWith(output, "weight_")) {
          trace.unappliedHazardOutputs.push_back(output);
        }
      }
    }

    trace.ran = true;
    trace.domainMeasured = stage->model->domainMeasured();
    const std::vector<std::string>& bands =
        stage->model->trainedScaleBands();
    for (std::size_t i = 0; i < bands.size(); ++i) {
      trace.trainedScale += (i ? "," : "") + bands[i];
    }
    if (!bands.empty() && stage->scale != DimensionScale::kUnscaled &&
        std::find(bands.begin(), bands.end(),
                  dimensionScaleName(stage->scale)) == bands.end()) {
      trace.scaleMismatch = true;
      ++result.stagesScaleMismatched;
    }
    trace.hasHoldout = stage->model->hasHoldout();
    trace.holdoutR2 = stage->model->holdoutR2Min();
    trace.holdoutSamples = stage->model->holdoutSamples();
    planned.push_back(std::move(plan));
    result.stages.push_back(std::move(trace));
    ++result.stagesRun;
  }

  if (planned.empty()) {
    return result;
  }

  const bool hasDirectHazards = !declaredHazards.empty();
  const bool hasWeights = !declaredWeights.empty();
  if (hasDirectHazards && (hasGlobalHazard || hasWeights)) {
    result.hazardSchemaValid = false;
  } else if (hasDirectHazards) {
    result.hazardMode = "direct";
  } else if (hasGlobalHazard &&
             (request.channels.size() == 1 || hasWeights)) {
    result.hazardMode = "weighted";
  } else {
    result.hazardSchemaValid = false;
  }

  std::vector<std::size_t> traceIndexOf;
  for (std::size_t i = 0; i < result.stages.size(); ++i) {
    if (result.stages[i].ran) {
      traceIndexOf.push_back(i);
    }
  }
  std::vector<std::set<std::string>> outOfDomainUnion(planned.size());
  std::vector<std::set<std::string>> starvedUnion(planned.size());
  std::vector<double> working(workingSize, 0.0);
  std::vector<double> x;
  std::vector<double> y;
  std::vector<double> scores(request.channels.size(), 0.0);
  std::uint64_t randomState = request.seed;

  for (std::size_t e = 0; e < elementCount; ++e) {
    const std::size_t stateBase = e * speciesCount;
    const std::size_t auxBase = e * auxCount;
    for (std::size_t s = 0; s < speciesCount; ++s) {
      working[s] = static_cast<double>(request.state[stateBase + s]);
    }
    for (std::size_t a = 0; a < auxCount; ++a) {
      working[speciesCount + a] = request.aux[auxBase + a];
    }
    std::fill(working.begin() + static_cast<std::ptrdiff_t>(
                  speciesCount + auxCount),
              working.end(), 0.0);

    for (std::size_t p = 0; p < planned.size(); ++p) {
      const PlannedStage& plan = planned[p];
      x.resize(plan.inputs.size());
      for (std::size_t i = 0; i < plan.inputs.size(); ++i) {
        const InputSource& source = plan.inputs[i];
        x[i] = source.constant ? source.value : working[source.slot];
      }
      if (!plan.stage->model->predictVector(x, &y) ||
          y.size() != plan.outputs.size()) {
        continue;
      }
      TransitionStageTrace& trace = result.stages[traceIndexOf[p]];
      const GenericSurrogate::Coverage coverage =
          plan.stage->model->coverageVector(x);
      if (!coverage.inDomain) {
        ++trace.elementsOutOfDomain;
        ++result.outOfDomainInferenceCount;
        outOfDomainUnion[p].insert(coverage.outOfDomainInputs.begin(),
                                   coverage.outOfDomainInputs.end());
      }
      if (!coverage.starvedInputs.empty()) {
        ++trace.elementsStarved;
        starvedUnion[p].insert(coverage.starvedInputs.begin(),
                               coverage.starvedInputs.end());
      }
      trace.maxExtrapolation =
          std::max(trace.maxExtrapolation, coverage.extrapolation);
      trace.maxStandardizedDeviation = std::max(
          trace.maxStandardizedDeviation,
          coverage.maxStandardizedDeviation);
      for (std::size_t o = 0; o < plan.outputs.size(); ++o) {
        working[plan.outputs[o].slot] = y[o];
      }
      ++result.inferenceCount;
    }

    if (!result.hazardSchemaValid) {
      continue;  // inference is counted; invalid output schema never draws
    }

    double eventHazard = 0.0;
    double scoreSum = 0.0;
    if (result.hazardMode == "direct") {
      for (std::size_t c = 0; c < request.channels.size(); ++c) {
        const std::string output =
            channelHazardOutputName(request.channels[c].name);
        const auto slot = slotOf.find(output);
        scores[c] = slot == slotOf.end()
                        ? 0.0
                        : boundedUnit(working[slot->second],
                                      &result.hazardsClamped);
        scoreSum += scores[c];
      }
      if (scoreSum > 1.0) {
        ++result.hazardRenormalizedElements;
        eventHazard = 1.0;
      } else {
        eventHazard = scoreSum;
      }
    } else {
      eventHazard = boundedUnit(
          working[slotOf.at(kGlobalHazardOutput)], &result.hazardsClamped);
      for (std::size_t c = 0; c < request.channels.size(); ++c) {
        const std::string output =
            channelWeightOutputName(request.channels[c].name);
        const auto slot = slotOf.find(output);
        if (slot == slotOf.end() && request.channels.size() == 1) {
          scores[c] = 1.0;
        } else {
          scores[c] = slot == slotOf.end()
                          ? 0.0
                          : boundedUnit(working[slot->second],
                                        &result.weightsClamped);
        }
        scoreSum += scores[c];
      }
    }
    if (!(eventHazard > 0.0) || !(scoreSum > 0.0)) {
      continue;
    }

    const double draw = uniform01(&randomState);
    ++result.drawCount;
    if (draw >= eventHazard) {
      continue;
    }
    const double channelDraw = (draw / eventHazard) * scoreSum;
    double cumulative = 0.0;
    std::size_t selected = request.channels.size() - 1;
    for (std::size_t c = 0; c < request.channels.size(); ++c) {
      cumulative += scores[c];
      if (channelDraw < cumulative) {
        selected = c;
        break;
      }
    }

    TransitionChannelTrace& channelTrace = result.channelTrace[selected];
    ++channelTrace.attempted;
    ++result.transitionAttempts;
    bool available = true;
    for (std::size_t s = 0; s < speciesCount; ++s) {
      const std::int64_t current = result.state[stateBase + s];
      const std::int64_t delta = request.channels[selected].delta[s];
      if (delta < 0) {
        const std::uint64_t magnitude =
            static_cast<std::uint64_t>(-(delta + 1)) + 1;
        if (static_cast<std::uint64_t>(current) < magnitude) {
          available = false;
          break;
        }
      } else if (current >
                 std::numeric_limits<std::int64_t>::max() - delta) {
        available = false;
        break;
      }
    }
    if (!available) {
      ++channelTrace.rejectedAvailability;
      ++result.rejectedAvailability;
      continue;
    }
    for (std::size_t s = 0; s < speciesCount; ++s) {
      result.state[stateBase + s] += request.channels[selected].delta[s];
    }
    ++channelTrace.accepted;
    ++result.transitionsAccepted;
  }

  for (std::size_t p = 0; p < planned.size(); ++p) {
    TransitionStageTrace& trace = result.stages[traceIndexOf[p]];
    trace.outOfDomainInputs.assign(outOfDomainUnion[p].begin(),
                                   outOfDomainUnion[p].end());
    trace.starvedInputs.assign(starvedUnion[p].begin(),
                               starvedUnion[p].end());
    if (trace.elementsOutOfDomain > 0) {
      ++result.stagesExtrapolating;
    }
    if (trace.elementsStarved > 0) {
      ++result.stagesStarved;
    }
    std::sort(trace.missingInputs.begin(), trace.missingInputs.end());
    std::sort(trace.intermediateOutputs.begin(),
              trace.intermediateOutputs.end());
    std::sort(trace.hazardOutputs.begin(), trace.hazardOutputs.end());
    std::sort(trace.unappliedHazardOutputs.begin(),
              trace.unappliedHazardOutputs.end());
  }

  result.ran = result.inferenceCount > 0;
  result.elementsEvaluated = result.ran ? elementCount : 0;
  return result;
}

}  // namespace trech::ml
