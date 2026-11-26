module

public import Mathlib.Algebra.BigOperators.Group.Finset.Basic
public import Mathlib.Basic.Real.Basic
import Mathlib.Algebra.Order.Field.Basic
import Mathlib.Algebra.Order.BigOperators.Group.Finset

/-!
# Group assembly of the engine's recursive lifting (`ctx.lift`)

Role: `method_property`. These theorems state what one level of `GroupHierarchy` keeps when it
turns a population into groups; they say nothing about what a group model predicts.

Classic implementation (the running path): `partition` and `GroupHierarchy::run` in
`src/ml/GroupHierarchy.cpp`. A level groups its elements by a key (`all`: one key; `explicit`:
the declared group id; `cell`: the floor of the scaled position), gives each element its group
as `parent`, sums the members' weights into the group weight `W g = ∑ w i`, and places the group
at the weighted centroid `c g = (∑ w i · p i) / W g` (per axis). The groups, with those weights
and positions, become the next level's elements.

* `mem_group_unique`: every element lies in exactly one group (the fibre of its key).
* `sum_groupWeight`: the group weights add up to the population's total weight (Mathlib's
  `Finset.sum_fiberwise_of_maps_to`), so total weight is the same at every level.
* `groupWeight_mul_centroid`: a group of nonzero weight carries its members' weighted first
  moment at its centroid.
* `sum_weight_centroid`: if no group weighs zero, the weighted first moment of the groups equals
  that of the elements, so the population's centre of weight is the same at every level.

Hypothesis of the moment statements: no group weighs zero (the classic code writes a NaN
centroid for such a group). Over the reals; in doubles the sums round. Conformance:
`tests/test_formal_laws.cpp` runs `GroupHierarchy::run` over `cell` and `explicit` groupings and
compares parents, weights and moments at each level.
-/

@[expose] public section

open Finset

namespace Trech.Methods.Group

variable {ι κ : Type*} [Fintype ι] [DecidableEq κ]

/-- The members of group `k`: the elements whose key is `k`. -/
def members (key : ι → κ) (k : κ) : Finset ι := univ.filter fun i => key i = k

/-- The groups a level forms: one per key that occurs. -/
def groups (key : ι → κ) : Finset κ := univ.image key

/-- A group's weight: the sum of its members' weights. -/
def groupWeight (key : ι → κ) (w : ι → ℝ) (k : κ) : ℝ := ∑ i ∈ members key k, w i

/-- A group's weighted first moment along one axis. -/
def groupMoment (key : ι → κ) (w p : ι → ℝ) (k : κ) : ℝ := ∑ i ∈ members key k, w i * p i

/-- The group's position: its weighted centroid along one axis. -/
noncomputable def centroid (key : ι → κ) (w p : ι → ℝ) (k : κ) : ℝ :=
  groupMoment key w p k / groupWeight key w k

theorem mem_group_unique (key : ι → κ) (i : ι) :
    ∃! k, k ∈ groups key ∧ i ∈ members key k := by
  refine ⟨key i, ⟨mem_image_of_mem key (mem_univ i), by simp [members]⟩, ?_⟩
  rintro k ⟨_, hk⟩
  simp only [members, mem_filter, mem_univ, true_and] at hk
  exact hk.symm

theorem sum_groupWeight (key : ι → κ) (w : ι → ℝ) :
    ∑ k ∈ groups key, groupWeight key w k = ∑ i, w i :=
  Finset.sum_fiberwise_of_maps_to (fun i _ => mem_image_of_mem key (mem_univ i)) w

theorem groupWeight_mul_centroid (key : ι → κ) (w p : ι → ℝ) (k : κ)
    (h : groupWeight key w k ≠ 0) :
    groupWeight key w k * centroid key w p k = groupMoment key w p k := by
  unfold centroid
  exact mul_div_cancel₀ _ h

theorem sum_weight_centroid (key : ι → κ) (w p : ι → ℝ)
    (h : ∀ k ∈ groups key, groupWeight key w k ≠ 0) :
    ∑ k ∈ groups key, groupWeight key w k * centroid key w p k = ∑ i, w i * p i := by
  rw [Finset.sum_congr rfl fun k hk => groupWeight_mul_centroid key w p k (h k hk)]
  exact Finset.sum_fiberwise_of_maps_to (fun i _ => mem_image_of_mem key (mem_univ i))
    (fun i => w i * p i)

/-! ## Recursion: a lift of any depth groups the base elements once

`GroupHierarchy::run` feeds each level's groups (weight `W`, centroid `c`) to the next level as
its elements. The theorems below show that this recursion loses nothing: grouping the groups
equals grouping the base elements once by the composed key (each element's ancestor), so the
weight, weighted first moment and centroid at any depth are those of the base elements whose
ancestor is that group. They need non-negative base weights only to rule out a group of zero
weight whose members' moments do not cancel (Lean reads `x / 0` as `0`; the classic code writes
NaN for such a group). With positive base weights no occurring group weighs zero at any depth
(`liftWeight_pos`), so the classic code never writes that NaN.
-/

section Compose

variable {κ₂ : Type*} [Fintype κ] [DecidableEq κ₂]

/-- Two levels group a base element by its composed key, through
`Finset.sum_fiberwise_eq_sum_filter`. -/
theorem sum_members_comp (k₁ : ι → κ) (k₂ : κ → κ₂) (f : ι → ℝ) (g : κ₂) :
    ∑ j ∈ members k₂ g, ∑ i ∈ members k₁ j, f i = ∑ i ∈ members (k₂ ∘ k₁) g, f i := by
  unfold members
  rw [Finset.sum_fiberwise_eq_sum_filter]
  refine Finset.sum_congr ?_ fun _ _ => rfl
  ext i
  simp

theorem groupWeight_comp (k₁ : ι → κ) (k₂ : κ → κ₂) (w : ι → ℝ) (g : κ₂) :
    groupWeight k₂ (groupWeight k₁ w) g = groupWeight (k₂ ∘ k₁) w g :=
  sum_members_comp k₁ k₂ w g

omit [Fintype κ] in
theorem groupWeight_nonneg (key : ι → κ) (w : ι → ℝ) (hw : ∀ i, 0 ≤ w i) (k : κ) :
    0 ≤ groupWeight key w k :=
  Finset.sum_nonneg fun i _ => hw i

omit [Fintype κ] in
/-- With non-negative weights a group always carries its moment at its centroid: a group of zero
weight has members of zero weight, hence zero moment. -/
theorem groupWeight_mul_centroid_of_nonneg (key : ι → κ) (w p : ι → ℝ) (hw : ∀ i, 0 ≤ w i)
    (k : κ) : groupWeight key w k * centroid key w p k = groupMoment key w p k := by
  by_cases h : groupWeight key w k = 0
  · have hz : ∀ i ∈ members key k, w i = 0 :=
      (Finset.sum_eq_zero_iff_of_nonneg fun i _ => hw i).1 h
    have hm : groupMoment key w p k = 0 :=
      Finset.sum_eq_zero fun i hi => by rw [hz i hi, zero_mul]
    rw [h, hm, zero_mul]
  · exact groupWeight_mul_centroid key w p k h

theorem groupMoment_comp (k₁ : ι → κ) (k₂ : κ → κ₂) (w p : ι → ℝ) (hw : ∀ i, 0 ≤ w i)
    (g : κ₂) :
    groupMoment k₂ (groupWeight k₁ w) (centroid k₁ w p) g = groupMoment (k₂ ∘ k₁) w p g := by
  unfold groupMoment
  rw [Finset.sum_congr rfl fun j _ => groupWeight_mul_centroid_of_nonneg k₁ w p hw j]
  exact sum_members_comp k₁ k₂ (fun i => w i * p i) g

/-- The centroid of the groups' centroids, weighted by group weight, is the base elements'
centroid under the composed key. -/
theorem centroid_comp (k₁ : ι → κ) (k₂ : κ → κ₂) (w p : ι → ℝ) (hw : ∀ i, 0 ≤ w i) (g : κ₂) :
    centroid k₂ (groupWeight k₁ w) (centroid k₁ w p) g = centroid (k₂ ∘ k₁) w p g := by
  change groupMoment k₂ (groupWeight k₁ w) (centroid k₁ w p) g /
    groupWeight k₂ (groupWeight k₁ w) g = _
  rw [groupMoment_comp k₁ k₂ w p hw, groupWeight_comp]
  rfl

end Compose

section Depth

/-! Any depth. The classic code numbers a level's groups `0 … groups - 1`, never more than the
level's elements, so every level fits in the base index type and a lift of depth `n` is a list of
`n` keys `ι → ι` (a key's value outside the groups it forms is a group of no members and weight 0,
which no element names). -/

variable [DecidableEq ι]

/-- An element's ancestor after the levels `ks` (its parent, its parent's parent, …). -/
def ancestor : List (ι → ι) → ι → ι
  | [], i => i
  | k :: ks, i => ancestor ks (k i)

/-- The group weights after the levels `ks`. -/
def liftWeight : List (ι → ι) → (ι → ℝ) → ι → ℝ
  | [], w => w
  | k :: ks, w => liftWeight ks (groupWeight k w)

/-- The group positions (one axis) after the levels `ks`. -/
noncomputable def liftPos : List (ι → ι) → (ι → ℝ) → (ι → ℝ) → ι → ℝ
  | [], _, p => p
  | k :: ks, w, p => liftPos ks (groupWeight k w) (centroid k w p)

omit [Fintype ι] [DecidableEq ι] in
theorem ancestor_cons (k : ι → ι) (ks : List (ι → ι)) :
    ancestor (k :: ks) = ancestor ks ∘ k := rfl

theorem groupWeight_id (w : ι → ℝ) (g : ι) : groupWeight id w g = w g := by
  simp [groupWeight, members, Finset.filter_eq']

theorem groupMoment_id (w p : ι → ℝ) (g : ι) : groupMoment id w p g = w g * p g := by
  simp [groupMoment, members, Finset.filter_eq']

/-- Every base element has exactly one ancestor group at every depth. -/
theorem ancestor_unique (ks : List (ι → ι)) (i : ι) :
    ∃! g, g ∈ groups (ancestor ks) ∧ i ∈ members (ancestor ks) g :=
  mem_group_unique (ancestor ks) i

/-- A group's weight at any depth is the summed weight of the base elements it descends from. -/
theorem liftWeight_eq (ks : List (ι → ι)) (w : ι → ℝ) (g : ι) :
    liftWeight ks w g = groupWeight (ancestor ks) w g := by
  induction ks generalizing w with
  | nil => exact (groupWeight_id w g).symm
  | cons k ks ih => rw [liftWeight, ih, ancestor_cons, groupWeight_comp]

/-- Total weight is the same at every depth. -/
theorem sum_liftWeight (ks : List (ι → ι)) (w : ι → ℝ) :
    ∑ g ∈ groups (ancestor ks), liftWeight ks w g = ∑ i, w i := by
  rw [Finset.sum_congr rfl fun g _ => liftWeight_eq ks w g]
  exact sum_groupWeight (ancestor ks) w

/-- A group's weighted first moment at any depth is that of its base elements. -/
theorem liftMoment_eq (ks : List (ι → ι)) (w p : ι → ℝ) (hw : ∀ i, 0 ≤ w i) (g : ι) :
    liftWeight ks w g * liftPos ks w p g = groupMoment (ancestor ks) w p g := by
  induction ks generalizing w p with
  | nil => exact (groupMoment_id w p g).symm
  | cons k ks ih =>
    rw [liftWeight, liftPos, ih _ _ (groupWeight_nonneg k w hw), ancestor_cons,
      groupMoment_comp k _ w p hw]

/-- After at least one level, a group's position is the centroid of its base elements. -/
theorem liftPos_eq_centroid (k : ι → ι) (ks : List (ι → ι)) (w p : ι → ℝ)
    (hw : ∀ i, 0 ≤ w i) (g : ι) :
    liftPos (k :: ks) w p g = centroid (ancestor (k :: ks)) w p g := by
  induction ks generalizing k w p with
  | nil => rfl
  | cons k' ks ih =>
    rw [liftPos, ih k' _ _ (groupWeight_nonneg k w hw), ancestor_cons (k := k),
      ← centroid_comp k (ancestor (k' :: ks)) w p hw]

/-- The centre of weight is the same at every depth. -/
theorem sum_liftMoment (ks : List (ι → ι)) (w p : ι → ℝ) (hw : ∀ i, 0 ≤ w i) :
    ∑ g ∈ groups (ancestor ks), liftWeight ks w g * liftPos ks w p g = ∑ i, w i * p i := by
  rw [Finset.sum_congr rfl fun g _ => liftMoment_eq ks w p hw g]
  exact Finset.sum_fiberwise_of_maps_to (fun i _ => mem_image_of_mem _ (mem_univ i))
    (fun i => w i * p i)

/-- With positive base weights every group that some element descends from weighs more than
zero at every depth, so no centroid divides by zero. -/
theorem liftWeight_pos (ks : List (ι → ι)) (w : ι → ℝ) (hw : ∀ i, 0 < w i) (g : ι)
    (hg : g ∈ groups (ancestor ks)) : 0 < liftWeight ks w g := by
  rw [liftWeight_eq]
  obtain ⟨i, -, hi⟩ := Finset.mem_image.1 hg
  exact Finset.sum_pos (fun j _ => hw j) ⟨i, by simp [members, hi]⟩

/-! ### Lineage flags

A level flags a group when the group's own check raises it (`loc`) or any member is flagged.
The classic code applies this rule to blocking (`valid`: overflow or a failed prediction, or a
blocked member), to `inDomain` and to `starved`. `liftFlag_iff` splits the flag at any depth into
the base elements it descends from and the flags raised by the levels themselves; so a flagged
base element always flags its ancestor (`flag_of_descendant`), and when no level raises a flag
a group is flagged exactly when some base element under it is (`liftFlag_no_local`). -/

/-- One level's flag rule. -/
def raise (k : ι → ι) (loc f : ι → Prop) : ι → Prop := fun g => loc g ∨ ∃ i, k i = g ∧ f i

/-- The flags after the levels `ls` (key and the level's own check), from base flags `f`. -/
def liftFlag : List ((ι → ι) × (ι → Prop)) → (ι → Prop) → ι → Prop
  | [], f => f
  | (k, loc) :: ls, f => liftFlag ls (raise k loc f)

omit [Fintype ι] [DecidableEq ι] in
theorem liftFlag_iff (ls : List ((ι → ι) × (ι → Prop))) (f : ι → Prop) (g : ι) :
    liftFlag ls f g ↔
      (∃ i, ancestor (ls.map Prod.fst) i = g ∧ f i) ∨ liftFlag ls (fun _ => False) g := by
  induction ls generalizing f with
  | nil => simp [liftFlag, ancestor]
  | cons l ls ih =>
    obtain ⟨k, loc⟩ := l
    simp only [liftFlag, List.map_cons, ancestor]
    rw [ih, ih (raise k loc fun _ => False)]
    simp only [raise, and_false, exists_false, or_false]
    constructor
    · rintro (⟨j, hj, hl | ⟨i, rfl, hi⟩⟩ | h)
      · exact Or.inr (Or.inl ⟨j, hj, hl⟩)
      · exact Or.inl ⟨i, hj, hi⟩
      · exact Or.inr (Or.inr h)
    · rintro (⟨i, hi, hf⟩ | ⟨j, hj, hl⟩ | h)
      · exact Or.inl ⟨k i, hi, Or.inr ⟨i, rfl, hf⟩⟩
      · exact Or.inl ⟨j, hj, Or.inl hl⟩
      · exact Or.inr h

omit [Fintype ι] [DecidableEq ι] in
/-- A flagged base element flags its ancestor at every depth: lineage is never lost. -/
theorem flag_of_descendant (ls : List ((ι → ι) × (ι → Prop))) (f : ι → Prop) (i : ι)
    (h : f i) : liftFlag ls f (ancestor (ls.map Prod.fst) i) :=
  (liftFlag_iff ls f _).2 (Or.inl ⟨i, rfl, h⟩)

omit [Fintype ι] [DecidableEq ι] in
/-- An unflagged group has no flagged base element under it. -/
theorem not_flag_no_descendant (ls : List ((ι → ι) × (ι → Prop))) (f : ι → Prop) (g : ι)
    (h : ¬ liftFlag ls f g) : ∀ i, ancestor (ls.map Prod.fst) i = g → ¬ f i :=
  fun i hi hf => h (hi ▸ flag_of_descendant ls f i hf)

omit [Fintype ι] [DecidableEq ι] in
theorem liftFlag_false (ls : List ((ι → ι) × (ι → Prop))) (hl : ∀ p ∈ ls, ∀ g, ¬ p.2 g)
    (g : ι) : ¬ liftFlag ls (fun _ => False) g := by
  induction ls generalizing g with
  | nil => simp [liftFlag]
  | cons l ls ih =>
    obtain ⟨k, loc⟩ := l
    have hloc : ∀ g, ¬ loc g := hl (k, loc) (List.mem_cons_self ..)
    have hrest : ∀ p ∈ ls, ∀ g, ¬ p.2 g := fun p hp => hl p (List.mem_cons_of_mem _ hp)
    have hr : raise k loc (fun _ => False) = fun _ => False := by
      funext g; simp [raise, hloc g]
    simp only [liftFlag, hr]
    exact ih hrest g

omit [Fintype ι] [DecidableEq ι] in
/-- When no level raises a flag of its own, a group is flagged exactly when a base element
under it is. -/
theorem liftFlag_no_local (ls : List ((ι → ι) × (ι → Prop))) (hl : ∀ p ∈ ls, ∀ g, ¬ p.2 g)
    (f : ι → Prop) (g : ι) :
    liftFlag ls f g ↔ ∃ i, ancestor (ls.map Prod.fst) i = g ∧ f i := by
  rw [liftFlag_iff]
  exact or_iff_left (liftFlag_false ls hl g)

end Depth

end Trech.Methods.Group
