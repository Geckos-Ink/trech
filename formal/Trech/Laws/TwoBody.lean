module

public import Mathlib.Analysis.InnerProductSpace.Basic
import Mathlib.Tactic.Linarith
import Mathlib.Tactic.LinearCombination

/-!
# Compton scattering from four-momentum conservation

Role: `reference`. A photon of energy `E` and momentum `k` (`‖k‖ = E`, units with `c = 1`)
scatters off an electron of mass `m` at rest. The photon leaves with energy `E'` and momentum
`k'` (`‖k'‖ = E'`); the electron leaves with energy `Ee` and momentum `p`, on its mass shell
`Ee² = ‖p‖² + m²`. Energy and momentum are conserved: `E + m = E' + Ee` and `k = k' + p`.
Then `m (E - E') = E E' - ⟪k, k'⟫`, which with `⟪k, k'⟫ = E E' cos θ` is the Compton relation
`E' (m + E (1 - cos θ)) = m E`, i.e. `E'/E = 1 / (1 + ε (1 - cos θ))` with `ε = E/m`.

Classic implementations (the running path):
* `include/trech/sim/KleinNishina.hpp` — `scatteredEnergyRatio`, the relation itself, which
  `SteppingAction` compares with each recorded first Compton scatter (`kinematicResidual`);
* `include/trech/sim/EnergyBalance.hpp` — `relativeMomentumResidual`, the momentum-conservation
  hypothesis `k = k' + p`, checked on the same recorded steps.

Mathlib search (2026-11-22): no Compton or four-momentum statement; `norm_sub_sq_real` gives the
vector identity used here.
-/

@[expose] public section

namespace Trech.Laws.TwoBody

variable {V : Type*} [NormedAddCommGroup V] [InnerProductSpace ℝ V]

/-- Lorentz-invariant form: conservation fixes the photon's energy loss by the angle. -/
theorem compton_invariant {E E' Ee m : ℝ} {k k' p : V}
    (hk : ‖k‖ = E) (hk' : ‖k'‖ = E') (hshell : Ee ^ 2 = ‖p‖ ^ 2 + m ^ 2)
    (henergy : E + m = E' + Ee) (hmomentum : k = k' + p) :
    m * (E - E') = E * E' - inner ℝ k k' := by
  have hp : p = k - k' := by rw [hmomentum]; abel
  have hnorm : ‖p‖ ^ 2 = E ^ 2 - 2 * inner ℝ k k' + E' ^ 2 := by
    rw [hp, norm_sub_sq_real, hk, hk']
  have hEe : Ee = E + m - E' := by linarith
  rw [hEe, hnorm] at hshell
  linear_combination hshell / 2

/-- The Compton relation in its angle form: `E' (m + E (1 - cos θ)) = m E`. -/
theorem compton_relation {E E' Ee m c : ℝ} {k k' p : V}
    (hk : ‖k‖ = E) (hk' : ‖k'‖ = E') (hshell : Ee ^ 2 = ‖p‖ ^ 2 + m ^ 2)
    (henergy : E + m = E' + Ee) (hmomentum : k = k' + p)
    (hcos : inner ℝ k k' = E * E' * c) :
    E' * (m + E * (1 - c)) = m * E := by
  have h := compton_invariant hk hk' hshell henergy hmomentum
  rw [hcos] at h
  linear_combination -h

end Trech.Laws.TwoBody
