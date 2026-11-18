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
byte-identical ordinary hook output. The 13 refined-frame diagnostic records also matched
between Debug and Release. The nominal lamp recorded 375 domain ID continuations,
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

At 1820 K, an independent comparison exposed when declared chemistry crossed its material
boundary with a stale class. The scenario now classifies after the thermal call. All eight
reported observer quantities then matched automatic routing. A 1,728-cell run exposed a second
problem. Rounding each ingredient separately limited local silica conversion to 75%. Distributing
whole stoichiometric batches preserves the exact initial inventory, and the high-precision
declared run now passes 11 checks and forms 547 glass cells.

The earlier learned domains covered formed glass at converted silica 0.9 only. Some refined
cells reach 1.0 and cool below the old glass temperature range. The old routed high-precision
run left 300,826 such thermal evaluations uncovered. Harvesting immediately before each operator
call and refitting on the five balanced runs plus three new high-precision runs restored measured
support. Whole-run holdouts at 1710 K and 1810 K reproduced all five reduced teacher operators to
RMSE below 4 × 10⁻¹⁴ in their output units. Two additional paired live runs at 1750 K and 1820 K
matched all eight observer values. Automatic routing agreed on 16,588,788 of 16,588,800 cell
evaluations, with the 12 disagreements at the batch-to-melt boundary. The refined checkpoints
are an opt-in study result through `operator_checkpoints`.

To reproduce the refit, emit training rows in three `precision_profile=high` furnace runs at
1680, 1770 and 1870 K, add the five balanced harvests described above (without 1890 K), and hold
out high-precision runs at 1710 K and 1810 K. Run
[study_glass_refinement.py](../tools/torch/study_glass_refinement.py) with those
`--fit` and `--test` directories and a new `--out` directory. The tool publishes all five
models and their manifests together after adding measured routing domains.

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
`observer_model` and `lift_checkpoint` paths. For a hierarchy fitted with
`--atomic-model`, pass that same module through `lift_atomic_model`. One routed atomic query
per distinct element supplies the nano groups, and the meso set model consumes their predictions.
The native replay checks checkpoint digests, strict mode, group counts and Python parity. The existing
[observer contract](particle_observer.md) covers the default checkpoint.

### Final runs and validation

The balanced Geant4 campaign ran for 7,466 seconds and finished 17 blocks of 48 runs.
Each run transported 240,000 photons. The targeted, selection, calibration and final
test panels added 48, 40, 36 and 48 runs respectively. Together these panels transported
237.12 million photons. The fits used 1,056 conditions, including 192 additional grid
conditions at 24,576 photons per condition. The host used Geant4 11.4 patch 2, LibTorch
2.14.1, PyTorch 2.8.0 and NumPy 2.0.2.

The final test panel withheld the propylene glycol, alanine and heptane composition proxies
and their energy and geometry combinations. In each case the acceptance tolerance was the
larger of five Monte Carlo standard errors and 0.03 for uncollided fraction or 0.04 for
deposition fraction. Every model below passed 48/48 cases.

| Frozen path | Uncollided fraction RMSE | Deposited-energy fraction RMSE |
| --- | ---: | ---: |
| Committed dense observer | 0.005328 | 0.004845 |
| Fresh refit of original dense observer | 0.005143 | 0.004606 |
| TorchScript observer with cross section × areal density features | **0.001447** | **0.001975** |
| Recursive set models with the original atomic stage | 0.008035 | 0.007268 |
| Recursive set models with routed atomic specialists | 0.010277 | 0.008897 |

The selected TorchScript model reduced RMSE by 73% and 59% relative to the committed
observer. The coverage checks still flagged 29/48 per-feature gaps and 10/48 joint gaps,
down from 38/48 and 26/48. Fully supported queries rose from 3/48 to 12/48. The interval
fitted for nominal 90% coverage covered 43/48 uncollided and 40/48 deposition tests. The
hierarchies covered 27/48 uncollided tests and 35/48 (original atomic stage) or 29/48
(routed stage) deposition tests. These residual envelopes measure transfer across fixed
simulation panels. Broader calibration sampling remains open.

Each hierarchy evaluated all 144 nano groups and 48 meso groups. Nano R² across the three
interaction targets ranged from 0.99978 to 0.99991 with the original atomic stage and
0.99963 to 0.99987 with specialists. Native Debug and Release replay made 2,288 model
evaluations across the two paths, including 144 routed atomic evaluations. Strict replays
made zero. The dense model matched Python TorchScript exactly. The exported hierarchy
predictions agreed with NumPy within 8 × 10⁻¹⁶ in fraction units. The routed hierarchy
remains an experimental deployment path. Its higher end-to-end test error matters even
though the atomic specialists improved over their pooled neural baseline on the table task.

The balanced sweep indexed blocks 0–16. The targeted bank used block 0 with the 288-condition
pilot's manifest. Selection used blocks 0–4, calibration blocks 0–2 and testing blocks 0–3.
All used the same case generator and fixed seeds. To reproduce the final fit with the local
artifacts, supply the initial campaign's `split=train` rows plus the 17 `train_*.json` files
and `targeted_0000.json` to `--fit`. Supply the five selection files to `--selection`.
Use 28,000 epochs for the observer and 7,200 for each hierarchy. Run `--calibration`
on its own panel after freezing the model, followed by `--test` on the untouched cases.
Pass `--binary` to the hierarchy test to validate its nano groups with fresh table probes.
Pass the same atomic module to training, calibration, testing and native replay for the
routed variant.

These results cover bounded photon transport and the observed thermofluid and furnace
diagnostics. The study checkpoints remain opt-in. The inference roadmap tracks other observer
families, physical validation, uncovered composition ranges and calibration transfer.

### Regression checks

The full Debug scenario suite recorded 62 passes and three informational cases across 65
cases. The Release scenario rerun recorded 59 passes and three informational results.
The three slow MD/sloshing cases were covered by the full Debug run. The original photon
observer's 18-case panel also passed with the new TorchScript candidate, with fraction RMSE
0.001435 and 0.001971. The checked-out build holds the run-level JSONL, checkpoint manifests
and detailed grades in `build/multiscale_study_1118`.
