#include "trech/sim/NuclearCycleAnalyzer.hpp"

#include "G4BaryonConstructor.hh"
#include "G4BosonConstructor.hh"
#include "G4IonConstructor.hh"
#include "G4LeptonConstructor.hh"
#include "G4MesonConstructor.hh"
#include "G4NucleiProperties.hh"
#include "G4ParticleDefinition.hh"
#include "G4ParticleTable.hh"
#include "G4SystemOfUnits.hh"

#include <algorithm>
#include <cmath>
#include <cctype>
#include <string>

namespace trech::sim {
namespace {

void ensureParticleDefinitions() {
  static bool initialized = false;
  if (initialized) {
    return;
  }
  G4BosonConstructor bosons;
  bosons.ConstructParticle();
  G4LeptonConstructor leptons;
  leptons.ConstructParticle();
  G4MesonConstructor mesons;
  mesons.ConstructParticle();
  G4BaryonConstructor baryons;
  baryons.ConstructParticle();
  G4IonConstructor ions;
  ions.ConstructParticle();
  initialized = true;
}

std::string trimLowerCopy(const std::string& text) {
  const auto begin = text.find_first_not_of(" \t\n\r");
  if (begin == std::string::npos) {
    return {};
  }
  const auto end = text.find_last_not_of(" \t\n\r");
  std::string out = text.substr(begin, end - begin + 1);
  std::transform(out.begin(), out.end(), out.begin(), [](unsigned char ch) {
    return static_cast<char>(std::tolower(ch));
  });
  return out;
}

struct ParticipantMetrics {
  bool resolved = false;
  double massMeV = 0.0;
  int baryonNumber = 0;
  int chargeNumber = 0;
  std::string label;
};

ParticipantMetrics analyzeParticipant(const NuclearReactionParticipantConfig& participant) {
  ParticipantMetrics metrics;
  if (participant.z > 0 && participant.a > 0) {
    metrics.label = "ion(z=" + std::to_string(participant.z) +
                    ",a=" + std::to_string(participant.a) + ")";
    const auto mass = G4NucleiProperties::GetNuclearMass(participant.a, participant.z) / MeV;
    if (mass > 0.0 && std::isfinite(mass)) {
      metrics.resolved = true;
      metrics.massMeV = mass;
      metrics.baryonNumber = participant.a;
      metrics.chargeNumber = participant.z;
    }
    return metrics;
  }

  if (participant.particle.empty()) {
    metrics.label = "particle(unknown)";
    return metrics;
  }

  metrics.label = participant.particle;
  ensureParticleDefinitions();
  auto* table = G4ParticleTable::GetParticleTable();
  if (!table) {
    return metrics;
  }
  auto* definition = table->FindParticle(participant.particle);
  if (!definition) {
    return metrics;
  }

  metrics.resolved = true;
  metrics.massMeV = definition->GetPDGMass() / MeV;
  metrics.baryonNumber = definition->GetBaryonNumber();
  metrics.chargeNumber = static_cast<int>(std::llround(definition->GetPDGCharge() / eplus));
  return metrics;
}

NuclearReactionMetrics analyzeReaction(const NuclearReactionConfig& reaction) {
  NuclearReactionMetrics metrics;
  metrics.name = reaction.name;
  metrics.halfLifeYears = reaction.halfLifeYears;
  metrics.available = !reaction.reactants.empty() && !reaction.products.empty();
  if (!metrics.available) {
    return metrics;
  }

  double reactantMass = 0.0;
  double productMass = 0.0;
  metrics.massResolved = true;

  for (const auto& reactant : reaction.reactants) {
    const auto m = analyzeParticipant(reactant);
    metrics.reactantBaryonNumber += m.baryonNumber;
    metrics.reactantChargeNumber += m.chargeNumber;
    if (!m.resolved) {
      metrics.massResolved = false;
      metrics.unresolvedParticipants.push_back(m.label);
      continue;
    }
    reactantMass += m.massMeV;
  }

  for (const auto& product : reaction.products) {
    const auto m = analyzeParticipant(product);
    metrics.productBaryonNumber += m.baryonNumber;
    metrics.productChargeNumber += m.chargeNumber;
    if (!m.resolved) {
      metrics.massResolved = false;
      metrics.unresolvedParticipants.push_back(m.label);
      continue;
    }
    productMass += m.massMeV;
  }

  metrics.baryonConserved = metrics.reactantBaryonNumber == metrics.productBaryonNumber;
  metrics.chargeConserved = metrics.reactantChargeNumber == metrics.productChargeNumber;
  if (metrics.massResolved) {
    metrics.qValueMeV = reactantMass - productMass;
  }
  return metrics;
}

std::string phaseTransition(const NuclearSpeciesConfig& source,
                            const NuclearSpeciesConfig& target) {
  const auto from = trimLowerCopy(source.phase);
  const auto to = trimLowerCopy(target.phase);
  if (from.empty() || to.empty()) {
    return {};
  }
  return from + "_to_" + to;
}

} // namespace

NuclearCycleMetrics analyzeNuclearCycle(const NuclearCycleConfig& cycle) {
  NuclearCycleMetrics metrics;
  metrics.name = cycle.name;
  metrics.enabled = cycle.enable;
  metrics.source = cycle.source;
  metrics.target = cycle.target;
  metrics.phaseTransition = phaseTransition(cycle.source, cycle.target);
  metrics.atomicMassConserved =
      cycle.source.a > 0 && cycle.target.a > 0 && cycle.source.a == cycle.target.a;
  if (cycle.source.densityGcm3 > 0.0 && cycle.target.densityGcm3 > 0.0) {
    metrics.densityDeltaGcm3 = cycle.target.densityGcm3 - cycle.source.densityGcm3;
    metrics.densityRatio = cycle.target.densityGcm3 / cycle.source.densityGcm3;
  }
  metrics.forward = analyzeReaction(cycle.forward);
  metrics.backward = analyzeReaction(cycle.backward);
  metrics.cycleConsistent = metrics.enabled && metrics.atomicMassConserved &&
                            metrics.forward.available && metrics.backward.available &&
                            metrics.forward.massResolved && metrics.backward.massResolved &&
                            metrics.forward.baryonConserved &&
                            metrics.forward.chargeConserved &&
                            metrics.backward.baryonConserved &&
                            metrics.backward.chargeConserved;
  return metrics;
}

} // namespace trech::sim
