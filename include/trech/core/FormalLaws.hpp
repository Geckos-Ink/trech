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
  double tolerance = 0.0;         // absolute tolerance (agreement) or the check's own bound
  double relativeTolerance = 0.0; // agreement only: |a - b| <= tolerance + this x max(|a|, |b|)
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

// Run record of the law checks performed (docs/engine/formal_laws.md, "In run outputs").
//
// Engine code (origin "engine", e.g. Lattice::checkLaws) and validation companions (origin
// "validation", through TRECH_FORMAL_LAWS.record) report each check here. The CLI drains the
// record at every run end: a non-empty result is written as `law_checks` in the run_end scores
// and summarised by `provenanceBlock` as the provenance `formal` object; an empty one writes
// nothing, so runs without checks keep their bytes. Checks with the same (origin, law, Lean
// declaration) merge: `count` checks, summed samples and violations, the largest error and
// tolerance, passed only if every one passed, and the lexicographically first detail of the
// failing (else passing) ones, so the result does not depend on thread order. Thread-safe.
// Never consumes RNG and never feeds anything back into a run.
void recordRunCheck(const LawCheck& check, const std::string& origin);
// Merged records since the previous call, sorted by origin, law and declaration; then cleared.
nlohmann::json takeRunChecks();
// SHA-256 of formal/laws.json, embedded at build time ("" when the build had none).
const std::string& manifestSha256();
// One SHA-256 over the manifest and every Lean module (formal/Trech.lean, formal/Trech/**.lean):
// SHA-256 of "<path>\n<sha256>\n" per file in sorted path order, embedded at build time.
const std::string& sourcesSha256();
// The provenance `formal` object for drained `checks` (trech_formal_provenance_v1): manifest
// identity, cited declarations, check counts and the Lean status. `auditPath` (from
// --formal-audit or $TRECH_FORMAL_AUDIT, may be empty) names a check_lean_laws.py --report file;
// its identity is copied, and `lean_status` is "audited" only when the audit passed, matches
// this build's manifest and Lean sources (sourcesSha256) and lists every cited declaration with
// standard axioms only.
nlohmann::json provenanceBlock(const nlohmann::json& checks, const std::string& auditPath);

}  // namespace formal
}  // namespace trech
