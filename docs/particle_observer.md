# Learned particle-to-observer transport

`particle_observer_cascade` extends the existing Geant4-trained CHNO atomic/nano response to
observable photon transmission and deposited-energy fractions. It predicts before the current
run's Monte Carlo events, then runs Geant4 independently for comparison. **Experimental:** the
bounded error gates pass, but sparse-training warnings and broader physical validation remain open.

```bash
./build/rel/trech run \
  examples/scenarios/particle_observer_cascade/particle_observer_cascade.js \
  --output build/rel/out_particle_observer
```

The default is an acetone-composition proxy, 19.3 keV photons and a 1 mm centre-to-face path.
Controls include `material`, `energy_kev`, `half_length_mm`, `events` and `mode`. For example,
`--param 'material="urea"' --param energy_kev=28.7 --param half_length_mm=7`.
`--param 'mode="strict"'` disables every learned stage and emits null predictions and zero inferences.

## Physical scope and execution

The domain is a homogeneous **unit-density composition proxy**, a central gamma source directed
along +z, a cube with half length 0.25–9 mm, 10–30 keV and `QBBC_LIV`. The density is an authored
benchmark condition, not the measured density of the named substance. Composition choices are
butane, dimethyl ether, acetamide, hexane, acetone and urea. No molecular geometry, chemical bonding,
isomer difference, correlated electronic response, or experimental accuracy is established.

| Band | Learned source | Runtime |
| --- | --- | --- |
| atomic | Existing Geant4 elemental interaction-table response | `ctx.evolve` over the actual element inventory |
| nano | Existing Geant4 mixture-table composition response | First stage of one `ctx.cascade` |
| meso | New Geant4 Monte Carlo photon-count and energy-deposition labels | Second stage of that same cascade |

`inferAtoms()` exposes the existing shared helper's atom/pooling half. Pooling groups learned
atomic facts by declared element inventory; the learned nano stage supplies molecular cross
sections. Its outputs feed the meso model automatically in the same cascade. The observer also
consumes photon energy and live Geant4 molecule number density times path length, with barn/mm
unit conversion. These are input/count definitions; no attenuation or deposition formula supplies
either output. Neither current-run energy deposit nor current-run transport tallies enters the
`onRunStart` prediction. Inference count is atom count + two property stages; the default uses 12.

The new generic C++ v2 `sigmoid` inverse link bounds fraction outputs to [0,1]. It rejects
non-finite encoded values atomically; bounded output is not an accuracy guarantee. The generic
trainer exposes explicit `--logit-outputs` without implicit clipping or pseudocounts.

## Data and independent acceptance

[`data/particle_observer/`](../data/particle_observer) contains the portable model, 222 compact
raw-label rows, manifest and failed first-attempt archive. Rows record actual primary counts,
energy-deposition moments, seeds, Geant4/physics identity and raw script/score/provenance hashes.
The committed data represent **2,292,864 simulated photons**: 192 fitting runs × 8,192 photons,
12 development runs × 30,000 and 18 final-test runs × 20,000. Superseded input-coverage audit
runs stay build-local and are excluded from these totals.

The first candidate failed three of twelve independent cases. Its model, labels, frozen hash
and failed gates are retained under `attempt1/`. Those twelve cases were explicitly reassigned
to development for the second campaign. They are never counted as fresh second-campaign tests.

The second campaign fits 192 runs over twelve compositions. A fixed 64×64 SiLU network, float64
arithmetic, deterministic seed and learning schedule select a checkpoint using development cases
only; the selected weights are retained without refitting. Its serialized hash is captured before
collecting the new final outcomes. Hexane/acetone/urea compositions, energies
13.3/19.3/28.7 keV and half lengths 1/7 mm are disjoint from fitting and development conditions.
Holdout metrics are inserted as metadata after the model is frozen.

All **18 final cases** pass the original unchanged gates: absolute transmission error at most
`max(0.03, 5 × binomial standard error)` and deposition error at most
`max(0.04, 5 × event-mean standard error)`. No classical formula is used as a target or acceptance
reference. The reference is independent Geant4 Monte Carlo, not physical measurements.

| Output | Final-test RMSE | Maximum absolute gap | Constant fitting-mean baseline RMSE |
| --- | ---: | ---: | ---: |
| Uncollided photon fraction | 0.004910 | 0.010438 | 0.206794 |
| Deposited incident-energy fraction | 0.002930 | 0.005250 | 0.198566 |

A separate engine validation with another Monte Carlo realization passes the same 18 conditions;
maximum gaps are 0.010843 and 0.009838. Six material/mode software cases also replay scores,
provenance and hook emits byte-for-byte. Strict mode reports zero learned evaluations.

## Trust, outputs and remaining work

The separate engine validation reports zero hull OOD and zero scale mismatch. **Fourteen of
eighteen observer queries still flag per-feature starvation; five also flag joint starvation.**
These warnings remain visible in recorded traces even though the tested numerical errors pass.
Expand the sampled domain and reserve new independent tests before promoting broader use.

`observer_prediction` records the prediction phase, lower/upper traces, exact inference counts,
live exposure inputs, output units and engine-carried `heldout_residual_rmse`. Those residuals
are global held-out model errors, not input-conditional confidence or calibrated intervals.
Training metadata says `geant4_trained:true`, `mc_sampled:true`, `measured:false`; predictions
themselves say `mc_sampled:false`. The optional `material_frame` is an explicitly labelled static
inference diagram: its layout and sphere sizes are display choices, not atomic structure,
photon trajectories or physical time.

This model stays experimental. Independent experimental validation, broader elements/densities,
other geometry/source conditions and calibrated uncertainty remain open. The general higher-scale
chemistry/electronic-dynamics objective is not closed by this finite-volume transport response.

```bash
python3 tests/test_particle_observer.py
python3 scripts/validate_particle_observer.py --binary build/rel/trech --events 20000
# Explicit offline rebuilding requires the existing NumPy/PyTorch environment and fresh MC runs:
build/render-venv/bin/python tools/torch/build_particle_observer_models.py \
  --binary build/rel/trech --campaign 2 --work build/rel/particle_observer_training
```

Future harvest cache reuse requires script, engine-byte, lower-model and feature-source identities to match;
legacy raw caches lacking that identity manifest must be regenerated. The current committed
rows retain audited raw script/score/provenance hashes; historical engine-byte identities are
not retrospectively invented. Rebuilding is an explicit scientific experiment, not an ordinary build.
