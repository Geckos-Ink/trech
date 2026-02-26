#include "trech/sim/RunAction.hpp"

#include "trech/core/Config.hpp"
#include "trech/js/JsRuntime.hpp"
#include "trech/ml/Stratifier.hpp"
#include "trech/sim/NuclearCycleAnalyzer.hpp"

#include "G4AccumulableManager.hh"
#include "G4Run.hh"
#include "G4RunManager.hh"
#include "G4SystemOfUnits.hh"
#include "G4Threading.hh"
#include "G4Version.hh"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <string>
#include <utility>
#include <vector>

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

std::string normalizeDeterminismMode(std::string mode) {
  std::transform(mode.begin(), mode.end(), mode.begin(),
                 [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
  if (mode == "predictive") {
    return mode;
  }
  return "strict";
}

std::string normalizeHookName(std::string hook) {
  std::string normalized;
  normalized.reserve(hook.size());
  for (char ch : hook) {
    const auto uc = static_cast<unsigned char>(ch);
    if (std::isalnum(uc)) {
      normalized.push_back(static_cast<char>(std::tolower(uc)));
    }
  }
  return normalized;
}

struct SystemVolume {
  double volumeMm3 = 0.0;
  std::string source = "unknown";
};

SystemVolume resolveSystemVolume(const TrechConfig& cfg) {
  if (!cfg.system.enable) {
    return {0.0, "disabled"};
  }
  if (cfg.system.volumeMm3 > 0.0) {
    return {cfg.system.volumeMm3, "config"};
  }
  if (cfg.detector.mediumBoxMm > 0.0) {
    const auto side = std::min(cfg.detector.mediumBoxMm, cfg.detector.worldSizeMm);
    if (side > 0.0) {
      return {side * side * side, "medium_box"};
    }
  }
  if (cfg.detector.worldSizeMm > 0.0) {
    const auto side = cfg.detector.worldSizeMm;
    return {side * side * side, "world"};
  }
  return {0.0, "unknown"};
}

nlohmann::json parseEmitPayload(const std::string& raw) {
  if (raw.empty()) {
    return nullptr;
  }
  try {
    return nlohmann::json::parse(raw);
  } catch (const std::exception&) {
    return raw;
  }
}

nlohmann::json nuclearReactionToJson(const sim::NuclearReactionMetrics& reaction) {
  nlohmann::json value;
  value["name"] = reaction.name;
  value["available"] = reaction.available;
  value["mass_resolved"] = reaction.massResolved;
  value["q_value_mev"] = reaction.qValueMeV;
  value["reactant_baryon_number"] = reaction.reactantBaryonNumber;
  value["product_baryon_number"] = reaction.productBaryonNumber;
  value["reactant_charge_number"] = reaction.reactantChargeNumber;
  value["product_charge_number"] = reaction.productChargeNumber;
  value["baryon_conserved"] = reaction.baryonConserved;
  value["charge_conserved"] = reaction.chargeConserved;
  if (reaction.halfLifeYears > 0.0) {
    value["half_life_years"] = reaction.halfLifeYears;
  }
  if (!reaction.unresolvedParticipants.empty()) {
    value["unresolved_participants"] = reaction.unresolvedParticipants;
  }
  return value;
}

nlohmann::json nuclearCycleToJson(const sim::NuclearCycleMetrics& cycle) {
  nlohmann::json value;
  value["name"] = cycle.name;
  value["enabled"] = cycle.enabled;
  value["source"] = {
      {"symbol", cycle.source.symbol},
      {"material", cycle.source.material},
      {"z", cycle.source.z},
      {"a", cycle.source.a},
      {"phase", cycle.source.phase},
      {"density_gcm3", cycle.source.densityGcm3},
  };
  value["target"] = {
      {"symbol", cycle.target.symbol},
      {"material", cycle.target.material},
      {"z", cycle.target.z},
      {"a", cycle.target.a},
      {"phase", cycle.target.phase},
      {"density_gcm3", cycle.target.densityGcm3},
  };
  value["phase_transition"] = cycle.phaseTransition;
  value["density_delta_gcm3"] = cycle.densityDeltaGcm3;
  value["density_ratio"] = cycle.densityRatio;
  value["atomic_mass_conserved"] = cycle.atomicMassConserved;
  value["forward"] = nuclearReactionToJson(cycle.forward);
  value["backward"] = nuclearReactionToJson(cycle.backward);
  value["cycle_consistent"] = cycle.cycleConsistent;
  return value;
}

} // namespace

TrechRunAction::TrechRunAction(const TrechConfig& cfg, const RunOptions& options)
    : cfg_(cfg),
      options_(options),
      provenance_(joinPath(options.outputDir, "trech_provenance.jsonl")),
      scoresPath_(joinPath(options.outputDir, "trech_scores.jsonl")),
      hookEmitsPath_(joinPath(options.outputDir, "trech_hook_emits.jsonl")),
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
      stratifySourceUnknownCount_(0),
      eventSummaryCount_(0),
      eventEdepSumMeV_(0.0),
      eventEdepSqSumMeV2_(0.0),
      hookOnInitCount_(0),
      hookOnRunStartCount_(0),
      hookOnEventStartCount_(0),
      hookOnStepRawCount_(0),
      hookOnEventEndCount_(0),
      hookOnRunEndCount_(0),
      hookPatchCount_(0),
      hookEmitCount_(0),
      hookEmitDroppedCount_(0) {
  auto* manager = G4AccumulableManager::Instance();
  manager->Register(totalEdep_);
  for (const auto& volume : cfg_.geometry.volumes) {
    if (!volume.scoreEdep || volume.name.empty()) {
      continue;
    }
    if (volumeScoreIndex_.find(volume.name) != volumeScoreIndex_.end()) {
      continue;
    }
    VolumeScore score;
    score.name = volume.name;
    score.edep = std::make_unique<G4Accumulable<G4double>>(0.0);
    volumeScoreIndex_[score.name] = volumeScores_.size();
    volumeScores_.push_back(std::move(score));
    manager->Register(*volumeScores_.back().edep);
  }
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
  manager->Register(eventSummaryCount_);
  manager->Register(eventEdepSumMeV_);
  manager->Register(eventEdepSqSumMeV2_);
  manager->Register(hookOnInitCount_);
  manager->Register(hookOnRunStartCount_);
  manager->Register(hookOnEventStartCount_);
  manager->Register(hookOnStepRawCount_);
  manager->Register(hookOnEventEndCount_);
  manager->Register(hookOnRunEndCount_);
  manager->Register(hookPatchCount_);
  manager->Register(hookEmitCount_);
  manager->Register(hookEmitDroppedCount_);

  hookMaxStepCallbacks_ = std::max(0, cfg_.hooks.maxStepCallbacks);
  hookMaxEmitsPerCallback_ = std::max(0, cfg_.hooks.maxEmitsPerCallback);
  hookMaxEmitPayloadBytes_ = std::max(0, cfg_.hooks.maxEmitPayloadBytes);
  for (const auto& rawName : cfg_.hooks.registered) {
    const auto hookName = normalizeHookName(rawName);
    if (hookName == "oninit") {
      hookOnInitEnabled_ = true;
      continue;
    }
    if (hookName == "onrunstart") {
      hookOnRunStartEnabled_ = true;
      continue;
    }
    if (hookName == "oneventstart") {
      hookOnEventStartEnabled_ = true;
      continue;
    }
    if (hookName == "onstep") {
      hookOnStepEnabled_ = true;
      continue;
    }
    if (hookName == "oneventend") {
      hookOnEventEndEnabled_ = true;
      continue;
    }
    if (hookName == "onrunend") {
      hookOnRunEndEnabled_ = true;
      continue;
    }
    if (!hookName.empty()) {
      ++hookUnknownRegisteredCount_;
    }
  }
  hooksEnabled_ = hookOnInitEnabled_ || hookOnRunStartEnabled_ ||
                  hookOnEventStartEnabled_ || hookOnStepEnabled_ ||
                  hookOnEventEndEnabled_ || hookOnRunEndEnabled_;
}

void TrechRunAction::BeginOfRunAction(const G4Run* /*run*/) {
  G4AccumulableManager::Instance()->Reset();
  if (!isMasterRunAction()) {
    return;
  }
  RecordHookOnInit();
  RecordHookOnRunStart();
  DispatchHook("onRunStart");

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
  record.determinismMode = normalizeDeterminismMode(cfg_.determinism.mode);
  record.predictiveMode = record.determinismMode == "predictive";
  record.stratifyEnabled = cfg_.stratify.enable;
  record.stratifyModelPath = cfg_.stratify.modelPath;
  record.stratifyModelHash = hashFileContents(cfg_.stratify.modelPath);
  record.stratifyModelHashAvailable = !record.stratifyModelHash.empty();
  record.hooksEnabled = hooksEnabled_;
  record.hooksRegistered = cfg_.hooks.registered;
  record.hooksGuardrailMaxStepCallbacks = hookMaxStepCallbacks_;
  record.hooksGuardrailMaxEmitsPerCallback = hookMaxEmitsPerCallback_;
  record.hooksGuardrailMaxEmitPayloadBytes = hookMaxEmitPayloadBytes_;
  record.hookOnInitCount = hookOnInitCount_.GetValue();
  record.hookOnRunStartCount = hookOnRunStartCount_.GetValue();
  record.hookOnEventStartCount = hookOnEventStartCount_.GetValue();
  record.hookOnStepCount = std::min(hookOnStepRawCount_.GetValue(), hookMaxStepCallbacks_);
  record.hookOnStepRawCount = hookOnStepRawCount_.GetValue();
  record.hookOnStepDroppedCount =
      std::max(0, hookOnStepRawCount_.GetValue() - hookMaxStepCallbacks_);
  record.hookOnEventEndCount = hookOnEventEndCount_.GetValue();
  record.hookOnRunEndCount = hookOnRunEndCount_.GetValue();
  record.hookUnknownRegisteredCount = hookUnknownRegisteredCount_;
  record.hookPatchCount = options_.hookInitPatchCount + hookPatchCount_.GetValue();
  record.hookEmitCount = options_.hookInitEmitCount + hookEmitCount_.GetValue();
  record.hookEmitDroppedCount =
      options_.hookInitEmitDroppedCount + hookEmitDroppedCount_.GetValue();
  record.nuclearEnabled = cfg_.nuclear.enable;
  record.nuclearCycleCount = static_cast<int>(cfg_.nuclear.cycles.size());
  record.nuclearConsistentCycleCount = 0;
  provenance_.write(record);
}

void TrechRunAction::EndOfRunAction(const G4Run* /*run*/) {
  auto* accumulables = G4AccumulableManager::Instance();
  if (isMasterRunAction()) {
    RecordHookOnRunEnd();
    DispatchHook("onRunEnd");
  }
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
  const auto hookOnInitCount = hookOnInitCount_.GetValue();
  const auto hookOnRunStartCount = hookOnRunStartCount_.GetValue();
  const auto hookOnEventStartCount = hookOnEventStartCount_.GetValue();
  const auto hookOnStepRawCount = hookOnStepRawCount_.GetValue();
  const auto hookOnEventEndCount = hookOnEventEndCount_.GetValue();
  const auto hookOnRunEndCount = hookOnRunEndCount_.GetValue();
  const auto hookOnStepCount = std::min(hookOnStepRawCount, hookMaxStepCallbacks_);
  const auto hookOnStepDroppedCount =
      std::max(0, hookOnStepRawCount - hookMaxStepCallbacks_);
  const auto hookPatchCount =
      options_.hookInitPatchCount + hookPatchCount_.GetValue();
  const auto hookEmitCount =
      options_.hookInitEmitCount + hookEmitCount_.GetValue();
  const auto hookEmitDroppedCount =
      options_.hookInitEmitDroppedCount + hookEmitDroppedCount_.GetValue();
  const auto eventCount = eventSummaryCount_.GetValue();
  const auto eventEdepSumMeV = eventEdepSumMeV_.GetValue();
  const auto eventEdepSqSumMeV2 = eventEdepSqSumMeV2_.GetValue();
  double eventEdepMeanMeV = 0.0;
  double eventEdepVarianceMeV2 = 0.0;
  double eventEdepStddevMeV = 0.0;
  if (eventCount > 0) {
    eventEdepMeanMeV = eventEdepSumMeV / static_cast<double>(eventCount);
    eventEdepVarianceMeV2 =
        std::max(0.0, (eventEdepSqSumMeV2 / static_cast<double>(eventCount)) -
                           (eventEdepMeanMeV * eventEdepMeanMeV));
    eventEdepStddevMeV = std::sqrt(eventEdepVarianceMeV2);
  }
  const auto determinismMode = normalizeDeterminismMode(cfg_.determinism.mode);
  const bool predictiveMode = determinismMode == "predictive";
  const auto stratifyModelHash = hashFileContents(cfg_.stratify.modelPath);
  const auto systemVolume = resolveSystemVolume(cfg_);
  double systemEdepDensity = 0.0;
  double systemOpticalTrackLengthDensity = 0.0;
  double systemOpticalTracksDensity = 0.0;
  double systemOpticalStepsDensity = 0.0;
  if (systemVolume.volumeMm3 > 0.0) {
    systemEdepDensity = totalEdepMeV / systemVolume.volumeMm3;
    systemOpticalTrackLengthDensity = photonTrackLengthMm / systemVolume.volumeMm3;
    systemOpticalTracksDensity = static_cast<double>(photonTracks) / systemVolume.volumeMm3;
    systemOpticalStepsDensity = static_cast<double>(photonSteps) / systemVolume.volumeMm3;
  }
  std::vector<sim::NuclearCycleMetrics> nuclearCycles;
  int nuclearConsistentCycleCount = 0;
  if (cfg_.nuclear.enable) {
    nuclearCycles.reserve(cfg_.nuclear.cycles.size());
    for (const auto& cycle : cfg_.nuclear.cycles) {
      auto metrics = sim::analyzeNuclearCycle(cycle);
      if (metrics.cycleConsistent) {
        ++nuclearConsistentCycleCount;
      }
      nuclearCycles.push_back(std::move(metrics));
    }
  }
  nlohmann::json scores;
  scores["phase"] = "run_end";
  scores["total_edep_mev"] = totalEdepMeV;
  if (!volumeScores_.empty()) {
    nlohmann::json volumeEdep = nlohmann::json::object();
    for (const auto& volume : volumeScores_) {
      if (volume.edep) {
        volumeEdep[volume.name] = volume.edep->GetValue() / MeV;
      }
    }
    if (!volumeEdep.empty()) {
      scores["volume_edep_mev"] = volumeEdep;
    }
  }
  scores["optics_enabled"] = cfg_.optics.enable;
  scores["optical_photon_tracks"] = photonTracks;
  scores["optical_photon_steps"] = photonSteps;
  scores["optical_photon_track_length_mm"] = photonTrackLengthMm;
  scores["n_events"] = cfg_.run.nEvents;
  scores["seed"] = cfg_.run.seed;
  scores["physics_list"] = options_.physicsList;
  scores["determinism_mode"] = determinismMode;
  scores["predictive_mode"] = predictiveMode;
  scores["hooks_enabled"] = hooksEnabled_;
  scores["hooks_registered"] = cfg_.hooks.registered;
  scores["hooks_guardrail_max_step_callbacks"] = hookMaxStepCallbacks_;
  scores["hooks_guardrail_max_emits_per_callback"] = hookMaxEmitsPerCallback_;
  scores["hooks_guardrail_max_emit_payload_bytes"] = hookMaxEmitPayloadBytes_;
  scores["hook_on_init_count"] = hookOnInitCount;
  scores["hook_on_run_start_count"] = hookOnRunStartCount;
  scores["hook_on_event_start_count"] = hookOnEventStartCount;
  scores["hook_on_step_count"] = hookOnStepCount;
  scores["hook_on_step_raw_count"] = hookOnStepRawCount;
  scores["hook_on_step_dropped_count"] = hookOnStepDroppedCount;
  scores["hook_on_event_end_count"] = hookOnEventEndCount;
  scores["hook_on_run_end_count"] = hookOnRunEndCount;
  scores["hook_unknown_registered_count"] = hookUnknownRegisteredCount_;
  scores["hook_patch_count"] = hookPatchCount;
  scores["hook_emit_count"] = hookEmitCount;
  scores["hook_emit_dropped_count"] = hookEmitDroppedCount;
  scores["system_enabled"] = cfg_.system.enable;
  scores["system_mode"] = cfg_.system.mode;
  scores["system_frame"] = cfg_.system.frame;
  scores["system_ensemble"] = cfg_.system.ensemble;
  scores["system_volume_mm3"] = systemVolume.volumeMm3;
  scores["system_volume_source"] = systemVolume.source;
  scores["system_edep_mev_per_mm3"] = systemEdepDensity;
  scores["system_optical_track_length_mm_per_mm3"] = systemOpticalTrackLengthDensity;
  scores["system_optical_tracks_per_mm3"] = systemOpticalTracksDensity;
  scores["system_optical_steps_per_mm3"] = systemOpticalStepsDensity;
  scores["system_event_count"] = eventCount;
  scores["system_event_edep_mean_mev"] = eventEdepMeanMeV;
  scores["system_event_edep_variance_mev2"] = eventEdepVarianceMeV2;
  scores["system_event_edep_stddev_mev"] = eventEdepStddevMeV;
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
  scores["nuclear_enabled"] = cfg_.nuclear.enable;
  scores["nuclear_cycle_count"] = cfg_.nuclear.enable
                                      ? static_cast<int>(nuclearCycles.size())
                                      : 0;
  scores["nuclear_consistent_cycle_count"] =
      cfg_.nuclear.enable ? nuclearConsistentCycleCount : 0;
  if (!nuclearCycles.empty()) {
    auto cycles = nlohmann::json::array();
    for (const auto& cycle : nuclearCycles) {
      cycles.push_back(nuclearCycleToJson(cycle));
    }
    scores["nuclear_cycles"] = cycles;
  }
  scores["stratify_enabled"] = cfg_.stratify.enable;
  scores["stratify_total_count"] = stratifyTotal;
  scores["stratify_predictable_count"] = stratifyPredictable;
  scores["stratify_exceptional_count"] = stratifyExceptional;
  scores["stratify_unclassified_count"] = stratifyUnclassified;
  scores["stratify_source_thresholds_count"] = stratifyThreshold;
  scores["stratify_source_model_count"] = stratifyModel;
  scores["stratify_source_unknown_count"] = stratifyUnknown;
  scores["stratify_model_path"] = cfg_.stratify.modelPath;
  scores["stratify_model_hash"] = stratifyModelHash;
  scores["stratify_model_hash_available"] = !stratifyModelHash.empty();

  if (options_.hookRuntime) {
    auto emitted = options_.hookRuntime->takeEmittedRecords();
    if (!emitted.empty()) {
      std::ofstream emitsOut(hookEmitsPath_, std::ios::app);
      for (const auto& emit : emitted) {
        nlohmann::json emitRecord;
        emitRecord["phase"] = "hook_emit";
        emitRecord["hook"] = emit.hook;
        emitRecord["event_id"] = emit.eventId;
        emitRecord["step_index"] = emit.stepIndex;
        emitRecord["tag"] = emit.tag;
        emitRecord["payload"] = parseEmitPayload(emit.payloadJson);
        emitsOut << emitRecord.dump() << '\n';
      }
    }
  }

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
  record.determinismMode = determinismMode;
  record.predictiveMode = predictiveMode;
  record.stratifyEnabled = cfg_.stratify.enable;
  record.stratifyModelPath = cfg_.stratify.modelPath;
  record.stratifyModelHash = stratifyModelHash;
  record.stratifyModelHashAvailable = !record.stratifyModelHash.empty();
  record.stratifyTotalCount = stratifyTotal;
  record.stratifyPredictableCount = stratifyPredictable;
  record.stratifyExceptionalCount = stratifyExceptional;
  record.stratifyUnclassifiedCount = stratifyUnclassified;
  record.stratifySourceThresholdsCount = stratifyThreshold;
  record.stratifySourceModelCount = stratifyModel;
  record.stratifySourceUnknownCount = stratifyUnknown;
  record.hooksEnabled = hooksEnabled_;
  record.hooksRegistered = cfg_.hooks.registered;
  record.hooksGuardrailMaxStepCallbacks = hookMaxStepCallbacks_;
  record.hooksGuardrailMaxEmitsPerCallback = hookMaxEmitsPerCallback_;
  record.hooksGuardrailMaxEmitPayloadBytes = hookMaxEmitPayloadBytes_;
  record.hookOnInitCount = hookOnInitCount;
  record.hookOnRunStartCount = hookOnRunStartCount;
  record.hookOnEventStartCount = hookOnEventStartCount;
  record.hookOnStepCount = hookOnStepCount;
  record.hookOnStepRawCount = hookOnStepRawCount;
  record.hookOnStepDroppedCount = hookOnStepDroppedCount;
  record.hookOnEventEndCount = hookOnEventEndCount;
  record.hookOnRunEndCount = hookOnRunEndCount;
  record.hookUnknownRegisteredCount = hookUnknownRegisteredCount_;
  record.hookPatchCount = hookPatchCount;
  record.hookEmitCount = hookEmitCount;
  record.hookEmitDroppedCount = hookEmitDroppedCount;
  record.nuclearEnabled = cfg_.nuclear.enable;
  record.nuclearCycleCount = cfg_.nuclear.enable
                                 ? static_cast<int>(nuclearCycles.size())
                                 : 0;
  record.nuclearConsistentCycleCount =
      cfg_.nuclear.enable ? nuclearConsistentCycleCount : 0;
  record.systemEventCount = eventCount;
  record.systemEventEdepMeanMeV = eventEdepMeanMeV;
  record.systemEventEdepVarianceMeV2 = eventEdepVarianceMeV2;
  record.systemEventEdepStddevMeV = eventEdepStddevMeV;
  provenance_.write(record);
}

void TrechRunAction::AddEnergyDeposit(G4double edep) {
  totalEdep_ += edep;
}

void TrechRunAction::AddVolumeEnergyDeposit(const std::string& volumeName, G4double edep) {
  const auto it = volumeScoreIndex_.find(volumeName);
  if (it == volumeScoreIndex_.end()) {
    return;
  }
  auto& score = volumeScores_[it->second];
  if (score.edep) {
    *(score.edep) += edep;
  }
}

void TrechRunAction::AddOpticalPhotonStep(G4double stepLength) {
  opticalPhotonSteps_ += 1;
  opticalPhotonTrackLength_ += stepLength;
}

void TrechRunAction::AddOpticalPhotonTrack() {
  opticalPhotonTracks_ += 1;
}

void TrechRunAction::RecordEventSummary(G4double eventEdep) {
  eventSummaryCount_ += 1;
  const auto edepMeV = eventEdep / MeV;
  eventEdepSumMeV_ += edepMeV;
  eventEdepSqSumMeV2_ += (edepMeV * edepMeV);
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

void TrechRunAction::RecordHookOnInit() {
  if (hookOnInitEnabled_) {
    hookOnInitCount_ += 1;
  }
}

void TrechRunAction::RecordHookOnRunStart() {
  if (hookOnRunStartEnabled_) {
    hookOnRunStartCount_ += 1;
  }
}

void TrechRunAction::RecordHookOnEventStart() {
  if (hookOnEventStartEnabled_) {
    hookOnEventStartCount_ += 1;
  }
}

bool TrechRunAction::RecordHookOnStep() {
  if (hookOnStepEnabled_) {
    hookOnStepRawCount_ += 1;
    return hookOnStepRawCount_.GetValue() <= hookMaxStepCallbacks_;
  }
  return false;
}

void TrechRunAction::RecordHookOnEventEnd() {
  if (hookOnEventEndEnabled_) {
    hookOnEventEndCount_ += 1;
  }
}

void TrechRunAction::RecordHookOnRunEnd() {
  if (hookOnRunEndEnabled_) {
    hookOnRunEndCount_ += 1;
  }
}

void TrechRunAction::DispatchHook(const std::string& hookName, int eventId, int stepIndex,
                                  double stepEdepMeV, double stepLengthMm) {
  if (!options_.hookRuntime) {
    return;
  }
  HookRuntimeContext context;
  context.seed = cfg_.run.seed;
  context.nEvents = cfg_.run.nEvents;
  context.determinismMode = normalizeDeterminismMode(cfg_.determinism.mode);
  context.eventId = eventId;
  context.stepIndex = stepIndex;
  context.stepEdepMeV = stepEdepMeV;
  context.stepLengthMm = stepLengthMm;
  context.maxEmitsPerCallback = hookMaxEmitsPerCallback_;
  context.maxEmitPayloadBytes = hookMaxEmitPayloadBytes_;
  const auto report =
      options_.hookRuntime->dispatchHook(hookName, context, nullptr, false);
  if (report.patchApplied) {
    hookPatchCount_ += 1;
  }
  if (report.emitCount > 0) {
    hookEmitCount_ += static_cast<int>(report.emitCount);
  }
  if (report.emitDroppedCount > 0) {
    hookEmitDroppedCount_ += static_cast<int>(report.emitDroppedCount);
  }
}

} // namespace trech
