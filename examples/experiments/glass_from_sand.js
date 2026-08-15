// Making glass: a material that does not exist when the run starts.
//
// Every other scenario in the tree simulates materials that are present from
// t=0. This one CREATES one: a crucible of silica sand, soda ash and limestone
// is heated in a furnace until the carbonates decompose, the batch melts, and
// silicate fusion produces soda-lime glass — a material whose inventory is
// exactly zero in the first frame.
//
// That is what forces the engine's dynamic, per-material inference: a cell's
// material CLASS changes while the run proceeds (batch_solid -> melt -> glass),
// so the operator that advances it, the chemistry that can occur in it, and the
// conduction across a contact between two cells all have to be re-selected as
// the run goes on. No fixed operator, no fixed level.
//
//   Geant4 base      : four real materials built from elements (the three raw
//                      batch components + the declared product), probed for
//                      density / electron density / mean excitation energy.
//   ctx.cascade      : those facts -> the temperatures at which this batch
//                      calcines, melts and fuses, plus the conduction
//                      coefficient. No onset is typed into this file.
//   ctx.evolve       : per-material thermal operators (a loose grain, a melt and
//                      a formed glass heat differently).
//   ctx.react        : per-material discrete chemistry with EXACT stoichiometry —
//                      Na2CO3 -> Na2O + CO2, CaCO3 -> CaO + CO2 and
//                      6 SiO2 + Na2O + CaO -> Na2O·CaO·6SiO2. The engine owns
//                      the seeded draw, availability and the declared Si/Na/Ca/
//                      C/O conservation; the models only predict hazards.
//   ctx.interact     : per-PAIR-material conduction (grain-grain, grain-melt,
//                      melt-melt, ... six combinations), so heat moves through
//                      whatever the neighbourhood is made of at that moment.
//
// Honest scope: Geant4 supplies the material base, the per-tick clock and the
// transported energy; it does not compute glass chemistry. The committed models
// under data/glass_furnace_* are hand-authored ILLUSTRATIVE maps (measured:false,
// no held-out accuracy) — this scenario demonstrates the mechanism and the
// per-material selection, not glass-making metrology. Cell heat capacities are
// assumed equal, which is what lets conduction be exactly equal-and-opposite.

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) throw new Error("TRECH_HELPERS not available");
const geometry = helpers.geometry;

// --- materials: three raw components + the product that does not exist yet ---
const SAND = "silica_sand";
const SODA = "soda_ash";
const LIME = "limestone";
const GLASS = "soda_lime_glass";
const CRUCIBLE = "G4_ALUMINUM_OXIDE";
const AIR = "G4_AIR";

// Compositions are material IDENTITY (kept in the scenario by the doctrine);
// every response to them is inferred.
const batchMaterials = [
  { name: SAND, densityGcm3: 2.65,
    components: [{ element: "Si", fraction: 0.4674 }, { element: "O", fraction: 0.5326 }] },
  { name: SODA, densityGcm3: 2.54,
    components: [{ element: "Na", fraction: 0.4341 }, { element: "C", fraction: 0.1134 },
                 { element: "O", fraction: 0.4525 }] },
  { name: LIME, densityGcm3: 2.71,
    components: [{ element: "Ca", fraction: 0.4004 }, { element: "C", fraction: 0.1200 },
                 { element: "O", fraction: 0.4796 }] },
  // Na2O·CaO·6SiO2 — declared to Geant4 so the cascade can read the PRODUCT's
  // real composition, while its simulated inventory starts at exactly zero.
  { name: GLASS, densityGcm3: 2.50,
    components: [{ element: "Na", fraction: 0.0967 }, { element: "Ca", fraction: 0.0843 },
                 { element: "Si", fraction: 0.3543 }, { element: "O", fraction: 0.4647 }] }
];

// --- typed controls ---------------------------------------------------------
const BALANCED_CELLS_PER_SIDE = 6;
const BALANCED_TICKS = 150;
const BALANCED_SUBSTEPS = 4;

const precisionProfile = TRECH_VALUE.choice("precision_profile", {
  label: "Precision profile", group: "Precision",
  description: "Moves every declared axis one rung; individual controls still override it.",
  default: "balanced", choices: helpers.precision.names()
});
const cellsPerSide = TRECH_VALUE.integer("cells_per_side", {
  label: "Crucible cells per side", group: "Precision", unit: "cells",
  description: "Spatial discretisation of the batch; the charge mass per cell scales with it.",
  default: BALANCED_CELLS_PER_SIDE, min: 4, max: 12, step: 1
});
const simulationTicks = TRECH_VALUE.integer("simulation_ticks", {
  label: "Geant4 ticks", group: "Precision", unit: "ticks",
  description: "Geant4 events and emitted states; the solver takes bounded sub-steps inside each.",
  default: BALANCED_TICKS, min: 20, max: 600, step: 10
});
const subStepsPerTick = TRECH_VALUE.integer("sub_steps_per_tick", {
  label: "Solver sub-steps per tick", group: "Precision", unit: "steps",
  description: "Temporal resolution of the operator passes inside one Geant4 tick.",
  default: BALANCED_SUBSTEPS, min: 1, max: 16, step: 1
});
const furnaceTemperatureK = TRECH_VALUE.number("furnace_temperature_k", {
  label: "Furnace temperature", group: "Conditions", unit: "K",
  description: "Lower boundary condition; changing it changes the inferred chemistry, not a script.",
  default: 1750.0, min: 1200.0, max: 1900.0, step: 10.0
});
const ambientTemperatureK = TRECH_VALUE.number("ambient_temperature_k", {
  label: "Ambient temperature", group: "Conditions", unit: "K",
  description: "Upper/side boundary and initial charge temperature.",
  default: 300.0, min: 280.0, max: 500.0, step: 5.0
});
// Which operator models the normal path runs. `reference` is the original
// hand-authored illustrative map family, kept as the audit/harvest teacher;
// `operator` is the distilled trained family that carries a measured input
// hull, a trained scale band and independent held-out accuracy.
const physicsSource = TRECH_VALUE.choice("physics_source", {
  label: "Physics source", group: "Inference",
  description: "operator = trained distilled models (default); reference = the illustrative " +
               "hand-authored teacher they were distilled from.",
  default: "operator", choices: ["operator", "reference"]
});
const emitTrainingRows = TRECH_VALUE.boolean("emit_training_rows", {
  label: "Emit training rows", group: "Inference",
  description: "Deterministic harvest sideband: the teacher's exact inputs/outputs for the " +
               "states this run actually visits. Off during ordinary runs.",
  default: false
});
const holdSeconds = TRECH_VALUE.number("hold_seconds", {
  label: "Furnace hold", group: "Time", unit: "s",
  description: "Physical duration of the melt; only the integration horizon.",
  default: 9000.0, min: 600.0, max: 36000.0, step: 600.0
});

const overrideOf = (value, balanced) => (value === balanced ? 0 : value);
const PRECISION = helpers.precision.resolve({
  profile: precisionProfile,
  note: "spatial cells / temporal sub-steps / output ticks; the charge inventory per cell is " +
        "rescaled so total batch mass is invariant under refinement",
  axes: [
    { name: "cells", role: "spatial", control: "cells_per_side", unit: "cells",
      balanced: BALANCED_CELLS_PER_SIDE, min: 4, max: 12,
      direction: "higher_is_finer", integer: true,
      override: overrideOf(cellsPerSide, BALANCED_CELLS_PER_SIDE) },
    { name: "sub_steps", role: "temporal", control: "sub_steps_per_tick", unit: "steps",
      balanced: BALANCED_SUBSTEPS, min: 1, max: 16,
      direction: "higher_is_finer", integer: true,
      override: overrideOf(subStepsPerTick, BALANCED_SUBSTEPS) },
    { name: "output_ticks", role: "output", control: "simulation_ticks", unit: "ticks",
      balanced: BALANCED_TICKS, min: 20, max: 600,
      direction: "higher_is_finer", integer: true,
      override: overrideOf(simulationTicks, BALANCED_TICKS) }
  ]
});

const SIDE = PRECISION.value("cells");
const TICKS = PRECISION.value("output_ticks");
const SUB_STEPS = PRECISION.value("sub_steps");
const CELL_COUNT = SIDE * SIDE;
const TICK_INTERVAL_S = holdSeconds / TICKS;
const SUB_STEP_S = TICK_INTERVAL_S / SUB_STEPS;

// --- crucible geometry (an experiment boundary condition, not a law) --------
const CRUCIBLE_WIDTH_MM = 120.0;
const CELL_PITCH_MM = CRUCIBLE_WIDTH_MM / SIDE;
const CHARGE_HEIGHT_MM = CRUCIBLE_WIDTH_MM;

// Formula-unit parcels per cell at the balanced discretisation, rescaled so the
// total charge is invariant when the cell count changes (precision must not
// silently change the experiment).
const BALANCED_CELLS = BALANCED_CELLS_PER_SIDE * BALANCED_CELLS_PER_SIDE;
const CHARGE_SCALE = BALANCED_CELLS / CELL_COUNT;
const round = (value) => Math.max(1, Math.round(value));
const CHARGE = {
  sio2: round(60 * CHARGE_SCALE),
  na2co3: round(10 * CHARGE_SCALE),
  caco3: round(10 * CHARGE_SCALE)
};

// --- species, channels and the conservation the engine must enforce ---------
const SPECIES = ["sio2", "na2co3", "caco3", "na2o", "cao", "co2", "glass"];
const CHANNELS = [
  // Na2CO3 -> Na2O + CO2
  { name: "soda_calcination", delta: { na2co3: -1, na2o: 1, co2: 1 } },
  // CaCO3 -> CaO + CO2
  { name: "lime_calcination", delta: { caco3: -1, cao: 1, co2: 1 } },
  // 6 SiO2 + Na2O + CaO -> Na2O·CaO·6SiO2  (the new material)
  { name: "glass_fusion", delta: { sio2: -6, na2o: -1, cao: -1, glass: 1 } }
];
// Atoms per formula unit. The engine validates every channel against these
// BEFORE any inference, draw or mutation.
const CONSERVATION = [
  { name: "silicon", coefficients: { sio2: 1, glass: 6 } },
  { name: "sodium", coefficients: { na2co3: 2, na2o: 2, glass: 2 } },
  { name: "calcium", coefficients: { caco3: 1, cao: 1, glass: 1 } },
  { name: "carbon", coefficients: { na2co3: 1, caco3: 1, co2: 1 } },
  { name: "oxygen",
    coefficients: { sio2: 2, na2co3: 3, caco3: 3, na2o: 1, cao: 1, co2: 2, glass: 14 } }
];

// Material classes a cell can be in. A cell's class is IDENTITY bookkeeping
// (what is this cell made of right now), not a law: the engine picks the
// operator, the chemistry and the conduction for whatever class it finds.
const KIND_BATCH = "batch_solid";
const KIND_MELT = "melt";
const KIND_GLASS = "glass";
// Representation only — display tints, never physics inputs.
const KIND_COLOR = {
  [KIND_BATCH]: [0.83, 0.74, 0.52, 0.95],
  [KIND_MELT]: [1.0, 0.45, 0.10, 0.95],
  [KIND_GLASS]: [0.55, 0.85, 0.90, 0.85]
};

// Promotion tolerances for the trained family against its teacher. The
// continuous fields must track it tightly; the discrete counts get a little
// room because a hazard difference of ~1e-8 can flip one borderline seeded
// draw, which then shifts a whole cell's later trajectory.
const OPERATOR_GAP_TOLERANCES = {
  glass_units_relative: 0.05,
  released_co2_relative: 0.05,
  remaining_carbonates_relative: 0.08,
  first_glass_tick_absolute: 3,
  glass_cells_absolute: 2,
  mean_temperature_k_absolute: 2.0,
  max_temperature_k_absolute: 1.0,
  min_fusion_temperature_k_absolute: 5.0
};

const state = {
  ready: false,
  tick: 0,
  timeS: 0.0,
  cells: null,
  params: null,
  cascade: null,
  probes: null,
  inference: { evolve: 0, react: 0, interact: 0, outOfDomain: 0, draws: 0 },
  selection: { evolve: [], react: [], interact: [] },
  kindsSeen: {},
  pairKindsRun: {},
  transitions: { toMelt: 0, toGlass: 0 },
  accepted: { soda_calcination: 0, lime_calcination: 0, glass_fusion: 0 },
  unclaimedGlassCells: 0,
  harvest: { thermal: {}, chemistry: {} },
  harvestRows: 0,
  harvestPredicts: 0,
  // Aggregated trust profile of the ACTIVE per-material operator family
  // (thermal + chemistry). Conduction is excluded on purpose: it stays in the
  // reference family in both modes, and the summary says so.
  trust: {
    stages: 0, domainMeasured: true, scaleMismatch: false, trainedScale: null,
    holdoutR2: null, holdoutSamples: null,
    missingInputs: [], starvedInputs: [], selection: null
  },
  minFusionTemperatureK: Infinity,
  minCalcinationTemperatureK: Infinity,
  firstGlassTick: -1,
  firstGlassHeightMm: null,
  atoms0: null,
  history: []
};

function elementTotals(cells) {
  const totals = { silicon: 0, sodium: 0, calcium: 0, carbon: 0, oxygen: 0 };
  for (const inv of CONSERVATION) {
    let sum = 0;
    for (const species of SPECIES) {
      const coefficient = inv.coefficients[species] || 0;
      if (!coefficient) continue;
      for (let i = 0; i < CELL_COUNT; ++i) {
        sum += coefficient * cells[species][i];
      }
    }
    totals[inv.name] = sum;
  }
  return totals;
}

function classifyCells(cells) {
  const kinds = new Array(CELL_COUNT);
  for (let i = 0; i < CELL_COUNT; ++i) {
    const convertedSilica = cells.glass[i] * 6;
    const silica = cells.sio2[i] + convertedSilica;
    const mostlyGlass = convertedSilica >= 0.85 * silica && cells.glass[i] > 0;
    if (mostlyGlass) {
      kinds[i] = KIND_GLASS;
    } else if (cells.melt_fraction[i] >= 0.5) {
      kinds[i] = KIND_MELT;
    } else {
      kinds[i] = KIND_BATCH;
    }
    if (kinds[i] !== cells.kind[i]) {
      if (kinds[i] === KIND_MELT) state.transitions.toMelt += 1;
      if (kinds[i] === KIND_GLASS) {
        state.transitions.toGlass += 1;
        if (state.firstGlassTick < 0) {
          state.firstGlassTick = state.tick;
          state.firstGlassHeightMm = cells.y[i];
        }
      }
    }
    cells.kind[i] = kinds[i];
    state.kindsSeen[kinds[i]] = (state.kindsSeen[kinds[i]] || 0) + 1;
  }
  return kinds;
}

function buildCells() {
  const cells = {
    x: new Float64Array(CELL_COUNT),
    y: new Float64Array(CELL_COUNT),
    z: new Float64Array(CELL_COUNT),
    temperature_k: new Float64Array(CELL_COUNT),
    melt_fraction: new Float64Array(CELL_COUNT),
    contact_temperature_k: new Float64Array(CELL_COUNT),
    boundary: new Array(CELL_COUNT).fill("interior"),
    kind: new Array(CELL_COUNT).fill(KIND_BATCH),
    ids: new Array(CELL_COUNT)
  };
  for (const species of SPECIES) {
    cells[species] = new Array(CELL_COUNT).fill(0);
  }
  for (let row = 0; row < SIDE; ++row) {
    for (let col = 0; col < SIDE; ++col) {
      const i = row * SIDE + col;
      cells.x[i] = (col + 0.5) * CELL_PITCH_MM - 0.5 * CRUCIBLE_WIDTH_MM;
      cells.y[i] = (row + 0.5) * (CHARGE_HEIGHT_MM / SIDE);
      cells.z[i] = 0.0;
      cells.temperature_k[i] = ambientTemperatureK;
      // Boundary condition (declared experiment geometry, not a law): the
      // bottom layer sits on the furnace floor, the top layer radiates to the
      // ambient roof, and an interior cell touches no boundary at all -- its
      // only exchange is with its neighbours, which the conduction operator
      // owns. "No boundary" is expressed as a contact at the cell's own
      // temperature, refreshed every sub-step.
      cells.boundary[i] = row === 0 ? "floor"
                          : (row === SIDE - 1 ? "roof" : "interior");
      cells.ids[i] = "cell_" + i;
      cells.sio2[i] = CHARGE.sio2;
      cells.na2co3[i] = CHARGE.na2co3;
      cells.caco3[i] = CHARGE.caco3;
    }
  }
  return cells;
}

// Refresh each cell's boundary contact temperature. Interior cells contact no
// boundary, so their contact temperature is their own -- the thermal operator
// then contributes nothing for them and all their heat arrives through the
// per-pair conduction operator.
function refreshContacts(cells) {
  for (let i = 0; i < CELL_COUNT; ++i) {
    const boundary = cells.boundary[i];
    cells.contact_temperature_k[i] =
      boundary === "floor" ? furnaceTemperatureK
      : (boundary === "roof" ? ambientTemperatureK : cells.temperature_k[i]);
  }
}

function recordTrust(result, isThermal) {
  if (!result || !result.trace) return;
  const trust = state.trust;
  if (isThermal && result.selection && result.selection.status === "selected") {
    trust.selection = result.selection;
  }
  for (const stage of result.trace) {
    if (!stage.ran || (stage.elementsMatched || 0) === 0) continue;
    trust.stages += 1;
    trust.domainMeasured = trust.domainMeasured && stage.domainMeasured === true;
    trust.scaleMismatch = trust.scaleMismatch || stage.scaleMismatch === true;
    if (trust.trainedScale === null && stage.trainedScale) {
      trust.trainedScale = stage.trainedScale;
    }
    if (stage.holdoutR2 !== null && stage.holdoutR2 !== undefined) {
      trust.holdoutR2 = trust.holdoutR2 === null
        ? stage.holdoutR2 : Math.min(trust.holdoutR2, stage.holdoutR2);
    }
    if (stage.holdoutSamples !== null && stage.holdoutSamples !== undefined) {
      trust.holdoutSamples = trust.holdoutSamples === null
        ? stage.holdoutSamples : Math.min(trust.holdoutSamples, stage.holdoutSamples);
    }
    for (const name of stage.missingInputs || []) {
      if (trust.missingInputs.indexOf(name) < 0) trust.missingInputs.push(name);
    }
    for (const name of stage.starvedInputs || []) {
      if (trust.starvedInputs.indexOf(name) < 0) trust.starvedInputs.push(name);
    }
  }
}

function recordSelection(bucket, result) {
  if (!result || !result.selection) return;
  const groups = (result.selection.groups || []).map(
    (g) => g.elementKind + ":" + g.status + ":" + g.elements);
  const signature = result.selection.status + " [" + groups.join(", ") + "]";
  if (state.selection[bucket].indexOf(signature) < 0) {
    state.selection[bucket].push(signature);
  }
}

// Deterministic harvest: the TEACHER's exact inputs and outputs for the states
// this run actually visits, sampled on a fixed stride. It calls the reference
// models through ctx.predict — no law is re-implemented here — and every sampled
// prediction is counted like any other inference.
const HARVEST_CELL_STRIDE = 5;
const HARVEST_SUBSTEP_STRIDE = 2;
function harvestTeacherRows(ctx, cells, kinds, subStep) {
  if (!emitTrainingRows || (subStep % HARVEST_SUBSTEP_STRIDE) !== 0) {
    return;
  }
  const thermal = { batch_solid: [], melt: [], glass: [] };
  const chemistry = { batch_solid: [], melt: [] };
  for (let i = 0; i < CELL_COUNT; i += HARVEST_CELL_STRIDE) {
    const kind = kinds[i];
    const temperature = cells.temperature_k[i];
    const contact = cells.contact_temperature_k[i];
    state.harvestPredicts += 1;
    const heat = ctx.predict("reference_thermal_" + kind, {
      temperature_k: temperature,
      contact_temperature_k: contact,
      melt_onset_k: state.params.melt_onset_k
    });
    if (heat) {
      const row = {
        temperature_k: temperature,
        contact_temperature_k: contact,
        melt_onset_k: state.params.melt_onset_k,
        d_temperature_k_dt: heat.d_temperature_k_dt
      };
      if (heat.d_melt_fraction_dt !== undefined) {
        row.d_melt_fraction_dt = heat.d_melt_fraction_dt;
      }
      thermal[kind].push(row);
    }
    if (kind !== KIND_GLASS) {
      state.harvestPredicts += 1;
      const hazards = ctx.predict("reference_chemistry_" + kind, {
        temperature_k: temperature,
        calcination_onset_k: state.params.calcination_onset_k,
        fusion_onset_k: state.params.fusion_onset_k
      });
      if (hazards) {
        const row = {
          temperature_k: temperature,
          calcination_onset_k: state.params.calcination_onset_k,
          fusion_onset_k: state.params.fusion_onset_k,
          hazard_soda_calcination: hazards.hazard_soda_calcination,
          hazard_lime_calcination: hazards.hazard_lime_calcination
        };
        if (hazards.hazard_glass_fusion !== undefined) {
          row.hazard_glass_fusion = hazards.hazard_glass_fusion;
        }
        chemistry[kind].push(row);
      }
    }
  }
  for (const kind of Object.keys(thermal)) {
    if (thermal[kind].length > 0) {
      state.harvest.thermal[kind] = (state.harvest.thermal[kind] || []).concat(thermal[kind]);
    }
  }
  for (const kind of Object.keys(chemistry)) {
    if (chemistry[kind].length > 0) {
      state.harvest.chemistry[kind] =
        (state.harvest.chemistry[kind] || []).concat(chemistry[kind]);
    }
  }
}

function flushHarvest(ctx) {
  if (!emitTrainingRows) return;
  for (const kind of Object.keys(state.harvest.thermal)) {
    const rows = state.harvest.thermal[kind];
    if (!rows || rows.length === 0) continue;
    state.harvestRows += rows.length;
    ctx.emit("thermal_sample_" + kind, { teacher: "reference_thermal_" + kind, samples: rows });
    state.harvest.thermal[kind] = [];
  }
  for (const kind of Object.keys(state.harvest.chemistry)) {
    const rows = state.harvest.chemistry[kind];
    if (!rows || rows.length === 0) continue;
    state.harvestRows += rows.length;
    ctx.emit("chemistry_sample_" + kind, { teacher: "reference_chemistry_" + kind, samples: rows });
    state.harvest.chemistry[kind] = [];
  }
}

function advance(ctx, cells, kinds, dt) {
  const context = Object.assign({}, state.params, {
    heater_temperature_k: furnaceTemperatureK,
    ambient_temperature_k: ambientTemperatureK
  });

  // 1) heat moves between neighbouring cells, through whatever the two cells
  //    are made of RIGHT NOW (six declared material combinations).
  const conduction = ctx.interact({
    dt,
    cutoff: CELL_PITCH_MM * 1.05,
    fields: [{ name: "temperature_k", symmetry: "antisymmetric", min: 0.0, max: 4000.0 }],
    state: { temperature_k: cells.temperature_k },
    positions: { x: cells.x, y: cells.y, z: cells.z },
    context,
    operator_role: "cell_conduction",
    element_kind: kinds
  });
  if (conduction) {
    state.inference.interact += conduction.inferenceCount;
    state.inference.outOfDomain += conduction.outOfDomainInferences;
    recordSelection("interact", conduction);
    for (const stage of conduction.trace || []) {
      if (stage.ran && stage.pairsMatched > 0) {
        state.pairKindsRun[stage.pairKind] =
          (state.pairKindsRun[stage.pairKind] || 0) + stage.pairsMatched;
      }
    }
  }

  // 2) each cell heats and melts through the operator its own material selected.
  const thermal = ctx.evolve({
    dt,
    fields: [
      { name: "temperature_k", min: 0.0, max: 4000.0 },
      { name: "melt_fraction", min: 0.0, max: 1.0 }
    ],
    state: { temperature_k: cells.temperature_k, melt_fraction: cells.melt_fraction },
    aux: { contact_temperature_k: cells.contact_temperature_k },
    context,
    operator_role: "thermal_state",
    element_kind: kinds
  });
  if (thermal) {
    state.inference.evolve += thermal.inferenceCount;
    state.inference.outOfDomain += thermal.outOfDomainInferences;
    recordSelection("evolve", thermal);
    recordTrust(thermal, true);
  }

  // 3) discrete chemistry: decomposition in the batch, fusion once molten.
  //    A fully formed glass cell has no declared chemistry left, so the engine
  //    reports it as unclaimed and leaves its inventory untouched.
  // Snapshot exactly what the chemistry operator will see, so the run can prove
  // afterwards that no cell reacted below its inferred onset.
  const before = {
    temperature: cells.temperature_k.slice(),
    co2: cells.co2.slice(),
    glass: cells.glass.slice()
  };
  const reaction = ctx.react({
    dt,
    species: SPECIES,
    state: {
      sio2: cells.sio2, na2co3: cells.na2co3, caco3: cells.caco3,
      na2o: cells.na2o, cao: cells.cao, co2: cells.co2, glass: cells.glass
    },
    aux: { temperature_k: cells.temperature_k, melt_fraction: cells.melt_fraction },
    context,
    channels: CHANNELS,
    conservation: CONSERVATION,
    operator_role: "batch_chemistry",
    element_kind: kinds
  });
  if (reaction) {
    state.inference.react += reaction.inferenceCount;
    state.inference.outOfDomain += reaction.outOfDomainInferences;
    state.inference.draws += reaction.drawCount;
    recordSelection("react", reaction);
    recordTrust(reaction, false);
    for (const channel of reaction.channels || []) {
      state.accepted[channel.name] += channel.accepted;
    }
    for (const group of (reaction.selection && reaction.selection.groups) || []) {
      if (group.status !== "selected") {
        state.unclaimedGlassCells += group.elements;
      }
    }
    if (reaction.transitionsAccepted > 0) {
      // Attribute each accepted transition to the CELL it changed (the engine
      // reports counts, not identities), and record the coldest temperature at
      // which each family fired. The validation then rejects any chemistry that
      // happened below its inferred onset.
      for (let i = 0; i < CELL_COUNT; ++i) {
        const t = before.temperature[i];
        if (cells.co2[i] !== before.co2[i]) {
          state.minCalcinationTemperatureK = Math.min(state.minCalcinationTemperatureK, t);
        }
        if (cells.glass[i] !== before.glass[i]) {
          state.minFusionTemperatureK = Math.min(state.minFusionTemperatureK, t);
        }
      }
    }
  }
  return { conduction, thermal, reaction };
}

function aggregate(cells) {
  let glass = 0, sio2 = 0, carbonates = 0, co2 = 0;
  let meanT = 0, maxT = -Infinity, minT = Infinity;
  const kindCounts = { [KIND_BATCH]: 0, [KIND_MELT]: 0, [KIND_GLASS]: 0 };
  for (let i = 0; i < CELL_COUNT; ++i) {
    glass += cells.glass[i];
    sio2 += cells.sio2[i];
    carbonates += cells.na2co3[i] + cells.caco3[i];
    co2 += cells.co2[i];
    meanT += cells.temperature_k[i];
    maxT = Math.max(maxT, cells.temperature_k[i]);
    minT = Math.min(minT, cells.temperature_k[i]);
    kindCounts[cells.kind[i]] += 1;
  }
  return {
    glass_units: glass, unreacted_sio2: sio2, remaining_carbonates: carbonates,
    released_co2: co2, mean_temperature_k: meanT / CELL_COUNT,
    max_temperature_k: maxT, min_temperature_k: minT, kinds: kindCounts
  };
}

globalThis.TRECH_HOOKS = {
  onEventEnd(ctx) {
    if (!state.ready) {
      // The Geant4 material base + the cascade that turns it into this batch's
      // onset temperatures. Nothing below is typed into this file.
      const probes = {};
      for (const name of [SAND, SODA, LIME, GLASS]) {
        const probe = ctx.materials && ctx.materials[name];
        if (probe) {
          probes[name] = {
            density_g_per_cm3: probe.density_g_per_cm3,
            electron_density_per_cm3: probe.electron_density_per_cm3,
            mean_excitation_energy_ev: probe.mean_excitation_energy_ev
          };
        }
      }
      state.probes = probes;
      const inferred = ctx.cascade(
        { "context.heater_temperature_k": furnaceTemperatureK },
        ["nano_batch_material_response", "macro_furnace_response"]);
      if (!inferred) {
        throw new Error("glass_from_sand requires determinism.mode=predictive");
      }
      state.cascade = inferred.__cascade;
      state.params = {
        calcination_onset_k: inferred.calcination_onset_k,
        melt_onset_k: inferred.melt_onset_k,
        fusion_onset_k: inferred.fusion_onset_k,
        conduction_coefficient: inferred.conduction_coefficient
      };
      state.cells = buildCells();
      refreshContacts(state.cells);
      state.atoms0 = elementTotals(state.cells);
      classifyCells(state.cells);
      state.ready = true;
      ctx.emit("glass_furnace_scenario", {
        scenario: "glass_from_sand",
        physics_source: physicsSource,
        honest_scope: "Geant4 supplies the material base and the per-tick clock; the committed " +
                      "operator/cascade models are hand-authored illustrative maps (measured:false).",
        geant4_materials: probes,
        inferred_conditions: state.params,
        cascade: state.cascade,
        charge_per_cell: CHARGE,
        cells: CELL_COUNT,
        channels: CHANNELS.map((c) => c.name),
        conserved: CONSERVATION.map((c) => c.name),
        precision: { profile: PRECISION.profile, axes: PRECISION.axes }
      });
    }

    const cells = state.cells;
    for (let s = 0; s < SUB_STEPS; ++s) {
      refreshContacts(cells);
      const kinds = cells.kind.slice();
      harvestTeacherRows(ctx, cells, kinds, s);
      advance(ctx, cells, kinds, SUB_STEP_S);
      classifyCells(cells);
    }
    flushHarvest(ctx);
    state.tick += 1;
    state.timeS += TICK_INTERVAL_S;

    const summary = aggregate(cells);
    state.history.push({
      tick: state.tick, time_s: state.timeS,
      glass_units: summary.glass_units, kinds: Object.assign({}, summary.kinds),
      mean_temperature_k: summary.mean_temperature_k
    });

    // Studio/viz replay: the created material is visible as a colour change,
    // labelled a representation choice.
    const positions = [];
    const colors = [];
    for (let i = 0; i < CELL_COUNT; ++i) {
      positions.push([cells.x[i], cells.y[i], cells.z[i]]);
      colors.push(KIND_COLOR[cells.kind[i]]);
    }
    ctx.emit("material_frame", {
      tag: "glass_furnace",
      time_s: state.timeS,
      physical_time_s: state.timeS,
      time_scale: 1.0,
      phase: summary.kinds[KIND_GLASS] > 0 ? "glass_forming"
             : (summary.kinds[KIND_MELT] > 0 ? "melting" : "heating"),
      particle_ids: cells.ids,
      positions_mm: positions,
      colors_rgba: colors,
      representation_override: "cell colour encodes the cell's CURRENT material class",
      counts: summary.kinds,
      physics_state: {
        glass_units: summary.glass_units,
        mean_temperature_k: summary.mean_temperature_k,
        remaining_carbonates: summary.remaining_carbonates
      }
    });

    if (state.tick >= TICKS) {
      const atoms = elementTotals(cells);
      const conserved = {};
      let allConserved = true;
      for (const key of Object.keys(state.atoms0)) {
        conserved[key] = atoms[key] - state.atoms0[key];
        if (conserved[key] !== 0) allConserved = false;
      }
      const pairKinds = Object.keys(state.pairKindsRun).sort();
      const materialKinds = Object.keys(state.kindsSeen).sort();
      const totalInferences = state.inference.evolve + state.inference.react +
                              state.inference.interact;
      const operatorOodFraction = totalInferences > 0
        ? state.inference.outOfDomain / totalInferences : 0.0;
      const round4 = (v) => Math.round(v * 1e4) / 1e4;
      const round3 = (v) => Math.round(v * 1e3) / 1e3;
      const validation = {
        geant4_material_base_present:
          Object.keys(state.probes).length === 4 &&
          Object.values(state.probes).every((p) => p.density_g_per_cm3 > 0.0),
        cascade_supplied_conditions:
          isFinite(state.params.calcination_onset_k) &&
          state.params.calcination_onset_k > 0.0 &&
          state.params.calcination_onset_k < state.params.melt_onset_k &&
          state.params.melt_onset_k < state.params.fusion_onset_k,
        // The point of the scenario: the product did not exist at t=0.
        product_material_created:
          state.history.length > 0 && state.history[0].glass_units === 0 &&
          summary.glass_units > 0,
        material_class_changed_during_run:
          state.transitions.toMelt > 0 && state.transitions.toGlass > 0 &&
          materialKinds.length === 3,
        // Per-material inference actually happened, in all three operators.
        per_material_operator_selection:
          state.selection.evolve.length > 0 && state.selection.react.length > 0 &&
          state.selection.interact.length > 0 &&
          state.selection.evolve.some((s) => s.indexOf(KIND_MELT) >= 0) &&
          state.selection.react.some((s) => s.indexOf(KIND_MELT) >= 0),
        per_pair_material_conduction: pairKinds.length >= 3,
        formed_glass_has_no_further_chemistry: state.unclaimedGlassCells > 0,
        exact_atom_conservation: allConserved,
        chemistry_respects_inferred_onsets:
          state.accepted.soda_calcination > 0 && state.accepted.lime_calcination > 0 &&
          state.accepted.glass_fusion > 0 &&
          state.minCalcinationTemperatureK >= state.params.calcination_onset_k &&
          state.minFusionTemperatureK >= state.params.fusion_onset_k,
        // Heat only enters at the floor, so the first glass must appear low.
        conversion_follows_the_thermal_gradient:
          state.firstGlassHeightMm !== null &&
          state.firstGlassHeightMm < 0.5 * CHARGE_HEIGHT_MM,
        every_inference_accounted: totalInferences > 0 &&
          state.inference.draws > 0 && state.inference.draws <= state.inference.react
      };
      ctx.emit("glass_furnace_summary", {
        scenario: "glass_from_sand",
        physics_source: physicsSource,
        harvest_rows: state.harvestRows,
        ticks: state.tick,
        hold_s: holdSeconds,
        conditions: {
          furnace_temperature_k: furnaceTemperatureK,
          ambient_temperature_k: ambientTemperatureK,
          cells: CELL_COUNT,
          sub_steps_per_tick: SUB_STEPS
        },
        precision: { profile: PRECISION.profile, axes: PRECISION.axes },
        geant4: state.probes,
        inferred_conditions: state.params,
        cascade: state.cascade,
        product: {
          glass_units: summary.glass_units,
          glass_units_at_start: state.history[0].glass_units,
          unreacted_sio2: summary.unreacted_sio2,
          remaining_carbonates: summary.remaining_carbonates,
          released_co2: summary.released_co2,
          first_glass_tick: state.firstGlassTick,
          first_glass_height_mm: state.firstGlassHeightMm,
          final_kinds: summary.kinds
        },
        materials: {
          classes_seen: materialKinds,
          transitions_to_melt: state.transitions.toMelt,
          transitions_to_glass: state.transitions.toGlass,
          pair_kinds_evaluated: pairKinds,
          pair_kind_evaluations: state.pairKindsRun,
          unclaimed_cell_evaluations: state.unclaimedGlassCells
        },
        selection: state.selection,
        chemistry: {
          accepted: state.accepted,
          min_calcination_temperature_k: state.minCalcinationTemperatureK,
          min_fusion_temperature_k: state.minFusionTemperatureK,
          atom_balance_delta: conserved
        },
        inference: Object.assign({ total: totalInferences }, state.inference),
        thermal: {
          mean_temperature_k: summary.mean_temperature_k,
          max_temperature_k: summary.max_temperature_k,
          min_temperature_k: summary.min_temperature_k
        },
        fidelity: {
          models: physicsSource === "operator"
            ? "distilled trained operators under data/glass_furnace_operators_trained/ " +
              "(measured meso hull + occupancy from the states five independent furnace " +
              "operating points visited, held out on two never-fitted ones); conduction and the " +
              "cascade stages remain the illustrative family"
            : "hand-authored illustrative maps under data/glass_furnace_operators/",
          measured: false,
          teacher: "hand-authored illustrative glass-furnace operator family " +
                   "(data/glass_furnace_operators/)",
          caveat: "the teacher is a LINEAR map, so the distilled family reproduces it to ~1e-6 " +
                  "and its near-unit held-out R2 is expected — the trained artefacts add a " +
                  "measured domain, occupancy, scale band and carried holdout, NOT new physics. " +
                  "Onsets/conductances remain illustrative and equal cell heat capacity is " +
                  "assumed, which is what makes conduction exactly equal-and-opposite."
        },
        // Both sources emit the same compact comparison record; the reusable
        // paired-run validator computes the gaps against these tolerances.
        operator_vs_reference: {
          schema: "trech_operator_reference_pair_v1",
          comparison_key: {
            seed: Number(ctx.runtime.seed),
            furnace_temperature_k: furnaceTemperatureK,
            ambient_temperature_k: ambientTemperatureK,
            hold_s: holdSeconds,
            cells: CELL_COUNT,
            sub_steps_per_tick: SUB_STEPS,
            geant4_ticks: TICKS
          },
          source: physicsSource,
          teacher: "hand-authored illustrative glass-furnace operator family in " +
                   "data/glass_furnace_operators/ (evaluated by the same engine operators)",
          measured: false,
          tolerances: OPERATOR_GAP_TOLERANCES,
          trust: {
            // No authored state law runs on EITHER path here: the reference
            // family is a model file, not JavaScript physics.
            authored_state_law: false,
            selection: state.trust.selection,
            domain_measured: state.trust.stages > 0 ? state.trust.domainMeasured : null,
            trained_scale: state.trust.trainedScale,
            scale_mismatch: state.trust.scaleMismatch,
            missing_inputs: state.trust.missingInputs,
            starved_inputs: state.trust.starvedInputs,
            holdout_r2: state.trust.holdoutR2,
            holdout_samples: state.trust.holdoutSamples,
            inference_count: totalInferences,
            out_of_domain_count: state.inference.outOfDomain,
            out_of_domain_fraction: operatorOodFraction,
            non_operator_inference_count: (state.cascade.stagesRun || 0) + state.harvestPredicts,
            non_operator_out_of_domain_count: state.cascade.stagesExtrapolating || 0,
            conduction_family: "reference (exactly linear in the temperature difference; a " +
                               "distilled twin would carry the same coefficient with fit error)"
          },
          observables: {
            glass_units: summary.glass_units,
            released_co2: summary.released_co2,
            remaining_carbonates: summary.remaining_carbonates,
            first_glass_tick: state.firstGlassTick,
            glass_cells: summary.kinds[KIND_GLASS],
            mean_temperature_k: round3(summary.mean_temperature_k),
            max_temperature_k: round3(summary.max_temperature_k),
            min_fusion_temperature_k: round3(state.minFusionTemperatureK)
          }
        },
        validation
      });
    }
  }
};

// --- declared models --------------------------------------------------------
// The per-material operators come from one of two families, chosen by
// `physics_source`:
//   operator  (default) -> data/glass_furnace_operators_trained/  — distilled
//              from the reference family across independent furnace operating
//              points; each carries a MEASURED input hull, an occupancy
//              histogram, its trained scale band and independent held-out
//              accuracy, so a run outside the states it learned is flagged.
//   reference           -> data/glass_furnace_operators/ — the original
//              hand-authored illustrative maps, retained as the audit/harvest
//              teacher. They are also declared (without an operator role, so
//              contextual selection never picks them up) whenever the harvest
//              sideband is on, which is how the teacher's exact rows are taken.
// Cell-to-cell conduction stays in the reference family in both modes: the law
// there is exactly linear in the temperature difference, so a distilled twin
// would carry the same coefficient with added fit error and no new signal.
const OPERATOR_DIR = physicsSource === "operator"
  ? "data/glass_furnace_operators_trained"
  : "data/glass_furnace_operators";
const REFERENCE_DIR = "data/glass_furnace_operators";
const OPERATOR_SCALE = "meso";

const MODELS = [
  { name: "nano_batch_material_response", scale: "nano",
    path: "data/glass_furnace_cascade/nano_batch_material_response.json" },
  { name: "macro_furnace_response", scale: "macro",
    path: "data/glass_furnace_cascade/macro_furnace_response.json" }
];
for (const kind of [KIND_BATCH, KIND_MELT, KIND_GLASS]) {
  MODELS.push({
    name: "thermal_" + kind, scale: OPERATOR_SCALE, operator_role: "thermal_state",
    element_kind: kind, required_context_keys: ["melt_onset_k"],
    path: OPERATOR_DIR + "/thermal_" + kind + ".json"
  });
}
for (const kind of [KIND_BATCH, KIND_MELT]) {
  MODELS.push({
    name: "chemistry_" + kind, scale: OPERATOR_SCALE, operator_role: "batch_chemistry",
    element_kind: kind,
    required_context_keys: kind === KIND_MELT ? ["fusion_onset_k"] : ["calcination_onset_k"],
    path: OPERATOR_DIR + "/chemistry_" + kind + ".json"
  });
}
for (const pair of [[KIND_BATCH, KIND_BATCH], [KIND_BATCH, KIND_MELT], [KIND_BATCH, KIND_GLASS],
                    [KIND_MELT, KIND_MELT], [KIND_GLASS, KIND_MELT], [KIND_GLASS, KIND_GLASS]]) {
  const kind = pair.slice().sort().join("|");
  MODELS.push({
    name: "conduction_" + pair[0] + "_" + pair[1], scale: OPERATOR_SCALE,
    operator_role: "cell_conduction", element_kind: kind,
    required_context_keys: ["conduction_coefficient"],
    path: REFERENCE_DIR + "/conduction_" + pair[0] + "__" + pair[1] + ".json"
  });
}
if (emitTrainingRows) {
  // Teacher models for the harvest only: no operator role, so contextual
  // selection never confuses them with the active family.
  for (const kind of [KIND_BATCH, KIND_MELT, KIND_GLASS]) {
    MODELS.push({ name: "reference_thermal_" + kind,
                  path: REFERENCE_DIR + "/thermal_" + kind + ".json" });
  }
  for (const kind of [KIND_BATCH, KIND_MELT]) {
    MODELS.push({ name: "reference_chemistry_" + kind,
                  path: REFERENCE_DIR + "/chemistry_" + kind + ".json" });
  }
}

globalThis.TRECH_CONFIG = {
  detector: {
    worldSizeMm: 600.0,
    worldMaterial: AIR,
    temperatureK: ambientTemperatureK,
    pressureAtm: 1.0
  },
  beam: { particle: "geantino", energyMeV: 0.0, direction: [0, 1, 0] },
  run: { nEvents: TICKS, seed: 20260815, threads: 1 },
  determinism: { mode: "predictive" },
  precision: PRECISION.config,
  materials: batchMaterials,
  materialProbe: { enable: true, materials: [SAND, SODA, LIME, GLASS, CRUCIBLE] },
  models: MODELS,
  system: { enable: true, mode: "transient", frame: "observer", ensemble: "glass_furnace" },
  hooks: { maxStepCallbacks: 1, maxEmitsPerCallback: 8, maxEmitPayloadBytes: 524288 },
  viz: { enable: true, maxTrajectories: 0, sampleEveryNth: 1,
         maxSegmentsPerTrajectory: 16, includeNonOptical: false, recordVertices: true },
  geometry: {
    volumes: [
      geometry.boxVolume({
        name: "crucible", material: CRUCIBLE,
        sizeMm: [CRUCIBLE_WIDTH_MM + 20.0, CHARGE_HEIGHT_MM + 20.0, CRUCIBLE_WIDTH_MM + 20.0],
        parent: "world", positionMm: [0.0, 0.5 * CHARGE_HEIGHT_MM, 0.0],
        tags: ["viz_shell"]
      }),
      geometry.boxVolume({
        name: "charge", material: SAND,
        sizeMm: [CRUCIBLE_WIDTH_MM, CHARGE_HEIGHT_MM, CRUCIBLE_WIDTH_MM],
        parent: "world", positionMm: [0.0, 0.5 * CHARGE_HEIGHT_MM, 0.0],
        scoreEdep: true, tags: ["viz_hidden"]
      })
    ]
  }
};
