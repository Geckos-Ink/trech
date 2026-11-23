module

public import Mathlib.Order.Interval.Set.ProjIcc
public import Mathlib.Basic.Real.Basic
import Mathlib.Tactic.Ring

/-!
# The bounded explicit step of `ctx.evolve`

Role: `method_property`. These theorems state what the engine's continuous-state integrator
guarantees; they say nothing about any field's physics.

Classic implementation (the running path): `include/trech/ml/BoundedStep.hpp`
(`boundedEulerStep`, `clampToBounds`, `boundsOrdered`), called by `src/ml/StateEvolution.cpp`
(`ctx.evolve`) for every declared field and by `src/ml/PairInteraction.cpp` (`ctx.interact`)
for its link and element updates. The step is `x + r · dt` (explicit Euler at the step the
caller chose, with `r` the summed stage rates), clamped below to `lo` and then above to `hi`.
`src/js/JsRuntime.cpp` rejects a field whose bounds are not ordered (`boundsOrdered`), so the
hypothesis `lo ≤ hi` holds for every call.

* `clampBounds_eq_projIcc`: the classic clamp equals Mathlib's projection onto `[lo, hi]`
  (`Set.projIcc`, `Set.coe_projIcc`) when the bounds are ordered.
* `boundedStep_mem`: with ordered bounds the result lies in `[lo, hi]`, from any start and
  any rate (Mathlib's `Subtype.prop` of the projection).
* `boundedStep_of_mem`: a step that already lands inside the bounds is not clipped
  (`Set.projIcc_of_mem`).
* `eulerStep_smul_dt`: the unclamped increment is linear in `dt`.
* `eulerStep_add_dt`: two steps at one rate equal one step of the summed length.

Over the reals only. A NaN update stays NaN in IEEE doubles, since every comparison with NaN
is false; the engine's bounds check rejects NaN bounds but not a NaN rate. Conformance:
`tests/test_formal_laws.cpp` drives `StateEvolution::evolve` with rates that cross both
bounds and compares with these statements.
-/

@[expose] public section

namespace Trech.Methods.Evolve

/-- The classic clamp: lower bound first, then the upper bound. -/
noncomputable def clampBounds (lo hi v : ℝ) : ℝ := min hi (max lo v)

/-- One explicit step of length `dt` at the fixed rate `r`, before the bounds. -/
def eulerStep (x r dt : ℝ) : ℝ := x + r * dt

/-- The engine's bounded step: the explicit step, then the declared bounds. -/
noncomputable def boundedStep (lo hi x r dt : ℝ) : ℝ := clampBounds lo hi (eulerStep x r dt)

/-- With ordered bounds the classic clamp is Mathlib's projection onto `[lo, hi]`. -/
theorem clampBounds_eq_projIcc {lo hi : ℝ} (h : lo ≤ hi) (v : ℝ) :
    clampBounds lo hi v = (Set.projIcc lo hi h v : ℝ) := by
  rw [Set.coe_projIcc]
  unfold clampBounds
  rcases le_total v lo with hv | hv
  · rw [max_eq_left hv, min_eq_right h, min_eq_right (hv.trans h), max_eq_left hv]
  · rw [max_eq_right hv]
    rcases le_total v hi with hw | hw
    · rw [min_eq_right hw, max_eq_right hv]
    · rw [min_eq_left hw, max_eq_right h]

/-- An explicit step within ordered bounds stays within them. -/
theorem boundedStep_mem {lo hi : ℝ} (h : lo ≤ hi) (x r dt : ℝ) :
    boundedStep lo hi x r dt ∈ Set.Icc lo hi := by
  unfold boundedStep
  rw [clampBounds_eq_projIcc h]
  exact (Set.projIcc lo hi h (eulerStep x r dt)).prop

/-- A step that lands inside the bounds is not clipped. -/
theorem boundedStep_of_mem {lo hi x r dt : ℝ} (h : lo ≤ hi)
    (hin : eulerStep x r dt ∈ Set.Icc lo hi) :
    boundedStep lo hi x r dt = eulerStep x r dt := by
  unfold boundedStep
  rw [clampBounds_eq_projIcc h, Set.projIcc_of_mem h hin]

/-- A rate-only update is linear in `dt`: scaling the step scales the increment. -/
theorem eulerStep_smul_dt (x r a dt : ℝ) :
    eulerStep x r (a * dt) - x = a * (eulerStep x r dt - x) := by
  unfold eulerStep
  ring

/-- Two steps at one rate equal one step of the summed length. -/
theorem eulerStep_add_dt (x r dt₁ dt₂ : ℝ) :
    eulerStep (eulerStep x r dt₁) r dt₂ = eulerStep x r (dt₁ + dt₂) := by
  unfold eulerStep
  ring

end Trech.Methods.Evolve
