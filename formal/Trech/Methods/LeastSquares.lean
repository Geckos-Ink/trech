module

public import Mathlib.Algebra.BigOperators.Ring.Finset
import Mathlib.Algebra.BigOperators.Group.Finset.Sigma
public import Mathlib.Basic.Real.Basic
import Mathlib.Tactic.Ring
import Mathlib.Tactic.Linarith
public import Mathlib.Analysis.SpecialFunctions.Log.Basic

/-!
# The split score of the engine's domain learner (`ctx.learnDomains`)

Role: `method_property`. These theorems state why the domain learner may score every candidate
split from summed statistics instead of refitting each side; they say nothing about any
domain's law.

Classic implementation (the running path): `scoreCuts` in `src/ml/DomainLearner.cpp`, through
`sseFromStatistics` in `include/trech/ml/LeastSquaresStatistics.hpp`. For the rows `s` of a
side, with weights `w`, basis rows `φ i` and target `y`, the learner sums the Gram matrix
`A = ∑ w φ φᵀ`, the moment `b = ∑ w φ y` and `c = ∑ w y²` over chunks between candidate cuts,
takes prefix sums for the left side, subtracts them from the total for the right side, solves
each side's (ridge) normal equations for `β`, and scores the cut by `c − 2 β·b + β·A β` per
target, summed over both sides.

* `sse_eq_stat` (with Mathlib's `Finset.sum_comm` and `Finset.mul_sum`): for any coefficients `β`, the weighted squared error of `β` on the rows equals
  `c − 2 β·b + β·A β` built from those rows' statistics (one target; the learner sums targets).
* `gram_union`, `moment_union`, `yy_union`: the statistics of disjoint row sets add (Mathlib's
  `Finset.sum_union`), so prefix sums give the left side and total minus prefix the right one.
* `split_le_parent`: if each side's coefficients minimise that side's error, the two sides'
  errors together never exceed the parent's error at any shared coefficients. A split therefore
  never raises the training error, which is why the learner gates splits by a BIC penalty and
  two-fold cross-validation rather than by the error alone.

* `split_le_parent_ridge`: with the learner's ridge terms `λL, λR ≥ 0` (scaled per side), if
  each side's `β` minimises its penalised error, the split's error exceeds the parent's at any
  shared `β` by at most `(λL + λR) · ‖β‖²`. The engine's penalty is about `10⁻⁹` of the mean
  Gram diagonal, so the excess is negligible next to the BIC penalty.
* `bicGate_iff`: the learner's gate `n · log(S / S₀) + pen < 0` accepts a split exactly when its
  error falls below `S₀ · exp(−pen / n)`; `bicGate_rejects` shows that with a nonnegative
  penalty a split that does not lower the error is never accepted.

The identity holds for any `β`, so it covers the ridge solutions the learner computes. The
learner's reduced affine fit for a small side is a minimiser over a subspace, which the
inequalities do not cover. Over the
reals; in doubles the statistic form cancels (`c` and `2β·b` are close for a good fit), which the
conformance test bounds. Conformance: `tests/test_formal_laws.cpp`.
-/

@[expose] public section

open Finset

namespace Trech.Methods.LeastSquares

variable {ι P : Type*} [Fintype P]

/-- Weighted squared error of coefficients `β` on the rows `s`. -/
def sse (s : Finset ι) (w y : ι → ℝ) (φ : ι → P → ℝ) (β : P → ℝ) : ℝ :=
  ∑ i ∈ s, w i * (y i - ∑ k, φ i k * β k) ^ 2

/-- Weighted Gram matrix `A = ∑ w φ φᵀ` of the rows `s`. -/
def gram (s : Finset ι) (w : ι → ℝ) (φ : ι → P → ℝ) (k l : P) : ℝ := ∑ i ∈ s, w i * φ i k * φ i l

/-- Weighted moment `b = ∑ w φ y` of the rows `s`. -/
def moment (s : Finset ι) (w y : ι → ℝ) (φ : ι → P → ℝ) (k : P) : ℝ := ∑ i ∈ s, w i * φ i k * y i

/-- Weighted target energy `c = ∑ w y²` of the rows `s`. -/
def yy (s : Finset ι) (w y : ι → ℝ) : ℝ := ∑ i ∈ s, w i * y i ^ 2

/-- The learner's score from statistics: `c − 2 β·b + β·A β`. -/
def sseStat (A : P → P → ℝ) (b : P → ℝ) (c : ℝ) (β : P → ℝ) : ℝ :=
  c - 2 * ∑ k, β k * b k + ∑ k, ∑ l, β k * A k l * β l

theorem sse_eq_stat (s : Finset ι) (w y : ι → ℝ) (φ : ι → P → ℝ) (β : P → ℝ) :
    sse s w y φ β = sseStat (gram s w φ) (moment s w y φ) (yy s w y) β := by
  unfold sse sseStat gram moment yy
  have hb : ∑ k, β k * ∑ i ∈ s, w i * φ i k * y i =
      ∑ i ∈ s, w i * y i * ∑ k, φ i k * β k := by
    simp only [Finset.mul_sum]
    rw [Finset.sum_comm]
    refine Finset.sum_congr rfl fun i _ => Finset.sum_congr rfl fun k _ => ?_
    ring
  have hA : ∑ k, ∑ l, β k * (∑ i ∈ s, w i * φ i k * φ i l) * β l =
      ∑ i ∈ s, w i * ((∑ k, φ i k * β k) * ∑ l, φ i l * β l) := by
    symm
    calc ∑ i ∈ s, w i * ((∑ k, φ i k * β k) * ∑ l, φ i l * β l)
        = ∑ i ∈ s, ∑ k, ∑ l, β k * (w i * φ i k * φ i l) * β l := by
          refine Finset.sum_congr rfl fun i _ => ?_
          rw [Finset.sum_mul_sum, Finset.mul_sum]
          refine Finset.sum_congr rfl fun k _ => ?_
          rw [Finset.mul_sum]
          refine Finset.sum_congr rfl fun l _ => ?_
          ring
      _ = ∑ k, ∑ i ∈ s, ∑ l, β k * (w i * φ i k * φ i l) * β l := Finset.sum_comm
      _ = ∑ k, ∑ l, ∑ i ∈ s, β k * (w i * φ i k * φ i l) * β l :=
          Finset.sum_congr rfl fun _ _ => Finset.sum_comm
      _ = _ := by simp only [Finset.mul_sum, Finset.sum_mul]
  rw [hb, hA, Finset.mul_sum, ← Finset.sum_sub_distrib, ← Finset.sum_add_distrib]
  refine Finset.sum_congr rfl fun i _ => ?_
  ring

variable [DecidableEq ι]

omit [Fintype P] in
theorem gram_union {s t : Finset ι} (h : Disjoint s t) (w : ι → ℝ) (φ : ι → P → ℝ) (k l : P) :
    gram (s ∪ t) w φ k l = gram s w φ k l + gram t w φ k l :=
  Finset.sum_union h

omit [Fintype P] in
theorem moment_union {s t : Finset ι} (h : Disjoint s t) (w y : ι → ℝ) (φ : ι → P → ℝ) (k : P) :
    moment (s ∪ t) w y φ k = moment s w y φ k + moment t w y φ k :=
  Finset.sum_union h

theorem yy_union {s t : Finset ι} (h : Disjoint s t) (w y : ι → ℝ) :
    yy (s ∪ t) w y = yy s w y + yy t w y :=
  Finset.sum_union h

/-- Separately fitted sides never do worse on their rows than one shared fit. -/
theorem split_le_parent {s t : Finset ι} (h : Disjoint s t) (w y : ι → ℝ) (φ : ι → P → ℝ)
    (βL βR β : P → ℝ) (hL : sse s w y φ βL ≤ sse s w y φ β)
    (hR : sse t w y φ βR ≤ sse t w y φ β) :
    sse s w y φ βL + sse t w y φ βR ≤ sse (s ∪ t) w y φ β := by
  unfold sse at *
  rw [Finset.sum_union h]
  linarith

/-- Ridge version: separately minimised penalised sides exceed the parent's error at a shared
`β` by at most the penalty that `β` pays on both sides. -/
theorem split_le_parent_ridge {s t : Finset ι} (h : Disjoint s t) (w y : ι → ℝ)
    (φ : ι → P → ℝ) (βL βR β : P → ℝ) (lL lR : ℝ) (hlL : 0 ≤ lL) (hlR : 0 ≤ lR)
    (hL : sse s w y φ βL + lL * ∑ k, βL k ^ 2 ≤ sse s w y φ β + lL * ∑ k, β k ^ 2)
    (hR : sse t w y φ βR + lR * ∑ k, βR k ^ 2 ≤ sse t w y φ β + lR * ∑ k, β k ^ 2) :
    sse s w y φ βL + sse t w y φ βR ≤ sse (s ∪ t) w y φ β + (lL + lR) * ∑ k, β k ^ 2 := by
  have nL : 0 ≤ lL * ∑ k, βL k ^ 2 := mul_nonneg hlL (Finset.sum_nonneg fun k _ => sq_nonneg _)
  have nR : 0 ≤ lR * ∑ k, βR k ^ 2 := mul_nonneg hlR (Finset.sum_nonneg fun k _ => sq_nonneg _)
  have hs : sse (s ∪ t) w y φ β = sse s w y φ β + sse t w y φ β := by
    unfold sse
    exact Finset.sum_union h
  rw [hs]
  nlinarith

/-- The learner's BIC gate is a threshold on the split's error. -/
theorem bicGate_iff {n S S₀ pen : ℝ} (hn : 0 < n) (hS : 0 < S) (hS₀ : 0 < S₀) :
    n * Real.log (S / S₀) + pen < 0 ↔ S < S₀ * Real.exp (-pen / n) := by
  have hq : 0 < S / S₀ := div_pos hS hS₀
  constructor
  · intro hg
    have hlog : Real.log (S / S₀) < -pen / n := by
      rw [lt_div_iff₀ hn]
      linarith
    have := (Real.log_lt_iff_lt_exp hq).1 hlog
    rwa [div_lt_iff₀ hS₀, mul_comm] at this
  · intro hlt
    have hq' : S / S₀ < Real.exp (-pen / n) := by
      rw [div_lt_iff₀ hS₀, mul_comm]
      exact hlt
    have hlog := (Real.log_lt_iff_lt_exp hq).2 hq'
    rw [lt_div_iff₀ hn] at hlog
    linarith

/-- With a nonnegative penalty, a split that does not lower the error is never accepted. -/
theorem bicGate_rejects {n S S₀ pen : ℝ} (hn : 0 < n) (hS₀ : 0 < S₀) (hpen : 0 ≤ pen)
    (hle : S₀ ≤ S) : ¬ (n * Real.log (S / S₀) + pen < 0) := by
  have h1 : 1 ≤ S / S₀ := by rw [le_div_iff₀ hS₀]; linarith
  have : 0 ≤ Real.log (S / S₀) := Real.log_nonneg h1
  have : 0 ≤ n * Real.log (S / S₀) := mul_nonneg hn.le this
  linarith

end Trech.Methods.LeastSquares
