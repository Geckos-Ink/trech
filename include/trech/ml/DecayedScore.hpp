#pragma once

// Decayed running scores of the method arbiter (and of ctx.evolveField, which it selects for).
//
// Every running score of MethodArbiter advances once per graded call by
// score <- forgetting * score + contribution. Lean pair: Trech.Methods.Decay
// (formal/Trech/Methods/Decay.lean): after T calls the score is sum_t forgetting^(T-1-t) x_t
// (decayed_eq_sum), so a decayed mean is a weighted mean with weights forgetting^age; with
// forgetting >= 0 the score is monotone in each contribution, and a method no worse on every
// call it shares with another ranks no worse by decayed mean (decayedMean_le / _lt). The
// guarantee needs shared calls (decayedMean_needs_common_calls).
//
// Callers compile with -ffp-contract=off (see CMakeLists.txt), so the update rounds the product
// and the sum separately on every compiler.

namespace trech::ml {

inline double decayedUpdate(double forgetting, double score, double contribution) {
  return forgetting * score + contribution;
}

}  // namespace trech::ml
