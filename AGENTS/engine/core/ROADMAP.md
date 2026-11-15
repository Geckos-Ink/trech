# Configuration, CLI and provenance — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Related owners: [Precision profiles and runtime budgets](../precision/ROADMAP.md) · [JavaScript host and live lab](../runtime/ROADMAP.md) · [Tests and validation ownership](../../tooling/validation/ROADMAP.md).

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

For config serialization and reporting changes, follow [precision profiles and runtime budgets](../precision/ROADMAP.md). CLI, inspected metadata and live-session changes belong to the [runtime workstream](../runtime/ROADMAP.md); regression and schema gates belong to [validation](../../tooling/validation/ROADMAP.md). Add new core-only gaps here when they do not belong to one of those workstreams.

- [x] Independent `stratify.resimOnStarvation` / `resimOnScaleMismatch` opt-ins round-trip
  without changing absent/false legacy config bytes or hashes. Routing and remaining gaps are
  tracked in the [trust roadmap](../inference/trust/ROADMAP.md).
- [x] Named parse errors across the scalar config blocks (2026-11-15). `Config.cpp` gains shared
  typed readers (`fieldOr`/`fieldValue`, a `FieldError` type) and a `located()` wrapper that adds
  one path segment per level, replacing the geometry- and beam-local wrappers (their messages are
  unchanged). `environment`/`medium`/`detector`, every `beam(s)` field (incl. `spread`,
  `polarization`, `spectrum[i]`, `active`), `run`, `physics`, `determinism`, `system`, `optics`
  (incl. `spectrum[i]` in both array and object form), `optics.derive`/`opticsDerive` (incl.
  `validate.references[i]`), `viz`, `chemistry` and the volume `name`/`material`/`scoreEdep` now
  name the field (e.g. `opticsDerive.validate.references[1].energyEv must be a number`); every
  other top-level block, `materials[i]` and `models[i]` prefix the library message with their
  location. Behaviour change: a boolean where a number goes is now an error instead of 0/1.
  Compatibility: an inspect sweep of 67 example scenarios parses with no error, and
  `configToJsonString` of every one is byte-identical to the previous parser's (config hashes
  unchanged). Verification: Release and Debug CTest 53/53 (`trech_config_roundtrip`: 19 named
  field errors, 2 block prefixes, a pass-through range error, integer-valued numbers;
  `trech_geometry_resolution`: 4 volume scalar errors replace the old library-message check).
  Residual: `nuclear`, `multiscale`, `analytic`, `materialProbe`, `precision`, `materials`,
  `models`, `hooks`, `stratify` and `lab` fields are not typed yet (block-level location only);
  `hooks`/`lab` integer limits and `determinism.predictive` still silently ignore a wrong type;
  `geometry.volumes[i].tags` silently drops non-string entries; three scenarios
  (`beaker_water_n_pentane`, its Studio variant, `testscenario_h2o_electrolysis_combustion`) were
  not swept because their inspect needs the PubChem cache.
