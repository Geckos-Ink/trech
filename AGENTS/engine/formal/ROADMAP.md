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

- **P1** · R8 · Law inventory, continued. Done: Compton kinematics, Beer–Lambert attenuation, lattice mass conservation, scalar-lattice conservation, `ctx.react` step probabilities, the arbiter's proper squared score. Added declared `ctx.react` count conservation and antisymmetric `ctx.interact` exchange. Next: energy conservation in recorded Geant4 secondaries. Search Mathlib first. ([detail](#operator-conservation-2026-11-22))
- **P2** · R8 · Conformance harness: a Lean reference evaluator (`@[export]` C symbols linked behind an opt-in `TRECH_ENABLE_LEAN`, default OFF, or a separate `lake exe` fed JSON) that checks the classic kernel on sampled or recorded inputs offline. Measure its cost; it never runs per step in production and never changes physics, RNG or emits. ([detail](#route-opened--2026-11-22))
- **P2** · R8 · Hardware acceleration contract: Lean compiles to scalar CPU code, so accelerated kernels (C++ SIMD, LibTorch, GPU) stay the compute path. Define how a proof about an algorithm's model transfers to its accelerated implementation (shared algorithm spec, sampled conformance, documented reduction-order and fused-operation differences). ([detail](#route-opened--2026-11-22))
- **P3** · R8 · More companions recording law checks: only `analytic_compton_transfer` records `TRECH_FORMAL_LAWS` verdicts. Candidates: `analytic_beer_lambert` (memorylessness at its own attenuation coefficients), and companions of `ctx.react` scenarios checking recorded per-cell probabilities with `checkProbabilityVector`. Always from the `.validation.js` companion under the `validation` role, never on the decision path. ([detail](#law-checks-in-run-outputs--2026-11-22))
- **P3** · R8 · Reals vs floats: bridge Mathlib's `ℝ` theorems to IEEE-754 kernels with stated error bounds, interval arithmetic or a rounding-model proof; until then label every Lean verdict as covering the real-valued statement only. ([detail](#route-opened--2026-11-22))
- **P3** · R8 · Arbiter ranking across calls: `Trech.Methods.Arbiter` covers one weighted sample; the leader ranks by the decayed mean of log call RMSE (a geometric mean over calls) and the learned policy by a decayed log-ratio score. State and prove what those rankings preserve (for example, that a method better on every call ranks first) or document why they need no such guarantee. ([detail](#more-law-pairs-and-the-first-engine-check--2026-11-22))
- **P3** · R8 · Lean CI beyond this machine: the toolchain, cache and `trech_formal_lean_build` are verified on macOS arm64 only; check Linux and decide whether CI runs the Lean check. ([detail](#proofs-compiled-and-audited--2026-11-22))
- **P3** · R8 · Better Mathlib search now that Mathlib is built: `exact?`/`apply?`/Loogle-style queries in place of the grep, so equivalent statements under other names are found. ([detail](#route-opened--2026-11-22))
- **P3** · R5 · Geant4 secondary track: Lean statements of Geant4's basic laws (two-body kinematics, the Compton relation from four-momentum conservation, exponential attenuation, energy conservation in `SampleSecondaries`), attached through derived classes in shadow mode (inheritance preferred; `patches/geant4/` only for non-virtual code). Observation first; any replacement needs byte parity or a validated tolerance, a regression against the unpatched build and the owner's go-ahead. ([detail](AGENTS.md#geant4-secondary-track))
- **gated** · R8 · Owner decision: whether to add a physics-specific Lean library (for example PhysLean) as a further reference checkout, so physical laws are also checked against it before being declared.
- **gated** · R8 · Owner decision: when (if ever) Lean stops being optional for a given path.

## Operator conservation (2026-11-22)

- [x] Added Lean statements for declared integer conservation and atomic count bounds in
  `ctx.react`, plus exchange of equal-and-opposite rates and increments in `ctx.interact`.
  Checked all 22 theorems against the standard axioms on the pinned Mathlib toolchain.
- [x] Classic conformance covers acceptance, availability and signed 64-bit overflow, early
  rejection of an unbalanced channel, and two antisymmetric links sharing a member. Pair
  conformance uses `1e-15` relative tolerance and verifies that clipping changes the total.
- Verification: Debug CTest 80/80 and the focused V8 set 3/3. The Geant4 Compton smoke accepted
  the new audit identity for all recorded checks and kept 200-event scores byte-identical with
  and without the audit.

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

## More law pairs and the first engine check — 2026-11-22

- [x] Pulled both Lean checkouts first (`scripts/pull_lean.sh`: no movement, lean4 `5ec4e0be17`,
  mathlib4 `6ebcce3733`). Mathlib searched for each statement: it has `Real.log_lt_log_iff` and
  the measure-theoretic `ProbabilityTheory.variance` lemmas, but no finite weighted
  "mean minimises the squared score" and nothing on the two-stage draw, so both are stated here.
- [x] `Trech.Methods.Transition` (5 theorems): `stepProbability h s c = h·s c/∑ s` is
  nonnegative, sums to `h`, leaves `1 − h ≥ 0`, equals `s c` in direct mode, and
  `channelDraw_lt_iff` is the inverse-CDF step. Classic side: the draw in
  `DiscreteTransition::react` moved verbatim into `selectTransitionChannel` (same operations in
  the same order, so RNG and results are unchanged; every CTest passed after it).
- [x] `Trech.Methods.Arbiter` (4 theorems): bias–variance split of the weighted squared score,
  the mean minimises it (strictly for positive weight), `log(error + floor)` keeps the order.
- [x] `Trech.Methods.Lattice.advectedEquilibrium_sum`: the scalar equilibrium carries the cell
  value; with the existing collision and streaming theorems it gives the scalar-lattice pair.
- [x] Engine call site: `Lattice::checkLaws` (end of `build()`), stored in `lawChecks()` and
  traced at info under `formal` (warn when a check fails). Moving walls and Dirichlet links
  record "not conservative by design".
- [x] Conformance (`trech_formal_laws`): `selectTransitionChannel` over 2^20 grid draws in four
  hazard/score cases matches `h·s_c/S` within 2/2^20 (8.7e-7 seen); the arbiter with a biased
  fallback ends with the unbiased method leading and lowest in `rmse_common`; a walled D2Q5
  lattice with an obstacle and prescribed advection keeps its total over 400 steps (1.6e-14
  relative seen, 1e-13 allowed) while a Dirichlet copy does not (negative control).
- [x] Audit: 19 distinct theorems (shared ones now audited once), all on the standard axioms;
  `--report` writes `trech_lean_audit_v1`. Full CTest in `build/rel`: 80/80 passed.
- [ ] Open: the provenance and output location (draft below), the next inventory items, and
  the arbiter's cross-call ranking, all queued above. Verified on macOS arm64 only.

## Provenance design draft — 2026-11-22

Approved by the owner and implemented the same day (record below); kept as the design of record. It answers the P1 item: what a run records
when it performs a law check, and where the records go.

1. **Run outputs.** A run that performs at least one law check writes a `law_checks` array in
   its `run_end` record of `trech_scores.jsonl`: one `LawCheck` JSON each (the current
   `toJson()` shape plus `origin`: `engine` for `Lattice::checkLaws`, `validation` for a
   companion's `TRECH_FORMAL_LAWS` call). A run without checks writes no key, so existing
   outputs keep their bytes. Lattices built several times in a run record each distinct check
   once, with a count.
2. **Provenance.** The same run adds a `formal` object to its provenance record, again only when
   a check ran: the SHA-256 of `formal/laws.json`, the declarations cited by its checks and,
   when an audit report is supplied (`--formal-audit PATH` or `TRECH_FORMAL_AUDIT`), that
   report's `lean_version`, `toolchain`, `mathlib_revision`, module hashes and `passed`. Without
   a report, `lean_status` stays `not_checked_by_this_check`; the run never invokes Lean.
3. **Config.** No config field: law checks are not a scenario choice and must not change the
   config hash. A companion's checks are part of the validation companion, which already sits
   off the decision path.
4. **Companion output.** A validation companion that wants recorded verdicts gets an
   executable hook (for example `onValidate(ctx)` beside its JSON contract) whose returned
   `LawCheck` records land in `law_checks` with `origin: "validation"`. It runs under the
   `validation` trace role and cannot emit physical fields.
5. **Tests.** Round-trip: a scenario without checks keeps its config hash and output bytes; a
   lattice scenario gains only `law_checks` and `formal`; strict replay stays byte-identical.

## Law checks in run outputs — 2026-11-22

- [x] Owner approved the design draft above. `formal::recordRunCheck`/`takeRunChecks` keep a
  thread-safe run record, merged by (origin, law, declaration) so the result does not depend on
  thread order; `TrechRunAction::EndOfRunAction` drains it after `onRunEnd` into `law_checks`
  (run_end scores) and `formal` (run_end provenance, `trech_formal_provenance_v1`). Both are
  written only when a check ran; no config field.
- [x] Identity: CMake embeds the SHA-256 of `formal/laws.json` and one hash over it and every
  Lean module (`sources_sha256`, also computed by `check_lean_laws.py`). `--formal-audit` /
  `TRECH_FORMAL_AUDIT` attach a `--report` file; `lean_status` is `audited` only when it matches
  both hashes, passed and lists every cited declaration on standard axioms
  (`audit_mismatch`, `audit_incomplete`, `audit_unreadable`, `not_checked_by_this_run` otherwise).
- [x] Sources: `Lattice::checkLaws` reports with origin `engine`; `TRECH_FORMAL_LAWS.record`
  (QuickJS and V8, `__TRECH_FORMAL_RECORD`) with origin `validation`, accepting only the
  library's own records. `analytic_compton_transfer.validation.js` records its Compton checks
  (eps grid including 662 keV) under the `validation` role; its family gate adds
  `formal_laws_recorded` and `formal_laws_hold`. The companion still loads on a binary without
  `TRECH_TRACE` (the stale `build/dev` one), where recording is a no-op.
- [x] Verified: `trech_formal_laws` (merging, provenance grading of missing, unreadable,
  stale, partial and matching audits, JS recording and rejection, embedded hash recomputed from
  the tree) and `trech_scenario_contracts` (gate passes, fails on a failing or missing record).
  A 200-event Compton run: `law_checks` has 2 validation records, `lean_status` `audited` with
  the report and `not_checked_by_this_run` without, scores byte-identical either way, and
  identical `law_checks` under V8. CTest: `build/rel` 80/80, `build/v8` 89/89 (`TRECH_JS_ENGINE=v8`).
- [ ] Open: more companions recording checks (queued above). `audited` covers the real-valued
  statements only (the reals-vs-floats item). macOS arm64 only.

