// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["testscenario_pascal"] = {
"frame0": function(PASCAL_RGBA, TOTAL_TICKS, WALL_DISPLAY_GAIN, apparatus, charts, colors, currentPhase, heat, helpers, labels, positions, radii, samples, tick) { return helpers.observer.frame({
    physicalTimeS: tick, playbackTimeS: tick,
    clockText: "tick " + tick + " / " + TOTAL_TICKS + " (" + currentPhase(tick) + ")",
    phase: "piston " + currentPhase(tick) + " (3D bath; vessels in a row)",
    lengthUnit: "sim_unit", upAxis: "y", digits: 2,
    positions, colors, radii, apparatus,
    legend: helpers.observer.legend([["H2O bath", PASCAL_RGBA.water], ["piston", PASCAL_RGBA.piston],
                                     ["wall at rest", heat(0.0)], ["wall displaced", heat(1.0)],
                                     ["displacement drawn ×" + WALL_DISPLAY_GAIN, [0.8, 0.8, 0.85, 1]]]),
    hud: ["piston " + currentPhase(tick) + ": the same push reaches every wall"],
    samples, charts, labels,
    motionScope: "hook-layer 3D bath, piston and sensor-wall patches (solver state)"
  }); }
};

Object.assign(TRECH_VIEWS["testscenario_pascal"], {
"emitPascalFrame": function(ctx, state, tick, snaps, PASCAL, PASCAL_RGBA, TOTAL_TICKS, TRECH_VIEWS, VESSEL_OFFSET_X, WALL_DISPLAY_GAIN, currentPhase, heat, helpers, meanPlasticWallDisplacement, meanWallDisplacement, wallMesh) {
  const positions = [], colors = [], radii = [], apparatus = [], hud = [];
  const samples = {}, labels = [];
  state.buckets.forEach((bucket, k) => {
    const offsetX = (k - 1) * VESSEL_OFFSET_X;
    for (const p of bucket.particles) {
      positions.push([p.x + offsetX, p.y, p.z]);
      colors.push(PASCAL_RGBA.water);
      radii.push(p.radius);
    }
    const mesh = wallMesh(bucket.sensorSegments, offsetX);
    const bulge = meanWallDisplacement(bucket.sensorSegments);
    apparatus.push({ shape: "mesh", vertices: mesh.vertices, faces: mesh.faces,
                     vertex_rgba: mesh.vertexRgba, color_rgba: [0.7, 0.7, 0.9, 0.9],
                     label: bucket.name + " sensor wall" });
    // The wall's undeformed rest plane, so the bulge is read against it.
    const restX = bucket.sensorSegments[0].initialRest + offsetX;
    apparatus.push({ shape: "box", center: [restX, 0, 0],
                     size: [0.05, 2 * PASCAL.domainHalfY, 2 * PASCAL.domainHalfZ], style: "wire",
                     color_rgba: [0.9, 0.9, 1.0, 0.8], label: "rest plane" });
    apparatus.push({ shape: "box", center: [bucket.pistonX - 0.6 + offsetX, 0, 0],
                     size: [1.2, 2 * PASCAL.domainHalfY, 2 * PASCAL.domainHalfZ],
                     color_rgba: PASCAL_RGBA.piston, label: "piston" });
    apparatus.push({ shape: "box", center: [offsetX, 0, 0],
                     size: [2 * PASCAL.domainHalfX, 2 * PASCAL.domainHalfY, 2 * PASCAL.domainHalfZ],
                     style: "wire", color_rgba: PASCAL_RGBA.chamber, label: "chamber" });
    const snap = snaps[k];
    const ratio = snap.piston_pressure_from_collisions > 0
      ? snap.sensor_pressure / snap.piston_pressure_from_collisions : 0.0;
    samples["ratio_" + k] = Math.round(ratio * 1000) / 1000;
    samples["bulge_" + k] = Math.round(bulge * 1000) / 1000;
    samples["plastic_" + k] = Math.round(meanPlasticWallDisplacement(bucket.sensorSegments) * 1000) / 1000;
    labels.push({ position: [offsetX, PASCAL.domainHalfY + 8.0, 0],
                  text: ["rigid wall", "Hookean (plastic) wall", "fine-mesh wall"][k] || bucket.name,
                  color_rgba: [0.85, 0.9, 1.0, 1] });
  });
  const names = ["rigid", "Hookean", "fine mesh"];
  const colours = ["#c9d3e6", "#ffb838", "#66e0ff"];
  const charts = !state.chartsDeclared ? [
    { id: "ratio", title: "Pascal: pressure at the wall / at the piston", x: "time",
      x_label: "solver tick", y_label: "P_sensor / P_piston", cursor: true, y_range: [0, 2.0],
      series: names.map((n, k) => ({ key: "ratio_" + k, label: n, color: colours[k] })),
      reference: [{ label: "Pascal: equal (1.0)", color: "#9aa4b8", x: [0, TOTAL_TICKS], y: [1, 1] }] },
    { id: "bulge", title: "mean wall bulge (solid) and permanent set (dashed)", x: "time",
      x_label: "solver tick", y_label: "displacement (sim units)", cursor: true,
      series: names.map((n, k) => ({ key: "bulge_" + k, label: n, color: colours[k] }))
        .concat(names.slice(1).map((n, j) => ({ key: "plastic_" + (j + 1), label: n + " plastic",
                                                 color: colours[j + 1], dashed: true }))) }
  ] : [];
  state.chartsDeclared = true;
  ctx.emit("material_frame", TRECH_VIEWS["testscenario_pascal"]["frame0"](PASCAL_RGBA, TOTAL_TICKS, WALL_DISPLAY_GAIN, apparatus, charts, colors, currentPhase, heat, helpers, labels, positions, radii, samples, tick));
}
});
