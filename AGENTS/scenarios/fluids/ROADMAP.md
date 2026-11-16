# Water and fluid comparisons — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

## Choose a subcategory

| Scope | Context | Work remaining |
| --- | --- | --- |
| Foam mechanics and validation | [AGENTS.md](foams/AGENTS.md) | [ROADMAP.md](foams/ROADMAP.md) |
| Lava lamp thermofluid | [AGENTS.md](lava/AGENTS.md) | [ROADMAP.md](lava/ROADMAP.md) |

Related owners: [Project workflow and shared status](../../project/ROADMAP.md) · [Scenario law migration ledger](../migrations/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Water phase program (`h2o_bulk_freeze_boil`)

[`h2o_bulk_freeze_boil.js`](../../../examples/scenarios/h2o_bulk_freeze_boil/h2o_bulk_freeze_boil.js)
drives 600 coarse-grained mW molecules ([`trech_water_mw.js`](../../../js/trech_water_mw.js)) on a fixed
ice Ih floor through 10 → −1 → 100 °C. The water really freezes at −1 °C: an ice front grows from the floor,
and CHILL+ detects every molecule's phase. On heating the ice melts back to a hot liquid. Open gaps:

- [ ] **Nucleation is heterogeneous by construction.** The ice floor is an ideal, fixed, perfectly
  matched template. Homogeneous nucleation at −1 °C would need far more than the reachable
  nanoseconds. A realistic wall (a material surface with a measured ice-binding affinity) is not modelled.
- [ ] **mW is coarse-grained.** One site per molecule, no hydrogens or electrostatics. Its dynamics
  are ~3× faster than real water, so the growth rate (≈ 18 Å/ns over the first 0.5 ns at 2.5 K
  supercooling) is not a real-water front velocity. A particle-derived (Geant4-trained) water operator
  that freezes would close the engine-thesis gap; today the forces are a literature potential
  ("physics for comparison").
- [ ] **The thermostat removes latent heat instantly.** Velocity rescaling on odd ticks, NVT. Growth
  is not limited by heat conduction as it is in a real glass.
- [ ] **Boiling is not measured.** The free surface evaporates into vacuum at fixed thermostat
  temperature, with no pressure control. A boiling point needs liquid–vapour coexistence at 1 atm
  (barostat or slab with a pressure observable). `boiling_point_measured` is always `false`.
- [ ] **No validation-suite family case.** The bundle's declarative checks gate
  `freeze_melt_cycle_reproduced`. It is not exported as a `family_case` in
  `tools/validation/trech_validation/cases.py`, and at ~2 h it is too slow for `scripts/run_validation_suite.sh`.
- [ ] **QuickJS cost.** ~26 ms per step for 792 sites (cell list, O(N)). A shorter program would
  need a C++ operator for the mW force loop, which must stay physics-agnostic.
