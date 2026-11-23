module

public import Mathlib.Algebra.BigOperators.Group.Finset.Basic
public import Mathlib.Basic.Real.Basic
import Mathlib.Algebra.Order.Field.Basic

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

end Trech.Methods.Group
