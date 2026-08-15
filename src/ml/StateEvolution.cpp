#include "trech/ml/StateEvolution.hpp"

#include <algorithm>
#include <set>
#include <unordered_map>

#include "trech/ml/GenericSurrogate.hpp"

namespace trech::ml {
namespace {

// Where one declared model input reads from, resolved ONCE per evolve call.
// Batched inference runs the same model over every element, so paying the
// name-resolution cost per element (a string hash per input per element per
// step) would dwarf the arithmetic.  After planning, the per-element inner loop
// is pure index arithmetic.
struct InputSource {
  bool constant = true;   // false -> read the per-element working vector
  std::size_t slot = 0;   // working-vector slot when !constant
  double value = 0.0;     // shared fact / dt / defaulted-missing 0
};

enum class OutputKind {
  kRate,          // d_<field>_dt -> accumulate, integrate once at the end
  kAssign,        // set_<field>  -> write immediately, visible to higher stages
  kIntermediate   // any other name -> context only, never written back
};

struct OutputTarget {
  OutputKind kind = OutputKind::kIntermediate;
  std::size_t index = 0;  // field index (kRate/kAssign) or working slot
};

struct PlannedStage {
  const EvolutionStage* stage = nullptr;
  std::vector<InputSource> inputs;
  std::vector<OutputTarget> outputs;
};

// The reserved per-call fact every operator may declare as an input: the
// bounded step it is being integrated over.  A model that needs to know its own
// step (a per-step probability rather than a rate) declares "dt".
constexpr const char* kStepInputName = "dt";

}  // namespace

std::string StateEvolution::rateOutputName(const std::string& field) {
  return "d_" + field + "_dt";
}

std::string StateEvolution::assignOutputName(const std::string& field) {
  return "set_" + field;
}

void StateEvolution::addStage(std::string name, DimensionScale scale,
                              const GenericSurrogate* model,
                              std::size_t elementKindIndex) {
  EvolutionStage stage;
  stage.name = std::move(name);
  stage.scale = scale;
  stage.model = model;
  stage.elementKindIndex = elementKindIndex;
  stages_.push_back(std::move(stage));
}

EvolutionResult StateEvolution::evolve(const EvolutionRequest& request) const {
  EvolutionResult result;
  result.state = request.state;

  const std::size_t fieldCount = request.fields.size();
  const std::size_t auxCount = request.auxNames.size();
  const std::size_t elementCount = request.elementCount;
  if (fieldCount == 0 || elementCount == 0 ||
      request.state.size() < fieldCount * elementCount ||
      request.aux.size() < auxCount * elementCount) {
    return result;  // nothing to evolve / malformed block: leave state as-is
  }

  // ---- order stages by scale band (registration order breaks ties) --------
  std::vector<const EvolutionStage*> ordered;
  ordered.reserve(stages_.size());
  for (const EvolutionStage& s : stages_) {
    ordered.push_back(&s);
  }
  std::stable_sort(ordered.begin(), ordered.end(),
                   [](const EvolutionStage* a, const EvolutionStage* b) {
                     return static_cast<int>(a->scale) < static_cast<int>(b->scale);
                   });

  // ---- working-vector layout: fields, then aux, then intermediates --------
  // Precedence when a name appears twice is fields > aux > intermediates: the
  // per-element state is the most specific meaning of a name.
  std::unordered_map<std::string, std::size_t> slotOf;
  slotOf.reserve(fieldCount + auxCount + 8);
  std::unordered_map<std::string, std::size_t> fieldIndexOf;
  fieldIndexOf.reserve(fieldCount);
  for (std::size_t f = 0; f < fieldCount; ++f) {
    slotOf.emplace(request.fields[f].name, f);
    fieldIndexOf.emplace(request.fields[f].name, f);
  }
  for (std::size_t a = 0; a < auxCount; ++a) {
    slotOf.emplace(request.auxNames[a], fieldCount + a);
  }
  std::size_t workingSize = fieldCount + auxCount;

  // ---- plan every stage, registering intermediates as they appear ---------
  // Plans are built in EXECUTION order, so a stage can only read intermediates
  // that a strictly lower-scale stage already produced; a forward reference
  // resolves to "missing" and is reported, never silently zero-filled.
  std::vector<PlannedStage> planned;
  planned.reserve(ordered.size());
  result.stages.reserve(ordered.size());

  for (const EvolutionStage* stage : ordered) {
    EvolutionStageTrace trace;
    trace.model = stage->name;
    trace.scale = stage->scale;

    if (!stage->model || !stage->model->loaded() ||
        stage->model->inputNames().empty() ||
        stage->model->outputNames().empty()) {
      // Graceful degradation, matching ScaleCascade: an unloaded stage (or a
      // positional-only `.pt`, which carries no names to bind) is recorded and
      // skipped rather than failing the run.
      result.stages.push_back(std::move(trace));
      continue;
    }

    PlannedStage plan;
    plan.stage = stage;

    const std::vector<std::string>& inputNames = stage->model->inputNames();
    plan.inputs.reserve(inputNames.size());
    for (const std::string& in : inputNames) {
      InputSource source;
      const auto slot = slotOf.find(in);
      if (slot != slotOf.end()) {
        source.constant = false;
        source.slot = slot->second;
      } else if (in == kStepInputName) {
        source.value = request.dt;
      } else {
        const auto shared = request.shared.find(in);
        if (shared != request.shared.end()) {
          source.value = shared->second;
        } else {
          source.value = 0.0;  // same default as GenericSurrogate::predict
          trace.missingInputs.push_back(in);
        }
      }
      plan.inputs.push_back(source);
    }

    const std::vector<std::string>& outputNames = stage->model->outputNames();
    plan.outputs.reserve(outputNames.size());
    for (const std::string& out : outputNames) {
      OutputTarget target;
      bool applied = false;
      // `d_<field>_dt` / `set_<field>`: decode against the DECLARED fields
      // rather than by string surgery, so a field whose own name contains the
      // affixes cannot be misread.
      for (std::size_t f = 0; f < fieldCount && !applied; ++f) {
        const std::string& name = request.fields[f].name;
        if (out == rateOutputName(name)) {
          target.kind = OutputKind::kRate;
          target.index = f;
          trace.integratedFields.push_back(name);
          applied = true;
        } else if (out == assignOutputName(name)) {
          target.kind = OutputKind::kAssign;
          target.index = f;
          trace.assignedFields.push_back(name);
          applied = true;
        }
      }
      if (!applied) {
        // An intermediate: it gets a working slot under its literal name so
        // higher stages consume it exactly like a cascade stage output.
        auto [it, inserted] = slotOf.emplace(out, workingSize);
        if (inserted) {
          ++workingSize;
        }
        target.kind = OutputKind::kIntermediate;
        target.index = it->second;
        trace.intermediateOutputs.push_back(out);
        // Report a rate/assignment aimed at a field the caller never declared:
        // it updates nothing, and a silent no-op here would look like physics
        // that simply stopped happening.
        const bool looksLikeRate =
            out.rfind("d_", 0) == 0 && out.size() > 5 &&
            out.compare(out.size() - 3, 3, "_dt") == 0;
        const bool looksLikeAssign = out.rfind("set_", 0) == 0 && out.size() > 4;
        if (looksLikeRate || looksLikeAssign) {
          trace.unappliedFieldOutputs.push_back(out);
        }
      }
      plan.outputs.push_back(target);
    }

    trace.ran = true;
    trace.domainMeasured = stage->model->domainMeasured();
    if (stage->elementKindIndex != kAnyElementKind &&
        stage->elementKindIndex < request.elementKindNames.size()) {
      trace.elementKind = request.elementKindNames[stage->elementKindIndex];
    }

    // Trained-band provenance, identical in meaning to the cascade's.
    const std::vector<std::string>& bands = stage->model->trainedScaleBands();
    for (std::size_t bi = 0; bi < bands.size(); ++bi) {
      trace.trainedScale += (bi ? "," : "") + bands[bi];
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
    return result;  // every stage skipped: state untouched, traces recorded
  }

  // Index of each planned stage's trace, so the per-element loop accumulates
  // coverage into the right record (skipped stages also occupy a trace slot).
  std::vector<std::size_t> traceIndexOf;
  traceIndexOf.reserve(planned.size());
  for (std::size_t i = 0; i < result.stages.size(); ++i) {
    if (result.stages[i].ran) {
      traceIndexOf.push_back(i);
    }
  }

  // ---- evolve every element ----------------------------------------------
  std::vector<double> working(workingSize, 0.0);
  std::vector<double> rates(fieldCount, 0.0);
  std::vector<double> x;
  std::vector<double> y;
  // Unions of flagged input names, kept in std::set so the reported order is
  // deterministic regardless of which element tripped the flag first.
  std::vector<std::set<std::string>> outOfDomainUnion(planned.size());
  std::vector<std::set<std::string>> starvedUnion(planned.size());

  std::size_t elementsTouched = 0;
  for (std::size_t e = 0; e < elementCount; ++e) {
    // Which operator applies to THIS element: a kind-bound stage runs only on
    // elements of its kind, so one call can advance several materials through
    // their own trained operators (and leave a material with no compatible
    // operator untouched rather than forcing someone else's law onto it).
    const std::size_t elementKind =
        e < request.elementKindIndex.size() ? request.elementKindIndex[e]
                                            : kAnyElementKind;
    const std::size_t stateBase = e * fieldCount;
    const std::size_t auxBase = e * auxCount;
    for (std::size_t f = 0; f < fieldCount; ++f) {
      working[f] = request.state[stateBase + f];
      rates[f] = 0.0;
    }
    for (std::size_t a = 0; a < auxCount; ++a) {
      working[fieldCount + a] = request.aux[auxBase + a];
    }
    for (std::size_t s = fieldCount + auxCount; s < workingSize; ++s) {
      working[s] = 0.0;  // intermediates never carry over between elements
    }

    bool touched = false;
    for (std::size_t p = 0; p < planned.size(); ++p) {
      const PlannedStage& plan = planned[p];
      if (plan.stage->elementKindIndex != kAnyElementKind &&
          plan.stage->elementKindIndex != elementKind) {
        continue;  // another material's operator
      }
      x.resize(plan.inputs.size());
      for (std::size_t i = 0; i < plan.inputs.size(); ++i) {
        const InputSource& src = plan.inputs[i];
        x[i] = src.constant ? src.value : working[src.slot];
      }
      if (!plan.stage->model->predictVector(x, &y) ||
          y.size() != plan.outputs.size()) {
        continue;  // a stage that cannot evaluate contributes nothing
      }

      EvolutionStageTrace& trace = result.stages[traceIndexOf[p]];
      const GenericSurrogate::Coverage cov =
          plan.stage->model->coverageVector(x);
      if (!cov.inDomain) {
        ++trace.elementsOutOfDomain;
        ++result.outOfDomainInferenceCount;
        for (const std::string& name : cov.outOfDomainInputs) {
          outOfDomainUnion[p].insert(name);
        }
      }
      if (!cov.starvedInputs.empty()) {
        ++trace.elementsStarved;
        for (const std::string& name : cov.starvedInputs) {
          starvedUnion[p].insert(name);
        }
      }
      trace.maxExtrapolation =
          std::max(trace.maxExtrapolation, cov.extrapolation);
      trace.maxStandardizedDeviation =
          std::max(trace.maxStandardizedDeviation, cov.maxStandardizedDeviation);

      for (std::size_t o = 0; o < plan.outputs.size(); ++o) {
        const OutputTarget& target = plan.outputs[o];
        switch (target.kind) {
          case OutputKind::kRate:
            // Accumulate: two stages may each drive the same field (competing
            // reactions heating one parcel) without the caller sequencing them.
            rates[target.index] += y[o];
            break;
          case OutputKind::kAssign:
            working[target.index] = y[o];
            break;
          case OutputKind::kIntermediate:
            working[target.index] = y[o];
            break;
        }
      }
      ++trace.elementsMatched;
      ++result.inferenceCount;
      touched = true;
    }

    if (!touched) {
      // No operator claimed this element: leave its state bit-for-bit alone
      // (an untouched material must not silently pick up a zero rate).
      continue;
    }
    ++elementsTouched;

    // One explicit-Euler integration per call, at the bounded step the caller
    // already chose, then the caller's declared bounds.  Rates were all
    // evaluated against the state at the start of the step, so the outcome does
    // not depend on stage order beyond the scale ordering.
    for (std::size_t f = 0; f < fieldCount; ++f) {
      double value = working[f] + rates[f] * request.dt;
      const EvolutionField& field = request.fields[f];
      if (value < field.minValue) value = field.minValue;
      if (value > field.maxValue) value = field.maxValue;
      result.state[stateBase + f] = value;
    }
  }

  for (std::size_t p = 0; p < planned.size(); ++p) {
    EvolutionStageTrace& trace = result.stages[traceIndexOf[p]];
    trace.outOfDomainInputs.assign(outOfDomainUnion[p].begin(),
                                   outOfDomainUnion[p].end());
    trace.starvedInputs.assign(starvedUnion[p].begin(), starvedUnion[p].end());
    if (trace.elementsOutOfDomain > 0) {
      ++result.stagesExtrapolating;
    }
    if (trace.elementsStarved > 0) {
      ++result.stagesStarved;
    }
    std::sort(trace.integratedFields.begin(), trace.integratedFields.end());
    std::sort(trace.assignedFields.begin(), trace.assignedFields.end());
    std::sort(trace.intermediateOutputs.begin(), trace.intermediateOutputs.end());
    std::sort(trace.unappliedFieldOutputs.begin(),
              trace.unappliedFieldOutputs.end());
    std::sort(trace.missingInputs.begin(), trace.missingInputs.end());
  }

  result.ran = result.inferenceCount > 0;
  result.elementsEvolved = elementsTouched;
  return result;
}

}  // namespace trech::ml
