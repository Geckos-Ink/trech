#pragma once

#include <cstdint>

namespace trech::ml {

struct EventFeatures {
  double totalEdepMeV = 0.0;
  double totalTrackLengthMm = 0.0;
  std::int32_t totalStepCount = 0;
  std::int32_t totalTrackCount = 0;
  std::int32_t opticalPhotonSteps = 0;
  std::int32_t opticalPhotonTracks = 0;
  double opticalPhotonTrackLengthMm = 0.0;
};

} // namespace trech::ml
