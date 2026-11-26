module

public import Mathlib.Algebra.Order.Group.MinMax
public import Mathlib.Basic.Real.Basic
public import Mathlib.Data.List.Forall2
import Mathlib.Tactic.Linarith

/-!
# Per-feature domain: the out-of-domain verdict and the occupancy bin

Role: `method_property`. `GenericSurrogate::coverageVector` runs two per-feature checks before
the joint one.

**Out-of-domain verdict.** Each input's excess `|z_i| - radius_i` (standardized units) is compared
with a small tolerance; an excess above it names the input out-of-domain and raises
`extrapolation` to the largest such excess. `inDomain` is "no input named".

* `extrap_eq_zero_iff`: with a non-negative tolerance, `extrapolation` is 0 exactly when every
  excess is within the tolerance, so `inDomain` and `extrapolation = 0` say the same thing.
* `le_extrap`, `extrap_attained`: otherwise it is the largest excess above the tolerance, and
  is one of them.
* `extrap_mono`: moving every input farther out (each excess no smaller) never lowers it.

**Occupancy bin.** Training (`numpy.histogram`) counts a value in the bin `b` whose edges contain
it: `e b ≤ x < e (b+1)`, the last bin closed. The engine finds the bin from a scaled-index guess
`g`, then corrects it by one against the edges, as numpy does.

* `correct_spec`: when the guess is at most one bin off, the corrected index is a bin that
  contains `x`. No monotonicity is needed for this.
* `bin_unique`: with monotone edges at most one bin contains `x`, so the engine and the trainer
  pick the same bin.
* `training_value_not_starved`: every training value lands in a bin the trainer counted, so
  the engine never reads a training value as starved.

The excesses and edges are reals here. In doubles the engine computes the same excesses and
comparisons, and its edges `k * ((hi - lo) / n) + lo` (last edge `hi`) are numpy's `linspace`
edges bit for bit; the scaled-index guess can be one bin off within about one ulp of an edge,
which is what the correction is for. The conformance test checks the off-by-one hypothesis and
the containment on edge-adjacent values, and `tests/test_occupancy_bins.py` checks the engine's
bins against `numpy.histogram` itself.

Classic implementation (the running path): `src/ml/GenericSurrogate.cpp`
(`GenericSurrogate::occupancyBin` and the per-feature loop of `coverageVector`).

Conformance: `tests/test_formal_laws.cpp` (`domainPairs`).
-/

@[expose] public section

namespace Trech.Methods.Domain

/-! ## Out-of-domain verdict -/

/-- One input: an excess above the tolerance raises the running extrapolation. -/
noncomputable def stepE (tol m o : ℝ) : ℝ := if tol < o then max m o else m

/-- The engine's `extrapolation`: the largest excess above the tolerance, 0 when there is none. -/
noncomputable def extrap (tol : ℝ) (os : List ℝ) : ℝ := os.foldl (stepE tol) 0

theorem start_le_foldl (tol : ℝ) (os : List ℝ) (m : ℝ) : m ≤ os.foldl (stepE tol) m := by
  induction os generalizing m with
  | nil => exact le_rfl
  | cons o os ih =>
    simp only [List.foldl_cons]
    refine le_trans ?_ (ih _)
    unfold stepE; split_ifs <;> simp

theorem le_foldl (tol : ℝ) (os : List ℝ) (m : ℝ) {o : ℝ} (ho : o ∈ os) (h : tol < o) :
    o ≤ os.foldl (stepE tol) m := by
  induction os generalizing m with
  | nil => simp at ho
  | cons o' os ih =>
    simp only [List.foldl_cons]
    rcases List.mem_cons.mp ho with rfl | ho
    · refine le_trans ?_ (start_le_foldl tol os _)
      simp [stepE, h]
    · exact ih _ ho

theorem foldl_of_within (tol : ℝ) (os : List ℝ) (m : ℝ) (h : ∀ o ∈ os, o ≤ tol) :
    os.foldl (stepE tol) m = m := by
  induction os generalizing m with
  | nil => rfl
  | cons o os ih =>
    simp only [List.foldl_cons]
    have ho : ¬ tol < o := not_lt.mpr (h o (List.mem_cons_self ..))
    simp only [stepE, ho, ite_false]
    exact ih m fun u hu => h u (List.mem_cons_of_mem _ hu)

theorem foldl_cases (tol : ℝ) (os : List ℝ) (m : ℝ) :
    os.foldl (stepE tol) m = m ∨ ∃ o ∈ os, tol < o ∧ os.foldl (stepE tol) m = o := by
  induction os generalizing m with
  | nil => left; rfl
  | cons o os ih =>
    simp only [List.foldl_cons, List.mem_cons, exists_eq_or_imp]
    rcases ih (stepE tol m o) with e | ⟨u, hu, hu', e⟩
    · rw [e]; unfold stepE
      split_ifs with h
      · rcases le_total m o with hmo | hmo
        · right; left; exact ⟨h, max_eq_right hmo⟩
        · left; exact max_eq_left hmo
      · left; rfl
    · right; right; exact ⟨u, hu, hu', e⟩

theorem extrap_nonneg (tol : ℝ) (os : List ℝ) : 0 ≤ extrap tol os := start_le_foldl tol os 0

/-- `extrapolation` is 0 exactly when every excess is within the tolerance: the engine's
`inDomain` verdict. -/
theorem extrap_eq_zero_iff {tol : ℝ} (htol : 0 ≤ tol) (os : List ℝ) :
    extrap tol os = 0 ↔ ∀ o ∈ os, o ≤ tol := by
  constructor
  · intro h o ho
    by_contra hc
    have hlt : tol < o := lt_of_not_ge hc
    have := le_foldl tol os 0 ho hlt
    unfold extrap at h; linarith
  · exact foldl_of_within tol os 0

/-- Every excess above the tolerance is at most `extrapolation`. -/
theorem le_extrap (tol : ℝ) (os : List ℝ) {o : ℝ} (ho : o ∈ os) (h : tol < o) :
    o ≤ extrap tol os := le_foldl tol os 0 ho h

/-- `extrapolation` is 0 or one of the excesses above the tolerance. -/
theorem extrap_attained (tol : ℝ) (os : List ℝ) :
    extrap tol os = 0 ∨ ∃ o ∈ os, tol < o ∧ extrap tol os = o := foldl_cases tol os 0

theorem stepE_mono (tol : ℝ) {m m' o o' : ℝ} (hm : m ≤ m') (ho : o ≤ o') :
    stepE tol m o ≤ stepE tol m' o' := by
  unfold stepE
  split_ifs with h1 h2 h2
  · exact max_le_max hm ho
  · exact absurd (lt_of_lt_of_le h1 ho) h2
  · exact le_trans hm (le_max_left _ _)
  · exact hm

/-- Moving every input farther out (no excess smaller) never lowers `extrapolation`. -/
theorem extrap_mono (tol : ℝ) {os os' : List ℝ} (h : List.Forall₂ (· ≤ ·) os os') :
    extrap tol os ≤ extrap tol os' := by
  unfold extrap
  suffices ∀ m m' : ℝ, m ≤ m' → os.foldl (stepE tol) m ≤ os'.foldl (stepE tol) m' from
    this 0 0 le_rfl
  induction h with
  | nil => intro m m' hm; exact hm
  | cons ho _ ih => intro m m' hm; exact ih _ _ (stepE_mono tol hm ho)

/-! ## Occupancy bin -/

variable (e : ℕ → ℝ) (n : ℕ)

/-- Bin `b` of `n` contains `x`: `e b ≤ x < e (b+1)`, the last bin closed on the right. -/
def Contains (b : ℕ) (x : ℝ) : Prop := b < n ∧ e b ≤ x ∧ (b + 1 = n ∨ x < e (b + 1))

/-- numpy's correction of the scaled-index guess `g`: one bin down when `x` is below the guessed
bin's lower edge, one bin up when it reaches the next edge (never past the last bin). -/
noncomputable def correct (g : ℕ) (x : ℝ) : ℕ :=
  if 0 < g ∧ x < e g then g - 1 else if g + 1 ≠ n ∧ e (g + 1) ≤ x then g + 1 else g

/-- A guess at most one bin off is corrected to a bin containing `x`. -/
theorem correct_spec {g : ℕ} {x : ℝ} (hg : g < n) (h0 : e 0 ≤ x)
    (hlo : g = 0 ∨ e (g - 1) ≤ x) (hhi : n ≤ g + 2 ∨ x < e (g + 2)) :
    Contains e n (correct e n g x) x := by
  unfold correct Contains
  split_ifs with hA hB
  · obtain ⟨hpos, hx⟩ := hA
    refine ⟨by omega, ?_, ?_⟩
    · rcases hlo with h | h
      · omega
      · exact h
    · right; rwa [Nat.sub_add_cancel hpos]
  · obtain ⟨hne, hx⟩ := hB
    refine ⟨by omega, hx, ?_⟩
    rcases hhi with h | h
    · left; omega
    · right; exact h
  · refine ⟨hg, ?_, ?_⟩
    · rcases Nat.eq_zero_or_pos g with h | h
      · rw [h]; exact h0
      · exact le_of_not_gt fun hx => hA ⟨h, hx⟩
    · by_cases hn : g + 1 = n
      · left; exact hn
      · right; exact lt_of_not_ge fun hx => hB ⟨hn, hx⟩

/-- With monotone edges at most one bin contains `x`. -/
theorem bin_unique (he : Monotone e) {b b' : ℕ} {x : ℝ} (hb : Contains e n b x)
    (hb' : Contains e n b' x) : b = b' := by
  have key : ∀ {c c' : ℕ}, Contains e n c x → Contains e n c' x → ¬ c < c' := by
    intro c c' hc hc' hlt
    obtain ⟨_, _, hc3⟩ := hc
    obtain ⟨hc'1, hc'2, _⟩ := hc'
    rcases hc3 with h | h
    · omega
    · have := he (show c + 1 ≤ c' by omega); linarith
  rcases lt_trichotomy b b' with h | h | h
  · exact absurd h (key hb hb')
  · exact h
  · exact absurd h (key hb' hb)

/-- A training value is never starved: when the trainer counts each value in a bin containing it
and the engine's bin contains the value too, the engine's bin has a positive count. -/
theorem training_value_not_starved (he : Monotone e) (trainer : ℝ → ℕ)
    (htr : ∀ u, Contains e n (trainer u) u) (train : List ℝ) {t : ℝ} (ht : t ∈ train) {b : ℕ}
    (hb : Contains e n b t) : 0 < train.countP fun u => trainer u = b := by
  have hbt : trainer t = b := bin_unique e n he (htr t) hb
  exact List.countP_pos_iff.mpr ⟨t, ht, by simpa using hbt⟩

end Trech.Methods.Domain
