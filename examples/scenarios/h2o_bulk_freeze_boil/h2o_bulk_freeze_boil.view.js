// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["h2o_bulk_freeze_boil"] = {
// Display colours by the CHILL+ phase each molecule was DETECTED in.
"palette": {
  floor: [0.58, 0.6, 0.66, 1.0],      // fixed ice-templating floor
  liquid: [0.2, 0.45, 0.95, 1.0],
  hex: [0.82, 0.96, 1.0, 1.0],        // hexagonal ice (Ih)
  cubic: [0.78, 0.74, 1.0, 1.0],      // cubic ice (Ic, stacking faults)
  inter: [0.5, 0.78, 0.98, 1.0],      // interfacial ice
  vapour: [1.0, 0.62, 0.3, 1.0]
},
// Playback-clock rate per stage (playback units per physical ps). It
// compresses the slow -1 °C growth (2.5 ns -> ~45% of the playback) and
// dilates the picosecond heating ramp where the ice melts (~25%), so every
// transition state gets screen time. Per-stage rates rather than a
// phase-change-driven rate: with 600 molecules the CHILL+ census flickers by
// ~10 molecules per frame, which would swamp a change-driven clock.
// Representation only: the physical clock is printed on every frame.
"playWeight": { prep: 0.0013, hold_10C: 0.0017, cool: 0.004, hold_m1C: 0.00018,
                heat: 0.0031, hold_100C: 0.0008 },
"emitFrame": function(ctx, s, st, targetK, cen, k) {
  const V = TRECH_VIEWS["h2o_bulk_freeze_boil"], P = V.palette;
  const sim = s.sim, helpers = k.helpers, C0 = k.C0;
  const tPs = s.tick * k.DT / 1000;
  // --- playback clock ---
  const play = s.play;
  const stageId = st ? st.id : "prep";
  const crystal = cen.crystalFraction;
  if (play.lastPs !== undefined) {
    const dPs = tPs - play.lastPs;
    const dPlay = V.playWeight[stageId] * dPs;
    play.t += dPlay;
    play.scale = dPlay > 0 ? (dPs * 1e-12) / dPlay : 1.0;
  }
  play.lastPs = tPs;
  // --- molecules, coloured by detected phase ---
  const positions = [], colors = [], radii = [];
  for (let i = 0; i < sim.n; i++) {
    positions.push(sim.wrapped(i));
    let c;
    if (sim.fixed[i]) c = P.floor;
    else if (cen.four[i].length === 0) c = P.vapour;
    else c = [P.liquid, P.hex, P.cubic, P.inter][cen.phase[i]];
    colors.push(c);
    radii.push(sim.fixed[i] ? 0.8 : 0.95);
  }
  // Tetrahedral network of the crystal: bonds between neighbouring molecules
  // that are both ice (or floor). Bonds across the periodic seam are skipped.
  const bonds = [];
  const crystalLike = (i) => sim.fixed[i] || cen.phase[i] === 1 || cen.phase[i] === 2;
  for (let i = 0; i < sim.n; i++) {
    if (!crystalLike(i)) continue;
    for (const j of cen.four[i]) {
      if (j <= i || !crystalLike(j)) continue;
      const a = positions[i], b = positions[j];
      const dx = a[0] - b[0], dy = a[1] - b[1], dz = a[2] - b[2];
      if (dx * dx + dy * dy + dz * dz < 12.25) bonds.push([i, j]);
    }
  }
  const T = sim.temperature();
  const pct = (v) => (100 * v).toFixed(0) + "%";
  const phase = !st ? "preparing liquid from the start grid (" + k.PREP_K + " K, not measured)"
    : st.kind === "ramp" ? st.label : "holding at " + st.label;
  const hud = [
    "T = " + (T - C0).toFixed(1) + " °C (" + T.toFixed(0) + " K)   target " +
      (targetK - C0).toFixed(1) + " °C   (mW melts at " + (k.mw.MELTING_POINT_K - C0).toFixed(1) + " °C)",
    "ice " + pct(crystal) + "  interfacial " + cen.inter + "  liquid " + cen.liquid +
      "  vapour " + cen.vapour,
    "ice grown above the floor ≈ " + cen.iceThicknessA.toFixed(1) + " Å"
  ];
  for (const h of s.results) {
    hud.push(h.label + ": " + h.phase_verdict.split(" (")[0] +
             (h.stage === "hold_m1C" ? ", front " + h.ice_front_velocity_A_per_ns.toFixed(0) + " Å/ns" : ""));
  }
  const r3 = (x) => Math.round(x * 1000) / 1000;
  const charts = s.chartsDeclared ? [] : [
    { id: "temp", title: "temperature program: 10 → -1 → 100 °C", x: "time", x_scale: 1e9,
      x_label: "physical time (ns)", y_label: "°C", cursor: true, y_range: [-15, 115],
      series: [{ key: "temperature_C", label: "MD kinetic T", color: "#ff8a5c" },
               { key: "target_C", label: "program target", color: "#9ad0ff", dashed: true }] },
    { id: "phase", title: "phase of each molecule (CHILL+)", x: "time", x_scale: 1e9,
      x_label: "physical time (ns)", y_label: "fraction", cursor: true, y_range: [0, 1],
      series: [{ key: "ice_fraction", label: "ice (hex + cubic)", color: "#d2f4ff" },
               { key: "interfacial_fraction", label: "interfacial ice", color: "#80c7fa" },
               { key: "liquid_fraction", label: "liquid", color: "#3373f2" },
               { key: "vapour_fraction", label: "vapour", color: "#ff9e4d" }] },
    { id: "thick", title: "ice grown above the floor", x: "time", x_scale: 1e9,
      x_label: "physical time (ns)", y_label: "Å", cursor: true,
      series: [{ key: "ice_thickness_A", label: "crystalline thickness", color: "#c7a6ff" }] }
  ];
  s.chartsDeclared = true;
  ctx.emit("material_frame", helpers.observer.frame({
    physicalTimeS: tPs * 1e-12,
    playbackTimeS: play.t,
    timeScale: play.scale || 1.0,
    clockText: "t = " + (tPs >= 1000 ? (tPs / 1000).toFixed(3) + " ns" : tPs.toFixed(1) + " ps") +
               " physical (playback time-dilated)",
    phase,
    lengthUnit: "angstrom", upAxis: "z", digits: 2,
    positions, colors, radii, bonds,
    apparatus: [{ shape: "box", center: [k.LX / 2, k.LY / 2, k.LZ / 2], size: [k.LX, k.LY, k.LZ],
                  style: "wire", color_rgba: [0.55, 0.7, 1.0, 0.5], label: "periodic cell" }],
    legend: helpers.observer.legend([["hexagonal ice", P.hex], ["cubic ice", P.cubic],
                                     ["interfacial ice", P.inter], ["liquid", P.liquid],
                                     ["vapour", P.vapour], ["ice floor (fixed)", P.floor]]),
    hud,
    samples: { temperature_C: Math.round((T - C0) * 10) / 10,
               target_C: Math.round((targetK - C0) * 10) / 10,
               ice_fraction: r3(crystal), interfacial_fraction: r3(cen.inter / cen.mobile),
               liquid_fraction: r3(cen.liquid / cen.mobile), vapour_fraction: r3(cen.vapour / cen.mobile),
               ice_thickness_A: Math.round(cen.iceThicknessA * 10) / 10 },
    charts,
    motionScope: "mW MD state (hook layer); thermostat imposes the program; colour = CHILL+ phase detected per molecule"
  }));
}
};
