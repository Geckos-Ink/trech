#pragma once

#include "trech/core/Config.hpp"
#include "trech/core/RunOptions.hpp"

#include <memory>

namespace trech {
int runGeant4(const TrechConfig& cfg, RunOptions options, int argc, char** argv);

// Reuses one initialized Geant4 kernel across real-time BeamOn batches. Event
// count, seed, and lab-planner settings may change between runs; geometry,
// beam, physics, scoring, and output configuration remain kernel-bound.
class GeantLabRunner {
 public:
  GeantLabRunner(RunOptions options, int argc, char** argv);
  ~GeantLabRunner();

  GeantLabRunner(const GeantLabRunner&) = delete;
  GeantLabRunner& operator=(const GeantLabRunner&) = delete;

  // Sets the batch event count, seed and config in batchMetadata(); a scenario-backed lab
  // sets that metadata's onInit tallies and script identity before calling this.
  int run(const TrechConfig& cfg);
  bool initialized() const;
  // True when `cfg` can run on this kernel without a restart: nothing is initialized yet, or
  // its labKernelSignature matches the initialized one.
  bool accepts(const TrechConfig& cfg) const;
  // Per-batch metadata shared with the run actions (batch counts, onInit tallies, script).
  RuntimeRunMetadata& batchMetadata();

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}
