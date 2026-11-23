#pragma once

// The bounded explicit step shared by the engine's continuous-state operators.
//
// `ctx.evolve` (StateEvolution) integrates each declared field once per call
// as f + (sum of rates) * dt at the step the caller chose, then applies the
// field's declared bounds; `ctx.interact` (PairInteraction) applies the same
// bounds to its element and link updates. Both route through these two
// functions, so the Lean pair `Trech.Methods.Evolve`
// (formal/Trech/Methods/Evolve.lean) covers what the engine runs:
//   * with ordered bounds (lo <= hi) the result lies in [lo, hi] for every
//     finite update (`boundedStep_mem`), and is the update itself when that
//     already lies inside (`boundedStep_of_mem`);
//   * the unclamped update is linear in dt (`eulerStep_smul_dt`) and two
//     steps at one rate equal one step of the summed length (`eulerStep_add_dt`).
// The engine rejects unordered or NaN bounds at the JS boundary
// (`boundsOrdered`), which is the theorems' hypothesis. A NaN update stays NaN:
// IEEE comparisons with NaN are false, so the clamp cannot repair it, and the
// theorems (over the reals) say nothing about it.

namespace trech::ml {

// Declared bounds, clamping below first and then above (Lean `clampBounds`).
inline double clampToBounds(double value, double lo, double hi) {
  if (value < lo) value = lo;
  if (value > hi) value = hi;
  return value;
}

// One explicit-Euler step of length dt at a fixed rate, then the bounds
// (Lean `boundedStep`).
inline double boundedEulerStep(double value, double rate, double dt, double lo,
                               double hi) {
  return clampToBounds(value + rate * dt, lo, hi);
}

// The theorems' hypothesis: lo <= hi (false for NaN on either side).
inline bool boundsOrdered(double lo, double hi) { return lo <= hi; }

}  // namespace trech::ml
