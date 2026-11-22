module

public import Mathlib.Basic.Real.Basic
import Mathlib.Tactic.Ring

/-!
# Equal-and-opposite pair exchange (`ctx.interact`)

Classic implementation: `src/ml/PairInteraction.cpp` applies the same inferred rate and
increment with opposite signs for an antisymmetric field, including arbitration corrections.
It adds the increment and the rate times the common step size before updating each member.
Over the reals and without bound clipping, this preserves the sum. The proof uses Mathlib's
ring normalization for the distributivity and additive inverse identities. Classic conformance
is in `tests/test_formal_laws.cpp`, with a tolerance for floating-point accumulation.
-/

@[expose] public section

namespace Trech.Methods.PairInteraction

/-- Both increments and time-integrated rates cancel in an antisymmetric pair. -/
theorem exchange_preserves_sum (a b increment rate dt : ℝ) :
    (a + (increment + rate * dt)) + (b + (-increment + -rate * dt)) = a + b := by
  ring

end Trech.Methods.PairInteraction
