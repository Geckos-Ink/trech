#include "trech/ml/Stratifier.hpp"

#include <algorithm>
#include <cctype>

namespace trech::ml {
namespace {

StratifyResult unclassified(const StratifyConfig& cfg) {
  return {cfg.labelUnclassified, "", "disabled", false};
}

std::string normalizeMode(std::string mode) {
  std::transform(mode.begin(), mode.end(), mode.begin(),
                 [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
  if (mode == "predictive") {
    return mode;
  }
  return "strict";
}

} // namespace

EventStratifier::EventStratifier(const StratifyConfig& cfg,
                                 const DeterminismConfig& determinism)
    : cfg_(cfg), determinism_(determinism) {
  model_.SetLabels(cfg_.labelPredictable, cfg_.labelExceptional);
  predictiveModeEnabled_ = normalizeMode(determinism_.mode) == "predictive";
  if (predictiveModeEnabled_ && !cfg_.modelPath.empty()) {
    modelLoaded_ = model_.Load(cfg_.modelPath);
  }
}

StratifyResult EventStratifier::Evaluate(const EventFeatures& features) {
  if (!cfg_.enable) {
    return unclassified(cfg_);
  }

  if (modelLoaded_) {
    const auto vector = pipeline_.ToVector(features);
    std::string label;
    if (model_.PredictLabel(vector, &label)) {
      return {label, "model", "model", label == cfg_.labelExceptional};
    }
  }

  return EvaluateThresholds(features);
}

bool EventStratifier::predictiveModeEnabled() const {
  return predictiveModeEnabled_;
}

bool EventStratifier::modelConfigured() const {
  return !cfg_.modelPath.empty();
}

bool EventStratifier::modelLoaded() const {
  return modelLoaded_;
}

StratifyResult EventStratifier::EvaluateThresholds(const EventFeatures& features) const {
  if (cfg_.edepMeVThreshold > 0.0 && features.totalEdepMeV > cfg_.edepMeVThreshold) {
    return {cfg_.labelExceptional, "edep_mev_threshold", "thresholds", true};
  }
  if (cfg_.opticalTrackLengthMmThreshold > 0.0 &&
      features.opticalPhotonTrackLengthMm > cfg_.opticalTrackLengthMmThreshold) {
    return {cfg_.labelExceptional, "optical_track_length_mm_threshold", "thresholds", true};
  }
  if (cfg_.totalTrackLengthMmThreshold > 0.0 &&
      features.totalTrackLengthMm > cfg_.totalTrackLengthMmThreshold) {
    return {cfg_.labelExceptional, "track_length_mm_threshold", "thresholds", true};
  }
  if (cfg_.totalTrackCountThreshold > 0 &&
      features.totalTrackCount > cfg_.totalTrackCountThreshold) {
    return {cfg_.labelExceptional, "track_count_threshold", "thresholds", true};
  }
  if (cfg_.totalStepCountThreshold > 0 &&
      features.totalStepCount > cfg_.totalStepCountThreshold) {
    return {cfg_.labelExceptional, "step_count_threshold", "thresholds", true};
  }
  if (cfg_.opticalPhotonTrackThreshold > 0 &&
      features.opticalPhotonTracks > cfg_.opticalPhotonTrackThreshold) {
    return {cfg_.labelExceptional, "optical_track_count_threshold", "thresholds", true};
  }
  if (cfg_.opticalPhotonStepThreshold > 0 &&
      features.opticalPhotonSteps > cfg_.opticalPhotonStepThreshold) {
    return {cfg_.labelExceptional, "optical_step_count_threshold", "thresholds", true};
  }

  return {cfg_.labelPredictable, "", "thresholds", false};
}

} // namespace trech::ml
