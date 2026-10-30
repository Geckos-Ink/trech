const cfg = {
  detector: {
    worldSizeMm: 120.0,
    worldMaterial: "G4_WATER"
  },
  beam: {
    particle: "e-",
    energyMeV: 1.0,
    direction: [0, 0, 1]
  },
  run: {
    nEvents: 5,
    seed: 424242
  },
  hooks: {
    maxStepCallbacks: 200
  }
};

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    ctx.emit("init", { seed: ctx.runtime.seed, mode: ctx.runtime.mode });
    return {
      override: {
        run: { nEvents: 4 },
        system: { ensemble: "hook_dispatch_flow" }
      }
    };
  },
  onRunStart(ctx) {
    ctx.emit("run_start", { nEvents: ctx.runtime.nEvents });
  },
  onEventStart(ctx) {
    if (ctx.event) {
      ctx.emit("event_start", { id: ctx.event.id });
    }
  },
  onStep(ctx) {
    if (ctx.step && ctx.step.index === 1) {
      ctx.emit("step_first", { edepMeV: ctx.step.edepMeV });
    }
  },
  onEventEnd(ctx) {
    if (ctx.event) {
      ctx.emit("event_end", { id: ctx.event.id });
    }
  },
  onRunEnd(ctx) {
    ctx.emit("run_end", { mode: ctx.runtime.mode });
  }
};

globalThis.TRECH_CONFIG = cfg;
