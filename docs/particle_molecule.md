# Learned particle → atom → molecule response

The molecular series now has a **shared Geant4-trained inference path**. Particle-interaction
data train an atomic operator; its predictions feed a learned molecular composition model.
The result controls purple interaction halos in the 3D view and the molecular response plot.
This is a bounded lift into the molecular context for H/C/N/O photons over **1–30 keV**,
rather than another response model for each named molecule.

Training labels are **Geant4 interaction-table data**, not Monte Carlo trajectories, PubChem
or quantum labels. Separate photon Monte Carlo runs validate the result. Bound-electron
polarization and molecular potentials remain the next inference targets; the current
absorption response does not determine those quantities.

## Data and learned stages

1. C++ `MaterialProbe` samples `G4EmCalculator` after initialization with `QBBC_LIV`.
   The scenario declares particle, processes and energies. Photoelectric (`phot`), Compton
   (`compt`) and Rayleigh (`Rayl`) responses are sampled for H/C/N/O materials. Number-density
   normalization converts the per-length Geant4 response to barns per atom: unit/particle-count
   bookkeeping, not an authored interaction law.
2. One portable v2 atomic model fits log cross sections with a degree-10 Chebyshev basis in
   log photon energy and categorical element inputs. All coefficients come from Geant4 data;
   no atomic-number power law supplies predictions. `exp` links decode positive outputs.
   **24 independent energies per element** are withheld.
3. Thirty-six separate CHNO compositions provide Geant4 mixture labels. They exclude the exact
   compositions of **all six showcased molecules**. A nano-tagged model learns the composition
   response from pooled atomic predictions. The relative-error fitting objective prevents large
   low-energy values from hiding bad high-energy tails. Whole molecules and validation energies
   are withheld together: **144 molecule/energy rows**.
4. At runtime `ctx.evolve` evaluates the shared atomic operator over every atom using live
   Geant4 element identity. `ctx.cascade` evaluates the nano model from those learned atom
   outputs. The shared helper handles the routing. Missing stages refuse a response; strict
   mode returns null at both boundaries.

Maximum held-out relative error is **0.585%** for atoms and **0.580%** for molecules
(molecular mean 0.080%). This grades interpolation of Geant4's **independent-atom mixture
approximation**, not experimental accuracy or chemical-bond sensitivity. Isomers with the
same composition have the same learned particle cross section. The separate quantum branch
distinguishes ground-state charges and torsional surfaces.

Models declare `geant4_trained:true`, `measured:false`, `mc_sampled:false` and atomic/nano
trained bands, with measured domain hulls, occupancy/joint checks and held-out errors.
`measured:false` distinguishes tabulated model response from physical measurements.
[`data/particle_molecule/`](../data/particle_molecule/) pins training labels, exact compositions,
source configuration/score hashes, model SHA-256 and Geant4 version. No quantum or PubChem
values enter these two fits. Rebuilding needs NumPy and the Geant4 binary.

## New molecules and visual meaning

| Molecule | Scenario | Torsion GIF | Particle-response GIF | PubChem |
| --- | --- | --- | --- | --- |
| Butane | [`molecular_04_butane.js`](../examples/experiments/molecular_04_butane.js) | [C–C conformations](../tools/viz/demos/molecular_butane.gif) | [photon scan](../tools/viz/demos/molecular_particle_butane.gif) | [CID 7843](https://pubchem.ncbi.nlm.nih.gov/compound/7843) |
| Dimethyl ether | [`molecular_05_dimethyl_ether.js`](../examples/experiments/molecular_05_dimethyl_ether.js) | [C–O torsion](../tools/viz/demos/molecular_dimethyl_ether.gif) | [photon scan](../tools/viz/demos/molecular_particle_dimethyl_ether.gif) | [CID 8254](https://pubchem.ncbi.nlm.nih.gov/compound/8254) |
| Acetamide | [`molecular_06_acetamide.js`](../examples/experiments/molecular_06_acetamide.js) | [amide torsion](../tools/viz/demos/molecular_acetamide.gif) | [photon scan](../tools/viz/demos/molecular_particle_acetamide.gif) | [CID 178](https://pubchem.ncbi.nlm.nih.gov/compound/178) |

Each new scenario emits two independent 24-frame streams. `torsion` holds queried particle
energy at 3 keV while scanning the bond. `particle_response` holds scaffold and quantum
charges fixed while querying the held-out photon energies. The latter is an inference sweep;
the run's actual transported beam remains 3 keV. Emits retain the queried energy and independent
Geant4 reference. Both streams have zero physical time and represent parameter scans.

Red/blue bubbles encode the RHF/STO-3G partial-charge fit. **Purple halo volume follows the
atomic operator's photoelectric cross section**, with one fixed display scale for all
molecules/energies. Halo dimensions/opacity are representation, not physical orbital size or
electron density. The photon-energy sweep visibly changes the halos while scaffold/charges
stay fixed. Its chart compares three learned molecular cross sections with held-out Geant4 data.

The original three scenarios retain their earlier default and can enable the shared particle
pipeline with `--param particle_response=true`. The new three enable it by default.

## Monte Carlo and reproducibility gates

The family gate runs each new scenario twice in predictive and strict modes, then fires
30,000 actual 29.7 keV Geant4 photons through each composition proxy. Learned molecular
cross sections predict attenuation **for comparison only**; Beer–Lambert does not drive the
simulation or provide training labels.

| Composition | Learned transmission comparison | Geant4 uncollided fraction | Absolute gap |
| --- | ---: | ---: | ---: |
| Butane | 0.75842 | 0.76237 | 0.00394 |
| Dimethyl ether | 0.72869 | 0.73220 | 0.00351 |
| Acetamide | 0.72994 | 0.73323 | 0.00329 |

All fifteen runs pass prediction/frame counts, strict zero inference, zero OOD/dropped emits,
byte-identical hook/score/provenance reruns, positivity and a 3% maximum relative-error gate.
Each predictive run evaluates `48 × (atom count + 2)` models: one quantum comparison,
one atomic operator per atom, and one molecular response per frame. Traces retain coverage,
joint gaps and accuracy; range checks are not treated as physical confidence. A photon-energy
counterfactual checks a >100× response change with fixed scaffold/charges and changing halo
radii. Atomic occupancy gaps remain reported where present.

```bash
build/render-venv/bin/python tools/torch/build_particle_molecule_models.py
python3 tests/test_particle_molecule.py
python3 scripts/validate_particle_molecule.py
build/rel/trech run examples/experiments/molecular_05_dimethyl_ether.js \
  --output build/rel/out_molecular_ether
build/render-venv/bin/python tools/viz/demos/render_readme_3d.py \
  --only molecular_butane molecular_dimethyl_ether molecular_acetamide \
         molecular_particle_butane molecular_particle_dimethyl_ether molecular_particle_acetamide
```

## Next learned lift

Train electronic response from particle track/ionization histories conditioned on local bonding
geometry, then validate learned charge/bond/torsion response against independent quantum and
experimental references. Extend independent atoms to correlated electrons, charge transfer,
excited states and coupled conformations before claiming those predictions. The task is to
learn and validate these maps even where Geant4 has no bound-atom or molecule representation.
Open items are recorded in [`ROADMAP.md`](../ROADMAP.md).

Primary physics sources: [Geant4 Livermore models](https://geant4.web.cern.ch/documentation/dev/prm_html/PhysicsReferenceManual/electromagnetic/introduction/livermore.html),
[Geant4 EM physics lists](https://geant4.web.cern.ch/documentation/dev/plg_html/PhysicsListGuide/electromagnetic/emphyslist.html).
