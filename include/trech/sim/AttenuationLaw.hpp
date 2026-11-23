#pragma once

// Memorylessness of Beer-Lambert survival at Geant4's own attenuation coefficients.
//
// A `beer_lambert` analytic check predicts the uncollided transmission exp(-mu x) from the
// linear attenuation coefficient mu that Geant4's cross sections give for its material and
// energy (AnalyticCrossCheck.cpp). The Lean pair Trech.Laws.Attenuation.survival_add states
// exp(-mu (x + y)) = exp(-mu x) exp(-mu y) over the reals. This check evaluates both sides at
// that mu over cuts of the check's own path, x + y = L with x = L k / 10 (k = 1..9), plus the
// doubled path (x = y = L). It observes only: RunAction records it at run end, in runs that
// configure a beer_lambert check, and nothing reads it back.
//
// Doubles: the two sides differ by about 2 ulp (exp rounds each factor), so the tolerance is
// the pair's stated 2e-15 relative, as in tests/test_formal_laws.cpp.

#include "trech/core/FormalLaws.hpp"

#include <cmath>
#include <utility>
#include <vector>

namespace trech::sim::attenuation_law {

inline constexpr double kRelativeTolerance = 2e-15;

// One coefficient/path pair per available beer_lambert check (mu in 1/mm, path in mm).
inline formal::LawCheck memorylessAtCoefficients(const std::vector<std::pair<double, double>>& muAndPath) {
  std::vector<double> joint, split;
  for (const auto& [mu, path] : muAndPath) {
    std::vector<std::pair<double, double>> cuts;
    for (int k = 1; k <= 9; ++k) cuts.push_back({path * k / 10.0, path - path * k / 10.0});
    cuts.push_back({path, path});
    for (const auto& [x, y] : cuts) {
      joint.push_back(std::exp(-mu * (x + y)));
      split.push_back(std::exp(-mu * x) * std::exp(-mu * y));
    }
  }
  return formal::checkAgreement("attenuation.memoryless", "Trech.Laws.Attenuation.survival_add", joint, split,
                                0.0, kRelativeTolerance);
}

}  // namespace trech::sim::attenuation_law
