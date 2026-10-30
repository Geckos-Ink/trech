// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["h2o_diffusion_temperature"] = {
"frame0": function(BOXL, DT, MELT_K, TRAIL_RGBA, charts, curves, helpers, hud, phase, s, sim, targetK, trails, view) { return helpers.observer.frame(Object.assign(view, {
    physicalTimeS: s.tick * DT * 1e-15,
    phase,
    lengthUnit: "angstrom", upAxis: "y", digits: 3,
    apparatus: trails.concat([{ shape: "box", center: [BOXL / 2, BOXL / 2, BOXL / 2],
                                size: [BOXL, BOXL, BOXL], style: "wire",
                                color_rgba: [0.55, 0.7, 1.0, 0.6], label: "periodic cell" }]),
    legend: helpers.observer.legend([["278 K trail", TRAIL_RGBA[278]], ["298 K trail", TRAIL_RGBA[298]],
                                     ["318 K trail", TRAIL_RGBA[318]]]),
    hud,
    samples: { temperature_K: Math.round(sim.temperature() * 10) / 10,
               target_K: targetK || MELT_K },
    charts, curves,
    motionScope: "rigid-SPC/E MD state (hook layer); trails = real unwrapped O displacement"
  })); }
};

Object.assign(TRECH_VIEWS["h2o_diffusion_temperature"], {
"emitObserverFrame": function(ctx, s, phase, targetK, BOXL, DT, EXP_D_TABLE, FRAME_EVERY, Float64Array, MAX_LAG, MELT_K, TRAIL_FRAMES, TRAIL_RGBA, TRECH_VIEWS, helpers, md) {
  const sim = s.sim;
  const nO = sim.mols.length;
  const now = new Float64Array(nO * 3);
  for (let i = 0; i < nO; i++) {
    const O = sim.atoms[sim.mols[i].O].p;
    now[3 * i] = O[0]; now[3 * i + 1] = O[1]; now[3 * i + 2] = O[2];
  }
  s.trailRing.push(now);
  if (s.trailRing.length > TRAIL_FRAMES + 1) s.trailRing.shift();
  const then = s.trailRing[0];
  const xyz = sim.snapshotXyz();
  const view = helpers.observer.atoms(md.moleculesFromXyz(xyz));
  const trailRgba = TRAIL_RGBA[targetK] || TRAIL_RGBA.melt;
  const trails = [];
  let meanDisp = 0;
  for (let i = 0; i < nO; i++) {
    const tip = xyz[3 * i];
    const dx = now[3 * i] - then[3 * i], dy = now[3 * i + 1] - then[3 * i + 1];
    const dz = now[3 * i + 2] - then[3 * i + 2];
    meanDisp += Math.sqrt(dx * dx + dy * dy + dz * dz) / nO;
    trails.push({ shape: "segment", from: [tip[0] - dx, tip[1] - dy, tip[2] - dz], to: tip,
                  color_rgba: trailRgba });
  }
  const span = (s.trailRing.length - 1) * FRAME_EVERY * DT;
  const hud = ["T = " + sim.temperature().toFixed(1) + " K" +
               (targetK ? "  (block target " + targetK + " K)" : "  (one-time lattice melt)"),
               "mean O displacement over last " + span.toFixed(0) + " fs: " +
               meanDisp.toFixed(2) + " A"];
  for (const point of s.points) {
    hud.push("D(" + point.mean_temperature_K.toFixed(0) + " K) = " +
             (point.self_diffusion_m2_per_s * 1e9).toFixed(2) + " e-9 m^2/s (MSD fit)");
  }
  // Side charts: the thermostat steps, each block's own multi-origin MSD(lag), and D(T) against
  // the measured Holz 2000 table (comparison only; it never feeds the MD).
  const curves = [];
  const blockColor = (k) => "#" + TRAIL_RGBA[k].slice(0, 3)
    .map((c) => Math.round(c * 255).toString(16).padStart(2, "0")).join("");
  for (const block of s.msdCurves) {
    curves.push({ chart: "msd", label: block.targetK + " K", color: blockColor(block.targetK),
                  x: block.x, y: block.y });
  }
  if (targetK && s.msdCnt[1] > 0) {
    const x = [], y = [];
    for (let lag = 10; lag <= MAX_LAG; lag += 10) {
      if (s.msdCnt[lag] > 0) {
        x.push(Math.round(lag * DT) / 1000);
        y.push(Math.round((s.msdSum[lag] / s.msdCnt[lag]) * 1000) / 1000);
      }
    }
    if (x.length) curves.push({ chart: "msd", label: targetK + " K (measuring)",
                                color: blockColor(targetK), x, y });
  }
  if (s.points.length) {
    curves.push({ chart: "dt", label: "this MD (MSD slope / 6)", color: "#ffd24d", style: "points",
                  x: s.points.map((p) => Math.round(p.mean_temperature_K * 10) / 10),
                  y: s.points.map((p) => Math.round(p.self_diffusion_m2_per_s * 1e12) / 1000) });
  }
  const charts = s.chartsDeclared ? [] : [
    { id: "temp", title: "thermostat: melt, then 278 → 298 → 318 K", x: "time", x_scale: 1e12,
      x_label: "time (ps)", y_label: "K", cursor: true,
      series: [{ key: "temperature_K", label: "MD kinetic T", color: "#ff8a5c" },
               { key: "target_K", label: "block target", color: "#9ad0ff", dashed: true }] },
    { id: "msd", title: "mean-square displacement per block", x_label: "lag (ps)",
      y_label: "MSD (Å²)", x_range: [0, MAX_LAG * DT / 1000] },
    { id: "dt", title: "self-diffusion D(T)", x_label: "T (K)", y_label: "D (10⁻⁹ m²/s)",
      x_range: [272, 324], y_range: [0, 4.2],
      reference: [{ label: "measured water (Holz 2000)", color: "#9ad0ff",
                    x: EXP_D_TABLE.map((r) => r[0]), y: EXP_D_TABLE.map((r) => r[1]) }] }
  ];
  s.chartsDeclared = true;
  ctx.emit("material_frame", TRECH_VIEWS["h2o_diffusion_temperature"]["frame0"](BOXL, DT, MELT_K, TRAIL_RGBA, charts, curves, helpers, hud, phase, s, sim, targetK, trails, view));
}
});
