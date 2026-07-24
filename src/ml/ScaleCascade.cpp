#include "trech/ml/ScaleCascade.hpp"

#include <algorithm>

#include "trech/ml/GenericSurrogate.hpp"

namespace trech::ml {

DimensionScale parseDimensionScale(const std::string& name) {
  if (name == "atomic") return DimensionScale::kAtomic;
  if (name == "nano") return DimensionScale::kNano;
  if (name == "micro") return DimensionScale::kMicro;
  if (name == "meso") return DimensionScale::kMeso;
  if (name == "macro") return DimensionScale::kMacro;
  return DimensionScale::kUnscaled;
}

const char* dimensionScaleName(DimensionScale scale) {
  switch (scale) {
    case DimensionScale::kAtomic:
      return "atomic";
    case DimensionScale::kNano:
      return "nano";
    case DimensionScale::kMicro:
      return "micro";
    case DimensionScale::kMeso:
      return "meso";
    case DimensionScale::kMacro:
      return "macro";
    case DimensionScale::kUnscaled:
      break;
  }
  return "unscaled";
}

void ScaleCascade::addStage(std::string name, DimensionScale scale,
                            const GenericSurrogate* model) {
  Stage stage;
  stage.name = std::move(name);
  stage.scale = scale;
  stage.model = model;
  stage.order = stages_.size();  // stable tie-breaker within a scale band
  stages_.push_back(std::move(stage));
}

CascadeResult ScaleCascade::run(
    const std::unordered_map<std::string, double>& seed) const {
  CascadeResult result;
  result.context = seed;

  // Evaluate in ascending scale order; registration order breaks ties so the
  // ordering is fully deterministic and independent of how the scenario listed
  // the models.
  std::vector<const Stage*> ordered;
  ordered.reserve(stages_.size());
  for (const Stage& s : stages_) {
    ordered.push_back(&s);
  }
  std::sort(ordered.begin(), ordered.end(),
            [](const Stage* a, const Stage* b) {
              if (a->scale != b->scale) {
                return static_cast<int>(a->scale) < static_cast<int>(b->scale);
              }
              return a->order < b->order;
            });

  result.stages.reserve(ordered.size());
  for (const Stage* stage : ordered) {
    CascadeStageResult sr;
    sr.model = stage->name;
    sr.scale = stage->scale;

    if (!stage->model || !stage->model->loaded()) {
      sr.ran = false;
      result.stages.push_back(std::move(sr));
      continue;  // graceful degradation: an unloaded stage is skipped, recorded
    }

    // Record which declared inputs are absent from the current context (the
    // surrogate defaults them to 0) so missing signal is surfaced, not hidden.
    for (const std::string& in : stage->model->inputNames()) {
      if (result.context.find(in) == result.context.end()) {
        sr.missingInputs.push_back(in);
      }
    }

    std::unordered_map<std::string, double> outputs;
    if (!stage->model->predict(result.context, &outputs)) {
      sr.ran = false;
      result.stages.push_back(std::move(sr));
      continue;
    }

    // Training-domain coverage of the inputs this stage predicted on (evaluated
    // on the context BEFORE merging this stage's own outputs, i.e. exactly what
    // the model saw).  A stage running out-of-domain is extrapolating: the flag
    // propagates up the ladder because its (low-confidence) outputs feed the
    // next stage's coverage too.
    const GenericSurrogate::Coverage cov =
        stage->model->coverage(result.context);
    sr.inDomain = cov.inDomain;
    sr.domainMeasured = cov.domainMeasured;
    sr.extrapolation = cov.extrapolation;
    sr.maxStandardizedDeviation = cov.maxStandardizedDeviation;
    sr.outOfDomainInputs = cov.outOfDomainInputs;
    if (!cov.inDomain) {
      ++result.stagesExtrapolating;
    }

    // Merge this stage's named outputs into the context for the next-higher
    // scale; later stages override earlier keys.
    for (const auto& [key, value] : outputs) {
      result.context[key] = value;
      sr.outputs.push_back(key);
    }
    // Deterministic ordering of the recorded output-name list.
    std::sort(sr.outputs.begin(), sr.outputs.end());
    sr.ran = true;
    ++result.stagesRun;
    result.stages.push_back(std::move(sr));
  }

  return result;
}

}  // namespace trech::ml
