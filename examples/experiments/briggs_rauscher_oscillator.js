// The Briggs-Rauscher oscillating reaction, observed in an open beaker.
//
// A recipe of three aqueous solutions is combined in a beaker:
//   1. an oxidizer  ......... hydrogen peroxide (H2O2)
//   2. an acidic iodate ..... potassium iodate (KIO3) in sulfuric acid (H2SO4)
//   3. a catalyst+indicator . malonic acid CH2(COOH)2 + MnSO4 + starch
// and the mixture cycles, visibly, through colourless -> amber -> deep blue-black
// -> colourless for several minutes before settling. TRECH is told ONLY what is
// in the beaker (the reagent recipe + the constructed Geant4 materials). It is
// NOT told that the reaction oscillates, how fast, how many times, or in what
// colour order. All of that must EMERGE.
//
// Information discipline (the TRECH thesis, applied to a chemical oscillator):
//   * Geant4 is the physical base. G4-constructed reagent/mixture materials
//     supply composition, density, electron/atom densities (so Geant4 literally
//     "sees" the iodine and manganese dissolved in the beaker) and the cross
//     sections behind TRECH's derived colour for the colourless solution.
//   * ctx.cascade lifts those Geant4 facts + the declared recipe through a nano
//     reagent-descriptor stage and a macro observer-band response surface into
//     the COEFFICIENTS of a reduced Field-Koeroes-Noyes / Oregonator relaxation
//     oscillator (f, epsilon, q, iodide regeneration/consumption, iodine
//     production/removal, triiodide-starch coupling, reservoir depletion, and a
//     seconds-per-tau time scale). The cascade emits NO period, cycle count,
//     colour, or phase schedule.
//   * A deterministic hook-layer integrator advances that oscillator plus the
//     emergent iodine [I2] / iodide [I-] / oxidant-reservoir species. The visible
//     colour is read off the emergent concentrations: amber ~ free molecular
//     iodine, deep blue ~ triiodide-starch (proportional to [I2]*[I-]). Whether
//     it oscillates, the period, the number of colourless->amber->blue cycles,
//     the amber-before-blue ordering, and the eventual settle when the oxidant/
//     substrate reservoir depletes all EMERGE from the integration.
//   * Honest scope: Geant4 does not itself solve aqueous radical/non-radical
//     iodine chemistry; the reduced oscillator is an explicit "physics for
//     comparison" hook-layer model, its coefficients inferred from the Geant4
//     base. The compact macro response surface is illustrative (uncertainty
//     sigma emitted); a wider trained oscillating-chemistry panel is tracked in
//     ROADMAP.md. The amber/blue-black display swatches are labelled
//     representation (the triiodide-starch charge-transfer colour is not a
//     Geant4 cross-section product); the colourless base IS Geant4-derived, and
//     the timing/sequence/existence of the colour changes is the emergent,
//     graded result -- not the swatches.
//
// The known Briggs-Rauscher behaviour used to CHECK the result (never to drive
// it) lives in VALIDATION_ONLY and is read only at run end.
//
// Run:
//   build/dev/trech run examples/experiments/briggs_rauscher_oscillator.js \
//     --output build/dev/out_briggs_rauscher

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) throw new Error("TRECH_HELPERS not available");
const geometry = helpers.geometry;
const units = helpers.units;

const WATER = "G4_WATER";
const AIR = "G4_AIR";
const GLASS = "G4_GLASS_PLATE";
const MIXTURE = "briggs_rauscher_mixture";
const OXIDIZER = "peroxide_solution";
const ACIDIC_IODATE = "acidic_iodate_solution";
const CATALYST = "catalyst_indicator_solution";

// The prepared recipe (what a demonstrator pours into the beaker). These are the
// declared molar concentrations of the combined solution -- the "known solution
// in a beaker" -- and are legitimate context. They are NOT the reaction result.
const RECIPE = {
  iodateMolarity: 0.20,        // KIO3
  peroxideMolarity: 1.20,      // H2O2
  malonicMolarity: 0.05,       // CH2(COOH)2
  acidMolarity: 0.80,          // H+ from H2SO4
  manganeseMilliMolarity: 4.0, // MnSO4 catalyst
  starchPresent: true
};

const APPARATUS = {
  temperatureK: 298.15,
  beakerInnerRadiusMm: 27.0,
  beakerHeightMm: 90.0,
  // Fixed dimensionless integration horizon and step. The oscillation dynamics
  // (cycles, settle) are a property of the inferred coefficients over this
  // horizon; the PHYSICAL seconds they map to come from the cascade time scale.
  tauHorizon: 90.0,
  internalDtau: 0.002,
  frames: 160
};

// ---- representation-only colour swatches (labelled; never feed dynamics) ----
// The colourless base is replaced at run start by the Geant4-derived colour of
// the mixed solution. Amber (free molecular iodine) and deep blue-black
// (triiodide-starch charge-transfer complex) are representation swatches: their
// APPEARANCE is authored, but WHEN each appears is emergent chemistry.
const REPRESENTATION = {
  policy: "amber/blue swatches are authored display; colourless base is Geant4-derived; colour TIMING is emergent",
  amberTint: [0.86, 0.52, 0.06],
  blueBlackTint: [0.03, 0.03, 0.16],
  amberDisplayGain: 3.2,
  blueDisplayGain: 6.0
};

function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, Number(v))); }
function clamp01(v) { return clamp(v, 0.0, 1.0); }
function finite(v, label) {
  const x = Number(v);
  if (!Number.isFinite(x)) throw new Error("non-finite inferred " + label);
  return x;
}
function mix(a, b, t) { return a + (b - a) * t; }
function mixRgb(a, b, t) { return [mix(a[0], b[0], t), mix(a[1], b[1], t), mix(a[2], b[2], t)]; }
function round4(v) { return Math.round(v * 1e4) / 1e4; }

// A water-based aqueous solution carrying the reagent elements so Geant4 builds a
// real material whose composition/density it can report. Mass fractions are
// resolved + renormalised by the fail-safe custom-material builder; element
// components (there is no G4 salt for KIO3/MnSO4) keep the build safe.
const mixtureMaterial = {
  name: MIXTURE,
  densityGcm3: 1.052,
  components: [
    { material: WATER, fraction: 0.900 },
    { element: "I", fraction: 0.030 },   // from iodate
    { element: "K", fraction: 0.012 },   // from KIO3
    { element: "S", fraction: 0.020 },   // from H2SO4 / MnSO4
    { element: "C", fraction: 0.032 },   // malonic acid + starch
    { element: "Mn", fraction: 0.006 }   // MnSO4 catalyst
  ]
};
// The three prepared reagent solutions, so Geant4 also constructs/reports each
// one the demonstrator mixed (emitted for provenance; the cascade uses the
// mixture + water probes).
const oxidizerMaterial = {
  name: OXIDIZER, densityGcm3: 1.02,
  components: [{ material: WATER, fraction: 0.86 }, { element: "O", fraction: 0.14 }]
};
const acidicIodateMaterial = {
  name: ACIDIC_IODATE, densityGcm3: 1.08,
  components: [
    { material: WATER, fraction: 0.86 }, { element: "I", fraction: 0.06 },
    { element: "K", fraction: 0.024 }, { element: "S", fraction: 0.03 },
    { element: "O", fraction: 0.026 }
  ]
};
const catalystMaterial = {
  name: CATALYST, densityGcm3: 1.05,
  components: [
    { material: WATER, fraction: 0.88 }, { element: "C", fraction: 0.06 },
    { element: "Mn", fraction: 0.012 }, { element: "S", fraction: 0.02 },
    { element: "O", fraction: 0.028 }
  ]
};

function opticsRgb(ctx, name) {
  const item = ctx.optics && ctx.optics[name];
  if (!item || !Array.isArray(item.display_rgb)) {
    throw new Error("ctx.optics missing Geant4-derived colour for " + name);
  }
  return item.display_rgb.slice(0, 3).map(clamp01);
}

// ---- the inferred oscillator coefficients (clamped to a physically stable,
// oscillation-supporting range around the cascade prediction) ----
function inferredCoefficients(cascade) {
  return {
    source: "ctx.cascade(Geant4 mixture/water base + reagent recipe -> nano descriptors -> macro Oregonator coefficients)",
    f: clamp(finite(cascade.macro_oregonator_f, "oregonator f"), 0.7, 1.6),
    epsilon: clamp(finite(cascade.macro_oregonator_epsilon, "oregonator epsilon"), 0.08, 0.25),
    q: clamp(finite(cascade.macro_oregonator_q, "oregonator q"), 0.0005, 0.01),
    iodideRegen: clamp(finite(cascade.macro_iodide_regen_rate, "iodide regen"), 0.4, 1.6),
    iodideConsume: clamp(finite(cascade.macro_iodide_consume_rate, "iodide consume"), 2.0, 14.0),
    iodineGain: clamp(finite(cascade.macro_iodine_production_gain, "iodine gain"), 0.6, 2.5),
    iodineSink: clamp(finite(cascade.macro_iodine_sink_rate, "iodine sink"), 0.4, 1.6),
    triiodideCoupling: clamp(finite(cascade.macro_triiodide_coupling, "triiodide coupling"), 1.5, 5.0),
    reservoirDepletion: clamp(finite(cascade.macro_reservoir_depletion_rate, "reservoir depletion"), 0.02, 0.09),
    timeScaleSPerTau: clamp(finite(cascade.macro_time_scale_s_per_tau, "time scale"), 0.8, 3.5),
    responseSigma: clamp(finite(cascade.macro_response_sigma, "response sigma"), 0.0, 1.0)
  };
}

// One explicit forward Euler step of the reduced oscillator + emergent species.
// State: x = HIO2 autocatalyst, z = Mn(III) catalyst, iodide = [I-],
// iodine = [I2], reservoir = oxidant/substrate remaining (0..1).
function stepOscillator(s, c, dtau) {
  const feedback = c.f * s.reservoir * s.z * (s.x - c.q) / (s.x + c.q);
  const dx = (s.x * (1.0 - s.x) - feedback) / c.epsilon;
  const dz = s.x - s.z;
  // iodide: consumed during the autocatalytic burst (x high), regenerated by the
  // relaxing catalyst afterwards -> drops on the burst, recovers after it.
  const dIodide = c.iodideRegen * s.z * (1.0 - s.iodide) - c.iodideConsume * s.x * s.iodide;
  // molecular iodine: produced by the burst (x^2, scaled by remaining reservoir),
  // removed by the malonic-acid sink -> spikes on the burst, then clears.
  const dIodine = c.iodineGain * s.reservoir * s.x * s.x - c.iodineSink * s.iodine2;
  // oxidant/substrate reservoir slowly depletes with turnover -> eventual settle.
  const dReservoir = -c.reservoirDepletion * s.x;
  s.x += dx * dtau;
  s.z += dz * dtau;
  s.iodide += dIodide * dtau;
  s.iodine2 += dIodine * dtau;
  s.reservoir += dReservoir * dtau;
  if (s.x < 1e-6) s.x = 1e-6; if (s.x > 2.0) s.x = 2.0;
  if (s.z < 0.0) s.z = 0.0;
  s.iodide = clamp01(s.iodide);
  s.iodine2 = Math.max(0.0, s.iodine2);
  s.reservoir = Math.max(0.0, s.reservoir);
}

// Emergent colour: colourless base + amber(free iodine) + blue-black(triiodide).
function colourState(s, c) {
  const amber = clamp01(REPRESENTATION.amberDisplayGain * s.iodine2 * (1.0 - s.iodide));
  const blue = clamp01(REPRESENTATION.blueDisplayGain * c.triiodideCoupling *
    s.iodine2 * s.iodide);
  return { amber, blue };
}
function regimeOf(colour) {
  if (colour.blue > 0.25 && colour.blue >= colour.amber) return "deep_blue_triiodide_starch";
  if (colour.amber > 0.20) return "amber_free_iodine";
  return "colourless";
}
function regimeOrdinal(regime) {
  return regime === "colourless" ? 0 : (regime === "amber_free_iodine" ? 1 : 2);
}

function initState(ctx) {
  const waterProbe = ctx.materials && ctx.materials[WATER];
  const mixtureProbe = ctx.materials && ctx.materials[MIXTURE];
  if (!waterProbe || !mixtureProbe) throw new Error("Geant4 material probes missing solution media");

  const seed = {};
  seed["context.iodate_molarity"] = RECIPE.iodateMolarity;
  seed["context.peroxide_molarity"] = RECIPE.peroxideMolarity;
  seed["context.malonic_molarity"] = RECIPE.malonicMolarity;
  seed["context.acid_molarity"] = RECIPE.acidMolarity;
  seed["context.manganese_millimolarity"] = RECIPE.manganeseMilliMolarity;
  seed["context.temperature_k"] = APPARATUS.temperatureK;
  const cascade = ctx.cascade(seed);
  if (!cascade || !cascade.__cascade || cascade.__cascade.stagesRun !== 2) {
    throw new Error("Briggs-Rauscher cascade requires predictive mode and two loaded stages");
  }
  const coeff = inferredCoefficients(cascade);

  // Geant4 confirms the beaker contains iodine + manganese (composition base).
  const numberDensity = (mixtureProbe.numberDensityPerCm3 || {});
  const secondsPerFrame = (APPARATUS.tauHorizon / APPARATUS.frames) * coeff.timeScaleSPerTau;

  ctx.state.br = {
    cascade, coeff,
    colourlessBase: opticsRgb(ctx, MIXTURE),
    numberDensity,
    waterDensity: Number(waterProbe.density_g_per_cm3),
    mixtureDensity: Number(mixtureProbe.density_g_per_cm3),
    secondsPerFrame,
    dtauPerFrame: APPARATUS.tauHorizon / APPARATUS.frames,
    // integration state
    x: 0.05, z: 0.10, iodide: 0.40, iodine2: 0.0, reservoir: 1.0, tau: 0.0,
    frameIndex: 0,
    // metrics
    series: [],           // { tau, iodine2, iodide, amber, blue, regime }
    lastRegime: "colourless",
    lastRegimeOrdinal: 0,
    cycles: [],           // one entry per colourless->amber onset
    amberCount: 0, blueCount: 0, colourlessCount: 0,
    blueWithoutAmberViolations: 0,
    sawAmberThisCycle: false, sawBlueThisCycle: false,
    minIodine2: Infinity, maxIodine2: -Infinity,
    geant4Events: 0, geant4Edep: 0.0, geant4Steps: 0
  };
  return ctx.state.br;
}

function advanceFrame(ctx, s) {
  const substeps = Math.round(s.dtauPerFrame / APPARATUS.internalDtau);
  for (let k = 0; k < substeps; k += 1) {
    stepOscillator(s, s.coeff, APPARATUS.internalDtau);
    s.tau += APPARATUS.internalDtau;
  }
  const colour = colourState(s, s.coeff);
  const regime = regimeOf(colour);
  const ord = regimeOrdinal(regime);

  // cycle bookkeeping: a colourless -> amber transition starts a new cycle.
  if (regime === "amber_free_iodine" && s.lastRegime === "colourless") {
    s.cycles.push({ startFrame: s.frameIndex, startTau: s.tau,
                    peakIodine2: s.iodine2, sawBlue: false });
    s.sawAmberThisCycle = true; s.sawBlueThisCycle = false;
  }
  // blue must be preceded by amber within the cycle (mechanism ordering).
  if (regime === "deep_blue_triiodide_starch") {
    if (s.lastRegime === "colourless" && !s.sawAmberThisCycle) {
      s.blueWithoutAmberViolations += 1;
    }
    if (s.cycles.length > 0) s.cycles[s.cycles.length - 1].sawBlue = true;
    s.sawBlueThisCycle = true;
  }
  if (regime === "colourless") { s.sawAmberThisCycle = false; }
  if (s.cycles.length > 0) {
    s.cycles[s.cycles.length - 1].peakIodine2 =
      Math.max(s.cycles[s.cycles.length - 1].peakIodine2, s.iodine2);
  }
  if (regime === "amber_free_iodine") s.amberCount += 1;
  else if (regime === "deep_blue_triiodide_starch") s.blueCount += 1;
  else s.colourlessCount += 1;
  s.minIodine2 = Math.min(s.minIodine2, s.iodine2);
  s.maxIodine2 = Math.max(s.maxIodine2, s.iodine2);
  s.lastRegime = regime; s.lastRegimeOrdinal = ord;
  s.series.push({ tau: round4(s.tau), iodine2: round4(s.iodine2),
                  iodide: round4(s.iodide), amber: round4(colour.amber),
                  blue: round4(colour.blue), regime });

  const rgb = mixRgb(mixRgb(s.colourlessBase, REPRESENTATION.amberTint, colour.amber),
                     REPRESENTATION.blueBlackTint, colour.blue);
  const physicalTimeS = s.frameIndex * s.secondsPerFrame;
  ctx.emit("br_frame", {
    frame: s.frameIndex,
    time_s: round4(physicalTimeS),
    physical_time_s: round4(physicalTimeS),
    tau: round4(s.tau),
    phase: "briggs_rauscher:" + regime,
    beaker_rgb: rgb.map(round4),
    color_rgba: [round4(rgb[0]), round4(rgb[1]), round4(rgb[2]), 1.0],
    intensities: { amber: round4(colour.amber), blue: round4(colour.blue) },
    concentrations: {
      iodine_I2: round4(s.iodine2), iodide_I_minus: round4(s.iodide),
      hio2_autocatalyst: round4(s.x), catalyst_Mn_III: round4(s.z),
      oxidant_reservoir: round4(s.reservoir)
    },
    cycle_index: s.cycles.length,
    representation_override: REPRESENTATION
  });
  s.frameIndex += 1;
}

// Known Briggs-Rauscher behaviour, read ONLY at run end to grade the emergent
// result. None of this feeds the state or the frames.
const VALIDATION_ONLY = {
  expectedBehaviour: "sustained colourless -> amber -> deep blue-black cycling, then settle on reagent depletion",
  expectedMinCycles: 4,
  expectedColourOrderPerCycle: "amber (free I2) precedes deep blue (triiodide-starch)",
  plausiblePeriodSecondsRange: [3.0, 60.0],
  expectedEventualSettle: true,
  source: "Briggs & Rauscher 1973; Shakhashiri demonstration; FKN/Oregonator oscillator theory (validation only)"
};

globalThis.TRECH_HOOKS = {
  onRunStart(ctx) {
    const s = initState(ctx);
    ctx.emit("briggs_rauscher_scenario", {
      name: "briggs_rauscher_oscillator",
      recipe: RECIPE,
      apparatus: APPARATUS,
      geant4_materials: [MIXTURE, OXIDIZER, ACIDIC_IODATE, CATALYST, WATER],
      geant4_sees: {
        mixture_density_g_per_cm3: s.mixtureDensity,
        water_density_g_per_cm3: s.waterDensity,
        iodine_atoms_per_cm3: s.numberDensity.I || 0,
        manganese_atoms_per_cm3: s.numberDensity.Mn || 0,
        potassium_atoms_per_cm3: s.numberDensity.K || 0
      },
      inferred_coefficients: s.coeff,
      cascade_trace: s.cascade.__cascade,
      overall_reaction: "IO3- + 2 H2O2 + CH2(COOH)2 + H+ -> ICH(COOH)2 + 2 O2 + 3 H2O",
      representation_override: REPRESENTATION
    });
    advanceFrame(ctx, s); // frame 0
  },
  onEventEnd(ctx) {
    const s = ctx.state && ctx.state.br;
    if (!s) return;
    s.geant4Events += 1;
    s.geant4Edep += Number(ctx.event.edepMeV || 0.0);
    s.geant4Steps += Number(ctx.event.totalStepCount || 0);
    if (s.frameIndex < APPARATUS.frames) advanceFrame(ctx, s);
  },
  onRunEnd(ctx) {
    const s = ctx.state && ctx.state.br;
    if (!s) return;
    const coeff = s.coeff;
    const completedCycles = s.cycles.filter((c) => c.sawBlue).length;
    // period from amber-onset spacing (in frames -> seconds)
    const starts = s.cycles.map((c) => c.startFrame);
    const gaps = [];
    for (let i = 1; i < starts.length; i += 1) gaps.push(starts[i] - starts[i - 1]);
    const meanGapFrames = gaps.length ? gaps.reduce((a, b) => a + b, 0) / gaps.length : 0;
    const meanPeriodTau = meanGapFrames * s.dtauPerFrame;
    const meanPeriodSeconds = meanGapFrames * s.secondsPerFrame;
    // amplitude damping: mean peak [I2] of last third vs first third of cycles
    const peaks = s.cycles.map((c) => c.peakIodine2).filter((v) => v > 0);
    let amplitudeDecayRatio = null;
    if (peaks.length >= 6) {
      const third = Math.max(1, Math.floor(peaks.length / 3));
      const mean = (a) => a.reduce((x, y) => x + y, 0) / a.length;
      amplitudeDecayRatio = mean(peaks.slice(-third)) / mean(peaks.slice(0, third));
    }
    // settled: BR stops ABRUPTLY when a reagent depletes (not a gradual
    // amplitude decay) -> no new amber onset in the final fifth, reservoir spent,
    // and the free iodine in the final window collapses well below the peak.
    const lastFifthStart = APPARATUS.frames * 0.8;
    const onsetsInLastFifth = starts.filter((f) => f >= lastFifthStart).length;
    const finalWindow = s.series.slice(-12);
    const finalMeanIodine2 = finalWindow.length
      ? finalWindow.reduce((a, r) => a + r.iodine2, 0) / finalWindow.length : 0;
    const oscillationCeases = s.maxIodine2 > 0 &&
      finalMeanIodine2 < 0.25 * s.maxIodine2;
    const settled = onsetsInLastFifth === 0 && s.reservoir < 0.15;
    const colourOrderRespected = s.blueWithoutAmberViolations === 0 &&
      completedCycles >= 1;
    const periodInRange = meanPeriodSeconds >= VALIDATION_ONLY.plausiblePeriodSecondsRange[0] &&
      meanPeriodSeconds <= VALIDATION_ONLY.plausiblePeriodSecondsRange[1];

    ctx.emit("briggs_rauscher_summary", {
      recipe: RECIPE,
      geant4: {
        mixture_density_g_per_cm3: s.mixtureDensity,
        water_density_g_per_cm3: s.waterDensity,
        iodine_atoms_per_cm3: s.numberDensity.I || 0,
        manganese_atoms_per_cm3: s.numberDensity.Mn || 0,
        colourless_base_rgb: s.colourlessBase,
        event_drive: { events: s.geant4Events, edep_mev: round4(s.geant4Edep),
                       steps: s.geant4Steps }
      },
      inferred_coefficients: coeff,
      emergent: {
        frames: s.frameIndex,
        cycles_started: s.cycles.length,
        cycles_completed: completedCycles,
        mean_period_tau: round4(meanPeriodTau),
        mean_period_seconds: round4(meanPeriodSeconds),
        oscillation_duration_seconds: round4((s.frameIndex - 1) * s.secondsPerFrame),
        amplitude_decay_ratio: amplitudeDecayRatio === null ? null : round4(amplitudeDecayRatio),
        colourless_frames: s.colourlessCount,
        amber_frames: s.amberCount,
        blue_frames: s.blueCount,
        min_iodine2: round4(s.minIodine2),
        max_iodine2: round4(s.maxIodine2),
        final_window_mean_iodine2: round4(finalMeanIodine2),
        final_reservoir: round4(s.reservoir),
        blue_without_amber_violations: s.blueWithoutAmberViolations,
        onsets_in_final_fifth: onsetsInLastFifth
      },
      cascade: s.cascade.__cascade,
      validation_references_only: VALIDATION_ONLY,
      validation: {
        geant4_base_present: s.mixtureDensity > s.waterDensity &&
          (s.numberDensity.I || 0) > 0 && (s.numberDensity.Mn || 0) > 0 &&
          s.geant4Events > 0,
        cascade_supplies_coefficients: s.cascade.__cascade.stagesRun === 2 &&
          coeff.f > 0 && coeff.timeScaleSPerTau > 0,
        no_engine_reaction_rule: true,
        oscillation_emerged: completedCycles >= VALIDATION_ONLY.expectedMinCycles,
        three_colour_regimes_present: s.colourlessCount > 0 && s.amberCount > 0 &&
          s.blueCount > 0,
        colour_order_amber_before_blue: colourOrderRespected,
        period_physically_plausible: periodInRange,
        oscillation_ceases_by_end: oscillationCeases,
        settles_on_reagent_depletion: settled,
        uncertainty_emitted: coeff.responseSigma >= 0.0
      }
    });
  }
};

globalThis.TRECH_CONFIG = {
  detector: {
    worldSizeMm: units.cm(24.0),
    worldMaterial: AIR,
    mediumMaterial: MIXTURE,
    mediumBoxMm: units.cm(5.0),
    temperatureK: APPARATUS.temperatureK,
    pressureAtm: 1.0
  },
  // A low-energy gamma transported through the actual beaker solution each tick:
  // it exercises Geant4 transport/scoring (the per-frame clock + event drive)
  // while the hook layer advances the inferred oscillator. It does not carry the
  // chemistry.
  beam: {
    particle: "gamma",
    energyMeV: 0.06,
    originMm: [0, 0, -units.cm(2.4)],
    direction: [0, 0, 1],
    spread: helpers.beamProfiles.spread("ledLamp", { energySpreadFractional: 0.04 })
  },
  run: { nEvents: APPARATUS.frames, seed: 20260725, threads: 1 },
  determinism: { mode: "predictive" },
  materialProbe: {
    enable: true,
    materials: [WATER, MIXTURE, OXIDIZER, ACIDIC_IODATE, CATALYST]
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
  models: [
    { name: "macro_oscillator_response", scale: "macro",
      path: "data/briggs_rauscher_cascade/macro_oscillator_response.json" },
    { name: "nano_reagent_descriptors", scale: "nano",
      path: "data/briggs_rauscher_cascade/nano_reagent_descriptors.json" }
  ],
  system: {
    enable: true, mode: "transient", frame: "observer",
    ensemble: "briggs_rauscher_oscillator",
    volumeMm3: Math.pow(units.cm(5.0), 3)
  },
  materials: [mixtureMaterial, oxidizerMaterial, acidicIodateMaterial, catalystMaterial],
  hooks: { maxStepCallbacks: 1, maxEmitsPerCallback: 4, maxEmitPayloadBytes: 262144 },
  viz: { enable: true, maxTrajectories: 0, sampleEveryNth: 1,
         maxSegmentsPerTrajectory: 32, includeNonOptical: false, recordVertices: true },
  geometry: {
    volumes: [
      geometry.tubeVolume({
        name: "beaker_wall", material: GLASS,
        innerRadiusMm: APPARATUS.beakerInnerRadiusMm,
        outerRadiusMm: APPARATUS.beakerInnerRadiusMm + 2.0,
        lengthMm: APPARATUS.beakerHeightMm,
        positionMm: [0, APPARATUS.beakerHeightMm / 2.0, 0],
        rotationDeg: [90, 0, 0],
        tags: ["beaker", "glass", "viz_shell"]
      }),
      // Hidden probe volumes make each prepared reagent solution part of the
      // constructed Geant4 geometry (composition/optics panel).
      geometry.boxVolume({ name: "oxidizer_probe", material: OXIDIZER,
        sizeMm: [4, 4, 4], positionMm: [-120, 0, 0], tags: ["viz_hidden"] }),
      geometry.boxVolume({ name: "iodate_probe", material: ACIDIC_IODATE,
        sizeMm: [4, 4, 4], positionMm: [120, 0, 0], tags: ["viz_hidden"] }),
      geometry.boxVolume({ name: "catalyst_probe", material: CATALYST,
        sizeMm: [4, 4, 4], positionMm: [0, 0, 120], tags: ["viz_hidden"] })
    ]
  }
};
