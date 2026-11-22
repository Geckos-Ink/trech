# Formal laws and Lean verification — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Builds and dependencies](../../tooling/dependencies/ROADMAP.md) · [Geant4 transport and diagnostics](../simulation/ROADMAP.md) · [Lattice methods](../lattice/ROADMAP.md) · [Scenario bundles](../../scenarios/bundles/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Priority queue

Every open item of this branch, highest priority first. The dated records below are delivery
history: the "Residual" and "Next" notes inside them are tracked here, and this queue wins
where they disagree. Keys and route steps: [priority keys](../../ROADMAP.md#priority-keys) ·
[implementation route](../../ROADMAP.md#implementation-route). When an item lands, delete it here, add a
dated record below, and queue its residuals in the same change.

Standing constraint for every item: Lean stays optional. Each law keeps its classic C++/JS
implementation as the running path, with the Lean definition beside it for validation
([rule](AGENTS.md#rules)).

- **P1** · R8 · Law-pair contract, second half. The manifest (`trech_formal_laws_v1`), the `LawCheck` record and the citation rule landed 2026-11-22. Still open: provenance fields for a run that performs a law check (declaration, Lean module hash, toolchain, Mathlib revision), conditionally serialized, and where a validation companion's JS law-check records go in the outputs. Design first; no engine field before review. ([detail](#first-law-pairs--2026-11-22))
- **P1** · R8 · Law inventory, continued. Done: Compton kinematics, Beer–Lambert attenuation, lattice mass conservation. Next candidates: probability normalisation and nonnegativity of `ctx.react` transition outputs, the arbiter's prequential score as a proper scoring rule, energy conservation in recorded Geant4 secondaries, and the scalar lattice's conservation under zero-flux walls. Search Mathlib first for each. ([detail](#first-law-pairs--2026-11-22))
- **P2** · R8 · Call the classic checks from the engine: run `checkVelocityMoments`, `checkInvolution` and `checkPermutation` when a lattice is built (cheap, once), and expose the JS checks to validation companions' recorded output, without changing physics, RNG or emits. ([detail](#first-law-pairs--2026-11-22))
- **P2** · R8 · Conformance harness: a Lean reference evaluator (`@[export]` C symbols linked behind an opt-in `TRECH_ENABLE_LEAN`, default OFF, or a separate `lake exe` fed JSON) that checks the classic kernel on sampled or recorded inputs offline. Measure its cost; it never runs per step in production and never changes physics, RNG or emits. ([detail](#route-opened--2026-11-22))
- **P2** · R8 · Hardware acceleration contract: Lean compiles to scalar CPU code, so accelerated kernels (C++ SIMD, LibTorch, GPU) stay the compute path. Define how a proof about an algorithm's model transfers to its accelerated implementation (shared algorithm spec, sampled conformance, documented reduction-order and fused-operation differences). ([detail](#route-opened--2026-11-22))
- **P2** · R8 · Scenario side: a `.validation.js` companion uses `TRECH_FORMAL_LAWS` next to its own classic reference and records both verdicts (the library exists; no companion uses it yet). Never from the physics script, never on the decision path. ([detail](#route-opened--2026-11-22))
- **P3** · R8 · Reals vs floats: bridge Mathlib's `ℝ` theorems to IEEE-754 kernels with stated error bounds, interval arithmetic or a rounding-model proof; until then label every Lean verdict as covering the real-valued statement only. ([detail](#route-opened--2026-11-22))
- **P3** · R8 · Lean CI beyond this machine: the toolchain, cache and `trech_formal_lean_build` are verified on macOS arm64 only; check Linux and decide whether CI runs the Lean check. ([detail](#proofs-compiled-and-audited--2026-11-22))
- **P3** · R8 · Better Mathlib search now that Mathlib is built: `exact?`/`apply?`/Loogle-style queries in place of the grep, so equivalent statements under other names are found. ([detail](#route-opened--2026-11-22))
- **P3** · R5 · Geant4 secondary track: Lean statements of Geant4's basic laws (two-body kinematics, the Compton relation from four-momentum conservation, exponential attenuation, energy conservation in `SampleSecondaries`), attached through derived classes in shadow mode (inheritance preferred; `patches/geant4/` only for non-virtual code). Observation first; any replacement needs byte parity or a validated tolerance, a regression against the unpatched build and the owner's go-ahead. ([detail](AGENTS.md#geant4-secondary-track))
- **gated** · R8 · Owner decision: whether to add a physics-specific Lean library (for example PhysLean) as a further reference checkout, so physical laws are also checked against it before being declared.
- **gated** · R8 · Owner decision: when (if ever) Lean stops being optional for a given path.

## Route opened — 2026-11-22

- [x] `thirds/lean4` (`5ec4e0be17`) and `thirds/mathlib4` (`6ebcce3733`) added as shallow
  submodules tracking `master`. Mathlib expects `leanprover/lean4:v4.37.0-rc1`.
- [x] [`scripts/pull_lean.sh`](../../../scripts/pull_lean.sh): pull-before-use for both checkouts
  plus the toolchain check; [`scripts/lean_mathlib_search.py`](../../../scripts/lean_mathlib_search.py):
  grep of Mathlib declaration headers.
- [x] Handbook rules: Lean optional, classic + Lean pairs, Mathlib first, building gated, Lean
  off the decision path and off the hot path, reals vs floats, Geant4 secondary track.
- [ ] Nothing is built, linked or run; every item above is open.

## First law pairs — 2026-11-22

- [x] `formal/` Lake package (Mathlib by path, `lean-toolchain` = Mathlib's `v4.37.0-rc1`) with
  `Trech.Laws.Compton` (T/E within [0, edge], equality at back-scatter), `Trech.Laws.Attenuation`
  (survival multiplicative, in (0, 1], decreasing) and `Trech.Methods.Lattice` (TRT collision,
  zero-sum source and bijective streaming conserve the total). Mathlib lemma names were checked
  against `thirds/mathlib4` `6ebcce3733`; compiled the same day (record below).
- [x] Classic side: `trech::formal` checks in `trech_core`, `js/trech_formal_laws.js`, Lean
  citations in `KleinNishina.hpp`, `AnalyticCrossCheck.cpp` and `LatticeKinetic.cpp` (comments
  only; no behaviour change), `formal/laws.json`.
- [x] Tests: `trech_formal_laws` (all pairs pass; negative controls fail as intended; C++ and
  QuickJS Compton values bit-identical) and `trech_formal_law_pairs`. Opt-in
  `TRECH_ENABLE_LEAN_CHECK` registers `trech_formal_lean_build`.
- [x] Finding: the attenuation identity is exact over `ℝ` but off by ~2 ulp in doubles; the
  check states a 2e-15 relative tolerance and an exact-equality negative control records the gap.
- [ ] Open: provenance fields, engine call sites and the
  next inventory items, all queued above.

## Proofs compiled and audited — 2026-11-22

- [x] Owner go-ahead for the toolchain gate. `brew install elan-init` (elan 4.4.0),
  `elan toolchain install leanprover/lean4:v4.37.0-rc1` (commit `0b77e12952`, the tag the pull
  script resolves), `lake exe cache get` in `formal/` (9,135 Mathlib files, 6.9 GB in ignored
  `thirds/mathlib4/.lake`; Mathlib's dependencies in ignored `formal/.lake/packages`, pinned
  by the committed `formal/lake-manifest.json`).
- [x] `lake build`: 3,197 jobs. The only failure on first build was `relaxTRT`, which divides
  reals and had to be `noncomputable`; every proof compiled as written. The files then moved
  to the module system and off the deprecated `Mathlib.Data.Real.Basic` import
  (`Mathlib.Basic.Real.Basic`); the build has no errors and no warnings.
- [x] Axiom audit (`scripts/check_lean_laws.py`): all nine declarations in `laws.json` depend
  only on `propext`, `Classical.choice`, `Quot.sound`. The opt-in CTest
  `trech_formal_lean_build` (`TRECH_ENABLE_LEAN_CHECK=ON`) passed in `build/rel` (12 s); the
  option was then set back OFF there.
- [ ] Verified on macOS arm64 only; other platforms, and the audit after the next Mathlib pull,
  are untested. The proofs cover the real-valued statements, not the float kernels (queued above).
