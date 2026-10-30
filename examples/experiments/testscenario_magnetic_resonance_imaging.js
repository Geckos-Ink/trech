// Validation scenario (Stage 3): 1D magnetic-resonance IMAGING via frequency
// encoding -- turning the tissue contrast into an actual image line.
//
// Stages 1-2 discovered the Larmor line and measured per-tissue signal. Stage 3
// adds the missing MRI ingredient: a static field GRADIENT that makes the Larmor
// frequency position-dependent, omega(x) = gamma*(B0 + Gx*x). Each position along
// the readout axis then precesses at its own frequency, so the received signal is
// the Fourier transform of the proton-density profile rho(x). Fourier-transforming
// the readout reconstructs rho(x) -- a 1D image line where frequency maps to
// position and amplitude to proton density.
//
// TRECH contract (same as Stage 1): Geant4 builds a REAL multi-tissue phantom
// (a row of NIST-tissue voxels) and transports a real probe beam through it (the
// per-event clock + a real per-voxel energy tally), and -- through the material
// -probe surface -- supplies each voxel's proton (1H) number density (an ignorant
// material fact, never hard-coded). The gradient encoding, the readout synthesis
// and the DFT reconstruction are the deterministic hook-layer "physics for
// comparison". We feed only gamma (a particle constant), B0 and the gradient Gx
// (machine settings); the frequency->position map and the reconstructed image
// then EMERGE. The known phantom (which tissue sits where) is used only to grade
// the reconstruction.
//
// The phantom deliberately includes dark features: an AIR gap (essentially no
// hydrogen, so no MR-visible 1H protons -- air's N/O/Ar carry no signal-producing
// nuclei -> black) and cortical bone (1H-poor -> dark), so the reconstructed line is a
// recognizable 1D image: bright - bright - BLACK(air) - bright - dark(bone) -
// bright - bright.
//
// Honest scope: Geant4 does not simulate nuclear spin or field gradients; the
// spatial encoding + reconstruction are hook-layer signal processing on
// Geant4-supplied proton densities. What is real is the Geant4 phantom + transport
// and the proton densities that weight the image.
//
// Run:
//   trech run examples/experiments/testscenario_magnetic_resonance_imaging.js \
//        --events 200 --output build/dev/out_mr_imaging
// Inspect trech_hook_emits.jsonl -> mr_image_line (reconstructed profile, per-voxel
// recovered position + amplitude, validation).

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}
const units = helpers.units;
const geometry = helpers.geometry;

const PHYS = {
  gammaProton: 2.6752218708e8, // rad/s/T (proton gyromagnetic ratio)
};
const TRUTH = { gammaOver2piHzPerT: 42.577478518e6 };

const MACHINE = {
  b0Tesla: 1.5,
  gradientTPerM: 0.05,          // readout gradient (~50 mT/m, clinical range)
  t2StarS: 8.0e-3,
  readoutS: 4.0e-3,            // acquisition window
  readoutSamples: 512,        // time samples (complex/quadrature)
  reconBins: 141,             // reconstruction pixels across the FOV
  fovHalfMm: 28.0,            // reconstruct x in [-28, +28] mm
  noise: 0.01                 // deterministic receiver noise (fraction of peak)
};

// The phantom: a row of tissue voxels along the readout (x) axis. AIR and cortical
// bone are the dark features. Each is a real Geant4 volume; its proton density is
// read from ctx.materials (Geant4), never hard-coded here.
const VOXEL_SIZE_MM = 6.0;
const PHANTOM = [
  { xMm: -24, material: "G4_WATER",               label: "water" },
  { xMm: -16, material: "G4_ADIPOSE_TISSUE_ICRP", label: "adipose" },
  { xMm:  -8, material: "G4_AIR",                  label: "air gap" },
  { xMm:   0, material: "G4_MUSCLE_SKELETAL_ICRP", label: "muscle" },
  { xMm:   8, material: "G4_BONE_CORTICAL_ICRP",   label: "bone" },
  { xMm:  16, material: "G4_BRAIN_ICRP",           label: "brain" },
  { xMm:  24, material: "G4_WATER",               label: "water" }
];
const PHANTOM_MATERIALS = PHANTOM.map((v) => v.material)
  .filter((m, i, a) => a.indexOf(m) === i);

const worldSizeMm = units.cm(7.0);

const cfg = {
  detector: {
    worldSizeMm: worldSizeMm,
    worldMaterial: helpers.materialAliases.air,
    mediumBoxMm: 0.0,            // world-only: the phantom voxels are the geometry
    mediumMaterial: helpers.materialAliases.air,
    temperatureK: 310.15,
    pressureAtm: 1.0
  },
  // A broad, real gamma beam illuminating the whole phantom row: genuine Geant4
  // transport + a per-voxel edep tally + the per-event clock.
  beam: {
    particle: "gamma",
    energyMeV: 0.1,
    originMm: [0, 0, -0.45 * worldSizeMm],
    direction: [0, 0, 1],
    spread: { spotRadiusMm: 30.0, divergenceDeg: 0.0, energySpreadFractional: 0.0 }
  },
  run: { nEvents: 200, seed: 20260705, threads: 1 },
  determinism: { mode: "strict" },
  system: {
    enable: true,
    mode: "steady_state",
    frame: "point_agnostic",
    ensemble: "magnetic_resonance_imaging"
  },
  materialProbe: {
    enable: true,
    materials: PHANTOM_MATERIALS
  },
  geometry: {
    volumes: PHANTOM.map((v, i) => geometry.boxVolume({
      name: "voxel_" + i + "_" + v.label.replace(/\s+/g, "_"),
      material: v.material,
      sizeMm: [VOXEL_SIZE_MM, VOXEL_SIZE_MM, VOXEL_SIZE_MM],
      positionMm: [v.xMm, 0, 0],
      parent: "world",
      scoreEdep: true,
      tags: ["phantom_voxel"]
    }))
  },
  hooks: {
    maxEmitsPerCallback: 160,
    maxEmitPayloadBytes: 262144
  }
};

const gaussian = helpers.random.gaussian;

function protonDensityOf(ctx, name) {
  const m = ctx.materials && ctx.materials[name];
  return (m && m.numberDensityPerCm3 && m.numberDensityPerCm3.H) ? m.numberDensityPerCm3.H : 0.0;
}

// Synthesize the frequency-encoded quadrature readout S(t) = sum_i rho_i *
// exp(-t/T2*) * exp(i * dOmega_i * t), where dOmega_i = gamma * Gx * x_i is the
// gradient-induced offset frequency of voxel i (in the rotating frame at omega0).
// This is the acquired MRI echo; its DFT is the image.
function synthesizeReadout(voxels, rng) {
  const N = MACHINE.readoutSamples;
  const dt = MACHINE.readoutS / N;
  const gGx = PHYS.gammaProton * MACHINE.gradientTPerM;
  const re = new Array(N);
  const im = new Array(N);
  // peak scale for the noise floor
  let ampSum = 0.0;
  for (let v = 0; v < voxels.length; v += 1) { ampSum += voxels[v].amp; }
  const noiseSigma = MACHINE.noise * (ampSum > 0 ? ampSum : 1.0);
  for (let k = 0; k < N; k += 1) {
    const t = k * dt;
    const decay = Math.exp(-t / MACHINE.t2StarS);
    let sr = 0.0, si = 0.0;
    for (let v = 0; v < voxels.length; v += 1) {
      const dOmega = gGx * voxels[v].xM;
      const a = voxels[v].amp * decay;
      sr += a * Math.cos(dOmega * t);
      si += a * Math.sin(dOmega * t);
    }
    re[k] = sr + gaussian(rng) * noiseSigma;
    im[k] = si + gaussian(rng) * noiseSigma;
  }
  return { re, im, dt, N, gGx };
}

// Reconstruct the image profile by evaluating the DFT at the offset frequency that
// each reconstruction pixel maps to: x_k -> dOmega_k = gamma*Gx*x_k. Returns the
// magnitude profile |rho_hat(x_k)| = the 1D image line.
function reconstructImage(readout) {
  const { re, im, dt, N, gGx } = readout;
  const bins = MACHINE.reconBins;
  const half = MACHINE.fovHalfMm;
  const profile = [];
  for (let b = 0; b < bins; b += 1) {
    const xMm = -half + (2.0 * half) * b / (bins - 1);
    const dOmega = gGx * (xMm * 1e-3);
    let ar = 0.0, ai = 0.0;
    for (let k = 0; k < N; k += 1) {
      const t = k * dt;
      const c = Math.cos(dOmega * t);
      const s = Math.sin(dOmega * t);
      // conjugate demodulation: S(t) * exp(-i dOmega t)
      ar += re[k] * c + im[k] * s;
      ai += im[k] * c - re[k] * s;
    }
    profile.push({ x_mm: xMm, intensity: Math.sqrt(ar * ar + ai * ai) * dt });
  }
  return profile;
}

// Nearest reconstructed intensity at a given x (mm).
function intensityAt(profile, xMm) {
  let best = profile[0], bestD = Infinity;
  for (let i = 0; i < profile.length; i += 1) {
    const d = Math.abs(profile[i].x_mm - xMm);
    if (d < bestD) { bestD = d; best = profile[i]; }
  }
  return best.intensity;
}

// Recover a voxel's position: the local peak of the profile within a window around
// x_true (parabolic-interpolated). Air voxels have no peak (returns null).
function recoverPeak(profile, xTrueMm, windowMm) {
  let bestI = -1, bestV = -Infinity;
  for (let i = 0; i < profile.length; i += 1) {
    if (Math.abs(profile[i].x_mm - xTrueMm) <= windowMm && profile[i].intensity > bestV) {
      bestV = profile[i].intensity; bestI = i;
    }
  }
  if (bestI <= 0 || bestI >= profile.length - 1) {
    return { x_mm: bestI >= 0 ? profile[bestI].x_mm : xTrueMm, amp: bestV };
  }
  const y0 = profile[bestI - 1].intensity, y1 = profile[bestI].intensity, y2 = profile[bestI + 1].intensity;
  const denom = y0 - 2 * y1 + y2;
  const dx = profile[1].x_mm - profile[0].x_mm;
  const delta = Math.abs(denom) > 1e-12 ? 0.5 * (y0 - y2) / denom : 0.0;
  return { x_mm: profile[bestI].x_mm + delta * dx, amp: y1 };
}

function pearson(xs, ys) {
  const n = xs.length;
  if (n < 2) { return 0.0; }
  let mx = 0, my = 0;
  for (let i = 0; i < n; i += 1) { mx += xs[i]; my += ys[i]; }
  mx /= n; my /= n;
  let sxy = 0, sxx = 0, syy = 0;
  for (let i = 0; i < n; i += 1) {
    sxy += (xs[i] - mx) * (ys[i] - my);
    sxx += (xs[i] - mx) * (xs[i] - mx);
    syy += (ys[i] - my) * (ys[i] - my);
  }
  const d = Math.sqrt(sxx * syy);
  return d > 0 ? sxy / d : 0.0;
}

// ---------------------------------------------------------------------------
// 3D observer frames (classic trech-viz / Studio), mm in the phantom's Geant4 frame, y-up with
// B0 drawn along +y so the transverse plane is x/z. Each voxel box is shaded by its Geant4
// proton density (the MR brightness); its arrow is that voxel's transverse magnetization in the
// rotating frame, amplitude * exp(-t/T2*) at phase gamma*Gx*x*t — exactly the terms
// synthesizeReadout sums — so the gradient's phase winding is visible. The summed receiver
// signal is the arrow beside the row, and the final frames add the reconstructed image line.
// ---------------------------------------------------------------------------
const OBS = helpers.observer;
function emitReadoutFrames(ctx, voxels, readout, profile, profileMax) {
  // Three acts, all evaluated from the same law synthesizeReadout sums (amp * exp(-t/T2*) at
  // phase gamma*Gx*x*t): (A) slow motion over the first 40 us, where the gradient's different
  // precession rates are visible (the outer voxels turn fastest, the centre not at all);
  // (B) the acquired readout, fast-forwarded; (C) the DFT reconstruction.
  const slowFrames = 60, readFrames = 40, reconFrames = 16;
  const slowWindowS = 40e-6;
  const armMm = 1.05 * VOXEL_SIZE_MM;
  const spinY = VOXEL_SIZE_MM * 1.1;
  const gradientDisplayGain = 0.9;   // display exaggeration of the field ramp (representation)
  const boxes = voxels.map((v) => ({
    shape: "box", center: [v.xMm, 0, 0], size: [VOXEL_SIZE_MM * 0.96, VOXEL_SIZE_MM * 0.96,
                                                VOXEL_SIZE_MM * 0.96],
    color_rgba: [0.15 + 0.8 * v.amp, 0.15 + 0.8 * v.amp, 0.18 + 0.8 * v.amp, 0.35],
    label: v.label }));
  // The field each voxel sits in: B0 + Gx x, drawn as a column whose height grows along x.
  const fieldBars = voxels.map((v) => {
    const h = 7.0 * (1.0 + gradientDisplayGain * v.xMm / 28.0);
    return { shape: "cylinder", center: [v.xMm, -0.5 * VOXEL_SIZE_MM + 0.5 * h, -1.4 * VOXEL_SIZE_MM],
             radius: 0.9, height: h, axis: "y", color_rgba: [0.45, 0.58, 1.0, 0.85],
             label: "local field" };
  });
  const labels = voxels.map((v) => ({ position: [v.xMm, -0.85 * VOXEL_SIZE_MM, 0.8 * VOXEL_SIZE_MM],
                                      text: v.label, color_rgba: [0.85, 0.9, 1.0, 1] }));
  labels.push({ position: [38.0, spinY + 4.0, 0], text: "receiver sum",
                color_rgba: [1.0, 0.45, 0.55, 1] });
  const truthX = [], truthY = [];
  for (const v of voxels) {
    const a = v.xMm - 0.5 * VOXEL_SIZE_MM, b = v.xMm + 0.5 * VOXEL_SIZE_MM;
    truthX.push(a, a, b, b); truthY.push(0, v.amp, v.amp, 0);
  }
  const reconX = profile.map((q) => Math.round(q.x_mm * 100) / 100);
  const reconY = profile.map((q) => Math.round(1000 * q.intensity / (profileMax || 1.0)) / 1000);
  const total = slowFrames + readFrames + reconFrames;
  for (let f = 0; f < total; f += 1) {
    let t, k;
    if (f < slowFrames) {
      t = slowWindowS * f / (slowFrames - 1);
      k = Math.floor(t / readout.dt);
    } else {
      const g = Math.min(f - slowFrames, readFrames - 1);
      k = Math.round(Math.max(1, (readout.N - 1) * g / (readFrames - 1)));
      t = k * readout.dt;
    }
    const decay = Math.exp(-t / MACHINE.t2StarS);
    const positions = [], colors = [], radii = [], vectors = [];
    let sr = 0.0, si = 0.0;
    for (const v of voxels) {
      const phase = readout.gGx * v.xM * t;
      const a = v.amp * decay;
      sr += a * Math.cos(phase); si += a * Math.sin(phase);
      positions.push([v.xMm, spinY, 0]);
      colors.push([1.0, 0.72, 0.2, 1.0]);
      radii.push(0.7);
      vectors.push([a * armMm * Math.cos(phase), 0, a * armMm * Math.sin(phase)]);
    }
    const norm = voxels.length;
    positions.push([38.0, spinY, 0]);
    colors.push([1.0, 0.35, 0.45, 1.0]);
    radii.push(0.9);
    vectors.push([armMm * 1.3 * sr / norm, 0, armMm * 1.3 * si / norm]);
    const reconstructed = f >= slowFrames + readFrames;
    const step = 2;
    const sigX = [], sigRe = [], sigIm = [];
    for (let j = 0; j <= Math.min(k, readout.N - 1); j += step) {
      sigX.push(Math.round(j * readout.dt * 1e6) / 1e3);
      sigRe.push(Math.round(1000 * readout.re[j] / norm) / 1000);
      sigIm.push(Math.round(1000 * readout.im[j] / norm) / 1000);
    }
    const curves = [
      { chart: "signal", label: "Re S(t)", color: "#ff5a70", x: sigX, y: sigRe },
      { chart: "signal", label: "Im S(t)", color: "#ffb0bc", x: sigX, y: sigIm }];
    if (reconstructed) {
      curves.push({ chart: "image", label: "reconstructed (DFT of S)", color: "#66e0ff",
                    x: reconX, y: reconY });
    }
    const act = f < slowFrames ? "slow motion: each voxel precesses at gamma*(B0 + Gx x)"
      : (reconstructed ? "DFT reconstruction: frequency -> position"
                       : "readout: the coil records the sum of all voxels");
    ctx.emit("material_frame", OBS.frame({
      physicalTimeS: t, playbackTimeS: f,
      clockText: "readout t = " + (t * 1e3).toFixed(4) + " ms / " + (MACHINE.readoutS * 1e3).toFixed(1) +
        " ms",
      phase: act,
      upAxis: "y", digits: 3,
      positions, colors, radii, vectors,
      apparatus: boxes.concat(fieldBars).concat([
        { shape: "segment", from: [-32, -6, 0], to: [32, -6, 0], color_rgba: [0.55, 0.65, 1.0, 0.7] }]),
      labels,
      curves,
      charts: f === 0 ? [
        { id: "signal", title: "signal the coil receives", x_label: "time (ms)",
          y_label: "S / voxel count", x_range: [0, MACHINE.readoutS * 1e3], y_range: [-1.05, 1.05] },
        { id: "image", title: "1D image: position from frequency", x_label: "x (mm)",
          y_label: "brightness (water = 1)", x_range: [-MACHINE.fovHalfMm, MACHINE.fovHalfMm],
          y_range: [0, 1.15],
          reference: [{ label: "Geant4 1H density (per voxel)", color: "#c9d3e6", x: truthX,
                        y: truthY }] }
      ] : [],
      legend: OBS.legend([["voxel M_xy (rotating frame)", [1.0, 0.72, 0.2]],
                          ["B0 + Gx·x (ramp exaggerated)", [0.45, 0.58, 1.0]],
                          ["summed receiver signal", [1.0, 0.35, 0.45]]]),
      hud: ["Gx = " + MACHINE.gradientTPerM * 1000 + " mT/m: precession rate encodes position",
            "voxel brightness = Geant4 1H density / water;  |S| = " +
              (Math.hypot(sr, si) / norm).toFixed(3)],
      motionScope: "hook-layer gradient encoding of Geant4 proton densities"
    }));
  }
}

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    ctx.emit("scenario", {
      name: "magnetic_resonance_imaging",
      stage: 3,
      b0_tesla: MACHINE.b0Tesla,
      gradient_t_per_m: MACHINE.gradientTPerM,
      voxels: PHANTOM.length
    });
    return { override: { system: { ensemble: "magnetic_resonance_imaging" } } };
  },
  onRunStart(ctx) {
    if (ctx.state) { ctx.state.geant4 = { events: 0, totalEdepMeV: 0.0 }; }
  },
  onEventEnd(ctx) {
    if (!ctx.state || !ctx.event) { return; }
    if (!ctx.state.geant4) { ctx.state.geant4 = { events: 0, totalEdepMeV: 0.0 }; }
    ctx.state.geant4.events += 1;
    ctx.state.geant4.totalEdepMeV += ctx.event.edepMeV || 0.0;
  },
  onRunEnd(ctx) {
    const g4 = (ctx.state && ctx.state.geant4) || { events: 0, totalEdepMeV: 0.0 };

    // Build the spin population per voxel from the Geant4-supplied proton density.
    const voxels = PHANTOM.map((v) => {
      const proton = protonDensityOf(ctx, v.material);
      return { xM: v.xMm * 1e-3, xMm: v.xMm, amp: proton, proton: proton,
               material: v.material, label: v.label };
    });
    // Normalize amplitudes to water (=max) for a stable image scale.
    let refProton = 0.0;
    voxels.forEach((v) => { if (v.proton > refProton) { refProton = v.proton; } });
    voxels.forEach((v) => { v.amp = refProton > 0 ? v.proton / refProton : 0.0; });

    const readout = synthesizeReadout(voxels, ctx.rng);
    const profile = reconstructImage(readout);
    let profileMax = 0.0;
    profile.forEach((p) => { if (p.intensity > profileMax) { profileMax = p.intensity; } });
    emitReadoutFrames(ctx, voxels, readout, profile, profileMax);
    profile.forEach((p) => { p.intensity_norm = profileMax > 0 ? p.intensity / profileMax : 0.0; });

    // Per-voxel recovery. Window = half the voxel spacing so peaks don't collide.
    const spacingMm = Math.abs(PHANTOM[1].xMm - PHANTOM[0].xMm);
    const windowMm = spacingMm * 0.5;
    const gGx = readout.gGx;
    const perVoxel = voxels.map((v) => {
      const isDark = v.proton < 0.15 * refProton; // air / no-signal region
      const peak = recoverPeak(profile, v.xMm, windowMm);
      const recAmp = intensityAt(profile, v.xMm);
      return {
        label: v.label,
        material: v.material,
        x_true_mm: v.xMm,
        x_recovered_mm: isDark ? null : peak.x_mm,
        position_error_mm: isDark ? null : Math.abs(peak.x_mm - v.xMm),
        larmor_offset_khz: (gGx * v.xM) / (2.0 * Math.PI) / 1e3,
        proton_per_cm3: v.proton,
        recovered_intensity: recAmp / (profileMax || 1.0),
        is_dark_feature: isDark
      };
    });

    // --- validation ---
    const bright = perVoxel.filter((p) => !p.is_dark_feature);
    const maxPosErr = bright.reduce((m, p) => Math.max(m, p.position_error_mm || 0), 0);
    const positionRecovered = maxPosErr <= 1.5;                 // sub-2mm localization
    const ampCorr = pearson(perVoxel.map((p) => p.proton_per_cm3),
                            perVoxel.map((p) => p.recovered_intensity));
    const amplitudeTracksProton = ampCorr >= 0.95;
    // dark features: air near-black; bone below the soft-tissue neighbours.
    const air = perVoxel.find((p) => p.label === "air gap");
    const bone = perVoxel.find((p) => p.label === "bone");
    const muscle = perVoxel.find((p) => p.label === "muscle");
    const brain = perVoxel.find((p) => p.label === "brain");
    const airDark = air && air.recovered_intensity < 0.20;
    const boneDark = bone && muscle && brain &&
      bone.recovered_intensity < muscle.recovered_intensity &&
      bone.recovered_intensity < brain.recovered_intensity;
    const geant4Present = g4.events === ctx.runtime.nEvents && g4.totalEdepMeV > 0.0;

    ctx.emit("mr_image_line", {
      scenario: "magnetic_resonance_imaging",
      honest_scope: {
        geant4_does: "builds the real multi-tissue phantom, transports a probe beam, supplies proton densities",
        hook_layer_does: "gradient frequency encoding + readout synthesis + DFT reconstruction of the 1D image",
        no_engine_spin_rule: true
      },
      machine: {
        b0_tesla: MACHINE.b0Tesla,
        gradient_t_per_m: MACHINE.gradientTPerM,
        readout_s: MACHINE.readoutS,
        readout_samples: MACHINE.readoutSamples,
        fov_mm: 2.0 * MACHINE.fovHalfMm,
        // encoding bandwidth across the FOV (Hz), from the gradient
        bandwidth_khz: TRUTH.gammaOver2piHzPerT * MACHINE.gradientTPerM * (2.0 * MACHINE.fovHalfMm * 1e-3) / 1e3
      },
      voxels: perVoxel,
      image_profile: profile.map((p) => ({
        x_mm: Math.round(p.x_mm * 100) / 100,
        intensity: Math.round(p.intensity_norm * 1e5) / 1e5
      })),
      geant4_drive: { events: g4.events, total_edep_mev: g4.totalEdepMeV },
      metrics: {
        max_position_error_mm: maxPosErr,
        amplitude_proton_corr: ampCorr
      },
      validation: {
        position_recovered: positionRecovered,
        amplitude_tracks_proton_density: amplitudeTracksProton,
        air_gap_is_dark: !!airDark,
        cortical_bone_is_dark: !!boneDark,
        geant4_transport_present: geant4Present,
        no_engine_spin_rule: true
      }
    });
  }
};

globalThis.TRECH_CONFIG = cfg;
