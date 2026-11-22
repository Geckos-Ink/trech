module

public import Mathlib.Analysis.Complex.Exponential
import Mathlib.Tactic.Linarith
import Mathlib.Tactic.Ring

/-!
# Exponential attenuation (Beer–Lambert survival)

Role: `reference`. The `beer_lambert` analytic cross-check predicts the unscattered fraction
`exp(-μ x)` from Geant4's own per-process attenuation coefficients and compares it with the
measured transmission. Geant4 itself samples interaction lengths from the same memoryless law.

Classic implementations (the running path):
* `src/sim/AnalyticCrossCheck.cpp` — `std::exp(-result.muTotalPerMm * result.pathLengthMm)`;
* `js/trech_formal_laws.js` — `attenuation.survival`.

Conformance: `tests/test_formal_laws.cpp`. Mathlib already proves the exponential facts used
here (`Real.exp_add`, `Real.exp_pos`, `Real.exp_le_exp`, `Real.exp_le_one_iff`); this file only
specialises them to the attenuation law.
-/

@[expose] public section

namespace Trech.Laws.Attenuation

/-- Probability that a particle crosses a path `x` without interacting, for a total linear
attenuation coefficient `μ`. -/
noncomputable def survival (μ x : ℝ) : ℝ := Real.exp (-(μ * x))

theorem survival_zero (μ : ℝ) : survival μ 0 = 1 := by
  simp [survival]

/-- Memorylessness: crossing `x + y` is crossing `x`, then `y`. -/
theorem survival_add (μ x y : ℝ) : survival μ (x + y) = survival μ x * survival μ y := by
  unfold survival
  rw [← Real.exp_add]
  congr 1
  ring

theorem survival_pos (μ x : ℝ) : 0 < survival μ x := Real.exp_pos _

theorem survival_le_one {μ x : ℝ} (hμ : 0 ≤ μ) (hx : 0 ≤ x) : survival μ x ≤ 1 := by
  unfold survival
  rw [Real.exp_le_one_iff]
  linarith [mul_nonneg hμ hx]

/-- A longer path never transmits more. -/
theorem survival_antitone {μ x y : ℝ} (hμ : 0 ≤ μ) (h : x ≤ y) :
    survival μ y ≤ survival μ x := by
  unfold survival
  rw [Real.exp_le_exp]
  nlinarith [mul_le_mul_of_nonneg_left h hμ]

end Trech.Laws.Attenuation
