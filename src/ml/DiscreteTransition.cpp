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
  bool available = true;  // false: no declared fact or earlier producer
  bool constant = true;
  std::size_t slot = 0;
  double value = 0.0;
};

struct OutputTarget {
  std::size_t slot = 0;
};

struct PlannedStage {
  const TransitionStage* stage = nullptr;
  std::size_t traceIndex = 0;
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
                                  const GenericSurrogate* model,
                                  std::size_t elementKindIndex) {
  TransitionStage stage;
  stage.name = std::move(name);
  stage.scale = scale;
  stage.model = model;
  stage.elementKindIndex = elementKindIndex;
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
    plan.traceIndex = result.stages.size();
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
          source.available = false;
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

    trace.domainMeasured = stage->model->domainMeasured();
    if (stage->elementKindIndex != kAnyElementKind &&
        stage->elementKindIndex < request.elementKindNames.size()) {
      trace.elementKind = request.elementKindNames[stage->elementKindIndex];
    }
    const std::vector<std::string>& bands =
        stage->model->trainedScaleBands();
    for (std::size_t i = 0; i < bands.size(); ++i) {
      trace.trainedScale += (i ? "," : "") + bands[i];
    }
    if (!bands.empty() && stage->scale != DimensionScale::kUnscaled &&
        std::find(bands.begin(), bands.end(),
                  dimensionScaleName(stage->scale)) == bands.end()) {
      trace.scaleMismatch = true;
    }
    trace.hasHoldout = stage->model->hasHoldout();
    trace.holdoutR2 = stage->model->holdoutR2Min();
    trace.holdoutSamples = stage->model->holdoutSamples();
    trace.outputAccuracy = collectOutputAccuracy(*stage->model);
    planned.push_back(std::move(plan));
    result.stages.push_back(std::move(trace));
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

  std::vector<std::set<std::string>> outOfDomainUnion(planned.size());
  std::vector<std::set<std::string>> starvedUnion(planned.size());
  std::vector<double> working(workingSize, 0.0);
  std::vector<unsigned char> available(workingSize, 0);
  std::vector<unsigned char> produced(workingSize, 0);
  // Shared context can seed an intermediate if its material-specific producer
  // does not run. Slots are reset per element/pair; another material's output
  // must never become an implicit constant for this one.
  std::vector<double> initialWorking(workingSize, 0.0);
  std::vector<unsigned char> initialAvailable(workingSize, 0);
  std::fill(initialAvailable.begin(),
            initialAvailable.begin() + (speciesCount + auxCount), 1);
  for (const auto& [name, slot] : slotOf) {
    if (slot < (speciesCount + auxCount)) continue;
    const auto fact = request.shared.find(name);
    if (fact != request.shared.end()) {
      initialWorking[slot] = fact->second;
      initialAvailable[slot] = 1;
    }
  }
  std::vector<double> x;
  std::vector<double> y;
  // Reused across every element/pair inference in this call, so the
  // batched path allocates nothing per evaluation (same arithmetic).
  GenericSurrogate::Workspace workspace;
  std::uint64_t randomState = request.seed;

  DomainRouter router;
  if (request.routeByDomain) {
    std::vector<DomainRouterStage> routed;
    routed.reserve(planned.size());
    for (const PlannedStage& plan : planned) {
      DomainRouterStage stage;
      stage.name = plan.stage->name;
      stage.model = plan.stage->model;
      stage.scale = plan.stage->scale;
      stage.outputs = plan.stage->model->outputNames();
      stage.routable = plan.stage->elementKindIndex == kAnyElementKind;
      routed.push_back(std::move(stage));
    }
    router.plan(routed, elementCount);
  }
  const bool routing = router.active();
  auto fillInputs = [&](std::size_t q, std::vector<double>& out) {
    const PlannedStage& plan = planned[q];
    out.resize(plan.inputs.size());
    for (std::size_t i = 0; i < plan.inputs.size(); ++i) {
      const InputSource& source = plan.inputs[i];
      if (!source.available || (!source.constant && !available[source.slot])) return false;
      out[i] = source.constant ? source.value : working[source.slot];
    }
    return true;
  };

  // A per-element fact by name (state, aux, an intermediate already produced,
  // or shared context): routing features read it; no prediction does.
  auto factOf = [&](const std::string& name, double& out) {
    const auto slot = slotOf.find(name);
    if (slot != slotOf.end()) {
      if (!available[slot->second]) return false;
      out = working[slot->second];
      return true;
    }
    const auto fact = request.shared.find(name);
    if (fact == request.shared.end()) return false;
    out = fact->second;
    return true;
  };

  // Channel output slots, resolved once (npos = no stage produces it).
  constexpr std::size_t kNoSlot = std::numeric_limits<std::size_t>::max();
  const std::size_t channelCount = request.channels.size();
  std::vector<std::size_t> hazardSlotOf(channelCount, kNoSlot);
  std::vector<std::size_t> weightSlotOf(channelCount, kNoSlot);
  for (std::size_t c = 0; c < channelCount; ++c) {
    const auto h = slotOf.find(channelHazardOutputName(request.channels[c].name));
    if (h != slotOf.end()) hazardSlotOf[c] = h->second;
    const auto w = slotOf.find(channelWeightOutputName(request.channels[c].name));
    if (w != slotOf.end()) weightSlotOf[c] = w->second;
  }
  const auto globalHazard = slotOf.find(kGlobalHazardOutput);
  const std::size_t globalHazardSlot =
      globalHazard == slotOf.end() ? kNoSlot : globalHazard->second;

  // The element's event hazard and channel scores from the hazard outputs
  // produced on it. Returns false when the element cannot draw.
  auto channelOdds = [&](const std::vector<double>& w,
                         const std::vector<unsigned char>& prod,
                         std::size_t* hazardClamps, std::size_t* weightClamps,
                         std::size_t* renormalized, double* eventHazard,
                         double* scoreSum, double* out) {
    *eventHazard = 0.0;
    *scoreSum = 0.0;
    if (result.hazardMode == "direct") {
      for (std::size_t c = 0; c < channelCount; ++c) {
        const std::size_t slot = hazardSlotOf[c];
        out[c] = slot == kNoSlot || !prod[slot] ? 0.0
                                                : boundedUnit(w[slot], hazardClamps);
        *scoreSum += out[c];
      }
      if (*scoreSum > 1.0) {
        ++(*renormalized);
        *eventHazard = 1.0;
      } else {
        *eventHazard = *scoreSum;
      }
    } else {
      // A shared fact may seed an intermediate, but a reaction hazard must
      // have been predicted by a stage that actually ran on THIS element.
      if (globalHazardSlot == kNoSlot || !prod[globalHazardSlot]) return false;
      *eventHazard = boundedUnit(w[globalHazardSlot], hazardClamps);
      for (std::size_t c = 0; c < channelCount; ++c) {
        const std::size_t slot = weightSlotOf[c];
        if (slot == kNoSlot && channelCount == 1) {
          out[c] = 1.0;
        } else {
          out[c] = slot == kNoSlot || !prod[slot] ? 0.0
                                                  : boundedUnit(w[slot], weightClamps);
        }
        *scoreSum += out[c];
      }
    }
    return *eventHazard > 0.0 && *scoreSum > 0.0;
  };

  // Rival arbitration bookkeeping (routing only): per set, its planned members
  // and the hazard/weight slots they write; per element, what each member
  // produced, so every candidate can be recomposed after the element ran.
  const bool arbitrating = routing && result.hazardSchemaValid &&
                           static_cast<bool>(request.arbitrateRivals);
  std::vector<RivalCandidates> rivals;
  std::vector<std::vector<std::size_t>> setMembers;
  std::vector<std::vector<std::size_t>> setHazardSlots;
  std::vector<std::vector<std::size_t>> hazardOutputsOf(planned.size());
  std::vector<unsigned char> stageRan(planned.size(), 0);
  std::vector<double> stageExtrapolation(planned.size(), 0.0);
  std::vector<std::vector<double>> stageY(planned.size());
  if (arbitrating) {
    for (std::size_t p = 0; p < planned.size(); ++p) {
      const auto& names = planned[p].stage->model->outputNames();
      for (std::size_t o = 0; o < names.size(); ++o) {
        const std::size_t slot = planned[p].outputs[o].slot;
        bool recognized = slot == globalHazardSlot;
        for (std::size_t c = 0; c < channelCount && !recognized; ++c)
          recognized = slot == hazardSlotOf[c] || slot == weightSlotOf[c];
        if (recognized) hazardOutputsOf[p].push_back(o);
      }
      const std::size_t set = router.setOf(p);
      if (set == DomainRouter::kNoSet) continue;
      if (set >= setMembers.size()) setMembers.resize(set + 1);
      setMembers[set].push_back(p);
    }
    rivals.resize(setMembers.size());
    setHazardSlots.resize(setMembers.size());
    for (std::size_t s = 0; s < setMembers.size(); ++s) {
      rivals[s].set = s;
      std::set<std::size_t> slots;
      for (std::size_t p : setMembers[s]) {
        rivals[s].members.push_back(planned[p].stage->name);
        for (std::size_t o : hazardOutputsOf[p]) slots.insert(planned[p].outputs[o].slot);
      }
      setHazardSlots[s].assign(slots.begin(), slots.end());
      if (!slots.empty())
        for (std::size_t c = 0; c < channelCount; ++c) rivals[s].fields.push_back(c);
    }
  }

  // Draws are deferred until every element is evaluated (arbitration may
  // replace a rival's odds); they still run once per element in element
  // order, so the arithmetic and the RNG sequence are unchanged.
  std::vector<unsigned char> drawable(elementCount, 0);
  std::vector<double> eventHazardOf(elementCount, 0.0);
  std::vector<double> scoreSumOf(elementCount, 0.0);
  std::vector<double> scoresOf(elementCount * channelCount, 0.0);
  std::vector<double> candidateWorking;
  std::vector<unsigned char> candidateProduced;
  std::vector<double> candidateScores(channelCount, 0.0);
  std::vector<double> baseOdds(channelCount, 0.0);
  std::vector<double> memberOdds;
  // Per-channel probability of a transition in this step for one composition
  // of the set's hazard slots (`member` = -1: no member ran).
  auto composedOdds = [&](std::size_t s, long member, double* out) {
    candidateWorking = working;
    candidateProduced = produced;
    for (std::size_t slot : setHazardSlots[s]) candidateProduced[slot] = 0;
    if (member >= 0) {
      const std::size_t p = setMembers[s][static_cast<std::size_t>(member)];
      for (std::size_t o : hazardOutputsOf[p]) {
        candidateWorking[planned[p].outputs[o].slot] = stageY[p][o];
        candidateProduced[planned[p].outputs[o].slot] = 1;
      }
    }
    std::size_t ignored = 0;
    double event = 0.0, sum = 0.0;
    const bool can = channelOdds(candidateWorking, candidateProduced, &ignored, &ignored,
                                 &ignored, &event, &sum, candidateScores.data());
    for (std::size_t c = 0; c < channelCount; ++c)
      out[c] = can ? event * candidateScores[c] / sum : 0.0;
  };

  std::size_t elementsTouched = 0;
  for (std::size_t e = 0; e < elementCount; ++e) {
    // Which chemistry applies to THIS cell: a kind-bound stage evaluates only
    // the elements of its material class, so a batch cell and a molten cell in
    // the same inventory arrays use the hazards their own material selected.
    const std::size_t elementKind =
        e < request.elementKindIndex.size() ? request.elementKindIndex[e]
                                            : kAnyElementKind;
    working = initialWorking;
    available = initialAvailable;
    std::fill(produced.begin(), produced.end(), 0);
    const std::size_t stateBase = e * speciesCount;
    const std::size_t auxBase = e * auxCount;
    for (std::size_t s = 0; s < speciesCount; ++s) {
      working[s] = static_cast<double>(request.state[stateBase + s]);
    }
    for (std::size_t a = 0; a < auxCount; ++a) {
      working[speciesCount + a] = request.aux[auxBase + a];
    }
    if (routing) router.beginElement();
    if (arbitrating) std::fill(stageRan.begin(), stageRan.end(), 0);

    bool touched = false;
    for (std::size_t p = 0; p < planned.size(); ++p) {
      const PlannedStage& plan = planned[p];
      if (plan.stage->elementKindIndex != kAnyElementKind &&
          plan.stage->elementKindIndex != elementKind) {
        continue;  // another material's chemistry
      }
      if (routing && !router.admits(p, fillInputs, factOf, workspace)) {
        continue;  // a rival law whose trained domain does not cover this cell
      }
      auto& trace = result.stages[plan.traceIndex];
      bool ready = true;
      x.resize(plan.inputs.size());
      for (std::size_t i = 0; i < plan.inputs.size(); ++i) {
        const InputSource& source = plan.inputs[i];
        if (!source.available || (!source.constant && !available[source.slot])) {
          const auto& name = plan.stage->model->inputNames()[i];
          if (std::find(trace.missingInputs.begin(), trace.missingInputs.end(), name) ==
              trace.missingInputs.end()) {
            trace.missingInputs.push_back(name);
          }
          ready = false;
        }
        x[i] = source.constant ? source.value : working[source.slot];
      }
      if (!ready) continue;
      y.resize(plan.outputs.size());
      if (!plan.stage->model->predictInto(x.data(), x.size(), y.data(),
                                          y.size(), workspace)) {
        continue;
      }
      const GenericSurrogate::Coverage coverage =
          plan.stage->model->coverageVector(x, workspace);
      if (!coverage.inDomain) {
        ++trace.elementsOutOfDomain;
        ++result.outOfDomainInferenceCount;
        outOfDomainUnion[p].insert(coverage.outOfDomainInputs.begin(),
                                   coverage.outOfDomainInputs.end());
      }
      if (!coverage.starvedInputs.empty() || coverage.jointStarved) {
        ++result.starvedInferenceCount;
      }
      if (trace.scaleMismatch) {
        ++result.scaleMismatchedInferenceCount;
      }
      trace.jointMeasured = coverage.jointMeasured;
      if (coverage.jointStarved) {
        ++trace.elementsJointStarved;
      }
      trace.maxJointDistance =
          std::max(trace.maxJointDistance, coverage.jointDistance);
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
        available[plan.outputs[o].slot] = 1;
        produced[plan.outputs[o].slot] = 1;
      }
      if (arbitrating) {
        stageRan[p] = 1;
        stageExtrapolation[p] = coverage.extrapolation;
        stageY[p] = y;
      }
      if (!trace.ran) {
        trace.ran = true;
        ++result.stagesRun;
        if (trace.scaleMismatch) ++result.stagesScaleMismatched;
      }
      ++trace.elementsMatched;
      ++result.inferenceCount;
      touched = true;
    }

    if (routing) router.endElement(e);
    if (!touched) {
      // No chemistry claimed this cell: no hazard, no draw, no mutation. The
      // RNG is untouched, so the other cells' draws are unaffected.
      continue;
    }
    ++elementsTouched;

    if (!result.hazardSchemaValid) {
      continue;  // inference is counted; invalid output schema never draws
    }

    drawable[e] = channelOdds(working, produced, &result.hazardsClamped,
                              &result.weightsClamped,
                              &result.hazardRenormalizedElements,
                              &eventHazardOf[e], &scoreSumOf[e],
                              &scoresOf[e * channelCount]) ? 1 : 0;

    // Sets where two or more rivals ran on this cell: every rival alone, then
    // their cooperating combination (the base odds plus each rival's change).
    for (std::size_t s = 0; arbitrating && s < rivals.size(); ++s) {
      std::size_t ran = 0;
      for (std::size_t p : setMembers[s]) ran += stageRan[p];
      if (ran < 2 || rivals[s].fields.empty()) continue;
      RivalCandidates& rc = rivals[s];
      const std::size_t M = rc.members.size();
      rc.elements.push_back(e);
      composedOdds(s, -1, baseOdds.data());
      std::vector<double> combined(baseOdds);
      for (std::size_t m = 0; m < M; ++m) {
        if (!stageRan[setMembers[s][m]]) {
          rc.totals.insert(rc.totals.end(), channelCount,
                           std::numeric_limits<double>::quiet_NaN());
          continue;
        }
        memberOdds.assign(channelCount, 0.0);
        composedOdds(s, static_cast<long>(m), memberOdds.data());
        rc.totals.insert(rc.totals.end(), memberOdds.begin(), memberOdds.end());
        for (std::size_t c = 0; c < channelCount; ++c) combined[c] += memberOdds[c] - baseOdds[c];
      }
      double total = 0.0;
      for (double& v : combined) total += (v = std::max(0.0, v));
      if (total > 1.0) for (double& v : combined) v /= total;
      rc.totals.insert(rc.totals.end(), combined.begin(), combined.end());
      for (std::size_t m = 0; m < M; ++m)
        rc.extrapolation.push_back(stageRan[setMembers[s][m]]
                                       ? stageExtrapolation[setMembers[s][m]]
                                       : std::numeric_limits<double>::quiet_NaN());
    }
  }

  if (arbitrating) {
    std::vector<RivalCandidates> pending;
    for (auto& rc : rivals)
      if (!rc.elements.empty()) { rc.choice.assign(rc.elements.size(), -1); pending.push_back(std::move(rc)); }
    if (!pending.empty()) {
      request.arbitrateRivals(pending);
      // A chosen candidate's channel probabilities replace the cell's odds.
      for (const RivalCandidates& rc : pending) {
        const std::size_t C = rc.candidates();
        for (std::size_t j = 0; j < rc.elements.size(); ++j) {
          const int choice = j < rc.choice.size() ? rc.choice[j] : -1;
          if (choice < 0 || static_cast<std::size_t>(choice) >= C) continue;
          const double* odds = &rc.totals[(j * C + static_cast<std::size_t>(choice)) * channelCount];
          if (!std::all_of(odds, odds + channelCount, [](double v) { return std::isfinite(v); })) continue;
          const std::size_t e = rc.elements[j];
          double sum = 0.0;
          for (std::size_t c = 0; c < channelCount; ++c) sum += (scoresOf[e * channelCount + c] = std::max(0.0, odds[c]));
          scoreSumOf[e] = sum;
          eventHazardOf[e] = std::min(1.0, sum);
          drawable[e] = sum > 0.0 ? 1 : 0;
        }
      }
      result.rivals = std::move(pending);
    }
  }

  for (std::size_t e = 0; e < elementCount; ++e) {
    if (!drawable[e]) continue;
    const double eventHazard = eventHazardOf[e];
    const double scoreSum = scoreSumOf[e];
    const double* scores = &scoresOf[e * channelCount];
    const std::size_t stateBase = e * speciesCount;

    const double draw = uniform01(&randomState);
    ++result.drawCount;
    if (draw >= eventHazard) {
      continue;
    }
    const double channelDraw = (draw / eventHazard) * scoreSum;
    double cumulative = 0.0;
    std::size_t selected = channelCount - 1;
    for (std::size_t c = 0; c < channelCount; ++c) {
      cumulative += scores[c];
      if (channelDraw < cumulative) {
        selected = c;
        break;
      }
    }

    TransitionChannelTrace& channelTrace = result.channelTrace[selected];
    ++channelTrace.attempted;
    ++result.transitionAttempts;
    bool countsAvailable = true;
    for (std::size_t s = 0; s < speciesCount; ++s) {
      const std::int64_t current = result.state[stateBase + s];
      const std::int64_t delta = request.channels[selected].delta[s];
      if (delta < 0) {
        const std::uint64_t magnitude =
            static_cast<std::uint64_t>(-(delta + 1)) + 1;
        if (static_cast<std::uint64_t>(current) < magnitude) {
          countsAvailable = false;
          break;
        }
      } else if (current >
                 std::numeric_limits<std::int64_t>::max() - delta) {
        countsAvailable = false;
        break;
      }
    }
    if (!countsAvailable) {
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
    TransitionStageTrace& trace = result.stages[planned[p].traceIndex];
    trace.outOfDomainInputs.assign(outOfDomainUnion[p].begin(),
                                   outOfDomainUnion[p].end());
    trace.starvedInputs.assign(starvedUnion[p].begin(),
                               starvedUnion[p].end());
    if (trace.elementsOutOfDomain > 0) {
      ++result.stagesExtrapolating;
    }
    // Both starvation signals mean the same thing -- guessing in a region
    // training never populated -- so they share the run-level count.
    if (trace.elementsStarved > 0 || trace.elementsJointStarved > 0) {
      ++result.stagesStarved;
    }
    std::sort(trace.missingInputs.begin(), trace.missingInputs.end());
    std::sort(trace.intermediateOutputs.begin(),
              trace.intermediateOutputs.end());
    std::sort(trace.hazardOutputs.begin(), trace.hazardOutputs.end());
    std::sort(trace.unappliedHazardOutputs.begin(),
              trace.unappliedHazardOutputs.end());
  }

  if (routing) result.routing = router.finish();
  result.ran = result.inferenceCount > 0;
  result.elementsEvaluated = elementsTouched;
  return result;
}

}  // namespace trech::ml
