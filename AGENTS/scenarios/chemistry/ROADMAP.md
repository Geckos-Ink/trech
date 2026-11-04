# Chemistry and molecular response — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

## Choose a subcategory

| Scope | Context | Work remaining |
| --- | --- | --- |
| Reaction oscillator validation | [AGENTS.md](oscillator/AGENTS.md) | [ROADMAP.md](oscillator/ROADMAP.md) |
| Quantum probability and nuclear diagnostics | [AGENTS.md](probability/AGENTS.md) | [ROADMAP.md](probability/ROADMAP.md) |

Related owners: [Chemistry workspace and field inspection](../../studio/chemistry/ROADMAP.md) · [Training tools, model data and feature schemas](../../tooling/training/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

- [x] Shared atomic/nano response now feeds a Geant4-MC-trained meso observer for uncollided
  photon and deposited-energy fractions. Predictions precede independent transport; strict mode
  returns nulls/zero inference. Eighteen untouched whole-material/energy/geometry cases and a fresh
  MC realization pass unchanged numerical gates; the failed first attempt remains auditable.
  [Scope, metrics and commands](../../../docs/particle_observer.md).
- [ ] Fourteen of eighteen fresh queries retain per-feature starvation and five joint starvation.
  Broaden sampling and reserve new independent tests before promotion. This composition-proxy
  transport response does not implement correlated electronic, bonding, isomer or general
  higher-scale chemistry dynamics, nor experimentally measured density/response.

## Chemistry mode — first workbench (2026-10-27)

- [x] C++ materials accept integer atom stoichiometry and explicit isotopes with Geant4-table
  masses; unresolved stoichiometric elements/isotopes fail closed. Opt-in isotope probes expose
  Z/A/neutrons/mass/abundance/number density, aggregate symbol density across isotope components,
  and seed recorded nuclide facts into generic inference without synthetic zeros.
- [x] Generic `hooks.inputs` snapshot conditionally enters config/hash/provenance, so graph,
  coordinates, charges and reaction-plan edits are reproducible. Existing defaults stay absent.
- [x] `chemistry_mode.js` + `trech_chemistry.js`: explicit graph editing, natural-neutral CHNO
  learned particle response, live isotope/photon probes and capability refusal. Optional supplied
  reaction-hazard models use `ctx.react`, with atom/isotope/charge conservation derived from
  explicit species structures. No default reaction rates, valence/stability law or product motion.
- [x] Fixed explicit single-population operator selection registering no groups/stages despite
  reporting successful model selection. Covered through the chemistry reaction test.
- [x] Verification: Release CTest 26/26; all 12 Studio test modules pass (ten Chemistry tests,
  including real engine inspection/run-argument glue). Twelve real Geant4 runs cover natural,
  explicit-isotope and mixed-isotope structures twice in both modes, byte-identical scores /
  provenance / emits / scene, strict zero inference, no dropped emits and a live learned-vs-table
  particle-response gap gate. Actual Metal 3D capture was inspected. These are software/particle
  response gates; they do not validate chemical stability, polarization or reaction rates.
- [x] Studio Chemistry menu/dock edits atoms/A/coordinates/charge/bonds, loads six independent
  quantum scaffolds, runs TRECH and displays emitted native-unit 3D structures and results;
  saved run structures/reaction plans can be restored as drafts. See `docs/chemistry_mode.md`.
- [ ] **Next physical deliverable:** learn geometry/charge/isotope-conditioned electronic and
  bond response driven by Geant4 particle/ionization histories; train across molecules and
  isotope substitutions with separate molecule/geometry/energy holdouts and independent
  quantum/experimental gaps. Current independent-atom photon response cannot infer isomer
  differences, stability, polarization, isotope shifts, nuclear stability or chemical rates.
- [ ] Learn/discover candidate reactions and calibrated hazards with uncertainty/refusal;
  user-authored channels and supplied models are currently explicit experimental attachments.
  Train and validate atomistic paths/product geometries before coupling reaction inventories
  to 3D dynamics. Reaction operator dt currently has no calibrated physical clock.
- [ ] Feed local molecular geometry/electronic state into context-driven model selection and
  propagate validated forces/charge transfer to `ctx.interact`/`ctx.evolve`; no fixed force-field
  fallback in Chemistry mode. Extend beyond neutral natural CHNO, isolated composition proxies
  and the existing bounded particle-energy panel. Benchmark errors/convergence across families.
- [ ] Resource/persistence edges: emits remain bounded/in-memory; very large reaction plans can
  exceed hook payload caps. The source Save action does not persist transient Chemistry/Options
  controls (inputs remain in run provenance); dedicated project files/import/export and direct
  3D picking/dragging are follow-ups. Dependency checkout still needs separate compatibility validation.

## 2026-10-22 — particle-trained atomic/molecular response and second molecular group

- **[landed C++]** `MaterialProbe` can sample caller-declared particle/process/energy grids
  through `G4EmCalculator` after initialization. `materialProbe.interactions` is conditionally
  serialized; old composition-only/config bytes are unchanged. Invalid requests are rejected;
  unknown particles/processes produce explicit unavailable samples without numeric zero facts.
- **[trained]** A shared CHNO atomic photon-response operator and a nano molecular composition
  model learn from actual Geant4 interaction-table labels (`QBBC_LIV`, 1–30 keV). They carry
  `geant4_trained:true`, `measured:false`, `mc_sampled:false`, measured domains, hashes and
  holdouts. Twenty-four energies per element are withheld; all six showcase compositions and
  independent energies are withheld from the molecular fit (144 rows). Maximum relative
  errors: atomic **0.585%**, molecular **0.580%**. The relative-error fitting gate caught a
  high-energy tail error hidden by excellent R²; it was corrected without relaxing tolerances.
- **[new group/media]** Butane, dimethyl ether and acetamide add six classic 3D GIFs: torsion
  and separate photon-energy streams. `ctx.evolve` atom predictions feed a learned `ctx.cascade`
  molecular response; purple halo volume is representation of the inferred photoelectric
  cross section. Photon-energy sweeps keep scaffold/quantum charge fixed. No physical time or
  radiation-induced molecular dynamics is invented. PubChem comparisons remain independent.
  Butane required a richer periodic quantum fit (128 training angles/ten harmonics) to pass the
  unchanged <0.01 kcal/mol gate; held-out RMSE is now 0.00119. Acetamide's 0.371 Å all-atom
  PubChem geometry gap (mostly hydrogen orientations) remains disclosed.
- **[validated]** Release CTest **20/20**; the original twelve mode/rerun cases still pass.
  Fifteen new runs pass strict gating, exact `48 × (atom count + 2)` inference counts,
  byte-identical reruns, positive/held-out responses, zero OOD/dropped emits and particle-energy
  sensitivity. Three 30,000-photon MC comparisons give absolute transmission gaps
  **0.00394 / 0.00351 / 0.00329** (butane / ether / acetamide). Classical attenuation is a
  validation-only comparison; it supplies neither learned labels nor production behaviour.
- **[open — next learned lift]** Learn electronic/charge/bond/torsion response from particle
  track/ionization histories conditioned on local geometry; validate against independent
  quantum/experimental references. Current table-trained independent-atom response cannot
  distinguish isomers or recover electron correlation/chemical bonding; the separate quantum
  fits must not be presented as that particle-derived lift. Extend to excited states,
  charge transfer, coupled conformations and broader elements/energies with active-learning
  coverage and physical uncertainty. Geant4's lack of a bound-molecule representation is a
  reason to train/validate these higher-scale maps, not a stopping boundary. The general
  micro/meso/macro chemistry cascade and density/orbital surfaces remain open.

## 2026-10-22 — first molecular polarization/torsion comparison series

- **[landed prototype]** Three grouped scenarios (ethane / ethanol / formamide) share a
  context-selected authoring module and C++ `ctx.predict` execution. The committed periodic
  models fit independent RHF/STO-3G energy/Mulliken-charge scans (72 fitting + 24 withheld
  angles per molecule); Geant4 supplies live elemental identity/electron-budget consistency
  and actual transport through a declared homogeneous composition proxy. No Geant4 quantum
  electronic surface is claimed (`measured:false`, `geant4_trained:false`). Model source,
  exact splits, reference rows, software versions and hashes are retained.
- **[comparison]** PubChem 3D atom-ID joins, graph-matched geometry and MMFF94 charges are
  acquired independently and excluded from fitting/scaffold construction. Bond MAEs are
  0.0105 / 0.0120 / 0.0087 Å; Mulliken–MMFF94 charge MAEs of 0.0874 / 0.1539 / 0.2221 e
  remain visible and are not experimental accuracy scores. RHF rigid barriers are
  2.99 / 3.35 / 16.64 kcal/mol. Energy interpolation RMSE <0.002 kcal/mol grades this
  reference only. Imposed scan frames disclose zero physical time; red/blue charge glyphs
  and a marked torsion axis replay through the existing 3D viewer and README media pipeline.
- **[C++ guard]** Named `GenericSurrogate::predict` rejects missing required inputs rather
  than synthesizing zero facts. Non-finite inputs or decoded outputs fail before publishing
  any output (identity/exp and optional Torch backends). Explicit supplied zeros remain valid.
- **[validated]** Offline parser/reference tests and twelve fresh Geant4 runs pass strict-mode
  zero-inference, 24 frames/run, 24 predictive inferences/run, neutrality, held-out error,
  zero dropped/OOD inferences, measured hull/joint checks and byte-identical reruns of
  scores/hook/provenance with identical CLI arguments. Per-feature Fourier occupancy gaps
  remain flagged/counted; they are not treated as fully sampled coverage.
  Release CTest passes 19/19, including the new offline molecular gate; the three README GIFs
  are 1280×720 held-frame 3D replays (96 display frames each).
- **[open — molecular truth/generalization]** This is one atomic, molecule-specific fixed-scaffold
  rung. Learn a shared graph/context-driven response across independent molecules, bond lengths,
  angles, ions and environments with genuine Geant4-linked training/validation; do not expand
  the family by quietly fitting narrow per-output maps. Add relaxed torsional scans, solvent /
  temperature ensembles, experimental conformer/rotation references and physical uncertainty.
  RHF/STO-3G interpolation fidelity alone cannot justify predictive physics promotion.
- **[open — electronic view]** Add quantum electron-density/ESP isosurfaces and directional
  orbital/lone-pair/donor–acceptor analysis with proper references, plus chiral/E–Z and coupled
  multi-bond scans. Present atom-centered charge bubbles only as partial-charge glyphs until
  then. Connect radiation-induced changes to an independently validated electronic response;
  current Geant4 event deposits do not drive the surface. Integrate the separate twelve-run
  family gate into the broader validation registry when its multi-run fixture support is added.
