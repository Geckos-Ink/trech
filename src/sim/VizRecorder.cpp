#include "trech/sim/VizRecorder.hpp"

#include <nlohmann/json.hpp>

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <utility>

namespace trech::sim {
namespace {

std::string joinPath(const std::string& dir, const std::string& file) {
  if (dir.empty()) {
    return file;
  }
  if (file.empty()) {
    return dir;
  }
  std::filesystem::path path(dir);
  path /= file;
  return path.string();
}

}  // namespace

VizRecorder& VizRecorder::instance() {
  static VizRecorder kInstance;
  return kInstance;
}

void VizRecorder::configure(const VizConfig& cfg, const std::string& outputDir,
                            std::uint64_t seed, bool ordered) {
  std::lock_guard<std::mutex> lock(mutex_);
  cfg_ = cfg;
  seed_ = seed;
  ordered_ = ordered;
  // If the trajectoriesPath in cfg is already absolute or has a directory
  // component, leave it untouched; otherwise resolve under outputDir.
  std::filesystem::path raw(cfg_.trajectoriesPath);
  if (raw.is_absolute() || raw.has_parent_path()) {
    trajectoriesPath_ = raw.string();
  } else {
    trajectoriesPath_ = joinPath(outputDir, cfg_.trajectoriesPath);
  }
  trajectories_.clear();
  indexByKey_.clear();
  flushed_ = false;
  droppedTrajectories_ = 0;
  cappedTrajectories_ = 0;
}

void VizRecorder::reset() {
  std::lock_guard<std::mutex> lock(mutex_);
  trajectories_.clear();
  indexByKey_.clear();
  flushed_ = false;
  droppedTrajectories_ = 0;
  cappedTrajectories_ = 0;
}

void VizRecorder::recordStep(int eventId, int trackId, const char* particle,
                             double xMm, double yMm, double zMm,
                             double dirX, double dirY, double dirZ,
                             double energyEv, double timeNs, double stepLengthMm,
                             const std::string& volume,
                             const std::string& material,
                             const std::string& process,
                             const std::string& interaction,
                             const std::string& boundary) {
  std::lock_guard<std::mutex> lock(mutex_);
  if (!cfg_.enable) {
    return;
  }
  const auto key = std::pair{eventId, trackId};
  auto it = indexByKey_.find(key);
  if (it == indexByKey_.end()) {
    // Sampling: deterministic stride on track ID; cap on distinct trajectories.
    const int stride = std::max(1, cfg_.sampleEveryNth);
    // We use (eventId * large_prime + trackId) so we don't bias toward early
    // tracks of every event.  Mixing in seed keeps determinism across reruns.
    const long long mix =
        static_cast<long long>(eventId) * 1315423911LL +
        static_cast<long long>(trackId) +
        static_cast<long long>(seed_ % 1000003);
    if ((mix % stride) != 0) {
      return;
    }
    auto index = trajectories_.size();
    if (cfg_.maxTrajectories > 0 && index >= static_cast<std::size_t>(cfg_.maxTrajectories)) {
      auto last = std::prev(indexByKey_.end());
      if (!ordered_ || key > last->first) {
        ++droppedTrajectories_;
        return;
      }
      // Keep the smallest sampled event/track IDs regardless of worker arrival.
      // The retained maximum can only decrease, so evicted tracks stay excluded.
      index = last->second;
      auto& evicted = trajectories_[index];
      droppedTrajectories_ += evicted.submittedPoints;
      cappedTrajectories_ -= evicted.capped ? 1 : 0;
      evicted = {};
      indexByKey_.erase(last);
    } else {
      trajectories_.emplace_back();
    }
    auto& traj = trajectories_[index];
    traj.eventId = eventId;
    traj.trackId = trackId;
    if (particle) {
      traj.particle = particle;
    }
    it = indexByKey_.emplace(key, index).first;
  }
  auto& traj = trajectories_[it->second];
  if (ordered_) {
    ++traj.submittedPoints;
  }
  if (static_cast<int>(traj.segments.size()) >= cfg_.maxSegmentsPerTrajectory) {
    if (!traj.capped) {
      traj.capped = true;
      ++cappedTrajectories_;
    }
    return;
  }
  VizTrajectorySegment seg;
  seg.x = xMm;
  seg.y = yMm;
  seg.z = zMm;
  seg.dirX = dirX;
  seg.dirY = dirY;
  seg.dirZ = dirZ;
  seg.energyEv = energyEv;
  seg.timeNs = timeNs;
  seg.stepLengthMm = stepLengthMm;
  seg.volume = volume;
  seg.material = material;
  seg.process = process;
  seg.interaction = interaction;
  seg.boundary = boundary;
  traj.segments.push_back(std::move(seg));
}

void VizRecorder::flush() {
  std::lock_guard<std::mutex> lock(mutex_);
  if (flushed_ || !cfg_.enable) {
    return;
  }
  if (trajectoriesPath_.empty()) {
    flushed_ = true;
    return;
  }
  std::ofstream out(trajectoriesPath_, std::ios::trunc);
  if (!out) {
    flushed_ = true;
    return;
  }
  const auto writeTrajectory = [&out](const VizTrajectory& traj) {
    if (traj.segments.empty()) {
      return;
    }
    nlohmann::json record;
    record["phase"] = "trajectory";
    record["event_id"] = traj.eventId;
    record["track_id"] = traj.trackId;
    record["particle"] = traj.particle;
    record["capped"] = traj.capped;
    auto points = nlohmann::json::array();
    for (const auto& seg : traj.segments) {
      nlohmann::json p;
      p["x_mm"] = seg.x;
      p["y_mm"] = seg.y;
      p["z_mm"] = seg.z;
      p["dx"] = seg.dirX;
      p["dy"] = seg.dirY;
      p["dz"] = seg.dirZ;
      p["energy_ev"] = seg.energyEv;
      p["time_ns"] = seg.timeNs;
      p["step_length_mm"] = seg.stepLengthMm;
      if (!seg.volume.empty()) {
        p["volume"] = seg.volume;
      }
      if (!seg.material.empty()) {
        p["material"] = seg.material;
      }
      if (!seg.process.empty()) {
        p["process"] = seg.process;
      }
      if (!seg.interaction.empty()) {
        p["interaction"] = seg.interaction;
      }
      if (!seg.boundary.empty()) {
        p["boundary"] = seg.boundary;
      }
      points.push_back(std::move(p));
    }
    record["points"] = std::move(points);
    out << record.dump() << '\n';
  };
  if (ordered_) {
    for (const auto& entry : indexByKey_) {
      writeTrajectory(trajectories_[entry.second]);
    }
  } else {
    for (const auto& traj : trajectories_) {
      writeTrajectory(traj);
    }
  }
  flushed_ = true;
}

int VizRecorder::recordedTrajectoryCount() const {
  std::lock_guard<std::mutex> lock(mutex_);
  return static_cast<int>(trajectories_.size());
}

int VizRecorder::recordedSegmentCount() const {
  std::lock_guard<std::mutex> lock(mutex_);
  int total = 0;
  for (const auto& t : trajectories_) {
    total += static_cast<int>(t.segments.size());
  }
  return total;
}

}  // namespace trech::sim
