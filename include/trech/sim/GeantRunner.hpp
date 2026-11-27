#pragma once

#include "trech/core/Config.hpp"
#include "trech/core/RunOptions.hpp"

#include <memory>
#include <string>

namespace trech {
// The linked Geant4 library in the run manager's format ("Geant4 version Name:
// geant4-11-04-patch-02 [MT]   (12-June-2026)"), read from G4Version.hh, so a record written
// when no kernel exists (run_failed provenance) names the same version as run_start.
std::string geant4LibraryVersion();

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
