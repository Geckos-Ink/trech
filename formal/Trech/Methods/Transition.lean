module

public import Mathlib.Algebra.BigOperators.Field
public import Mathlib.Algebra.Order.BigOperators.Group.Finset
public import Mathlib.Basic.Real.Basic
import Mathlib.Tactic.Linarith

/-!
# Step probabilities of the engine's discrete transitions (`ctx.react`)

Role: `method_property`. These theorems state why the engine's stochastic transition step is a
proper probability law over its channels; they say nothing about any chemistry.

Classic implementation (the running path): `src/ml/DiscreteTransition.cpp` (`ctx.react`). Each
element has an event hazard `h` in `[0, 1]` (direct mode: `min(1, ∑ s)`; weighted mode: the
predicted global hazard) and channel scores `s c ≥ 0` with total `S = ∑ s > 0`. One uniform draw
`u ∈ [0, 1)` decides: no transition when `u ≥ h`, otherwise the channel whose cumulative score
interval contains `(u / h) · S` (`selectTransitionChannel` in
`include/trech/ml/DiscreteTransition.hpp`). Rival arbitration's composed odds use the same
`h · s c / S`.

The probability of channel `c` is then `h · s c / S` (`stepProbability`): every one is
nonnegative, they sum to `h ≤ 1`, so "no transition" keeps `1 - h ≥ 0`, and direct mode below
the renormalisation threshold returns each channel's own predicted probability.
`channelDraw_lt_iff` is the inverse-CDF step: `(u / h) · S < t` exactly when `u < h · t / S`, so
the `u`-interval of a channel whose cumulative scores run from `a` to `a + s c` has length
`h · s c / S`.

Conformance: `tests/test_formal_laws.cpp` sweeps `u` over a uniform grid of `[0, 1)` through the
classic selection and compares each channel's share with `stepProbability`. Mathlib supplies
the field and order facts (`Finset.sum_div`, `Finset.mul_sum`, `div_lt_iff₀`, `lt_div_iff₀`);
it has no statement about this two-stage draw.
-/

@[expose] public section

open Finset

namespace Trech.Methods.Transition

variable {C : Type*} [Fintype C]

/-- Probability that a step fires channel `c`: event hazard `h` times the channel's share of
the scores. -/
noncomputable def stepProbability (h : ℝ) (s : C → ℝ) (c : C) : ℝ := h * s c / ∑ k, s k

theorem stepProbability_nonneg {h : ℝ} {s : C → ℝ} (hh : 0 ≤ h) (hs : ∀ c, 0 ≤ s c) (c : C) :
    0 ≤ stepProbability h s c :=
  div_nonneg (mul_nonneg hh (hs c)) (Finset.sum_nonneg fun k _ => hs k)

/-- The channel probabilities add up to the event hazard. -/
theorem sum_stepProbability (h : ℝ) (s : C → ℝ) (hS : ∑ k, s k ≠ 0) :
    ∑ c, stepProbability h s c = h := by
  unfold stepProbability
  rw [← Finset.sum_div, ← Finset.mul_sum, mul_div_assoc, div_self hS, mul_one]

/-- With `h ≤ 1`, "no transition" keeps a nonnegative probability: the channels and the
no-event outcome form a probability vector. -/
theorem noEvent_nonneg {h : ℝ} (s : C → ℝ) (hS : ∑ k, s k ≠ 0) (h1 : h ≤ 1) :
    0 ≤ 1 - ∑ c, stepProbability h s c := by
  rw [sum_stepProbability h s hS]
  linarith

/-- Direct mode below the threshold (`h = ∑ s ≤ 1`): each channel fires with its own predicted
probability. -/
theorem stepProbability_direct (s : C → ℝ) (hS : ∑ k, s k ≠ 0) (c : C) :
    stepProbability (∑ k, s k) s c = s c := by
  unfold stepProbability
  exact mul_div_cancel_left₀ (s c) hS

/-- Inverse-CDF step of the classic draw: the rescaled draw `(u / h) · S` lies below a
cumulative score `t` exactly when `u` lies below `h · t / S`. -/
theorem channelDraw_lt_iff {u h S t : ℝ} (hh : 0 < h) (hS : 0 < S) :
    u / h * S < t ↔ u < h * t / S := by
  rw [div_mul_eq_mul_div, div_lt_iff₀ hh, lt_div_iff₀ hS]
  constructor <;> intro hu <;> linarith [mul_comm t h]

end Trech.Methods.Transition
