#include "trech/sim/EventAction.hpp"
#include "trech/sim/RunAction.hpp"

#include "G4Event.hh"
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

TrechRunAction* currentRunAction() {
  auto* manager = G4RunManager::GetRunManager();
  if (!manager) {
    return nullptr;
  }
  return const_cast<TrechRunAction*>(
      dynamic_cast<const TrechRunAction*>(manager->GetUserRunAction()));
}

} // namespace

TrechEventAction::TrechEventAction(const TrechConfig& cfg, const RunOptions& options)
    : cfg_(cfg),
      options_(options),
      stratifier_(cfg_.stratify, cfg_.determinism),
      eventsPath_(joinPath(options.outputDir, "trech_event_scores.jsonl")),
      featuresPath_(joinPath(options.outputDir, "trech_event_features.jsonl")),
      resimPath_(joinPath(options.outputDir, "trech_resim_queue.jsonl")),
      eventEdep_(0.0),
      totalStepCount_(0),
      totalTrackCount_(0),
      totalTrackLength_(0.0),
      opticalPhotonSteps_(0),
      opticalPhotonTracks_(0),
      opticalPhotonTrackLength_(0.0) {}

void TrechEventAction::BeginOfEventAction(const G4Event* /*event*/) {
  if (auto* runAction = currentRunAction()) {
    runAction->RecordHookOnEventStart();
  }
  ResetEvent();
}

void TrechEventAction::EndOfEventAction(const G4Event* event) {
  if (event) {
    if (auto* runAction = currentRunAction()) {
      runAction->RecordHookOnEventEnd();
      runAction->RecordEventSummary(eventEdep_);
    }
  }
  if (!cfg_.stratify.enable) {
    return;
  }
  if (!event) {
    return;
  }

  const auto totalEdepMeV = eventEdep_ / MeV;
  const auto photonTrackLengthMm = opticalPhotonTrackLength_ / mm;
  const auto totalTrackLengthMm = totalTrackLength_ / mm;
  const ml::EventFeatures features = {
    totalEdepMeV,
    totalTrackLengthMm,
    totalStepCount_,
    totalTrackCount_,
    opticalPhotonSteps_,
    opticalPhotonTracks_,
    photonTrackLengthMm,
  };
  const auto result = stratifier_.Evaluate(features);

  nlohmann::json record;
  record["phase"] = "event_end";
  record["event_id"] = event->GetEventID();
  record["total_edep_mev"] = totalEdepMeV;
  record["total_track_length_mm"] = totalTrackLengthMm;
  record["total_step_count"] = totalStepCount_;
  record["total_track_count"] = totalTrackCount_;
  record["optical_photon_tracks"] = opticalPhotonTracks_;
  record["optical_photon_steps"] = opticalPhotonSteps_;
  record["optical_photon_track_length_mm"] = photonTrackLengthMm;
  record["optics_enabled"] = cfg_.optics.enable;
  record["stratification"] = {
    {"enabled", cfg_.stratify.enable},
    {"label", result.label},
    {"reason", result.reason},
    {"source", result.source},
    {"exceptional", result.exceptional},
  };

  std::ofstream out(eventsPath_, std::ios::app);
  out << record.dump() << '\n';

  if (cfg_.stratify.dumpFeatures) {
    nlohmann::json featuresRecord;
    featuresRecord["phase"] = "event_features";
    featuresRecord["event_id"] = event->GetEventID();
    featuresRecord["features"] = {
      {"total_edep_mev", totalEdepMeV},
      {"total_track_length_mm", totalTrackLengthMm},
      {"total_step_count", totalStepCount_},
      {"total_track_count", totalTrackCount_},
      {"optical_photon_steps", opticalPhotonSteps_},
      {"optical_photon_tracks", opticalPhotonTracks_},
      {"optical_photon_track_length_mm", photonTrackLengthMm},
    };
    featuresRecord["label"] = result.label;
    featuresRecord["exceptional"] = result.exceptional;
    featuresRecord["source"] = result.source;
    std::ofstream featuresOut(featuresPath_, std::ios::app);
    featuresOut << featuresRecord.dump() << '\n';
  }

  if (cfg_.stratify.dumpResimQueue && result.exceptional) {
    nlohmann::json resimRecord;
    resimRecord["phase"] = "resim_candidate";
    resimRecord["event_id"] = event->GetEventID();
    resimRecord["label"] = result.label;
    resimRecord["reason"] = result.reason;
    resimRecord["source"] = result.source;
    std::ofstream resimOut(resimPath_, std::ios::app);
    resimOut << resimRecord.dump() << '\n';
  }

  if (auto* runAction = currentRunAction()) {
    runAction->AddStratifyResult(result);
  }
}

void TrechEventAction::AddEnergyDeposit(double edep) {
  eventEdep_ += edep;
}

void TrechEventAction::AddStep(double stepLength) {
  if (!cfg_.stratify.enable) {
    return;
  }
  totalStepCount_ += 1;
  totalTrackLength_ += stepLength;
}

void TrechEventAction::AddTrack() {
  if (!cfg_.stratify.enable) {
    return;
  }
  totalTrackCount_ += 1;
}

void TrechEventAction::AddOpticalPhotonStep(double stepLength) {
  if (!cfg_.stratify.enable) {
    return;
  }
  opticalPhotonSteps_ += 1;
  opticalPhotonTrackLength_ += stepLength;
}

void TrechEventAction::AddOpticalPhotonTrack() {
  if (!cfg_.stratify.enable) {
    return;
  }
  opticalPhotonTracks_ += 1;
}

void TrechEventAction::ResetEvent() {
  eventEdep_ = 0.0;
  totalStepCount_ = 0;
  totalTrackCount_ = 0;
  totalTrackLength_ = 0.0;
  opticalPhotonSteps_ = 0;
  opticalPhotonTracks_ = 0;
  opticalPhotonTrackLength_ = 0.0;
}

} // namespace trech
