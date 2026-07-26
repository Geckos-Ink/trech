// The polyurethane foam experiment ("the solid sponge"), observed in an open cup.
//
// Two viscous liquids are poured together:
//   Solution A ... a polyol (multiple -OH groups) carrying a small amount of WATER
//                  plus amine catalyst and silicone surfactant
//   Solution B ... a diisocyanate (two -NCO groups)
// Within seconds the mixture creams, expands up to ~30x its volume, and cures into
// a rigid porous sponge. Two reactions run SIMULTANEOUSLY:
//   polymerization (gel):  R-N=C=O + R'-OH  -> R-NH-CO-O-R'   (urethane linkage)
//   blowing        (blow): R-N=C=O + H2O    -> R-NH2 + CO2^   (gas generation)
// TRECH is told ONLY what is in the cup (the two-solution recipe + the constructed
// Geant4 materials). It is NOT told the expansion ratio, the cream/rise/gel times,
// the exotherm, the colour, that the result is a rigid solid, that the rising bun
// leans, or that overhanging pieces crack off and fall to the table. All of that
// must EMERGE.
//
// Information discipline (the TRECH thesis, applied to a curing foam):
//   * Geant4 is the physical base. G4-constructed solution/mixture materials supply
//     composition, density, and electron/atom densities (Geant4 literally "sees"
//     the isocyanate nitrogen dissolved in Solution B and the density contrast
//     between the two solutions) plus the cross sections behind TRECH's derived
//     colour for the mixed liquid resin.
//   * ctx.cascade lifts those Geant4 facts + the declared recipe through a nano
//     reagent-descriptor stage and a macro observer-band response surface into the
//     COEFFICIENTS of (a) a reduced dual-reaction foaming model and (b) the
//     MECHANICS of the foam it builds: bond stiffness, failure strain, stress
//     relaxation, structural damping, contact friction/restitution, and the
//     magnitude of the cell-scale IMPERFECTION. The cascade emits NO expansion
//     ratio, milestone time, colour, lean angle, crack, or fragment count.
//   * Every parcel carries its own chemistry -- temperature, urethane conversion,
//     water conversion, dissolved/trapped CO2 -- with heat diffusing along the
//     bond network and leaking to the room from the free surface, so a hot core
//     and a cooler skin arise on their own. A deterministic per-parcel
//     imperfection field (magnitude inferred, pattern reproducible) makes no two
//     cells identical, exactly as a hand-mixed foam is not.
//   * The material is a GROWING VISCOELASTIC BOND NETWORK under standard gravity
//     (see trech_foam_solver.js): rest lengths grow with each parcel's own gas
//     generation, creep away stress while the resin is still fluid, lock as it
//     cures, and BREAK when strain passes the inferred failure strain. So whether
//     the bun leans, which way it leans, whether an overhang cracks off, how many
//     pieces detach, where they fall and how they pile on the table are all
//     consequences of gravity acting on an imperfect network -- never scheduled.
//   * Honest scope: Geant4 does not itself solve urethane reaction kinetics, bubble
//     rheology, or continuum mechanics; the reduced foaming model and the bonded
//     parcel solver are explicit "physics for comparison" hook-layer models whose
//     coefficients are inferred from the Geant4 base. Standard gravity is used as a
//     physical constant (like the gyromagnetic ratio in the MRI track), not as a
//     fitted behaviour. The compact macro response surface is illustrative
//     (uncertainty sigma emitted). The cream/tan display swatches are labelled
//     representation (the aromatic-urethane chromophore is not a Geant4
//     cross-section product); the liquid base colour IS Geant4-derived, and the
//     whitening as bubbles nucleate is tied to the emergent gas fraction -- its
//     TIMING is the emergent, graded result.
//   * PubChem supplies structure identity ONLY (CID + SMILES + formula) for the
//     reagents; those element sets are cross-checked against the declared Geant4
//     composition at run end. No PubChem density/colour/viscosity feeds runtime.
//
// The known polyurethane-foam behaviour used to CHECK the result (never to drive
// it) lives in VALIDATION_ONLY and is read only at run end.
//
// Run (PubChem structure cache first, once):
//   PYTHONPATH=tools/pubchem python -m trech_pubchem fetch --cache-dir build/pubchem_cache \
//     glycerol "toluene 2,4-diisocyanate" water
//   TRECH_PUBCHEM_CACHE_DIR=build/pubchem_cache build/dev/trech run \
//     examples/experiments/polyurethane_foam.js --output build/dev/out_polyurethane_foam
// Zero-gravity control (proves gravity causes the lean/sag/fall):
//   ... --param gravity_scale=0 --output build/dev/out_polyurethane_foam_zero_g

TRECH_INCLUDE("trech_helpers.js");
TRECH_INCLUDE("trech_foam_solver.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) throw new Error("TRECH_HELPERS not available");
const FOAM = globalThis.TRECH_FOAM;
if (!FOAM) throw new Error("TRECH_FOAM solver not available");
const geometry = helpers.geometry;

const WATER = "G4_WATER";
const AIR = "G4_AIR";
const CUP = "G4_POLYSTYRENE";
const POLYOL_SOLUTION = "polyol_resin_solution";        // Solution A
const ISOCYANATE_SOLUTION = "diisocyanate_solution";    // Solution B
const RESIN_MIX = "polyurethane_resin_mix";             // A + B, freshly mixed

// The prepared two-part recipe (what a demonstrator pours). Declared formulation
// context -- the "known solutions in a cup" -- NOT the reaction result.
const RECIPE = {
  polyolHydroxylNumberMgKohG: 400.0,  // rigid-foam polyether polyol
  waterPartsPerHundredPolyol: 3.5,    // the blowing agent dissolved in Solution A
  isocyanateIndex: 1.10,              // 10% NCO excess over all active hydrogens
  amineCatalystPphp: 1.5,
  surfactantPphp: 1.5,                // silicone cell stabiliser
  pourMassG: 101.0,                   // A + B combined (88 cm3 of 1.15 g/cm3 resin)
  mixRatioAtoB: 1.0
};

const durationS = TRECH_VALUE.number("duration_s", {
  label: "Physical duration", group: "Time", unit: "s",
  description: "How long the same stateful foaming + mechanics solver advances.",
  default: 180.0, min: 60.0, max: 900.0, step: 30.0
});
const playbackDurationS = TRECH_VALUE.number("playback_duration_s", {
  label: "Playback duration", group: "Time", unit: "s",
  description: "Display time paired with the retained physical clock.",
  default: 12.0, min: 1.0, max: 60.0, step: 1.0
});
const simulationTicks = TRECH_VALUE.integer("simulation_ticks", {
  label: "Output / Geant4 ticks", group: "Precision", unit: "ticks",
  description: "Geant4 events and emitted states; physics uses bounded finer steps.",
  default: 216, min: 20, max: 1000, step: 12
});
const foamParcels = TRECH_VALUE.integer("foam_parcels", {
  label: "Persistent foam parcels", group: "Precision", unit: "parcels",
  description: "Spatial resolution of the bonded network; the poured volume stays fixed.",
  default: 620, min: 200, max: 1400, step: 20
});
const maxPhysicsStepS = TRECH_VALUE.number("max_physics_step_s", {
  label: "Maximum physics step", group: "Precision", unit: "s",
  description: "Temporal resolution of the reaction + mechanics integrator.",
  default: 0.04, min: 0.005, max: 0.2, step: 0.005
});
const constraintIterations = TRECH_VALUE.integer("constraint_iterations", {
  label: "Constraint iterations", group: "Precision", unit: "iterations",
  description: "Network stiffness convergence per physics step.",
  default: 3, min: 1, max: 12, step: 1
});
const fragmentSubsteps = TRECH_VALUE.integer("fragment_substeps", {
  label: "Fragment substeps", group: "Precision", unit: "substeps",
  description: "Ballistic resolution for detached pieces inside one network step.",
  default: 6, min: 1, max: 32, step: 1
});
const renderSurfaceGridMm = TRECH_VALUE.number("render_surface_grid_mm", {
  label: "Foam surface grid", group: "Representation", unit: "mm",
  description: "Metaball display precision only; changes no simulated state.",
  default: 2.0, min: 1.0, max: 6.0, step: 0.25
});
const initialTemperatureK = TRECH_VALUE.number("initial_temperature_k", {
  label: "Initial temperature", group: "Conditions", unit: "K",
  description: "Both solutions and the ambient start here.",
  default: 296.15, min: 285.0, max: 310.0, step: 1.0
});
// Where the per-parcel chemistry comes from. "reference" is the reduced law
// written out in this file; "operator" hands the state to the engine and lets a
// trained scale-tagged model drive it through ctx.evolve, so no reaction rate
// law is authored here at all. The operator is the default after passing its
// independent holdout, full-size paired observer-gap gate, and nominal/zero-g
// mechanics controls; reference remains available as teacher/audit fallback.
const chemistrySource = TRECH_VALUE.choice("chemistry_source", {
  label: "Chemistry source", group: "Inference",
  description: "reference = the reduced law authored in this scenario; operator = the engine infers the per-parcel chemistry from a trained model (ctx.evolve).",
  choices: ["reference", "operator"], default: "operator"
});
const emitOperatorSamples = TRECH_VALUE.boolean("emit_operator_samples", {
  label: "Emit operator training samples", group: "Inference",
  description: "Deterministically sample (parcel state -> observed rate) rows from the reference law for harvesting; sideband only, changes no physics.",
  default: false
});
const gravityScale = TRECH_VALUE.number("gravity_scale", {
  label: "Gravity scale", group: "Conditions", unit: "x g",
  description: "Multiplies standard gravity; 0 is the free-fall control that must remove the lean, the sag and every fallen piece.",
  default: 1.0, min: 0.0, max: 2.0, step: 0.1
});

const APPARATUS = {
  durationS,
  playbackDurationS,
  outputTicks: simulationTicks,
  outputTickIntervalS: durationS / simulationTicks,
  physicsStepS: maxPhysicsStepS,
  constraintIterations,
  fragmentSubsteps,
  // A tall, narrow cup: the same poured volume rises as a slender bun rather than
  // a squat mushroom, which is the shape whose own weight can actually bend it.
  cupInnerRadiusMm: 24.5,
  cupHeightMm: 116.0,
  tableRadiusMm: 165.0,
  initialLiquidHeightMm: 58.0,
  initialTemperatureK,
  parcels: foamParcels,
  renderSurfaceGridMm,
  gravityScale
};

// ---- representation-only display swatches (labelled; never feed dynamics) ----
const REPRESENTATION = {
  policy: "cream/tan swatches are authored display; liquid base is Geant4-derived; whitening/tanning TIMING is emergent",
  creamTint: [0.95, 0.90, 0.78],
  curedTint: [0.88, 0.77, 0.55],
  liquidAlpha: 0.85,
  foamAlpha: 0.96,
  scatterGain: 2.2
};

const PARCEL_R_MM = APPARATUS.cupInnerRadiusMm - 2.5;   // liquid pool radius
const POOL_VOLUME_MM3 = Math.PI * PARCEL_R_MM * PARCEL_R_MM *
  APPARATUS.initialLiquidHeightMm;
const RENDER_ISO_LEVEL = 0.42;
const RENDER_SIGMA_PER_SPACING = 0.72;

// The declared model that carries the per-parcel chemistry when
// chemistry_source=operator. It rides the ordinary `models:` surface, so the
// engine loads and scale-orders it exactly like any cascade stage.
const OPERATOR_MODEL = "meso_reaction_operator";
const OPERATOR_ROLE = "reaction_state";
const OPERATOR_ELEMENT_KIND = "foam_parcel";
const OPERATOR_REQUIRED_CONTEXT = [
  "gel_rate_per_s", "blow_rate_per_s", "activation_temperature_k",
  "gel_exotherm_k", "blow_exotherm_k", "heat_loss_per_s",
  "co2_expansion_capacity", "co2_saturation_fraction",
  "gel_point_conversion", "viscosity_growth_exponent",
  "bubble_trap_base", "expansion_mobility_per_s", "autocatalysis_gain",
  "solid_conversion", "nco_share", "initial_temperature_k"
];
// Deterministic harvest stride: every Nth physics step, every Mth parcel. Fixed
// numbers (not sampled), so a harvest run is reproducible and its row count is
// a property of the run, not of chance.
const SAMPLE_EVERY_STEPS = 10;
const SAMPLE_EVERY_PARCELS = 10;
// Promotion gate for the distilled operator. A paired validation run compares
// these observer-level chemistry outcomes against the reference source under
// identical recipe, temperature, precision and seed. Fracture locations are
// intentionally excluded: the solver documents them as discretisation- and
// perturbation-sensitive, while the chemical→mechanical coupling is still the
// next operator work item.
const OPERATOR_GAP_TOLERANCES = {
  final_expansion_factor_relative: 0.02,
  cream_time_s_absolute: 1.5,
  rise_time_s_absolute: 2.0,
  gel_time_s_absolute: 2.0,
  solid_time_s_absolute: 5.0,
  exotherm_rise_k_absolute: 2.0,
  core_skin_gap_k_absolute: 3.0,
  trapped_gas_fraction_absolute: 0.01
};

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, Number(v))); }
function clamp01(v) { return clamp(v, 0.0, 1.0); }
function mix(a, b, t) { return a + (b - a) * t; }
function mixRgb(a, b, t) { return [mix(a[0], b[0], t), mix(a[1], b[1], t), mix(a[2], b[2], t)]; }
function round3(v) { return Math.round(v * 1e3) / 1e3; }
function round4(v) { return Math.round(v * 1e4) / 1e4; }
function finite(v, label) {
  const x = Number(v);
  if (!Number.isFinite(x)) throw new Error("non-finite inferred " + label);
  return x;
}

// ---- Geant4 materials (fail-safe element components; no PubChem properties) ----
const polyolMaterial = {
  name: POLYOL_SOLUTION, densityGcm3: 1.08,
  components: [
    { element: "C", fraction: 0.545 },
    { element: "H", fraction: 0.095 },
    { element: "O", fraction: 0.310 },
    { material: WATER, fraction: 0.035 },
    { element: "N", fraction: 0.015 }
  ]
};
const isocyanateMaterial = {
  name: ISOCYANATE_SOLUTION, densityGcm3: 1.22,
  components: [
    { element: "C", fraction: 0.621 },
    { element: "H", fraction: 0.035 },
    { element: "N", fraction: 0.161 },
    { element: "O", fraction: 0.183 }
  ]
};
const resinMixMaterial = {
  name: RESIN_MIX, densityGcm3: 1.15,
  components: [
    { element: "C", fraction: 0.583 },
    { element: "H", fraction: 0.065 },
    { element: "O", fraction: 0.246 },
    { element: "N", fraction: 0.088 },
    { material: WATER, fraction: 0.018 }
  ]
};
const DECLARED_ELEMENTS = ["C", "H", "O", "N"];

// ---- PubChem structure identity (CID + SMILES + formula ONLY) ----
function pubchemStructure(name) {
  if (typeof globalThis.TRECH_PUBCHEM !== "function") {
    throw new Error("TRECH_PUBCHEM unavailable; fetch the build-local structure cache first");
  }
  const raw = globalThis.TRECH_PUBCHEM(name);
  if (!raw || !raw.cid || !raw.smiles) {
    throw new Error("PubChem structure cache for " + name + " must contain cid + smiles");
  }
  return { cid: Number(raw.cid), smiles: String(raw.smiles),
           formula: String(raw.molecular_formula || "") };
}
function formulaElements(formula) {
  const out = [];
  const re = /([A-Z][a-z]?)(\d*)/g;
  let m;
  while ((m = re.exec(formula)) !== null) {
    if (m[1] && out.indexOf(m[1]) < 0) out.push(m[1]);
  }
  return out;
}
function structureConsistent(structures) {
  return Object.keys(structures).every((key) =>
    formulaElements(structures[key].formula).every(
      (el) => DECLARED_ELEMENTS.indexOf(el) >= 0));
}

function opticsRgb(ctx, name) {
  const item = ctx.optics && ctx.optics[name];
  if (!item || !Array.isArray(item.display_rgb)) {
    throw new Error("ctx.optics missing Geant4-derived colour for " + name);
  }
  return item.display_rgb.slice(0, 3).map(clamp01);
}

// ---- the inferred coefficients: chemistry AND mechanics ----
function inferredCoefficients(cascade) {
  return {
    source: "ctx.cascade(Geant4 solution/mixture base + two-part recipe -> nano descriptors -> macro dual-reaction foaming + foam mechanics coefficients)",
    gelRatePerS: clamp(finite(cascade.macro_gel_rate_per_s, "gel rate"), 0.001, 0.02),
    blowRatePerS: clamp(finite(cascade.macro_blow_rate_per_s, "blow rate"), 0.002, 0.03),
    activationTemperatureK: clamp(finite(cascade.macro_activation_temperature_k,
      "activation temperature"), 2500.0, 7000.0),
    gelExothermK: clamp(finite(cascade.macro_gel_exotherm_k, "gel exotherm"), 30.0, 90.0),
    blowExothermK: clamp(finite(cascade.macro_blow_exotherm_k, "blow exotherm"), 15.0, 60.0),
    heatLossPerS: clamp(finite(cascade.macro_heat_loss_per_s, "heat loss"), 0.002, 0.03),
    heatDiffusionPerS: clamp(finite(cascade.macro_heat_diffusion_per_s,
      "heat diffusion"), 0.005, 0.5),
    co2ExpansionCapacity: clamp(finite(cascade.macro_co2_expansion_capacity,
      "CO2 expansion capacity"), 15.0, 55.0),
    co2SaturationFraction: clamp(finite(cascade.macro_co2_saturation_fraction,
      "CO2 saturation"), 0.03, 0.30),
    gelPointConversion: clamp(finite(cascade.macro_gel_point_conversion,
      "gel point"), 0.45, 0.75),
    viscosityGrowthExponent: clamp(finite(cascade.macro_viscosity_growth_exponent,
      "viscosity exponent"), 1.0, 4.0),
    bubbleTrapBase: clamp(finite(cascade.macro_bubble_trap_base, "bubble trap"), 0.30, 0.90),
    expansionMobilityPerS: clamp(finite(cascade.macro_expansion_mobility_per_s,
      "expansion mobility"), 0.05, 0.8),
    autocatalysisGain: clamp(finite(cascade.macro_autocatalysis_gain,
      "autocatalysis gain"), 0.0, 5.0),
    solidConversion: clamp(finite(cascade.macro_solid_conversion,
      "solid conversion"), 0.80, 0.98),
    // --- mechanics ---
    bondStiffnessPerS2: clamp(finite(cascade.macro_bond_stiffness_per_s2,
      "bond stiffness"), 50.0, 40000.0),
    bondFailureStrain: clamp(finite(cascade.macro_bond_failure_strain,
      "bond failure strain"), 0.05, 1.2),
    stressRelaxationPerS: clamp(finite(cascade.macro_stress_relaxation_per_s,
      "stress relaxation"), 0.05, 20.0),
    // material drag: the terminal creep velocity inside the foam is g/drag
    structuralDampingPerS: clamp(finite(cascade.macro_structural_damping_per_s,
      "structural damping"), 50.0, 40000.0),
    contactFriction: clamp(finite(cascade.macro_contact_friction, "contact friction"), 0.0, 1.0),
    contactRestitution: clamp(finite(cascade.macro_contact_restitution,
      "contact restitution"), 0.0, 0.6),
    imperfectionDispersion: clamp(finite(cascade.macro_imperfection_dispersion,
      "imperfection dispersion"), 0.0, 0.6),
    responseSigma: clamp(finite(cascade.macro_response_sigma, "response sigma"), 0.0, 1.0)
  };
}

// ---- per-parcel reaction: every parcel runs its own chemistry ----
// gel  = urethane conversion (R-NCO + R'-OH -> urethane)
// blow = water conversion    (R-NCO + H2O   -> amine + CO2)
// Both draw on the shared isocyanate budget (ncoShare from the declared index).
//
// This scenario carries TWO interchangeable sources for that chemistry, chosen
// by the `chemistry_source` parameter:
//
//   "reference" ... the reduced dual-reaction law written out below in
//                   JavaScript. This is the hand-coded chemical operation the
//                   engine is meant to have INFERRED, kept as the graded
//                   comparison (and as the teacher the operator is harvested
//                   from) rather than deleted unmeasured.
//   "operator"  ... the engine evaluates a trained scale-tagged model over
//                   every parcel through `ctx.evolve`: the scenario declares
//                   what state each parcel carries and the engine integrates
//                   the rates the model predicts. No rate law is written here.
//
// Both drive the same downstream mechanics coupling and produce the same
// emergent observables, so the two can be run against each other and compared
// on identical measurements. The run summary reports which source ran, under
// `chemistry_inference`.
//
// STATUS: the operator path is backed by the committed, independently
// held-out-validated model at
// data/polyurethane_cascade/meso_reaction_operator.json. It is distilled from
// the reference teacher (not measured foam physics). `operator` is the promoted
// default; the still-authored mechanics coupling is tracked in ROADMAP.md
// "Engine-side inference operator".

// The per-parcel state the chemistry evolves, and the bounds that are
// DEFINITIONAL for it (a conversion fraction lives in [0,1]; a gas inventory
// cannot be negative; an expansion factor cannot shrink the parcel below its
// poured volume). These are declarations about what the state IS, not tuned
// physics -- the engine applies them and knows nothing else about the names.
const OPERATOR_FIELDS = [
  { name: "gel", min: 0.0, max: 1.0 },
  { name: "blow", min: 0.0, max: 1.0 },
  { name: "temperature_k", min: 0.0 },
  { name: "dissolved_co2", min: 0.0 },
  { name: "trapped_gas", min: 0.0 },
  { name: "local_expansion", min: 1.0 },
  { name: "rigidity", min: 0.0, max: 1.0 },
  // The RECIPROCAL of the Castro-Macosko relative viscosity: it is the form
  // every consumer actually uses (bubble trapping and creep both scale with
  // 1/eta_r), and unlike eta_r itself -- which diverges at the gel point -- it
  // stays in [0,1], so it is a well-conditioned thing for a model to predict.
  { name: "inverse_relative_viscosity", min: 0.0, max: 1.0 }
];

// How a parcel's chemical state drives the mechanics of the network it is part
// of. NOT yet inferred: these four lines are the remaining hand-written
// coupling, tracked in ROADMAP.md as the next operator to train.
// `relativeViscosity` is passed rather than recovered from its stored
// reciprocal: a/b and a*(1/b) are not the same IEEE double, and the reference
// path must stay bit-identical to the result the validation report records.
function applyMechanicsCoupling(s, i, growthRatePerS, relativeViscosity) {
  const c = s.coeff;
  const foam = s.foam;
  const rigidity = s.rigidity[i];
  foam.growthRatePerS[i] = growthRatePerS;
  // Viscous creep dies as the resin cures: the shape stops flowing and locks.
  foam.relaxRatePerS[i] = c.stressRelaxationPerS / relativeViscosity;
  // ... and so does the material's ability to sag under its own weight. That
  // resistance is carried by the SOLID network, so it follows the rigidity built
  // past the gel point rather than the pre-gel viscosity climb: the foam stays
  // soft enough to lean and droop all through the rise, then stops creeping once
  // it has set.
  foam.dragPerS[i] = Math.min(c.structuralDampingPerS *
    (1.0 + 2000.0 * rigidity * rigidity), 4.0e6);
  // Structural strength builds with conversion (nothing to break before gelation).
  foam.strengthScale[i] = clamp01(s.gel[i] / c.solidConversion);
}

// Roll the per-parcel state into the aggregates the observer reads. Shared by
// both chemistry sources so they are compared on identical measurements.
function accumulateChemistryAggregates(s) {
  const n = s.foam.n;
  let sumGel = 0.0, sumBlow = 0.0, sumT = 0.0, sumExpansion = 0.0;
  let sumRigidity = 0.0;
  let maxT = -Infinity, minT = Infinity;
  for (let i = 0; i < n; i += 1) {
    sumGel += s.gel[i];
    sumBlow += s.blow[i];
    sumT += s.temperatureK[i];
    sumExpansion += s.localExpansion[i];
    sumRigidity += s.rigidity[i];
    if (s.temperatureK[i] > maxT) maxT = s.temperatureK[i];
    if (s.temperatureK[i] < minT) minT = s.temperatureK[i];
  }
  s.meanGel = sumGel / n;
  s.meanBlow = sumBlow / n;
  s.meanTemperatureK = sumT / n;
  s.meanExpansion = sumExpansion / n;
  s.meanRigidity = sumRigidity / n;
  s.minTemperatureK = minT;
  s.maxTemperatureK = maxT;
  if (maxT > s.peakTemperatureK) s.peakTemperatureK = maxT;
}

// The harvest sideband: while the reference law runs, capture (parcel state at
// t -> observed rate over [t, t+dt]) rows for a bounded, deterministic subset
// of parcels and steps. These rows are what `trech-train-surrogate --expand`
// turns into the trained operator; they change no physics and are emitted only
// when explicitly asked for.
function makeOperatorSampler(state) {
  const rows = [];
  const boundaryIndices = [];
  return {
    rows,
    // The regular parcel stride keeps the dataset bounded. Also retain the
    // actual min/max reactivity and exposure parcels for each sampled step so
    // the measured training hull covers the operator's whole live population,
    // not just whichever indices happened to land on the stride.
    prepare(s) {
      boundaryIndices.length = 0;
      const series = [s.reactivity, s.foam.exposure];
      for (let k = 0; k < series.length; k += 1) {
        let minIndex = 0, maxIndex = 0;
        for (let i = 1; i < s.foam.n; i += 1) {
          if (series[k][i] < series[k][minIndex]) minIndex = i;
          if (series[k][i] > series[k][maxIndex]) maxIndex = i;
        }
        if (boundaryIndices.indexOf(minIndex) < 0) boundaryIndices.push(minIndex);
        if (boundaryIndices.indexOf(maxIndex) < 0) boundaryIndices.push(maxIndex);
      }
    },
    // Snapshot the fields the operator reads, before the step advances them.
    capture(s, i, dt) {
      if (!s.samplingStep ||
          ((i % SAMPLE_EVERY_PARCELS) !== 0 &&
           boundaryIndices.indexOf(i) < 0)) return null;
      // Only full-size steps: a trailing partial step would teach the operator
      // a rate that is really a step-size artefact.
      if (Math.abs(dt - APPARATUS.physicsStepS) > 1e-12) return null;
      return {
        gel: s.gel[i], blow: s.blow[i], temperature_k: s.temperatureK[i],
        dissolved_co2: s.dissolvedCo2[i], trapped_gas: s.trappedGas[i],
        local_expansion: s.localExpansion[i],
        rigidity: s.rigidity[i],
        inverse_relative_viscosity: s.inverseRelativeViscosity[i],
        reactivity: s.reactivity[i], exposure: s.foam.exposure[i]
      };
    },
    record(s, i, dt, before) {
      const inv = 1.0 / dt;
      rows.push({
        // Preserve the exact inputs used by the teacher. Rounding an extrema
        // parcel inward would make the live value fall microscopically outside
        // the model's measured hull even though that exact parcel was sampled.
        gel: before.gel, blow: before.blow,
        temperature_k: before.temperature_k,
        dissolved_co2: before.dissolved_co2,
        trapped_gas: before.trapped_gas,
        local_expansion: before.local_expansion,
        rigidity: before.rigidity,
        inverse_relative_viscosity: before.inverse_relative_viscosity,
        reactivity: before.reactivity, exposure: before.exposure,
        d_gel_dt: (s.gel[i] - before.gel) * inv,
        d_blow_dt: (s.blow[i] - before.blow) * inv,
        d_temperature_k_dt: (s.temperatureK[i] - before.temperature_k) * inv,
        d_dissolved_co2_dt: (s.dissolvedCo2[i] - before.dissolved_co2) * inv,
        d_trapped_gas_dt: (s.trappedGas[i] - before.trapped_gas) * inv,
        d_local_expansion_dt: (s.localExpansion[i] - before.local_expansion) * inv,
        set_rigidity: s.rigidity[i],
        set_inverse_relative_viscosity: s.inverseRelativeViscosity[i]
      });
    },
    take() {
      const out = rows.slice();
      rows.length = 0;
      return out;
    }
  };
}

// --- source A: the hand-written reduced law (reference / teacher) ----------
function stepChemistryReference(s, dt, sampler) {
  const c = s.coeff;
  const foam = s.foam;
  const n = foam.n;
  const T0 = APPARATUS.initialTemperatureK;
  const saturation = c.co2SaturationFraction * c.co2ExpansionCapacity;
  for (let i = 0; i < n; i += 1) {
    const T = s.temperatureK[i];
    // Everything the operator is given as its input row, captured BEFORE the
    // step so a harvested sample is (state at t, rate over [t, t+dt]).
    const before = sampler ? sampler.capture(s, i, dt) : null;
    const arr = Math.exp(c.activationTemperatureK * (1.0 / T0 - 1.0 / T));
    const rateMul = s.reactivity[i];
    const avail = Math.max(0.0, 1.0 - (s.gel[i] + s.blow[i]) * s.ncoShare);
    let dGel = c.gelRatePerS * (1.0 - s.gel[i]) * avail * arr *
      (1.0 + c.autocatalysisGain * s.gel[i]) * rateMul * dt;
    let dBlow = c.blowRatePerS * (1.0 - s.blow[i]) * avail * arr * rateMul * dt;
    if (dGel > 1.0 - s.gel[i]) dGel = 1.0 - s.gel[i];
    if (dBlow > 1.0 - s.blow[i]) dBlow = 1.0 - s.blow[i];
    s.gel[i] += dGel;
    s.blow[i] += dBlow;
    // exotherm; the room only reaches the parcels on the free surface
    s.temperatureK[i] = T + c.gelExothermK * dGel + c.blowExothermK * dBlow -
      c.heatLossPerS * (0.15 + 1.85 * foam.exposure[i]) * (T - T0) * dt;

    // Castro-Macosko viscosity divergence toward the local gel point
    const gelClamped = Math.min(s.gel[i], c.gelPointConversion - 1e-3);
    const relativeViscosity = Math.pow(c.gelPointConversion /
      (c.gelPointConversion - gelClamped), c.viscosityGrowthExponent);
    const inverseRelativeViscosity = 1.0 / relativeViscosity;
    const trap = Math.min(1.0, c.bubbleTrapBase +
      (1.0 - c.bubbleTrapBase) * (1.0 - inverseRelativeViscosity));
    const rigidity = clamp01((s.gel[i] - c.gelPointConversion) /
      (c.solidConversion - c.gelPointConversion));
    s.rigidity[i] = rigidity;
    s.inverseRelativeViscosity[i] = inverseRelativeViscosity;

    // CO2 dissolves first; only past saturation do bubbles nucleate and grow
    s.dissolvedCo2[i] += c.co2ExpansionCapacity * dBlow;
    if (s.dissolvedCo2[i] > saturation) {
      const excess = s.dissolvedCo2[i] - saturation;
      s.dissolvedCo2[i] = saturation;
      s.trappedGas[i] += excess * trap;
      s.escapedGas += excess * (1.0 - trap);
      s.trappedGasTotal += excess * trap;
    }
    // local target expansion and the growth rate the network is driven with
    const target = 1.0 + s.trappedGas[i] * (s.temperatureK[i] / T0);
    const mobility = c.expansionMobilityPerS * (1.0 - rigidity);
    const previous = s.localExpansion[i];
    const next = previous + (target - previous) * (1.0 - Math.exp(-mobility * dt));
    s.localExpansion[i] = next;
    applyMechanicsCoupling(s, i,
      dt > 0 ? Math.max(0.0, (next - previous) / (previous * dt)) : 0.0,
      relativeViscosity);
    if (before) sampler.record(s, i, dt, before);
  }
  // Aggregates are read from the reacted state BEFORE conduction redistributes
  // it, so the reported core/skin gap is the one the reaction produced.
  accumulateChemistryAggregates(s);
  // heat conducts through the material itself
  foam.diffuseAlongBonds(s.temperatureK, c.heatDiffusionPerS, dt);
}

// --- source B: the engine's inference operator (no rate law here) ----------
// The scenario hands the engine its per-parcel state, the read-only per-parcel
// facts, and the run-constant coefficients the cascade already inferred; the
// engine chains the declared scale-tagged model(s) over every parcel and
// integrates the rates they predict. Whether the mixture reacts, how fast, how
// hot it gets and how much gas it traps is then a property of a TRAINED model
// carrying a measured domain and a held-out accuracy -- not of a formula typed
// into this file.
function stepChemistryOperator(ctx, s, dt) {
  const c = s.coeff;
  const foam = s.foam;
  const n = foam.n;
  const before = s.expansionBefore;
  for (let i = 0; i < n; i += 1) before[i] = s.localExpansion[i];
  const blowBefore = s.blowBefore;
  for (let i = 0; i < n; i += 1) blowBefore[i] = s.blow[i];
  const dissolvedBefore = s.dissolvedBefore;
  for (let i = 0; i < n; i += 1) dissolvedBefore[i] = s.dissolvedCo2[i];
  const trappedBefore = s.trappedBefore;
  for (let i = 0; i < n; i += 1) trappedBefore[i] = s.trappedGas[i];

  const report = ctx.evolve({
    dt,
    fields: OPERATOR_FIELDS,
    state: s.fieldArrays,
    aux: { reactivity: s.reactivity, exposure: foam.exposure },
    context: s.operatorContext,
    operator_role: OPERATOR_ROLE,
    element_kind: OPERATOR_ELEMENT_KIND
  });
  if (!report || !report.ran) {
    throw new Error("chemistry_source=operator requires predictive mode and a " +
                    "compatible '" + OPERATOR_ROLE + "' operator");
  }
  if (!report.selection || report.selection.status !== "selected" ||
      report.selection.selectedModels.indexOf(OPERATOR_MODEL) < 0) {
    throw new Error("ctx.evolve selected the wrong polyurethane operator");
  }
  s.operatorReport = report;
  s.operatorInferences += Number(report.inferenceCount || 0);
  s.operatorOutOfDomain += Number(report.outOfDomainInferences || 0);

  // Gas that the curing matrix failed to hold is what the reaction generated
  // minus what stayed in solution or was trapped -- a bookkeeping identity over
  // the operator's own outputs, not a second rate law.
  for (let i = 0; i < n; i += 1) {
    const generated = c.co2ExpansionCapacity * (s.blow[i] - blowBefore[i]);
    const retained = (s.dissolvedCo2[i] - dissolvedBefore[i]) +
                     (s.trappedGas[i] - trappedBefore[i]);
    const escaped = generated - retained;
    if (escaped > 0.0) s.escapedGas += escaped;
    if (retained > 0.0) s.trappedGasTotal += (s.trappedGas[i] - trappedBefore[i]);
    const previous = before[i];
    const inverse = s.inverseRelativeViscosity[i];
    applyMechanicsCoupling(s, i,
      dt > 0 && previous > 0 ?
        Math.max(0.0, (s.localExpansion[i] - previous) / (previous * dt)) : 0.0,
      inverse > 1e-12 ? 1.0 / inverse : 1e12);
  }
  accumulateChemistryAggregates(s);
  foam.diffuseAlongBonds(s.temperatureK, c.heatDiffusionPerS, dt);
}

function stepChemistry(ctx, s, dt) {
  if (s.chemistrySource === "operator") {
    stepChemistryOperator(ctx, s, dt);
  } else {
    stepChemistryReference(s, dt, s.sampler);
  }
}

function physicsStep(ctx, s, dt) {
  s.samplingStep = s.sampler !== null &&
    (s.physicsSteps % SAMPLE_EVERY_STEPS) === 0;
  if (s.samplingStep) s.sampler.prepare(s);
  stepChemistry(ctx, s, dt);
  s.foam.step(dt);
  s.physicsTimeS += dt;
  s.physicsSteps += 1;
  if (s.creamTimeS === null && s.meanExpansion > 1.15) s.creamTimeS = s.physicsTimeS;
  if (s.gelTimeS === null && s.meanGel >= s.coeff.gelPointConversion) {
    s.gelTimeS = s.physicsTimeS;
  }
  if (s.solidTimeS === null && s.meanRigidity >= 0.9) s.solidTimeS = s.physicsTimeS;
  s.expansionSeries.push([round3(s.physicsTimeS), round3(s.meanExpansion)]);
}

function advanceTo(ctx, s, targetTimeS) {
  const epsilon = 1e-10;
  while (s.physicsTimeS + APPARATUS.physicsStepS <= targetTimeS + epsilon) {
    physicsStep(ctx, s, APPARATUS.physicsStepS);
  }
  const remainder = targetTimeS - s.physicsTimeS;
  if (remainder > epsilon) physicsStep(ctx, s, remainder);
  s.physicsTimeS = targetTimeS;
}

function frameClock(frameIndex) {
  const fraction = frameIndex / APPARATUS.outputTicks;
  return {
    physicalTimeS: fraction * APPARATUS.durationS,
    playbackTimeS: fraction * APPARATUS.playbackDurationS,
    timeScale: APPARATUS.durationS / APPARATUS.playbackDurationS
  };
}

function renderSurfaceHint(s, metrics) {
  const sigma = RENDER_SIGMA_PER_SPACING * metrics.spacingMm;
  const bulge = Math.sqrt(2.0 * Math.log(1.0 / RENDER_ISO_LEVEL)) * sigma;
  return {
    mode: "metaball",
    kernel: "gaussian",
    grid_spacing_mm: APPARATUS.renderSurfaceGridMm,
    sigma_mm: round3(sigma),
    iso_level: RENDER_ISO_LEVEL,
    clip_cylinder: {
      axis: "z",
      radius_mm: APPARATUS.tableRadiusMm,
      min_mm: 0.0,
      max_mm: round3(metrics.maxZMm + bulge + 6.0)
    },
    fresnel_r0: 0.04,
    gloss: 0.35,
    opacity: mix(REPRESENTATION.liquidAlpha, REPRESENTATION.foamAlpha,
      clamp01(s.meanExpansion - 1.0)),
    positions_unmodified: true,
    policy: "representation only: Gaussian surface over emitted parcel positions; sigma tracks the emergent parcel spacing"
  };
}

function observedPhase(s, metrics) {
  if (metrics.detachedParcels > 0 && s.meanRigidity >= 0.9) return "cured_with_fallen_pieces";
  if (metrics.detachedParcels > 0) return "cracking_shedding_pieces";
  if (s.meanRigidity >= 0.9) return "solid_sponge";
  if (s.meanRigidity > 0.05) return "gelling_curing";
  if (s.creamTimeS !== null && s.meanExpansion > 1.5) return "rising";
  if (s.creamTimeS !== null) return "creaming";
  return "mixing_liquids";
}

function emitFrame(ctx, s, frameIndex) {
  const clock = frameClock(frameIndex);
  const foam = s.foam;
  foam.updateComponents();
  const metrics = foam.metrics();
  const phase = observedPhase(s, metrics);
  const T0 = APPARATUS.initialTemperatureK;
  const n = foam.n;
  const positions = new Array(n);
  const colors = new Array(n);
  let maxDisplacement = 0.0;
  for (let i = 0; i < n; i += 1) {
    positions[i] = [round3(foam.px[i]), round3(foam.py[i]), round3(foam.pz[i])];
    const gasFraction = clamp01((s.localExpansion[i] - 1.0) /
      Math.max(s.localExpansion[i], 1e-9));
    const whiteness = 1.0 - Math.exp(-REPRESENTATION.scatterGain * gasFraction);
    let rgb = mixRgb(s.liquidBaseRgb, REPRESENTATION.creamTint, whiteness);
    rgb = mixRgb(rgb, REPRESENTATION.curedTint, 0.35 * s.gel[i] * whiteness);
    // A detached piece is drawn from the same emitted state; only its colour is
    // slightly darkened so the observer can tell body from fallen debris.
    const shade = foam.freeFlag[i] ? 0.86 : 1.0;
    colors[i] = [round3(clamp01(rgb[0] * shade)), round3(clamp01(rgb[1] * shade)),
                 round3(clamp01(rgb[2] * shade)),
                 round3(mix(REPRESENTATION.liquidAlpha, REPRESENTATION.foamAlpha,
                            gasFraction))];
    if (s.lastEmittedPx) {
      const dx = foam.px[i] - s.lastEmittedPx[i];
      const dy = foam.py[i] - s.lastEmittedPy[i];
      const dz = foam.pz[i] - s.lastEmittedPz[i];
      const d = Math.sqrt(dx * dx + dy * dy + dz * dz);
      if (d > maxDisplacement) maxDisplacement = d;
    }
  }
  s.lastEmittedPx = new Float64Array(foam.px);
  s.lastEmittedPy = new Float64Array(foam.py);
  s.lastEmittedPz = new Float64Array(foam.pz);
  // The late-motion probe must not be dominated by falling debris, nor by the one
  // half-cracked flap still hanging by a bond (which really does keep swinging):
  // the cured BULK is what has to be frozen, so report the distribution.
  let bodyMedian = 0.0, bodyP95 = 0.0, bodyMax = 0.0;
  if (s.lastBodyPz) {
    const moved = [];
    for (let i = 0; i < n; i += 1) {
      if (foam.freeFlag[i]) continue;
      const dx = foam.px[i] - s.lastBodyPx[i];
      const dy = foam.py[i] - s.lastBodyPy[i];
      const dz = foam.pz[i] - s.lastBodyPz[i];
      moved.push(Math.sqrt(dx * dx + dy * dy + dz * dz));
    }
    if (moved.length > 0) {
      moved.sort((a, b) => a - b);
      bodyMedian = moved[Math.floor(moved.length * 0.5)];
      bodyP95 = moved[Math.min(moved.length - 1, Math.floor(moved.length * 0.95))];
      bodyMax = moved[moved.length - 1];
    }
  }
  s.lastBodyPx = new Float64Array(foam.px);
  s.lastBodyPy = new Float64Array(foam.py);
  s.lastBodyPz = new Float64Array(foam.pz);
  s.bodyMedianDisplacementsMm.push(round4(bodyMedian));
  s.bodyP95DisplacementsMm.push(round4(bodyP95));

  s.lastFrame = frameIndex;
  s.lastPhysicalTimeS = clock.physicalTimeS;
  if (metrics.leanDeg > s.maxLeanDeg) s.maxLeanDeg = metrics.leanDeg;
  if (metrics.bodyTopZMm > s.maxHeightMm) s.maxHeightMm = metrics.bodyTopZMm;
  if (metrics.detachedParcels > s.maxDetachedParcels) {
    s.maxDetachedParcels = metrics.detachedParcels;
  }
  if (metrics.groundParcels > s.maxGroundParcels) {
    s.maxGroundParcels = metrics.groundParcels;
  }

  ctx.emit("material_frame", {
    time_s: round3(clock.physicalTimeS),
    physical_time_s: round3(clock.physicalTimeS),
    playback_time_s: round3(clock.playbackTimeS),
    time_scale: clock.timeScale,
    phase: "polyurethane_foam:" + phase,
    particle_ids: foam.ids,
    positions_mm: positions,
    colors_rgba: colors,
    render_surface: renderSurfaceHint(s, metrics),
    counts: {
      persistent_foam_parcels: n,
      mean_expansion_factor: round3(s.meanExpansion),
      bonds_intact: metrics.bondsTotal - metrics.bondsBroken,
      bonds_broken: metrics.bondsBroken,
      connected_components: metrics.componentCount,
      detached_parcels: metrics.detachedParcels,
      parcels_on_ground: metrics.groundParcels
    },
    physics_state: {
      mean_gel_conversion: round4(s.meanGel),
      mean_blow_conversion: round4(s.meanBlow),
      mean_temperature_k: round3(s.meanTemperatureK),
      core_temperature_k: round3(s.maxTemperatureK),
      skin_temperature_k: round3(s.minTemperatureK),
      mean_rigidity: round4(s.meanRigidity),
      foam_top_mm: round3(metrics.bodyTopZMm),
      debris_top_mm: round3(metrics.maxZMm),
      foam_max_radius_mm: round3(metrics.bodyMaxRadiusMm),
      debris_max_radius_mm: round3(metrics.maxRadiusMm),
      lean_deg: round3(metrics.leanDeg),
      lean_offset_mm: round3(metrics.leanOffsetMm),
      body_median_displacement_since_prior_emit_mm: round4(bodyMedian),
      body_p95_displacement_since_prior_emit_mm: round4(bodyP95),
      body_max_displacement_since_prior_emit_mm: round4(bodyMax),
      max_displacement_since_prior_emit_mm: round4(maxDisplacement)
    },
    geant4_event_id: s.lastGeant4EventId,
    inference: { source: s.coeff.source, response_sigma: s.coeff.responseSigma },
    clock: {
      source: "scenario-emitted observer clocks",
      physical_time_retained: true,
      playback_acceleration: clock.timeScale
    },
    motion_scope: "persistent foam parcels in a growing viscoelastic bond network under standard gravity; leaning, cracking, detachment and where pieces land are consequences of the stress state, not scheduled events",
    representation_override: REPRESENTATION
  });
}

// Known polyurethane-foam behaviour, read ONLY at run end to grade the emergent
// result. None of this feeds the state or the frames.
const VALIDATION_ONLY = {
  expectedBehaviour: "cream within seconds-to-tens-of-seconds, expand up to ~30x, exotherm, lean/sag under its own weight, shed cracked overhang pieces, cure into a rigid porous sponge",
  plausibleExpansionRange: [8.0, 40.0],
  plausibleCreamTimeRangeS: [5.0, 45.0],
  plausibleExothermRiseK: [30.0, 130.0],
  expectedGravityConsequences: "a free-rising bun is never a perfect cylinder: it leans, it sags, and overhanging pieces crack off and fall",
  expectedFinalConsistency: "rigid (motion frozen past the gel point), porous (mostly gas)",
  source: "rigid PU foam demonstration kits; Flory gelation + Castro-Macosko rheology; urethane/water-isocyanate reaction chemistry (validation only)"
};

globalThis.TRECH_HOOKS = {
  onRunStart(ctx) {
    const waterProbe = ctx.materials && ctx.materials[WATER];
    const polyolProbe = ctx.materials && ctx.materials[POLYOL_SOLUTION];
    const isoProbe = ctx.materials && ctx.materials[ISOCYANATE_SOLUTION];
    const mixProbe = ctx.materials && ctx.materials[RESIN_MIX];
    if (!waterProbe || !polyolProbe || !isoProbe || !mixProbe) {
      throw new Error("Geant4 material probes missing foam media");
    }
    const structures = {
      polyol_initiator: pubchemStructure("glycerol"),
      diisocyanate: pubchemStructure("toluene 2,4-diisocyanate"),
      blowing_agent: pubchemStructure("water")
    };
    const seed = {};
    seed["context.polyol_hydroxyl_number"] = RECIPE.polyolHydroxylNumberMgKohG;
    seed["context.water_pphp"] = RECIPE.waterPartsPerHundredPolyol;
    seed["context.isocyanate_index"] = RECIPE.isocyanateIndex;
    seed["context.amine_catalyst_pphp"] = RECIPE.amineCatalystPphp;
    seed["context.surfactant_pphp"] = RECIPE.surfactantPphp;
    seed["context.initial_temperature_k"] = APPARATUS.initialTemperatureK;
    // This config can also declare the independent per-element reaction
    // operator. Narrow the property cascade to its two coefficient stages so
    // the operator is never evaluated against missing parcel inputs.
    const cascade = ctx.cascade(
      seed, ["nano_reagent_descriptors", "macro_foam_response"]);
    if (!cascade || !cascade.__cascade || cascade.__cascade.stagesRun !== 2) {
      throw new Error("polyurethane cascade requires predictive mode and two loaded stages");
    }
    const coeff = inferredCoefficients(cascade);

    const foam = FOAM.create({
      parcelCount: APPARATUS.parcels,
      fillRadiusMm: PARCEL_R_MM,
      fillHeightMm: APPARATUS.initialLiquidHeightMm,
      cupInnerRadiusMm: PARCEL_R_MM,
      cupHeightMm: APPARATUS.cupHeightMm,
      groundZMm: 0.0,
      groundRadiusMm: APPARATUS.tableRadiusMm,
      gravityScale: APPARATUS.gravityScale,
      constraintIterations: APPARATUS.constraintIterations,
      fragmentSubsteps: APPARATUS.fragmentSubsteps,
      imperfectionDispersion: coeff.imperfectionDispersion
    });
    foam.coeff.bondStiffnessPerS2 = coeff.bondStiffnessPerS2;
    foam.coeff.bondFailureStrain = coeff.bondFailureStrain;
    foam.coeff.structuralDampingPerS = coeff.structuralDampingPerS;
    foam.coeff.contactFriction = coeff.contactFriction;
    foam.coeff.contactRestitution = coeff.contactRestitution;
    foam.updateComponents();

    const n = foam.n;
    const state = {
      cascade, coeff, structures, foam,
      // per-parcel chemistry
      temperatureK: new Float64Array(n),
      gel: new Float64Array(n),
      blow: new Float64Array(n),
      dissolvedCo2: new Float64Array(n),
      trappedGas: new Float64Array(n),
      localExpansion: new Float64Array(n),
      // Carried per parcel so both chemistry sources expose the same state:
      // the reference law writes them, the operator ASSIGNS them (set_*).
      rigidity: new Float64Array(n),
      inverseRelativeViscosity: new Float64Array(n),
      reactivity: new Float64Array(n),
      // Pre-step snapshots the operator path needs to recover the per-step
      // deltas the reference law had in hand (gas bookkeeping, growth rate).
      expansionBefore: new Float64Array(n),
      blowBefore: new Float64Array(n),
      dissolvedBefore: new Float64Array(n),
      trappedBefore: new Float64Array(n),
      chemistrySource,
      sampler: null,
      samplingStep: false,
      operatorReport: null,
      operatorInferences: 0,
      operatorOutOfDomain: 0,
      escapedGas: 0.0,
      trappedGasTotal: 0.0,
      liquidBaseRgb: opticsRgb(ctx, RESIN_MIX),
      waterDensity: Number(waterProbe.density_g_per_cm3),
      polyolDensity: Number(polyolProbe.density_g_per_cm3),
      isoDensity: Number(isoProbe.density_g_per_cm3),
      mixDensity: Number(mixProbe.density_g_per_cm3),
      mixElectronDensity: Number(mixProbe.electron_density_per_cm3),
      isoNitrogenPerCm3: Number((isoProbe.numberDensityPerCm3 || {}).N || 0),
      ncoShare: 1.0 / (2.0 * RECIPE.isocyanateIndex),
      // aggregates
      meanGel: 0.0, meanBlow: 0.0, meanExpansion: 1.0, meanRigidity: 0.0,
      meanTemperatureK: APPARATUS.initialTemperatureK,
      minTemperatureK: APPARATUS.initialTemperatureK,
      maxTemperatureK: APPARATUS.initialTemperatureK,
      peakTemperatureK: APPARATUS.initialTemperatureK,
      physicsTimeS: 0.0, physicsSteps: 0,
      creamTimeS: null, gelTimeS: null, solidTimeS: null,
      expansionSeries: [],
      lastEmittedPx: null, lastEmittedPy: null, lastEmittedPz: null,
      lastBodyPx: null, lastBodyPy: null, lastBodyPz: null,
      bodyMedianDisplacementsMm: [],
      bodyP95DisplacementsMm: [],
      maxLeanDeg: 0.0, maxHeightMm: 0.0,
      maxDetachedParcels: 0, maxGroundParcels: 0,
      lastFrame: 0, lastPhysicalTimeS: 0.0,
      geant4Events: 0, geant4Edep: 0.0, geant4Steps: 0, lastGeant4EventId: -1
    };
    // Mixing is never perfect: each parcel gets its own reactivity, and the
    // solver its own growth/strength imperfection, from the SAME inferred
    // dispersion. Deterministic pattern, inferred magnitude.
    for (let i = 0; i < n; i += 1) {
      state.temperatureK[i] = APPARATUS.initialTemperatureK;
      state.localExpansion[i] = 1.0;
      state.inverseRelativeViscosity[i] = 1.0;  // fresh resin: eta_r = 1
      // The same spatially correlated imperfection field the mechanics uses:
      // a badly mixed patch reacts at its own pace.
      state.reactivity[i] = foam.reactivityImperfection[i];
    }
    // The named per-parcel state the engine's operator evolves. Same arrays the
    // rest of the scenario reads: ctx.evolve mutates them in place.
    state.fieldArrays = {
      gel: state.gel,
      blow: state.blow,
      temperature_k: state.temperatureK,
      dissolved_co2: state.dissolvedCo2,
      trapped_gas: state.trappedGas,
      local_expansion: state.localExpansion,
      rigidity: state.rigidity,
      inverse_relative_viscosity: state.inverseRelativeViscosity
    };
    // Run-constant facts the operator predicts against: every coefficient the
    // cascade inferred plus the declared stoichiometric share and the ambient
    // temperature. The engine adds the Geant4 base (material probes, per-event
    // tallies) to this automatically.
    state.operatorContext = {
      gel_rate_per_s: coeff.gelRatePerS,
      blow_rate_per_s: coeff.blowRatePerS,
      activation_temperature_k: coeff.activationTemperatureK,
      gel_exotherm_k: coeff.gelExothermK,
      blow_exotherm_k: coeff.blowExothermK,
      heat_loss_per_s: coeff.heatLossPerS,
      co2_expansion_capacity: coeff.co2ExpansionCapacity,
      co2_saturation_fraction: coeff.co2SaturationFraction,
      gel_point_conversion: coeff.gelPointConversion,
      viscosity_growth_exponent: coeff.viscosityGrowthExponent,
      bubble_trap_base: coeff.bubbleTrapBase,
      expansion_mobility_per_s: coeff.expansionMobilityPerS,
      autocatalysis_gain: coeff.autocatalysisGain,
      solid_conversion: coeff.solidConversion,
      nco_share: state.ncoShare,
      initial_temperature_k: APPARATUS.initialTemperatureK
    };
    if (emitOperatorSamples) {
      state.sampler = makeOperatorSampler(state);
    }
    ctx.state.puFoam = state;

    ctx.emit("polyurethane_foam_scenario", {
      name: "polyurethane_foam",
      recipe: RECIPE,
      apparatus: APPARATUS,
      reactions: {
        polymerization: "R-N=C=O + R'-OH -> R-NH-CO-O-R' (urethane linkage; builds the cross-linked matrix)",
        blowing: "R-N=C=O + H2O -> R-NH2 + CO2^ (gas generation; inflates the curing matrix)"
      },
      geant4_materials: [POLYOL_SOLUTION, ISOCYANATE_SOLUTION, RESIN_MIX, WATER],
      geant4_sees: {
        polyol_solution_density_g_per_cm3: state.polyolDensity,
        diisocyanate_solution_density_g_per_cm3: state.isoDensity,
        resin_mix_density_g_per_cm3: state.mixDensity,
        water_density_g_per_cm3: state.waterDensity,
        isocyanate_nitrogen_atoms_per_cm3: state.isoNitrogenPerCm3,
        mix_electron_density_per_cm3: state.mixElectronDensity
      },
      pubchem_structure_only: {
        policy: "CID + SMILES + formula identity; no physical property feeds runtime",
        structures
      },
      inferred_coefficients: coeff,
      cascade_trace: cascade.__cascade,
      mechanics: {
        model: "growing viscoelastic bonded-parcel network (trech_foam_solver.js)",
        parcels: n,
        bonds: foam.bondCountTotal,
        gravity_mm_per_s2: foam.gravityMmPerS2,
        gravity_scale: APPARATUS.gravityScale,
        gravity_source: "standard gravity as a physical constant (9806.65 mm/s2); not inferred and not fitted",
        constraint_iterations: APPARATUS.constraintIterations,
        fragment_substeps: APPARATUS.fragmentSubsteps,
        imperfection: "per-parcel reactivity, growth and strength multipliers; magnitude inferred (macro_imperfection_dispersion), pattern deterministic",
        honest_scope: FOAM.honestScope
      },
      representation_override: REPRESENTATION
    });
    emitFrame(ctx, state, 0);
  },
  onEventEnd(ctx) {
    const s = ctx.state && ctx.state.puFoam;
    if (!s) return;
    s.geant4Events += 1;
    s.geant4Edep += Number(ctx.event.edepMeV || 0.0);
    s.geant4Steps += Number(ctx.event.totalStepCount || 0);
    s.lastGeant4EventId = Number(ctx.event.id);
    const frameIndex = Math.min(APPARATUS.outputTicks, Number(ctx.event.id) + 1);
    advanceTo(ctx, s, frameClock(frameIndex).physicalTimeS);
    emitFrame(ctx, s, frameIndex);
    // Harvest sideband: one bounded record per tick carrying this tick's
    // sampled (state -> observed rate) rows. Emitted only when asked for; it
    // changes no state and no frame.
    if (s.sampler) {
      const rows = s.sampler.take();
      if (rows.length > 0) {
        // The run-constant coefficients ride at the TOP level under the exact
        // names ctx.evolve binds them to, so a harvested column and an operator
        // input are the same identifier -- the trained model's input_features
        // are directly resolvable at run time with no renaming step.
        const payload = {
          teacher: "reduced dual-reaction foaming law authored in polyurethane_foam.js",
          // Exact reserved input name exposed by ctx.evolve. Keep dt_s as the
          // human/unit-labelled audit field, but train against `dt` so the
          // exported model resolves directly at runtime.
          dt: APPARATUS.physicsStepS,
          dt_s: APPARATUS.physicsStepS,
          step_stride: SAMPLE_EVERY_STEPS,
          parcel_stride: SAMPLE_EVERY_PARCELS,
          samples: rows
        };
        for (const key in s.operatorContext) payload[key] = s.operatorContext[key];
        ctx.emit("operator_sample", payload);
      }
    }
  },
  onRunEnd(ctx) {
    const s = ctx.state && ctx.state.puFoam;
    if (!s) return;
    const coeff = s.coeff;
    const foam = s.foam;
    foam.updateComponents();
    const metrics = foam.metrics();
    const finalExpansion = s.meanExpansion;
    let riseTimeS = null;
    for (let i = 0; i < s.expansionSeries.length; i += 1) {
      if (s.expansionSeries[i][1] >= 0.95 * finalExpansion) {
        riseTimeS = s.expansionSeries[i][0];
        break;
      }
    }
    const lateMedianWindow = s.bodyMedianDisplacementsMm.slice(-12);
    const lateP95Window = s.bodyP95DisplacementsMm.slice(-12);
    const lateMedianDisplacement = lateMedianWindow.length ?
      Math.max.apply(null, lateMedianWindow) : Infinity;
    const lateP95Displacement = lateP95Window.length ?
      Math.max.apply(null, lateP95Window) : Infinity;
    const peakMedianDisplacement = s.bodyMedianDisplacementsMm.length ?
      Math.max.apply(null, s.bodyMedianDisplacementsMm) : 0.0;
    const gasFraction = clamp01((finalExpansion - 1.0) / Math.max(finalExpansion, 1e-9));
    const trappedFraction = s.trappedGasTotal /
      Math.max(1e-9, s.trappedGasTotal + s.escapedGas);
    const seedKeys = s.cascade.__cascade.seedKeys || [];
    const g4Seeded = seedKeys.indexOf("material." + RESIN_MIX + ".density_g_per_cm3") >= 0 &&
      seedKeys.indexOf("material." + ISOCYANATE_SOLUTION + ".density_g_per_cm3") >= 0;
    const exothermRiseK = s.peakTemperatureK - APPARATUS.initialTemperatureK;
    const coreSkinGapK = s.maxTemperatureK - s.minTemperatureK;
    const ordering = s.creamTimeS !== null && s.gelTimeS !== null &&
      s.solidTimeS !== null && riseTimeS !== null &&
      s.creamTimeS < s.gelTimeS && s.gelTimeS < s.solidTimeS &&
      s.creamTimeS < riseTimeS;
    const gravityOn = APPARATUS.gravityScale > 0.0;
    const operatorTrace = s.operatorReport ? s.operatorReport.trace : [];
    const trustStage = operatorTrace.length ? operatorTrace[operatorTrace.length - 1] : null;
    const operatorOodFraction = s.operatorInferences > 0 ?
      round4(s.operatorOutOfDomain / s.operatorInferences) : null;

    ctx.emit("polyurethane_foam_summary", {
      recipe: RECIPE,
      conditions: {
        gravity_scale: APPARATUS.gravityScale,
        gravity_mm_per_s2: foam.gravityMmPerS2,
        initial_temperature_k: APPARATUS.initialTemperatureK
      },
      precision: {
        parcels: foam.n,
        bonds: foam.bondCountTotal,
        max_physics_step_s: APPARATUS.physicsStepS,
        physics_steps: s.physicsSteps,
        constraint_iterations: APPARATUS.constraintIterations,
        fragment_substeps: APPARATUS.fragmentSubsteps,
        geant4_ticks: APPARATUS.outputTicks,
        representation_only: { render_surface_grid_mm: APPARATUS.renderSurfaceGridMm }
      },
      geant4: {
        polyol_solution_density_g_per_cm3: s.polyolDensity,
        diisocyanate_solution_density_g_per_cm3: s.isoDensity,
        resin_mix_density_g_per_cm3: s.mixDensity,
        water_density_g_per_cm3: s.waterDensity,
        isocyanate_nitrogen_atoms_per_cm3: s.isoNitrogenPerCm3,
        mix_electron_density_per_cm3: s.mixElectronDensity,
        liquid_base_rgb: s.liquidBaseRgb,
        event_drive: { events: s.geant4Events, edep_mev: round4(s.geant4Edep),
                       steps: s.geant4Steps }
      },
      pubchem_structure_only: {
        policy: "CID + SMILES + formula identity; no physical property feeds runtime",
        structures: s.structures
      },
      inferred_coefficients: coeff,
      cascade: s.cascade.__cascade,
      // Where the per-parcel chemistry came from this run. In `operator` mode
      // NO reaction rate law is authored in this scenario: the engine evolved
      // the declared per-parcel state through a trained model (ctx.evolve), and
      // the stage's own trust profile (trained band, held-out accuracy, how many
      // parcel-steps fell outside the trained domain) is reported here rather
      // than assumed.
      chemistry_inference: {
        source: s.chemistrySource,
        authored_rate_law: s.chemistrySource === "reference",
        operator_model: s.chemistrySource === "operator" ? OPERATOR_MODEL : null,
        teacher: s.chemistrySource === "operator" ?
          "reduced dual-reaction foaming law authored in polyurethane_foam.js" : null,
        measured: s.chemistrySource === "operator" ? false : null,
        state_fields: OPERATOR_FIELDS.map((f) => f.name),
        parcel_step_inferences: s.operatorInferences,
        parcel_step_out_of_domain: s.operatorOutOfDomain,
        out_of_domain_fraction: operatorOodFraction,
        selection: s.operatorReport ? s.operatorReport.selection : null,
        stage_trace: operatorTrace.length ? operatorTrace : null,
        remaining_authored_coupling:
          "chemical state -> mechanics (growth/creep/drag/strength) is still " +
          "hand-written in applyMechanicsCoupling; tracked in ROADMAP.md",
        harvest_samples_emitted: s.sampler !== null
      },
      // Each source emits the same compact comparison record. The validation
      // case pairs a reference run with an operator run that has the same
      // comparison_key and computes the actual gaps against these tolerances.
      operator_vs_reference: {
        schema: "trech_operator_reference_pair_v1",
        comparison_key: {
          seed: Number(ctx.runtime.seed),
          initial_temperature_k: APPARATUS.initialTemperatureK,
          duration_s: APPARATUS.durationS,
          parcels: foam.n,
          max_physics_step_s: APPARATUS.physicsStepS,
          constraint_iterations: APPARATUS.constraintIterations,
          fragment_substeps: APPARATUS.fragmentSubsteps,
          geant4_ticks: APPARATUS.outputTicks
        },
        source: s.chemistrySource,
        teacher: "reduced dual-reaction foaming law authored in polyurethane_foam.js",
        measured: false,
        tolerances: OPERATOR_GAP_TOLERANCES,
        // Normalized trust payload consumed by the reusable paired-run
        // validator. Future scenario pairs emit this same schema instead of
        // growing another chemistry-specific Python evaluator.
        trust: {
          authored_state_law: s.chemistrySource === "reference",
          selection: s.operatorReport ? s.operatorReport.selection : null,
          domain_measured: trustStage ? trustStage.domainMeasured : null,
          trained_scale: trustStage ? trustStage.trainedScale : null,
          scale_mismatch: trustStage ? trustStage.scaleMismatch : null,
          missing_inputs: trustStage ? trustStage.missingInputs : [],
          starved_inputs: trustStage ? trustStage.starvedInputs : [],
          holdout_r2: trustStage ? trustStage.holdoutR2 : null,
          holdout_samples: trustStage ? trustStage.holdoutSamples : null,
          inference_count: s.operatorInferences,
          out_of_domain_count: s.operatorOutOfDomain,
          out_of_domain_fraction: operatorOodFraction,
          non_operator_inference_count: s.cascade.__cascade.stagesRun,
          non_operator_out_of_domain_count:
            s.cascade.__cascade.stagesExtrapolating
        },
        observables: {
          final_expansion_factor: round3(finalExpansion),
          cream_time_s: s.creamTimeS === null ? null : round3(s.creamTimeS),
          rise_time_s: riseTimeS === null ? null : round3(riseTimeS),
          gel_time_s: s.gelTimeS === null ? null : round3(s.gelTimeS),
          solid_time_s: s.solidTimeS === null ? null : round3(s.solidTimeS),
          exotherm_rise_k: round3(exothermRiseK),
          core_skin_gap_k: round3(coreSkinGapK),
          trapped_gas_fraction: round4(trappedFraction)
        }
      },
      emergent: {
        frames: s.lastFrame + 1,
        final_expansion_factor: round3(finalExpansion),
        final_gas_volume_fraction: round4(gasFraction),
        cream_time_s: s.creamTimeS === null ? null : round3(s.creamTimeS),
        rise_time_s: riseTimeS === null ? null : round3(riseTimeS),
        gel_time_s: s.gelTimeS === null ? null : round3(s.gelTimeS),
        solid_time_s: s.solidTimeS === null ? null : round3(s.solidTimeS),
        peak_temperature_k: round3(s.peakTemperatureK),
        exotherm_rise_k: round3(exothermRiseK),
        core_skin_gap_k: round3(coreSkinGapK),
        final_core_temperature_k: round3(s.maxTemperatureK),
        final_skin_temperature_k: round3(s.minTemperatureK),
        final_mean_gel_conversion: round4(s.meanGel),
        final_mean_blow_conversion: round4(s.meanBlow),
        final_mean_rigidity: round4(s.meanRigidity),
        trapped_gas_fraction: round4(trappedFraction),
        escaped_gas_volumes: round3(s.escapedGas),
        foam_top_mm: round3(metrics.bodyTopZMm),
        max_height_mm: round3(s.maxHeightMm),
        max_radius_mm: round3(metrics.bodyMaxRadiusMm),
        debris_max_radius_mm: round3(metrics.maxRadiusMm),
        // --- gravity + imperfection consequences ---
        lean_deg: round3(metrics.leanDeg),
        max_lean_deg: round3(s.maxLeanDeg),
        lean_offset_mm: round3(metrics.leanOffsetMm),
        bonds_total: metrics.bondsTotal,
        bonds_broken: metrics.bondsBroken,
        broken_bond_fraction: round4(metrics.bondsBroken / Math.max(1, metrics.bondsTotal)),
        connected_components: metrics.componentCount,
        detached_parcels: metrics.detachedParcels,
        max_detached_parcels: s.maxDetachedParcels,
        parcels_on_ground: metrics.groundParcels,
        max_parcels_on_ground: s.maxGroundParcels,
        fallen_mass_fraction: round4(metrics.groundParcels / foam.n),
        parcels_outside_cup_footprint: metrics.outsideCupParcels,
        late_window_body_median_displacement_mm: round4(lateMedianDisplacement),
        late_window_body_p95_displacement_mm: round4(lateP95Displacement),
        peak_body_median_displacement_mm: round4(peakMedianDisplacement),
        late_vs_peak_motion_ratio: peakMedianDisplacement > 0 ?
          round4(lateMedianDisplacement / peakMedianDisplacement) : null,
        max_parcel_speed_mm_per_s: round3(foam.maxSpeedMmS)
      },
      validation_references_only: VALIDATION_ONLY,
      validation: {
        geant4_base_present: s.isoDensity > s.polyolDensity &&
          s.mixDensity > s.waterDensity && s.isoNitrogenPerCm3 > 0 &&
          s.geant4Events === APPARATUS.outputTicks && s.geant4Edep > 0.0,
        cascade_supplies_coefficients: s.cascade.__cascade.stagesRun === 2 &&
          g4Seeded && coeff.gelRatePerS > 0 && coeff.blowRatePerS > 0 &&
          coeff.co2ExpansionCapacity > 0,
        cascade_supplies_mechanics: coeff.bondStiffnessPerS2 > 0 &&
          coeff.bondFailureStrain > 0 && coeff.stressRelaxationPerS > 0 &&
          coeff.imperfectionDispersion > 0,
        no_engine_reaction_rule: true,
        two_simultaneous_reactions: s.meanGel > 0.8 && s.meanBlow > 0.8,
        induction_then_cream: s.creamTimeS !== null &&
          s.creamTimeS >= VALIDATION_ONLY.plausibleCreamTimeRangeS[0] &&
          s.creamTimeS <= VALIDATION_ONLY.plausibleCreamTimeRangeS[1],
        expansion_emerged_plausible:
          finalExpansion >= VALIDATION_ONLY.plausibleExpansionRange[0] &&
          finalExpansion <= VALIDATION_ONLY.plausibleExpansionRange[1],
        milestone_ordering_cream_gel_solid: ordering,
        exotherm_plausible: exothermRiseK >= VALIDATION_ONLY.plausibleExothermRiseK[0] &&
          exothermRiseK <= VALIDATION_ONLY.plausibleExothermRiseK[1],
        hot_core_cool_skin: coreSkinGapK > 1.0,
        gas_trapped_by_curing_matrix: trappedFraction >= 0.7 && s.escapedGas > 0.0,
        // Two separable claims, both stated as physics rather than as a tuned
        // millimetre threshold. (a) The material cured: mean rigidity past the
        // inferred solid conversion. (b) The bulk stopped flowing: its late motion
        // collapsed by at least an ORDER OF MAGNITUDE from its peak, measured
        // against its own rise. The exact ratio is emitted so the reader sees the
        // margin. A cracked flap still hanging by a bond genuinely keeps swinging,
        // so this is bulk (median) motion, with the p95 emitted beside it rather
        // than quietly excluded; the residual few percent is solver residual plus
        // those flaps settling (see ROADMAP.md).
        solidifies_rigid: s.meanRigidity >= 0.9 &&
          lateMedianDisplacement < 0.1 * peakMedianDisplacement,
        porous_sponge_structure: gasFraction > 0.85,
        // --- gravity + imperfection consequences (the point of this upgrade) ---
        imperfection_breaks_symmetry: metrics.leanOffsetMm > 1.0,
        leans_under_gravity: !gravityOn || s.maxLeanDeg > 2.0,
        cracks_under_its_own_weight: !gravityOn || metrics.bondsBroken > 0,
        sheds_pieces: !gravityOn || s.maxDetachedParcels > 0,
        pieces_fall_to_the_ground: !gravityOn || s.maxGroundParcels > 0,
        // Without gravity the bun still grows slightly crooked and can still crack
        // pieces loose -- that is the IMPERFECTION doing it, not the weight, and it
        // is worth seeing separately. What gravity is strictly required for is the
        // FALLING: with g=0 nothing may reach the table, however much came loose.
        // How much gravity amplifies the lean and the cracking is graded by
        // comparing this control against the nominal run.
        no_fall_without_gravity: gravityOn || metrics.groundParcels === 0,
        mass_conserved: foam.ids.length === foam.n &&
          metrics.largestComponentSize + metrics.detachedParcels === foam.n,
        pubchem_structure_consistent_with_geant4: structureConsistent(s.structures),
        uncertainty_emitted: coeff.responseSigma >= 0.0
      }
    });
  }
};

globalThis.TRECH_CONFIG = {
  detector: {
    worldSizeMm: 1600.0,
    worldMaterial: AIR,
    temperatureK: APPARATUS.initialTemperatureK,
    pressureAtm: 1.0
  },
  // A low-energy gamma transported through the actual liquid resin pool each tick:
  // it exercises Geant4 transport/scoring (the per-frame clock + event drive) while
  // the hook layer advances the inferred foaming model. It does not carry the
  // chemistry.
  beam: {
    particle: "gamma",
    energyMeV: 0.06,
    originMm: [0, 25.0, -70.0],
    direction: [0, 0, 1],
    spread: helpers.beamProfiles.spread("ledLamp", { energySpreadFractional: 0.04 })
  },
  run: { nEvents: APPARATUS.outputTicks, seed: 20260725, threads: 1 },
  determinism: { mode: "predictive" },
  materialProbe: {
    enable: true,
    materials: [WATER, POLYOL_SOLUTION, ISOCYANATE_SOLUTION, RESIN_MIX]
  },
  optics: {
    enable: true,
    derive: {
      enable: true,
      mode: "microscale_geant4",
      energyMinEv: 1.6,
      energyMaxEv: 3.2,
      nEnergyBins: 16,
      kkIntegrationMinEv: 50.0,
      kkIntegrationMaxEv: 200000.0,
      kkIntegrationBins: 256,
      writeSpectrum: false
    }
  },
  // The two coefficient stages are always declared: ctx.cascade chains every
  // declared model, so the per-parcel OPERATOR is added only in operator mode.
  // ctx.evolve selects it contextually from its role, element kind and required
  // shared facts; an explicit model list remains available as an override. A
  // reference run's config — and therefore its hash — is unchanged by this.
  models: chemistrySource === "operator" ? [
    { name: "macro_foam_response", scale: "macro",
      path: "data/polyurethane_cascade/macro_foam_response.json" },
    { name: "nano_reagent_descriptors", scale: "nano",
      path: "data/polyurethane_cascade/nano_reagent_descriptors.json" },
    { name: OPERATOR_MODEL, scale: "meso",
      operator_role: OPERATOR_ROLE,
      element_kind: OPERATOR_ELEMENT_KIND,
      required_context_keys: OPERATOR_REQUIRED_CONTEXT,
      path: "data/polyurethane_cascade/meso_reaction_operator.json" }
  ] : [
    { name: "macro_foam_response", scale: "macro",
      path: "data/polyurethane_cascade/macro_foam_response.json" },
    { name: "nano_reagent_descriptors", scale: "nano",
      path: "data/polyurethane_cascade/nano_reagent_descriptors.json" }
  ],
  system: {
    enable: true, mode: "transient", frame: "observer",
    ensemble: "polyurethane_foam",
    volumeMm3: POOL_VOLUME_MM3
  },
  materials: [polyolMaterial, isocyanateMaterial, resinMixMaterial],
  hooks: { maxStepCallbacks: 1, maxEmitsPerCallback: 4, maxEmitPayloadBytes: 1048576 },
  viz: { enable: true, maxTrajectories: 0, sampleEveryNth: 1,
         maxSegmentsPerTrajectory: 16, includeNonOptical: false, recordVertices: true },
  geometry: {
    volumes: [
      geometry.tubeVolume({
        name: "cup_wall", material: CUP,
        innerRadiusMm: APPARATUS.cupInnerRadiusMm,
        outerRadiusMm: APPARATUS.cupInnerRadiusMm + 2.5,
        lengthMm: APPARATUS.cupHeightMm,
        positionMm: [0, APPARATUS.cupHeightMm / 2.0, 0],
        rotationDeg: [90, 0, 0],
        tags: ["cup", "viz_shell", "viz_opacity=0.14"]
      }),
      geometry.tubeVolume({
        name: "table", material: CUP,
        innerRadiusMm: 0.0, outerRadiusMm: APPARATUS.tableRadiusMm, lengthMm: 5.0,
        positionMm: [0, -3.0, 0], rotationDeg: [90, 0, 0],
        tags: ["table", "viz_solid", "viz_color=#20242c"]
      }),
      // The freshly mixed liquid resin pool: the beam medium + optics/composition
      // base. Hidden in viz -- the persistent parcels represent the material.
      geometry.tubeVolume({
        name: "resin_pool", material: RESIN_MIX,
        innerRadiusMm: 0.0, outerRadiusMm: APPARATUS.cupInnerRadiusMm,
        lengthMm: APPARATUS.initialLiquidHeightMm,
        positionMm: [0, APPARATUS.initialLiquidHeightMm / 2.0, 0],
        rotationDeg: [90, 0, 0],
        tags: ["viz_hidden"]
      }),
      // Hidden probe volumes make each prepared solution part of the constructed
      // Geant4 geometry (composition/optics panel).
      geometry.boxVolume({ name: "polyol_probe", material: POLYOL_SOLUTION,
        sizeMm: [4, 4, 4], positionMm: [-260, 0, 0], tags: ["viz_hidden"] }),
      geometry.boxVolume({ name: "isocyanate_probe", material: ISOCYANATE_SOLUTION,
        sizeMm: [4, 4, 4], positionMm: [260, 0, 0], tags: ["viz_hidden"] })
    ]
  }
};
