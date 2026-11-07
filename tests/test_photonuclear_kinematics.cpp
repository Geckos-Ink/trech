// Geant4-free checks of the relativistic kinematics behind the photonuclear
// final-state analytic cross-check (two-body ejectile edge, channel threshold,
// four-momentum closure).
#include "trech/sim/PhotonuclearKinematics.hpp"

#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>

namespace pn = trech::sim::photonuclear;

namespace {

void require(bool ok, const std::string& what) {
  if (!ok) {
    throw std::runtime_error(what);
  }
}

// CODATA-style masses (MeV) for the deuteron photodisintegration test case.
constexpr double kNeutron = 939.56542052;
constexpr double kProton = 938.27208816;
constexpr double kDeuteron = 1875.61294257;

// Recoil kinetic energy implied by momentum conservation for a forward ejectile.
double recoilTotalEnergy(double photon, double ejectileMass, double ejectileKinetic,
                         double recoilMass) {
  const double ejectileTotal = ejectileKinetic + ejectileMass;
  const double ejectileMomentum =
      std::sqrt(std::max(0.0, ejectileTotal * ejectileTotal - ejectileMass * ejectileMass));
  const double recoilMomentum = photon - ejectileMomentum;  // collinear
  return std::sqrt(recoilMomentum * recoilMomentum + recoilMass * recoilMass);
}

} // namespace

int main() {
  try {
    // Deuteron threshold: binding B = m_n + m_p - M_d plus the recoil term B^2/2M.
    const double binding = kNeutron + kProton - kDeuteron;
    const double threshold = pn::channelThreshold(kDeuteron, kNeutron, kProton);
    const double expected = binding + binding * binding / (2.0 * kDeuteron);
    require(std::abs(threshold - (binding * (kNeutron + kProton + kDeuteron)) /
                                      (2.0 * kDeuteron)) < 1e-12,
            "deuteron threshold closed form");
    require(std::abs(threshold - expected) < 1e-9, "deuteron threshold = B + B^2/2M");
    require(threshold > 2.2245 && threshold < 2.2265, "deuteron threshold ~2.2259 MeV");

    // Closed below threshold, open (and non-negative) just above.
    require(std::isnan(pn::twoBodyMaxKinetic(threshold * 0.999, kDeuteron, kNeutron, kProton)),
            "closed channel below threshold");
    const double justAbove = pn::twoBodyMaxKinetic(threshold * 1.000001, kDeuteron, kNeutron,
                                                   kProton);
    require(std::isfinite(justAbove) && justAbove >= 0.0, "open just above threshold");

    // The edge conserves four-momentum exactly with a collinear ground-state
    // recoil, and grows with the photon energy.
    double previous = -1.0;
    for (double photon : {2.5, 5.0, 10.0, 23.0, 50.0}) {
      const double edge = pn::twoBodyMaxKinetic(photon, kDeuteron, kNeutron, kProton);
      require(std::isfinite(edge) && edge > previous, "edge increases with photon energy");
      previous = edge;
      const double eOut =
          edge + kNeutron + recoilTotalEnergy(photon, kNeutron, edge, kProton);
      require(std::abs(photon + kDeuteron - eOut) < 1e-9 * photon,
              "edge conserves energy and momentum");
      // Nonrelativistic bound: at most the available energy E - threshold.
      require(edge <= photon - threshold + 1e-12, "edge below available energy");
      // Energy closure of that exact final state is zero.
      require(std::abs(pn::energyClosure(photon, kDeuteron, eOut, 0.0)) < 1e-12,
              "zero closure for a conserving final state");
    }
    // Forward emission beats any other direction: the backward-emitted ejectile
    // energy from the same CM state is lower.
    {
      const double photon = 23.0;
      const double s = kDeuteron * kDeuteron + 2.0 * photon * kDeuteron;
      const double rootS = std::sqrt(s);
      const double pStar =
          std::sqrt(pn::kallen(s, kNeutron * kNeutron, kProton * kProton)) / (2.0 * rootS);
      const double eStar = (s + kNeutron * kNeutron - kProton * kProton) / (2.0 * rootS);
      const double gamma = (photon + kDeuteron) / rootS;
      const double gammaBeta = photon / rootS;
      const double backward = gamma * eStar - gammaBeta * pStar - kNeutron;
      require(backward < pn::twoBodyMaxKinetic(photon, kDeuteron, kNeutron, kProton),
              "forward emission is the maximum");
    }
    // Exothermic channels open at zero photon energy.
    require(pn::channelThreshold(10.0, 4.0, 5.0) == 0.0, "exothermic threshold is zero");
    // Invalid inputs.
    require(std::isnan(pn::twoBodyMaxKinetic(-1.0, kDeuteron, kNeutron, kProton)),
            "negative photon energy");
    require(std::isnan(pn::energyClosure(0.0, 1.0, 1.0, 0.0)), "zero photon energy closure");
    // Multiplicity bins: 0, 1, 2, >= 3.
    require(pn::neutronMultiplicityBin(0) == 0 && pn::neutronMultiplicityBin(2) == 2 &&
                pn::neutronMultiplicityBin(7) == pn::kNeutronMultiplicityBins - 1 &&
                pn::neutronMultiplicityBin(-1) == -1,
            "neutron multiplicity bins");
  } catch (const std::exception& error) {
    std::cerr << "test_photonuclear_kinematics: " << error.what() << "\n";
    return 1;
  }
  std::cout << "test_photonuclear_kinematics: ok\n";
  return 0;
}
