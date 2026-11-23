module

public import Mathlib.Algebra.BigOperators.Ring.Finset
public import Mathlib.Algebra.Order.BigOperators.Group.Finset
public import Mathlib.Basic.Real.Basic
import Mathlib.Tactic.Linarith
import Mathlib.Tactic.NormNum
import Mathlib.Tactic.Ring

/-!
# The arbiter's decayed prequential scores

Role: `method_property`. `MethodArbiter` (and through it `ctx.evolveField`, whose methods it
selects) keeps every running score by one update per graded call: `s ← λ s + x`, with
`λ = policyForgetting` and `x` the call's contribution (summed squared error, row count, log
call RMSE or `1` per call in which the method predicted, the policy log-ratio, the error
learner's squared RMSE). These theorems say what such a score is and what its ranking keeps:

* `decayed_eq_sum`: after `T` calls the score is `∑ λ^(T-1-t) x_t`, a weighted sum in which a
  call's weight depends only on its age. So the decayed mean `ewSq / ewN` is the weighted
  squared score of `Trech.Methods.Arbiter` with weights `λ^age`, and `squaredScore_mean_le`
  applies to it unchanged.
* `decayed_mono`, `decayed_nonneg`: for `λ ≥ 0` the score is monotone in each call's value.
* `decayedMean_le`, `decayedMean_lt`: the leader ranks by the decayed mean log call error
  `ewLog / ewCalls`. When two methods predicted in the same calls, the one no worse on every
  call ranks no worse, and strictly better when it is strictly better on one call (`λ > 0`).
* `decayedMean_needs_common_calls`: the guarantee needs the shared calls. A method that is
  better on the only call both predicted, but abstained on an easy call, ranks behind.

Classic implementation (the running path): `decayedUpdate` in
`include/trech/ml/DecayedScore.hpp`, called by `src/ml/MethodArbiter.cpp` for every decayed
score, compiled without floating-point contraction.

Conformance: `tests/test_formal_laws.cpp` (`decayPairs`) folds `decayedUpdate` against the
closed form, compares the arbiter's exported `ew_calls` with `∑ λ^age`, runs a method better on
every element of every call against a biased fallback (it leads), and runs the abstaining case
of `decayedMean_needs_common_calls` on the engine (it does not lead).

Mathlib has no moving-average statement; the proofs use `Finset.sum_range_succ`,
`Finset.mul_sum`, `Finset.sum_lt_sum` and `div_le_div_of_nonneg_right`.
-/

@[expose] public section

open Finset

namespace Trech.Methods.Decay

/-- One decayed update of a running score: `λ s + x`. -/
def decayStep (lam s x : ℝ) : ℝ := lam * s + x

/-- The score after the first `T` calls, starting from zero. -/
def decayed (lam : ℝ) (x : ℕ → ℝ) : ℕ → ℝ
  | 0 => 0
  | T + 1 => decayStep lam (decayed lam x T) (x T)

/-- Closed form: each call is weighted by `λ` to the power of its age. -/
theorem decayed_eq_sum (lam : ℝ) (x : ℕ → ℝ) (T : ℕ) :
    decayed lam x T = ∑ t ∈ range T, lam ^ (T - 1 - t) * x t := by
  induction T with
  | zero => simp [decayed]
  | succ T ih =>
    rw [decayed, decayStep, ih, Finset.sum_range_succ, Finset.mul_sum]
    congr 1
    · refine Finset.sum_congr rfl fun t ht => ?_
      have htT : t < T := Finset.mem_range.mp ht
      have hexp : T + 1 - 1 - t = (T - 1 - t) + 1 := by omega
      rw [hexp, pow_succ]
      ring
    · simp

/-- With `λ ≥ 0` the score is monotone in every call's value. -/
theorem decayed_mono {lam : ℝ} (hlam : 0 ≤ lam) {x y : ℕ → ℝ} (T : ℕ)
    (hxy : ∀ t < T, x t ≤ y t) : decayed lam x T ≤ decayed lam y T := by
  induction T with
  | zero => simp [decayed]
  | succ T ih =>
    simp only [decayed, decayStep]
    have h1 := ih fun t ht => hxy t (Nat.lt_succ_of_lt ht)
    have h2 := hxy T (Nat.lt_succ_self T)
    nlinarith [mul_le_mul_of_nonneg_left h1 hlam]

/-- Nonnegative contributions give a nonnegative score. -/
theorem decayed_nonneg {lam : ℝ} (hlam : 0 ≤ lam) {x : ℕ → ℝ} (T : ℕ)
    (hx : ∀ t < T, 0 ≤ x t) : 0 ≤ decayed lam x T := by
  have h := decayed_mono hlam (x := fun _ => 0) (y := x) T hx
  have h0 : decayed lam (fun _ => 0) T = 0 := by simp [decayed_eq_sum]
  linarith

/-- Leader ranking with shared calls: `c t ≥ 0` is the weight of call `t` (the arbiter uses `1`
when the method predicted, else `0`), the same for both methods. A method no worse on every call
has a decayed mean log error no greater. -/
theorem decayedMean_le {lam : ℝ} (hlam : 0 ≤ lam) (c a b : ℕ → ℝ) (T : ℕ)
    (hc : ∀ t < T, 0 ≤ c t) (hab : ∀ t < T, a t ≤ b t) :
    decayed lam (fun t => c t * a t) T / decayed lam c T ≤
      decayed lam (fun t => c t * b t) T / decayed lam c T :=
  div_le_div_of_nonneg_right
    (decayed_mono hlam T fun t ht => mul_le_mul_of_nonneg_left (hab t ht) (hc t ht))
    (decayed_nonneg hlam T hc)

/-- Strictly better on one shared call it weighs (`c t₀ > 0`, `λ > 0`) ranks strictly first. -/
theorem decayedMean_lt {lam : ℝ} (hlam : 0 < lam) (c a b : ℕ → ℝ) (T : ℕ)
    (hc : ∀ t < T, 0 ≤ c t) (hab : ∀ t < T, a t ≤ b t)
    {t₀ : ℕ} (ht₀ : t₀ < T) (hc₀ : 0 < c t₀) (hab₀ : a t₀ < b t₀) :
    decayed lam (fun t => c t * a t) T / decayed lam c T <
      decayed lam (fun t => c t * b t) T / decayed lam c T := by
  have hmem : t₀ ∈ range T := Finset.mem_range.mpr ht₀
  have hw : ∀ t, 0 < lam ^ (T - 1 - t) := fun t => pow_pos hlam _
  apply div_lt_div_of_pos_right
  · rw [decayed_eq_sum, decayed_eq_sum]
    refine Finset.sum_lt_sum (fun t ht => ?_) ⟨t₀, hmem, ?_⟩
    · have := Finset.mem_range.mp ht
      exact mul_le_mul_of_nonneg_left (mul_le_mul_of_nonneg_left (hab t this) (hc t this))
        (hw t).le
    · exact mul_lt_mul_of_pos_left (mul_lt_mul_of_pos_left hab₀ hc₀) (hw t₀)
  · rw [decayed_eq_sum]
    refine Finset.sum_pos' (fun t ht => ?_) ⟨t₀, hmem, mul_pos (hw t₀) hc₀⟩
    exact mul_nonneg (hw t).le (hc t (Finset.mem_range.mp ht))

/-- Without shared calls the ranking can invert. Over two calls (`λ = 1`), method `b` predicts
in both with log errors `0` and `10`; method `a` predicts only in the second, with `9`. `a` is
better on the only shared call, yet its mean (`9`) is above `b`'s (`5`). -/
theorem decayedMean_needs_common_calls :
    decayed 1 (fun t => (if t = 1 then (1 : ℝ) else 0) * 9) 2 /
        decayed 1 (fun t => if t = 1 then (1 : ℝ) else 0) 2 >
      decayed 1 (fun t => (1 : ℝ) * (if t = 1 then 10 else 0)) 2 /
        decayed 1 (fun _ => (1 : ℝ)) 2 := by
  simp only [decayed_eq_sum, Finset.sum_range_succ, Finset.sum_range_zero]
  norm_num

end Trech.Methods.Decay
