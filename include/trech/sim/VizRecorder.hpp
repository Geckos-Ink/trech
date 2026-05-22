#pragma once

#include "trech/core/Config.hpp"

#include <cstddef>
#include <cstdint>
#include <functional>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>

namespace trech::sim {

struct VizTrajectorySegment {
  double x = 0.0;
  double y = 0.0;
  double z = 0.0;
  double dirX = 0.0;
  double dirY = 0.0;
  double dirZ = 0.0;
  double energyEv = 0.0;
  double timeNs = 0.0;
  double stepLengthMm = 0.0;
  std::string volume;
  std::string material;
};

struct VizTrajectory {
  int eventId = -1;
  int trackId = -1;
  std::string particle;
  std::vector<VizTrajectorySegment> segments;
  bool capped = false;  // hit maxSegmentsPerTrajectory
};

// Thread-safe collector for sampled trajectory polylines.  Geant4 may run with
// worker threads; we serialize all writes through a single mutex.  This is
// fine for a viz-debug workflow where event volumes are low.
class VizRecorder {
 public:
  static VizRecorder& instance();

  void configure(const VizConfig& cfg, const std::string& outputDir,
                 std::uint64_t seed);
  void reset();
  bool enabled() const { return cfg_.enable; }
  const VizConfig& config() const { return cfg_; }

  // Push a single sampled step for an optical-photon track.  Sampling rules
  // are applied internally — caller can pass every step and rely on this to
  // skip / cap as configured.
  void recordStep(int eventId, int trackId, const char* particle,
                  double xMm, double yMm, double zMm,
                  double dirX, double dirY, double dirZ,
                  double energyEv, double timeNs, double stepLengthMm,
                  const std::string& volume, const std::string& material);

  // Persist all captured trajectories to trajectoriesPath.  Idempotent.
  void flush();

  std::string trajectoriesPath() const { return trajectoriesPath_; }
  int recordedTrajectoryCount() const;
  int recordedSegmentCount() const;
  int droppedTrajectoryCount() const { return droppedTrajectories_; }
  int cappedTrajectoryCount() const { return cappedTrajectories_; }

 private:
  VizRecorder() = default;

  struct TrajectoryKey {
    int eventId;
    int trackId;
    bool operator==(const TrajectoryKey& other) const {
      return eventId == other.eventId && trackId == other.trackId;
    }
  };
  struct TrajectoryKeyHash {
    std::size_t operator()(const TrajectoryKey& k) const noexcept {
      return std::hash<long long>{}((static_cast<long long>(k.eventId) << 32) ^
                                    static_cast<long long>(k.trackId));
    }
  };

  mutable std::mutex mutex_;
  VizConfig cfg_;
  std::string trajectoriesPath_;
  std::uint64_t seed_ = 0;
  std::unordered_map<TrajectoryKey, std::size_t, TrajectoryKeyHash> indexByKey_;
  std::vector<VizTrajectory> trajectories_;
  bool flushed_ = false;
  int droppedTrajectories_ = 0;
  int cappedTrajectories_ = 0;
};

}  // namespace trech::sim
