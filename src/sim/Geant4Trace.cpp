#include "trech/sim/Geant4Trace.hpp"

#include "trech/core/Config.hpp"
#include "trech/core/Trace.hpp"

#include "G4Event.hh"
#include "G4LogicalVolume.hh"
#include "G4Material.hh"
#include "G4ParticleDefinition.hh"
#include "G4ParticleTable.hh"
#include "G4PhysicalVolumeStore.hh"
#include "G4ProcessManager.hh"
#include "G4ProcessVector.hh"
#include "G4ProductionCutsTable.hh"
#include "G4Run.hh"
#include "G4Step.hh"
#include "G4SystemOfUnits.hh"
#include "G4Threading.hh"
#include "G4Track.hh"
#include "G4VPhysicalVolume.hh"
#include "G4VProcess.hh"
#include "G4VSolid.hh"
#include "G4Version.hh"

#include <map>
#include <mutex>
#include <set>
#include <string>

namespace trech::sim::g4trace {
namespace {

using trech::trace::Level;

// Per-thread counts, flushed into the trace tallies at each event end so the hot step path never
// takes the trace mutex.
struct ThreadTally {
  std::map<std::string, double> stepsByProcess, edepByProcess, tracksByParticle, tracksByCreator,
      stepsByVolume;
  std::set<std::string> particles;
};

ThreadTally& local() {
  thread_local ThreadTally t;
  return t;
}

// Particles seen during the run (any thread), for the run-end process listing.
std::mutex gSeenMutex;
std::set<std::string> gSeen;

std::string processName(const G4VProcess* process) {
  return process ? std::string(process->GetProcessName()) : std::string("none");
}

std::string particleName(const G4Track* track) {
  const auto* def = track ? track->GetDefinition() : nullptr;
  return def ? std::string(def->GetParticleName()) : std::string("unknown");
}

std::string volumeName(const G4VPhysicalVolume* volume) {
  return volume ? std::string(volume->GetName()) : std::string("outside");
}

nlohmann::json processesOf(const G4ParticleDefinition* particle) {
  nlohmann::json out = nlohmann::json::array();
  const auto* manager = particle ? particle->GetProcessManager() : nullptr;
  const auto* list = manager ? manager->GetProcessList() : nullptr;
  if (!list) return out;
  for (std::size_t i = 0; i < list->size(); ++i) {
    const auto* process = (*list)[i];
    if (!process) continue;
    out.push_back({{"name", process->GetProcessName()},
                   {"type", G4VProcess::GetProcessTypeName(process->GetProcessType())},
                   {"active", manager->GetProcessActivation(i)}});
  }
  return out;
}

nlohmann::json beamJson(const BeamConfig& b) {
  nlohmann::json out = {{"particle", b.particle},
                        {"energy_mev", b.energyMeV},
                        {"direction", {b.directionX, b.directionY, b.directionZ}},
                        {"origin_mm", {b.originXMm, b.originYMm, b.originZMm}}};
  if (!b.name.empty()) out["name"] = b.name;
  if (b.spotRadiusMm > 0) out["spot_radius_mm"] = b.spotRadiusMm;
  if (b.divergenceDeg > 0) out["divergence_deg"] = b.divergenceDeg;
  if (b.energySpreadFractional > 0) out["energy_spread_fractional"] = b.energySpreadFractional;
  return out;
}

void flush(ThreadTally& t) {
  static const std::pair<const char*, std::map<std::string, double> ThreadTally::*> kSections[] = {
      {"geant4.steps_by_process", &ThreadTally::stepsByProcess},
      {"geant4.edep_mev_by_process", &ThreadTally::edepByProcess},
      {"geant4.tracks_by_particle", &ThreadTally::tracksByParticle},
      {"geant4.tracks_by_creator", &ThreadTally::tracksByCreator},
      {"geant4.steps_by_volume", &ThreadTally::stepsByVolume}};
  for (const auto& [section, member] : kSections) {
    for (const auto& [key, n] : t.*member) trace::tally(section, key, n);
    (t.*member).clear();
  }
  if (!t.particles.empty()) {
    std::lock_guard<std::mutex> lock(gSeenMutex);
    gSeen.insert(t.particles.begin(), t.particles.end());
    t.particles.clear();
  }
}

}  // namespace

void kernelInitialized(const TrechConfig& cfg, const std::string& physicsListName, int threads) {
  if (!trace::active()) return;
  if (trace::enabled(Level::Info, "geant4")) {
    nlohmann::json materials = nlohmann::json::array();
    if (const auto* table = G4Material::GetMaterialTable()) {
      for (const auto* m : *table) {
        if (!m) continue;
        materials.push_back({{"name", m->GetName()},
                             {"density_g_cm3", m->GetDensity() / (g / cm3)},
                             {"elements", m->GetNumberOfElements()},
                             {"state", m->GetState() == kStateGas      ? "gas"
                                       : m->GetState() == kStateLiquid ? "liquid"
                                       : m->GetState() == kStateSolid  ? "solid"
                                                                       : "undefined"}});
      }
    }
    const auto* store = G4PhysicalVolumeStore::GetInstance();
    trace::record(Level::Info, "geant4", "kernel initialized",
                  {{"geant4_version", G4Version},
                   {"physics_list", physicsListName},
                   {"physics_list_requested", cfg.physics.list.empty() ? "QBBC" : cfg.physics.list},
                   {"threads", threads},
                   {"multithreaded", G4Threading::IsMultithreadedApplication()},
                   {"placed_volumes", store ? store->size() : 0},
                   {"materials", trace::digest(materials, trace::options().maxDigestBytes)}});
  }
  if (trace::enabled(Level::Debug, "geant4")) {
    if (const auto* store = G4PhysicalVolumeStore::GetInstance()) {
      for (const auto* pv : *store) {
        if (!pv) continue;
        const auto* lv = pv->GetLogicalVolume();
        const auto* mother = pv->GetMotherLogical();
        const auto t = pv->GetTranslation();
        trace::record(Level::Debug, "geant4", "volume placed",
                      {{"volume", pv->GetName()},
                       {"logical", lv ? std::string(lv->GetName()) : std::string()},
                       {"solid", lv && lv->GetSolid() ? std::string(lv->GetSolid()->GetEntityType()) : std::string()},
                       {"material", lv && lv->GetMaterial() ? std::string(lv->GetMaterial()->GetName()) : std::string()},
                       {"mother", mother ? std::string(mother->GetName()) : std::string("(world)")},
                       {"translation_mm", {t.x() / mm, t.y() / mm, t.z() / mm}}});
      }
    }
    if (const auto* cuts = G4ProductionCutsTable::GetProductionCutsTable()) {
      nlohmann::json couples = nlohmann::json::array();
      for (std::size_t i = 0; i < cuts->GetTableSize(); ++i) {
        const auto* couple = cuts->GetMaterialCutsCouple(static_cast<G4int>(i));
        if (!couple || !couple->GetMaterial()) continue;
        couples.push_back({{"material", couple->GetMaterial()->GetName()}, {"used", couple->IsUsed()}});
      }
      trace::record(Level::Debug, "geant4", "production cuts", {{"couples", couples}});
    }
    // Processes of the primaries and of the particles every TRECH run meets.
    std::set<std::string> names = {"gamma", "e-", "e+", "proton", "neutron", "opticalphoton"};
    names.insert(cfg.beam.particle);
    for (const auto& b : cfg.beams) names.insert(b.particle);
    auto* table = G4ParticleTable::GetParticleTable();
    for (const auto& name : names) {
      const auto* particle = table ? table->FindParticle(name) : nullptr;
      if (!particle) continue;
      trace::record(Level::Debug, "geant4", "physics processes",
                    {{"particle", name}, {"processes", processesOf(particle)}});
    }
  }
}

void runStarted(const G4Run* run, const TrechConfig& cfg, int events, unsigned long long seed) {
  if (!trace::active()) return;
  {
    std::lock_guard<std::mutex> lock(gSeenMutex);
    gSeen.clear();
  }
  if (!trace::enabled(Level::Info, "geant4")) return;
  nlohmann::json beams = nlohmann::json::array();
  if (cfg.beams.empty()) beams.push_back(beamJson(cfg.beam));
  for (const auto& b : cfg.beams) beams.push_back(beamJson(b));
  trace::record(Level::Info, "geant4", "run start (beamOn)",
                {{"run_id", run ? run->GetRunID() : -1},
                 {"events", events},
                 {"seed", seed},
                 {"determinism", cfg.determinism.mode},
                 {"sources", beams}});
}

void runEnded(const G4Run* run, int eventsProcessed) {
  if (!trace::active()) return;
  flush(local());  // master-thread counts (serial runs step on the master)
  std::set<std::string> seen;
  {
    std::lock_guard<std::mutex> lock(gSeenMutex);
    seen = gSeen;
  }
  if (trace::enabled(Level::Info, "geant4")) {
    nlohmann::json particles = nlohmann::json::array();
    for (const auto& p : seen) particles.push_back(p);
    trace::record(Level::Info, "geant4", "run end",
                  {{"run_id", run ? run->GetRunID() : -1},
                   {"events", eventsProcessed},
                   {"particles_seen", particles}});
  }
  if (trace::enabled(Level::Debug, "geant4")) {
    auto* table = G4ParticleTable::GetParticleTable();
    for (const auto& name : seen) {
      const auto* particle = table ? table->FindParticle(name) : nullptr;
      if (!particle) continue;
      trace::record(Level::Debug, "geant4", "physics processes (seen)",
                    {{"particle", name}, {"processes", processesOf(particle)}});
    }
  }
}

void eventStarted(const G4Event* event) {
  if (!trace::enabled(Level::Trace, "geant4")) return;
  nlohmann::json primaries = nlohmann::json::array();
  if (event) {
    for (int i = 0; i < event->GetNumberOfPrimaryVertex(); ++i) {
      const auto* vertex = event->GetPrimaryVertex(i);
      if (!vertex) continue;
      for (int j = 0; j < vertex->GetNumberOfParticle(); ++j) {
        const auto* p = vertex->GetPrimary(j);
        if (!p) continue;
        const auto* def = p->GetParticleDefinition();
        primaries.push_back({{"particle", def ? std::string(def->GetParticleName()) : std::string()},
                             {"kinetic_mev", p->GetKineticEnergy() / MeV},
                             {"position_mm", {vertex->GetX0() / mm, vertex->GetY0() / mm, vertex->GetZ0() / mm}}});
      }
    }
  }
  trace::record(Level::Trace, "geant4", "event start",
                {{"event", event ? event->GetEventID() : -1},
                 {"primaries", trace::digest(primaries, trace::options().maxDigestBytes)}});
}

void eventEnded(const G4Event* event, double edepMeV, double steps, double tracks) {
  if (!trace::active()) return;
  auto& t = local();
  flush(t);
  trace::tally("geant4.events", "simulated", 1.0);
  if (trace::enabled(Level::Debug, "geant4")) {
    trace::record(Level::Debug, "geant4", "event simulated",
                  {{"event", event ? event->GetEventID() : -1},
                   {"edep_mev", edepMeV},
                   {"steps", steps},
                   {"tracks", tracks},
                   {"thread", G4Threading::G4GetThreadId()}});
  }
}

void trackStarted(const G4Track* track) {
  if (!trace::active() || !track) return;
  auto& t = local();
  const auto particle = particleName(track);
  t.tracksByParticle[particle] += 1.0;
  t.tracksByCreator[track->GetCreatorProcess() ? processName(track->GetCreatorProcess()) : "primary"] += 1.0;
  t.particles.insert(particle);
  if (!trace::enabled(Level::Trace, "geant4_track")) return;
  const auto p = track->GetPosition();
  trace::record(Level::Trace, "geant4_track", "track start",
                {{"track", track->GetTrackID()},
                 {"parent", track->GetParentID()},
                 {"particle", particle},
                 {"kinetic_mev", track->GetKineticEnergy() / MeV},
                 {"creator", track->GetCreatorProcess() ? processName(track->GetCreatorProcess()) : "primary"},
                 {"volume", volumeName(track->GetVolume())},
                 {"position_mm", {p.x() / mm, p.y() / mm, p.z() / mm}}});
}

void trackEnded(const G4Track* track) {
  if (!track || !trace::enabled(Level::Trace, "geant4_track")) return;
  const auto* last = track->GetStep();
  const auto* post = last ? last->GetPostStepPoint() : nullptr;
  trace::record(Level::Trace, "geant4_track", "track end",
                {{"track", track->GetTrackID()},
                 {"particle", particleName(track)},
                 {"ended_by", post ? processName(post->GetProcessDefinedStep()) : "none"},
                 {"steps", track->GetCurrentStepNumber()},
                 {"length_mm", track->GetTrackLength() / mm},
                 {"kinetic_mev", track->GetKineticEnergy() / MeV}});
}

void step(const G4Step* step) {
  if (!trace::active() || !step) return;
  const auto* pre = step->GetPreStepPoint();
  const auto* post = step->GetPostStepPoint();
  const auto process = processName(post ? post->GetProcessDefinedStep() : nullptr);
  const double edep = step->GetTotalEnergyDeposit() / MeV;
  auto& t = local();
  t.stepsByProcess[process] += 1.0;
  if (edep > 0.0) t.edepByProcess[process] += edep;
  const auto volume = volumeName(pre ? pre->GetPhysicalVolume() : nullptr);
  t.stepsByVolume[volume] += 1.0;
  if (!trace::enabled(Level::Trace, "geant4_step")) return;
  const auto* track = step->GetTrack();
  trace::record(Level::Trace, "geant4_step", process,
                {{"track", track ? track->GetTrackID() : -1},
                 {"step", track ? track->GetCurrentStepNumber() : -1},
                 {"particle", particleName(track)},
                 {"volume", volume},
                 {"edep_mev", edep},
                 {"length_mm", step->GetStepLength() / mm},
                 {"pre_kinetic_mev", pre ? pre->GetKineticEnergy() / MeV : 0.0},
                 {"post_kinetic_mev", post ? post->GetKineticEnergy() / MeV : 0.0}});
}

}  // namespace trech::sim::g4trace
