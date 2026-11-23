#pragma once

// Least-squares error from summed statistics, as the domain learner scores
// candidate splits (DomainLearner.cpp, `scoreCuts`).
//
// For rows with weights w, basis rows phi and targets y, the sufficient
// statistics are A = sum w phi phi^T (p x p), b = sum w phi y^T (p x T) and
// c = sum w y^2 (per target, summed). For any coefficients beta (p x T),
//   sum w |y - phi beta|^2 = c - 2 <beta, b> + <beta, A beta>,
// and the statistics of disjoint row sets add, so prefix sums score every cut.
// Lean pair `Trech.Methods.LeastSquares` (formal/Trech/Methods/LeastSquares.lean):
// `sse_eq_stat`, `gram_union`, `moment_union`, `yy_union`, `split_le_parent`,
// `split_le_parent_ridge`, `bicGate_iff`, `bicGate_rejects`.
// The identity holds over the reals; in doubles the statistic form cancels
// c against 2 <beta, b>, so it is accurate to about eps * c, not eps * SSE.
//
// LibTorch is a required TRECH dependency (TRECH_ML_BACKEND=torch).

#include <ATen/ATen.h>

#include <algorithm>
#include <cmath>

namespace trech::ml {

// Batched: a is (m x p x p), b and betas are (m x p x T), c is (m). Returns
// the (m) total squared errors, one per batch entry.
inline at::Tensor sseFromStatistics(const at::Tensor& a, const at::Tensor& b, const at::Tensor& c,
                                    const at::Tensor& betas) {
  return c - 2.0 * (betas * b).sum({1, 2}) + (betas * a.bmm(betas)).sum({1, 2});
}

// The learner's BIC gate on a candidate split: n_eff * log(score / sseParent)
// + penalty < 0, with the score floored at 1e-300. Lean `bicGate_iff` shows it
// accepts exactly when score < sseParent * exp(-penalty / n_eff), and
// `bicGate_rejects` that a split not lowering the error is never accepted.
inline bool bicSplitAccepted(double neff, double score, double sseParent, double penalty) {
  return neff * std::log(std::max(score, 1e-300) / sseParent) + penalty < 0.0;
}

}  // namespace trech::ml
