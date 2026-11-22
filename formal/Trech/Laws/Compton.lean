import Mathlib.Algebra.Order.Field.Basic
import Mathlib.Data.Real.Basic
import Mathlib.Tactic.Linarith
import Mathlib.Tactic.Ring

/-!
# Compton kinematics on a free electron at rest

Role: `reference` (the `compton_energy_transfer` analytic cross-check compares these formulas,
fed with Geant4's own electron mass, with the energy loss Geant4 samples). They never drive
transport.

Classic implementations (the running path):
* `include/trech/sim/KleinNishina.hpp` — `scatteredEnergyRatio`, `comptonEdgeFraction`;
* `js/trech_formal_laws.js` — `compton.scatteredEnergyRatio`, `compton.transferFraction`,
  `compton.edgeFraction`.

Conformance: `tests/test_formal_laws.cpp` samples the classic functions against the bounds
stated here. Statements are over `ℝ`; the classic code is IEEE-754 double.

`ε = E / (m_e c²)` is the reduced photon energy and `c = cos θ` the scattering angle cosine.
-/

namespace Trech.Laws.Compton

/-- Scattered-photon energy ratio `E'/E = 1 / (1 + ε (1 - cos θ))`. -/
noncomputable def scatteredEnergyRatio (ε c : ℝ) : ℝ := 1 / (1 + ε * (1 - c))

/-- Share of the photon energy given to the electron, `T/E = 1 - E'/E`. -/
noncomputable def transferFraction (ε c : ℝ) : ℝ := 1 - scatteredEnergyRatio ε c

/-- Compton edge, the back-scatter share `T_max/E = 2ε / (1 + 2ε)`. -/
noncomputable def edgeFraction (ε : ℝ) : ℝ := 2 * ε / (1 + 2 * ε)

theorem denom_pos {ε c : ℝ} (hε : 0 ≤ ε) (hc : c ≤ 1) : 0 < 1 + ε * (1 - c) := by
  have : 0 ≤ ε * (1 - c) := mul_nonneg hε (by linarith)
  linarith

/-- A scattered photon never gains energy. -/
theorem scatteredEnergyRatio_le_one {ε c : ℝ} (hε : 0 ≤ ε) (hc : c ≤ 1) :
    scatteredEnergyRatio ε c ≤ 1 := by
  unfold scatteredEnergyRatio
  rw [div_le_one (denom_pos hε hc)]
  have : 0 ≤ ε * (1 - c) := mul_nonneg hε (by linarith)
  linarith

/-- Back-scatter (`cos θ = -1`) is the largest energy loss. -/
theorem backscatter_le_scatteredEnergyRatio {ε c : ℝ} (hε : 0 ≤ ε) (hc₁ : -1 ≤ c)
    (hc : c ≤ 1) : 1 / (1 + 2 * ε) ≤ scatteredEnergyRatio ε c := by
  unfold scatteredEnergyRatio
  apply one_div_le_one_div_of_le (denom_pos hε hc)
  nlinarith [mul_nonneg hε (show (0 : ℝ) ≤ 1 + c by linarith)]

theorem edgeFraction_eq {ε : ℝ} (hε : 0 ≤ ε) : edgeFraction ε = 1 - 1 / (1 + 2 * ε) := by
  have h : (1 + 2 * ε) ≠ 0 := (show (0 : ℝ) < 1 + 2 * ε by linarith).ne'
  unfold edgeFraction
  rw [eq_sub_iff_add_eq, div_add_div _ _ h h, div_eq_one_iff_eq (mul_ne_zero h h)]
  ring

/-- The electron never takes a negative share. -/
theorem transferFraction_nonneg {ε c : ℝ} (hε : 0 ≤ ε) (hc : c ≤ 1) :
    0 ≤ transferFraction ε c := by
  unfold transferFraction
  linarith [scatteredEnergyRatio_le_one hε hc]

/-- The electron's share never exceeds the Compton edge. -/
theorem transferFraction_le_edge {ε c : ℝ} (hε : 0 ≤ ε) (hc₁ : -1 ≤ c) (hc : c ≤ 1) :
    transferFraction ε c ≤ edgeFraction ε := by
  rw [edgeFraction_eq hε]
  unfold transferFraction
  linarith [backscatter_le_scatteredEnergyRatio hε hc₁ hc]

/-- The edge is reached exactly at back-scatter. -/
theorem transferFraction_backscatter {ε : ℝ} (hε : 0 ≤ ε) :
    transferFraction ε (-1) = edgeFraction ε := by
  rw [edgeFraction_eq hε]
  unfold transferFraction scatteredEnergyRatio
  rw [show ε * (1 - -1 : ℝ) = 2 * ε by ring]

end Trech.Laws.Compton
