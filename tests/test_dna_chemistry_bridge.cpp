#include "trech/chem/DnaChemistry.hpp"

#include <iostream>
#include <string>

namespace {

int expect(bool condition, const char* message) {
  if (!condition) {
    std::cerr << message << "\n";
    return 1;
  }
  return 0;
}

} // namespace

int main() {
  trech::ChemistryConfig cfg;

  cfg.enable = false;
  cfg.model = "dna_opt2";
  cfg.solver = "stub";
  {
    const trech::chem::DnaChemistryStatus status = trech::chem::DnaChemistryBridge(cfg).Configure();
    if (expect(!status.enabled, "Disabled chemistry should report enabled=false.")) {
      return 1;
    }
    if (expect(status.status == "disabled", "Disabled chemistry should report status=disabled.")) {
      return 1;
    }
    if (expect(!status.dnaPhysics, "Disabled chemistry should not enable DNA physics.")) {
      return 1;
    }
  }

  cfg.enable = true;
  cfg.model = "DNA_Opt2";
  cfg.solver = "stub";
  {
    const trech::chem::DnaChemistryStatus status = trech::chem::DnaChemistryBridge(cfg).Configure();
    if (expect(status.enabled, "Enabled chemistry should report enabled=true.")) {
      return 1;
    }
    if (expect(status.dnaPhysics, "Enabled chemistry should enable DNA physics.")) {
      return 1;
    }
    if (expect(status.dnaPhysicsOption == 2, "DNA option parsing failed for DNA_Opt2.")) {
      return 1;
    }
    if (expect(!status.chemistryStage, "Stub solver should not enable chemistry stage.")) {
      return 1;
    }
  }

  cfg.model = "dna_option7";
  cfg.solver = "chem_option2";
  {
    const trech::chem::DnaChemistryStatus status = trech::chem::DnaChemistryBridge(cfg).Configure();
    if (expect(status.dnaPhysicsOption == 7, "DNA option parsing failed for dna_option7.")) {
      return 1;
    }
    if (expect(status.chemistryStage, "Non-stub solver should enable chemistry stage.")) {
      return 1;
    }
    if (expect(status.chemistryOption == 2, "Chemistry option parsing failed for chem_option2.")) {
      return 1;
    }
  }

  cfg.model = "dna";
  cfg.solver = "stubs";
  {
    const trech::chem::DnaChemistryStatus status = trech::chem::DnaChemistryBridge(cfg).Configure();
    if (expect(!status.chemistryStage, "Stub-prefixed solver should not enable chemistry stage.")) {
      return 1;
    }
  }

  // Geant4 11.5 removed G4EmDNAPhysics options 1, 3, 5 and 7; the gate must
  // keep them on 11.4.x and reject (never remap) them from 11.5 on.
  for (int option = 0; option <= 8; ++option) {
    const bool odd = option % 2 == 1;
    if (expect(trech::chem::dnaPhysicsOptionAvailable(option, 1142),
               "Every DNA option 0..8 should be available on Geant4 11.4.2.")) {
      return 1;
    }
    if (expect(trech::chem::dnaPhysicsOptionUnavailableReason(option, 1142).empty(),
               "An available option should have no unavailability reason.")) {
      return 1;
    }
    if (expect(trech::chem::dnaPhysicsOptionAvailable(option, 1150) == !odd,
               "Geant4 11.5 should keep DNA options 0/2/4/6/8 and drop 1/3/5/7.")) {
      return 1;
    }
  }
  if (expect(trech::chem::dnaPhysicsOptionUnavailableReason(7, 1150).find("removed in Geant4 11.5") !=
                 std::string::npos,
             "A removed option should explain the Geant4 11.5 removal.")) {
    return 1;
  }
  if (expect(!trech::chem::dnaPhysicsOptionAvailable(9, 1142) &&
                 !trech::chem::dnaPhysicsOptionAvailable(-1, 1142),
             "Out-of-range DNA options should be unavailable.")) {
    return 1;
  }

  return 0;
}
