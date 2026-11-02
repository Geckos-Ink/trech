# CNT electronics — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## CNT milestone parallel track (consistency check)

- Define a CNT experiment stub that stays within the JS -> JSON boundary and reuses the shared config structure (detector/beam/optics/stratify).
- Express CNT geometry as a generic `geometry.volumes` entry (tube shell) with `scoreEdep` enabled.
- CNT placement stays scenario-defined: use `placement.parent = "medium"` to sit inside the medium box, `placement.parent = "world"` for world placement, or named container volumes for nested assemblies.
- Run-level scores stay schema-agnostic; CNT observables are tracked via `volume_edep_mev` on the named volume.
- Validate that CNT runs exercise the same physics wiring order and that optics/stratify toggles behave identically across medium/CNT media.
- Mixed testing: add a CNT + optics stub to confirm photon scoring fields coexist with `volume_edep_mev` on the same engine.
- Gate: proceed with CNT implementation only if it improves overall consistency (shared config surface, shared scoring outputs, fewer special cases).
- CNT smoke run: `./build/dev/trech run examples/scenarios/config_cnt_stub/config_cnt_stub.js --events 5 --output build/dev/out_cnt`.
- CNT world smoke run: `./build/dev/trech run examples/scenarios/config_cnt_world_stub/config_cnt_world_stub.js --events 5 --output build/dev/out_cnt_world`.
- CNT optics smoke run: `./build/dev/trech run examples/scenarios/config_cnt_optics_stub/config_cnt_optics_stub.js --events 5 --output build/dev/out_cnt_optics`.
- Expected scoring: `trech_scores.jsonl` includes `total_edep_mev`, `volume_edep_mev`, `optics_enabled`, optical photon counts, `n_events`, `seed`, `physics_list`.
- Expected provenance: `trech_provenance.jsonl` includes `config_json` (with `geometry.volumes` and hook registrations when present), `config_hash`, `geant4_version`, `physics_list`, `seed`, `n_events`.
- **[electronic structure landed 2026-06-12; curvature secondary gaps landed 2026-06-26]** `cnt_band_structure.js` advances the track from geometry/transport stubs to the actual "electron behaviour differences / Fermi gap" physics: a hook-layer tight-binding zone-folding model over a 26-tube (n,m) panel reproduces the metallicity rule ((n-m) mod 3), the semiconducting E_g ∝ 1/d gap law on STM-measured anchors (within ~1%), and the small curvature-induced secondary gap for nominally metallic non-armchair tubes (`E_curv ~= 50 meV nm² * |cos(3θ)| / d²`; 7 quasi-metallic tubes, max gap 0.1007 eV; armchairs zero). Guarded by the `cnt_band_structure` validation case (category `cnt`), plotted as `cnt_band_structure.png`. Next on this track: trigonal-warping family (Kataura) split of the semiconducting gaps.
- **[logic gates + circuit truth tables landed 2026-06-29; topology-viz provenance fixed 2026-06-30]** `cnt_logic_gates.js` advances the track from band structure to working **CNTFET devices and digital logic**: the tube's `E_g` becomes the transistor's Fermi-statistics on/off ratio (`~exp(E_g/2kT)`), the full static-CMOS gate family (NOT/BUFFER/AND/OR/NAND/NOR/XOR/XNOR) is built as resistive-divider pull-up/pull-down FET networks, and three circuits (half adder, full adder, 2-bit ripple-carry adder) propagate real output voltages whose thresholded levels **confirm the canonical truth/arithmetic tables**. The scenario emits `visual_topologies` serialized from the same primitive networks; `render_cnt_circuit.py` consumes that payload so gate visuals differ by emitted topology. The recovered subthreshold swing (60.3 mV/dec) sits on the ~60 mV/dec room-temperature Fermi limit; a metallic tube in the same topology collapses outputs to ~Vdd/2 and breaks the logic (the metallic-short manufacturing problem). Geant4 transports the e- beam through the representative (16,0) channel each event. Guarded by `cnt_logic_gates` (category `cnt`). Next on this track: sequential logic (latch/flip-flop), Schottky-contact barrier (the second `BackToTheCarbon.md` barrier), and chirality-distribution yield modelling.
