#pragma once

#include "trech/core/Config.hpp"

#include <string>

namespace trech::chem {

struct DnaChemistryStatus {
  bool enabled = false;
  bool dnaPhysics = false;
  bool chemistryStage = false;
  int dnaPhysicsOption = 0;
  int chemistryOption = 0;
  std::string model;
  std::string solver;
  std::string status;
};

class DnaChemistryBridge {
public:
  explicit DnaChemistryBridge(const ChemistryConfig& cfg);

  DnaChemistryStatus Configure() const;

private:
  ChemistryConfig cfg_;
};

} // namespace trech::chem
