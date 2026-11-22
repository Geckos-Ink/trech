#pragma once

// Classic-side checks for the optional Lean law pairs (docs/engine/formal_laws.md).
//
// Every law with a Lean definition keeps a classic C++/JS implementation, and that classic
// implementation is the one that runs. These functions check the classic side against the
// statement of its Lean pair: invariants (a conserved total, bounds, a normalised probability
// vector), the hypotheses a theorem needs (a permutation, an involution, velocity-set moments)
// and agreement between two classic implementations. They name no material, scenario or
// domain, never consume RNG and never change a value they check.
//
// A check records the Lean declaration it pairs with. Whether that Lean proof was checked is
// not known here: Lean is optional, and `lean_status` stays "not_checked_by_this_check".

#include <nlohmann/json.hpp>

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace trech {
namespace formal {

struct LawCheck {
  std::string law;               // manifest id, e.g. "lattice.collision_conserves_mass"
  std::string leanDeclaration;   // e.g. "Trech.Methods.Lattice.relaxTRT_sum_eq"
  std::string kind;              // "invariant", "hypothesis", "agreement"
  std::size_t samples = 0;
  std::size_t violations = 0;
  double maxAbsError = 0.0;      // largest deviation found (0 when every sample holds exactly)
  double tolerance = 0.0;
  bool passed = false;
  std::string detail;            // first violation, or empty

  nlohmann::json toJson() const;
};

// Compensated (Neumaier) sum in index order, so a conservation check does not report its own
// rounding as a violation.
double compensatedSum(const double* values, std::size_t count);

// |sum(after) - sum(before)| <= tolerance * max(1, |sum(before)|).
LawCheck checkConservedTotal(const std::string& law, const std::string& lean,
                             const std::vector<double>& before, const std::vector<double>& after,
                             double relativeTolerance);

// lower[i] - tolerance <= values[i] <= upper[i] + tolerance for every sample.
LawCheck checkWithinBounds(const std::string& law, const std::string& lean,
                           const std::vector<double>& values, const std::vector<double>& lower,
                           const std::vector<double>& upper, double tolerance);

// Every entry finite and >= -tolerance, and |sum - 1| <= tolerance.
LawCheck checkProbabilityVector(const std::string& law, const std::string& lean,
                                const std::vector<double>& probabilities, double tolerance);

// |a[i] - b[i]| <= absTolerance + relTolerance * max(|a[i]|, |b[i]|) for every sample.
LawCheck checkAgreement(const std::string& law, const std::string& lean,
                        const std::vector<double>& a, const std::vector<double>& b,
                        double absTolerance, double relTolerance);

// Hypothesis: map[k] in [0, count) and every target hit exactly once (a bijection).
LawCheck checkPermutation(const std::string& law, const std::string& lean, const int32_t* map,
                          std::size_t count);

// Hypothesis: map[map[k]] == k for every k (opposite-direction table).
LawCheck checkInvolution(const std::string& law, const std::string& lean, const int32_t* map,
                         std::size_t count);

// Hypothesis behind "sum feq = rho" and "sum of the Guo forcing = 0": the velocity set's
// weights satisfy sum w = 1, sum w c_a = 0 and sum w c_a c_b = cs2 delta_ab over the first
// `dimensions` axes (x, y, z); the second moment along an unused axis must be 0.
LawCheck checkVelocityMoments(const std::string& law, const std::string& lean, std::size_t q,
                              const double* cx, const double* cy, const double* cz,
                              const double* w, double cs2, int dimensions, double tolerance);

}  // namespace formal
}  // namespace trech
