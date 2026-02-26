#pragma once

#include "trech/core/Config.hpp"

#include <string>
#include <vector>

namespace trech::sim {

struct NuclearReactionMetrics {
  std::string name;
  bool available = false;
  bool massResolved = false;
  double qValueMeV = 0.0;
  int reactantBaryonNumber = 0;
  int productBaryonNumber = 0;
  int reactantChargeNumber = 0;
  int productChargeNumber = 0;
  bool baryonConserved = false;
  bool chargeConserved = false;
  double halfLifeYears = 0.0;
  std::vector<std::string> unresolvedParticipants;
};

struct NuclearCycleMetrics {
  std::string name;
  bool enabled = false;
  NuclearSpeciesConfig source;
  NuclearSpeciesConfig target;
  std::string phaseTransition;
  double densityDeltaGcm3 = 0.0;
  double densityRatio = 0.0;
  bool atomicMassConserved = false;
  NuclearReactionMetrics forward;
  NuclearReactionMetrics backward;
  bool cycleConsistent = false;
};

NuclearCycleMetrics analyzeNuclearCycle(const NuclearCycleConfig& cycle);

} // namespace trech::sim
