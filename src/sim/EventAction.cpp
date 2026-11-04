#include "trech/sim/EventAction.hpp"
#include "trech/sim/RunAction.hpp"
#include "trech/core/SimulationBudget.hpp"

#include "G4Event.hh"
#include "G4RunManager.hh"
#if defined(G4MULTITHREADED)
#include "G4MTRunManager.hh"
#endif
#include "G4SafetyHelper.hh"
#include "G4Threading.hh"
#include "G4TransportationManager.hh"
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
      stratifier_(cfg_.stratify, cfg_.determinism, options.stratifierModelSnapshot),
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

void TrechEventAction::BeginOfEventAction(const G4Event* event) {
  // The safety helper caches the distance at a position across tracks/events.
  // At a repeated source position this can make the MSC branch depend on the
  // previous event assigned to this worker, despite per-event RNG seeding.
  // Reset only strict MT workers; preserve the established serial trajectory.
#if defined(G4MULTITHREADED)
  const auto* master = G4MTRunManager::GetMasterRunManager();
  if (cfg_.determinism.mode == "strict" && G4Threading::IsWorkerThread() &&
      master && master->GetNumberOfThreads() > 1) {
    G4TransportationManager::GetTransportationManager()->GetSafetyHelper()->InitialiseHelper();
  }
#endif
  if (auto* runAction = currentRunAction()) {
    runAction->RecordHookOnEventStart();
    if (cfg_.hooks.registered.size() > 0 && event) {
      runAction->DispatchHook("onEventStart", event->GetEventID());
    }
    if (event) {
      const int nVertex = event->GetNumberOfPrimaryVertex();
      int primaryCount = 0;
      for (int i = 0; i < nVertex; ++i) {
        if (auto* vertex = event->GetPrimaryVertex(i)) {
          primaryCount += vertex->GetNumberOfParticle();
        }
      }
      if (primaryCount <= 0) {
        primaryCount = 1;  // particle gun fallback
      }
      for (int i = 0; i < primaryCount; ++i) {
        runAction->AddPrimaryEmitted();
      }
    }
  }
  ResetEvent();
}

void TrechEventAction::EndOfEventAction(const G4Event* event) {
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

  // Trust evidence from THIS event's onEventEnd hook only. Earlier callbacks
  // and other events must not leak into the event's resim decision.
  HookInferenceCounts inference;
  if (event) {
    if (auto* runAction = currentRunAction()) {
      runAction->RecordHookOnEventEnd();
      runAction->RecordEventSummary(eventEdep_);
      runAction->RecordEventFeatureVector(features);
      inference = runAction->DispatchHook("onEventEnd",
                              event->GetEventID(),
                              -1,
                              0.0,
                              0.0,
                              totalEdepMeV,
                              totalTrackLengthMm,
                              totalStepCount_,
                              totalTrackCount_,
                              opticalPhotonSteps_,
                              opticalPhotonTracks_,
                              photonTrackLengthMm);
    }
  }
  if (event && options_.simulationBudget && options_.simulationBudget->finishEvent()) {
    G4RunManager::GetRunManager()->AbortRun(true);
  }
  if (!cfg_.stratify.enable) {
    return;
  }
  if (!event) {
    return;
  }

  const auto result = stratifier_.Evaluate(features);
  // Each policy is explicit: sparse training and off-band use are independent
  // evidence, and must never become hull-domain failures in the OOD counter.
  const bool extendedPolicy =
      cfg_.stratify.resimOnStarvation || cfg_.stratify.resimOnScaleMismatch;
  auto inferenceReasons = nlohmann::json::array();
  if (cfg_.stratify.resimOnLowConfidence && inference.outOfDomain > 0) {
    inferenceReasons.push_back("inference_out_of_domain");
  }
  if (cfg_.stratify.resimOnStarvation && inference.starved > 0) {
    inferenceReasons.push_back("inference_starved");
  }
  if (cfg_.stratify.resimOnScaleMismatch && inference.scaleMismatched > 0) {
    inferenceReasons.push_back("inference_scale_mismatch");
  }
  const bool lowConfidence = !inferenceReasons.empty();
  auto appendTrustEvidence = [&](nlohmann::json& target) {
    target["low_confidence_inference"] = lowConfidence;
    target["inference_out_of_domain_count"] = inference.outOfDomain;
    // Preserve legacy event/queue bytes when neither new policy is requested.
    if (extendedPolicy) {
      target["inference_starved_count"] = inference.starved;
      target["inference_scale_mismatch_count"] = inference.scaleMismatched;
      target["inference_resim_reasons"] = inferenceReasons;
    }
  };

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
  appendTrustEvidence(record["stratification"]);

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

  if (cfg_.stratify.dumpResimQueue && (result.exceptional || lowConfidence)) {
    nlohmann::json resimRecord;
    resimRecord["phase"] = "resim_candidate";
    resimRecord["event_id"] = event->GetEventID();
    resimRecord["label"] = result.label;
    // Preserve feature-classification precedence and retain every enabled
    // inference cause in inference_resim_reasons when using the new policies.
    resimRecord["reason"] =
        result.exceptional ? result.reason : inferenceReasons.front().get<std::string>();
    resimRecord["source"] =
        result.exceptional ? result.source : "cascade_coverage";
    appendTrustEvidence(resimRecord);
    std::ofstream resimOut(resimPath_, std::ios::app);
    resimOut << resimRecord.dump() << '\n';
  }

  if (auto* runAction = currentRunAction()) {
    runAction->AddStratifyResult(result);
    if (lowConfidence) {
      runAction->AddLowConfidenceEvent();
    }
  }
}

void TrechEventAction::AddEnergyDeposit(double edep) {
  eventEdep_ += edep;
}

void TrechEventAction::AddStep(double stepLength) {
  totalStepCount_ += 1;
  totalTrackLength_ += stepLength;
}

void TrechEventAction::AddTrack() {
  totalTrackCount_ += 1;
}

void TrechEventAction::AddOpticalPhotonStep(double stepLength) {
  opticalPhotonSteps_ += 1;
  opticalPhotonTrackLength_ += stepLength;
}

void TrechEventAction::AddOpticalPhotonTrack() {
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
