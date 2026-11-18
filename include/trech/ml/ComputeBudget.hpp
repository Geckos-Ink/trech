#pragma once

#include <cstddef>
#include <string>

#include <nlohmann/json.hpp>

namespace trech::ml {

// The computational context a learned model is created in. Model capacity
// (buffered rows, domain count, basis degree, residual network width and
// optimisation steps) is derived from it, so the same scenario builds a model
// sized to the machine instead of a fixed size chosen for another one.
//
// Results that depend on the budget are only reproducible under the same
// budget: every consumer records the resolved budget beside its output, and
// TRECH_COMPUTE_BUDGET (a JSON object or a path to one) pins it.
struct ComputeBudget {
  std::size_t hardwareThreads = 1;   // std::thread::hardware_concurrency
  std::size_t torchThreads = 1;      // LibTorch intra-op threads
  double memoryBytes = 0.0;          // physical memory, 0 when unknown
  double gflops = 0.0;               // measured double-precision matmul rate
  std::string source = "probe";      // probe | env | override
  // Optional user caps applied after the probe (0 = no cap).
  double memoryFraction = 0.05;      // share of memory a single learner may hold
  double secondsPerCall = 0.05;      // wall-time target of one learner update

  nlohmann::json toJson() const;
  static ComputeBudget fromJson(const nlohmann::json& value);
};

// Capacity a learned-domain model may use, derived from a ComputeBudget.
struct LearnerCapacity {
  std::size_t maxDomains = 16;       // leaves of the domain tree
  std::size_t bufferRows = 4096;     // recent rows kept per domain
  std::size_t splitCandidates = 32;  // thresholds tested per direction
  int basisDegree = 2;               // 1 affine, 2 full quadratic
  std::size_t residualHidden = 0;    // residual MLP width, 0 disables it
  std::size_t residualSteps = 0;     // optimiser steps per update
  std::size_t specialistWidth = 32;  // offline specialist hidden width
  std::size_t specialistEpochs = 600;

  nlohmann::json toJson() const;
};

// Probe the host once per process (cached). Honors TRECH_COMPUTE_BUDGET.
const ComputeBudget& hostComputeBudget();

// Capacity for a learner with `features` inputs and `targets` outputs.
LearnerCapacity learnerCapacity(const ComputeBudget& budget, std::size_t features,
                                std::size_t targets);

}  // namespace trech::ml
