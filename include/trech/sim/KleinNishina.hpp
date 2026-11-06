#pragma once

// Free-electron Klein-Nishina kinematics for the `compton_energy_transfer`
// analytic cross-check. Pure, Geant4-free functions so they can be unit tested
// without a transport build. The caller supplies epsilon = E_gamma / (m_e c^2),
// taking m_e c^2 from Geant4's own CLHEP constant (`electron_mass_c2`).
//
// These are CLASSICAL closed-form references ("physics for comparison"): the
// check compares them to the energy loss Geant4 actually samples for a primary
// photon's first Compton interaction. They never drive transport.

#include <cmath>

namespace trech {
namespace sim {
namespace klein_nishina {

// Scattered-photon energy ratio P = E'/E for scattering angle cos(theta).
inline double scatteredEnergyRatio(double epsilon, double cosTheta) {
  return 1.0 / (1.0 + epsilon * (1.0 - cosTheta));
}

// Unnormalised Klein-Nishina weight dsigma/dcos(theta) / (pi r_e^2):
// P^2 (P + 1/P - sin^2 theta).
inline double differentialWeight(double epsilon, double cosTheta) {
  const double p = scatteredEnergyRatio(epsilon, cosTheta);
  const double sin2 = 1.0 - cosTheta * cosTheta;
  return p * p * (p + 1.0 / p - sin2);
}

// Compton edge: maximum fraction of the photon energy given to the electron
// (back-scatter, theta = pi): T_max / E = 2 eps / (1 + 2 eps).
inline double comptonEdgeFraction(double epsilon) {
  if (!(epsilon > 0.0)) {
    return 0.0;
  }
  return 2.0 * epsilon / (1.0 + 2.0 * epsilon);
}

// Mean fraction of the photon energy transferred to the electron per Compton
// scatter, <T>/E = sigma_tr / sigma = int (1-P) w dcos / int w dcos, evaluated by
// fixed composite Simpson quadrature over cos(theta) in [-1, 1]. The integrand is
// smooth on the closed interval, so a fixed even panel count is deterministic and
// accurate far below Monte-Carlo noise (relative error <1e-8 at 4096 panels up
// to 10 MeV, where the forward peak is sharpest).
inline double meanTransferFraction(double epsilon, int panels = 4096) {
  if (!(epsilon > 0.0)) {
    return 0.0;
  }
  if (panels < 2) {
    panels = 2;
  }
  if (panels % 2 != 0) {
    ++panels;
  }
  const double h = 2.0 / static_cast<double>(panels);
  double weightSum = 0.0;
  double transferSum = 0.0;
  for (int i = 0; i <= panels; ++i) {
    const double cosTheta = -1.0 + h * static_cast<double>(i);
    const double coefficient = (i == 0 || i == panels) ? 1.0 : (i % 2 == 1 ? 4.0 : 2.0);
    const double w = differentialWeight(epsilon, cosTheta);
    const double p = scatteredEnergyRatio(epsilon, cosTheta);
    weightSum += coefficient * w;
    transferSum += coefficient * w * (1.0 - p);
  }
  return weightSum > 0.0 ? transferSum / weightSum : 0.0;
}

} // namespace klein_nishina
} // namespace sim
} // namespace trech
