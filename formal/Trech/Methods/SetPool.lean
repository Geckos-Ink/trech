module

public import Mathlib.Algebra.BigOperators.Group.Finset.Basic
public import Mathlib.Algebra.Module.Defs
public import Mathlib.Data.Fintype.Card
public import Mathlib.Logic.Equiv.Defs
public import Mathlib.Basic.Real.Basic

/-!
# Order-independence of the engine's set networks (`ctx.lift`, set operators)

Role: `method_property`. These theorems state why a `generic_surrogate_v3` set network
(DeepSets or message passing) gives the same answer whatever order its elements are listed in,
and why an absent element takes no part; they say nothing about the physics a model learned.

Classic implementation (the running path): `GenericSurrogate::predictSet` in
`src/ml/GenericSurrogate.cpp`, used by `ctx.lift` (`GroupHierarchy`) and by every set-network
operator. Each element block is standardised, mapped by the shared `phi` layers, optionally
updated by `rounds` of message passing (each present element `i` adds the shared `message` of
`(h i, h j, z j - z i)` over every other present `j`, then the shared `update`), pooled over the
present elements by sum, mean or max, and read out by `rho` together with the context inputs.
Presence is read from each element's own raw mask feature.

* `sumPool_perm`, `presentCount_perm`, `meanPool_perm`: permuting the elements leaves the sum
  pool, the number of present elements and so the mean pool unchanged (Mathlib's
  `Equiv.sum_comp`).
* `presentImage_perm`: the set of present element images is unchanged, so any reduction of it,
  such as the max pool, is too.
* `sumPool_update_absent`: changing an absent element (one that stays absent) does not change
  the pool.
* `deepSets_perm`: a readout of the sum pool and the context is permutation invariant.
* `mpnnRound_perm`: one message-passing round is permutation equivariant: permuting the inputs
  permutes the outputs the same way. Rounds therefore compose to an equivariant state, which
  the invariant pools then reduce. The element state `S` may carry the raw features, which
  covers the relative features `z j - z i`.

Hypothesis (checked when the model loads): every element slot shares its feature's
`input_mean` and `input_std`, so permuting the raw blocks permutes the standardised blocks; the
loader fails closed otherwise. Over the reals or any commutative monoid; in doubles the sum's
rounding depends on order, so conformance states a tolerance. Conformance:
`tests/test_formal_laws.cpp` evaluates the committed set-network fixtures under every
permutation of their four element blocks.
-/

@[expose] public section

open Finset

namespace Trech.Methods.SetPool

variable {ι F H : Type*} [Fintype ι]

/-- Sum of the element maps `φ` over the present elements (presence from the element itself). -/
def sumPool [AddCommMonoid H] (q : F → Prop) [DecidablePred q] (φ : F → H) (x : ι → F) : H :=
  ∑ e, if q (x e) then φ (x e) else 0

/-- Number of present elements. -/
def presentCount (q : F → Prop) [DecidablePred q] (x : ι → F) : ℕ :=
  ∑ e, if q (x e) then 1 else 0

/-- Mean pool: the sum pool divided by the number of present elements. -/
noncomputable def meanPool [AddCommMonoid H] [Module ℝ H] (q : F → Prop) [DecidablePred q]
    (φ : F → H) (x : ι → F) : H :=
  ((presentCount q x : ℝ))⁻¹ • sumPool q φ x

theorem sumPool_perm [AddCommMonoid H] (q : F → Prop) [DecidablePred q] (φ : F → H)
    (x : ι → F) (σ : Equiv.Perm ι) : sumPool q φ (x ∘ σ) = sumPool q φ x :=
  Equiv.sum_comp σ (fun e => if q (x e) then φ (x e) else 0)

theorem presentCount_perm (q : F → Prop) [DecidablePred q] (x : ι → F) (σ : Equiv.Perm ι) :
    presentCount q (x ∘ σ) = presentCount q x :=
  Equiv.sum_comp σ (fun e => if q (x e) then 1 else 0)

theorem meanPool_perm [AddCommMonoid H] [Module ℝ H] (q : F → Prop) [DecidablePred q]
    (φ : F → H) (x : ι → F) (σ : Equiv.Perm ι) : meanPool q φ (x ∘ σ) = meanPool q φ x := by
  unfold meanPool
  rw [sumPool_perm, presentCount_perm]

/-- The present element images, the only thing a max pool reads. -/
def presentImage [DecidableEq H] (q : F → Prop) [DecidablePred q] (φ : F → H) (x : ι → F) :
    Finset H :=
  (univ.filter fun e => q (x e)).image fun e => φ (x e)

theorem presentImage_perm [DecidableEq H] (q : F → Prop) [DecidablePred q] (φ : F → H)
    (x : ι → F) (σ : Equiv.Perm ι) : presentImage q φ (x ∘ σ) = presentImage q φ x := by
  ext y
  simp only [presentImage, Finset.mem_image, Finset.mem_filter, Finset.mem_univ, true_and,
    Function.comp_apply]
  constructor
  · rintro ⟨e, he, rfl⟩
    exact ⟨σ e, he, rfl⟩
  · rintro ⟨e, he, rfl⟩
    exact ⟨σ.symm e, by simpa using he, by simp⟩

/-- An absent element can change freely while it stays absent. -/
theorem sumPool_update_absent [AddCommMonoid H] [DecidableEq ι] (q : F → Prop)
    [DecidablePred q] (φ : F → H) (x : ι → F) (e : ι) (v : F) (hx : ¬ q (x e))
    (hv : ¬ q v) : sumPool q φ (Function.update x e v) = sumPool q φ x := by
  unfold sumPool
  refine Finset.sum_congr rfl fun k _ => ?_
  by_cases hk : k = e
  · subst hk
    simp [hx, hv]
  · simp [Function.update_of_ne hk]

/-- A DeepSets readout `ρ` of the sum pool and the context `c`. -/
def deepSets {C O : Type*} [AddCommMonoid H] (q : F → Prop) [DecidablePred q] (φ : F → H)
    (ρ : H → C → O) (x : ι → F) (c : C) : O :=
  ρ (sumPool q φ x) c

theorem deepSets_perm {C O : Type*} [AddCommMonoid H] (q : F → Prop) [DecidablePred q]
    (φ : F → H) (ρ : H → C → O) (x : ι → F) (c : C) (σ : Equiv.Perm ι) :
    deepSets q φ ρ (x ∘ σ) c = deepSets q φ ρ x c := by
  unfold deepSets
  rw [sumPool_perm]

/-- One message-passing round over element states `h` with presence `p`: a present element
adds the message from every other present element and updates; an absent one keeps its state. -/
def mpnnRound {S A : Type*} [AddCommMonoid A] [DecidableEq ι] (p : ι → Prop) [DecidablePred p]
    (M : S → S → A) (U : S → A → S) (h : ι → S) (i : ι) : S :=
  if p i then U (h i) (∑ j, if j ≠ i ∧ p j then M (h i) (h j) else 0) else h i

theorem mpnnRound_perm {S A : Type*} [AddCommMonoid A] [DecidableEq ι] (p : ι → Prop)
    [DecidablePred p] (M : S → S → A) (U : S → A → S) (h : ι → S) (σ : Equiv.Perm ι) :
    mpnnRound (p ∘ σ) M U (h ∘ σ) = mpnnRound p M U h ∘ σ := by
  funext i
  simp only [mpnnRound, Function.comp_apply]
  split_ifs with hi
  · congr 1
    rw [← Equiv.sum_comp σ (fun j => if j ≠ σ i ∧ p j then M (h (σ i)) (h j) else 0)]
    simp [σ.injective.ne_iff]
  · rfl

end Trech.Methods.SetPool
