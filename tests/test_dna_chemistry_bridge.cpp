#include "trech/chem/DnaChemistry.hpp"

#include <iostream>

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

  return 0;
}
