module

public import Mathlib.Algebra.BigOperators.Group.List.Basic
public import Mathlib.Basic.Real.Basic
public import Mathlib.Data.Finset.Basic
import Mathlib.Tactic.Linarith
import Mathlib.Tactic.Ring

/-!
# Stage order inside a `ctx.evolve` scale band

Role: `method_property`. `StateEvolution::evolve` sorts its stages by scale band and, inside a
band, runs them in registration order on one element's working vector. A stage reads the
working vector (fields, aux and earlier intermediates); it *adds* its rate outputs
(`d_<field>_dt`) to the element's rates and *overwrites* its assignment and intermediate
outputs (`set_<field>`, any other name) in the working vector, where later stages read them.
The field step then integrates the final working values with the summed rates. So a band's
outcome is the final (working, rates) pair, and these theorems say when the order inside a
band does not change it:

* `apply_comm`: two stages commute when they write disjoint slots and neither reads a slot the
  other writes.
* `rateOnly_comm`: two stages that write no slot (rate-only) always commute.
* `foldRateOnly`, `rateOnly_perm`: a band of rate-only stages adds the sum of their rates,
  so any reordering gives the same outcome.
* `order_matters`: an assignment read by a rate stage is order-dependent.

Over the reals. In doubles, two rates added to zero commute exactly (IEEE addition is
commutative) but three or more sum in registration order, so a reordered band may differ in
the last place; the conformance test states that.

Classic implementation (the running path): `src/ml/StateEvolution.cpp` (the stage loop: rates
accumulate, assignments and intermediates overwrite `working`).

Conformance: `tests/test_formal_laws.cpp` (`bandPairs`) registers the same stages in both
orders on `StateEvolution`: two rate stages give bit-identical states, three within a stated
tolerance, two disjoint commuting assigners bit-identical, and an assigner read by a rate stage
differs (the counterexample).
-/

@[expose] public section

namespace Trech.Methods.Band

variable {ι φ : Type*} [DecidableEq ι]

/-- A stage: the working slots it writes, the values it writes there, and the rates it adds,
all computed from the working vector it reads. -/
structure Stage (ι φ : Type*) where
  writes : Finset ι
  value : (ι → ℝ) → ι → ℝ
  rate : (ι → ℝ) → φ → ℝ

/-- Run one stage on (working vector, summed rates). -/
def apply (s : Stage ι φ) (p : (ι → ℝ) × (φ → ℝ)) : (ι → ℝ) × (φ → ℝ) :=
  (fun i => if i ∈ s.writes then s.value p.1 i else p.1 i, p.2 + s.rate p.1)

/-- The stage's outputs do not depend on the slots in `W`. -/
def ReadsOutside (s : Stage ι φ) (W : Finset ι) : Prop :=
  ∀ w w' : ι → ℝ, (∀ i, i ∉ W → w i = w' i) → s.value w = s.value w' ∧ s.rate w = s.rate w'

/-- A stage that writes nothing (rate-only). -/
def RateOnly (s : Stage ι φ) : Prop := s.writes = ∅

/-- Two stages writing disjoint slots, neither reading what the other writes, commute. -/
theorem apply_comm (a b : Stage ι φ) (hdisj : Disjoint a.writes b.writes)
    (ha : ReadsOutside a b.writes) (hb : ReadsOutside b a.writes) (p : (ι → ℝ) × (φ → ℝ)) :
    apply a (apply b p) = apply b (apply a p) := by
  obtain ⟨w, r⟩ := p
  have hwb : ∀ i, i ∉ b.writes → (if i ∈ b.writes then b.value w i else w i) = w i := by
    intro i hi; simp [hi]
  have hwa : ∀ i, i ∉ a.writes → (if i ∈ a.writes then a.value w i else w i) = w i := by
    intro i hi; simp [hi]
  obtain ⟨hav, har⟩ := ha _ w hwb
  obtain ⟨hbv, hbr⟩ := hb _ w hwa
  simp only [apply, hav, har, hbv, hbr, Prod.mk.injEq]
  constructor
  · funext i
    by_cases hia : i ∈ a.writes
    · have hib : i ∉ b.writes := Finset.disjoint_left.mp hdisj hia
      simp [hia, hib]
    · by_cases hib : i ∈ b.writes <;> simp [hia, hib]
  · rw [add_assoc, add_assoc, add_comm (b.rate w)]

omit [DecidableEq ι] in
/-- A rate-only stage's outputs may read every slot: nothing it could read is written by a
rate-only partner. -/
theorem readsOutside_empty (s : Stage ι φ) : ReadsOutside s ∅ := by
  intro w w' h
  have : w = w' := funext fun i => h i (Finset.notMem_empty i)
  subst this
  exact ⟨rfl, rfl⟩

/-- Rate-only stages always commute. -/
theorem rateOnly_comm (a b : Stage ι φ) (ha : RateOnly a) (hb : RateOnly b)
    (p : (ι → ℝ) × (φ → ℝ)) : apply a (apply b p) = apply b (apply a p) := by
  apply apply_comm
  · rw [ha]; exact Finset.disjoint_empty_left _
  · rw [hb]; exact readsOutside_empty a
  · rw [ha]; exact readsOutside_empty b

/-- A band of rate-only stages keeps the working vector and adds the sum of their rates. -/
theorem foldRateOnly (l : List (Stage ι φ)) (hl : ∀ s ∈ l, RateOnly s)
    (w : ι → ℝ) (r : φ → ℝ) :
    l.foldl (fun p s => apply s p) (w, r) = (w, r + (l.map fun s => s.rate w).sum) := by
  induction l generalizing r with
  | nil => simp
  | cons s l ih =>
    have hs : s.writes = ∅ := hl s (List.mem_cons_self ..)
    have hrest : ∀ t ∈ l, RateOnly t := fun t ht => hl t (List.mem_cons_of_mem _ ht)
    have hstep : apply s (w, r) = (w, r + s.rate w) := by
      simp only [apply, hs, Finset.notMem_empty, ite_false]
    simp only [List.foldl_cons, hstep, ih hrest, List.map_cons, List.sum_cons, add_assoc]

/-- Reordering a band of rate-only stages does not change its outcome. -/
theorem rateOnly_perm {l l' : List (Stage ι φ)} (hp : l.Perm l') (hl : ∀ s ∈ l, RateOnly s)
    (w : ι → ℝ) (r : φ → ℝ) :
    l.foldl (fun p s => apply s p) (w, r) = l'.foldl (fun p s => apply s p) (w, r) := by
  have hl' : ∀ s ∈ l', RateOnly s := fun s hs => hl s (hp.symm.subset hs)
  rw [foldRateOnly l hl, foldRateOnly l' hl', (hp.map _).sum_eq]

/-- Order matters once a rate reads an assignment: one slot, one rate. `set` writes `1` to the
slot; `drive` adds the slot's value as a rate. From a slot of `0`, `set` then `drive` adds `1`,
`drive` then `set` adds `0`. -/
theorem order_matters :
    let set : Stage Unit Unit := ⟨{()}, fun _ _ => 1, fun _ _ => 0⟩
    let drive : Stage Unit Unit := ⟨∅, fun w => w, fun w _ => w ()⟩
    apply drive (apply set (fun _ => 0, fun _ => 0)) ≠
      apply set (apply drive (fun _ => 0, fun _ => 0)) := by
  intro set drive h
  have := congrArg (fun p => p.2 ()) h
  simp [set, drive, apply] at this

end Trech.Methods.Band
