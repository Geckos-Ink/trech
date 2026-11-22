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

- **P1** · R8 · Law-pair contract. Specify how a classic implementation and its Lean definition are paired: the naming convention (Lean namespace `Trech.Laws.*` / `Trech.Methods.*` ↔ classic source path), the roles (`invariant`, `method_property`, `reference`, `validation`), the conformance record (inputs, tolerance, result, skip reason when Lean is absent), and the provenance fields (declaration, module hash, toolchain, Mathlib revision), conditionally serialized. Design document plus a schema draft first; no engine field before it is reviewed. ([detail](#route-opened--2026-11-22))
- **P1** · R8 · First law inventory. List the laws and invariants TRECH already computes classically (lattice mass/momentum conservation, probability normalisation in `ctx.react`, the arbiter's prequential scoring, energy conservation in recorded Geant4 steps, the analytic cross-checks), mark which Mathlib already covers (`scripts/lean_mathlib_search.py`), and pick the first two pairs to formalise. ([detail](#route-opened--2026-11-22))
- **P2** · R8 · Lean project skeleton: a `formal/` Lake package requiring Mathlib from `thirds/mathlib4` by path, pinned to Mathlib's `lean-toolchain`, with the first two law pairs and an optional CTest entry that skips when `lake` is absent. Blocked by the toolchain gate below. ([detail](#route-opened--2026-11-22))
- **P2** · R8 · Conformance harness: a Lean reference evaluator (`@[export]` C symbols linked behind an opt-in `TRECH_ENABLE_LEAN`, default OFF, or a separate `lake exe` fed JSON) that checks the classic kernel on sampled or recorded inputs offline. Measure its cost; it never runs per step in production and never changes physics, RNG or emits. ([detail](#route-opened--2026-11-22))
- **P2** · R8 · Hardware acceleration contract: Lean compiles to scalar CPU code, so accelerated kernels (C++ SIMD, LibTorch, GPU) stay the compute path. Define how a proof about an algorithm's model transfers to its accelerated implementation (shared algorithm spec, sampled conformance, documented reduction-order and fused-operation differences). ([detail](#route-opened--2026-11-22))
- **P2** · R8 · Scenario side: a `.validation.js` companion cites a Lean law next to its classic JS reference and records both verdicts. Never from the physics script, never on the decision path. ([detail](#route-opened--2026-11-22))
- **P3** · R8 · Reals vs floats: bridge Mathlib's `ℝ` theorems to IEEE-754 kernels with stated error bounds, interval arithmetic or a rounding-model proof; until then label every Lean verdict as covering the real-valued statement only. ([detail](#route-opened--2026-11-22))
- **P3** · R8 · Better Mathlib search once built: `exact?`/`apply?`/Loogle-style queries in place of the grep, so equivalent statements under other names are found. ([detail](#route-opened--2026-11-22))
- **P3** · R5 · Geant4 secondary track: Lean statements of Geant4's basic laws (two-body kinematics, the Compton relation from four-momentum conservation, exponential attenuation, energy conservation in `SampleSecondaries`), attached through derived classes in shadow mode (inheritance preferred; `patches/geant4/` only for non-virtual code). Observation first; any replacement needs byte parity or a validated tolerance, a regression against the unpatched build and the owner's go-ahead. ([detail](AGENTS.md#geant4-secondary-track))
- **gated** · R8 · Lean toolchain and Mathlib build: install Mathlib's `lean-toolchain` (`elan`) or build `thirds/lean4` at that tag, then `lake exe cache get` or a full Mathlib build (heavy: GBs or a long compile; needs an explicit go-ahead). Tracked in the [dependency queue](../../tooling/dependencies/ROADMAP.md#priority-queue).
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
