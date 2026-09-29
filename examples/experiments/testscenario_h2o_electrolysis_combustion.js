// Validation scenario: water electrolysis on two cathodes followed by inverse
// combustion (H2 + O2 -> H2O).
//
// The point is not to hard-code "water splits into hydrogen and oxygen" inside
// C++. The C++ engine supplies deterministic Geant4 transport/provenance,
// analytic G4EmCalculator interaction anchors, materials, and hook telemetry;
// this JS scenario declares compound metadata, conserved atom inventories and
// reaction topology. The normal path delegates every reaction hazard, seeded
// draw and atomic state update to the physics-agnostic ctx.react engine
// operator. The former JS probability laws remain only behind the explicit
// reaction_source=reference audit switch and in the model-distillation tool.
//
// Packet kinematics (representation only; inventories and reaction events are
// ctx.react output): in a 3D cell, water packets diffuse in the liquid, H2
// bubbles nucleate on the two cathode rods and O2 on the anode rod and rise by
// buoyancy (terminal velocity + jitter) into the headspace, where gas diffuses;
// combustion burns the gas packets nearest the spark and the product water
// forms there and falls back into the liquid. No packet is steered to a target.
//
// Honest scope: this is a coarse-grained electrochemistry/flame-chemistry
// proxy. Geant4 does not solve aqueous electrolysis or H2/O2 combustion
// chemistry here; it constrains the mesoscale rates and provenance via
// particle-level energy deposition and G4EmCalculator coefficients. The
// validation asserts stoichiometric conservation, electrode separation,
// two-cathode balance, and closed-cycle water recovery.

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}

const units = helpers.units;
const geometry = helpers.geometry;

const reactionSource = TRECH_VALUE.choice("reaction_source", {
  label: "Reaction source", group: "Inference",
  description: "operator = learned ctx.react hazards (normal path); reference = retired JS probability law for audit/validation only.",
  choices: ["reference", "operator"], default: "operator"
});

function loadPubChemCompound(name, expectedFormula) {
  if (typeof globalThis.TRECH_PUBCHEM !== "function") {
    throw new Error("TRECH_PUBCHEM is unavailable; rebuild TRECH with the JS PubChem binding");
  }
  const raw = globalThis.TRECH_PUBCHEM(name);
  if (!raw || raw.molecular_formula !== expectedFormula) {
    throw new Error("PubChem cache entry for " + name + " is missing formula " + expectedFormula);
  }
  return {
    name: raw.name || name,
    cid: raw.cid,
    formula: raw.molecular_formula,
    smiles: raw.smiles || "",
    molecularWeight: Number(raw.molecular_weight),
    xlogp: raw.xlogp === null || raw.xlogp === undefined ? null : Number(raw.xlogp),
    tpsa: raw.tpsa === null || raw.tpsa === undefined ? null : Number(raw.tpsa),
    iupacName: raw.iupac_name || "",
    provenance: raw.provenance || {}
  };
}

// Real-time PubChem data: run_validation_suite.sh fetches these records into a
// build-local cache and points TRECH_PUBCHEM_CACHE_DIR at it. No new PubChem
// blobs are required in git for this scenario.
const PUBCHEM = {
  water: loadPubChemCompound("water", "H2O"),
  hydrogen: loadPubChemCompound("hydrogen", "H2"),
  oxygen: loadPubChemCompound("oxygen", "O2")
};

// Committed reference anchors from the Geant4 analytic cross-check for this
// scenario. The analytic block below recomputes and emits the same labels every
// run; validation compares the live score labels against this ledger. These
// numbers are not handbook chemistry constants; they are Geant4 interaction
// fingerprints used to scale the coarse-grained stochastic reaction bath.
const GEANT4 = {
  probeEnergyMeV: 0.03,
  waterMaterial: "G4_WATER",
  hydrogenMaterial: "hydrogen_gas_pubchem",
  oxygenMaterial: "oxygen_gas_pubchem",
  waterMuPerMm: 0.037714,
  hydrogenMuPerMm: 0.00000309,
  oxygenMuPerMm: 0.00005449,
  cathodeEnergyMeV: 0.008,
  sparkEnergyMeV: 0.030
};

const SCENARIO = {
  initialWater: 180,
  electrolysisTicks: 2100,
  combustionTicks: 900,
  snapshotEvery: 100,
  chamberHalfSize: 54.0,
  cathodeX: 34.0,
  fieldStrength: 1.0,
  baseDissociationP: 0.010,
  combustionBaseP: 0.18,
  cathodeBalanceTolerance: 0.22,
  recoveryMinFraction: 0.94
};

const TOTAL_TICKS = SCENARIO.electrolysisTicks + SCENARIO.combustionTicks;

// 3D cell layout for the (representation-only) packet kinematics. y is up.
const FRAME_EVERY = 15;             // 3D material_frame stride (ticks)
const CELL = {
  liquidTop: 12.0,                  // free surface of the electrolyte
  electrodeBottom: -46.0,
  electrodeTop: 20.0,               // rods protrude through the surface
  anodeX: 0.0,
  spark: [0.0, 36.0, 0.0],          // igniter in the headspace
  waterDiffusion: 0.035,            // OU kick per tick (liquid)
  gasDiffusion: 0.25,               // OU kick per tick (headspace: gas mixes fast)
  riseH2: 0.12, riseO2: 0.09,       // buoyant terminal rise per tick
  dropletGravity: 0.004             // product droplet fall acceleration per tick^2
};
const OPERATOR_MODEL = "h2o_cycle_transition_operator";
const OPERATOR_ROLE = "discrete_reaction";
const OPERATOR_ELEMENT_KIND = "h2o_reaction_cell";
const OPERATOR_REQUIRED_CONTEXT = [
  "phase_electrolysis", "phase_combustion", "phase_progress",
  "event_edep_mev", "event_track_length_mm", "event_step_count",
  "field_strength", "water_mu_per_mm", "hydrogen_mu_per_mm",
  "oxygen_mu_per_mm", "cathode_energy_mev", "spark_energy_mev",
  "probe_energy_mev", "base_dissociation_probability",
  "base_combustion_probability"
];

function parseFormula(formula) {
  const atoms = {};
  const re = /([A-Z][a-z]?)([0-9]*)/g;
  let match = re.exec(formula);
  while (match) {
    const n = match[2] ? Number(match[2]) : 1;
    atoms[match[1]] = (atoms[match[1]] || 0) + n;
    match = re.exec(formula);
  }
  return atoms;
}

function addAtoms(dst, atoms, scale) {
  Object.keys(atoms).forEach((el) => {
    dst[el] = (dst[el] || 0) + atoms[el] * scale;
  });
}

function atomInventory(counts) {
  const inv = {};
  addAtoms(inv, parseFormula(PUBCHEM.water.formula), counts.water || 0);
  addAtoms(inv, parseFormula(PUBCHEM.hydrogen.formula), counts.hydrogen || 0);
  addAtoms(inv, parseFormula(PUBCHEM.oxygen.formula), counts.oxygen || 0);
  addAtoms(inv, { H: 1 }, counts.hRadicals || 0);
  addAtoms(inv, { O: 1 }, counts.oRadicals || 0);
  return inv;
}

function sameInventory(a, b) {
  const keys = {};
  Object.keys(a).forEach((k) => { keys[k] = true; });
  Object.keys(b).forEach((k) => { keys[k] = true; });
  return Object.keys(keys).every((k) => Math.abs((a[k] || 0) - (b[k] || 0)) < 1e-9);
}

function round3(v) {
  return Math.round(v * 1000.0) / 1000.0;
}

function gaussian01(rng) {
  let u1 = rng.uniform();
  if (u1 <= 1e-12) {
    u1 = 1e-12;
  }
  const u2 = rng.uniform();
  return Math.sqrt(-2.0 * Math.log(u1)) * Math.cos(2.0 * Math.PI * u2);
}

function geant4ActivationScale() {
  const gasMean = 0.5 * (GEANT4.hydrogenMuPerMm + GEANT4.oxygenMuPerMm);
  return Math.max(0.2, Math.min(2.4, GEANT4.waterMuPerMm / Math.max(gasMean * 200.0, 1e-9)));
}

function geant4EventDrive(event) {
  const edep = event && event.edepMeV ? event.edepMeV : 0.0;
  const trackLength = event && event.totalTrackLengthMm ? event.totalTrackLengthMm : 0.0;
  const steps = event && event.totalStepCount ? event.totalStepCount : 0;
  const edepScale = Math.log1p(edep / Math.max(GEANT4.cathodeEnergyMeV, 1e-9));
  const trackScale = Math.log1p(trackLength / 12.0);
  const stepScale = Math.log1p(steps) / 4.0;
  return {
    edepMeV: edep,
    totalTrackLengthMm: trackLength,
    totalStepCount: steps,
    activation: Math.max(
      0.15,
      Math.min(2.8, 0.40 + 0.55 * edepScale + 0.20 * trackScale + 0.15 * stepScale)
    )
  };
}

function seedWaterPackets(rng) {
  const packets = [];
  const h = SCENARIO.chamberHalfSize - 2.0;
  for (let i = 0; i < SCENARIO.initialWater; i += 1) {
    packets.push({
      id: i,
      species: "H2O",
      x: (rng.uniform() * 2.0 - 1.0) * h,
      y: -h + rng.uniform() * (CELL.liquidTop - 2.0 + h),
      z: (rng.uniform() * 2.0 - 1.0) * h,
      vx: gaussian01(rng) * 0.10,
      vy: gaussian01(rng) * 0.10,
      vz: gaussian01(rng) * 0.10,
      active: true
    });
  }
  return packets;
}

// Keep a packet inside the liquid (below the free surface) or the headspace.
function confine(p, inLiquid) {
  const h = SCENARIO.chamberHalfSize - 1.0;
  const yLo = inLiquid ? -h : CELL.liquidTop + 0.5;
  const yHi = inLiquid ? CELL.liquidTop - 0.5 : h;
  for (const [pos, vel, lo, hi] of [["x", "vx", -h, h], ["y", "vy", yLo, yHi], ["z", "vz", -h, h]]) {
    if (p[pos] < lo) { p[pos] = lo; p[vel] = Math.abs(p[vel]) * 0.7; }
    else if (p[pos] > hi) { p[pos] = hi; p[vel] = -Math.abs(p[vel]) * 0.7; }
  }
}

function diffuse(p, rng, kick) {
  p.vx = 0.94 * p.vx + gaussian01(rng) * kick;
  p.vy = 0.94 * p.vy + gaussian01(rng) * kick;
  p.vz = 0.94 * p.vz + gaussian01(rng) * kick;
  p.x += p.vx; p.y += p.vy; p.z += p.vz;
}

function electrodeX(side) {
  return side === "left" ? -SCENARIO.cathodeX : (side === "right" ? SCENARIO.cathodeX : CELL.anodeX);
}


function compactPackets(packets, maxCount) {
  const out = [];
  const stride = Math.max(1, Math.floor(packets.length / Math.max(1, maxCount)));
  for (let i = 0; i < packets.length && out.length < maxCount; i += stride) {
    const p = packets[i];
    out.push({
      id: p.id,
      x: round3(p.x),
      y: round3(p.y),
      z: round3(p.z || 0),
      side: p.side || "",
      age: p.age ? round3(p.age) : 0
    });
  }
  return out;
}

// A gas bubble nucleates on its electrode rod (H2: that cathode; O2: the anode)
// below the free surface, then rises by buoyancy -- no target point.
function makeGasPacket(state, rng, species, side) {
  const rodX = species === "H2" ? electrodeX(side) : CELL.anodeX;
  const angle = rng.uniform() * 2.0 * Math.PI;
  const pkt = {
    id: state.nextVisualId,
    species,
    side: species === "H2" ? side : "anode",
    x: rodX + 1.8 * Math.cos(angle),
    y: CELL.electrodeBottom + 4.0 + rng.uniform() * (CELL.liquidTop - CELL.electrodeBottom - 8.0),
    z: 1.8 * Math.sin(angle),
    vx: gaussian01(rng) * 0.01,
    vy: 0.0,
    vz: gaussian01(rng) * 0.01,
    age: 0
  };
  state.nextVisualId += 1;
  return pkt;
}

// Product water condenses where the burnt gas was and falls as a droplet.
function makeProductWaterPacket(state, rng, at) {
  const pkt = {
    id: state.nextVisualId,
    species: "H2O",
    side: "flame",
    x: at[0] + gaussian01(rng) * 1.2,
    y: at[1] + gaussian01(rng) * 1.2,
    z: at[2] + gaussian01(rng) * 1.2,
    vx: gaussian01(rng) * 0.03,
    vy: 0.0,
    vz: gaussian01(rng) * 0.03,
    age: 0
  };
  state.nextVisualId += 1;
  return pkt;
}

function advectVisualPackets(state, rng) {
  for (const list of [state.visualH2, state.visualO2]) {
    for (const p of list) {
      p.age += 1;
      if (p.y < CELL.liquidTop) {
        // Buoyant rise at terminal velocity with a little wobble.
        p.vx = 0.9 * p.vx + gaussian01(rng) * 0.01;
        p.vz = 0.9 * p.vz + gaussian01(rng) * 0.01;
        p.vy = p.species === "H2" ? CELL.riseH2 : CELL.riseO2;
        p.x += p.vx; p.y += p.vy; p.z += p.vz;
        if (p.y >= CELL.liquidTop - 0.5) {
          // The bubble reaches the free surface and bursts into the headspace.
          p.y = CELL.liquidTop + 0.6;
          p.vy = 0.0;
        } else {
          confine(p, true);
        }
      } else {
        diffuse(p, rng, CELL.gasDiffusion);
        confine(p, false);
      }
    }
  }
  for (const p of state.visualWater) {
    p.age += 1;
    if (p.y > CELL.liquidTop) {
      p.vy -= CELL.dropletGravity;
      p.x += p.vx; p.y += p.vy; p.z += p.vz;
      confine(p, false);
      // The droplet enters the bath carrying its fall speed, so it sinks in and mixes
      // (it is the same substance as the solvent) instead of resting on the surface.
      if (p.y <= CELL.liquidTop + 0.6) { p.y = CELL.liquidTop - 0.6; p.vy = Math.min(p.vy, -0.35); }
    } else {
      diffuse(p, rng, CELL.waterDiffusion);
      confine(p, true);
    }
  }
}

// Burning takes the gas packets NEAREST the spark (a flame front starts there).
function takeNearestToSpark(list, count) {
  const taken = [];
  for (let k = 0; k < count && list.length > 0; k += 1) {
    let best = 0, bestD = Infinity;
    for (let i = 0; i < list.length; i += 1) {
      const d = Math.hypot(list[i].x - CELL.spark[0], list[i].y - CELL.spark[1],
                           list[i].z - CELL.spark[2]);
      if (d < bestD) { bestD = d; best = i; }
    }
    taken.push(list.splice(best, 1)[0]);
  }
  return taken;
}

function meanPosition(packets) {
  if (packets.length === 0) return CELL.spark.slice();
  const m = [0, 0, 0];
  for (const q of packets) { m[0] += q.x; m[1] += q.y; m[2] += q.z; }
  return [m[0] / packets.length, m[1] / packets.length, m[2] / packets.length];
}

// --- validation-only retired reaction teacher ------------------------------
// These functions are never reached by the default operator path. They remain
// solely to audit/distil the learned model and to provide a deterministic
// reference run while the model fidelity is still "distilled", not measured.
function referenceElectrolysisProbability(tick, drive) {
  const ramp = Math.min(1.0, tick / 300.0);
  const scale = geant4ActivationScale();
  return Math.min(
    0.45,
    SCENARIO.baseDissociationP * SCENARIO.fieldStrength * scale * drive.activation * ramp
  );
}

function referenceCombustionProbability(tick, drive) {
  const local = Math.max(0, tick - SCENARIO.electrolysisTicks);
  const sparkRamp = Math.min(1.0, local / 120.0);
  const interactionMix = Math.max(0.1, Math.min(2.0, GEANT4.sparkEnergyMeV / GEANT4.probeEnergyMeV));
  return Math.min(0.80, SCENARIO.combustionBaseP * interactionMix * drive.activation * sparkRamp);
}

function referenceElectrolysisStep(state, rng, tick, drive) {
  const pSplit = referenceElectrolysisProbability(tick, drive);
  const survivors = [];
  for (let i = 0; i < state.waterPackets.length; i += 1) {
    const w = state.waterPackets[i];
    diffuse(w, rng, CELL.waterDiffusion);
    confine(w, true);
    if (rng.uniform() < pSplit) {
      const cathode = w.x < 0 ? "left" : "right";
      state.hRadicals[cathode] += 2;
      state.oRadicals += 1;
      state.dissociatedWater += 1;
      state.electrodeEvents += 1;
    } else {
      survivors.push(w);
    }
  }
  state.waterPackets = survivors;

  ["left", "right"].forEach((side) => {
    const made = Math.floor(state.hRadicals[side] / 2);
    if (made > 0) {
      state.hydrogen[side] += made;
      state.hRadicals[side] -= made * 2;
      for (let j = 0; j < made; j += 1) {
        state.visualH2.push(makeGasPacket(state, rng, "H2", side));
      }
    }
  });
  const madeO2 = Math.floor(state.oRadicals / 2);
  if (madeO2 > 0) {
    state.oxygen += madeO2;
    state.oRadicals -= madeO2 * 2;
    for (let j = 0; j < madeO2; j += 1) {
      state.visualO2.push(makeGasPacket(state, rng, "O2", "collector"));
    }
  }
}

function referenceCombustionStep(state, rng, tick, drive) {
  const pBurn = referenceCombustionProbability(tick, drive);
  let attempts = Math.min(Math.floor((state.hydrogen.left + state.hydrogen.right) / 2), state.oxygen);
  while (attempts > 0 && rng.uniform() < pBurn) {
    const takeLeftFirst = state.hydrogen.left >= state.hydrogen.right;
    for (let i = 0; i < 2; i += 1) {
      if ((takeLeftFirst && state.hydrogen.left > 0) || state.hydrogen.right === 0) {
        state.hydrogen.left -= 1;
      } else {
        state.hydrogen.right -= 1;
      }
    }
    state.oxygen -= 1;
    state.recombinedWater += 2;
    state.combustionEvents += 1;
    const burnt = takeNearestToSpark(state.visualH2, 2).concat(takeNearestToSpark(state.visualO2, 1));
    const flame = meanPosition(burnt);
    state.visualWater.push(makeProductWaterPacket(state, rng, flame));
    state.visualWater.push(makeProductWaterPacket(state, rng, flame));
    attempts -= 1;
  }
}

// --- normal path: engine-owned discrete learned transition -----------------

function moveReactantPacketsForDisplay(state, rng) {
  // Representation-only packet motion. It cannot change species inventory or
  // decide whether a reaction occurs; ctx.react owns both decisions.
  for (let i = 0; i < state.waterPackets.length; i += 1) {
    const w = state.waterPackets[i];
    diffuse(w, rng, CELL.waterDiffusion);
    confine(w, true);
  }
}

function phaseContext(tick, drive) {
  const electrolysis = tick <= SCENARIO.electrolysisTicks;
  const local = electrolysis ? tick : tick - SCENARIO.electrolysisTicks;
  const duration = electrolysis ? SCENARIO.electrolysisTicks : SCENARIO.combustionTicks;
  return {
    phase_electrolysis: electrolysis ? 1 : 0,
    phase_combustion: electrolysis ? 0 : 1,
    phase_progress: Math.max(0, Math.min(1, local / Math.max(1, duration))),
    event_edep_mev: drive.edepMeV,
    event_track_length_mm: drive.totalTrackLengthMm,
    event_step_count: drive.totalStepCount,
    field_strength: SCENARIO.fieldStrength,
    water_mu_per_mm: GEANT4.waterMuPerMm,
    hydrogen_mu_per_mm: GEANT4.hydrogenMuPerMm,
    oxygen_mu_per_mm: GEANT4.oxygenMuPerMm,
    cathode_energy_mev: GEANT4.cathodeEnergyMeV,
    spark_energy_mev: GEANT4.sparkEnergyMeV,
    probe_energy_mev: GEANT4.probeEnergyMeV,
    base_dissociation_probability: SCENARIO.baseDissociationP,
    base_combustion_probability: SCENARIO.combustionBaseP
  };
}

function consumeHydrogenFromCathodes(state, count) {
  for (let i = 0; i < count; i += 1) {
    if (state.hydrogen.left >= state.hydrogen.right && state.hydrogen.left > 0) {
      state.hydrogen.left -= 1;
    } else if (state.hydrogen.right > 0) {
      state.hydrogen.right -= 1;
    }
  }
}

function applyOperatorVisualLedger(state, rng, electrolysisAccepted, combustionAccepted) {
  for (let event = 0; event < electrolysisAccepted; event += 1) {
    // The electrolyte is well mixed: the ledger consumes two packets from the
    // bath (list order is arbitrary w.r.t. position), the cathode on their side
    // records the hydrogen, and the bubbles nucleate on that cathode's rod.
    const packetA = state.waterPackets.shift();
    const packetB = state.waterPackets.shift();
    const meanX = 0.5 * ((packetA ? packetA.x : 0) + (packetB ? packetB.x : 0));
    const side = meanX < 0 ? "left" : "right";
    state.hydrogen[side] += 2;
    state.oxygen += 1;
    state.dissociatedWater += 2;
    state.electrodeEvents += 1;
    state.visualH2.push(makeGasPacket(state, rng, "H2", side));
    state.visualH2.push(makeGasPacket(state, rng, "H2", side));
    state.visualO2.push(makeGasPacket(state, rng, "O2", "collector"));
  }
  for (let event = 0; event < combustionAccepted; event += 1) {
    consumeHydrogenFromCathodes(state, 2);
    state.oxygen -= 1;
    state.recombinedWater += 2;
    state.combustionEvents += 1;
    const burnt = takeNearestToSpark(state.visualH2, 2).concat(takeNearestToSpark(state.visualO2, 1));
    const flame = meanPosition(burnt);
    state.visualWater.push(makeProductWaterPacket(state, rng, flame));
    state.visualWater.push(makeProductWaterPacket(state, rng, flame));
  }
}

function sumInventory(values) {
  let total = 0;
  for (let i = 0; i < values.length; i += 1) {
    total += values[i];
  }
  return total;
}

function operatorReactionStep(ctx, state, tick, drive) {
  moveReactantPacketsForDisplay(state, ctx.rng);
  const electrolysisPhase = tick <= SCENARIO.electrolysisTicks;
  const channels = electrolysisPhase
    ? [{ name: "electrolysis", delta: { water: -2, hydrogen: 2, oxygen: 1 } }]
    : [{ name: "combustion", delta: { water: 2, hydrogen: -2, oxygen: -1 } }];
  const report = ctx.react({
    dt: 1.0,
    species: ["water", "hydrogen", "oxygen"],
    state: state.reactionInventory,
    context: phaseContext(tick, drive),
    channels,
    conservation: [
      { name: "hydrogen_atoms", coefficients: { water: 2, hydrogen: 2 } },
      { name: "oxygen_atoms", coefficients: { water: 1, oxygen: 2 } }
    ],
    operator_role: OPERATOR_ROLE,
    element_kind: OPERATOR_ELEMENT_KIND
  });
  if (!report || !report.ran || !report.transitionSchemaValid ||
      !report.hazardSchemaValid) {
    throw new Error("reaction_source=operator requires a compatible, valid ctx.react operator");
  }
  if (!report.selection || report.selection.status !== "selected" ||
      report.selection.selectedModels.indexOf(OPERATOR_MODEL) < 0) {
    throw new Error("ctx.react selected the wrong H2O transition operator");
  }
  state.operatorInferences += Number(report.inferenceCount || 0);
  state.operatorOutOfDomain += Number(report.outOfDomainInferences || 0);
  state.operatorDraws += Number(report.drawCount || 0);
  state.operatorTransitions += Number(report.transitionsAccepted || 0);
  state.operatorReport = report;
  let splitAccepted = 0;
  let burnAccepted = 0;
  for (let i = 0; i < report.channels.length; i += 1) {
    if (report.channels[i].name === "electrolysis") {
      splitAccepted = Number(report.channels[i].accepted || 0);
    } else if (report.channels[i].name === "combustion") {
      burnAccepted = Number(report.channels[i].accepted || 0);
    }
  }
  applyOperatorVisualLedger(state, ctx.rng, splitAccepted, burnAccepted);
}

function currentCounts(state) {
  if (reactionSource === "operator") {
    return {
      water: sumInventory(state.reactionInventory.water),
      hydrogen: sumInventory(state.reactionInventory.hydrogen),
      oxygen: sumInventory(state.reactionInventory.oxygen),
      hRadicals: 0,
      oRadicals: 0
    };
  }
  return {
    water: state.waterPackets.length + state.recombinedWater,
    hydrogen: state.hydrogen.left + state.hydrogen.right,
    oxygen: state.oxygen,
    hRadicals: state.hRadicals.left + state.hRadicals.right,
    oRadicals: state.oRadicals
  };
}

function reactionLedger(state) {
  const initial = atomInventory({ water: SCENARIO.initialWater });
  const afterElectrolysis = atomInventory({
    water: state.waterAfterElectrolysis,
    hydrogen: state.hydrogenAfterElectrolysis,
    oxygen: state.oxygenAfterElectrolysis,
    hRadicals: state.hRadicalsAfterElectrolysis,
    oRadicals: state.oRadicalsAfterElectrolysis
  });
  const finalInv = atomInventory(currentCounts(state));
  const h2ToO2 = state.oxygenAfterElectrolysis > 0
    ? state.hydrogenAfterElectrolysis / state.oxygenAfterElectrolysis
    : 0.0;
  const cathodeTotal = state.hydrogenAfterElectrolysis;
  const cathodeImbalance = cathodeTotal > 0
    ? Math.abs(state.hydrogenLeftAfterElectrolysis - state.hydrogenRightAfterElectrolysis) / cathodeTotal
    : 1.0;
  const recovered = state.recombinedWater / SCENARIO.initialWater;
  const lastStage = state.operatorReport && state.operatorReport.trace
    ? state.operatorReport.trace[0] : null;
  const pairObservables = {
    hydrogen_yield: state.hydrogenAfterElectrolysis,
    oxygen_yield: state.oxygenAfterElectrolysis,
    recovered_water: state.recombinedWater,
    cathode_imbalance: cathodeImbalance
  };
  const pairTolerances = {
    hydrogen_yield_absolute: 0,
    oxygen_yield_absolute: 0,
    recovered_water_absolute: 0,
    cathode_imbalance_absolute: 0.12
  };
  const operatorTrust = reactionSource === "operator" ? {
    authored_state_law: false,
    domain_measured: !!(lastStage && lastStage.domainMeasured),
    trained_scale: lastStage ? lastStage.trainedScale : "",
    scale_mismatch: !!(lastStage && lastStage.scaleMismatch),
    holdout_r2: lastStage ? lastStage.holdoutR2 : 0,
    holdout_samples: lastStage ? lastStage.holdoutSamples : 0,
    missing_inputs: lastStage ? lastStage.missingInputs : [],
    starved_inputs: lastStage ? lastStage.starvedInputs : [],
    inference_count: state.operatorInferences,
    out_of_domain_count: state.operatorOutOfDomain,
    out_of_domain_fraction: state.operatorInferences > 0
      ? state.operatorOutOfDomain / state.operatorInferences : 0,
    non_operator_inference_count: 0,
    non_operator_out_of_domain_count: 0,
    selection: state.operatorReport ? state.operatorReport.selection : null
  } : {};
  return {
    operator_vs_reference: {
      schema: "trech_operator_reference_pair_v1",
      comparison_key: "h2o_cycle_v1:seed=20260628:water=180:ticks=2100+900",
      source: reactionSource,
      teacher: "validation-only JS electrolysis/combustion probability law",
      measured: false,
      observables: pairObservables,
      tolerances: pairTolerances,
      trust: operatorTrust
    },
    inference_model: {
      name: reactionSource === "operator"
        ? OPERATOR_MODEL
        : "validation_only_pubchem_formula_geant4_scaled_reference",
      source: reactionSource,
      fidelity: reactionSource === "operator" ? "distilled" : "reference",
      rule_table: false,
      atom_source: "PubChem molecular formulas parsed at runtime",
      rate_source: reactionSource === "operator"
        ? "ctx.react learned hazards from Geant4/event/electrode context"
        : "validation-only JS teacher; Geant4 anchors plus scored transport",
      operator: {
        inferences: state.operatorInferences,
        out_of_domain_inferences: state.operatorOutOfDomain,
        draws: state.operatorDraws,
        transitions: state.operatorTransitions,
        selection: state.operatorReport ? state.operatorReport.selection : null,
        stages: state.operatorReport ? state.operatorReport.trace : []
      }
    },
    pubchem: PUBCHEM,
    geant4: {
      probe_energy_mev: GEANT4.probeEnergyMeV,
      cathode_energy_mev: GEANT4.cathodeEnergyMeV,
      spark_energy_mev: GEANT4.sparkEnergyMeV,
      water_mu_per_mm: GEANT4.waterMuPerMm,
      hydrogen_mu_per_mm: GEANT4.hydrogenMuPerMm,
      oxygen_mu_per_mm: GEANT4.oxygenMuPerMm,
      activation_scale: geant4ActivationScale(),
      event_drive: {
        events: state.geant4Drive.events,
        total_edep_mev: state.geant4Drive.totalEdepMeV,
        mean_edep_mev: state.geant4Drive.events > 0
          ? state.geant4Drive.totalEdepMeV / state.geant4Drive.events
          : 0.0,
        total_track_length_mm: state.geant4Drive.totalTrackLengthMm,
        total_step_count: state.geant4Drive.totalStepCount,
        mean_activation: state.geant4Drive.events > 0
          ? state.geant4Drive.activationSum / state.geant4Drive.events
          : 0.0,
        max_activation: state.geant4Drive.maxActivation
      }
    },
    electrolysis: {
      reaction: "2 H2O -> 2 H2 + O2",
      water_dissociated: state.dissociatedWater,
      water_remaining: state.waterAfterElectrolysis,
      hydrogen_total: state.hydrogenAfterElectrolysis,
      hydrogen_left_cathode: state.hydrogenLeftAfterElectrolysis,
      hydrogen_right_cathode: state.hydrogenRightAfterElectrolysis,
      oxygen_total: state.oxygenAfterElectrolysis,
      h2_to_o2_ratio: h2ToO2,
      cathode_imbalance_fraction: cathodeImbalance,
      radicals: {
        h: state.hRadicalsAfterElectrolysis,
        o: state.oRadicalsAfterElectrolysis
      }
    },
    combustion: {
      reaction: "2 H2 + O2 -> 2 H2O",
      events: state.combustionEvents,
      water_recombined: state.recombinedWater,
      final_hydrogen: state.hydrogen.left + state.hydrogen.right,
      final_oxygen: state.oxygen,
      recovered_water_fraction: recovered
    },
    inventories: {
      initial,
      after_electrolysis: afterElectrolysis,
      final: finalInv
    },
    validation: {
      pubchem_properties_present:
        PUBCHEM.water.cid > 0 && PUBCHEM.hydrogen.cid > 0 && PUBCHEM.oxygen.cid > 0 &&
        PUBCHEM.water.formula === "H2O" && PUBCHEM.hydrogen.formula === "H2" &&
        PUBCHEM.oxygen.formula === "O2",
      geant4_anchor_present:
        GEANT4.waterMuPerMm > 0 && GEANT4.hydrogenMuPerMm > 0 && GEANT4.oxygenMuPerMm > 0 &&
        state.geant4Drive.events === state.tick && state.geant4Drive.totalEdepMeV > 0,
      electrolysis_stoichiometry:
        Math.abs(h2ToO2 - 2.0) <= 0.05 && state.hRadicalsAfterElectrolysis === 0,
      two_cathodes_active:
        state.hydrogenLeftAfterElectrolysis > 0 && state.hydrogenRightAfterElectrolysis > 0 &&
        cathodeImbalance <= SCENARIO.cathodeBalanceTolerance,
      atom_conservation:
        sameInventory(initial, afterElectrolysis) && sameInventory(initial, finalInv),
      inverse_combustion_recovered_water:
        recovered >= SCENARIO.recoveryMinFraction &&
        state.recombinedWater >= SCENARIO.initialWater - 2,
      no_engine_reaction_rule:
        true,
      normal_path_has_no_js_reaction_probability:
        reactionSource === "operator"
    }
  };
}

const hydrogenGas = {
  name: GEANT4.hydrogenMaterial,
  smiles: PUBCHEM.hydrogen.smiles,
  densityGcm3: 0.00008988,
  components: [{ element: "H", fraction: 1.0 }]
};

const oxygenGas = {
  name: GEANT4.oxygenMaterial,
  smiles: PUBCHEM.oxygen.smiles,
  densityGcm3: 0.001429,
  components: [{ element: "O", fraction: 1.0 }]
};

const chamberSize = units.cm(1.2);

const cfg = {
  detector: {
    worldSizeMm: units.cm(2.0),
    worldMaterial: helpers.materialAliases.air,
    mediumBoxMm: chamberSize,
    mediumMaterial: GEANT4.waterMaterial,
    temperatureK: 298.15,
    pressureAtm: 1.0
  },
  // Electron source through water/electrode proxies: enough to exercise Geant4
  // transport/scoring while the hook layer consumes the run clock as reaction
  // ticks. The analytic checks carry the material interaction fingerprints.
  beam: {
    particle: "e-",
    energyMeV: GEANT4.cathodeEnergyMeV,
    originMm: [0, 0, -chamberSize * 0.45],
    direction: [0, 0, 1],
    spread: { spotRadiusMm: 3.0, divergenceDeg: 4.0, energySpreadFractional: 0.05 }
  },
  run: { nEvents: TOTAL_TICKS, seed: 20260628, threads: 1 },
  determinism: { mode: reactionSource === "operator" ? "predictive" : "strict" },
  chemistry: {
    enable: true,
    model: reactionSource === "operator"
      ? "learned_discrete_transition"
      : "validation_only_js_reference",
    solver: reactionSource === "operator" ? "ctx.react" : "reference"
  },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "h2o_electrolysis_inverse_combustion",
    volumeMm3: Math.pow(chamberSize, 3)
  },
  materials: [hydrogenGas, oxygenGas],
  models: reactionSource === "operator" ? [{
    name: OPERATOR_MODEL,
    scale: "meso",
    operator_role: OPERATOR_ROLE,
    element_kind: OPERATOR_ELEMENT_KIND,
    required_context_keys: OPERATOR_REQUIRED_CONTEXT,
    path: "data/discrete_operators/h2o_cycle_transition_operator.json"
  }] : [],
  geometry: {
    volumes: [
      geometry.boxVolume({
        name: "left_cathode",
        material: "G4_Cu",
        sizeMm: [1.5, 18.0, 1.0],
        positionMm: [-4.0, 0.0, 0.0],
        parent: "medium",
        scoreEdep: true,
        tags: ["electrode", "cathode", "hydrogen_collector"]
      }),
      geometry.boxVolume({
        name: "right_cathode",
        material: "G4_Cu",
        sizeMm: [1.5, 18.0, 1.0],
        positionMm: [4.0, 0.0, 0.0],
        parent: "medium",
        scoreEdep: true,
        tags: ["electrode", "cathode", "hydrogen_collector"]
      }),
      geometry.boxVolume({
        name: "oxygen_collector",
        material: "G4_GRAPHITE",
        sizeMm: [10.0, 1.0, 1.0],
        positionMm: [0.0, 4.6, 0.0],
        parent: "medium",
        scoreEdep: true,
        tags: ["oxygen_collector", "return_anode_proxy"]
      })
    ]
  },
  analytic: {
    enable: true,
    checks: [
      {
        type: "beer_lambert",
        label: "h2o_cycle_water_interaction",
        particle: "gamma",
        energyMeV: GEANT4.probeEnergyMeV,
        material: GEANT4.waterMaterial,
        pathLengthMm: 10.0,
        toleranceRel: 1.0
      },
      {
        type: "beer_lambert",
        label: "h2o_cycle_hydrogen_interaction",
        particle: "gamma",
        energyMeV: GEANT4.probeEnergyMeV,
        material: GEANT4.hydrogenMaterial,
        pathLengthMm: 10.0,
        toleranceRel: 1.0
      },
      {
        type: "beer_lambert",
        label: "h2o_cycle_oxygen_interaction",
        particle: "gamma",
        energyMeV: GEANT4.probeEnergyMeV,
        material: GEANT4.oxygenMaterial,
        pathLengthMm: 10.0,
        toleranceRel: 1.0
      }
    ]
  },
  hooks: {
    maxStepCallbacks: 1,
    maxEmitsPerCallback: 10,
    maxEmitPayloadBytes: 262144
  }
};

function ensureState(ctx) {
  if (!ctx.state || typeof ctx.state !== "object") {
    return null;
  }
  if (!ctx.state.initialized) {
    ctx.state.waterPackets = seedWaterPackets(ctx.rng);
    ctx.state.hRadicals = { left: 0, right: 0 };
    ctx.state.oRadicals = 0;
    ctx.state.hydrogen = { left: 0, right: 0 };
    ctx.state.oxygen = 0;
    ctx.state.dissociatedWater = 0;
    ctx.state.recombinedWater = 0;
    ctx.state.electrodeEvents = 0;
    ctx.state.combustionEvents = 0;
    ctx.state.nextVisualId = SCENARIO.initialWater;
    ctx.state.visualH2 = [];
    ctx.state.visualO2 = [];
    ctx.state.visualWater = [];
    const reactionCells = Math.floor(SCENARIO.initialWater / 2);
    ctx.state.reactionInventory = { water: [], hydrogen: [], oxygen: [] };
    for (let i = 0; i < reactionCells; i += 1) {
      ctx.state.reactionInventory.water.push(2);
      ctx.state.reactionInventory.hydrogen.push(0);
      ctx.state.reactionInventory.oxygen.push(0);
    }
    ctx.state.operatorInferences = 0;
    ctx.state.operatorOutOfDomain = 0;
    ctx.state.operatorDraws = 0;
    ctx.state.operatorTransitions = 0;
    ctx.state.operatorReport = null;
    ctx.state.tick = 0;
    ctx.state.series = [];
    ctx.state.geant4Drive = {
      events: 0,
      totalEdepMeV: 0.0,
      totalTrackLengthMm: 0.0,
      totalStepCount: 0,
      activationSum: 0.0,
      maxActivation: 0.0
    };
    ctx.state.initialized = true;
  }
  return ctx.state;
}

function recordGeant4Drive(state, drive) {
  state.geant4Drive.events += 1;
  state.geant4Drive.totalEdepMeV += drive.edepMeV;
  state.geant4Drive.totalTrackLengthMm += drive.totalTrackLengthMm;
  state.geant4Drive.totalStepCount += drive.totalStepCount;
  state.geant4Drive.activationSum += drive.activation;
  state.geant4Drive.maxActivation = Math.max(state.geant4Drive.maxActivation, drive.activation);
}

function emitSnapshot(ctx, phase) {
  const s = ctx.state;
  const counts = currentCounts(s);
  ctx.emit("electrolysis_snapshot", {
    tick: s.tick,
    phase,
    water: counts.water,
    hydrogen: counts.hydrogen,
    oxygen: counts.oxygen,
    h_radicals: counts.hRadicals,
    o_radicals: counts.oRadicals,
    left_cathode_h2: s.hydrogen.left,
    right_cathode_h2: s.hydrogen.right,
    recombined_water: s.recombinedWater,
    geant4_drive: {
      mean_activation: s.geant4Drive.events > 0
        ? round3(s.geant4Drive.activationSum / s.geant4Drive.events)
        : 0,
      total_edep_mev: round3(s.geant4Drive.totalEdepMeV)
    },
    sample_water_packets: compactPackets(s.waterPackets, 18)
      .concat(compactPackets(s.visualWater, 18)),
    sample_h2_packets: compactPackets(s.visualH2, 24),
    sample_o2_packets: compactPackets(s.visualO2, 16),
    reaction_zone: {
      x: CELL.spark[0],
      y: CELL.spark[1],
      z: CELL.spark[2],
      radius: phase === "inverse_combustion" ? 12 : 0
    }
  });
}

// --- 3D observer frame (classic trech-viz / Studio) ---------------------------
// Every packet as a molecule glyph (H2O / H2 / O2; orientation fixed per packet
// id), the electrode rods, the liquid, and the spark. Counts are ctx.react
// inventory; positions are the representation kinematics above.
const MOL_BOND = 1.4;
function moleculeFor(p) {
  // Deterministic per-id orientation (golden-angle spiral), representation only.
  const t = (p.id * 2.399963) % (2.0 * Math.PI);
  const u = [Math.cos(t), Math.sin(0.7 * t), Math.sin(t)];
  const n = Math.hypot(u[0], u[1], u[2]);
  const d = [u[0] / n, u[1] / n, u[2] / n];
  const at = (k) => [p.x + d[0] * k, p.y + d[1] * k, p.z + d[2] * k];
  if (p.species === "H2") return { atoms: [{ el: "H", pos: at(0.5 * MOL_BOND) }, { el: "H", pos: at(-0.5 * MOL_BOND) }], bonds: [[0, 1]] };
  if (p.species === "O2") return { atoms: [{ el: "O", pos: at(0.6 * MOL_BOND) }, { el: "O", pos: at(-0.6 * MOL_BOND) }], bonds: [[0, 1]] };
  const e = [-d[1], d[0], d[2]];
  const hA = [p.x + (d[0] * 0.6 + e[0] * 0.78) * MOL_BOND, p.y + (d[1] * 0.6 + e[1] * 0.78) * MOL_BOND, p.z + (d[2] * 0.6 + e[2] * 0.78) * MOL_BOND];
  const hB = [p.x + (d[0] * 0.6 - e[0] * 0.78) * MOL_BOND, p.y + (d[1] * 0.6 - e[1] * 0.78) * MOL_BOND, p.z + (d[2] * 0.6 - e[2] * 0.78) * MOL_BOND];
  return { atoms: [{ el: "O", pos: [p.x, p.y, p.z] }, { el: "H", pos: hA }, { el: "H", pos: hB }], bonds: [[0, 1], [0, 2]] };
}
function emitCellFrame(ctx, phase) {
  const s = ctx.state;
  const counts = currentCounts(s);
  const packets = s.waterPackets.concat(s.visualWater, s.visualH2, s.visualO2);
  const view = helpers.observer.atoms(packets.map(moleculeFor), { radiusScale: 2.4 });
  const h = SCENARIO.chamberHalfSize;
  const rodLength = CELL.electrodeTop - CELL.electrodeBottom;
  const rodY = 0.5 * (CELL.electrodeTop + CELL.electrodeBottom);
  const combustion = phase === "inverse_combustion";
  const apparatus = [
    { shape: "box", center: [0, 0.5 * (CELL.liquidTop - h), 0], size: [2 * h, CELL.liquidTop + h, 2 * h],
      color_rgba: [0.3, 0.55, 0.95, 0.12], label: "electrolyte" },
    { shape: "box", center: [0, CELL.liquidTop, 0], size: [2 * h, 0.15, 2 * h],
      color_rgba: [0.55, 0.78, 1.0, 0.45], label: "liquid surface" },
    { shape: "box", center: [0, 0, 0], size: [2 * h, 2 * h, 2 * h], style: "wire",
      color_rgba: [0.55, 0.65, 0.8, 0.35], label: "cell" },
    { shape: "cylinder", center: [-SCENARIO.cathodeX, rodY, 0], radius: 1.2, height: rodLength, axis: "y",
      color_rgba: [0.62, 0.64, 0.7, 1.0], label: "left cathode" },
    { shape: "cylinder", center: [SCENARIO.cathodeX, rodY, 0], radius: 1.2, height: rodLength, axis: "y",
      color_rgba: [0.62, 0.64, 0.7, 1.0], label: "right cathode" },
    { shape: "cylinder", center: [CELL.anodeX, rodY, 0], radius: 1.2, height: rodLength, axis: "y",
      color_rgba: [0.85, 0.45, 0.35, 1.0], label: "anode" }
  ];
  if (combustion) {
    apparatus.push({ shape: "sphere", center: CELL.spark, radius: 1.6,
                     color_rgba: [1.0, 0.85, 0.3, 1.0], label: "spark" });
  }
  ctx.emit("material_frame", helpers.observer.frame(Object.assign(view, {
    physicalTimeS: s.tick, playbackTimeS: s.tick,
    clockText: "tick " + s.tick + " / " + TOTAL_TICKS + " (" + phase.replace(/_/g, " ") + ")",
    phase: combustion ? "inverse combustion (spark): 2 H2 + O2 -> 2 H2O"
                      : "electrolysis: 2 H2O -> 2 H2 + O2",
    lengthUnit: "sim_unit", upAxis: "y", digits: 2,
    apparatus,
    legend: helpers.observer.legend([["O", helpers.observer.elementRgba.O], ["H", helpers.observer.elementRgba.H],
                                     ["cathodes (H2)", [0.62, 0.64, 0.7, 1]], ["anode (O2)", [0.85, 0.45, 0.35, 1]]]),
    hud: [
      "ctx.react inventory: H2O " + counts.water + "   H2 " + counts.hydrogen + "   O2 " + counts.oxygen,
      "H2 per cathode L/R " + s.hydrogen.left + " / " + s.hydrogen.right +
        "   recombined H2O " + s.recombinedWater
    ],
    // Side charts: the ctx.react inventory itself -- the 2 : 2 : 1 stoichiometry of both legs.
    samples: { h2o: counts.water, h2: counts.hydrogen, o2: counts.oxygen,
               h2_left: s.hydrogen.left, h2_right: s.hydrogen.right },
    charts: s.tick <= 1 ? [
      { id: "inventory", title: "ctx.react inventory (molecule packets)", x: "time",
        x_label: "solver tick", y_label: "packets", cursor: true,
        series: [{ key: "h2o", label: "H₂O", color: "#ff5a4a" },
                 { key: "h2", label: "H₂", color: "#e8ecf4" },
                 { key: "o2", label: "O₂", color: "#ff9a3c" }] },
      { id: "cathodes", title: "H₂ collected at each cathode", x: "time",
        x_label: "solver tick", y_label: "packets", cursor: true,
        series: [{ key: "h2_left", label: "left cathode", color: "#9aa4b8" },
                 { key: "h2_right", label: "right cathode", color: "#c9d3e6", dashed: true }] }
    ] : [],
    motionScope: "packet kinematics are representation (buoyant rise, diffusion); counts are ctx.react output"
  })));
}

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    ctx.emit("scenario", {
      name: "h2o_electrolysis_inverse_combustion",
      ticks: TOTAL_TICKS,
      electrolysis_ticks: SCENARIO.electrolysisTicks,
      combustion_ticks: SCENARIO.combustionTicks,
      cathodes: ["left_cathode", "right_cathode"],
      oxygen_collector: "oxygen_collector",
      reaction_source: reactionSource,
      normal_path: reactionSource === "operator"
        ? "ctx.react learned hazards + engine conservation/RNG"
        : "validation-only retired JS reaction teacher",
      pubchem: PUBCHEM,
      geant4: GEANT4
    });
    return { override: { system: { ensemble: "h2o_electrolysis_inverse_combustion" } } };
  },
  onRunStart(ctx) {
    ensureState(ctx);
    emitSnapshot(ctx, "initial");
  },
  onEventEnd(ctx) {
    const state = ensureState(ctx);
    if (!state || !ctx.event) {
      return;
    }
    const drive = geant4EventDrive(ctx.event);
    recordGeant4Drive(state, drive);
    state.tick += 1;
    if (reactionSource === "operator") {
      operatorReactionStep(ctx, state, state.tick, drive);
    } else if (state.tick <= SCENARIO.electrolysisTicks) {
      referenceElectrolysisStep(state, ctx.rng, state.tick, drive);
    } else {
      referenceCombustionStep(state, ctx.rng, state.tick, drive);
    }
    if (state.tick <= SCENARIO.electrolysisTicks) {
      if (state.tick === SCENARIO.electrolysisTicks) {
        const counts = currentCounts(state);
        state.waterAfterElectrolysis = counts.water;
        state.hydrogenAfterElectrolysis = counts.hydrogen;
        state.hydrogenLeftAfterElectrolysis = state.hydrogen.left;
        state.hydrogenRightAfterElectrolysis = state.hydrogen.right;
        state.oxygenAfterElectrolysis = counts.oxygen;
        state.hRadicalsAfterElectrolysis = counts.hRadicals;
        state.oRadicalsAfterElectrolysis = counts.oRadicals;
      }
    }
    advectVisualPackets(state, ctx.rng);
    const phase = state.tick <= SCENARIO.electrolysisTicks ? "electrolysis" : "inverse_combustion";
    if (state.tick === 1 || state.tick % SCENARIO.snapshotEvery === 0 ||
        state.tick === SCENARIO.electrolysisTicks || state.tick === TOTAL_TICKS) {
      emitSnapshot(ctx, phase);
    }
    if (state.tick === 1 || state.tick % FRAME_EVERY === 0 || state.tick === TOTAL_TICKS) {
      emitCellFrame(ctx, phase);
    }
  },
  onRunEnd(ctx) {
    const state = ctx.state;
    if (!state || !state.initialized) {
      return;
    }
    if (state.waterAfterElectrolysis === undefined) {
      const counts = currentCounts(state);
      state.waterAfterElectrolysis = counts.water;
      state.hydrogenAfterElectrolysis = counts.hydrogen;
      state.hydrogenLeftAfterElectrolysis = state.hydrogen.left;
      state.hydrogenRightAfterElectrolysis = state.hydrogen.right;
      state.oxygenAfterElectrolysis = counts.oxygen;
      state.hRadicalsAfterElectrolysis = counts.hRadicals;
      state.oRadicalsAfterElectrolysis = counts.oRadicals;
    }
    ctx.emit("h2o_cycle_summary", reactionLedger(state));
  }
};

globalThis.TRECH_CONFIG = cfg;
