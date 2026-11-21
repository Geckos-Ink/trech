// Live hook tuning: a scenario-backed `trech lab` session whose hook-layer observer is
// personalised between batches without restarting Geant4.
//
// A 1.25 MeV gamma beam crosses a 60 mm water cube in air. onEventEnd reads Geant4's own
// per-event energy deposit (ctx.event.edepMeV) and counts the events above a threshold;
// onRunEnd emits one `deposit_tally` per lab batch. Two TRECH_VALUE declarations show the
// two kinds of value a live session meets:
//   - edep_threshold_mev only changes the hook-layer observer. A lab `params` command
//     re-evaluates the scenario with the new value and swaps the hooks in before the next
//     batch, on the same initialized Geant4 kernel.
//   - beam_energy_mev changes the beam, which the initialized kernel is bound to. The lab
//     refuses that re-evaluation (restart required) and keeps the previous script active.
// Editing this file and sending {"action":"reload"} swaps in the edited hooks the same way.
//
// Run (the commands file sends simulate / params / reload / simulate):
//   trech lab examples/lab/live_hook_tuning.js \
//        --commands examples/lab/live_hook_tuning_commands.jsonl --output build/dev/out_live_lab
//
// Honest scope: a hook-layer observer over Geant4 tallies, not a physics result or a
// prediction method. run.threads is 1 so the hook tally replays exactly.

const threshold = TRECH_VALUE.number("edep_threshold_mev", {
  label: "Deposit threshold", group: "Observer", unit: "MeV",
  default: 0.5, min: 0, max: 1.25, step: 0.05
});
const beamEnergy = TRECH_VALUE.number("beam_energy_mev", {
  label: "Beam energy", group: "Beam", unit: "MeV",
  default: 1.25, min: 0.1, max: 10, step: 0.05
});

globalThis.TRECH_CONFIG = {
  environment: {
    worldSizeMm: 200.0,
    worldMaterial: "G4_AIR",
    mediumBoxMm: 60.0,
    mediumMaterial: "G4_WATER"
  },
  beam: { particle: "gamma", energyMeV: beamEnergy, direction: [0, 0, 1], originMm: [0, 0, -90] },
  run: { nEvents: 200, seed: 20261121, threads: 1 },
  lab: { targetHz: 10, minRoundsPerTick: 50, maxRoundsPerTick: 2000 }
};

// Module state survives between batches; a reload or params command starts it afresh.
let batches = 0;

globalThis.TRECH_HOOKS = {
  onRunStart(ctx) {
    batches += 1;
    ctx.state.tally = { events: 0, above: 0, edepSumMeV: 0 };
  },
  onEventEnd(ctx) {
    const tally = ctx.state.tally;
    tally.events += 1;
    tally.edepSumMeV += ctx.event.edepMeV;
    if (ctx.event.edepMeV > threshold) tally.above += 1;
  },
  onRunEnd(ctx) {
    const tally = ctx.state.tally;
    ctx.emit("deposit_tally", {
      batch_in_generation: batches,
      threshold_mev: threshold,
      events: tally.events,
      above_threshold: tally.above,
      fraction_above: tally.events ? tally.above / tally.events : null,
      mean_edep_mev: tally.events ? tally.edepSumMeV / tally.events : null
    });
  }
};
