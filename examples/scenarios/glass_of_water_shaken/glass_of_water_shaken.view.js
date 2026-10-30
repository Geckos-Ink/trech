// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["glass_of_water_shaken"] = {
"frame0": function(maxSpeed, n, pouring, r4, s, sNow, settling, splash, surfStd, t, xyz) { return {
        tick: s.tick, time_s: r4(t),
        phase: pouring ? "pour" : (settling ? "settle" : "shake"),
        active: n, glass_xy_m: [r4(sNow[0]), r4(sNow[1])],
        max_speed: r4(maxSpeed), surf_roughness_m: r4(surfStd), splash_height_m: r4(splash),
        xyz
      }; },
"frame1": function(H_WALL, RENDER_GRID_MM, R_IN, S0, SHAKE_CHARTS, glassRgba, helpers, mm, n, pouring, s, sNow, settling, splash, surfStd, t, waterRgba) { return helpers.observer.frame({
        physicalTimeS: t,
        phase: pouring ? "pour" : (settling ? "settle" : "shake"),
        positions: mm,
        colors: mm.map(() => waterRgba),
        digits: 2,
        apparatus: [
          { shape: "cylinder", center: [sNow[0] * 1000.0, sNow[1] * 1000.0, H_WALL * 500.0],
            radius: R_IN * 1000.0, height: H_WALL * 1000.0, axis: "z", style: "open",
            color_rgba: glassRgba, label: "glass (shaken)" },
          { shape: "cylinder", center: [sNow[0] * 1000.0, sNow[1] * 1000.0, -2.0],
            radius: R_IN * 1000.0 + 3.0, height: 4.0, axis: "z",
            color_rgba: [0.8, 0.9, 1.0, 0.3], label: "glass base" }
        ],
        hud: [
          n + " PBF particles   rho0 " + (s.restDensity || 0).toFixed(1) + " kg/m^3 (cascade)",
          "surface roughness " + (surfStd * 1000.0).toFixed(2) + " mm   splash " +
            (Math.max(0, splash) * 1000.0).toFixed(1) + " mm"
        ],
        renderSurface: {
          mode: "metaball", kernel: "gaussian", grid_spacing_mm: RENDER_GRID_MM,
          // Tight enough that the fused surface stays within ~a particle margin of the glass
          // wall; neighbours 6 mm apart still fuse (2 * exp(-9 / (2 sigma^2)) > iso).
          sigma_mm: 0.62 * S0 * 1000.0, iso_level: 0.42, opacity: 0.93, gloss: 0.8,
          fresnel_r0: 0.02, positions_unmodified: true,
          policy: "representation only: Gaussian fusion of PBF particle centres"
        },
        motionScope: "hook-layer PBF particles (cascade-inferred macro params); glass at s(tau)",
        samples: { glass_x_mm: Math.round(sNow[0] * 1e5) / 100, particles: n,
                   roughness_mm: Math.round(surfStd * 1e5) / 100,
                   splash_mm: Math.round(Math.max(0, splash) * 1e4) / 10 },
        charts: SHAKE_CHARTS.declared ? [] : (SHAKE_CHARTS.declared = true, [
          { id: "drive", title: "the shake: glass position (prescribed drive)", x: "time",
            x_label: "time (s)", y_label: "mm", cursor: true,
            series: [{ key: "glass_x_mm", label: "glass x", color: "#c9d3e6" }] },
          { id: "waves", title: "the water's response (PBF solver)", x: "time", x_label: "time (s)",
            y_label: "mm", cursor: true,
            series: [{ key: "roughness_mm", label: "surface roughness", color: "#59bfff" },
                     { key: "splash_mm", label: "splash height", color: "#ffd24d" }] }
        ])
      }); }
};

Object.assign(TRECH_VIEWS["glass_of_water_shaken"], {
"RENDER_GRID_MM0": function() { return 2.0; }
});
