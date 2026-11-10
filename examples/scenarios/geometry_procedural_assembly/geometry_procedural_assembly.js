// Procedurally generated apparatus: a layered entrance window, a 3x3 grid of
// polystyrene dosimeter cells inside a water phantom, and a ring of NaI tubes
// around it -- authored with TRECH_GEOMETRY generators rather than one volume
// at a time. The audit runs before the config is handed to the engine, so an
// overlapping or escaping generated volume fails at authoring time instead of
// being placed silently by Geant4.
//
// The onStep hook reads the Geant4 step detail (ctx.step.volume / process /
// trackId / parentTrackId) to record, per event, which generated group hosts
// the primary photon's first non-transport interaction. It is a bookkeeping
// tally of Geant4's own transport, not a physics model.
TRECH_INCLUDE("../../../js/trech_geometry.js");
const G = globalThis.TRECH_GEOMETRY;

const worldSizeMm = 400.0;
const phantomSizeMm = 90.0;

const window = G.layerStack({
  name: "window",
  axis: "z",
  sizeMm: [80.0, 80.0],
  startMm: -110.0,
  layers: [
    { name: "window_al", material: "G4_Al", thicknessMm: 2.0 },
    { name: "window_pb", material: "G4_Pb", thicknessMm: 1.0, scoreEdep: true }
  ],
  tags: ["generated"]
});

const phantom = G.volume({
  name: "phantom",
  material: "G4_WATER",
  shape: { type: "box", sizeMm: phantomSizeMm },
  scoreEdep: true,
  tags: ["generated", "phantom"]
});

const cells = G.grid({
  name: "cell",
  parent: "phantom",
  count: [3, 3, 1],
  pitchMm: [20.0, 20.0, 1.0],
  centerMm: [0.0, 0.0, -20.0],
  material: "G4_POLYSTYRENE",
  shape: { type: "box", sizeMm: [15.0, 15.0, 5.0] },
  scoreEdep: true,
  tags: ["dosimeter"]
});

const ring = G.ring({
  name: "nai",
  count: 8,
  radiusMm: 110.0,
  axis: "z",
  orient: true,
  material: "G4_SODIUM_IODIDE",
  shape: { type: "tube", outerRadiusMm: 12.0, lengthMm: 60.0 },
  scoreEdep: true,
  tags: ["generated", "ring"]
});

const volumes = window.concat([phantom], cells, ring);
// Read-only pre-flight check; throws on hard overlaps/escapes/naming errors.
const geometryAudit = G.assertClean(volumes, { worldSizeMm });

const GROUPS = [
  ["window", /^window_/i], ["cell", /^cell_/i], ["phantom", /^phantom$/i],
  ["ring", /^nai_/i], ["world", /^world$/i]
];
function groupOf(volume) {
  for (const [group, pattern] of GROUPS) {
    if (volume && pattern.test(volume)) return group;
  }
  return "other";
}

globalThis.TRECH_HOOKS = {
  onRunStart(ctx) {
    ctx.state.firstInteraction = {};
    ctx.state.noInteraction = 0;
    ctx.state.events = 0;
  },
  onEventStart(ctx) {
    ctx.state.seen = false;
    ctx.state.events += 1;
  },
  onStep(ctx) {
    const s = ctx.step;
    if (ctx.state.seen || s.trackId !== 1 || s.parentTrackId !== 0) return;
    if (s.process === "Transportation" || s.process === "CoupledTransportation") return;
    ctx.state.seen = true;
    const group = groupOf(s.volume);
    ctx.state.firstInteraction[group] = (ctx.state.firstInteraction[group] || 0) + 1;
  },
  onEventEnd(ctx) {
    if (!ctx.state.seen) ctx.state.noInteraction += 1;
  },
  onRunEnd(ctx) {
    ctx.emit("procedural_assembly_summary", {
      runId: ctx.runtime.runId,
      events: ctx.state.events,
      volumes: volumes.length,
      auditOverlaps: geometryAudit.overlaps.length,
      firstInteraction: ctx.state.firstInteraction,
      noInteraction: ctx.state.noInteraction
    });
  }
};

globalThis.TRECH_CONFIG = {
  environment: { worldSizeMm, worldMaterial: "G4_AIR" },
  beam: { particle: "gamma", energyMeV: 1.25, direction: [0, 0, 1], originMm: [0, 0, -150] },
  run: { nEvents: 400, seed: 20261110, threads: 1 },
  hooks: { maxStepCallbacks: 400000 },
  geometry: { volumes }
};
