module

public import Mathlib.Algebra.BigOperators.Group.Finset.Basic
public import Mathlib.Data.Finset.Card

/-!
# Domain routing of `ctx.learnDomains`

Role: `method_property`. `DomainLearner` keeps its response domains as the leaves of a binary
tree. Each inner node is a half-space test (`direction · x ≤ threshold` goes left); `route`
walks from the root to a leaf and returns its domain id. A split replaces one leaf by a node
with two new leaves; a merge replaces such a node by one new leaf. These theorems say what
that structure guarantees about where rows go:

* `route_mem_ids`: every row lands in a domain of the tree.
* `mem_region_iff`, `regions_disjoint`, `regions_cover`: the domains' regions partition the
  input space.
* `card_routed`: the rows of a batch, counted per domain, add up to the batch.
* `route_replace`: replacing a leaf `j` by a subtree changes the route only of rows that went
  to `j`; `split_keeps_other_rows` and `merge_keeps_other_rows` are the learner's two
  refinements.

The test is any Boolean predicate here; the engine's is a dot product compared with a
threshold, evaluated in doubles by the same function at routing and at split time.

Classic implementation (the running path): `src/ml/DomainLearner.cpp` (`route`, `split`,
`tryMerges`; both route and split call `goesLeft`).

Conformance: `tests/test_formal_laws.cpp` (`routePairs`) drives a learner through splits and
merges and checks, per call, that every routed row's domain is a current domain, that the
domains' element counts add up to the routed rows, that rows whose pre-refinement domain was
not split or merged keep it, and that the exported tree, walked as `route` is defined here,
gives every row's domain.
-/

@[expose] public section

namespace Trech.Methods.Route

variable {α : Type*}

/-- A routing tree: leaves carry domain ids, nodes a test (`true` = left). -/
inductive Tree (α : Type*) where
  | leaf (id : ℕ)
  | node (goLeft : α → Bool) (l r : Tree α)

end Trech.Methods.Route

namespace Trech.Methods.Route.Tree

variable {α : Type*}

/-- The domain a row lands in. -/
def route : Tree α → α → ℕ
  | leaf i, _ => i
  | node p l r, x => if p x then route l x else route r x

/-- The domain ids of the leaves, left to right. -/
def ids : Tree α → List ℕ
  | leaf i => [i]
  | node _ l r => ids l ++ ids r

/-- The rows of domain `i`, built from the tests along the paths to its leaves. -/
def region : Tree α → ℕ → Set α
  | leaf j, i => if j = i then Set.univ else ∅
  | node p l r, i => {x | p x = true ∧ x ∈ region l i} ∪ {x | p x = false ∧ x ∈ region r i}

/-- Replace every leaf `j` by the subtree `s`. -/
def replace : Tree α → ℕ → Tree α → Tree α
  | leaf k, j, s => if k = j then s else leaf k
  | node p l r, j, s => node p (replace l j s) (replace r j s)

theorem route_mem_ids (t : Tree α) (x : α) : t.route x ∈ t.ids := by
  induction t with
  | leaf i => simp [route, ids]
  | node p l r ihl ihr =>
    by_cases hp : p x <;> simp [route, ids, hp, ihl, ihr]

theorem mem_region_iff (t : Tree α) (x : α) (i : ℕ) : x ∈ t.region i ↔ t.route x = i := by
  induction t with
  | leaf j => by_cases h : j = i <;> simp [region, route, h]
  | node p l r ihl ihr =>
    by_cases hp : p x <;> simp [region, route, hp, ihl, ihr]

/-- Two domains never share a row. -/
theorem regions_disjoint (t : Tree α) {i j : ℕ} (hij : i ≠ j) :
    Disjoint (t.region i) (t.region j) := by
  rw [Set.disjoint_left]
  intro x hi hj
  rw [mem_region_iff] at hi hj
  exact hij (hi.symm.trans hj)

/-- Every row lies in the region of one of the tree's domains. -/
theorem regions_cover (t : Tree α) (x : α) : ∃ i ∈ t.ids, x ∈ t.region i :=
  ⟨t.route x, route_mem_ids t x, (mem_region_iff t x _).mpr rfl⟩

/-- Counted per domain, the rows of a batch add up to the batch. -/
theorem card_routed (t : Tree α) (rows : Finset α) :
    ∑ i ∈ t.ids.toFinset, (rows.filter fun x => t.route x = i).card = rows.card := by
  rw [Finset.card_eq_sum_card_fiberwise (f := t.route) (t := t.ids.toFinset)]
  intro x _
  exact List.mem_toFinset.mpr (route_mem_ids t x)

/-- Replacing leaf `j` reroutes only the rows that went to `j`. -/
theorem route_replace (t : Tree α) (j : ℕ) (s : Tree α) (x : α) :
    (t.replace j s).route x = if t.route x = j then s.route x else t.route x := by
  induction t with
  | leaf k => by_cases h : k = j <;> simp [replace, route, h]
  | node p l r ihl ihr =>
    by_cases hp : p x <;> simp [replace, route, hp, ihl, ihr]

/-- A split of domain `j` into `a` and `b` along the test `p` leaves every other row in place
and sends `j`'s rows to `a` or `b` by `p`. -/
theorem split_keeps_other_rows (t : Tree α) (j a b : ℕ) (p : α → Bool) (x : α) :
    (t.replace j (node p (leaf a) (leaf b))).route x =
      if t.route x = j then (if p x then a else b) else t.route x := by
  rw [route_replace]
  rfl

/-- A merge of the split node back into a new domain `k` leaves every row that was in neither
`a` nor `b` in place. -/
theorem merge_keeps_other_rows (t : Tree α) (j a b k : ℕ) (p : α → Bool) (x : α)
    (ha : (t.replace j (node p (leaf a) (leaf b))).route x ≠ a)
    (hb : (t.replace j (node p (leaf a) (leaf b))).route x ≠ b) :
    (t.replace j (leaf k)).route x = (t.replace j (node p (leaf a) (leaf b))).route x := by
  rw [split_keeps_other_rows] at ha hb ⊢
  rw [route_replace]
  by_cases hj : t.route x = j
  · exfalso
    by_cases hp : p x <;> simp [hj, hp] at ha hb
  · simp [hj]

end Trech.Methods.Route.Tree
