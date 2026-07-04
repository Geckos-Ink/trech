// Validation scenario (Stage 1): nuclear magnetic resonance of a water cube.
//
// GOAL: reproduce the first steps of an MRI/NMR experiment inside TRECH --
//   1. a 5 cm^3 cube of water,
//   2. a resonance apparatus (static field B0 + a swept RF pulse),
//   3. detection of the "output" RF photons (the free-induction-decay signal) --
// WITHOUT telling the simulation the answer. The resonance frequency is
// DISCOVERED from a driven frequency sweep, and the signal strength is scaled by
// the proton (1H) density Geant4 reports for the material -- not a hard-coded
// number. The textbook "know-what" (gamma/2pi = 42.5775 MHz/T, the literature
// water proton density) is used ONLY to grade the discovery, and the gap-to-truth
// is measured and emitted.
//
// HONEST SCOPE (same contract as the MD-water, CNT-band-structure and
// electrolysis scenarios): Geant4 does NOT simulate nuclear spin. What Geant4
// actually does here is real and load-bearing:
//   * builds the 5 cm^3 water phantom + a copper receiver-coil volume,
//   * supplies the 1H number density from the constructed G4Material
//     (ctx.materials -- the new material-probe engine surface), which sets the
//     equilibrium magnetization M0 and therefore the signal amplitude,
//   * supplies a G4EmCalculator interaction anchor (analytic beer_lambert), and
//   * transports a probe beam every event, acting as the per-event clock.
// The spin dynamics themselves -- Larmor precession, the RF pulse, the FID and
// the T2* decay -- are the deterministic hook-layer "physics for comparison",
// integrated from the Bloch equations. We feed the proton gyromagnetic ratio
// gamma (a particle constant, exactly as the MD scenarios feed the SPC/E force
// field); the Lorentzian resonance peak, the FID and the proton-density signal
// scaling then EMERGE and are validated against the known values.
//
// Stage 2 (virtual tissues -> proton-density/relaxation contrast) builds on the
// same ctx.materials surface with more materials; see mr_summary.tissue_preview,
// which already lists the Geant4-derived proton-density contrast for a few ICRP
// tissues so the contrast mechanism is visible before Stage 2 lands.
//
// Run:
//   trech run examples/experiments/testscenario_magnetic_resonance.js \
//        --events 236 --output build/dev/out_mr
// Inspect trech_hook_emits.jsonl -> mr_summary (discovered Larmor, recovered
// gamma, proton density, T2*, detected RF quanta, validation flags) and
// trech_scores.jsonl -> material_probes (Geant4 1H density).

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}
const units = helpers.units;
const geometry = helpers.geometry;

// ---------------------------------------------------------------------------
// Physical constants the apparatus is ALLOWED to know: fundamental particle
// constants and machine settings. None of these encode "water behaviour".
// ---------------------------------------------------------------------------
const PHYS = {
  // CODATA proton gyromagnetic ratio (rad/s/T). A property of the proton, like
  // the electron charge -- NOT an H2O-specific quantity. gamma/2pi = 42.5775 MHz/T.
  gammaProton: 2.6752218708e8,
  hbar: 1.054571817e-34, // J*s
  kB: 1.380649e-23       // J/K
};

// The textbook truth, used ONLY for grading (never fed into the discovery).
const TRUTH = {
  gammaOver2piMHzPerT: 42.577478518, // proton gyromagnetic ratio / 2pi
  // Pure water at 1 g/cm^3: (1/18.015)*N_A*2 H = 6.686e22 protons/cm^3.
  waterProtonPerCm3: 6.686e22
};

// Machine + sequence settings (the "magnetic pulse etc." the user allows us to
// set explicitly). B0 fixes the field; the sweep brackets a broad band that
// merely CONTAINS the (unknown-to-the-sweep) Larmor line.
const MACHINE = {
  b0Tesla: 1.5,                  // static field
  sweepLoMHz: 30.0,              // broad bracket -- deliberately NOT centred on f0
  sweepHiMHz: 100.0,
  sweepPoints: 140,             // one Geant4 event per sweep sample
  pulseDurationS: 1.0e-7,       // 100 ns hard pulse (sets the excitation bandwidth)
  blochStepsPerPulse: 300,      // RK4 substeps through the pulse
  t2StarS: 8.0e-3,              // generic field-inhomogeneity dephasing (same for all)
  fidSamples: 96,               // one Geant4 event per FID sample
  fidWindowT2Star: 3.5,         // acquire out to 3.5*T2*
  measurementNoise: 0.004       // deterministic receiver noise (fraction of peak)
};

const N_SWEEP = MACHINE.sweepPoints;
const N_FID = MACHINE.fidSamples;
const TOTAL_TICKS = N_SWEEP + N_FID;

// Reference ICRP tissues probed alongside water: their Geant4-derived proton
// densities preview the Stage-2 contrast (fat is proton-rich, cortical bone
// proton-poor). Listing them here only asks the engine to report composition; it
// does not change Stage-1 physics (the phantom is water).
const TISSUE_PREVIEW = [
  "G4_ADIPOSE_TISSUE_ICRP",
  "G4_MUSCLE_SKELETAL_ICRP",
  "G4_BRAIN_ICRP",
  "G4_BONE_CORTICAL_ICRP"
];

// 5 cm^3 water cube -> side = cbrt(5) cm = 17.0998 mm.
const cubeSideMm = units.cm(Math.cbrt(5.0));
const worldSizeMm = units.cm(6.0);

const cfg = {
  detector: {
    worldSizeMm: worldSizeMm,
    worldMaterial: helpers.materialAliases.air,
    mediumBoxMm: cubeSideMm,
    mediumMaterial: helpers.materialAliases.water,
    temperatureK: 310.15, // body temperature (MRI context); M0 ~ 1/T
    pressureAtm: 1.0
  },
  // Real Geant4 probe: a low-energy gamma pencil that traverses the phantom every
  // event, giving genuine transport + a per-event clock. RF (7 m wavelength) is
  // not transportable, so the resonance signal is hook-layer -- the beam is the
  // clock/anchor, exactly as in the other hook-driven scenarios.
  beam: {
    particle: "gamma",
    energyMeV: 0.05,
    originMm: [0, 0, -0.45 * worldSizeMm],
    direction: [0, 0, 1]
  },
  run: { nEvents: TOTAL_TICKS, seed: 20260704, threads: 1 },
  determinism: { mode: "strict" },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "magnetic_resonance_water",
    volumeMm3: Math.pow(cubeSideMm, 3)
  },
  // Geant4 material-composition probe: expose water + the reference tissues to
  // hooks as ctx.materials and to trech_scores.jsonl as material_probes. This is
  // where the proton density comes from -- never hard-coded in this scenario.
  materialProbe: {
    enable: true,
    materials: TISSUE_PREVIEW
  },
  // A real G4EmCalculator interaction anchor for the phantom (also the mu the
  // Stage-2 relaxation proxy will scale from).
  analytic: {
    enable: true,
    checks: [
      {
        type: "beer_lambert",
        label: "mr_water_probe_interaction",
        particle: "gamma",
        energyMeV: 0.05,
        material: helpers.materialAliases.water,
        pathLengthMm: cubeSideMm,
        toleranceRel: 1.0
      }
    ]
  },
  geometry: {
    volumes: [
      // Copper receiver coil ringing the phantom: the pickup-coil geometry whose
      // real NMR signal is the hook-layer FID. scoreEdep gives a real Geant4
      // detection tally (volume_edep_mev) for whatever scatter it catches.
      geometry.tubeVolume({
        name: "receiver_coil",
        material: "G4_Cu",
        innerRadiusMm: 13.0,
        outerRadiusMm: 14.0,
        lengthMm: cubeSideMm,
        parent: "world",
        scoreEdep: true,
        tags: ["receiver_coil", "detector"]
      })
    ]
  },
  hooks: {
    maxEmitsPerCallback: 8,
    maxEmitPayloadBytes: 262144
  }
};

// ---------------------------------------------------------------------------
// Bloch-equation machinery (deterministic hook-layer physics).
// ---------------------------------------------------------------------------

// Box-Muller gaussian from the deterministic hook RNG.
function gaussian(rng) {
  let u1 = rng.uniform();
  if (u1 <= 1e-12) { u1 = 1e-12; }
  const u2 = rng.uniform();
  return Math.sqrt(-2.0 * Math.log(u1)) * Math.cos(2.0 * Math.PI * u2);
}

// Integrate the Bloch equations through a hard RF pulse, in the frame rotating at
// the transmit frequency (deltaOmega = omega0 - omega_rf, omega1 = gamma*B1 along
// x). Relaxation is negligible over the ~100 ns pulse, so it is dropped here.
// Returns the transverse magnetization magnitude |Mxy| starting from equilibrium
// (0,0,1). On resonance (deltaOmega=0) a 90 deg pulse gives |Mxy| = 1; far off
// resonance the spin is barely tipped -> the response is a peak centred on the
// Larmor line. This is the driven-spin dynamics that DISCOVER f0.
function blochPulseResponseMxy(deltaOmega, omega1, tau, nSteps) {
  const dt = tau / nSteps;
  let mx = 0.0, my = 0.0, mz = 1.0;
  const deriv = (x, y, z) => [
    deltaOmega * y,
    -deltaOmega * x + omega1 * z,
    -omega1 * y
  ];
  for (let i = 0; i < nSteps; i += 1) {
    const k1 = deriv(mx, my, mz);
    const k2 = deriv(mx + 0.5 * dt * k1[0], my + 0.5 * dt * k1[1], mz + 0.5 * dt * k1[2]);
    const k3 = deriv(mx + 0.5 * dt * k2[0], my + 0.5 * dt * k2[1], mz + 0.5 * dt * k2[2]);
    const k4 = deriv(mx + dt * k3[0], my + dt * k3[1], mz + dt * k3[2]);
    mx += (dt / 6.0) * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]);
    my += (dt / 6.0) * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]);
    mz += (dt / 6.0) * (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2]);
  }
  return Math.sqrt(mx * mx + my * my);
}

// Equilibrium nuclear magnetization (Curie law, SI A/m) for spin-1/2 protons at
// number density nPerM3 in field b0 at temperature T. M0 ~ N -> this is the ONLY
// place the Geant4 proton density enters the signal amplitude.
function curieMagnetization(nPerM3, b0, tempK) {
  const g = PHYS.gammaProton;
  return (nPerM3 * g * g * PHYS.hbar * PHYS.hbar * b0) / (4.0 * PHYS.kB * tempK);
}

function sweepFrequencyMHz(index) {
  const frac = N_SWEEP > 1 ? index / (N_SWEEP - 1) : 0.0;
  return MACHINE.sweepLoMHz + (MACHINE.sweepHiMHz - MACHINE.sweepLoMHz) * frac;
}

// Precise Larmor line from the FID carrier. The transverse magnetization
// precesses in the lab frame at exactly the Larmor frequency; the receiver coil
// picks up that oscillation. We MEASURE its frequency (hysteresis up-crossing
// timing over a long window) -- exactly how real NMR reads the line, and far
// sharper than the apparatus-broadened excitation sweep. The FID is generated at
// omega0 = gamma*B0 (gamma = proton constant, B0 = machine), so recovering that
// frequency demonstrates the Larmor relation rather than assuming it.
function measureLarmorFromFidMHz(state, rng) {
  const omega0 = state.omega0;
  const tWin = 30.0e-6;                                   // ~2000 cycles at 64 MHz
  const dt = 1.0 / (8.0 * MACHINE.sweepHiMHz * 1.0e6);     // Nyquist-safe for the band
  const nSamp = Math.floor(tWin / dt);
  const thr = 0.05;                                        // hysteresis >> receiver noise
  let armed = false, count = 0, firstT = -1.0, lastT = -1.0;
  for (let i = 0; i < nSamp; i += 1) {
    const t = i * dt;
    let s = Math.exp(-t / MACHINE.t2StarS) * Math.cos(omega0 * t);
    s += gaussian(rng) * MACHINE.measurementNoise * 0.5;
    if (s < -thr) {
      armed = true;
    } else if (s > thr && armed) {
      count += 1;
      if (firstT < 0) { firstT = t; }
      lastT = t;
      armed = false;
    }
  }
  const freqHz = (count >= 2 && lastT > firstT)
    ? (count - 1) / (lastT - firstT)  // whole periods between first/last up-crossing
    : count / tWin;
  return freqHz / 1.0e6;
}

// Parabolic peak interpolation over the sampled spectrum -> sub-bin frequency.
// Used for the COARSE spectroscopy peak (apparatus-bandwidth-limited); the precise
// line comes from measureLarmorFromFidMHz above.
function findResonancePeakMHz(spectrum) {
  let peakIdx = 0;
  for (let i = 1; i < spectrum.length; i += 1) {
    if (spectrum[i].response > spectrum[peakIdx].response) {
      peakIdx = i;
    }
  }
  const fPeak = spectrum[peakIdx].freqMHz;
  if (peakIdx > 0 && peakIdx < spectrum.length - 1) {
    const y0 = spectrum[peakIdx - 1].response;
    const y1 = spectrum[peakIdx].response;
    const y2 = spectrum[peakIdx + 1].response;
    const denom = y0 - 2.0 * y1 + y2;
    if (Math.abs(denom) > 1e-12) {
      const delta = 0.5 * (y0 - y2) / denom; // in bins
      const spacing = spectrum[1].freqMHz - spectrum[0].freqMHz;
      return { peakMHz: fPeak + delta * spacing, peakIdx, peakResponse: y1 };
    }
  }
  return { peakMHz: fPeak, peakIdx, peakResponse: spectrum[peakIdx].response };
}

function ensureState(ctx) {
  if (!ctx.state || typeof ctx.state !== "object") {
    return null;
  }
  if (!ctx.state.initialized) {
    // Read the Geant4-derived proton density for the phantom (medium = water).
    const water = ctx.materials && ctx.materials[helpers.materialAliases.water];
    const protonPerCm3 = water && water.numberDensityPerCm3 && water.numberDensityPerCm3.H
      ? water.numberDensityPerCm3.H : 0.0;
    ctx.state.protonPerCm3 = protonPerCm3;
    ctx.state.m0 = curieMagnetization(
      protonPerCm3 * 1.0e6, MACHINE.b0Tesla, cfg.detector.temperatureK);
    // omega1 calibrated so an on-resonance pulse is exactly 90 degrees.
    ctx.state.omega1 = (Math.PI / 2.0) / MACHINE.pulseDurationS;
    ctx.state.b1Tesla = ctx.state.omega1 / PHYS.gammaProton;
    ctx.state.omega0 = PHYS.gammaProton * MACHINE.b0Tesla; // TRUE precession (feeds Bloch, not the sweep)
    ctx.state.spectrum = [];
    ctx.state.fid = [];
    ctx.state.discoveredMHz = 0.0;
    ctx.state.tick = 0;
    ctx.state.geant4 = { events: 0, totalEdepMeV: 0.0, totalStepCount: 0, totalTrackLengthMm: 0.0 };
    // Preview tissue proton densities (Geant4-derived) for Stage 2.
    ctx.state.tissuePreview = TISSUE_PREVIEW.map((name) => {
      const m = ctx.materials && ctx.materials[name];
      const h = m && m.numberDensityPerCm3 && m.numberDensityPerCm3.H ? m.numberDensityPerCm3.H : 0.0;
      return {
        material: name,
        density_g_per_cm3: m ? m.density_g_per_cm3 : 0.0,
        proton_per_cm3: h,
        // Relative signal amplitude vs water (proton-density-weighted, Geant4-derived).
        relative_signal: protonPerCm3 > 0 ? h / protonPerCm3 : 0.0
      };
    });
    ctx.state.initialized = true;
  }
  return ctx.state;
}

function recordGeant4(state, event) {
  state.geant4.events += 1;
  state.geant4.totalEdepMeV += event && event.edepMeV ? event.edepMeV : 0.0;
  state.geant4.totalStepCount += event && event.totalStepCount ? event.totalStepCount : 0;
  state.geant4.totalTrackLengthMm += event && event.totalTrackLengthMm ? event.totalTrackLengthMm : 0.0;
}

// One sweep sample: drive the spin at this transmit frequency and record |Mxy|.
function doSweepPoint(state, rng, index) {
  const fMHz = sweepFrequencyMHz(index);
  const omegaRf = 2.0 * Math.PI * fMHz * 1.0e6;
  const deltaOmega = state.omega0 - omegaRf;
  let response = blochPulseResponseMxy(
    deltaOmega, state.omega1, MACHINE.pulseDurationS, MACHINE.blochStepsPerPulse);
  response += gaussian(rng) * MACHINE.measurementNoise; // deterministic receiver noise
  state.spectrum.push({ freqMHz: fMHz, response });
}

// One FID sample at the discovered resonance: the transverse magnetization decays
// with T2*, radiating the detected RF signal (M0-scaled -> proton-density-scaled).
function doFidPoint(state, rng, index) {
  const tAcq = MACHINE.fidWindowT2Star * MACHINE.t2StarS;
  const t = N_FID > 1 ? (index / (N_FID - 1)) * tAcq : 0.0;
  const envelope = state.m0 * Math.exp(-t / MACHINE.t2StarS);
  const noisy = envelope * (1.0 + gaussian(rng) * MACHINE.measurementNoise);
  state.fid.push({ tS: t, envelope: noisy });
}

// Least-squares T2* recovered from the FID envelope: slope of ln(env) vs t.
function fitT2Star(fid) {
  let n = 0, sx = 0, sy = 0, sxx = 0, sxy = 0;
  for (let i = 0; i < fid.length; i += 1) {
    const y = fid[i].envelope;
    if (y <= 0) { continue; }
    const ly = Math.log(y);
    const x = fid[i].tS;
    n += 1; sx += x; sy += ly; sxx += x * x; sxy += x * ly;
  }
  if (n < 2) { return 0.0; }
  const denom = n * sxx - sx * sx;
  if (Math.abs(denom) < 1e-30) { return 0.0; }
  const slope = (n * sxy - sx * sy) / denom;
  return slope < 0 ? -1.0 / slope : 0.0;
}

// A short lab-frame oscillation snippet so viewers can see the carrier at the
// discovered frequency modulated by the FID envelope (the full envelope spans ms,
// far too long to show the ~64 MHz carrier directly).
function carrierSnippet(state) {
  const f0 = state.discoveredMHz * 1.0e6;
  if (f0 <= 0) { return []; }
  const period = 1.0 / f0;
  const nSnip = 200;
  const window = 10.0 * period;
  const out = [];
  for (let i = 0; i < nSnip; i += 1) {
    const t = (i / (nSnip - 1)) * window;
    out.push({
      tS: t,
      signal: state.m0 * Math.exp(-t / MACHINE.t2StarS) * Math.cos(2.0 * Math.PI * f0 * t)
    });
  }
  return out;
}

function buildSummary(state, rng) {
  // Coarse spectroscopy peak (broad, apparatus-bandwidth-limited) localizes the
  // resonance region; the FID carrier gives the precise Larmor line.
  const peak = findResonancePeakMHz(state.spectrum);
  state.sweepCoarsePeakMHz = peak.peakMHz;
  state.discoveredMHz = measureLarmorFromFidMHz(state, rng);
  const t2StarFit = fitT2Star(state.fid);

  // Recovered gyromagnetic ratio = discovered line / field.
  const gammaRecoveredMHzPerT = state.discoveredMHz / MACHINE.b0Tesla;
  const larmorExpectedMHz = TRUTH.gammaOver2piMHzPerT * MACHINE.b0Tesla;

  const larmorRelError = Math.abs(state.discoveredMHz - larmorExpectedMHz) / larmorExpectedMHz;
  const gammaRelError =
    Math.abs(gammaRecoveredMHzPerT - TRUTH.gammaOver2piMHzPerT) / TRUTH.gammaOver2piMHzPerT;
  const protonRelError = TRUTH.waterProtonPerCm3 > 0
    ? Math.abs(state.protonPerCm3 - TRUTH.waterProtonPerCm3) / TRUTH.waterProtonPerCm3
    : 1.0;
  const t2RelError = Math.abs(t2StarFit - MACHINE.t2StarS) / MACHINE.t2StarS;

  // Detected "output RF photons": magnetic energy stored in the polarized sample,
  // 0.5*M0*B0*V, divided by the RF quantum hbar*omega0 -> a detected-quanta proxy
  // that scales with the Geant4 proton density. Order-of-magnitude, labelled.
  const volumeM3 = Math.pow(cubeSideMm * 1.0e-3, 3);
  const omega0 = 2.0 * Math.PI * state.discoveredMHz * 1.0e6;
  const magneticEnergyJ = 0.5 * state.m0 * MACHINE.b0Tesla * volumeM3;
  const detectedPhotons = omega0 > 0 ? magneticEnergyJ / (PHYS.hbar * omega0) : 0.0;

  // FID must actually decay: envelope end below start.
  const envStart = state.fid.length > 0 ? state.fid[0].envelope : 0.0;
  const envEnd = state.fid.length > 0 ? state.fid[state.fid.length - 1].envelope : 0.0;
  const fidDecays = envStart > 0 && envEnd < envStart && t2StarFit > 0 && t2RelError <= 0.10;

  // Resonance peak is a genuine interior peak, well above the sweep baseline.
  let baseline = 0.0;
  for (let i = 0; i < state.spectrum.length; i += 1) { baseline += state.spectrum[i].response; }
  baseline = state.spectrum.length > 0 ? baseline / state.spectrum.length : 0.0;
  const resonanceLorentzian =
    peak.peakIdx > 0 && peak.peakIdx < state.spectrum.length - 1 &&
    peak.peakResponse > Math.max(0.5, 3.0 * baseline);

  const geant4DrivePresent =
    state.geant4.events === state.tick && state.geant4.totalEdepMeV > 0.0;

  return {
    scenario: "magnetic_resonance_water",
    honest_scope: {
      geant4_does:
        "builds the water phantom + copper coil, supplies 1H number density " +
        "(ctx.materials) and a G4EmCalculator anchor, transports a probe each event",
      hook_layer_does:
        "Bloch spin dynamics: RF frequency sweep, resonance discovery, FID, T2* decay",
      no_engine_spin_rule: true
    },
    machine: {
      b0_tesla: MACHINE.b0Tesla,
      sweep_lo_mhz: MACHINE.sweepLoMHz,
      sweep_hi_mhz: MACHINE.sweepHiMHz,
      sweep_points: N_SWEEP,
      b1_tesla: state.b1Tesla,
      pulse_duration_s: MACHINE.pulseDurationS,
      t2_star_s_input: MACHINE.t2StarS
    },
    // --- DISCOVERED (emergent) quantities ---
    discovered: {
      larmor_mhz: state.discoveredMHz,
      sweep_coarse_peak_mhz: state.sweepCoarsePeakMHz,
      gamma_recovered_mhz_per_t: gammaRecoveredMHzPerT,
      t2_star_s_fit: t2StarFit,
      detected_rf_photons: detectedPhotons
    },
    // --- from Geant4 (never hard-coded here) ---
    geant4_material: {
      water_proton_per_cm3: state.protonPerCm3,
      m0_a_per_m: state.m0,
      probe_beer_lambert_label: "mr_water_probe_interaction",
      event_drive: {
        events: state.geant4.events,
        total_edep_mev: state.geant4.totalEdepMeV,
        total_step_count: state.geant4.totalStepCount,
        total_track_length_mm: state.geant4.totalTrackLengthMm
      }
    },
    // --- gap-to-truth (know-what used only for grading) ---
    gap_to_truth: {
      larmor_expected_mhz: larmorExpectedMHz,
      larmor_rel_error: larmorRelError,
      gamma_reference_mhz_per_t: TRUTH.gammaOver2piMHzPerT,
      gamma_rel_error: gammaRelError,
      proton_density_reference_per_cm3: TRUTH.waterProtonPerCm3,
      proton_density_rel_error: protonRelError,
      t2_star_rel_error: t2RelError
    },
    // --- Stage-2 preview: Geant4-derived proton-density contrast ---
    tissue_preview: state.tissuePreview,
    validation: {
      larmor_discovered: larmorRelError <= 0.02,
      proton_density_from_geant4: state.protonPerCm3 > 0 && protonRelError <= 0.05,
      fid_decays: fidDecays,
      resonance_lorentzian: resonanceLorentzian,
      geant4_drive_present: geant4DrivePresent,
      no_engine_spin_rule: true
    }
  };
}

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    ctx.emit("scenario", {
      name: "magnetic_resonance_water",
      stage: 1,
      cube_side_mm: cubeSideMm,
      cube_volume_cm3: Math.pow(cubeSideMm, 3) / 1000.0,
      b0_tesla: MACHINE.b0Tesla,
      sweep_points: N_SWEEP,
      fid_samples: N_FID
    });
    return { override: { system: { ensemble: "magnetic_resonance_water" } } };
  },
  onRunStart(ctx) {
    ensureState(ctx);
  },
  onEventEnd(ctx) {
    const state = ensureState(ctx);
    if (!state || !ctx.event) { return; }
    recordGeant4(state, ctx.event);
    state.tick += 1;
    if (state.tick <= N_SWEEP) {
      doSweepPoint(state, ctx.rng, state.tick - 1);
    } else {
      // FID phase: the magnetization precesses at the true Larmor frequency
      // regardless of the sweep; the precise line is read from it at run end.
      doFidPoint(state, ctx.rng, state.tick - N_SWEEP - 1);
    }
  },
  onRunEnd(ctx) {
    const state = ctx.state;
    if (!state || !state.initialized) { return; }
    const summary = buildSummary(state, ctx.rng);
    ctx.emit("mr_spectrum", {
      b0_tesla: MACHINE.b0Tesla,
      discovered_larmor_mhz: state.discoveredMHz,
      expected_larmor_mhz: TRUTH.gammaOver2piMHzPerT * MACHINE.b0Tesla,
      points: state.spectrum.map((p) => ({
        freq_mhz: Math.round(p.freqMHz * 1000) / 1000,
        response: Math.round(p.response * 1e6) / 1e6
      }))
    });
    ctx.emit("mr_fid", {
      t2_star_s_input: MACHINE.t2StarS,
      t2_star_s_fit: summary.discovered.t2_star_s_fit,
      carrier_mhz: state.discoveredMHz,
      envelope: state.fid.map((p) => ({
        t_ms: Math.round(p.tS * 1e6) / 1000,
        amplitude: p.envelope
      })),
      carrier_snippet: carrierSnippet(state).map((p) => ({
        t_ns: Math.round(p.tS * 1e12) / 1000,
        signal: p.signal
      }))
    });
    ctx.emit("mr_summary", summary);
  }
};

globalThis.TRECH_CONFIG = cfg;
