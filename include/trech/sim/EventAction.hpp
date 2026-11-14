#pragma once

#include "trech/core/Config.hpp"
#include "trech/core/RunOptions.hpp"
#include "trech/ml/Stratifier.hpp"
#include "trech/sim/SecondarySpecies.hpp"

#include <array>

#include "G4UserEventAction.hh"

class G4Event;

namespace trech {

class TrechEventAction : public G4UserEventAction {
public:
  TrechEventAction(const TrechConfig& cfg, const RunOptions& options);

  void BeginOfEventAction(const G4Event* event) override;
  void EndOfEventAction(const G4Event* event) override;

  // stepSpecies: the sim::secondary_species class of the stepping particle
  // (primaries included); feeds the per-class event deposit / length split.
  void AddEnergyDeposit(double edep, int stepSpecies);
  void AddStep(double stepLength, int stepSpecies);
  void AddTrack();
  void AddOpticalPhotonStep(double stepLength);
  void AddOpticalPhotonTrack();
  // One secondary (non-zero parent ID) track's first step, by species class.
  void AddSecondaryTrack(sim::secondary_species::Species species);

private:
  void ResetEvent();

  TrechConfig cfg_;
  RunOptions options_;
  ml::EventStratifier stratifier_;
  std::string eventsPath_;
  std::string featuresPath_;
  std::string resimPath_;
  double eventEdep_;
  int totalStepCount_;
  int totalTrackCount_;
  double totalTrackLength_;
  int opticalPhotonSteps_;
  int opticalPhotonTracks_;
  double opticalPhotonTrackLength_;
  // Primaries injected at BeginOfEventAction (set before ResetEvent; not
  // reset there) so EndOfEventAction can separate secondaries.
  int eventPrimaryCount_;
  std::array<int, sim::secondary_species::kCount> secondarySpeciesCounts_{};
  // This event's deposit (Geant4 energy units) and step length (Geant4 length
  // units) by stepping-particle class; they sum to eventEdep_ / totalTrackLength_.
  std::array<double, sim::secondary_species::kCount> edepByClass_{};
  std::array<double, sim::secondary_species::kCount> trackLengthByClass_{};
};

} // namespace trech
