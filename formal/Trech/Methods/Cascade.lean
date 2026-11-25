module

public import Mathlib.Data.Finset.Basic
public import Mathlib.Data.List.Perm.Basic
public import Mathlib.Basic.Real.Basic

/-!
# `ScaleCascade` chaining: registration order does not change the chained result

Role: `method_property`. `ScaleCascade::run` sorts its stages by scale band, then runs each band
in turn on one shared context of named facts. Inside a band it runs the first *ready* stage
(every declared input present in the context), keeping registration order among ready peers.
A stage reads its declared inputs and, when it predicts, writes its declared outputs into the
context; a stage that is not ready, or whose model declines, leaves the context unchanged.

The context is a map from fact names to optional values (`none` = absent). A stage's prediction
depends only on the facts it reads; readiness is part of that dependence.

* `run_of_notMem`, `run_of_mem`: a stage changes no fact outside its declared outputs, and on
  an output keeps the old fact when it does not predict.
* `run_comm`: two stages commute when they write disjoint facts and neither reads a fact the
  other writes.
* `runAll_move_front`: a stage moves to the front of a band past every stage it commutes with.
* `runAll_perm`: two orders of one band in which every stage comes after every producer of its
  inputs (`ProducerFirst`: no later stage writes a fact an earlier one reads, and no two stages
  write the same fact) give the same context.
* `cascade_perm`: permuting the registration of the whole cascade permutes each band's stages
  only (bands run in a fixed scale order), so when the band orders it runs are producer-first,
  the chained result does not depend on registration order.
* `rivals_order_matters`, `stale_read_order_matters`: the two hypotheses are needed. Two stages
  writing one fact (rivals) leave the last writer's value; a consumer that runs on a fact
  already present (a seed or a lower band's value) before an in-band producer replaces it reads
  the stale value.

No real arithmetic is involved: each stage evaluates the same model on the same inputs in every
order, so in doubles the agreement is exact.

Not proved: that the engine's greedy "first ready stage" choice is producer-first. It is when no
fact an in-band stage writes is present at band start; the conformance test checks the chosen
orders. Rival sets are arbitrated at band end (`arbitrateRivals`), outside this statement.

Classic implementation (the running path): `src/ml/ScaleCascade.cpp` (the band sort and the
ready-stage rotation in `ScaleCascade::run`).

Conformance: `tests/test_formal_laws.cpp` (`cascadePairs`) registers a layered set of stages
across three bands in many orders and compares the contexts bit for bit, checks that every stage
that ran ran after its in-band producers, and shows both counterexamples on the engine.
-/

@[expose] public section

namespace Trech.Methods.Cascade

variable {κ : Type*} [DecidableEq κ]

/-- The facts a cascade reads and writes: a name maps to a value or is absent. -/
abbrev Context (κ : Type*) := κ → Option ℝ

/-- A stage: the facts it reads, the facts it writes, and its prediction (`none` when it does
not run: an input is missing or the model declines). -/
structure Stage (κ : Type*) where
  reads : Finset κ
  writes : Finset κ
  predict : Context κ → Option (κ → ℝ)

/-- The prediction depends only on the facts the stage reads. -/
def ReadsOnly (s : Stage κ) : Prop :=
  ∀ c c' : Context κ, (∀ k ∈ s.reads, c k = c' k) → s.predict c = s.predict c'

/-- Run one stage: merge its outputs into the context when it predicts. -/
def run (s : Stage κ) (c : Context κ) : Context κ :=
  match s.predict c with
  | none => c
  | some v => fun k => if k ∈ s.writes then some (v k) else c k

/-- Run a band's stages in list order. -/
def runAll (l : List (Stage κ)) (c : Context κ) : Context κ :=
  l.foldl (fun c s => run s c) c

/-- `a` may run before `b`: they write disjoint facts and `b` writes nothing `a` reads. -/
def Before (a b : Stage κ) : Prop :=
  Disjoint a.writes b.writes ∧ Disjoint a.reads b.writes

/-- Every stage comes after every producer of its inputs, and no fact has two writers. -/
def ProducerFirst (l : List (Stage κ)) : Prop := l.Pairwise Before

/-- A stage changes no fact outside its outputs. -/
theorem run_of_notMem (s : Stage κ) (c : Context κ) {k : κ} (hk : k ∉ s.writes) :
    run s c k = c k := by
  unfold run
  cases s.predict c <;> simp [hk]

/-- On one of its outputs, a stage leaves the fact as it was when it does not predict. -/
theorem run_of_mem (s : Stage κ) (c : Context κ) {k : κ} (hk : k ∈ s.writes) :
    run s c k = (s.predict c).elim (c k) fun v => some (v k) := by
  unfold run
  cases s.predict c <;> simp [hk]

/-- Two stages that write disjoint facts, neither reading the other's, commute. -/
theorem run_comm (a b : Stage κ) (ha : ReadsOnly a) (hb : ReadsOnly b)
    (hw : Disjoint a.writes b.writes) (hab : Disjoint a.reads b.writes)
    (hba : Disjoint b.reads a.writes) (c : Context κ) :
    run a (run b c) = run b (run a c) := by
  have pa : a.predict (run b c) = a.predict c :=
    ha _ _ fun k hk => run_of_notMem b c (Finset.disjoint_left.mp hab hk)
  have pb : b.predict (run a c) = b.predict c :=
    hb _ _ fun k hk => run_of_notMem a c (Finset.disjoint_left.mp hba hk)
  funext k
  by_cases hka : k ∈ a.writes
  · have hkb : k ∉ b.writes := Finset.disjoint_left.mp hw hka
    rw [run_of_notMem b _ hkb, run_of_mem a _ hka, run_of_mem a _ hka, pa,
      run_of_notMem b c hkb]
  · rw [run_of_notMem a _ hka]
    by_cases hkb : k ∈ b.writes
    · rw [run_of_mem b _ hkb, run_of_mem b _ hkb, pb, run_of_notMem a c hka]
    · rw [run_of_notMem b _ hkb, run_of_notMem b _ hkb, run_of_notMem a _ hka]

/-- A stage moves to the front of a band past stages it commutes with. -/
theorem runAll_move_front (s : Stage κ) (a b : List (Stage κ))
    (h : ∀ t ∈ a, ∀ c : Context κ, run s (run t c) = run t (run s c)) (c : Context κ) :
    runAll (a ++ s :: b) c = runAll (s :: (a ++ b)) c := by
  induction a generalizing c with
  | nil => rfl
  | cons t a ih =>
    have ht := h t (List.mem_cons_self ..)
    have hrest : ∀ u ∈ a, ∀ c : Context κ, run s (run u c) = run u (run s c) :=
      fun u hu => h u (List.mem_cons_of_mem _ hu)
    simp only [runAll, List.cons_append, List.foldl_cons] at ih ⊢
    rw [ih hrest, ht]

/-- Two producer-first orders of the same band give the same context. -/
theorem runAll_perm {l l' : List (Stage κ)} (hp : l.Perm l') (hl : ProducerFirst l)
    (hl' : ProducerFirst l') (hr : ∀ s ∈ l, ReadsOnly s) (c : Context κ) :
    runAll l c = runAll l' c := by
  induction l' generalizing l c with
  | nil => rw [List.perm_nil.mp hp]
  | cons s r ih =>
    obtain ⟨a, b, rfl⟩ := List.append_of_mem (hp.symm.subset (List.mem_cons_self ..))
    unfold ProducerFirst at hl hl'
    rw [List.pairwise_append, List.pairwise_cons] at hl
    rw [List.pairwise_cons] at hl'
    have hrs : ReadsOnly s := hr s (List.mem_append_right _ (List.mem_cons_self ..))
    have hcomm : ∀ t ∈ a, ∀ c : Context κ, run s (run t c) = run t (run s c) := by
      intro t ht c
      have htr : ReadsOnly t := hr t (List.mem_append_left _ ht)
      have hts : Before t s := hl.2.2 t ht s (List.mem_cons_self ..)
      have hpa : (a ++ b).Perm r :=
        ((List.perm_middle).symm.trans hp).cons_inv
      have hst : Before s t := hl'.1 t (hpa.subset (List.mem_append_left _ ht))
      exact (run_comm t s htr hrs hts.1 hts.2 hst.2 c).symm
    rw [runAll_move_front s a b hcomm]
    simp only [runAll, List.foldl_cons]
    have hpa : (a ++ b).Perm r := ((List.perm_middle).symm.trans hp).cons_inv
    have hab : ProducerFirst (a ++ b) := by
      unfold ProducerFirst
      rw [List.pairwise_append]
      exact ⟨hl.1, hl.2.1.2, fun x hx y hy => hl.2.2 x hx y (List.mem_cons_of_mem _ hy)⟩
    have hrab : ∀ t ∈ a ++ b, ReadsOnly t := by
      intro t ht
      rcases List.mem_append.mp ht with h | h
      · exact hr t (List.mem_append_left _ h)
      · exact hr t (List.mem_append_right _ (List.mem_cons_of_mem _ h))
    exact ih hpa hab hl'.2 hrab _

/-- A cascade: its bands in scale order, each running the registered stages of that band. -/
def cascade {β : Type*} [DecidableEq β] (bands : List β) (band : Stage κ → β)
    (order : β → List (Stage κ) → List (Stage κ)) (regs : List (Stage κ)) (c : Context κ) :
    Context κ :=
  bands.foldl (fun c x => runAll (order x (regs.filter fun s => band s = x)) c) c

/-- Registration order does not change the chained result: when two registrations are
permutations of each other and the order each band runs (`order`, any reordering of the band's
registered stages, such as the engine's ready-stage choice) is producer-first in both, the
cascades agree. -/
theorem cascade_perm {β : Type*} [DecidableEq β] (bands : List β) (band : Stage κ → β)
    (order : β → List (Stage κ) → List (Stage κ))
    (horder : ∀ x l, (order x l).Perm l)
    {regs regs' : List (Stage κ)} (hp : regs.Perm regs')
    (hpf : ∀ x ∈ bands, ProducerFirst (order x (regs.filter fun s => band s = x)) ∧
      ProducerFirst (order x (regs'.filter fun s => band s = x)))
    (hr : ∀ s ∈ regs, ReadsOnly s) (c : Context κ) :
    cascade bands band order regs c = cascade bands band order regs' c := by
  induction bands generalizing c with
  | nil => rfl
  | cons x bands ih =>
    simp only [cascade, List.foldl_cons] at ih ⊢
    have hx := hpf x (List.mem_cons_self ..)
    have hperm : (order x (regs.filter fun s => band s = x)).Perm
        (order x (regs'.filter fun s => band s = x)) :=
      (horder x _).trans ((hp.filter _).trans (horder x _).symm)
    have hrx : ∀ s ∈ order x (regs.filter fun s => band s = x), ReadsOnly s := fun s hs =>
      hr s (List.mem_of_mem_filter ((horder x _).subset hs))
    rw [runAll_perm hperm hx.1 hx.2 hrx c]
    exact ih (fun y hy => hpf y (List.mem_cons_of_mem _ hy)) _

/-- Rivals: two stages writing one fact leave the last writer's value. -/
theorem rivals_order_matters :
    let one : Stage Unit := ⟨∅, {()}, fun _ => some fun _ => 1⟩
    let two : Stage Unit := ⟨∅, {()}, fun _ => some fun _ => 2⟩
    runAll [one, two] (fun _ => none) ≠ runAll [two, one] (fun _ => none) := by
  intro one two h
  have := congrFun h ()
  simp [one, two, runAll, run] at this

/-- A stale read: fact `false` is present (a seed) with value 0; `refine` replaces it by 1 and
`read` copies it into fact `true`. Run before its producer, `read` copies the seed. -/
theorem stale_read_order_matters :
    let refine : Stage Bool := ⟨∅, {false}, fun _ => some fun _ => 1⟩
    let read : Stage Bool :=
      ⟨{false}, {true}, fun c => (c false).map fun v _ => v⟩
    let seed : Context Bool := fun k => if k then none else some 0
    runAll [refine, read] seed ≠ runAll [read, refine] seed := by
  intro refine read seed h
  have := congrFun h true
  simp [refine, read, seed, runAll, run] at this

end Trech.Methods.Cascade
