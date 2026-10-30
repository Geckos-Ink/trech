# Chemistry mode — initial molecular workbench

For multiple entities, joint electron-density fields and Geant4 proton/neutron ensemble views,
see [`Multi-molecule scenarios and probability views`](chemistry_probability.md). The single
structure workflow below remains available; Scene JSON and its view selector extend it with
explicitly sourced recorded fields and distinct physical/parameter/ensemble clocks.

Studio's **Chemistry → Open chemistry workspace** opens `chemistry_mode.js`. Edit explicit
atoms, isotope mass numbers, Cartesian positions in Å, net charge and declared bond orders,
then choose **Run chemistry**. The viewport draws the engine-emitted structure as spheres and
bond lines. Options sets the photon energy, transport-proxy density, event count and strict /
predictive mode. To replace the draft with another of the six independent quantum scaffolds,
choose a preset in Options and press **Load scaffold selected in Options**. Editing a preset
name alone does not overwrite a draft. Open saved run output and use **Use loaded run structure
as draft** to recover its structure/reaction inputs. Current Options still set the next run's
probe conditions; restoring a structure does not restore those conditions.

This is the first implementation of the workbench and inference boundary, not general chemical
prediction. No valence rules, equilibrium bond lengths, stability thresholds, reaction rates,
partial charges or isotope-effect formulas have been added. Positions, connectivity, bond orders
and net charge are **authored inputs**. Presets come from the existing RHF/STO-3G rigid-scan
fixtures; their geometries are independent quantum comparison data, not Geant4 results. Bond
orders are optional: omitted order stays unknown, including in the existing connectivity-only
scaffold fixtures. Explicit orders are retained in provenance but currently draw one line per declared bond. Spheres/colors
are display choices. One held frame has zero physical time; no molecular dynamics is invented.

## What the engine supplies

- `materials[].components` accepts integer `atoms` instead of mass `fraction`. All components
  of such a material must be elements using `atoms`; mass weighting comes from Geant4.
  Optional `massNumber` selects a pure isotope. For example:
  `[{"element":"H","atoms":1,"massNumber":1},{"element":"H","atoms":1,"massNumber":2}]`.
  Unresolved stoichiometric elements and isotopes absent from Geant4's NIST mass table fail
  closed. A mass-table entry does not establish nuclear stability or a supported transport process.
- `materialProbe.includeIsotopes:true` adds the constructed isotope inventory: Z, A, A−Z neutrons,
  atom abundance, atomic mass and number density. Symbol number densities sum all same-symbol
  isotope components. These are Geant4 material-table facts, not inferred molecular properties.
- Live `QBBC_LIV` photon photoelectric/Compton/Rayleigh samples accompany the composition probe.
  The declared density and homogeneous transport box are a **composition proxy**, separate from
  the Å-scale structure. Geometry, bonds and net molecular charge do not alter that proxy's
  independent-atom EM transport or electronic shell state.
- Natural, neutral CHNO structures can use the shared Geant4-trained atomic → nano response
  (`ctx.evolve` → `ctx.cascade`, 1–30 keV). This predicts independent-atom photon response and
  reports its domain/holdout traces. Equal-composition isomers remain indistinguishable to it.
  Explicit isotopes, ions and other elements report learned response unavailable; the material
  probe remains available. Strict mode disables all inference. General stability and
  polarization remain explicitly unavailable in every mode.
- `hooks.inputs` preserves the canonical structure and optional reaction plan inside config
  JSON/hash/provenance. Moving an atom or changing a declared bond changes the config hash even
  when the homogeneous transport composition stays the same. It is a generic authored-state
  snapshot, not an engine physics law.

Isotope facts are also available to all generic inference paths as
`material.<name>.isotope.Z<z>.A<a>.{neutrons,atomic_mass_amu,number_density_per_cm3}`.
Only recorded facts exist; missing nuclides/fields are not supplied as zeros. These are inputs for
future trained isotope-conditioned models, not a claim that such models already exist.

## Optional reaction experiment

The Reaction experiment tab accepts JSON describing explicit species structures/counts and
candidate stoichiometric channels. For example, this **declares a candidate association**; it
makes no prediction that the association happens:

```json
{
  "species": [
    {"name":"H", "count":2, "structure":{
      "atoms":[{"element":"H","position":[0,0,0]}], "bonds":[], "charge":0}},
    {"name":"H2", "count":0, "structure":{
      "atoms":[{"element":"H","position":[0,0,0]},
               {"element":"H","position":[1,0,0]}], "bonds":[[0,1,1]], "charge":0}}
  ],
  "channels":[{"name":"associate", "delta":{"H":-2,"H2":1}}]
}
```

Without `modelPath` the inventory stays unchanged and status is `model_unavailable`. A supplied
portable surrogate can output `hazard_associate` (or the generic hazard/weight interface of
`ctx.react`). It receives actual event/material facts and integer species state; no authored
fallback activation/rate is supplied. `dt` is an optional positive model input (default 1);
physical kinetics and clock calibration are **unclaimed**. Model paths resolve using the ordinary
TRECH model loader; absolute paths are useful for external experiments.

The engine-side operator validates conservation, availability and integer updates before applying
one stochastic channel per element. The JS adapter derives conserved coefficient vectors from
all species' element/isotope inventories and net charges; it rejects malformed topology before
running. Natural composition and each explicit isotope are distinct conserved inventories;
chemical channels cannot transmute or silently relabel them. No predefined chemistry/rate
library is used. A supplied model is an attachment, not proof of Geant4 training or chemical
accuracy. Missing inputs block inference, state changes and reaction draws; strict mode leaves
inventories unchanged and consumes no reaction draw.

`chemistry_reaction_step` reports inventories, selection/coverage trace, inference/draw counts,
accepted/rejected transitions and status. Engine results displays the last recorded inventory;
all steps remain in Emits. The 3D viewport shows the separately authored molecular structure.
Species identity or counts do not synthesize product coordinates, bond-breaking paths or
reaction animations. `physical_time_s:null` on reaction steps discloses the absent calibration.

## CLI and verification

```bash
cmake --build --preset rel
build/rel/trech inspect examples/scenarios/chemistry_mode/chemistry_mode.js
build/rel/trech run examples/scenarios/chemistry_mode/chemistry_mode.js --output build/chemistry_run
PYTHONPATH=studio build/studio-venv/bin/python -m trech_studio \
  --scenario examples/scenarios/chemistry_mode/chemistry_mode.js
ctest --test-dir build/rel --output-on-failure
build/studio-venv/bin/python studio/tests/test_chemistry.py
python3 scripts/validate_chemistry_mode.py
```

`structure_json` and `reaction_json` are JSON-encoded **string** parameters, so CLI values require
an additional JSON string encoding. Studio handles it. Runs retain these inputs in config
provenance; saving the JavaScript source alone does not save transient control edits.

The gates exercise config hash/round-trip compatibility, actual Geant4 isotope masses and
stoichiometry, natural/isotope strict/predictive byte-identical reruns, live photon-response gaps,
malformed graph/topology rejection, isotope/charge conservation, missing-input no-mutation/no-RNG,
and a deterministic **test-only** hazard model. No deployed reaction model or chemical-accuracy
claim follows from those software gates. Roadmaps track learned structure-conditioned electronic
response, isotope-conditioned stability, emergent reaction discovery and atomistic dynamics.

Geant4's [material model](https://geant4.web.cern.ch/documentation/dev/bfad_html/ForApplicationDevelopers/Detector/material.html)
provides elements/isotopes/materials. Its existing
[DNA chemistry](https://geant4.web.cern.ch/documentation/dev/bfad_html/ForApplicationDevelopers/TrackingAndPhysics/physicsProcess.html)
uses configured species and dissociation/reaction channels. This workspace is separate from the
existing `chemistry.enable` / DNA-water feature; it does not turn that predefined channel system
into generic learned chemistry.
