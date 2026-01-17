#include "trech/sim/RunAction.hpp"

#include "trech/core/Config.hpp"
#include "trech/ml/Stratifier.hpp"

#include "G4AccumulableManager.hh"
#include "G4Run.hh"
#include "G4RunManager.hh"
#include "G4SystemOfUnits.hh"
#include "G4Threading.hh"
#include "G4Version.hh"

#include <filesystem>
#include <fstream>
#include <string>

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

std::string trimCopy(const std::string& input) {
  const auto start = input.find_first_not_of(" \t\n\r");
  if (start == std::string::npos) {
    return "";
  }
  const auto end = input.find_last_not_of(" \t\n\r");
  return input.substr(start, end - start + 1);
}

std::string resolveGeant4Version() {
  std::string version;
  if (auto* manager = G4RunManager::GetRunManager()) {
    version = manager->GetVersionString();
  }
  version = trimCopy(version);
  if (!version.empty()) {
    return version;
  }

  std::string fallback = trimCopy(G4Version);
  if (!fallback.empty()) {
    return fallback;
  }

#ifdef G4VERSION_TAG
  std::string tag = trimCopy(G4VERSION_TAG);
  if (!tag.empty()) {
    return tag;
  }
#endif

#ifdef G4VERSION_NUMBER
  return std::to_string(G4VERSION_NUMBER);
#else
  return "unknown";
#endif
}

bool isMasterRunAction() {
  return G4Threading::IsMasterThread();
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
      opticalPhotonTrackLength_(0.0),
      stratifyTotalCount_(0),
      stratifyPredictableCount_(0),
      stratifyExceptionalCount_(0),
      stratifyUnclassifiedCount_(0),
      stratifyThresholdCount_(0),
      stratifyModelCount_(0),
      stratifySourceUnknownCount_(0) {
  auto* manager = G4AccumulableManager::Instance();
  manager->Register(totalEdep_);
  manager->Register(opticalPhotonSteps_);
  manager->Register(opticalPhotonTracks_);
  manager->Register(opticalPhotonTrackLength_);
  manager->Register(stratifyTotalCount_);
  manager->Register(stratifyPredictableCount_);
  manager->Register(stratifyExceptionalCount_);
  manager->Register(stratifyUnclassifiedCount_);
  manager->Register(stratifyThresholdCount_);
  manager->Register(stratifyModelCount_);
  manager->Register(stratifySourceUnknownCount_);
}

void TrechRunAction::BeginOfRunAction(const G4Run* /*run*/) {
  G4AccumulableManager::Instance()->Reset();
  if (!isMasterRunAction()) {
    return;
  }

  ProvenanceRecord record;
  record.phase = "run_start";
  record.configJson = configToJsonString(cfg_);
  record.configHash = hashConfigJson(record.configJson);
  record.geant4Version = resolveGeant4Version();
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
  if (!isMasterRunAction()) {
    return;
  }

  const auto totalEdepMeV = totalEdep_.GetValue() / MeV;
  const auto photonSteps = opticalPhotonSteps_.GetValue();
  const auto photonTracks = opticalPhotonTracks_.GetValue();
  const auto photonTrackLengthMm = opticalPhotonTrackLength_.GetValue() / mm;
  const auto stratifyTotal = stratifyTotalCount_.GetValue();
  const auto stratifyPredictable = stratifyPredictableCount_.GetValue();
  const auto stratifyExceptional = stratifyExceptionalCount_.GetValue();
  const auto stratifyUnclassified = stratifyUnclassifiedCount_.GetValue();
  const auto stratifyThreshold = stratifyThresholdCount_.GetValue();
  const auto stratifyModel = stratifyModelCount_.GetValue();
  const auto stratifyUnknown = stratifySourceUnknownCount_.GetValue();
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
  scores["chemistry_enabled"] = cfg_.chemistry.enable;
  scores["chemistry_model"] = cfg_.chemistry.model;
  scores["chemistry_solver"] = cfg_.chemistry.solver;
  scores["dna_physics_enabled"] = options_.dnaPhysicsEnabled;
  scores["dna_physics_option"] = options_.dnaPhysicsOption;
  scores["dna_chemistry_enabled"] = options_.dnaChemistryEnabled;
  scores["dna_chemistry_option"] = options_.dnaChemistryOption;
  scores["stratify_enabled"] = cfg_.stratify.enable;
  scores["stratify_total_count"] = stratifyTotal;
  scores["stratify_predictable_count"] = stratifyPredictable;
  scores["stratify_exceptional_count"] = stratifyExceptional;
  scores["stratify_unclassified_count"] = stratifyUnclassified;
  scores["stratify_source_thresholds_count"] = stratifyThreshold;
  scores["stratify_source_model_count"] = stratifyModel;
  scores["stratify_source_unknown_count"] = stratifyUnknown;

  std::ofstream scoreOut(scoresPath_, std::ios::app);
  scoreOut << scores.dump() << '\n';

  ProvenanceRecord record;
  record.phase = "run_end";
  record.configJson = configToJsonString(cfg_);
  record.configHash = hashConfigJson(record.configJson);
  record.geant4Version = resolveGeant4Version();
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

void TrechRunAction::AddStratifyResult(const ml::StratifyResult& result) {
  if (!cfg_.stratify.enable) {
    return;
  }
  stratifyTotalCount_ += 1;
  if (result.label == cfg_.stratify.labelPredictable) {
    stratifyPredictableCount_ += 1;
  } else if (result.label == cfg_.stratify.labelExceptional) {
    stratifyExceptionalCount_ += 1;
  } else {
    stratifyUnclassifiedCount_ += 1;
  }

  if (result.source == "thresholds") {
    stratifyThresholdCount_ += 1;
  } else if (result.source == "model") {
    stratifyModelCount_ += 1;
  } else {
    stratifySourceUnknownCount_ += 1;
  }
}

} // namespace trech
