# Statistical domains and multi-scale prediction

TRECH analyzes the feature distribution of a population, measures candidate subdivisions, and
can fit separate response models to recurring populations. The live detector is an opt-in
diagnostic. The specialist trainer freezes membership and support at fit time, chooses experts
using whole selection runs, and measures the frozen checkpoint on whole test runs. Runtime
dispatch uses the module's frozen decision rules and the current inputs.

## Live subdivision and lineage

The projected-gap detector checks feature axes, LibTorch principal components and pairwise
diagonals. The density detector uses a symmetric local distance graph when components overlap
in projection. It recovered both rings in a concentric-ring regression. In the lava lamp,
per-axis standardization stretched the geometry and failed to recover the known initial droplets.
The lamp now uses a shared spatial scale for its x, y and z coordinates.

| Lamp run | Frames | Parcel assignments | Frames with a subdivision | Initial four droplets | Group count agreed with separate spatial count |
| --- | ---: | ---: | ---: | --- | ---: |
| Nominal 600 s | 121 | 29,040 | 109 | Recovered | 82 / 121 |
| 310 K heater, 60 s | 13 | 3,120 | 6 | Recovered | 12 / 13 |
| High precision, 60 s | 13 | 6,240 | 8 | Recovered | 11 / 13 |

NumPy reproduced all 38,400 assignments and every lineage record. Each pair of runs produced
byte-identical ordinary hook output. The nominal lamp recorded 375 domain ID continuations,
20 groups with multiple predecessors and 18 predecessor IDs with multiple destinations. These
are topology diagnostics of a reduced thermofluid simulation. The initial droplets are an
authored check. The separate spatial count uses a fixed connection radius, so agreement
measures consistency between two definitions of connectedness.

Enable the graph with `--param detect_domains=true --param 'domain_method="density"'`.
The [hook contract](scenario_hooks.md#context-object-draft) describes its limits, and
[the emit schema](output_schema.md#statistical-domain-discovery-emits) describes lineage.

## Training and deploying specialists

`trech-train-domain-specialists` accepts independent TRECH runs through `--fit`,
`--selection` and `--test`. Supply `--inputs`, `--outputs` and a subset of inputs
in `--routing-features`. Copy `response.pt` with its hash-bound `response.pt.io.json`
when deploying the checkpoint. It accepts named inputs in a `models[]` declaration and can
run through point prediction or a cascade. Support checks use the measured per-expert bounds
and nearest training-region distance. A query with no accepted expert uses the pooled response.
The manifest records decisions, training data hashes, and errors per whole test run and expert.

The atomic experiment used four fit panels, two selection panels, and two final panels. Each
panel sampled Geant4 photon-interaction tables at interleaved energies for H, C, N and O.
The trainer selected one hydrogen network and one shared carbon/nitrogen/oxygen network.
Both improved all three held-out outputs within their own domain on both panels.

| Log cross section | Pooled RMSE | Routed RMSE | Reduction |
| --- | ---: | ---: | ---: |
| Photoelectric | 0.04832 | 0.02118 | 56% |
| Compton | 0.02134 | 0.01089 | 49% |
| Rayleigh | 0.04331 | 0.01397 | 68% |

The comparison covers 384 held-out rows. The study measures interpolation over the four
element identities and uses Geant4's interaction tables as targets. In a separate native query
panel, both LibTorch and Python TorchScript produced identical results. The native run evaluated
24 H and 72 C/N/O expert queries and eight pooled queries beyond the fit range. Strict mode
recorded zero evaluations. The accepted experts differ from the pooled prediction on 96 rows.

For a negative control, the furnace supplied whole 1500, 1600, 1700, 1750, 1880 and 1890 K
fit runs, 1760 and 1860 K selection runs, and 1560 and 1820 K held-out runs. The projected
groups provided insufficient independent specialist support. The pooled affine model served all
5,211 held-out rows at RMSE 3.88 × 10⁻⁷ K/s against the thermal teacher.

Reproduce the table study from the repository root:

```bash
build/render-venv/bin/python tools/torch/study_atomic_domains.py \
  --binary build/dev/trech --out build/atomic_domain_study
```

## Particle-to-observer experiment

The photon study uses two learned chains on a bounded Geant4 reference. The existing
atomic and nano composition model supplies the dense observer. A separate `ctx.lift` branch
starts from trained atomic cross sections, groups atoms by elemental identity, evaluates a
nano set model for each group, and passes those group predictions into a meso set model.
The nano training labels come from fresh Geant4 element tables. Multiplication by areal density
accounts for units and material amount. Both meso models learn uncollided-photon and
deposited-energy fractions from independent Geant4 events. All predictions run before the
scenario starts transporting its photons.

The study exercises unit-density homogeneous CHNO composition proxies, 10–30 keV central
photons, and 0.25–9 mm centre-to-face paths. Fit, selection, calibration and final test use
disjoint composition inventories. Balanced blocks vary energy and path length continuously.
A separate coverage-targeted bank ranks feasible operating points by the frozen model's measured
coverage and adds separation within each material's requested experiments.

The study tools are [coverage sampling](../tools/torch/study_particle_coverage.py),
[dense observer fitting](../tools/torch/study_particle_observer.py),
[hierarchy fitting](../tools/torch/study_particle_hierarchy.py), and
[native replay](../tools/torch/replay_particle_study.py). The scenario takes explicit
`observer_model` and `lift_checkpoint` paths. The existing
[observer contract](particle_observer.md) covers the default checkpoint.
