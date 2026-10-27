#pragma once
#include <cstdint>
#include <nlohmann/json_fwd.hpp>
namespace trech::sim {
// Samples Geant4's nuclear initialization model on an isolated RNG engine.
// Ensemble index is not time, and no wavefunction or nuclear dynamics is inferred.
nlohmann::json sampleNuclearInitialStates(int z, int a, int configurations, std::uint64_t seed);
}
