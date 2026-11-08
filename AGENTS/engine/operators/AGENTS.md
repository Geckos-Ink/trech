# Learned state and pair operators — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

## Choose a subcategory

| Scope | Context | Work remaining |
| --- | --- | --- |
| Operator migration contract | [AGENTS.md](migration/AGENTS.md) | [ROADMAP.md](migration/ROADMAP.md) |
| Operator migration prerequisites | [AGENTS.md](prerequisites/AGENTS.md) | [ROADMAP.md](prerequisites/ROADMAP.md) |

Related owners: [Reusable solution and material processes](../../scenarios/processes/AGENTS.md) · [Scenario law migration ledger](../../scenarios/migrations/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

- **`ctx.react` owns discrete invariants, not reaction knowledge.** Models predict only bounded
  hazards/channel weights. The caller declares integer species, channel deltas, and conserved
  coefficient vectors; `DiscreteTransition` validates exact conservation before inference,
  uses only hazards produced for that element (shared hazard keys cannot replace a blocked model),
  performs deterministic draws, enforces non-negative availability, and applies deltas atomically.
  A malformed/non-conserving topology or ambiguous hazard interface never draws or mutates.

- **One call may span several materials, each with its own operator.** `ctx.evolve`, `ctx.react`
  and `ctx.interact` all accept a per-element ARRAY for `element_kind`. `ctx.evolve`/`ctx.react`
  select an operator per element kind; `ctx.interact` composes the canonical unordered **pair kind**
  (`PairInteraction::pairKindName`, e.g. `melt|sand`) and selects per material *combination*. A kind
  that selects nothing is reported (`selection.groups`, run status `partial`), its elements stay
  **bit-identical**, and `ctx.react` consumes no RNG for it — never advanced (or drawn) by another
  material's law. Inference counting follows *matched* element-/pair-stages. This is what lets a
  scenario whose cells CHANGE material mid-run (`glass_from_sand.js`) keep using the right
  operator.
- **Independent trust evaluation counts.** Every operator result carries `starvedInferenceCount`
  (union of per-feature and joint starvation, once per successful evaluation) and
  `scaleMismatchedInferenceCount` (off-band evaluations). Both count actual matched element/pair
  stages; missing inputs and unloaded models contribute zero. These remain local checks, with
  no cross-stage/state lineage extension. Hook dispatch uses them for the independent
  [event resim policies](../inference/trust/AGENTS.md).
- **`ctx.interact` owns pair enumeration and equal-and-opposite application, not the interaction
  law.** Pairs are canonical `(a,b)`, `a < b`, enumerated in ascending index order so the
  floating-point accumulation cannot change with the cell size or hash-map layout; a declared link
  is always evaluated and never double-counted against the cutoff search; a field's declared
  symmetry applies the *same double* to both members (antisymmetric ⇒ the pair exchange cancels
  exactly); contributions accumulate and apply once, so no member sees a half-updated neighbour.

#### [`src/ml/StateEvolution.cpp`](../../../src/ml/StateEvolution.cpp) · [`StateEvolution.hpp`](../../../include/trech/ml/StateEvolution.hpp)

The per-element inference **operator**: where `ScaleCascade` answers "given this context, what are
the properties?", this answers "given this state, how does it CHANGE over dt?" — the half of the
physics scenarios used to hand-write as JavaScript per-element loops (reaction rate laws, relaxation
laws). Chains scale-tagged `GenericSurrogate` models over N elements in one deterministic pass.

- **Key symbols:** `EvolutionField` (name + the caller's declared bounds), `EvolutionRequest`
  (element-major `state`/`aux` blocks, `shared` context, `dt`, optional per-element
  `elementKindNames`/`elementKindIndex` for a multi-material pass), `EvolutionResult`
  (`inferenceCount` = stagesRun × elements, `outOfDomainInferenceCount`, per-stage
  `EvolutionStageTrace`), `StateEvolution::evolve`, `rateOutputName`/`assignOutputName`.
- **Naming convention (the whole domain interface):** `d_<field>_dt` → rate, accumulated across
  stages and integrated once per call; `set_<field>` → assignment applied immediately (visible to
  higher stages); anything else → intermediate merged into the per-element context. No domain name
  enters C++.
- **Tests:** [`tests/test_state_evolution.cpp`](../../../tests/test_state_evolution.cpp) (Geant4-free) +
  the `ctx.evolve` case in [`tests/test_js_runtime.cpp`](../../../tests/test_js_runtime.cpp), including
  contextual role/kind selection and ambiguous/no-compatible no-mutation.
- **Common mistakes:** resolving input names per element (plan once — the inner loop must be index
  arithmetic); applying rates immediately instead of accumulating (two stages must be able to drive
  one field); reporting one inference per call instead of stagesRun × elements.

#### [`src/ml/DiscreteTransition.cpp`](../../../src/ml/DiscreteTransition.cpp) · [`DiscreteTransition.hpp`](../../../include/trech/ml/DiscreteTransition.hpp)

The discrete learned operator behind `ctx.react`: N integer-state elements, declared
stoichiometric channels and conserved linear quantities, evaluated through scale-tagged
`GenericSurrogate` stages. It supports direct `hazard_<channel>` outputs or `hazard` plus
`weight_<channel>`, never both.

- **Key invariants:** topology/conservation validate before inference or RNG; hazards/weights clamp
  to [0,1]; competing direct hazards above unity renormalize deterministically; at most one channel
  is attempted per element per call; availability is checked before an atomic delta; integer state
  never goes negative. `inferenceCount` is N×K model evaluations while `drawCount`,
  `transitionAttempts`, `transitionsAccepted`, and `rejectedAvailability` remain distinct.
- **Tests:** [`tests/test_discrete_transition.cpp`](../../../tests/test_discrete_transition.cpp) +
  the `ctx.react` boundary/strict-mode case in [`tests/test_js_runtime.cpp`](../../../tests/test_js_runtime.cpp).

#### [`src/ml/PairInteraction.cpp`](../../../src/ml/PairInteraction.cpp) · [`PairInteraction.hpp`](../../../include/trech/ml/PairInteraction.hpp)

The pair/neighbour **interaction** operator behind `ctx.interact`: where `StateEvolution` answers
"how does THIS element change?", this answers "what does one element do TO ANOTHER" — the shape of
every remaining authored solver loop (MD force loops, bonded foam networks, PBF neighbourhood sums,
parcel cohesion/collision). The engine builds a deterministic uniform cell list, evaluates
scale-tagged `GenericSurrogate` stages over each canonical pair, and accumulates the result back
onto both members.

- **Naming convention:** `d_<element field>_dt` → rate contribution to both members (integrated once
  over `dt`); `add_<element field>` → direct increment (neighbourhood sum, no `dt`);
  `d_<pair field>_dt` / `set_<pair field>` → the pair's own persistent state (bond rest length,
  damage); anything else → intermediate. Members are read as `a_<name>`/`b_<name>`, geometry through
  reserved `r`, `dx/dy/dz`, `ux/uy/uz`, `dt`. `set_<element field>` is refused
  (`unappliedFieldOutputs`) — many pairs cannot assign one element one value.
- **Key symbols:** `PairElementField` (name + caller-declared `PairSymmetry` + bounds),
  `PairStateField`, `PairLink`, `PairInteractionRequest` (element-major state/aux, positions,
  `cutoff`, `maxNeighborPairs`, links + pair state, shared, `dt`), `PairInteractionResult`
  (`pairCount`/`linkPairCount`/`neighborPairCount`, `neighborPairsSkipped`, `noPairs` for a
  well-formed request with an empty pair list — exposed as `blockedReason:"no_pairs"` —, `invalidLinks`,
  `duplicateLinks`, `inferenceCount` = pairs × stages, per-stage `PairStageTrace`),
  `PairInteraction::interact`, `PairInteraction::pairKindName` (canonical unordered material
  combination; a stage's `pairKindIndex` binds it to one combination).
- **Tests:** [`tests/test_pair_interaction.cpp`](../../../tests/test_pair_interaction.cpp) (Geant4-free) +
  the `ctx.interact` case in [`tests/test_js_runtime.cpp`](../../../tests/test_js_runtime.cpp).
- **Common mistakes:** letting the cell map or the cutoff decide accumulation order (sort/enumerate
  by index instead); applying a bond only when it is inside the cutoff (a stretched bond is exactly
  the interesting case); scaling an `add_` neighbourhood sum by `dt`; reporting one inference per
  call instead of pairs × stages.
