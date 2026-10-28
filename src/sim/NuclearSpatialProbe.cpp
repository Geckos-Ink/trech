#include "trech/sim/NuclearSpatialProbe.hpp"
#include "G4Fancy3DNucleus.hh"
#include "G4SystemOfUnits.hh"
#include "Randomize.hh"
#include "CLHEP/Random/MixMaxRng.h"
#include <nlohmann/json.hpp>
#include <cmath>
#include <stdexcept>
#include <array>
#include <algorithm>

namespace trech::sim {
nlohmann::json sampleNuclearInitialStates(int z, int a, int configurations, std::uint64_t seed) {
  nlohmann::json result = {{"z", z}, {"a", a}, {"available", false}, {"length_unit", "fm"},
    {"source", {{"kind", "geant4"}, {"method", "G4Fancy3DNucleus"},
      {"scope", "independent nuclear initial-state model samples; not a nuclear wavefunction or time evolution"}}},
    {"time_kind", "ensemble_index"}, {"seed", seed}};
  if (z < 1 || a < 2 || a < z || a > 250 || configurations < 1 || configurations > 32) {
    result["note"] = "Supported sampling panel: 2 <= A <= 250, 1 <= Z <= A, 1..32 configurations; no single-proton internal distribution";
    return result;
  }
  // Swapping the pointer (rather than reseeding/restoring transport) also keeps
  // this diagnostic independent of the number/order of other material probes.
  const auto localSeed = static_cast<long>((seed ^ (std::uint64_t(z) << 32) ^ std::uint64_t(a)) % 2147483646ULL + 1);
  CLHEP::MixMaxRng engine(localSeed);
  struct RestoreEngine {
    CLHEP::HepRandomEngine* previous;
    ~RestoreEngine() { G4Random::setTheEngine(previous); }
  } restore{G4Random::getTheEngine()};
  G4Random::setTheEngine(&engine);
  auto samples = nlohmann::json::array();
  // Descriptive statistics of this model's samples, never an assumed shell law.
  std::array<std::array<unsigned, 16>, 2> radialCounts{};
  double largestRadius = 0;
  for (int i = 0; i < configurations; ++i) {
    G4Fancy3DNucleus nucleus;
    nucleus.Init(a, z);
    auto protons = nlohmann::json::array(), neutrons = nlohmann::json::array();
    for (const auto& nucleon : nucleus.GetNucleons()) {
      const auto& p = nucleon.GetPosition();
      const auto* particle = nucleon.GetDefinition();
      if (!std::isfinite(p.x()) || !std::isfinite(p.y()) || !std::isfinite(p.z()))
        throw std::runtime_error("non-finite Geant4 nuclear sample");
      auto point = nlohmann::json::array({p.x() / fermi, p.y() / fermi, p.z() / fermi});
      if (particle->GetParticleName() == "proton") protons.push_back(point);
      else if (particle->GetParticleName() == "neutron") neutrons.push_back(point);
      else throw std::runtime_error("unexpected species in Geant4 nuclear sample");
    }
    if (protons.size() != std::size_t(z) || neutrons.size() != std::size_t(a - z))
      throw std::runtime_error("Geant4 nuclear sample nucleon-count mismatch");
    std::array<double, 3> centre{};
    for (const auto* points : {&protons, &neutrons}) for (const auto& p : *points)
      for (int axis = 0; axis < 3; ++axis) centre[axis] += p[axis].get<double>() / a;
    nlohmann::json statistics = {{"centre_fm", centre}};
    for (int species = 0; species < 2; ++species) {
      const auto& points = species == 0 ? protons : neutrons;
      double squaredSum = 0, maximum = 0;
      for (const auto& p : points) {
        double squared = 0;
        for (int axis = 0; axis < 3; ++axis) squared += std::pow(p[axis].get<double>() - centre[axis], 2);
        const double radius = std::sqrt(squared);
        squaredSum += squared; maximum = std::max(maximum, radius);
        // Last bin is overflow, explicitly reported as such below.
        ++radialCounts[species][std::min(15, static_cast<int>(radius / 0.5))];
      }
      largestRadius = std::max(largestRadius, maximum);
      statistics[species == 0 ? "protons" : "neutrons"] = {{"count", points.size()},
        {"rms_radius_fm", points.empty() ? nlohmann::json(nullptr) : nlohmann::json(std::sqrt(squaredSum / points.size()))},
        {"max_radius_fm", maximum}};
    }
    samples.push_back({{"protons", protons}, {"neutrons", neutrons}, {"statistics", statistics}});
  }
  result["available"] = true;
  result["configurations"] = samples;
  result["inventory"] = {{"protons", z}, {"neutrons", a-z}, {"nucleons", a}, {"nuclei_per_configuration", 1}};
  result["radial_distribution"] = {{"origin", "each configuration's nucleon centroid"},
    {"bin_width_fm", 0.5}, {"last_bin_overflow", true}, {"proton_counts", radialCounts[0]},
    {"neutron_counts", radialCounts[1]}, {"configurations", configurations}, {"max_radius_fm", largestRadius},
    {"scope", "finite sampled radial counts, not shell occupations or a nuclear wavefunction"}};
  return result;
}
}
