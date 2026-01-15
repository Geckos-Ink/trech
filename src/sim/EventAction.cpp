#include "trech/sim/EventAction.hpp"

#include "G4Event.hh"
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

std::string stratifyLabel(bool enabled, bool exceptional) {
  if (!enabled) {
    return "unclassified";
  }
  return exceptional ? "exceptional" : "predictable";
}

} // namespace

TrechEventAction::TrechEventAction(const TrechConfig& cfg, const RunOptions& options)
    : cfg_(cfg),
      options_(options),
      eventsPath_(joinPath(options.outputDir, "trech_event_scores.jsonl")),
      eventEdep_(0.0),
      opticalPhotonSteps_(0),
      opticalPhotonTracks_(0),
      opticalPhotonTrackLength_(0.0) {}

void TrechEventAction::BeginOfEventAction(const G4Event* /*event*/) {
  if (!cfg_.stratify.enable) {
    return;
  }
  ResetEvent();
}

void TrechEventAction::EndOfEventAction(const G4Event* event) {
  if (!cfg_.stratify.enable) {
    return;
  }
  if (!event) {
    return;
  }

  const auto totalEdepMeV = eventEdep_ / MeV;
  const auto photonTrackLengthMm = opticalPhotonTrackLength_ / mm;
  bool exceptional = false;
  std::string reason;
  if (cfg_.stratify.edepMeVThreshold > 0.0 &&
      totalEdepMeV > cfg_.stratify.edepMeVThreshold) {
    exceptional = true;
    reason = "edep_mev_threshold";
  }
  if (!exceptional && cfg_.stratify.opticalTrackLengthMmThreshold > 0.0 &&
      photonTrackLengthMm > cfg_.stratify.opticalTrackLengthMmThreshold) {
    exceptional = true;
    reason = "optical_track_length_mm_threshold";
  }

  nlohmann::json record;
  record["phase"] = "event_end";
  record["event_id"] = event->GetEventID();
  record["total_edep_mev"] = totalEdepMeV;
  record["optical_photon_tracks"] = opticalPhotonTracks_;
  record["optical_photon_steps"] = opticalPhotonSteps_;
  record["optical_photon_track_length_mm"] = photonTrackLengthMm;
  record["stratification"] = {
    {"enabled", cfg_.stratify.enable},
    {"label", stratifyLabel(cfg_.stratify.enable, exceptional)},
    {"reason", reason},
  };

  std::ofstream out(eventsPath_, std::ios::app);
  out << record.dump() << '\n';
}

void TrechEventAction::AddEnergyDeposit(double edep) {
  if (!cfg_.stratify.enable) {
    return;
  }
  eventEdep_ += edep;
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
  opticalPhotonSteps_ = 0;
  opticalPhotonTracks_ = 0;
  opticalPhotonTrackLength_ = 0.0;
}

} // namespace trech
