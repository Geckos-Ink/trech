#pragma once

// Relativistic kinematics for the photonuclear FINAL-STATE analytic check
// (rides on the `photonuclear_fraction` check). Pure, Geant4-free functions so
// they can be unit tested without a transport build. All energies and masses
// share one unit (the caller passes Geant4's internal MeV); masses come from
// Geant4's own nuclear mass table (G4NucleiProperties) at the call site.
//
// These are CLASSICAL closed-form references ("physics for comparison"): the
// two-body edge bounds what Geant4's photonuclear final-state model may emit,
// and the four-momentum closure tests that model's conservation. They never
// drive transport.

#include <algorithm>
#include <cmath>
#include <limits>

namespace trech {
namespace sim {
namespace photonuclear {

// Kaellen triangle function lambda(a, b, c) = a^2 + b^2 + c^2 - 2ab - 2bc - 2ca.
inline double kallen(double a, double b, double c) {
  return a * a + b * b + c * c - 2.0 * a * b - 2.0 * b * c - 2.0 * c * a;
}

// Maximum laboratory kinetic energy of an ejectile of mass m emitted when a
// photon of energy E is absorbed by a target nucleus of mass M at rest,
// gamma + M -> m + R. It is reached for the two-body final state with the
// recoil R in its ground state (mass mRecoil) and the ejectile emitted along
// the photon: every multi-body or excited final state has a recoil-system
// invariant mass >= mRecoil and so gives the ejectile less energy. Returns NaN
// when the channel is closed (sqrt(s) < m + mRecoil) or inputs are invalid.
inline double twoBodyMaxKinetic(double photonEnergy, double targetMass, double ejectileMass,
                                double recoilMass) {
  if (!(photonEnergy > 0.0) || !(targetMass > 0.0) || !(ejectileMass >= 0.0) ||
      !(recoilMass > 0.0)) {
    return std::numeric_limits<double>::quiet_NaN();
  }
  const double s = targetMass * targetMass + 2.0 * photonEnergy * targetMass;
  const double rootS = std::sqrt(s);
  if (rootS < ejectileMass + recoilMass) {
    return std::numeric_limits<double>::quiet_NaN();
  }
  const double lambda =
      std::max(0.0, kallen(s, ejectileMass * ejectileMass, recoilMass * recoilMass));
  const double pStar = std::sqrt(lambda) / (2.0 * rootS);
  const double eStar = (s + ejectileMass * ejectileMass - recoilMass * recoilMass) / (2.0 * rootS);
  // Boost along the photon: gamma*beta = E / sqrt(s), gamma = (E + M) / sqrt(s).
  const double gamma = (photonEnergy + targetMass) / rootS;
  const double gammaBeta = photonEnergy / rootS;
  const double eLab = gamma * eStar + gammaBeta * pStar;
  return std::max(0.0, eLab - ejectileMass);
}

// Photon energy at which gamma + M -> m + R opens: E_th = ((m+R)^2 - M^2)/(2M).
// Zero for an exothermic channel.
inline double channelThreshold(double targetMass, double ejectileMass, double recoilMass) {
  if (!(targetMass > 0.0)) {
    return std::numeric_limits<double>::quiet_NaN();
  }
  const double sum = ejectileMass + recoilMass;
  return std::max(0.0, (sum * sum - targetMass * targetMass) / (2.0 * targetMass));
}

// Signed energy closure of one absorption, relative to the photon energy:
// (E + M - sum E_out - localDeposit) / E. Zero for an exactly conserving model.
inline double energyClosure(double photonEnergy, double targetMass, double totalOutEnergy,
                            double localDeposit) {
  if (!(photonEnergy > 0.0)) {
    return std::numeric_limits<double>::quiet_NaN();
  }
  return (photonEnergy + targetMass - totalOutEnergy - localDeposit) / photonEnergy;
}

// Neutron-multiplicity histogram bins: 0, 1, 2, >= 3 neutrons per absorption.
constexpr int kNeutronMultiplicityBins = 4;

inline int neutronMultiplicityBin(int neutrons) {
  if (neutrons < 0) {
    return -1;
  }
  return std::min(neutrons, kNeutronMultiplicityBins - 1);
}

} // namespace photonuclear
} // namespace sim
} // namespace trech
