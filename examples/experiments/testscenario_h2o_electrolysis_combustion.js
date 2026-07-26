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
  collectorY: 34.0,
  fieldStrength: 1.0,
  baseDissociationP: 0.010,
  combustionBaseP: 0.18,
  cathodeBalanceTolerance: 0.22,
  recoveryMinFraction: 0.94
};

const TOTAL_TICKS = SCENARIO.electrolysisTicks + SCENARIO.combustionTicks;
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
  for (let i = 0; i < SCENARIO.initialWater; i += 1) {
    const side = rng.uniform() < 0.5 ? -1 : 1;
    packets.push({
      id: i,
      x: side * (7.0 + rng.uniform() * 16.0),
      y: -18.0 + rng.uniform() * 36.0,
      vx: gaussian01(rng) * 0.10,
      vy: gaussian01(rng) * 0.10,
      active: true
    });
  }
  return packets;
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
      side: p.side || "",
      age: p.age ? round3(p.age) : 0
    });
  }
  return out;
}

function makeGasPacket(state, rng, species, side) {
  const cathodeX = side === "left" ? -SCENARIO.cathodeX : SCENARIO.cathodeX;
  const collectorY = SCENARIO.collectorY;
  const fromCathode = species === "H2";
  const x = fromCathode
    ? cathodeX + gaussian01(rng) * 1.8
    : gaussian01(rng) * 3.0;
  const y = fromCathode
    ? -26.0 + rng.uniform() * 16.0
    : collectorY + gaussian01(rng) * 1.8;
  const targetX = species === "H2" ? 0.0 : 0.0;
  const targetY = species === "H2" ? 18.0 + rng.uniform() * 7.0 : 20.0 + rng.uniform() * 5.0;
  const dx = targetX - x;
  const dy = targetY - y;
  const norm = Math.max(1e-9, Math.sqrt(dx * dx + dy * dy));
  const speed = species === "H2" ? 0.10 : 0.075;
  const pkt = {
    id: state.nextVisualId,
    species,
    side: side || "collector",
    x,
    y,
    vx: speed * dx / norm + gaussian01(rng) * 0.012,
    vy: speed * dy / norm + gaussian01(rng) * 0.012,
    age: 0
  };
  state.nextVisualId += 1;
  return pkt;
}

function makeProductWaterPacket(state, rng) {
  const a = rng.uniform() * 2.0 * Math.PI;
  const r = 2.0 + rng.uniform() * 6.0;
  const pkt = {
    id: state.nextVisualId,
    species: "H2O",
    side: "flame",
    x: Math.cos(a) * r,
    y: 12.0 + Math.sin(a) * r,
    vx: gaussian01(rng) * 0.035,
    vy: -0.045 + gaussian01(rng) * 0.025,
    age: 0
  };
  state.nextVisualId += 1;
  return pkt;
}

function advectVisualPackets(state) {
  function advect(list, maxKeep) {
    for (let i = 0; i < list.length; i += 1) {
      const p = list[i];
      p.x += p.vx;
      p.y += p.vy;
      p.age += 1;
      p.vx *= 0.995;
      p.vy *= 0.995;
      if (p.species === "H2O") {
        p.vy -= 0.0015;
      }
      if (p.x < -SCENARIO.chamberHalfSize || p.x > SCENARIO.chamberHalfSize) {
        p.vx *= -0.45;
        p.x = Math.max(-SCENARIO.chamberHalfSize, Math.min(SCENARIO.chamberHalfSize, p.x));
      }
      if (p.y < -SCENARIO.chamberHalfSize || p.y > SCENARIO.chamberHalfSize) {
        p.vy *= -0.45;
        p.y = Math.max(-SCENARIO.chamberHalfSize, Math.min(SCENARIO.chamberHalfSize, p.y));
      }
    }
    while (list.length > maxKeep) {
      list.shift();
    }
  }
  advect(state.visualH2, 220);
  advect(state.visualO2, 120);
  advect(state.visualWater, 220);
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
    w.vx = 0.94 * w.vx + gaussian01(rng) * 0.035;
    w.vy = 0.94 * w.vy + gaussian01(rng) * 0.035;
    w.x += w.vx;
    w.y += w.vy;
    if (Math.abs(w.x) > SCENARIO.chamberHalfSize) {
      w.vx *= -0.7;
      w.x = Math.max(-SCENARIO.chamberHalfSize, Math.min(SCENARIO.chamberHalfSize, w.x));
    }
    if (Math.abs(w.y) > SCENARIO.chamberHalfSize) {
      w.vy *= -0.7;
      w.y = Math.max(-SCENARIO.chamberHalfSize, Math.min(SCENARIO.chamberHalfSize, w.y));
    }
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
    if (state.visualH2.length >= 2) {
      state.visualH2.pop();
      state.visualH2.shift();
    }
    if (state.visualO2.length >= 1) {
      state.visualO2.pop();
    }
    state.visualWater.push(makeProductWaterPacket(state, rng));
    state.visualWater.push(makeProductWaterPacket(state, rng));
    attempts -= 1;
  }
}

// --- normal path: engine-owned discrete learned transition -----------------

function moveReactantPacketsForDisplay(state, rng) {
  // Representation-only packet motion. It cannot change species inventory or
  // decide whether a reaction occurs; ctx.react owns both decisions.
  for (let i = 0; i < state.waterPackets.length; i += 1) {
    const w = state.waterPackets[i];
    w.vx = 0.94 * w.vx + gaussian01(rng) * 0.035;
    w.vy = 0.94 * w.vy + gaussian01(rng) * 0.035;
    w.x += w.vx;
    w.y += w.vy;
    if (Math.abs(w.x) > SCENARIO.chamberHalfSize) {
      w.vx *= -0.7;
      w.x = Math.max(-SCENARIO.chamberHalfSize, Math.min(SCENARIO.chamberHalfSize, w.x));
    }
    if (Math.abs(w.y) > SCENARIO.chamberHalfSize) {
      w.vy *= -0.7;
      w.y = Math.max(-SCENARIO.chamberHalfSize, Math.min(SCENARIO.chamberHalfSize, w.y));
    }
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
    if (state.visualH2.length >= 2) {
      state.visualH2.pop();
      state.visualH2.shift();
    }
    if (state.visualO2.length >= 1) {
      state.visualO2.pop();
    }
    state.visualWater.push(makeProductWaterPacket(state, rng));
    state.visualWater.push(makeProductWaterPacket(state, rng));
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
    maxEmitPayloadBytes: 131072
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
      x: 0,
      y: 16,
      radius: phase === "inverse_combustion" ? 12 : 0
    }
  });
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
    advectVisualPackets(state);
    const phase = state.tick <= SCENARIO.electrolysisTicks ? "electrolysis" : "inverse_combustion";
    if (state.tick === 1 || state.tick % SCENARIO.snapshotEvery === 0 ||
        state.tick === SCENARIO.electrolysisTicks || state.tick === TOTAL_TICKS) {
      emitSnapshot(ctx, phase);
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
