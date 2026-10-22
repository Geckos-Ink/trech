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

std::vector<NamedOutputAccuracy> collectOutputAccuracy(
    const GenericSurrogate& model) {
  std::vector<NamedOutputAccuracy> records;
  if (!model.hasOutputAccuracy()) {
    return records;  // illustrative map: absent stays absent
  }
  const std::vector<std::string>& names = model.outputNames();
  records.reserve(names.size());
  for (std::size_t o = 0; o < names.size(); ++o) {
    const GenericSurrogate::OutputAccuracy accuracy = model.outputAccuracy(o);
    if (!accuracy.measured()) {
      continue;  // this output carries no metric; never report a fake 0
    }
    NamedOutputAccuracy record;
    record.name = names[o];
    record.hasR2 = accuracy.hasR2;
    record.r2 = accuracy.r2;
    record.hasMeanAbsoluteError = accuracy.hasMeanAbsoluteError;
    record.meanAbsoluteError = accuracy.meanAbsoluteError;
    record.hasRootMeanSquaredError = accuracy.hasRootMeanSquaredError;
    record.rootMeanSquaredError = accuracy.rootMeanSquaredError;
    records.push_back(std::move(record));
  }
  std::sort(records.begin(), records.end(),
            [](const NamedOutputAccuracy& a, const NamedOutputAccuracy& b) {
              return a.name < b.name;
            });
  return records;
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
    const std::unordered_map<std::string, double>& seed,
    const CascadeOptions& options) const {
  CascadeResult result;
  result.context = seed;

  // Ascending scale order; dependency-ready stages within each band run in
  // registration order. Ordering depends only on declared IO and supplied facts.
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
  for (std::size_t index = 0; index < ordered.size(); ++index) {
    // A band may contain any number of dependent models. Prefer the first
    // ready stage in that band, retaining registration order among ready
    // peers. Never pull facts down from a higher band or retry a stage.
    auto ready = [&](const Stage* candidate) {
      if (!candidate->model || !candidate->model->loaded()) return true;
      const auto& inputs = candidate->model->inputNames();
      return std::all_of(inputs.begin(), inputs.end(), [&](const std::string& key) {
        return result.context.count(key) != 0;
      });
    };
    if (!ready(ordered[index])) {
      for (std::size_t next = index + 1;
           next < ordered.size() && ordered[next]->scale == ordered[index]->scale; ++next) {
        if (ready(ordered[next])) {
          std::rotate(ordered.begin() + index, ordered.begin() + next, ordered.begin() + next + 1);
          break;
        }
      }
    }
    const Stage* stage = ordered[index];
    CascadeStageResult sr;
    sr.model = stage->name;
    sr.scale = stage->scale;
    const bool targetsReached = !options.targetOutputs.empty() &&
        std::all_of(options.targetOutputs.begin(), options.targetOutputs.end(),
                    [&](const std::string& key) { return result.context.count(key) != 0; });
    if (targetsReached || (options.maxStages > 0 &&
                           static_cast<std::size_t>(result.stagesRun) >= options.maxStages)) {
      sr.skipReason = targetsReached ? "targets_reached" : "stage_budget";
      result.stopReason = sr.skipReason;
      ++result.stagesLimited;
      result.stages.push_back(std::move(sr));
      continue;
    }

    if (!stage->model || !stage->model->loaded()) {
      sr.ran = false;
      result.stages.push_back(std::move(sr));
      continue;  // graceful degradation: an unloaded stage is skipped, recorded
    }

    // Record which declared inputs are absent from the current context (the
    // stage must not manufacture a prediction from a zero substitute).
    for (const std::string& in : stage->model->inputNames()) {
      if (result.context.find(in) == result.context.end()) {
        sr.missingInputs.push_back(in);
      }
    }

    if (!sr.missingInputs.empty()) {
      std::sort(sr.missingInputs.begin(), sr.missingInputs.end());
      result.stages.push_back(std::move(sr));
      continue;  // no facts -> no prediction, including downstream dependencies
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
    sr.starvedInputs = cov.starvedInputs;
    sr.jointMeasured = cov.jointMeasured;
    sr.jointStarved = cov.jointStarved;
    sr.jointDistance = cov.jointDistance;
    sr.jointRadius = cov.jointRadius;
    if (!cov.inDomain) {
      ++result.stagesExtrapolating;
    }
    // Both starvation signals mean the same thing -- the model is guessing in a
    // region training never populated -- so they share the run-level count.
    if (!cov.starvedInputs.empty() || cov.jointStarved) {
      ++result.stagesStarved;
    }

    // Trained-scale-band provenance (workstream 3b): a stage run at a scale NOT
    // among its model's trained bands is being applied off the band it learned.
    const std::vector<std::string>& bands = stage->model->trainedScaleBands();
    for (std::size_t bi = 0; bi < bands.size(); ++bi) {
      sr.trainedScale += (bi ? "," : "") + bands[bi];
    }
    if (!bands.empty() && stage->scale != DimensionScale::kUnscaled &&
        std::find(bands.begin(), bands.end(),
                  dimensionScaleName(stage->scale)) == bands.end()) {
      sr.scaleMismatch = true;
      ++result.stagesScaleMismatched;
    }

    // Held-out accuracy carried with the model (workstream 3c): grade-the-gap
    // travels with the stage. Absent for illustrative maps (hasHoldout false).
    sr.hasHoldout = stage->model->hasHoldout();
    sr.holdoutR2 = stage->model->holdoutR2Min();
    sr.holdoutSamples = stage->model->holdoutSamples();

    // Per-output split of that accuracy, so a consumer can report the measured
    // uncertainty of the quantity IT read rather than the model's worst output.
    sr.outputAccuracy = collectOutputAccuracy(*stage->model);

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

  result.targetsReached = !options.targetOutputs.empty() &&
      std::all_of(options.targetOutputs.begin(), options.targetOutputs.end(),
                  [&](const std::string& key) { return result.context.count(key) != 0; });
  if (!options.targetOutputs.empty() && !result.targetsReached && result.stopReason == "complete") {
    result.stopReason = "targets_unavailable";
  }
  return result;
}

}  // namespace trech::ml
