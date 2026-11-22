import Mathlib.Algebra.BigOperators.Ring.Finset
import Mathlib.Data.Real.Basic
import Mathlib.Tactic.Ring

/-!
# Mass conservation of the engine's lattice method

Role: `method_property`. These theorems state why the engine-owned lattice Boltzmann method
conserves the summed populations; they say nothing about any material.

Classic implementation (the running path): `src/core/LatticeKinetic.cpp` — `flowStep`
(two-relaxation-time collision, then pull streaming `f[k] = post[src[k]]`).

Hypothesis checks and conformance: `tests/test_formal_laws.cpp` checks that the classic
kernel's inputs satisfy the hypotheses below (`src` is a permutation, `opp` an involution,
the velocity-set moments give `∑ feq = ρ`) and that a periodic lattice conserves its mass.

The collision is per cell over the velocity directions `Q`; streaming is over all links `L`.
-/

open Finset

namespace Trech.Methods.Lattice

variable {Q : Type*} [Fintype Q]

/-- Two-relaxation-time collision without forcing: the even part of `f - feq` relaxes at `ωp`,
the odd part at `ωm`, with `opp` the opposite-direction permutation. Equal to the classic
`f - ωp (½(f + f∘opp) - ½(feq + feq∘opp)) - ωm (½(f - f∘opp) - ½(feq - feq∘opp))`. -/
def relaxTRT (ωp ωm : ℝ) (opp : Q ≃ Q) (f feq : Q → ℝ) (k : Q) : ℝ :=
  f k - (ωp / 2) * ((f k + f (opp k)) - (feq k + feq (opp k)))
      - (ωm / 2) * ((f k - f (opp k)) - (feq k - feq (opp k)))

/-- Collision conserves a cell's mass whenever the equilibrium carries the same mass. -/
theorem relaxTRT_sum_eq (ωp ωm : ℝ) (opp : Q ≃ Q) (f feq : Q → ℝ)
    (h : ∑ k, feq k = ∑ k, f k) :
    ∑ k, relaxTRT ωp ωm opp f feq k = ∑ k, f k := by
  have hf : ∑ k, f (opp k) = ∑ k, f k := Equiv.sum_comp opp f
  have he : ∑ k, feq (opp k) = ∑ k, feq k := Equiv.sum_comp opp feq
  simp only [relaxTRT, Finset.sum_sub_distrib, Finset.sum_add_distrib, ← Finset.mul_sum, hf, he, h]
  ring

/-- A source term with zero total (Guo forcing over a velocity set with the lattice moments)
does not change the mass. -/
theorem sum_add_zero_source (g s : Q → ℝ) (hs : ∑ k, s k = 0) :
    ∑ k, (g k + s k) = ∑ k, g k := by
  rw [Finset.sum_add_distrib, hs, add_zero]

/-- Pull streaming along a bijection of the links (periodic wrap and plain bounce-back both
are one) conserves the total. -/
theorem stream_sum_eq {L : Type*} [Fintype L] (src : L ≃ L) (post : L → ℝ) :
    ∑ l, post (src l) = ∑ l, post l :=
  Equiv.sum_comp src post

end Trech.Methods.Lattice
