#include "trech/ml/ScaleCascade.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <map>
#include <set>
#include <unordered_set>

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
    record.hasIntervalHalfWidth = accuracy.hasIntervalHalfWidth;
    record.intervalHalfWidth = accuracy.intervalHalfWidth;
    record.intervalCoverage = accuracy.intervalCoverage;
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

std::vector<ScaleCascade::RivalSet> ScaleCascade::planRivals() const {
  // Per band, connect loaded stages that declare a shared output.
  std::vector<RivalSet> sets;
  std::map<int, std::vector<const Stage*>> bands;
  for (const Stage& s : stages_)
    if (s.model && s.model->loaded()) bands[static_cast<int>(s.scale)].push_back(&s);
  for (auto& [band, members] : bands) {
    const std::size_t n = members.size();
    std::vector<std::size_t> parent(n);
    for (std::size_t i = 0; i < n; ++i) parent[i] = i;
    auto root = [&](std::size_t i) { while (parent[i] != i) i = parent[i] = parent[parent[i]]; return i; };
    std::map<std::string, std::vector<std::size_t>> producers;
    for (std::size_t i = 0; i < n; ++i)
      for (const std::string& o : members[i]->model->outputNames()) producers[o].push_back(i);
    for (const auto& [name, list] : producers)
      for (std::size_t k = 1; k < list.size(); ++k) parent[root(list[k])] = root(list[0]);
    std::map<std::size_t, RivalSet> byRoot;
    for (std::size_t i = 0; i < n; ++i) byRoot[root(i)].members.push_back(members[i]);
    for (auto& [r, set] : byRoot) {
      if (set.members.size() < 2) continue;
      set.scale = static_cast<DimensionScale>(band);
      std::set<std::string> shared, inputs;
      for (const auto& [name, list] : producers)
        if (list.size() >= 2 && root(list[0]) == r) shared.insert(name);
      for (const Stage* m : set.members)
        inputs.insert(m->model->inputNames().begin(), m->model->inputNames().end());
      set.outputs.assign(shared.begin(), shared.end());
      set.features.assign(inputs.begin(), inputs.end());
      sets.push_back(std::move(set));
    }
  }
  return sets;
}

std::vector<std::string> ScaleCascade::rivalOutputs() const {
  std::set<std::string> names;
  for (const RivalSet& set : planRivals()) names.insert(set.outputs.begin(), set.outputs.end());
  return {names.begin(), names.end()};
}

CascadeResult ScaleCascade::run(
    const std::unordered_map<std::string, double>& seed,
    const CascadeOptions& options) const {
  CascadeResult result;
  result.context = seed;
  // Trust follows the current producer of each named fact, not the whole
  // cascade. Independent branches and clean replacement facts stay independent.
  std::unordered_set<std::string> outOfDomainFacts;
  std::unordered_set<std::string> starvedFacts;
  std::unordered_set<std::string> scaleMismatchedFacts;

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

  // Rival arbitration: what each stage produced, resolved per band at its end.
  const bool arbitrating = static_cast<bool>(options.arbitrateRivals);
  std::vector<RivalSet> rivalSets;
  std::vector<std::string> rivalNames;
  struct Produced {
    bool ran = false;
    std::unordered_map<std::string, double> outputs;
    double extrapolation = 0.0;
    bool inDomain = true, starved = false, scaleMismatch = false;
  };
  std::vector<Produced> produced;
  if (arbitrating) {
    rivalSets = planRivals();
    rivalNames = rivalOutputs();
    produced.resize(stages_.size());
  }
  auto setTrust = [&](const std::string& key, bool inDomain, bool starved, bool mismatch) {
    if (inDomain) outOfDomainFacts.erase(key); else outOfDomainFacts.insert(key);
    if (starved) starvedFacts.insert(key); else starvedFacts.erase(key);
    if (mismatch) scaleMismatchedFacts.insert(key); else scaleMismatchedFacts.erase(key);
  };
  auto resolveBand = [&](DimensionScale scale) {
    std::vector<RivalCandidates> pending;
    std::vector<const RivalSet*> pendingSets;
    for (std::size_t si = 0; si < rivalSets.size(); ++si) {
      const RivalSet& set = rivalSets[si];
      if (set.scale != scale) continue;
      std::size_t ran = 0;
      for (const Stage* m : set.members) ran += produced[m->order].ran ? 1 : 0;
      if (ran < 2) continue;
      RivalCandidates rc;
      rc.set = si;
      rc.elements = {0};
      rc.featureNames = set.features;
      for (const std::string& f : set.features) {
        const auto it = result.context.find(f);
        rc.features.push_back(it == result.context.end() ? 0.0 : it->second);
      }
      for (const Stage* m : set.members) rc.members.push_back(m->name);
      const std::size_t M = set.members.size(), K = set.outputs.size();
      std::vector<double> mean(K, 0.0);
      bool complete = true;
      for (std::size_t k = 0; k < K; ++k) {
        rc.fields.push_back(static_cast<std::size_t>(
            std::lower_bound(rivalNames.begin(), rivalNames.end(), set.outputs[k]) - rivalNames.begin()));
        double sum = 0.0;
        std::size_t count = 0;
        for (const Stage* m : set.members) {
          const auto it = produced[m->order].outputs.find(set.outputs[k]);
          if (produced[m->order].ran && it != produced[m->order].outputs.end()) { sum += it->second; ++count; }
        }
        if (!count) complete = false; else mean[k] = sum / static_cast<double>(count);
      }
      if (!complete) continue;  // a shared output no running member produced
      for (std::size_t m = 0; m < M; ++m) {
        const Produced& p = produced[set.members[m]->order];
        for (std::size_t k = 0; k < K; ++k) {
          if (!p.ran) { rc.totals.push_back(std::numeric_limits<double>::quiet_NaN()); continue; }
          const auto it = p.outputs.find(set.outputs[k]);
          rc.totals.push_back(it != p.outputs.end() ? it->second : mean[k]);
        }
        rc.extrapolation.push_back(p.ran ? p.extrapolation : std::numeric_limits<double>::quiet_NaN());
      }
      rc.totals.insert(rc.totals.end(), mean.begin(), mean.end());
      rc.choice.assign(1, -1);
      pending.push_back(std::move(rc));
      pendingSets.push_back(&set);
    }
    if (pending.empty()) return;
    options.arbitrateRivals(pending);
    // The chosen candidate's values become the facts the next band reads;
    // their trust follows the members that produced them.
    for (std::size_t i = 0; i < pending.size(); ++i) {
      const RivalCandidates& rc = pending[i];
      const RivalSet& set = *pendingSets[i];
      const std::size_t M = set.members.size(), K = set.outputs.size();
      const int c = rc.choice.empty() ? -1 : rc.choice[0];
      if (c < 0 || static_cast<std::size_t>(c) > M) continue;
      for (std::size_t k = 0; k < K; ++k) {
        const double v = rc.totals[static_cast<std::size_t>(c) * K + k];
        if (!std::isfinite(v)) continue;
        bool inDomain = true, starved = false, mismatch = false;
        for (std::size_t m = 0; m < M; ++m) {
          const Produced& p = produced[set.members[m]->order];
          const bool contributes = static_cast<std::size_t>(c) == M
                                       ? p.ran && p.outputs.count(set.outputs[k]) != 0
                                       : m == static_cast<std::size_t>(c);
          if (!contributes) continue;
          inDomain = inDomain && p.inDomain;
          starved = starved || p.starved;
          mismatch = mismatch || p.scaleMismatch;
        }
        result.context[set.outputs[k]] = v;
        setTrust(set.outputs[k], inDomain, starved, mismatch);
      }
    }
    for (auto& rc : pending) result.rivals.push_back(std::move(rc));
  };

  result.stages.reserve(ordered.size());
  for (std::size_t index = 0; index < ordered.size(); ++index) {
    if (arbitrating && index > 0 && ordered[index]->scale != ordered[index - 1]->scale) {
      resolveBand(ordered[index - 1]->scale);
    }
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
    // the model saw). Numeric coverage alone cannot establish downstream trust:
    // a biased/bounded output can sit in the next model's hull despite being
    // produced outside its own model's trained domain.
    const GenericSurrogate::Coverage cov =
        stage->model->coverage(result.context);
    sr.localInDomain = cov.inDomain;
    for (const std::string& input : stage->model->inputNames()) {
      if (outOfDomainFacts.count(input)) {
        sr.upstreamOutOfDomainInputs.push_back(input);
      }
      if (starvedFacts.count(input)) {
        sr.upstreamStarvedInputs.push_back(input);
      }
      if (scaleMismatchedFacts.count(input)) {
        sr.upstreamScaleMismatchedInputs.push_back(input);
      }
    }
    std::sort(sr.upstreamOutOfDomainInputs.begin(),
              sr.upstreamOutOfDomainInputs.end());
    std::sort(sr.upstreamStarvedInputs.begin(), sr.upstreamStarvedInputs.end());
    std::sort(sr.upstreamScaleMismatchedInputs.begin(),
              sr.upstreamScaleMismatchedInputs.end());
    sr.inDomain = sr.localInDomain && sr.upstreamOutOfDomainInputs.empty();
    sr.domainMeasured = cov.domainMeasured;
    sr.extrapolation = cov.extrapolation;
    sr.maxStandardizedDeviation = cov.maxStandardizedDeviation;
    sr.outOfDomainInputs = cov.outOfDomainInputs;
    sr.starvedInputs = cov.starvedInputs;
    sr.jointMeasured = cov.jointMeasured;
    sr.jointStarved = cov.jointStarved;
    sr.jointDistance = cov.jointDistance;
    sr.jointRadius = cov.jointRadius;
    if (!sr.inDomain) {
      ++result.stagesExtrapolating;
    }
    // Both starvation signals mean the same thing -- the model is guessing in a
    // region training never populated -- so they share the run-level count.
    sr.localStarved = !cov.starvedInputs.empty() || cov.jointStarved;
    sr.starved = sr.localStarved || !sr.upstreamStarvedInputs.empty();
    if (sr.starved) {
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
      sr.localScaleMismatch = true;
    }
    sr.scaleMismatch = sr.localScaleMismatch || !sr.upstreamScaleMismatchedInputs.empty();
    if (sr.scaleMismatch) {
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
      setTrust(key, sr.inDomain, sr.starved, sr.scaleMismatch);
      sr.outputs.push_back(key);
    }
    if (arbitrating) {
      Produced& p = produced[stage->order];
      p.ran = true;
      p.outputs = outputs;
      p.extrapolation = sr.extrapolation;
      p.inDomain = sr.inDomain;
      p.starved = sr.starved;
      p.scaleMismatch = sr.scaleMismatch;
    }
    // Deterministic ordering of the recorded output-name list.
    std::sort(sr.outputs.begin(), sr.outputs.end());
    sr.ran = true;
    ++result.stagesRun;
    result.stages.push_back(std::move(sr));
  }

  if (arbitrating && !ordered.empty()) resolveBand(ordered.back()->scale);

  result.targetsReached = !options.targetOutputs.empty() &&
      std::all_of(options.targetOutputs.begin(), options.targetOutputs.end(),
                  [&](const std::string& key) { return result.context.count(key) != 0; });
  if (!options.targetOutputs.empty() && !result.targetsReached && result.stopReason == "complete") {
    result.stopReason = "targets_unavailable";
  }
  return result;
}

}  // namespace trech::ml
