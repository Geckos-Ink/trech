// Track ledger: onTrackStart / onTrackEnd bookkeeping of Geant4's own transport.
// A 1.25 MeV gamma beam crosses a water cube in air. The hooks open a ledger
// entry when Geant4 starts a track (ctx.track: id, parent, particle, creator
// process, vertex, kinetic energy) and close it when the track ends, while
// onStep counts each track's steps and length. At run end one emit reports
// the totals and the internal identities that must hold for every track:
//   - every started track ends exactly once, and the started tracks equal the
//     engine's own per-event track count (ctx.event.totalTrackCount);
//   - one primary per event;
//   - ctx.track.stepCount and lengthMm at track end equal the onStep count and
//     summed step length of that track;
//   - no track ends with more kinetic energy than it started with.
// It also tallies creator and ending processes and the track length per
// particle. All of it reads Geant4 values copied into ctx.track/ctx.step; no
// physics is computed here. run.threads is 1 because the ledger accumulates
// across hook callbacks (multi-worker order is not deterministic).
//
// Run:
//   trech run examples/scenarios/hooks_track_ledger/hooks_track_ledger.js \
//        --output build/dev/out_hooks_track_ledger
//
// Honest scope: hook-layer bookkeeping and a consistency gate for the
// track-hook contract, not a physics result.

const eventCount = 300;

globalThis.TRECH_CONFIG = {
  environment: {
    worldSizeMm: 200.0,
    worldMaterial: "G4_AIR",
    mediumBoxMm: 60.0,
    mediumMaterial: "G4_WATER"
  },
  beam: { particle: "gamma", energyMeV: 1.25, direction: [0, 0, 1], originMm: [0, 0, -90] },
  run: { nEvents: eventCount, seed: 20261114, threads: 1 },
  hooks: { maxStepCallbacks: 1000000 }
};

const tally = (map, key, by) => { map[key] = (map[key] || 0) + (by === undefined ? 1 : by); };

globalThis.TRECH_HOOKS = {
  onRunStart(ctx) {
    ctx.state.ledger = {
      events: 0, starts: 0, ends: 0, primaries: 0, tracksFromEvents: 0,
      stepMismatch: 0, lengthMismatch: 0, energyGain: 0, unknownEnd: 0, unclosed: 0,
      creators: {}, endProcesses: {}, particles: {}, lengthMmByParticle: {}
    };
  },
  onEventStart(ctx) {
    ctx.state.open = {};
  },
  onTrackStart(ctx) {
    const ledger = ctx.state.ledger;
    const t = ctx.track;
    ledger.starts += 1;
    if (t.primary) ledger.primaries += 1;
    tally(ledger.creators, t.process || "primary");
    tally(ledger.particles, t.particle || "unknown");
    ctx.state.open[t.id] = { energyMeV: t.kineticEnergyMeV, steps: 0, lengthMm: 0 };
  },
  onStep(ctx) {
    const entry = ctx.state.open[ctx.step.trackId];
    if (entry) {
      entry.steps += 1;
      entry.lengthMm += ctx.step.stepLengthMm;
    }
  },
  onTrackEnd(ctx) {
    const ledger = ctx.state.ledger;
    const t = ctx.track;
    ledger.ends += 1;
    const entry = ctx.state.open[t.id];
    if (!entry) {
      ledger.unknownEnd += 1;
      return;
    }
    if (entry.steps !== t.stepCount) ledger.stepMismatch += 1;
    if (Math.abs(entry.lengthMm - t.lengthMm) > 1e-9 * Math.max(1, t.lengthMm)) {
      ledger.lengthMismatch += 1;
    }
    if (t.kineticEnergyMeV > entry.energyMeV + 1e-12) ledger.energyGain += 1;
    tally(ledger.endProcesses, t.process || "none");
    tally(ledger.lengthMmByParticle, t.particle || "unknown", t.lengthMm);
    delete ctx.state.open[t.id];
  },
  onEventEnd(ctx) {
    const ledger = ctx.state.ledger;
    ledger.events += 1;
    ledger.tracksFromEvents += ctx.event.totalTrackCount;
    ledger.unclosed += Object.keys(ctx.state.open).length;
  },
  onRunEnd(ctx) {
    const ledger = ctx.state.ledger;
    ledger.consistent = ledger.starts === ledger.ends && ledger.starts === ledger.tracksFromEvents &&
      ledger.primaries === ledger.events && ledger.stepMismatch === 0 &&
      ledger.lengthMismatch === 0 && ledger.energyGain === 0 && ledger.unknownEnd === 0 &&
      ledger.unclosed === 0;
    ctx.emit("track_ledger", ledger);
  }
};
