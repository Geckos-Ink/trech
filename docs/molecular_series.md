# Molecular polarization and torsion — first comparison series

The first group contains three neutral isolated molecules, sharing one authoring module:

| Group | Scenario | Selected dihedral | PubChem | Rigid RHF/STO-3G barrier (kcal/mol) | Held-out energy RMSE (kcal/mol) | PubChem bond-length MAE (Å) |
| --- | --- | --- | --- | ---: | ---: | ---: |
| Nonpolar control | [`molecular_01_ethane.js`](../examples/experiments/molecular_01_ethane.js) | H–C–C–H | [CID 6324](https://pubchem.ncbi.nlm.nih.gov/compound/6324) | 2.9876 | 0.000012 | 0.0105 |
| Polar alcohol | [`molecular_02_ethanol.js`](../examples/experiments/molecular_02_ethanol.js) | C–C–O–H | [CID 702](https://pubchem.ncbi.nlm.nih.gov/compound/702) | 3.3547 | 0.000158 | 0.0120 |
| Restricted amide | [`molecular_03_formamide.js`](../examples/experiments/molecular_03_formamide.js) | O–C–N–H | [CID 713](https://pubchem.ncbi.nlm.nih.gov/compound/713) | 16.6389 | 0.001184 | 0.0087 |

These are **bounded hybrid comparison prototypes**, not a completed Geant4-to-molecule cascade.
Geant4 transports 100 keV electrons through a unit-density homogeneous composition proxy and
provides live elemental identity and a neutral electron-budget consistency check. That proxy is
not a bound atomistic molecule. Its density is a declared transport condition, not a predicted
liquid/gas density. Event deposits are logged independently and do not determine the electronic
surface. **Geant4 does not compute these charges, bonds, geometries or torsional energies.**

An independent quantum reference supplies the electronic targets: RDKit constructs a
hydrogen-explicit graph from the scenario SMILES, embeds it with seed 20261022 and supplies an
MMFF starting scaffold; PySCF RHF/STO-3G then optimizes that geometry with analytic gradients.
One fragment is rotated about a selected acyclic bond with every other internal coordinate fixed.
Each angle receives a separate converged RHF energy and Mulliken population calculation.
The classical scaffold initializer never supplies the published energy/charge labels.

A least-squares periodic model fits the energy and each atom's partial charge on **72 training
angles**. Its six Fourier harmonics are a numerical coordinate basis; no textbook torsional
potential or electronegativity law supplies the response. A separate set of **24 angles**
(2.5°, 17.5°, …, 347.5°) is calculated and withheld from fitting. The portable JSON model runs in
the C++ `GenericSurrogate` through `ctx.predict`. Only the first, atomic rung is present;
the model is molecule/scaffold specific. Excellent interpolation of this cheap reference does
**not** establish experimental accuracy, general molecular prediction, or Geant4 training.
Models explicitly carry `measured:false` and `geant4_trained:false`.

The scan barrier is the maximum minus minimum energy on the training grid. It is an
**unrelaxed electronic scan barrier**, not a relaxed activation barrier, free energy, rate,
thermal torsion amplitude or a claim that the molecule explores all these angles spontaneously.
The amide's larger barrier illustrates restricted rotation within this reference model. It does
not quantify a separate hyperconjugation or donor/acceptor orbital contribution.

## What the 3D view means

CPK spheres and bonds show the scaffold. A gold line marks the selected rotation axis.
Transparent red bubbles denote negative partial charge (electron rich); blue bubbles denote
positive partial charge (electron poor). Bubbles are centered on the atoms and their display
volume is proportional to the absolute **predicted Mulliken charge**. They are atom-integrated
polarization glyphs, **not orbitals, lone-pair lobes, an electrostatic-potential surface or
electron probability density**. Local C–H polarization in the ethane control does not imply a
net molecular dipole. Radii, opacity, labels, the axis and camera orbit are representation.

The shown geometries are imposed scan samples emitted by the scenario, not inferred molecular
dynamics. Every frame declares `physical_time_s:0`, a separate `playback_time_s` and a
`clock_text` identifying the torsion parameter. No physical time is invented. The chart compares
the runtime's predictions with the independent RHF calculation at that same held-out angle.

## PubChem comparison and provenance

[PUG-REST](https://pubchem.ncbi.nlm.nih.gov/docs/pug-rest) supplies a default 3D conformer,
explicit atom IDs, bond orders and, when available, MMFF94 charges. Coordinates are joined by
atom ID; an absent 3D record is rejected rather than replaced with 2D data. Missing MMFF charge
properties remain absent; explicit sparse MMFF properties imply zero for unlisted atoms.
The PubChem parser never silently supplies unknown quantum labels.

PubChem is read **after** constructing the independent geometry, calculating quantum labels and
fitting the model. Its coordinates, charges and conformer energies never enter fitting or
scaffold construction. Graph isomorphisms match atom identities, including equivalent hydrogens;
proper rotations align the independently calculated minimum with the PubChem default conformer.
The comparison records topology agreement, all-atom/heavy-atom RMSD and bond-length MAE.

The all-atom RMSDs are 0.0148 / 0.0434 / 0.0155 Å (ethane / ethanol / formamide).
The corresponding Mulliken–MMFF94 charge MAEs are **0.0874 / 0.1539 / 0.2221 e**.
These substantial charge differences are retained. They compare different charge definitions,
not interchangeable experimental measurements. PubChem's 3D coordinates are theoretical
conformer models too; a matching minimum is not proof of conformational-ensemble accuracy.
See the primary [PubChem3D description](https://pmc.ncbi.nlm.nih.gov/articles/PMC3269824/) and
[PySCF SCF documentation](https://pyscf.org/user/scf.html).

Deployable models, quantum reference rows, normalized PubChem comparison fixtures and emitted
scaffold data live under [`data/molecular_series/`](../data/molecular_series/). Model SHA-256,
software versions, exact angle splits, source URLs, raw-response SHA-256 and PubChem fetch time
are retained. Emits label the fixture's expected model digest `expected_model_sha256`;
the offline gate verifies it against the model bytes. Raw downloads and ordinary run outputs stay in `build/`. Comparisons are pinned
fixtures, refreshed deliberately; normal runs require no PubChem network connection.

## Run, grade and render

```bash
./build/rel/trech run examples/experiments/molecular_02_ethanol.js \
  --output build/rel/out_molecular_ethanol
./build/rel/trech run examples/experiments/molecular_series.js \
  --param 'molecule="formamide"' --param 'mode="strict"' \
  --output build/rel/out_molecular_strict
python3 tests/test_molecular_series.py
python3 scripts/run_molecular_series.py
build/render-venv/bin/python tools/viz/demos/render_readme_3d.py \
  --only molecular_ethane molecular_ethanol molecular_formamide
```

The twelve-run validator runs each molecule twice in both modes. It checks byte-identical
hook/scores/provenance outputs with identical CLI arguments, exact prediction/frame counts,
zero dropped emits and OOD evaluations, charge neutrality, held-out charge/energy error,
measured domain metadata and the absence of inferred charges/energies in strict mode.
Strict mode shows only the imposed scaffold/axis and independently labelled reference data;
its prediction count is zero. The C++ named-prediction boundary rejects missing inputs and
non-finite inputs/outputs before publishing any result.

All 72 runtime predictive samples pass the measured per-feature hull and joint-domain gates.
Some individual Fourier-coordinate occupancy bins are empty: their `starvedInputs` flags are
retained per prediction and counted in `report.json`, not relabelled as full coverage. Held-out
quantum error and joint coverage are separate evidence. The held-out set is angle interpolation
on the same fixed scaffold, not an independent molecule or geometry holdout.

To rebuild the reference and models, use the rendering environment with `pyscf`, `rdkit`,
`numpy` and `scipy` installed (the captured versions are in each model):

```bash
PYTHONPATH=tools/pubchem build/render-venv/bin/python -m trech_pubchem fetch \
  --conformer --cache-dir build/pubchem_cache ethane ethanol formamide
build/render-venv/bin/python tools/torch/build_molecular_series.py
```

Broader geometry/ion/solvent generalization, relaxed scans, quantum electron-density/ESP
surfaces, orbital analysis, independent experimental references and a genuinely learned
Geant4-linked cascade remain open in [`ROADMAP.md`](../ROADMAP.md).
