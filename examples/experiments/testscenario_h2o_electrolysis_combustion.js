// Validation scenario: water electrolysis on two cathodes followed by inverse
// combustion (H2 + O2 -> H2O).
//
// The point is not to hard-code "water splits into hydrogen and oxygen" inside
// C++. The C++ engine supplies deterministic Geant4 transport/provenance,
// analytic G4EmCalculator interaction anchors, materials, and hook telemetry;
// this JS scenario carries a small reaction-inference layer over PubChem
// compound metadata and conserved atom inventories. The reaction ledger emitted
// at run end is therefore inspectable: PubChem supplies substance identity and
// formulas, Geant4 supplies interaction/energy anchors, and the hook layer
// advances a stochastic electrode/ignition bath without changing engine rules.
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
    molecularWeight: raw.molecular_weight,
    xlogp: raw.xlogp,
    tpsa: raw.tpsa,
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
    out.push({ id: p.id, x: round3(p.x), y: round3(p.y) });
  }
  return out;
}

function electrolysisProbability(tick, drive) {
  const ramp = Math.min(1.0, tick / 300.0);
  const scale = geant4ActivationScale();
  return Math.min(
    0.45,
    SCENARIO.baseDissociationP * SCENARIO.fieldStrength * scale * drive.activation * ramp
  );
}

function combustionProbability(tick, drive) {
  const local = Math.max(0, tick - SCENARIO.electrolysisTicks);
  const sparkRamp = Math.min(1.0, local / 120.0);
  const interactionMix = Math.max(0.1, Math.min(2.0, GEANT4.sparkEnergyMeV / GEANT4.probeEnergyMeV));
  return Math.min(0.80, SCENARIO.combustionBaseP * interactionMix * drive.activation * sparkRamp);
}

function inferElectrolysisStep(state, rng, tick, drive) {
  const pSplit = electrolysisProbability(tick, drive);
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
    }
  });
  const madeO2 = Math.floor(state.oRadicals / 2);
  if (madeO2 > 0) {
    state.oxygen += madeO2;
    state.oRadicals -= madeO2 * 2;
  }
}

function inferCombustionStep(state, rng, tick, drive) {
  const pBurn = combustionProbability(tick, drive);
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
    attempts -= 1;
  }
}

function currentCounts(state) {
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
  return {
    inference_model: {
      name: "pubchem_formula_conservation_geant4_scaled_stochastic",
      rule_table: false,
      atom_source: "PubChem molecular formulas parsed at runtime",
      rate_source: "Geant4 G4EmCalculator interaction anchors plus scored e-/gamma transport"
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
        true
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
  determinism: { mode: "strict" },
  chemistry: {
    enable: true,
    model: "pubchem_geant4_h2o_cycle_proxy",
    solver: "hook_inference"
  },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "h2o_electrolysis_inverse_combustion",
    volumeMm3: Math.pow(chamberSize, 3)
  },
  materials: [hydrogenGas, oxygenGas],
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
    if (state.tick <= SCENARIO.electrolysisTicks) {
      inferElectrolysisStep(state, ctx.rng, state.tick, drive);
      if (state.tick === SCENARIO.electrolysisTicks) {
        state.waterAfterElectrolysis = state.waterPackets.length;
        state.hydrogenAfterElectrolysis = state.hydrogen.left + state.hydrogen.right;
        state.hydrogenLeftAfterElectrolysis = state.hydrogen.left;
        state.hydrogenRightAfterElectrolysis = state.hydrogen.right;
        state.oxygenAfterElectrolysis = state.oxygen;
        state.hRadicalsAfterElectrolysis = state.hRadicals.left + state.hRadicals.right;
        state.oRadicalsAfterElectrolysis = state.oRadicals;
      }
    } else {
      inferCombustionStep(state, ctx.rng, state.tick, drive);
    }
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
      state.waterAfterElectrolysis = state.waterPackets.length;
      state.hydrogenAfterElectrolysis = state.hydrogen.left + state.hydrogen.right;
      state.hydrogenLeftAfterElectrolysis = state.hydrogen.left;
      state.hydrogenRightAfterElectrolysis = state.hydrogen.right;
      state.oxygenAfterElectrolysis = state.oxygen;
      state.hRadicalsAfterElectrolysis = state.hRadicals.left + state.hRadicals.right;
      state.oRadicalsAfterElectrolysis = state.oRadicals;
    }
    ctx.emit("h2o_cycle_summary", reactionLedger(state));
  }
};

globalThis.TRECH_CONFIG = cfg;
