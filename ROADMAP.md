# ROADMAP

This file tracks the short-term execution plan; keep it updated as items are completed or re-scoped.
`docs/trech-roadmap.md` is the initial roadmap concept and is reference-only.

## Sputnik milestone (north star)

- Simulate a single H2O melecule starting from its elementar particle: their behavior and bonds prediction over the time should be stable without "exploding".
- Secondary reference (not first priority): simulate carbon nanotube variants (structure, chirality, diameter) and electron behavior differences, including Fermi gap modeling, per `docs/CNT/BackToTheCarbon.md`.
- Simulate H2O fluid behavior with Geant4 using as much subatomic detail as practical.
- In parallel, learn to separate predictable events from exceptional ones so only outliers are re-simulated.
- Optimize large-scale molecule simulations with congenial multi-scale methods (e.g., Lattice Boltzmann, variance reduction, reduced-order models).
- Use Geant4 with the "right creativity" to maximize the available physics within library boundaries and maintain provenance parity.
- Treat photon transport as a key Geant4 focus: scattering, absorption, refraction, and color response in molecular volumes.

## Short-term next steps

- Expand the H2O config schema (water box, environment, beam direction, optics toggles) and update `examples/experiments/h2o_fluid_spec.md` + `examples/experiments/h2o_fluid.js`.
- Implement water volume geometry and environment handling in the detector setup using the new config fields.
- Add `optics.enable` and wire Geant4 optical physics when enabled (per photon transport milestones).
- Add photon-focused scoring summaries and a validation run for `examples/experiments/h2o_fluid.js`.
- Add a smoke test target or script to run `trech` on `examples/experiments/hello_world.js`.
- Document the JSON schema for provenance and scoring outputs.
- Add a minimal batch macro example and optional `--ui` flag for interactive runs.

## Photon transport milestones (optical physics plan)

- Phase 1: add `optics.enable` config flag and wire Geant4 optical physics when enabled.
- Phase 2: map water optical properties (absorption, scattering, refraction) into materials.
- Phase 3: add photon-focused scoring summaries and validation runs.

## Long-term structure

- core/ (config, provenance, storage)
- js/ (runtime + bindings)
- sim/ (Geant4 integration and scoring)
- chem/ (species registry, reaction network, RD engine, DNA bridge)
- ml/ (TorchScript runtime + feature pipelines)
- data/ (PubChem cache + dataset builders)
- bench/ (benchmarks, manifests, reproducible datasets)
- docs/ (architecture, APIs, user guides)
- thirds/ (submodules and vendored dependencies)

## Completed

- Geant4 submodule initialized and documented.
- Dependency acquisition decision: default FetchContent via presets, with vendoring optional.
- CLI flags for macro execution, output directory, seed override, and event count.
- Provenance logging expanded (physics list, RNG engine, CLI args).
- First scoring output (total energy deposit summary).
- Unit tests for CLI parsing, JS config evaluation, and provenance output.
- Draft initial H2O experiment spec (`examples/experiments/h2o_fluid_spec.md`).
- Initial H2O experiment stub (`examples/experiments/h2o_fluid.js`).
