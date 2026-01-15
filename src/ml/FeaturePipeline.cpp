#include "trech/ml/FeaturePipeline.hpp"

namespace trech::ml {

std::vector<float> FeaturePipeline::ToVector(const EventFeatures& features) const {
  return {
    static_cast<float>(features.totalEdepMeV),
    static_cast<float>(features.totalTrackLengthMm),
    static_cast<float>(features.totalStepCount),
    static_cast<float>(features.totalTrackCount),
    static_cast<float>(features.opticalPhotonSteps),
    static_cast<float>(features.opticalPhotonTracks),
    static_cast<float>(features.opticalPhotonTrackLengthMm),
  };
}

std::vector<std::string> FeaturePipeline::FeatureNames() const {
  return {
    "total_edep_mev",
    "total_track_length_mm",
    "total_step_count",
    "total_track_count",
    "optical_photon_steps",
    "optical_photon_tracks",
    "optical_photon_track_length_mm",
  };
}

} // namespace trech::ml
