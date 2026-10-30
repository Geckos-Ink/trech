# Crystallization and aerodynamics: initial comparison references

These scenarios begin the work requested in [AUTHOR_NOTES.md](AUTHOR_NOTES.md). They are
**independent comparisons**, not Geant4-trained higher-scale predictions. Their tests establish
bookkeeping, numerical invariants and replay; they do not establish experimental accuracy.
Geant4 transports real particles through separate material probes and records its own tallies.
Neither comparison solver uses those tallies to manufacture a claim of learned physics.

```sh
build/rel/trech run examples/scenarios/nacl_dehydration_reference/nacl_dehydration_reference.js --output build/nacl
build/rel/trech run examples/scenarios/aerodynamics_reference/aerodynamics_reference.js --output build/aerodynamics
python3 scripts/validate_process_references.py --trech build/rel/trech
```

Both scenarios declare typed `TRECH_VALUE` controls, run serially, snapshot their assumptions in
`hooks.inputs`, and emit ordinary `material_frame` records. Open them in Studio's Scenarios tree,
run, and scrub the timeline. Options selects the airflow colour field (`temperature`, `pressure`
or `density`) before Run. Processes lists the JS comparison stage, separate Geant4 stage and
unavailable learned lift. No trainer or inference is silently started.

Both fixtures emit phase, native clock, inventory/field-range HUD text and labelled display
legends. Processes follows those values on the held timeline; Preview exports them with the
recorded 3D state. The suite includes `nacl_dehydration` and `aerodynamics`, with gated compact
GIFs. [Native windows, renders and reproduction guide](images/studio-processes/README.md).

## NaCl dehydration

`trech_crystallization_reference.js` removes an authored number of solvent parcels, accounts
for vapour, and grows a connected six-neighbour solid cluster when the assumed dissolved-salt
capacity is exceeded. The supplied attachment probability controls seeded stochastic growth.
Each salt parcel contains one NaCl formula-unit inventory; all Na/Cl and solvent parcels remain
accounted for. Geant4 constructs NaCl from integer Na:Cl stoichiometry and reports equal element
number densities. Its homogeneous solid/water probes are separate from the growth lattice.

The default fixture starts with 64 dissolved salt parcels and 256 solvent parcels. Dehydration
finishes at 75% of the comparison horizon, followed by a growth hold. With its default seed and
controls, all 64 salt parcels become solid. Removing no solvent leaves the default solution
uncrystallized; setting attachment probability to zero blocks growth even when dry.

The lattice spacing, tray positions, radii and colours are display choices. The clock is a
**comparison step index**, not physical seconds. Solubility and attachment are illustrative
assumptions, not fitted NaCl properties. There is no atom-resolved rock-salt lattice, ion
solvation, reversible dissolution, physical nucleation barrier or thermal solver. Crystallization
of salt is a useful phase-change fixture; it does not validate metal tempering. That requires
separate alloy phase/thermal histories, microstructure evolution, stress and measured anchors.

## Compressible airflow

`trech_euler_reference.js` advances 2D conservative ideal-gas Euler state (`rho`, both momentum
components, total energy) using first-order Rusanov fluxes and a CFL-limited timestep. A fixed
stair-step circular mask reflects flow. The left/top/bottom reservoirs retain the inlet state;
the right boundary uses zero-gradient outflow. The grid is 0.4 m long, with approximately 0.6
times as many cells transversely. Its extent/obstacle discretization is recorded.

Every snapshot supplies SI density, velocity, pressure and gas temperature, plus integrals per
unit span, integrated boundary/wall exchange and their conservation residuals. Nonpositive
density/pressure stops the comparison rather than clipping values. Gas temperature follows the
declared ideal-gas closure; it is not a solid surface temperature or viscous heating calculation.
The conservation components are mass, x/y momentum and energy. The solid mask transfers momentum
but no mass or energy; the domain is open, so its inventory alone need not remain constant.

The closure parameters (`gamma=1.4`, `R=287.05 J/(kg K)`) are explicit comparison assumptions.
See NASA's [Euler equations](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/euler-equations-2/)
and [ideal-gas equation of state](https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/equation-of-state/).
Colour maps saturate between 0.5 and 2.5 times the inlet field; original numeric output is
unchanged. Grey cells show the fixed obstacle; velocity arrows use a disclosed display scale.
Geant4's separate air/aluminium probes do not set the gas closure or compute the airflow.

No viscosity, turbulence, boundary layers, moving/rotating geometry, solid thermal coupling,
deformation, fracture, combustion or explosion is modelled. Mach controls are bounded to 0–3.
This is a numerical comparison fixture, not a validated high-speed vehicle predictor.

## Validation and next work

`test_process_references.cpp` exercises both solvers through the actual QuickJS host: inventory,
growth controls, uniform flow preservation, positive state, integrated flux balance, exact
replay and inlet-speed sensitivity. `validate_process_references.py` runs seven Geant4 fixtures,
checks zero inference/dropped emits, and compares repeated scores/emits/viz-scene bytes.

Quantitative phase-change/aerodynamic validation remains open: independent experimental or
trusted solver anchors, uncertainty, resolution/time convergence, held-out compositions,
geometries and histories. Train future scale-tagged models from particle-derived features plus
properly labelled response data, evaluate on independent runs, and grade the gap before exposing
a predictive path. These illustrative comparisons are not synthetic Geant4 truth. The residuals
are registered in `tools/validation/js_law_audit.json` and both roadmaps.
