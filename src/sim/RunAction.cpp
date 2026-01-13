#include "trech/sim/RunAction.hpp"

#include "trech/core/Config.hpp"

#include "G4Run.hh"
#include "G4RunManager.hh"

namespace trech {

TrechRunAction::TrechRunAction(const TrechConfig& cfg)
    : cfg_(cfg), provenance_("trech_provenance.jsonl") {}

void TrechRunAction::BeginOfRunAction(const G4Run* /*run*/) {
  ProvenanceRecord record;
  record.phase = "run_start";
  record.configJson = configToJsonString(cfg_);
  record.configHash = hashConfigJson(record.configJson);
  if (G4RunManager::GetRunManager()) {
    record.geant4Version = G4RunManager::GetRunManager()->GetVersionString();
  }
  record.seed = cfg_.run.seed;
  provenance_.write(record);
}

void TrechRunAction::EndOfRunAction(const G4Run* /*run*/) {
  ProvenanceRecord record;
  record.phase = "run_end";
  record.configJson = configToJsonString(cfg_);
  record.configHash = hashConfigJson(record.configJson);
  if (G4RunManager::GetRunManager()) {
    record.geant4Version = G4RunManager::GetRunManager()->GetVersionString();
  }
  record.seed = cfg_.run.seed;
  provenance_.write(record);
}

} // namespace trech
