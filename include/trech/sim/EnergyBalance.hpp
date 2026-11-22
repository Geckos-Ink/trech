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
#include <array>
#include <cmath>
#include <cstddef>
#include <limits>
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

// Momentum balance of the same step, the hypothesis `k = k' + p` of the Lean pair
// Trech.Laws.TwoBody (formal/Trech/Laws/TwoBody.lean), which derives the Compton relation from
// four-momentum conservation: |p_pre - p_post - sum p_i| over the largest momentum magnitude
// among the terms, per Cartesian component with Neumaier sums, the largest component reported.
// It holds only where every product is recorded as a track: a particle absorbed on the spot
// (an electron below the production threshold) carries momentum the step record drops, so
// callers check steps whose products are all tracks. NaN when any input is not finite.
using Momentum = std::array<double, 3>;

inline double relativeMomentumResidual(const Momentum& pre, const Momentum& post,
                                       const std::vector<Momentum>& secondaries) {
  double scale = 0.0;
  auto magnitude = [](const Momentum& v) { return std::sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]); };
  for (const Momentum* v : {&pre, &post}) scale = std::max(scale, magnitude(*v));
  for (const auto& v : secondaries) scale = std::max(scale, magnitude(v));
  double worst = 0.0;
  for (std::size_t axis = 0; axis < 3; ++axis) {
    std::vector<double> terms = {pre[axis], -post[axis]};
    for (const auto& v : secondaries) terms.push_back(-v[axis]);
    for (const double t : terms) {
      if (!std::isfinite(t)) return std::nan("");
    }
    worst = std::max(worst, std::abs(formal::compensatedSum(terms.data(), terms.size())));
  }
  return scale == 0.0 ? 0.0 : worst / scale;
}

// Stated tolerance for relativeMomentumResidual on a scatter that hands kinetic energy T to a
// particle of mass m. Its momentum sqrt(T (T + 2m)) is formed from T = E - E', which carries a
// rounding error of a few ulp of E; for T << m that error grows by sqrt(m / 2T) relative to E
// (for a photon: 1 / (eps sqrt(2 (1 - cos theta)))). The bound is kRelativeTolerance plus eight
// times that rounding model; it says how far doubles can miss the real-valued Lean statement.
inline double momentumRoundingBound(double kineticEnergy, double mass) {
  if (!(kineticEnergy > 0.0) || !(mass > 0.0)) return kRelativeTolerance;
  return kRelativeTolerance +
         8.0 * std::numeric_limits<double>::epsilon() * std::sqrt(mass / (2.0 * kineticEnergy));
}

}  // namespace energy_balance
}  // namespace sim
}  // namespace trech
