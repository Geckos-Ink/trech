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

// G4VERSION_NUMBER of the first Geant4 release without the G4EmDNAPhysics
// option 1, 3, 5 and 7 constructors (removed in 11.5.0.beta, phys-ctor-em-V11-04-08).
inline constexpr int kGeant4DnaOddOptionsRemovedVersion = 1150;

// Whether the Geant4 release identified by `geant4VersionNumber` (G4VERSION_NUMBER,
// e.g. 1142 for 11.4.2) still ships the G4EmDNAPhysics constructor for `option`
// (0 = the default G4EmDNAPhysics, 1..8 = G4EmDNAPhysics_optionN). Geant4-free so
// the gate is testable without a Geant4 build.
bool dnaPhysicsOptionAvailable(int option, int geant4VersionNumber);

// Human-readable reason `option` is unavailable for that Geant4 release; empty when
// it is available.
std::string dnaPhysicsOptionUnavailableReason(int option, int geant4VersionNumber);

class DnaChemistryBridge {
public:
  explicit DnaChemistryBridge(const ChemistryConfig& cfg);

  DnaChemistryStatus Configure() const;

private:
  ChemistryConfig cfg_;
};

} // namespace trech::chem
