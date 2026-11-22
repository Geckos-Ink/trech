#pragma once

// Geant4 side of the engine trace (trech/core/Trace.hpp): when and how the base of truth was
// simulated. Every function is observation-only: it reads Geant4 state, never changes it, and
// returns at once when the trace is off (one relaxed atomic load).
//
// Categories and levels:
//   geant4        info:  kernel initialized (physics list, threads, materials, world), run start
//                        (beamOn: events, seed, primary source), run end (tallies).
//                 debug: physics processes per particle, production cuts, every placed volume,
//                        one record per simulated event.
//   geant4_track  trace: one record per track start and end (particle, energy, creator/ending
//                        process, volume, length).
//   geant4_step   trace: one record per step (particle, defining process, volume, deposit, length,
//                        kinetic energy before/after). Subject to the per-category cap.
// Tallies (summary `tallies`, per batch and per run): geant4.events, geant4.steps_by_process,
// geant4.edep_mev_by_process, geant4.tracks_by_particle, geant4.tracks_by_creator,
// geant4.steps_by_volume. Per-thread counts are flushed at each event end.

#include <string>

class G4Event;
class G4Run;
class G4Step;
class G4Track;
class G4VModularPhysicsList;

namespace trech {
struct TrechConfig;
}

namespace trech::sim::g4trace {

// After G4RunManager::Initialize(): physics list, threads, geometry, materials, processes, cuts.
void kernelInitialized(const TrechConfig& cfg, const std::string& physicsListName, int threads);
// Master BeginOfRunAction / EndOfRunAction.
void runStarted(const G4Run* run, const TrechConfig& cfg, int events, unsigned long long seed);
void runEnded(const G4Run* run, int eventsProcessed);
// Event and track/step actions (any thread).
void eventStarted(const G4Event* event);
void eventEnded(const G4Event* event, double edepMeV, double steps, double tracks);
void trackStarted(const G4Track* track);
void trackEnded(const G4Track* track);
void step(const G4Step* step);

}  // namespace trech::sim::g4trace
