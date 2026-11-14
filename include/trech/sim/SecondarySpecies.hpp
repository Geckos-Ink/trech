#pragma once

// Geant4-free species classes for the per-event secondary multiplicity split
// (`system_event_secondaries_<species>_*`). A secondary is any track with a
// non-zero parent ID that took a step in the event. The classes are reporting
// bins of what Geant4 produced, not a physics model: every secondary falls in
// exactly one class, so the per-species counts sum to the event's secondaries.
// Since 2026-11-14 protons, alphas and other nuclei (deuteron, triton, He3,
// generic ions: PDG nuclear codes 10LZZZAAAI) have their own classes, so
// "other" holds only the remaining particles (mesons, muons, neutrinos,
// antinucleons, geantinos, ...).

#include <array>
#include <cstddef>
#include <string_view>

namespace trech::sim::secondary_species {

enum Species : std::size_t {
  kGamma = 0,
  kElectron,
  kPositron,
  kOpticalPhoton,
  kNeutron,
  kProton,
  kAlpha,
  kIon,
  kOther,
  kCount
};

inline constexpr std::array<std::string_view, kCount> kNames = {
    "gamma", "electron", "positron", "optical_photon", "neutron",
    "proton", "alpha", "ion", "other"};

// Classify by Geant4 particle name first (optical photons share no stable PDG
// code across Geant4 releases: 0 before 10.7, -22 since), then by PDG code.
inline Species classify(int pdgEncoding, std::string_view particleName) {
  if (particleName == "opticalphoton") {
    return kOpticalPhoton;
  }
  switch (pdgEncoding) {
  case 22:
    return kGamma;
  case 11:
    return kElectron;
  case -11:
    return kPositron;
  case 2112:
    return kNeutron;
  case 2212:
    return kProton;
  case 1000020040:
    return kAlpha;
  default:
    // Nuclear codes are 10LZZZAAAI; antinuclei are negative and stay "other".
    return pdgEncoding >= 1000000000 ? kIon : kOther;
  }
}

inline std::string_view name(Species species) {
  return species < kCount ? kNames[species] : std::string_view("other");
}

} // namespace trech::sim::secondary_species
