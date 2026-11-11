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
- **[electronic structure landed 2026-06-12; curvature secondary gaps landed 2026-06-26]** `cnt_band_structure.js` advances the track from geometry/transport stubs to the actual "electron behaviour differences / Fermi gap" physics: a hook-layer tight-binding zone-folding model over a 26-tube (n,m) panel reproduces the metallicity rule ((n-m) mod 3), the semiconducting E_g ∝ 1/d gap law on STM-measured anchors (within ~1%), and the small curvature-induced secondary gap for nominally metallic non-armchair tubes (`E_curv ~= 50 meV nm² * |cos(3θ)| / d²`; 7 quasi-metallic tubes, max gap 0.1007 eV; armchairs zero). Guarded by the `cnt_band_structure` validation case (category `cnt`), plotted as `cnt_band_structure.png`. **[trigonal-warping family split landed 2026-11-09]** each tube's subband edges are also found numerically by cutting the full nearest-neighbour graphene dispersion along its quantized lines near K (no warping formula inserted): the cut independently reproduces the metallicity rule, stays within 3.2% of the leading-order gap (full-TB anchors within 3%), puts E22/E11 above 2 for every (n-m) mod 3 = 1 panel tube (min 2.045) and below 2 for mod 2 (max 1.913), shrinks the split monotonically with diameter on both zigzag rows, and orders five photoluminescence anchors ((6,5), (7,6) vs (7,5), (8,3), (9,4); approximate Bachilo 2002 assignments) by family like the measurements (margins 0.067 TB / 0.137 measured). Graded by seven new declared `family_checks`. Residual: single-particle model — measured ratios sit near 1.4-1.7, not 2 (excitonic "ratio problem"), so only ordering is graded; no curvature-modified hopping or third-neighbour terms; the 3D panel and committed media are unchanged and were not recaptured.
- **[logic gates + circuit truth tables landed 2026-06-29; topology-viz provenance fixed 2026-06-30]** `cnt_logic_gates.js` advances the track from band structure to working **CNTFET devices and digital logic**: the tube's `E_g` becomes the transistor's Fermi-statistics on/off ratio (`~exp(E_g/2kT)`), the full static-CMOS gate family (NOT/BUFFER/AND/OR/NAND/NOR/XOR/XNOR) is built as resistive-divider pull-up/pull-down FET networks, and three circuits (half adder, full adder, 2-bit ripple-carry adder) propagate real output voltages whose thresholded levels **confirm the canonical truth/arithmetic tables**. The scenario emits `visual_topologies` serialized from the same primitive networks; `render_cnt_circuit.py` consumes that payload so gate visuals differ by emitted topology. The recovered subthreshold swing (60.3 mV/dec) sits on the ~60 mV/dec room-temperature Fermi limit; a metallic tube in the same topology collapses outputs to ~Vdd/2 and breaks the logic (the metallic-short manufacturing problem). Geant4 transports the e- beam through the representative (16,0) channel each event. Guarded by `cnt_logic_gates` (category `cnt`). Next on this track: sequential logic (latch/flip-flop; landed 2026-11-10, below), Schottky-contact barrier (the second `BackToTheCarbon.md` barrier), and chirality-distribution yield modelling.
- **[sequential logic landed 2026-11-10]** `cnt_logic_gates.js` now evaluates memory built from
  the same static-CMOS divider gates: a NOR SR latch over every (stored state, S, R) except the
  forbidden S = R = 1 (bistable: hold-state separation 1.0 Vdd on (16,0)), a master-slave D
  flip-flop driven by an 8-bit pattern with data glitches while the clock is high and after it
  falls (16/16 glitches rejected, Q changes only on rising edges) and a 2-bit synchronous counter
  (D0 = NOT Q0, D1 = Q1 XOR Q0; counts 1, 2, 3, 0, 1, 2, 3, 0, 1). The metallic (5,5) tube has no
  second stable state (separation 0) and its counter sticks at 3; the quasi-metallic (9,0) tube
  still stores and counts but at a 0.36 rail margin. New `sequential_logic_ok` family check
  (folded into `cnt_logic_gates_ok`). Honest scope: DC fixed points with hard-threshold switching
  — no gate delay, RC timing, setup/hold windows or metastability; Geant4 does not compute any of
  it. Next: an RC/delay model for timing (setup/hold, maximum clock), Schottky-contact barriers
  and chirality-distribution yield (yield landed 2026-11-11, below).
- **[chirality-distribution yield landed 2026-11-11]** `cnt_logic_gates.js` grades a grown tube
  population instead of one chosen chirality: all 154 (n,m) within ±4σ of a 1.2 ± 0.15 nm
  diameter-selective distribution (chiral tubes weighted twice for handedness) go through the
  same static-CMOS gate panel. Result: metallic weight fraction 0.3333 (every metallic tube,
  quasi-metallic included, fails the clean-rail panel; every semiconducting tube in range passes).
  Full adders (50 FETs; FET counts come from the serialized topologies and are cross-checked
  against the evaluator's per-row FET reads) are built with an independently drawn tube per slot
  and evaluated by the same netlist, 400 seeded trials per sorted purity: MC yield 0 / 0.583 /
  0.973 at 90 / 99 / 99.9 % semiconducting purity against the all-slots-usable bound 0.005 /
  0.605 / 0.951. No draw with a bad tube ever worked (0 tolerated) and no all-usable draw failed,
  so in this model one metallic FET anywhere kills the adder. Unsorted, the full-adder bound is
  1.6e-9; a 99 % 2-bit ripple adder (100 FETs) needs 99.990 % purity. Eight new checks fold into
  `chirality_yield_ok` → `cnt_logic_gates_ok`, with three new declared family checks (5/5 pass).
  Honest scope: hook-layer comparison physics; the diameter distribution is an assumed growth
  input (not fitted to a measured PLE map), purity sorting keeps relative weights, there is no
  contact/doping variability, and the sequential circuits were not yield-tested (their
  Gauss-Seidel solve re-reads FETs, which the slot device does not support). Next: a measured
  chirality map as the growth input, sequential-circuit yield with per-FET device arrays, RC
  timing and Schottky contacts.
