// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["cnt_band_structure"] = {
"frame0": function(bonds, colors, fitSlope, gapRgba, obs, positions, radii, tubes) { return obs.frame({
    physicalTimeS: 0, playbackTimeS: 0,
    clockText: tubes.length + " chiralities (static panel)",
    phase: "tight-binding zone-folding band gaps (hook layer)",
    lengthUnit: "nm", upAxis: "y", digits: 4,
    positions, colors, radii, bonds,
    legend: obs.legend([["armchair (metallic)", gapRgba({ metallic: true, curvature_secondary_gap_eV: 0 })],
                        ["quasi-metallic (curvature gap)", gapRgba({ metallic: true, curvature_secondary_gap_eV: 0.1 })],
                        ["semiconducting (deeper = wider gap)", gapRgba({ metallic: false, band_gap_eV: 0.8 })]]),
    hud: ["rows: armchair | quasi-metallic zigzag/chiral | semiconducting, by diameter",
          "E_g * d fit " + fitSlope.toFixed(3) + " eV nm  (2 a_cc gamma0; measured 0.7-0.9)"],
    motionScope: "static geometry from (n,m); colour = model band gap"
  }); }
};

Object.assign(TRECH_VIEWS["cnt_band_structure"], {
"emitPanelFrame": function(ctx, tubes, fitSlope, TRECH_VIEWS, gapRgba, helpers) {
  const obs = helpers.observer;
  const rows = [tubes.filter((t) => t.metallic && t.n === t.m),
                tubes.filter((t) => t.metallic && t.n !== t.m),
                tubes.filter((t) => !t.metallic)];
  const positions = [], colors = [], radii = [], bonds = [];
  rows.forEach((row, r) => {
    row.slice().sort((a, b) => a.diameter_nm - b.diameter_nm).forEach((t, k) => {
      const x0 = (k - 0.5 * (row.length - 1)) * 2.2;
      const geo = helpers.cnt.roll(t.n, t.m, 2.4, {
        place: (q) => [q[0] + x0, q[2] - 1.2, q[1] + (r - 1) * 4.0]
      });
      const base = positions.length;
      const rgba = gapRgba(t);
      for (const q of geo.atoms) { positions.push(q); colors.push(rgba); radii.push(0.07); }
      for (const b of geo.bonds) bonds.push([base + b[0], base + b[1]]);
    });
  });
  ctx.emit("material_frame", TRECH_VIEWS["cnt_band_structure"]["frame0"](bonds, colors, fitSlope, gapRgba, obs, positions, radii, tubes));
}
});
