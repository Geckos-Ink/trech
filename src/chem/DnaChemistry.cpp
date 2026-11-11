#include "trech/chem/DnaChemistry.hpp"

#include <algorithm>
#include <cctype>
#include <string>

namespace trech::chem {
namespace {

std::string toLowerCopy(const std::string& input) {
  std::string output = input;
  std::transform(output.begin(), output.end(), output.begin(), [](unsigned char ch) {
    return static_cast<char>(std::tolower(ch));
  });
  return output;
}

int parseOptionNumber(const std::string& input, int maxOption) {
  const std::string tokens[] = {"opt", "option"};
  for (const auto& token : tokens) {
    std::size_t pos = input.find(token);
    while (pos != std::string::npos) {
      std::size_t idx = pos + token.size();
      int value = 0;
      bool hasDigit = false;
      while (idx < input.size()) {
        const unsigned char ch = static_cast<unsigned char>(input[idx]);
        if (!std::isdigit(ch)) {
          break;
        }
        hasDigit = true;
        value = (value * 10) + (static_cast<int>(ch) - static_cast<int>('0'));
        idx += 1;
      }
      if (hasDigit && value >= 1 && value <= maxOption) {
        return value;
      }
      pos = input.find(token, pos + token.size());
    }
  }
  return 0;
}

bool isStubSolver(const std::string& solver) {
  if (solver.empty()) {
    return true;
  }
  if (solver.rfind("stub", 0) == 0) {
    return true;
  }
  return solver == "none" || solver == "off" || solver == "disabled";
}

} // namespace

bool dnaPhysicsOptionAvailable(int option, int geant4VersionNumber) {
  if (option < 0 || option > 8) {
    return false;
  }
  const bool oddOption = option == 1 || option == 3 || option == 5 || option == 7;
  return !(oddOption && geant4VersionNumber >= kGeant4DnaOddOptionsRemovedVersion);
}

std::string dnaPhysicsOptionUnavailableReason(int option, int geant4VersionNumber) {
  if (dnaPhysicsOptionAvailable(option, geant4VersionNumber)) {
    return {};
  }
  if (option < 0 || option > 8) {
    return "Geant4-DNA physics option " + std::to_string(option) +
           " does not exist (valid: 0 for G4EmDNAPhysics, 1..8)";
  }
  return "Geant4-DNA physics option " + std::to_string(option) +
         " (G4EmDNAPhysics_option" + std::to_string(option) +
         ") was removed in Geant4 11.5; this build links G4VERSION_NUMBER " +
         std::to_string(geant4VersionNumber) +
         ". Choose DNA_Opt2, DNA_Opt4, DNA_Opt6, DNA_Opt8 or the default "
         "G4EmDNAPhysics; TRECH does not substitute another option because that "
         "would change the physics behind the recorded config";
}

DnaChemistryBridge::DnaChemistryBridge(const ChemistryConfig& cfg) : cfg_(cfg) {}

DnaChemistryStatus DnaChemistryBridge::Configure() const {
  DnaChemistryStatus status;
  status.enabled = cfg_.enable;
  status.model = cfg_.model;
  status.solver = cfg_.solver;
  if (!cfg_.enable) {
    status.status = "disabled";
    return status;
  }

  status.dnaPhysics = true;
  status.dnaPhysicsOption = parseOptionNumber(toLowerCopy(cfg_.model), 8);

  const auto solver = toLowerCopy(cfg_.solver);
  if (!isStubSolver(solver)) {
    status.chemistryStage = true;
    status.chemistryOption = parseOptionNumber(solver, 3);
  }

  status.status = status.chemistryStage ? "dna_physics_chemistry" : "dna_physics";
  return status;
}

} // namespace trech::chem
