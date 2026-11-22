#pragma once

// Energy balance of one recorded Geant4 step (a classic law with an optional Lean pair).
//
// A step that turns an incoming particle of kinetic energy E_pre into an outgoing one of
// kinetic energy E_post, secondaries of kinetic energies T_i and a local deposit d conserves
// energy when
//
//     E_pre + Q = E_post + sum_i T_i + d,
//
// where Q is the rest-mass energy released by the step (0 for Compton scattering,
// photo-absorption with local binding deposit, Rayleigh scattering and ionisation; -2 m_e c^2
// for a gamma conversion). The engine reads the residual from Geant4's own step record in
// SteppingAction. It only observes: it never changes transport, RNG, emits or scores other
// than the check's own record. Today it is evaluated on a primary photon's first Compton
// scatter when a `compton_energy_transfer` analytic check is configured.
//
// Lean pair (optional, for validation): Trech.Laws.EnergyBalance in
// formal/Trech/Laws/EnergyBalance.lean states the balance, bounds each product by the
// incoming energy when Q = 0, and proves that balanced steps telescope along a track. A theorem
// over the reals does not certify this double-precision evaluation; the tolerance below is
// stated for doubles.

#include "trech/core/FormalLaws.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <vector>

namespace trech {
namespace sim {
namespace energy_balance {

// Relative tolerance for a balanced step in doubles. Geant4 forms the electron energy as
// E_pre - E_post, so a balanced Compton step closes to a few ulp of E_pre.
constexpr double kRelativeTolerance = 1e-12;

// |(E_pre + Q) - (E_post + sum T_i + d)| divided by the largest term's magnitude, summed with
// Neumaier compensation so the check does not report its own rounding. Returns 0 for a step
// with no energy at all, and NaN when any input is not finite.
inline double relativeResidual(double preKineticEnergy, double restMassReleased,
                               double postKineticEnergy, const std::vector<double>& secondaryKineticEnergies,
                               double localDeposit) {
  std::vector<double> terms;
  terms.reserve(secondaryKineticEnergies.size() + 4);
  terms.push_back(preKineticEnergy);
  terms.push_back(restMassReleased);
  terms.push_back(-postKineticEnergy);
  for (const double t : secondaryKineticEnergies) terms.push_back(-t);
  terms.push_back(-localDeposit);
  double scale = 0.0;
  for (const double t : terms) {
    if (!std::isfinite(t)) return std::nan("");
    scale = std::max(scale, std::abs(t));
  }
  if (scale == 0.0) return 0.0;
  return std::abs(formal::compensatedSum(terms.data(), terms.size())) / scale;
}

}  // namespace energy_balance
}  // namespace sim
}  // namespace trech
