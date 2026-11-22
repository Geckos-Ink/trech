module

public import Mathlib.Algebra.BigOperators.Ring.Finset
public import Mathlib.Analysis.SpecialFunctions.Log.Basic
import Mathlib.Tactic.Linarith
import Mathlib.Tactic.Ring

/-!
# The method arbiter's squared-error score is proper

Role: `method_property`. The engine's `MethodArbiter` grades each method by its squared error
against the reference (mean over outputs, per element), ranks methods by the log of that error
plus a positive floor, and selects the lowest. These theorems state why that rewards the
honest prediction: over any weighted sample, the squared score is minimised exactly by the
weighted mean (`squaredScore_mean_le`, strictly for any other value), and adding a positive
floor and taking the log keeps the error order (`logError_lt_iff`). They say nothing about any
physics.

Classic implementation (the running path): `src/ml/MethodArbiter.cpp` (`squaredError`, the
error learners' `log(error + floor)` targets, and the leader ranking by decayed mean log call
error).

Scope: the theorems cover one weighted sample (one graded call, or decayed weights over many).
The leader ranks by the decayed mean of log call RMSE, a geometric mean across calls, which
these statements do not cover.

Conformance: `tests/test_formal_laws.cpp` runs the classic arbiter on noisy references with a
mean-predicting method and two biased ones and checks that the mean method leads and has the
lowest score. Mathlib proves the measure-theoretic analogue (`ProbabilityTheory.variance` and
`variance_le_expectation_sq`) but not this finite weighted form; the log step specialises
`Real.log_lt_log_iff`.
-/

@[expose] public section

open Finset

namespace Trech.Methods.Arbiter

variable {E : Type*} [Fintype E]

/-- Weighted squared score of a constant prediction `p` against references `x`. -/
def squaredScore (w x : E → ℝ) (p : ℝ) : ℝ := ∑ e, w e * (x e - p) ^ 2

/-- Bias–variance split: the score of `p` is the score of the weighted mean `m` plus the total
weight times `(m - p)²`. The mean is given by `(∑ w) · m = ∑ w x`, so no division appears. -/
theorem squaredScore_decompose (w x : E → ℝ) (m p : ℝ)
    (hm : (∑ e, w e) * m = ∑ e, w e * x e) :
    squaredScore w x p = squaredScore w x m + (∑ e, w e) * (m - p) ^ 2 := by
  unfold squaredScore
  have split : ∀ e, w e * (x e - p) ^ 2 =
      w e * (x e - m) ^ 2 + ((m - p) ^ 2 * w e + 2 * (m - p) * (w e * x e) - 2 * (m - p) * m * w e) := by
    intro e
    ring
  simp only [split, Finset.sum_add_distrib, Finset.sum_sub_distrib, ← Finset.mul_sum]
  rw [← hm]
  ring

/-- The weighted mean has the lowest squared score (nonnegative total weight). -/
theorem squaredScore_mean_le (w x : E → ℝ) (m p : ℝ) (hw : 0 ≤ ∑ e, w e)
    (hm : (∑ e, w e) * m = ∑ e, w e * x e) :
    squaredScore w x m ≤ squaredScore w x p := by
  rw [squaredScore_decompose w x m p hm]
  exact le_add_of_nonneg_right (mul_nonneg hw (sq_nonneg _))

/-- Strictly proper: with positive total weight, any other prediction scores worse. -/
theorem squaredScore_mean_lt (w x : E → ℝ) (m p : ℝ) (hw : 0 < ∑ e, w e)
    (hm : (∑ e, w e) * m = ∑ e, w e * x e) (hp : p ≠ m) :
    squaredScore w x m < squaredScore w x p := by
  rw [squaredScore_decompose w x m p hm]
  have hd : m - p ≠ 0 := sub_ne_zero.mpr (Ne.symm hp)
  exact lt_add_of_pos_right _ (mul_pos hw (pow_pos (abs_pos.mpr hd) 2 |>.trans_eq (sq_abs _)))

/-- The arbiter's `log(error + floor)` keeps the order of nonnegative errors. -/
theorem logError_lt_iff {a b floor : ℝ} (hfloor : 0 < floor) (ha : 0 ≤ a) (hb : 0 ≤ b) :
    Real.log (a + floor) < Real.log (b + floor) ↔ a < b := by
  rw [Real.log_lt_log_iff (by linarith) (by linarith)]
  constructor <;> intro h <;> linarith

end Trech.Methods.Arbiter
