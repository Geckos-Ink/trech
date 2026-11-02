# Quantum probability and nuclear diagnostics — context and contracts

[Root principles](../../../../AGENTS.md) · [Root roadmap](../../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Related owners: [Chemistry workspace and field inspection](../../../studio/chemistry/AGENTS.md) · [Geant4 transport and diagnostics](../../../engine/simulation/AGENTS.md).

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

- **Multi-molecule probability scenes:** `trech_chemistry_scene_v1` holds named placed/rotated
  structures, explicit links and supplied timed density frames. `TRECH_READ_JSON` parses data
  without evaluating it. Canonical scenes/fields enter `hooks.inputs` and round-trip through
  import/export/restore; electron fields must match their placed owners' geometry/isotopes/charge.
  `quantum_frame` preserves density values, units, source, time kind and shared owner IDs. Strict
  mode omits imported `inferred` fields; independent quantum comparisons remain labelled.
  Occupied-energy density components require a complete electronic spectrum even when its
  frame key is absent/null; inspection rejects orphan components before any inference.
- **Nuclear spatial diagnostics never drive transport.** Opt-in `materialProbe.nuclearSamples`
  samples `G4Fancy3DNucleus` on an isolated RNG engine for explicit isotopes (2≤A≤250), reports
  proton/neutron positions in fm and labels independent ensemble indices, not physical time.
  Natural mixtures and single-proton internal distributions are not invented. Tests verify exact
  replay, nucleon counts, RNG preservation and identical transported tallies with sampling on/off.
  `chemistry_probability_reference.js` adds a joint water/D2 RHF/6-31g **comparison** density;
  this is not Geant4-trained electronic dynamics. See [the probability contract](../../../../docs/chemistry_probability.md).

**Electronic reference service and state views:** `tools/quantum/build_density_scene.py --scene`
calculates optional independent PySCF RHF/6-31g joint density, occupied/LUMO probability grids,
orbital energies/occupations, total energy and dipole for a bounded edited scene. Studio delegates
through `engine/quantum.py`, then ordinary TRECH inspection/run; it imports no quantum solver.
JS checks geometry binding, spectrum/field agreement, occupation sum and live Geant4 Z minus
charge. `quantum_frame` carries `electronic_structure` and `particle_inventory`; strict also
suppresses inferred spectra. States/particles UI selects recorded orbitals and reports counts.
C++ `NuclearSpatialProbe` adds exact inventory, centroid/species RMS distances and finite sampled
radial counts; one-nucleus fm guides remain display choices. Full scene restore uses hashed
`provenance.config_json.hooks.inputs.scene`; summary emits avoid repeating every grid. These are
independent reference/diagnostic improvements, not a Geant4-trained electronic lift. Scope and
remaining open-shell/correlation/dynamics work: [probability contract](../../../../docs/chemistry_probability.md) and [paired roadmap](ROADMAP.md).
