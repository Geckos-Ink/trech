#include "trech/chem/DnaChemistry.hpp"

namespace trech::chem {

DnaChemistryBridge::DnaChemistryBridge(const ChemistryConfig& cfg) : cfg_(cfg) {}

DnaChemistryStatus DnaChemistryBridge::Configure() {
  DnaChemistryStatus status;
  status.enabled = cfg_.enable;
  status.model = cfg_.model;
  status.solver = cfg_.solver;
  status.status = cfg_.enable ? "stub_configured" : "disabled";
  return status;
}

} // namespace trech::chem
