module

public import Mathlib.Algebra.BigOperators.Group.Finset.Basic
public import Mathlib.Basic.Real.Basic
import Mathlib.Algebra.Order.BigOperators.Group.Finset
import Mathlib.Tactic.Linarith

/-!
# Energy balance of a recorded step

Role: `reference`. A Geant4 step that turns an incoming particle of kinetic energy `ePre` into
an outgoing one of kinetic energy `ePost`, secondaries of kinetic energies `T i` and a local
deposit `d` conserves energy when `ePre + q = ePost + ∑ T i + d`, where `q` is the rest-mass
energy the step releases (`0` for Compton scattering).

Classic implementation (the running path): `include/trech/sim/EnergyBalance.hpp`
(`energy_balance::relativeResidual`), read in `src/sim/SteppingAction.cpp` from Geant4's own
step record (pre/post kinetic energy, `GetSecondaryInCurrentStep`, `GetTotalEnergyDeposit`) on
a primary photon's first Compton scatter. Conformance: `tests/test_formal_laws.cpp`; the
Geant4 run records the verdict as the engine law check `energy.step_balance`.

Mathlib already proves the pieces: `sub_eq_zero`, `Finset.single_le_sum`,
`Finset.sum_range_sub'` (telescoping) and `Finset.sum_add_distrib`. This file specialises them.
-/

@[expose] public section

open Finset

namespace Trech.Laws.EnergyBalance

variable {ι : Type*}

/-- Energy a step hands on: the secondaries' kinetic energies plus the local deposit. -/
def released (s : Finset ι) (T : ι → ℝ) (d : ℝ) : ℝ := ∑ i ∈ s, T i + d

/-- Imbalance of a step; the classic check evaluates it in doubles. -/
def residual (ePre q ePost : ℝ) (s : Finset ι) (T : ι → ℝ) (d : ℝ) : ℝ :=
  ePre + q - (ePost + released s T d)

/-- A step conserves energy exactly when its residual vanishes. -/
theorem residual_eq_zero_iff (ePre q ePost : ℝ) (s : Finset ι) (T : ι → ℝ) (d : ℝ) :
    residual ePre q ePost s T d = 0 ↔ ePre + q = ePost + released s T d := by
  unfold residual
  exact sub_eq_zero

theorem released_nonneg {s : Finset ι} {T : ι → ℝ} {d : ℝ} (hT : ∀ i ∈ s, 0 ≤ T i)
    (hd : 0 ≤ d) : 0 ≤ released s T d := by
  unfold released
  have := Finset.sum_nonneg hT
  linarith

/-- With no rest mass released, the outgoing particle never gains energy. -/
theorem post_le_pre {ePre ePost d : ℝ} {s : Finset ι} {T : ι → ℝ}
    (h : ePre = ePost + released s T d) (hT : ∀ i ∈ s, 0 ≤ T i) (hd : 0 ≤ d) :
    ePost ≤ ePre := by
  have := released_nonneg hT hd
  linarith

/-- With no rest mass released, no secondary carries more than the incoming energy. -/
theorem secondary_le_pre {ePre ePost d : ℝ} {s : Finset ι} {T : ι → ℝ}
    (h : ePre = ePost + released s T d) (hT : ∀ i ∈ s, 0 ≤ T i) (hd : 0 ≤ d)
    (hPost : 0 ≤ ePost) {j : ι} (hj : j ∈ s) : T j ≤ ePre := by
  have hsingle : T j ≤ ∑ i ∈ s, T i := Finset.single_le_sum hT hj
  unfold released at h
  linarith

/-- Balanced steps telescope along a track: the energy handed on over `n` steps is the drop in
kinetic energy plus the rest mass released. `k i` is the kinetic energy before step `i`. -/
theorem track_released_sum (n : ℕ) (k q r : ℕ → ℝ)
    (h : ∀ i ∈ range n, k i + q i = k (i + 1) + r i) :
    ∑ i ∈ range n, r i = (k 0 - k n) + ∑ i ∈ range n, q i := by
  have hr : ∀ i ∈ range n, r i = (k i - k (i + 1)) + q i := by
    intro i hi
    linarith [h i hi]
  rw [Finset.sum_congr rfl hr, Finset.sum_add_distrib, Finset.sum_range_sub']

end Trech.Laws.EnergyBalance
