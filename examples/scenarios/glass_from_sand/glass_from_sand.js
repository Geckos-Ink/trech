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
//   set network      : opt-in (`conduction_source=set_network`): the SAME
//                      conduction learned per cell as a DeepSets model over the
//                      cell's face-neighbour SET (generic_surrogate_v3, one per
//                      cell material, trained on the pair operator's rows), so
//                      the neighbour order is irrelevant by construction.
//
// Honest scope: Geant4 supplies the material base, the per-tick clock and the
// transported energy; it does not compute glass chemistry. The committed models
// under data/glass_furnace_* are hand-authored ILLUSTRATIVE maps (measured:false,
// no held-out accuracy) — this scenario demonstrates the mechanism and the
// per-material selection, not glass-making metrology. Cell heat capacities are
// assumed equal, which is what lets conduction be exactly equal-and-opposite.

TRECH_INCLUDE("../../../js/trech_helpers.js");
TRECH_INCLUDE("../../../js/trech_domain_learning.js");
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

const precisionProfile = TRECH_PARAMETER("precision_profile");
const cellsPerSide = TRECH_PARAMETER("cells_per_side");
const simulationTicks = TRECH_PARAMETER("simulation_ticks");
const subStepsPerTick = TRECH_PARAMETER("sub_steps_per_tick");
const furnaceTemperatureK = TRECH_PARAMETER("furnace_temperature_k");
const ambientTemperatureK = TRECH_PARAMETER("ambient_temperature_k");
// Which operator models the normal path runs. `reference` is the original
// hand-authored illustrative map family, kept as the audit/harvest teacher;
// `operator` is the distilled trained family that carries a measured input
// hull, a trained scale band and independent held-out accuracy.
const physicsSource = TRECH_PARAMETER("physics_source");
const operatorCheckpoints = TRECH_PARAMETER("operator_checkpoints");
const emitTrainingRows = TRECH_PARAMETER("emit_training_rows");
const detectDomains = TRECH_PARAMETER("detect_domains");
// Online response-domain learning of the thermal law (ctx.learnDomains):
// `learn` grades it beside the operators, `deploy` lets a frozen learner drive
// the thermal update with the declared operator as a shadow.
const learnDomains = TRECH_PARAMETER("learn_domains");
const domainLearnerModel = TRECH_PARAMETER("domain_learner_model");
const LEARNER_STATE = domainLearnerModel
  ? TRECH_READ_JSON(domainLearnerModel.startsWith("/") ? domainLearnerModel : "../../../" + domainLearnerModel)
  : null;
if ((learnDomains === "deploy" || learnDomains === "evaluate") && !LEARNER_STATE) {
  throw new Error("learn_domains=" + learnDomains + " needs domain_learner_model");
}
// `domain` (default) names no material for the per-cell thermal and chemistry operators or
// the pair conduction: the engine routes each cell, and each face-neighbour pair by the
// lo_/hi_ facts of its two cells, by measured training domain (docs/engine/scenario_hooks.md,
// domain routing). `declared` names each cell's and pair's material and is the reference the
// routed grouping is validated against. The opt-in set-network conduction still passes the
// cell materials (its set models carry no routing domain yet; inference roadmap).
const grouping = TRECH_PARAMETER("grouping");
const routeByDomain = grouping === "domain";
// How cell-to-cell conduction is inferred. `pair` (default) runs the per-pair-
// material operators through ctx.interact. `set_network` runs one learned
// permutation-invariant set network per CELL material through ctx.evolve: the
// cell's face neighbours enter as a set of (present, temperature offset,
// material) elements. It is distilled from the pair path, carries fit error and
// is NOT exactly equal-and-opposite -- the summary reports the net heat it
// creates or destroys instead of hiding it.
const conductionSource = TRECH_PARAMETER("conduction_source");
const holdSeconds = TRECH_PARAMETER("hold_seconds");

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
// A 3D charge: SIDE^3 cells (x across, y up from the furnace floor, z in depth).
const CELL_COUNT = SIDE * SIDE * SIDE;
const TICK_INTERVAL_S = holdSeconds / TICKS;
const SUB_STEP_S = TICK_INTERVAL_S / SUB_STEPS;

// --- crucible geometry (an experiment boundary condition, not a law) --------
const CRUCIBLE_WIDTH_MM = 120.0;
const CELL_PITCH_MM = CRUCIBLE_WIDTH_MM / SIDE;
const CHARGE_HEIGHT_MM = CRUCIBLE_WIDTH_MM;

// Allocate whole stoichiometric batches so refining the mesh preserves both
// the recipe in each cell and the total material inventory.
const BALANCED_CELLS = BALANCED_CELLS_PER_SIDE ** 3;
const batchCount = BALANCED_CELLS * 10;
const recipe = {sio2: 6, na2co3: 1, caco3: 1};
const averageBatches = batchCount / CELL_COUNT;
const chargePerCell = Object.fromEntries(Object.entries(recipe)
  .map(([species, units]) => [species, units * averageBatches]));

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
const KIND_COLOR = TRECH_VIEWS["glass_from_sand"]["KIND_COLOR0"](KIND_BATCH, KIND_GLASS, KIND_MELT);

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
  // Domain grouping bookkeeping (grouping = "domain" only): how the engine's
  // unnamed routing compares with the scenario's own classifier.
  pairRouting: { calls: 0, pairs: 0, agree: 0, disagree: 0, nearest: 0, uncovered: 0, disagreements: {} },
  routing: { calls: 0, elements: 0, agree: 0, disagree: 0, nearest: 0, uncovered: 0,
             groups: {}, disagreements: {}, examples: [] },
  harvest: { thermal: {}, chemistry: {}, conduction: {}, pairs: {} },
  // set_network conduction bookkeeping (stays zero on the pair path).
  conductionSet: {
    evaluations: 0, outOfDomain: 0, kinds: {}, stages: 0, domainMeasured: true,
    holdoutR2: null, netHeatKCells: 0.0, movedHeatKCells: 0.0, maxStepNetKCells: 0.0
  },
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
  // ctx.learnDomains bookkeeping (learn_domains != off).
  learning: null,
  shadow: { calls: 0, elements: 0, sq: { temperature_k: 0, melt_fraction: 0 }, maxAbs: { temperature_k: 0, melt_fraction: 0 },
            signed: {}, phases: [], byDomain: {},
            untouched: 0, extrapolated: 0 },
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

// Fraction of the cell's silica already bound in the glass product. It is
// inventory bookkeeping (a count ratio), not a law; the classifier below
// thresholds it, and domain routing reads it as a routing feature.
function glassSilicaFraction(cells, i) {
  const convertedSilica = cells.glass[i] * 6;
  const silica = cells.sio2[i] + convertedSilica;
  return silica > 0 ? convertedSilica / silica : 0.0;
}

function glassSilicaFractions(cells) {
  const out = new Float64Array(CELL_COUNT);
  for (let i = 0; i < CELL_COUNT; ++i) out[i] = glassSilicaFraction(cells, i);
  return out;
}

// The scenario's material classifier for one cell's CURRENT state.
function kindOf(cells, i) {
  const convertedSilica = cells.glass[i] * 6;
  const silica = cells.sio2[i] + convertedSilica;
  const mostlyGlass = convertedSilica >= 0.85 * silica && cells.glass[i] > 0;
  if (mostlyGlass) return KIND_GLASS;
  return cells.melt_fraction[i] >= 0.5 ? KIND_MELT : KIND_BATCH;
}

function classifyCells(cells) {
  const kinds = new Array(CELL_COUNT);
  for (let i = 0; i < CELL_COUNT; ++i) {
    kinds[i] = kindOf(cells, i);
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
    // Face-neighbour table (-x, +x, -y, +y, -z, +z); -1 = no neighbour. It is
    // lattice bookkeeping, the same contacts ctx.interact finds by cutoff.
    neighbours: new Int32Array(CELL_COUNT * NEIGHBOUR_SLOTS).fill(-1),
    kind: new Array(CELL_COUNT).fill(KIND_BATCH),
    ids: new Array(CELL_COUNT)
  };
  for (const species of SPECIES) {
    cells[species] = new Array(CELL_COUNT).fill(0);
  }
  for (let layer = 0; layer < SIDE; ++layer) {
   for (let row = 0; row < SIDE; ++row) {
    for (let col = 0; col < SIDE; ++col) {
      const i = (layer * SIDE + row) * SIDE + col;
      cells.x[i] = (col + 0.5) * CELL_PITCH_MM - 0.5 * CRUCIBLE_WIDTH_MM;
      cells.y[i] = (row + 0.5) * (CHARGE_HEIGHT_MM / SIDE);
      cells.z[i] = (layer + 0.5) * CELL_PITCH_MM - 0.5 * CRUCIBLE_WIDTH_MM;
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
      const offsets = [[0, 0, -1], [0, 0, 1], [0, -1, 0], [0, 1, 0], [-1, 0, 0], [1, 0, 0]];
      for (let k = 0; k < NEIGHBOUR_SLOTS; ++k) {
        const l = layer + offsets[k][0], r = row + offsets[k][1], c = col + offsets[k][2];
        if (l >= 0 && l < SIDE && r >= 0 && r < SIDE && c >= 0 && c < SIDE) {
          cells.neighbours[i * NEIGHBOUR_SLOTS + k] = (l * SIDE + r) * SIDE + c;
        }
      }
      const batches = Math.floor((i + 1) * batchCount / CELL_COUNT) -
                      Math.floor(i * batchCount / CELL_COUNT);
      for (const [species, units] of Object.entries(recipe)) cells[species][i] = units * batches;
    }
   }
  }
  return cells;
}

// --- the neighbour SET a set-network conduction model reads -----------------
// Element k of cell i is its k-th face neighbour, described by the features
// below (element-major names nb<k>_<feature>, the generic_surrogate_v3 layout).
// The temperature is an OFFSET from the cell's own (a relative coordinate, like
// a message-passing edge feature), and the material is a one-hot identity. An
// absent neighbour (crucible wall) has present = 0 and zeros elsewhere; the
// model's mask drops it. Slot order carries no meaning: the model is permutation
// invariant over the six elements.
const NEIGHBOUR_SLOTS = 6;
const NEIGHBOUR_FEATURES = ["present", "delta_temperature_k", "is_batch_solid", "is_melt", "is_glass"];
const NEIGHBOUR_INPUTS = [];
for (let k = 0; k < NEIGHBOUR_SLOTS; ++k) {
  for (const f of NEIGHBOUR_FEATURES) NEIGHBOUR_INPUTS.push("nb" + k + "_" + f);
}

function neighbourSetFeatures(cells, kinds) {
  const aux = {};
  for (const name of NEIGHBOUR_INPUTS) aux[name] = new Float64Array(CELL_COUNT);
  for (let i = 0; i < CELL_COUNT; ++i) {
    for (let k = 0; k < NEIGHBOUR_SLOTS; ++k) {
      const j = cells.neighbours[i * NEIGHBOUR_SLOTS + k];
      if (j < 0) continue;
      const prefix = "nb" + k + "_";
      aux[prefix + "present"][i] = 1.0;
      aux[prefix + "delta_temperature_k"][i] = cells.temperature_k[j] - cells.temperature_k[i];
      aux[prefix + "is_batch_solid"][i] = kinds[j] === KIND_BATCH ? 1.0 : 0.0;
      aux[prefix + "is_melt"][i] = kinds[j] === KIND_MELT ? 1.0 : 0.0;
      aux[prefix + "is_glass"][i] = kinds[j] === KIND_GLASS ? 1.0 : 0.0;
    }
  }
  return aux;
}

// Harvest sideband for the set network: the neighbour set each sampled cell
// saw and the conduction rate the PAIR operator actually applied to it over the
// sub-step (engine result, not a re-implemented law). A rotating cell offset
// samples every cell over the run.
const CONDUCTION_HARVEST_CELL_STRIDE = 4;
function harvestConductionRows(cells, kinds, features, before, dt, subStep) {
  if (!emitTrainingRows || conductionSource !== "pair" ||
      (subStep % HARVEST_SUBSTEP_STRIDE) !== 0) {
    return;
  }
  const offset = (state.tick * SUB_STEPS + subStep) % CONDUCTION_HARVEST_CELL_STRIDE;
  for (let i = offset; i < CELL_COUNT; i += CONDUCTION_HARVEST_CELL_STRIDE) {
    const row = {};
    for (const name of NEIGHBOUR_INPUTS) row[name] = features[name][i];
    row.temperature_k = before[i];
    row.d_temperature_k_dt = (cells.temperature_k[i] - before[i]) / dt;
    const kind = kinds[i];
    (state.harvest.conduction[kind] = state.harvest.conduction[kind] || []).push(row);
  }
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

// The pair conduction laws, by unordered material pair (model names carry the materials only
// because this scenario declared them that way; routing never reads them).
const CONDUCTION_PAIRS = [[KIND_BATCH, KIND_BATCH], [KIND_BATCH, KIND_MELT], [KIND_BATCH, KIND_GLASS],
                          [KIND_MELT, KIND_MELT], [KIND_GLASS, KIND_MELT], [KIND_GLASS, KIND_GLASS]];
function conductionModelOf(kindA, kindB) {
  const key = [kindA, kindB].sort().join("|");
  const pair = CONDUCTION_PAIRS.find((p) => p.slice().sort().join("|") === key);
  return pair ? "conduction_" + pair[0] + "_" + pair[1] : null;
}

// Pair routing graded the same way: the law the engine routed each canonical pair to,
// against the law the classifier's materials of its two cells would name.
function recordPairRouting(result, kinds) {
  if (!result || !result.routing || !result.pairs) return;
  const routing = state.pairRouting;
  const pathOf = {};
  for (const group of result.routing.groups) pathOf[group.id] = group.path;
  routing.calls += 1;
  for (let p = 0; p < result.pairs.length; ++p) {
    const path = pathOf[result.routing.elementGroups[p]] || [];
    const routed = path.length === 1 ? path[0] : (path.length === 0 ? null : path.join("+"));
    const expected = conductionModelOf(kinds[result.pairs[p][0]], kinds[result.pairs[p][1]]);
    routing.pairs += 1;
    if (routed === expected) { routing.agree += 1; continue; }
    routing.disagree += 1;
    const key = (expected || "(none)") + " -> " + (routed || "(none)");
    routing.disagreements[key] = (routing.disagreements[key] || 0) + 1;
  }
  for (const set of result.routing.sets) {
    routing.nearest += set.elementsNearest;
    routing.uncovered += set.elementsUncovered + set.elementsUnscorable;
  }
}

// Compare the engine's unnamed routing with the scenario's classifier applied to
// the state the call actually saw. Each
// element's group path names the operator that covered it (model names carry the
// material only because this scenario declared them that way); `expectedOf`
// gives the operator the classifier would choose, or null for none.
const ROUTING_EXAMPLES = 8;
function recordRouting(result, prefix, expectedOf, cells) {
  if (!result || !result.routing) return;
  const routing = state.routing;
  const pathOf = {};
  for (const group of result.routing.groups) {
    pathOf[group.id] = group.path;
    routing.groups[group.id] = group.path.join("+") || "(none)";
  }
  routing.calls += 1;
  for (let i = 0; i < result.routing.elementGroups.length; ++i) {
    const path = (pathOf[result.routing.elementGroups[i]] || []).filter((m) => m.indexOf(prefix) === 0);
    const routed = path.length === 1 ? path[0] : (path.length === 0 ? null : path.join("+"));
    routing.elements += 1;
    const expected = expectedOf(kindOf(cells, i));
    if (routed === expected) {
      routing.agree += 1;
      continue;
    }
    routing.disagree += 1;
    const key = (expected || "(none)") + " -> " + (routed || "(none)");
    routing.disagreements[key] = (routing.disagreements[key] || 0) + 1;
    if (routing.examples.length < ROUTING_EXAMPLES) {
      routing.examples.push({ declared: expected, routed, tick: state.tick,
                              melt_fraction: cells.melt_fraction[i],
                              glass_silica_fraction: glassSilicaFraction(cells, i),
                              temperature_k: cells.temperature_k[i] });
    }
  }
  for (const set of result.routing.sets) {
    routing.nearest += set.elementsNearest;
    routing.uncovered += set.elementsUncovered + set.elementsUnscorable;
  }
}

// Deterministic harvest: the TEACHER's exact inputs and outputs for the states
// this run actually visits, sampled on a fixed stride. It calls the reference
// models through ctx.predict — no law is re-implemented here — and every sampled
// prediction is counted like any other inference.
const HARVEST_CELL_STRIDE = 5;
const HARVEST_SUBSTEP_STRIDE = 2;
function harvestTeacherRows(ctx, cells, kinds, subStep, family) {
  if (!emitTrainingRows || (subStep % HARVEST_SUBSTEP_STRIDE) !== 0) return;
  const thermal = family === "thermal";
  for (let i = 0; i < CELL_COUNT; i += HARVEST_CELL_STRIDE) {
    const kind = kinds ? kinds[i] : kindOf(cells, i);
    if (!thermal && kind === KIND_GLASS) continue;
    const inputs = thermal ? {
      temperature_k: cells.temperature_k[i], contact_temperature_k: cells.contact_temperature_k[i],
      melt_onset_k: state.params.melt_onset_k
    } : {
      temperature_k: cells.temperature_k[i], calcination_onset_k: state.params.calcination_onset_k,
      fusion_onset_k: state.params.fusion_onset_k
    };
    state.harvestPredicts += 1;
    const response = ctx.predict("reference_" + family + "_" + kind, inputs);
    if (!response) continue;
    const row = Object.assign({}, inputs, {
      melt_fraction: cells.melt_fraction[i], glass_silica_fraction: glassSilicaFraction(cells, i)
    });
    const outputs = thermal ? ["d_temperature_k_dt", "d_melt_fraction_dt"]
      : ["hazard_soda_calcination", "hazard_lime_calcination", "hazard_glass_fusion"];
    for (const name of outputs) if (response[name] !== undefined) row[name] = response[name];
    const samples = state.harvest[family];
    (samples[kind] = samples[kind] || []).push(row);
  }
}

// Pair-state harvest (routing domains of the pair conduction laws): for face-neighbour pairs
// on a fixed stride, the ordered member facts the engine exposes to an unordered pair
// (lo_/hi_ of melt fraction and converted-silica fraction), keyed by the declared pair
// material. Only the routing domains are measured from these rows; no law is fitted here.
const PAIR_HARVEST_CELL_STRIDE = 7;
function harvestPairStates(cells, kinds, subStep) {
  if (!emitTrainingRows || (subStep % HARVEST_SUBSTEP_STRIDE) !== 0) return;
  const silica = glassSilicaFractions(cells);
  for (let i = 0; i < CELL_COUNT; i += PAIR_HARVEST_CELL_STRIDE) {
    for (let k = 0; k < NEIGHBOUR_SLOTS; ++k) {
      const j = cells.neighbours[i * NEIGHBOUR_SLOTS + k];
      if (j <= i) continue;  // each unordered pair once
      const kind = [kinds[i], kinds[j]].sort().join("|");
      const row = {
        lo_melt_fraction: Math.min(cells.melt_fraction[i], cells.melt_fraction[j]),
        hi_melt_fraction: Math.max(cells.melt_fraction[i], cells.melt_fraction[j]),
        lo_glass_silica_fraction: Math.min(silica[i], silica[j]),
        hi_glass_silica_fraction: Math.max(silica[i], silica[j])
      };
      (state.harvest.pairs[kind] = state.harvest.pairs[kind] || []).push(row);
    }
  }
}

function flushHarvest(ctx) {
  if (!emitTrainingRows) return;
  for (const kind of Object.keys(state.harvest.pairs)) {
    const rows = state.harvest.pairs[kind];
    if (!rows || rows.length === 0) continue;
    state.harvestRows += rows.length;
    ctx.emit("pair_state_sample_" + kind.replace("|", "__"),
             { teacher: "declared pair material (routing-domain measurement only)", samples: rows });
    state.harvest.pairs[kind] = [];
  }
  for (const kind of Object.keys(state.harvest.conduction)) {
    const rows = state.harvest.conduction[kind];
    if (!rows || rows.length === 0) continue;
    state.harvestRows += rows.length;
    ctx.emit("conduction_set_sample_" + kind,
             { teacher: "pair conduction operator (ctx.interact) of this run", samples: rows });
    state.harvest.conduction[kind] = [];
  }
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

// --- online response-domain learning (ctx.learnDomains) ----------------------
// The learner sees what the thermal law could read -- the cell's state at the
// start of the step, its contact temperature and the run's inferred melt onset
// -- and the rate the operator produced. It names no material: domains emerge
// where one law stops explaining the rows. Kinds are only compared afterwards.
const LEARNER_KIND_LABELS = { [KIND_BATCH]: "batch_solid", [KIND_MELT]: "melt", [KIND_GLASS]: "glass" };

function thermalFeatures(start) {
  const onset = new Float64Array(CELL_COUNT).fill(state.params.melt_onset_k);
  return {
    temperature_k: start.temperature_k,
    melt_fraction: start.melt_fraction,
    glass_silica_fraction: glassSilicaFractions(start),
    contact_temperature_k: start.contact_temperature_k,
    melt_onset_k: onset
  };
}

// The operators are time-invariant, so the learner is stationary (no
// forgetting): its reservoirs sample every row it saw, across runs when a
// training campaign warm-starts each run from the previous state.
function learnerOptions(frozen) {
  return LEARNER_STATE ? { warm_start: LEARNER_STATE, frozen } : { frozen, min_elements: 24, forgetting: 1.0 };
}

// Targets are the operator's own rates before integration and bounds
// (ctx.evolve report_rates). A finite difference of the clamped state would
// teach the clamp: a cold batch cell's melt rate is negative and bounded at 0,
// and a learner fed the bounded zero has no restoring law to deploy.
function learnThermal(ctx, rates, start, kinds, dt, subStepIndex) {
  const toArray = (values) => Float64Array.from(values, (v) => (v === null ? NaN : v));
  const dT = toArray(rates.temperature_k), dMelt = toArray(rates.melt_fraction);
  const lastSubStep = subStepIndex === SUB_STEPS - 1;
  const finalCall = lastSubStep && state.tick + 1 >= TICKS;
  const report = ctx.learnDomains({
    name: "furnace_thermal",
    time: state.timeS + (subStepIndex + 1) * dt,
    features: thermalFeatures(start),
    targets: { d_temperature_k_dt: dT, d_melt_fraction_dt: dMelt },
    options: learnerOptions(learnDomains === "evaluate"),
    report: finalCall ? "full" : "summary",
    export_rows: finalCall
  });
  if (!report) return;
  const labels = kinds.map((k) => LEARNER_KIND_LABELS[k]);
  const agreement = TRECH_DOMAIN_LEARNING.agreement(report.elementDomains, labels);
  state.learning = state.learning || TRECH_DOMAIN_LEARNING.accumulator();
  TRECH_DOMAIN_LEARNING.accumulate(state.learning, report, agreement.contingency);
  if (lastSubStep) {
    ctx.emit("domain_learning", TRECH_DOMAIN_LEARNING.summarize(report,
      { scenario: "glass_from_sand", tick: state.tick + 1, mode: learnDomains },
      { labels, allTendencies: finalCall }));
  }
}

// Per cell: does the operator that applies to it rate `field`? Read from the call's own report:
// the routed group path of each cell (domain grouping) or the stage bound to the cell's
// material (declared grouping); a kind-free stage applies to every cell.
function operatorRatesField(report, kinds, field) {
  const mask = new Uint8Array(CELL_COUNT);
  if (!report) return mask;
  const ratesOf = {};
  for (const stage of report.trace || []) {
    ratesOf[stage.model] = (stage.integratedFields || []).indexOf(field) >= 0;
  }
  if (report.routing) {
    const pathOf = {};
    for (const group of report.routing.groups) pathOf[group.id] = group.path;
    // A kind-free stage that belongs to no rival set runs on every cell.
    const rivals = new Set();
    for (const set of report.routing.sets) for (const model of set.models) rivals.add(model);
    for (const stage of report.trace || []) {
      if (!stage.elementKind && ratesOf[stage.model] && !rivals.has(stage.model)) mask.fill(1);
    }
    for (let i = 0; i < CELL_COUNT; ++i) {
      const path = pathOf[report.routing.elementGroups[i]] || [];
      if (path.some((model) => ratesOf[model])) mask[i] = 1;
    }
    return mask;
  }
  for (const stage of report.trace || []) {
    if (!ratesOf[stage.model]) continue;
    for (let i = 0; i < CELL_COUNT; ++i) {
      if (!stage.elementKind || stage.elementKind === kinds[i]) mask[i] = 1;
    }
  }
  return mask;
}

function deployThermal(ctx, cells, start, thermalSpec, dt, subStepIndex) {
  const features = thermalFeatures(start);
  const report = ctx.learnDomains({
    name: "furnace_thermal_deployed",
    time: state.timeS + (subStepIndex + 1) * dt,
    features,
    options: learnerOptions(true)
  });
  if (!report) throw new Error("learn_domains=deploy requires determinism.mode=predictive");
  // Shadow: the thermal operator on a copy, never applied. Under domain grouping the engine
  // routes it like the applied call, so its routing is graded the same way.
  const shadow = { temperature_k: cells.temperature_k.slice(), melt_fraction: cells.melt_fraction.slice() };
  const shadowReport = ctx.evolve(thermalSpec(shadow));
  recordRouting(shadowReport, "thermal_", (kind) => "thermal_" + kind, start);
  // The learner stands in for the thermal operator, so it drives a field only on the cells
  // whose operator rates that field (the glass law rates temperature, never melt fraction).
  const rated = (field) => operatorRatesField(shadowReport, cells.kind, field);
  const applied = TRECH_DOMAIN_LEARNING.applyRates(report, [
    { rate: "d_temperature_k_dt", values: cells.temperature_k, min: 0.0, max: 4000.0,
      mask: rated("temperature_k") },
    { rate: "d_melt_fraction_dt", values: cells.melt_fraction, min: 0.0, max: 1.0,
      mask: rated("melt_fraction") }
  ], dt);
  const s = state.shadow;
  s.calls += 1;
  s.untouched += applied.untouched;
  s.extrapolated += report.extrapolated;
  state.inference.evolve += applied.applied;
  state.inference.outOfDomain += report.extrapolated;
  // Signed per-step error (learner minus operator) by material and by run third: where and
  // when a bias accumulates (reported only).
  const third = Math.min(2, Math.floor(3 * state.tick / TICKS));
  for (let i = 0; i < CELL_COUNT; ++i) {
    const kind = cells.kind[i];
    const bucket = s.signed[kind] = s.signed[kind] || { n: 0, temperature_k: 0, melt_fraction: 0 };
    const phase = s.phases[third] = s.phases[third] || { n: 0, temperature_k: 0 };
    bucket.n += 1; phase.n += 1;
    for (const field of ["temperature_k", "melt_fraction"]) {
      const e = cells[field][i] - shadow[field][i];
      s.sq[field] += e * e;
      s.maxAbs[field] = Math.max(s.maxAbs[field], Math.abs(e));
      bucket[field] += e;
    }
    phase.temperature_k += cells.temperature_k[i] - shadow.temperature_k[i];
    const domain = String((report.predictionDomains || [])[i]);
    const d = s.byDomain[domain] = s.byDomain[domain] || { n: 0, temperature_k: 0, kinds: {} };
    d.n += 1; d.temperature_k += cells.temperature_k[i] - shadow.temperature_k[i];
    d.kinds[kind] = (d.kinds[kind] || 0) + 1;
  }
  s.elements += CELL_COUNT;
  if (subStepIndex === SUB_STEPS - 1) {
    ctx.emit("domain_learning", TRECH_DOMAIN_LEARNING.summarize(report,
      { scenario: "glass_from_sand", tick: state.tick + 1, mode: "deploy" },
      { labels: cells.kind.map((k) => LEARNER_KIND_LABELS[k]), samples: { features, count: 64 } }));
  }
}

function learningSummary() {
  if (learnDomains === "off") return undefined;
  const s = state.shadow;
  return {
    mode: learnDomains,
    note: "Response domains learned online by ctx.learnDomains from the thermal operator's own " +
          "pre-bound rates (ctx.evolve report_rates); no material label is read. learn: prequential " +
          "(predict-then-learn) error against " +
          "a pooled single-domain model fed the same rows. deploy: a frozen learner drives the thermal " +
          "update; the declared operator runs on a copy as a shadow. Agreement compares domains with " +
          "this scenario's classifier afterwards.",
    learner_state: domainLearnerModel || null,
    online: state.learning ? TRECH_DOMAIN_LEARNING.finish(state.learning) : null,
    shadow: learnDomains === "deploy" ? {
      calls: s.calls, element_steps: s.elements, untouched: s.untouched, extrapolated: s.extrapolated,
      rmse: { temperature_k: Math.sqrt(s.sq.temperature_k / Math.max(s.elements, 1)),
              melt_fraction: Math.sqrt(s.sq.melt_fraction / Math.max(s.elements, 1)) },
      max_abs: s.maxAbs,
      mean_signed_error_by_kind: Object.fromEntries(Object.entries(s.signed).map(([k, b]) => [k, {
        element_steps: b.n, temperature_k: b.temperature_k / Math.max(b.n, 1),
        melt_fraction: b.melt_fraction / Math.max(b.n, 1)}])),
      mean_signed_temperature_error_by_third: s.phases.map((p) => p ? p.temperature_k / Math.max(p.n, 1) : null),
      mean_signed_temperature_error_by_domain: Object.fromEntries(Object.entries(s.byDomain).map(([id, d]) => [id, {
        element_steps: d.n, temperature_k: d.temperature_k / Math.max(d.n, 1), kinds: d.kinds}]))
    } : null
  };
}

function advance(ctx, cells, kinds, dt, subStepIndex) {
  const context = Object.assign({}, state.params, {
    heater_temperature_k: furnaceTemperatureK,
    ambient_temperature_k: ambientTemperatureK
  });

  // 1) heat moves between neighbouring cells, through whatever the two cells
  //    are made of RIGHT NOW (six declared material combinations) -- or, on
  //    the set-network path, through each cell's learned neighbour-set model.
  if (conductionSource === "set_network") {
    const before = cells.temperature_k.slice();
    const set = ctx.evolve({
      dt,
      fields: [{ name: "temperature_k", min: 0.0, max: 4000.0 }],
      state: { temperature_k: cells.temperature_k },
      aux: neighbourSetFeatures(cells, kinds),
      context,
      operator_role: "cell_conduction_set",
      element_kind: kinds
    });
    if (set) {
      const book = state.conductionSet;
      book.evaluations += set.inferenceCount;
      book.outOfDomain += set.outOfDomainInferences;
      state.inference.interact += set.inferenceCount;
      state.inference.outOfDomain += set.outOfDomainInferences;
      recordSelection("interact", set);
      for (const stage of set.trace || []) {
        if (!stage.ran || (stage.elementsMatched || 0) === 0) continue;
        book.stages += 1;
        book.kinds[stage.elementKind || "?"] =
          (book.kinds[stage.elementKind || "?"] || 0) + stage.elementsMatched;
        book.domainMeasured = book.domainMeasured && stage.domainMeasured === true;
        if (stage.holdoutR2 !== null && stage.holdoutR2 !== undefined) {
          book.holdoutR2 = book.holdoutR2 === null
            ? stage.holdoutR2 : Math.min(book.holdoutR2, stage.holdoutR2);
        }
      }
      // Equal cell heat capacity: conduction alone must move heat, not create
      // it. The pair path does that exactly; a per-cell learned model does not.
      let net = 0.0, moved = 0.0;
      for (let i = 0; i < CELL_COUNT; ++i) {
        const delta = cells.temperature_k[i] - before[i];
        net += delta;
        moved += Math.abs(delta);
      }
      book.netHeatKCells += net;
      book.movedHeatKCells += moved;
      book.maxStepNetKCells = Math.max(book.maxStepNetKCells, Math.abs(net));
    }
    return advanceLocal(ctx, cells, kinds, dt, context, set, subStepIndex);
  }
  const harvesting = emitTrainingRows && (subStepIndex % HARVEST_SUBSTEP_STRIDE) === 0;
  const pairFeatures = harvesting ? neighbourSetFeatures(cells, kinds) : null;
  const pairBefore = harvesting ? cells.temperature_k.slice() : null;
  // Domain grouping names no material: the engine routes every pair to the conduction law
  // whose measured routing domain (the lo_/hi_ melt and converted-silica fractions of the
  // two members) covers it. Declared grouping names each pair's materials (the reference).
  const conduction = ctx.interact(Object.assign({
    dt,
    cutoff: CELL_PITCH_MM * 1.05,
    fields: [{ name: "temperature_k", symmetry: "antisymmetric", min: 0.0, max: 4000.0 }],
    state: { temperature_k: cells.temperature_k },
    positions: { x: cells.x, y: cells.y, z: cells.z },
    context,
    operator_role: "cell_conduction"
  }, routeByDomain
    ? { aux: { melt_fraction: cells.melt_fraction, glass_silica_fraction: glassSilicaFractions(cells) } }
    : { element_kind: kinds }));
  if (harvesting) {
    harvestConductionRows(cells, kinds, pairFeatures, pairBefore, dt, subStepIndex);
    harvestPairStates(cells, kinds, subStepIndex);
  }
  if (conduction) {
    state.inference.interact += conduction.inferenceCount;
    state.inference.outOfDomain += conduction.outOfDomainInferences;
    recordSelection("interact", conduction);
    recordPairRouting(conduction, kinds);
    for (const stage of conduction.trace || []) {
      if (stage.ran && stage.pairsMatched > 0) {
        // Declared grouping keys by the pair material; routed pairs name none, so the pair
        // law the engine routed to stands in.
        const key = stage.pairKind || stage.model;
        state.pairKindsRun[key] = (state.pairKindsRun[key] || 0) + stage.pairsMatched;
      }
    }
  }

  return advanceLocal(ctx, cells, kinds, dt, context, conduction, subStepIndex);
}

// Steps 2-3 (per-cell thermal state and chemistry) are shared by both
// conduction paths.
function advanceLocal(ctx, cells, kinds, dt, context, conduction, subStepIndex) {
  // 2) each cell heats and melts through the operator its own material selected.
  const sampleDomains = detectDomains && subStepIndex === SUB_STEPS - 1;
  const learning = learnDomains !== "off";
  const thermalStart = routeByDomain || sampleDomains || learning
    ? { glass: cells.glass.slice(), sio2: cells.sio2.slice(), melt_fraction: cells.melt_fraction.slice(),
        temperature_k: cells.temperature_k.slice(), contact_temperature_k: cells.contact_temperature_k.slice() }
    : null;
  harvestTeacherRows(ctx, cells, kinds, subStepIndex, "thermal");
  const thermalSpec = (target) => ({
    dt,
    fields: [
      { name: "temperature_k", min: 0.0, max: 4000.0 },
      { name: "melt_fraction", min: 0.0, max: 1.0 }
    ],
    state: target,
    aux: routeByDomain
      ? { contact_temperature_k: cells.contact_temperature_k,
          glass_silica_fraction: glassSilicaFractions(cells) }
      : { contact_temperature_k: cells.contact_temperature_k },
    context,
    operator_role: "thermal_state",
    element_kind: routeByDomain ? undefined : kinds,
    // The learner learns the operator's law, not the integrator's bounds.
    report_rates: learning
  });
  let thermal = null;
  if (learnDomains === "deploy") {
    deployThermal(ctx, cells, thermalStart, thermalSpec, dt, subStepIndex);
  } else {
    thermal = ctx.evolve(thermalSpec({ temperature_k: cells.temperature_k, melt_fraction: cells.melt_fraction }));
    if (learning && thermal) learnThermal(ctx, thermal.rates, thermalStart, kinds, dt, subStepIndex);
  }
  if (thermal && routeByDomain) {
    // Evaluated after the call: compare with the state it started from.
    recordRouting(thermal, "thermal_", (kind) => "thermal_" + kind, thermalStart);
  }
  if (sampleDomains) {
    const features = {
      temperature_k: thermalStart.temperature_k,
      melt_fraction: thermalStart.melt_fraction,
      glass_silica_fraction: glassSilicaFractions(thermalStart)
    };
    const parents = thermal && thermal.routing ? thermal.routing.elementGroups : undefined;
    const report = ctx.detectDomains({ features, parent_groups: parents });
    if (report) ctx.emit("domain_discovery", {
      frame: state.tick + 1, parents,
      features: Object.fromEntries(Object.entries(features).map(([name, values]) => [name, Array.from(values)])),
      report
    });
  }
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
  const chemistryStart = routeByDomain
    ? { glass: cells.glass.slice(), sio2: cells.sio2.slice(), melt_fraction: cells.melt_fraction.slice(),
        temperature_k: cells.temperature_k.slice() }
    : null;
  // Thermal inference can cross the melt boundary within this substep.
  const chemistryKinds = routeByDomain ? undefined : kinds.map((_, i) => kindOf(cells, i));
  harvestTeacherRows(ctx, cells, chemistryKinds, subStepIndex, "chemistry");
  const reaction = ctx.react({
    dt,
    species: SPECIES,
    state: {
      sio2: cells.sio2, na2co3: cells.na2co3, caco3: cells.caco3,
      na2o: cells.na2o, cao: cells.cao, co2: cells.co2, glass: cells.glass
    },
    aux: routeByDomain
      ? { temperature_k: cells.temperature_k, melt_fraction: cells.melt_fraction,
          glass_silica_fraction: glassSilicaFractions(cells) }
      : { temperature_k: cells.temperature_k, melt_fraction: cells.melt_fraction },
    context,
    channels: CHANNELS,
    conservation: CONSERVATION,
    operator_role: "batch_chemistry",
    element_kind: chemistryKinds
  });
  if (reaction && routeByDomain) {
    recordRouting(reaction, "chemistry_",
                  (kind) => (kind === KIND_GLASS ? null : "chemistry_" + kind), chemistryStart);
    // A cell no chemistry law covers is the routed form of "unclaimed".
    for (const set of (reaction.routing && reaction.routing.sets) || []) {
      state.unclaimedGlassCells += set.elementsUncovered + set.elementsUnscorable;
    }
  }
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

// --- Validation observer ---------------------------------------------------------------
// At each tick the furnace hands its observed state to its validation companion, which may
// grade engine methods against it (glass_from_sand.validation.js). Nothing returned feeds back.
function observeValidationFrame(ctx, cells, final) {
  TRECH_CHECKS["glass_from_sand"].observeFrame(ctx, {
    cells, final, tick: state.tick, timeS: state.timeS, params: state.params,
    geometry: {cellCount: CELL_COUNT, side: SIDE, cellPitchMm: CELL_PITCH_MM,
      crucibleWidthMm: CRUCIBLE_WIDTH_MM, chargeHeightMm: CHARGE_HEIGHT_MM},
    conditions: {furnaceTemperatureK, ambientTemperatureK}});
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
        charge_per_cell: chargePerCell,
        charge_total: Number.isInteger(averageBatches) ? undefined : Object.fromEntries(
          Object.keys(recipe).map(species => [species, state.cells[species].reduce((sum, n) => sum + n, 0)])),
        cells: CELL_COUNT,
        channels: CHANNELS.map((c) => c.name),
        conserved: CONSERVATION.map((c) => c.name),
        precision: { profile: PRECISION.profile, axes: PRECISION.axes }
      });
    }

    const cells = state.cells;
    if (state.tick === 0) observeValidationFrame(ctx, cells, false);
    for (let s = 0; s < SUB_STEPS; ++s) {
      refreshContacts(cells);
      const kinds = cells.kind.slice();
      advance(ctx, cells, kinds, SUB_STEP_S, s);
      classifyCells(cells);
    }
    flushHarvest(ctx);
    state.tick += 1;
    state.timeS += TICK_INTERVAL_S;
    observeValidationFrame(ctx, cells, state.tick >= TICKS);

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
    ctx.emit("material_frame", TRECH_VIEWS["glass_from_sand"]["frame0"](CELL_PITCH_MM, CHARGE_HEIGHT_MM, CRUCIBLE_WIDTH_MM, KIND_BATCH, KIND_COLOR, KIND_GLASS, KIND_MELT, SIDE, cells, colors, positions, state, summary));

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
      const validation = TRECH_CHECKS["glass_from_sand"]["expectations0"](CHARGE_HEIGHT_MM, KIND_MELT, allConserved, materialKinds, pairKinds, state, summary, totalInferences, conductionSource);
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
        domain_learning: learningSummary(),
        domain_routing: routeByDomain ? {
          grouping: "domain",
          note: "thermal_state and batch_chemistry name no material: the engine routed each " +
                "cell by the operators' measured training domains (inputs + routing_domain). " +
                "Agreement is against this scenario's own threshold classifier.",
          calls: state.routing.calls,
          element_evaluations: state.routing.elements,
          agree: state.routing.agree,
          disagree: state.routing.disagree,
          agreement: state.routing.elements > 0
            ? round4(state.routing.agree / state.routing.elements) : null,
          disagreements: state.routing.disagreements,
          disagreement_examples: state.routing.examples,
          nearest_in_gap: state.routing.nearest,
          left_untouched: state.routing.uncovered,
          groups: state.routing.groups,
          // cell_conduction names no material either: each face-neighbour pair is routed by
          // the lo_/hi_ melt and converted-silica fractions of its two cells.
          pair_routing: state.pairRouting.calls > 0 ? {
            calls: state.pairRouting.calls,
            pair_evaluations: state.pairRouting.pairs,
            agree: state.pairRouting.agree,
            disagree: state.pairRouting.disagree,
            agreement: state.pairRouting.pairs > 0
              ? round4(state.pairRouting.agree / state.pairRouting.pairs) : null,
            disagreements: state.pairRouting.disagreements,
            nearest_in_gap: state.pairRouting.nearest,
            left_untouched: state.pairRouting.uncovered
          } : undefined
        } : undefined,
        conduction: conductionSource === "set_network" ? {
          source: "set_network",
          models: "per-cell-material DeepSets set networks (generic_surrogate_v3) under " +
                  CONDUCTION_SET_DIR + "/, distilled from the pair conduction operator",
          measured: false,
          cell_kind_evaluations: state.conductionSet.kinds,
          inferences: state.conductionSet.evaluations,
          out_of_domain: state.conductionSet.outOfDomain,
          domain_measured: state.conductionSet.stages > 0 ? state.conductionSet.domainMeasured : null,
          holdout_r2_min: state.conductionSet.holdoutR2,
          // Conduction must move heat, not create it (equal heat capacities).
          // The pair path is exact; this is the learned path's departure.
          net_heat_k_cells: state.conductionSet.netHeatKCells,
          moved_heat_k_cells: state.conductionSet.movedHeatKCells,
          net_to_moved_ratio: state.conductionSet.movedHeatKCells > 0
            ? Math.abs(state.conductionSet.netHeatKCells) / state.conductionSet.movedHeatKCells : 0.0,
          max_step_net_k_cells: state.conductionSet.maxStepNetKCells
        } : { source: "pair", exact_equal_and_opposite: true },
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
          comparison_key: Object.assign({
            seed: Number(ctx.runtime.seed),
            conduction_source: conductionSource,
            furnace_temperature_k: furnaceTemperatureK,
            ambient_temperature_k: ambientTemperatureK,
            hold_s: holdSeconds,
            cells: CELL_COUNT,
            sub_steps_per_tick: SUB_STEPS,
            geant4_ticks: TICKS
          }, routeByDomain ? { grouping: "domain" } : {}),
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
  ? (operatorCheckpoints || "data/glass_furnace_operators_trained")
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
    element_kind: routeByDomain ? undefined : kind, required_context_keys: ["melt_onset_k"],
    path: OPERATOR_DIR + "/thermal_" + kind + ".json"
  });
}
for (const kind of [KIND_BATCH, KIND_MELT]) {
  MODELS.push({
    name: "chemistry_" + kind, scale: OPERATOR_SCALE, operator_role: "batch_chemistry",
    element_kind: routeByDomain ? undefined : kind,
    required_context_keys: kind === KIND_MELT ? ["fusion_onset_k"] : ["calcination_onset_k"],
    path: OPERATOR_DIR + "/chemistry_" + kind + ".json"
  });
}
// Set-network conduction (opt-in): one DeepSets model per CELL material over
// the neighbour set, distilled from the pair path below. Declared instead of the
// pair maps, so exactly one conduction family runs.
const CONDUCTION_SET_DIR = "data/glass_furnace_conduction_set";
if (conductionSource === "set_network") {
  for (const kind of [KIND_BATCH, KIND_MELT, KIND_GLASS]) {
    MODELS.push({
      name: "conduction_set_" + kind, scale: OPERATOR_SCALE,
      operator_role: "cell_conduction_set", element_kind: kind,
      path: CONDUCTION_SET_DIR + "/conduction_set_" + kind + ".json"
    });
  }
}
for (const pair of (conductionSource === "set_network" ? [] : CONDUCTION_PAIRS)) {
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
  environment: {
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
  // The harvest sideband adds up to three conduction-set and six pair-state emits per tick.
  hooks: { maxStepCallbacks: 1, maxEmitsPerCallback: emitTrainingRows ? 18 : 8,
           // The final learner state carries its reservoir rows (tens of MB).
           maxEmitPayloadBytes: learnDomains === "off" ? 524288 : 268435456 },
  viz: TRECH_VIEWS["glass_from_sand"]["viz1"](),
  geometry: {
    volumes: [
      geometry.boxVolume({
        name: "crucible", material: CRUCIBLE,
        sizeMm: [CRUCIBLE_WIDTH_MM + 20.0, CHARGE_HEIGHT_MM + 20.0, CRUCIBLE_WIDTH_MM + 20.0],
        parent: "world", positionMm: [0.0, 0.5 * CHARGE_HEIGHT_MM, 0.0],
        tags: TRECH_VIEWS["glass_from_sand"]["tags2"]()
      }),
      // The charge sits inside the crucible (10 mm refractory wall all round).
      // As a world sibling at the same position it overlapped the crucible,
      // which Geant4 navigates ambiguously.
      geometry.boxVolume({
        name: "charge", material: SAND,
        sizeMm: [CRUCIBLE_WIDTH_MM, CHARGE_HEIGHT_MM, CRUCIBLE_WIDTH_MM],
        parent: "crucible", positionMm: [0.0, 0.0, 0.0],
        scoreEdep: true, tags: TRECH_VIEWS["glass_from_sand"]["tags3"]()
      })
    ]
  }
};
