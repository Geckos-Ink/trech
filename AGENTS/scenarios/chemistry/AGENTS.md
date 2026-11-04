# Chemistry and molecular response — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

## Choose a subcategory

| Scope | Context | Work remaining |
| --- | --- | --- |
| Reaction oscillator validation | [AGENTS.md](oscillator/AGENTS.md) | [ROADMAP.md](oscillator/ROADMAP.md) |
| Quantum probability and nuclear diagnostics | [AGENTS.md](probability/AGENTS.md) | [ROADMAP.md](probability/ROADMAP.md) |

Related owners: [Chemistry workspace and field inspection](../../studio/chemistry/AGENTS.md) · [Training tools, model data and feature schemas](../../tooling/training/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

- **Chemistry workbench is an authored graph, not inferred stability.**
  `chemistry_mode.js` + `trech_chemistry.js` validate explicit structures and derive
  isotope/atom/charge conservation for optional `ctx.react` plans. Natural-neutral CHNO
  structures reuse the Geant4-trained particle response; isotope/ion response and general
  stability/polarization remain unavailable. No built-in reaction rates or valence rules.
  `hooks.inputs` records authored state in config/hash/provenance. Studio's Chemistry dock
  edits those inputs and displays engine emits. Contract: [`docs/chemistry_mode.md`](../../../docs/chemistry_mode.md).
- **Stoichiometry/isotopes come from Geant4.** Material components may use positive integer
  `atoms` instead of `fraction` (all-element/all-atoms mode); optional `massNumber` builds a
  pure isotope using Geant4's tabulated mass. Unknown isotopes/stoichiometric elements fail
  closed. Opt-in `materialProbe.includeIsotopes` reports isotope inventories; same-symbol
  number density sums split isotope components. Ambient inference seeds recorded nuclide facts
  under `material.<name>.isotope.Z<z>.A<a>.*`; absent nuclides are unknown, never zero.
  Tests: `test_material_isotopes`, `test_chemistry_authoring`, `scripts/validate_chemistry_mode.py`.

- **[`tools/pubchem/trech_pubchem/`](../../../tools/pubchem)** — property + 2D-structure cache;
  `fetch --conformer` adds comparison-only 3D coordinates/bonds/MMFF94 charges with atom-ID joins,
  response hashes and explicit missing-data rejection (`conformers.py`). Molecular quantum models
  never fit PubChem targets. Ordinary caches remain build-local; the molecular series pins small
  normalized comparison fixtures under `data/molecular_series/`.
  (`python -m trech_pubchem fetch <names>`; `TRECH_PUBCHEM`/`TRECH_PUBCHEM_CACHE_DIR`). XLogP
  is an explicit input to the learned efflux crossing model; chemistry showcase scenarios that
  declare structure-only policy use only CID/SMILES/formula, never density/boiling-point/colour.

### Molecular polarization/torsion — Experimental comparison prototypes

`molecular_series.js` selects six numbered scenarios: ethane, ethanol, formamide, butane,
dimethyl ether and acetamide. `ctx.predict` evaluates the **comparison** periodic models
fitted to PySCF RHF/STO-3G energies/Mulliken charges on an independently constructed fixed
scaffold (72 fitting / 24 withheld angles; butane uses 128 fitting angles). This branch uses elemental identity,
neutral-electron consistency and independent electron transport through a unit-density
homogeneous proxy, **not quantum electronic labels**. Models carry `geant4_trained:false` and
`measured:false`. Bubbles are atom-integrated partial-charge glyphs; positions are imposed
rigid torsion samples with no physical time, not orbitals/density or molecular dynamics.
PubChem is comparison-only (topology, aligned geometry, MMFF94 charge disagreement).
`tools/torch/build_molecular_series.py` rebuilds models/reference rows/JS fixtures;
`docs/molecular_series.md` owns quantitative scope and sources. Measured occupancy flags remain
visible even when hull/joint checks pass. This first atomic rung does **not** close the general
Geant4-linked inference-cascade gap. GenericSurrogate's named C++ API now also rejects missing
inputs, and every backend rejects non-finite inputs/outputs before publishing any output.

The second group also enables a **shared Geant4-trained atomic → molecular response** by default.
`trech_molecular_particle.js` uses `ctx.evolve` for each atom's photon interaction response and
`ctx.cascade` for the nano composition lift. Both models fit Geant4 `G4EmCalculator` labels,
not QM/PubChem; `geant4_trained:true`, `measured:false`, `mc_sampled:false` distinguish those
table labels from physical measurements/MC histories. Shared CHNO response is bounded to
1–30 keV and Geant4's independent-atom mixture approximation; it cannot distinguish isomers'
bond effects. Purple halo volume follows the learned atomic photoelectric response. Separate
torsion/particle-energy streams each emit 24 frames; photon-energy sweeps keep scaffold/QM
charges fixed. Strict mode disables every stage. Counts are `48 × (atom count + 2)` per new
predictive run. `tools/torch/build_particle_molecule_models.py` rebuilds the models/labels;
`scripts/validate_particle_molecule.py` covers mode/reproducibility, held-out responses,
particle-energy sensitivity and three 30,000-photon MC comparisons. Details:
[`docs/particle_molecule.md`](../../../docs/particle_molecule.md). Particle-trained correlated electronic,
charge/bond/torsion inference remains the next lift; the external quantum fits do not fulfill it.

`inferAtoms(ctx,spec,energyEv)` now exposes the same helper's atomic/pooling half while retaining
legacy `infer()` outputs. `particle_observer_cascade` composes the learned nano response and new
MC-trained meso observer in one property pass. It predicts before transport, emits full trust
traces and engine-carried global held-out RMSE, and uses an explicitly labelled static inference
diagram rather than molecular motion. The six named materials are unit-density composition
proxies. Bounded held-out error gates pass, while per-feature/joint sparsity keeps the model
experimental. No bond/isomer/physical-density or experimental-accuracy claim follows.
See the [observer contract](../../../docs/particle_observer.md).
