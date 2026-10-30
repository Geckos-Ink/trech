// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["testscenario_magnetic_resonance"] = {
"frame0": function(MACHINE, N_FID, N_SWEEP, OBS, apparatus, charts, colors, half, hud, inSweep, positions, radii, samples, state, vectors) { return OBS.frame({
    physicalTimeS: state.tick, playbackTimeS: state.tick,
    clockText: (inSweep ? "sweep " + state.tick + "/" + N_SWEEP
                        : "FID " + (state.tick - N_SWEEP) + "/" + N_FID) + " (one Geant4 event each)",
    phase: inSweep ? "driven RF sweep (Bloch, rotating frame)" : "free induction decay",
    upAxis: "y", digits: 3,
    positions, colors, radii, vectors, apparatus,
    samples, charts,
    labels: [{ position: [1.9 * half, 1.9 * half, 1.9 * half], text: "B0 = " + MACHINE.b0Tesla + " T",
               color_rgba: [0.7, 0.8, 1.0, 1] },
             { position: [0, -1.2 * half, 1.6 * half], text: "RF / receiver coil (Cu)",
               color_rgba: [0.95, 0.75, 0.55, 1] }],
    legend: OBS.legend([["M: net 1H magnetization (Bloch)", [1.0, 0.62, 0.15]],
                        ["B0 field lines", [0.45, 0.58, 1.0]],
                        ["B_eff: B0 offset + RF B1 (rotating frame)", [0.4, 1.0, 0.55]],
                        ["spin isochromats after the pulse (representation)", [1.0, 0.86, 0.55]],
                        ["water sample (Geant4 1H density)", [0.35, 0.62, 1.0]]]),
    hud,
    motionScope: "hook-layer Bloch magnetization; Geant4 supplies proton density + event clock; " +
                 "field lines, poles and isochromats are representation"
  }); }
};

Object.assign(TRECH_VIEWS["testscenario_magnetic_resonance"], {
"emitMrFrame": function(ctx, state, ARROW_MM, ISO_OFFSETS, MACHINE, N_FID, N_ISO, N_SWEEP, OBS, TRECH_VIEWS, TRUTH, cubeSideMm, toView, traceSegments) {
  const inSweep = state.tick <= N_SWEEP;
  const half = 0.5 * cubeSideMm;
  const positions = [], colors = [], radii = [], vectors = [];
  const apparatus = [];
  const hud = [];
  // Static field B0 (the magnet): thin field lines through the sample with small arrowheads,
  // poles above and below.
  for (const x of [-1.6, 0, 1.6]) {
    for (const z of [-1.6, 0, 1.6]) {
      if (x === 0 && z === 0) continue;
      apparatus.push({ shape: "segment", from: [x * half, -2.3 * half, z * half],
                       to: [x * half, 2.3 * half, z * half], color_rgba: [0.45, 0.58, 1.0, 0.7] });
      positions.push([x * half, 0.9 * half, z * half]);
      colors.push([0.45, 0.58, 1.0, 0.9]);
      radii.push(0.01);
      vectors.push([0, 0.55 * half, 0]);
    }
  }
  apparatus.push({ shape: "box", center: [0, 2.55 * half, 0], size: [3.4 * half, 0.3 * half, 3.4 * half],
                   color_rgba: [0.85, 0.3, 0.3, 0.85], label: "magnet N pole" });
  apparatus.push({ shape: "box", center: [0, -2.55 * half, 0], size: [3.4 * half, 0.3 * half, 3.4 * half],
                   color_rgba: [0.3, 0.45, 0.9, 0.85], label: "magnet S pole" });
  apparatus.push({ shape: "box", center: [0, 0, 0], size: [cubeSideMm, cubeSideMm, cubeSideMm],
                   color_rgba: [0.35, 0.62, 1.0, 0.16], label: "5 cm^3 water" });
  let mView;
  const samples = {};
  if (inSweep) {
    const q = state.spectrum[state.spectrum.length - 1];
    mView = toView(state.lastM, ARROW_MM);
    // B_eff = (omega1, 0, deltaOmega)/gamma in the rotating frame: M precesses around it.
    const b = state.lastBeff, bn = Math.hypot(b[0], b[1], b[2]) || 1;
    positions.push([0, 0, 0]); colors.push([0.4, 1.0, 0.55, 1.0]); radii.push(0.01);
    vectors.push(toView([b[0] / bn, b[1] / bn, b[2] / bn], ARROW_MM * 1.15));
    // The Bloch solver's own path of M through this pulse (RK4 samples).
    const pts = state.lastPath.map((m) => toView(m, ARROW_MM));
    apparatus.push(...traceSegments(pts, [1.0, 0.72, 0.2, 0.75]));
    hud.push("RF pulse at " + q.freqMHz.toFixed(2) + " MHz: M tips about B_eff; |Mxy|/M0 = " +
             q.response.toFixed(3));
    samples.freq_mhz = Math.round(q.freqMHz * 1000) / 1000;
    samples.response = Math.round(q.response * 1e4) / 1e4;
  } else {
    const q = state.fid[state.fid.length - 1];
    const rel = state.m0 > 0 ? q.envelope / state.m0 : 0.0;
    mView = toView([rel, 0, 0], ARROW_MM);
    const tS = q.tS;
    for (let i = 0; i < N_ISO; i += 1) {
      const phi = ISO_OFFSETS[i] * tS;
      const ring = 2.0 * Math.PI * i / N_ISO;
      positions.push([0.95 * half * Math.cos(ring), -0.55 * half, 0.95 * half * Math.sin(ring)]);
      colors.push([1.0, 0.86, 0.55, 0.9]);
      radii.push(0.35);
      vectors.push(toView([Math.cos(phi), Math.sin(phi), 0], 0.3 * ARROW_MM));
    }
    hud.push("free induction decay t = " + (tS * 1e3).toFixed(2) + " ms: spins dephase, |Mxy|/M0 = " +
             rel.toFixed(3));
    samples.fid_t_ms = Math.round(tS * 1e5) / 100;
    samples.fid_envelope = Math.round(rel * 1e4) / 1e4;
  }
  positions.push([0, 0, 0]); colors.push([1.0, 0.62, 0.15, 1.0]); radii.push(0.9);
  vectors.push(mView);
  hud.push("B0 = " + MACHINE.b0Tesla + " T   1H density (Geant4) " +
           state.protonPerCm3.toExponential(3) + " /cm^3   M0 " + state.m0.toExponential(2) + " A/m");
  const charts = state.tick === 1 ? [
    { id: "spectrum", title: "RF sweep: tip response vs frequency", x: "freq_mhz",
      x_label: "RF frequency (MHz)", y_label: "|Mxy| / M0 after pulse",
      x_range: [MACHINE.sweepLoMHz, MACHINE.sweepHiMHz], y_range: [-0.05, 1.1],
      series: [{ key: "response", label: "Bloch pulse response", color: "#ffb838" }],
      vlines: [{ x: TRUTH.gammaOver2piMHzPerT * MACHINE.b0Tesla,
                 label: "γ·B0 (CODATA, grading only)", color: "#9ad0ff" }] },
    { id: "fid", title: "free induction decay (T2* dephasing)", x: "fid_t_ms",
      x_label: "time after pulse (ms)", y_label: "|Mxy| / M0",
      x_range: [0, MACHINE.fidWindowT2Star * MACHINE.t2StarS * 1e3], y_range: [0, 1.1],
      series: [{ key: "fid_envelope", label: "signal envelope", color: "#66e0ff" }] }
  ] : [];
  ctx.emit("material_frame", TRECH_VIEWS["testscenario_magnetic_resonance"]["frame0"](MACHINE, N_FID, N_SWEEP, OBS, apparatus, charts, colors, half, hud, inSweep, positions, radii, samples, state, vectors));
}
});
