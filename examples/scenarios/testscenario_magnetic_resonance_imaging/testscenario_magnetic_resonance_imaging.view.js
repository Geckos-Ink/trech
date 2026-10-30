// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["testscenario_magnetic_resonance_imaging"] = {
"frame0": function(MACHINE, OBS, act, boxes, colors, curves, f, fieldBars, labels, norm, positions, radii, si, sr, t, truthX, truthY, vectors) { return OBS.frame({
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
    }); }
};

Object.assign(TRECH_VIEWS["testscenario_magnetic_resonance_imaging"], {
"emitReadoutFrames": function(ctx, voxels, readout, profile, profileMax, MACHINE, OBS, TRECH_VIEWS, VOXEL_SIZE_MM) {
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
    ctx.emit("material_frame", TRECH_VIEWS["testscenario_magnetic_resonance_imaging"]["frame0"](MACHINE, OBS, act, boxes, colors, curves, f, fieldBars, labels, norm, positions, radii, si, sr, t, truthX, truthY, vectors));
  }
}
});
