module

public import Mathlib.Algebra.BigOperators.Group.List.Basic
public import Mathlib.Algebra.Order.Group.MinMax
public import Mathlib.Basic.Real.Basic
public import Mathlib.Algebra.Order.BigOperators.Group.List
import Mathlib.Tactic.Linarith
import Mathlib.Tactic.NormNum
import Mathlib.Tactic.Ring

/-!
# Joint coverage: the pruned nearest-centre scan gives the full scan's verdict

Role: `method_property`. `GenericSurrogate::coverageVector` decides whether an input lies near
the training data by its squared standardized distance to the nearest of the model's exported
training centres: *covered* when some centre lies within the acceptance radius `A`, otherwise
*jointly starved*, with the nearest distance reported. To stay cheap it takes two shortcuts:

* while summing one centre's squared differences it stops as soon as the partial sum reaches
  the best distance so far (`partialBreak`; the terms are non-negative, so the full sum could
  only be larger), and
* it stops scanning centres as soon as one covers the input.

These theorems say the shortcuts change nothing the engine reports as a verdict:

* `partialBreak_spec`: the pruned sum is the full sum, or lies between the best so far and the
  full sum, so it is below the best exactly when the full sum is (`pruned_lt_iff`).
* `scan_spec`: from a best value above `A` (the engine starts at `+∞`), the scan is covered
  exactly when some centre's full distance is at most `A`, and when it is not covered its best
  value is the true minimum over all centres.
* `covered_distance_not_min`: when covered, the reported distance need not be the minimum (the
  scan stopped early); only the starved distance is exact.

Over the reals. In doubles the pruned and full sums add the same terms in the same order, so the
comparison is the same one the full scan would make, and the starved distance is bit-identical
to a full scan's minimum; the conformance test checks both.

Classic implementation (the running path): `src/ml/GenericSurrogate.cpp`
(`GenericSurrogate::coverageVector`, the joint check).

Conformance: `tests/test_formal_laws.cpp` (`coveragePairs`) compares the engine's verdict and
starved distance with a brute-force scan of every centre on a grid of inputs.
-/

@[expose] public section

namespace Trech.Methods.Coverage

/-- Sum `terms` onto `s`, stopping (and returning the partial sum) as soon as it reaches `b`. -/
noncomputable def partialBreak (b : ℝ) : ℝ → List ℝ → ℝ
  | s, [] => s
  | s, t :: ts => if b ≤ s + t then s + t else partialBreak b (s + t) ts

/-- With non-negative terms the pruned sum is the full sum, or lies between `b` and it. -/
theorem partialBreak_spec (b : ℝ) (ts : List ℝ) (h : ∀ t ∈ ts, 0 ≤ t) (s : ℝ) :
    partialBreak b s ts = s + ts.sum ∨
      (b ≤ partialBreak b s ts ∧ partialBreak b s ts ≤ s + ts.sum) := by
  induction ts generalizing s with
  | nil => left; simp [partialBreak]
  | cons t ts ih =>
    have hrest : ∀ u ∈ ts, 0 ≤ u := fun u hu => h u (List.mem_cons_of_mem _ hu)
    have hsum : 0 ≤ ts.sum := List.sum_nonneg hrest
    simp only [partialBreak, List.sum_cons]
    split_ifs with hb
    · by_cases hz : ts.sum = 0
      · left; rw [hz]; ring
      · right; exact ⟨hb, by linarith⟩
    · rcases ih hrest (s + t) with e | ⟨h1, h2⟩
      · left; rw [e]; ring
      · right; exact ⟨h1, by linarith⟩

/-- A pruned value: the full value, or between the best so far and the full value. -/
def Pruned (b full p : ℝ) : Prop := p = full ∨ (b ≤ p ∧ p ≤ full)

/-- A pruned value is below the best exactly when the full value is, and then equals it. -/
theorem pruned_lt_iff {b full p : ℝ} (h : Pruned b full p) : p < b ↔ full < b := by
  rcases h with rfl | ⟨h1, h2⟩
  · rfl
  · constructor <;> intro h3 <;> linarith

/-- One centre of the scan: skip once covered; otherwise keep a smaller pruned distance, covered
when it lies within `A`. -/
noncomputable def step {α : Type*} (A : ℝ) (pruned : ℝ → α → ℝ) (st : ℝ × Bool) (c : α) : ℝ × Bool :=
  if st.2 then st
  else if pruned st.1 c < st.1 then (pruned st.1 c, decide (pruned st.1 c ≤ A)) else st

theorem foldl_step_covered {α : Type*} (A : ℝ) (pruned : ℝ → α → ℝ) (cs : List α) (b : ℝ) :
    cs.foldl (step A pruned) (b, true) = (b, true) := by
  induction cs with
  | nil => rfl
  | cons c cs ih => simp only [List.foldl_cons, step, ite_true]; exact ih

/-- The pruned, early-stopping scan gives the full scan's verdict, and its starved distance is
the true minimum. -/
theorem scan_spec {α : Type*} (A : ℝ) (full : α → ℝ) (pruned : ℝ → α → ℝ)
    (hp : ∀ b c, Pruned b (full c) (pruned b c)) (cs : List α) (b : ℝ) (hA : A < b) :
    let r := cs.foldl (step A pruned) (b, false)
    (r.2 = true ↔ ∃ c ∈ cs, full c ≤ A) ∧ (r.2 = false → r.1 = (cs.map full).foldl min b) := by
  induction cs generalizing b with
  | nil => simp
  | cons c cs ih =>
    simp only [List.foldl_cons, List.map_cons, List.mem_cons, exists_eq_or_imp]
    have hlt := pruned_lt_iff (hp b c)
    by_cases hc : full c < b
    · have heq : pruned b c = full c := by
        rcases hp b c with e | ⟨h1, h2⟩
        · exact e
        · linarith
      have hs : step A pruned (b, false) c = (full c, decide (full c ≤ A)) := by
        simp [step, heq, hc]
      rw [hs, min_eq_right hc.le]
      by_cases hcA : full c ≤ A
      · simp only [hcA, decide_true, foldl_step_covered]
        simp
      · have hA' : A < full c := lt_of_not_ge hcA
        simp only [hcA, decide_false]
        obtain ⟨h1, h2⟩ := ih (full c) hA'
        exact ⟨by simpa [hcA] using h1, h2⟩
    · have hs : step A pruned (b, false) c = (b, false) := by
        have : ¬ pruned b c < b := fun h => hc (hlt.mp h)
        simp [step, this]
      rw [hs, min_eq_left (le_of_not_gt hc)]
      have hcA : ¬ full c ≤ A := by intro h; exact hc (by linarith)
      obtain ⟨h1, h2⟩ := ih b hA
      exact ⟨by simpa [hcA] using h1, h2⟩

/-- When covered, the reported distance need not be the minimum: the first centre (distance 1)
covers the input with `A = 2`, so the nearer second centre (distance 0) is never read. -/
theorem covered_distance_not_min :
    let r := [(1 : ℝ), 0].foldl (step 2 fun _ d => d) (3, false)
    r.2 = true ∧ r.1 ≠ ([(1 : ℝ), 0].map id).foldl min 3 := by
  norm_num [step]

end Trech.Methods.Coverage
