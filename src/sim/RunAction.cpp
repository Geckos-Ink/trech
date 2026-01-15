#include "trech/sim/RunAction.hpp"

#include "trech/core/Config.hpp"

#include "G4AccumulableManager.hh"
#include "G4Run.hh"
#include "G4RunManager.hh"
#include "G4SystemOfUnits.hh"

#include <filesystem>
#include <fstream>

#include <nlohmann/json.hpp>

namespace trech {
namespace {

std::string joinPath(const std::string& dir, const std::string& file) {
  if (dir.empty()) {
    return file;
  }
  std::filesystem::path path(dir);
  path /= file;
  return path.string();
}

} // namespace

TrechRunAction::TrechRunAction(const TrechConfig& cfg, const RunOptions& options)
    : cfg_(cfg),
      options_(options),
      provenance_(joinPath(options.outputDir, "trech_provenance.jsonl")),
      scoresPath_(joinPath(options.outputDir, "trech_scores.jsonl")),
      totalEdep_(0.0),
      opticalPhotonSteps_(0),
      opticalPhotonTracks_(0),
      opticalPhotonTrackLength_(0.0) {
  G4AccumulableManager::Instance()->RegisterAccumulable(totalEdep_);
  G4AccumulableManager::Instance()->RegisterAccumulable(opticalPhotonSteps_);
  G4AccumulableManager::Instance()->RegisterAccumulable(opticalPhotonTracks_);
  G4AccumulableManager::Instance()->RegisterAccumulable(opticalPhotonTrackLength_);
}

void TrechRunAction::BeginOfRunAction(const G4Run* /*run*/) {
  G4AccumulableManager::Instance()->Reset();

  ProvenanceRecord record;
  record.phase = "run_start";
  record.configJson = configToJsonString(cfg_);
  record.configHash = hashConfigJson(record.configJson);
  if (G4RunManager::GetRunManager()) {
    record.geant4Version = G4RunManager::GetRunManager()->GetVersionString();
  }
  record.physicsList = options_.physicsList;
  record.rngEngine = options_.rngEngine;
  record.cliArgs = options_.cliArgs;
  record.macroPath = options_.macroPath;
  record.outputDir = options_.outputDir;
  record.nEvents = cfg_.run.nEvents;
  record.seed = cfg_.run.seed;
  provenance_.write(record);
}

void TrechRunAction::EndOfRunAction(const G4Run* /*run*/) {
  auto* accumulables = G4AccumulableManager::Instance();
  accumulables->Merge();

  const auto totalEdepMeV = totalEdep_.GetValue() / MeV;
  const auto photonSteps = opticalPhotonSteps_.GetValue();
  const auto photonTracks = opticalPhotonTracks_.GetValue();
  const auto photonTrackLengthMm = opticalPhotonTrackLength_.GetValue() / mm;
  nlohmann::json scores;
  scores["phase"] = "run_end";
  scores["total_edep_mev"] = totalEdepMeV;
  scores["optics_enabled"] = cfg_.optics.enable;
  scores["optical_photon_tracks"] = photonTracks;
  scores["optical_photon_steps"] = photonSteps;
  scores["optical_photon_track_length_mm"] = photonTrackLengthMm;
  scores["n_events"] = cfg_.run.nEvents;
  scores["seed"] = cfg_.run.seed;
  scores["physics_list"] = options_.physicsList;
  scores["multiscale_enabled"] = cfg_.multiscale.enable;
  scores["multiscale_method"] = cfg_.multiscale.method;
  scores["multiscale_mode"] = cfg_.multiscale.mode;

  std::ofstream scoreOut(scoresPath_, std::ios::app);
  scoreOut << scores.dump() << '\n';

  ProvenanceRecord record;
  record.phase = "run_end";
  record.configJson = configToJsonString(cfg_);
  record.configHash = hashConfigJson(record.configJson);
  if (G4RunManager::GetRunManager()) {
    record.geant4Version = G4RunManager::GetRunManager()->GetVersionString();
  }
  record.physicsList = options_.physicsList;
  record.rngEngine = options_.rngEngine;
  record.cliArgs = options_.cliArgs;
  record.macroPath = options_.macroPath;
  record.outputDir = options_.outputDir;
  record.nEvents = cfg_.run.nEvents;
  record.seed = cfg_.run.seed;
  provenance_.write(record);
}

void TrechRunAction::AddEnergyDeposit(G4double edep) {
  totalEdep_ += edep;
}

void TrechRunAction::AddOpticalPhotonStep(G4double stepLength) {
  opticalPhotonSteps_ += 1;
  opticalPhotonTrackLength_ += stepLength;
}

void TrechRunAction::AddOpticalPhotonTrack() {
  opticalPhotonTracks_ += 1;
}

} // namespace trech
