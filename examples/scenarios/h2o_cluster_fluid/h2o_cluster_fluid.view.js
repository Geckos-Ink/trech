// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["h2o_cluster_fluid"] = {
"frame0": function(DT, FRAME_EVERY, R_DROP, T, TARGET_K, TOTAL_TICKS, com, contacts, helpers, r, rg, s, view) { return helpers.observer.frame(Object.assign(view, {
        physicalTimeS: s.tick * DT * 1e-15,
        phase: "NVT droplet (Berendsen), spherical restraint",
        lengthUnit: "angstrom", upAxis: "y", digits: 3,
        apparatus: contacts.concat([{ shape: "sphere", center: com, radius: R_DROP, style: "wire",
                                      color_rgba: [0.55, 0.7, 1.0, 0.25], label: "R_DROP restraint" }]),
        legend: helpers.observer.legend([["O", helpers.observer.elementRgba.O],
                                         ["H", helpers.observer.elementRgba.H],
                                         ["O-O < 3.5 A", [0.35, 0.85, 1.0, 1.0]]]),
        hud: ["T = " + T.toFixed(1) + " K   Rg = " + rg.toFixed(2) + " A   contacts " + r.hbonds],
        motionScope: "classical MD atoms (hook layer); Geant4 is the per-tick clock",
        samples: { T: Math.round(T * 10) / 10, rg: Math.round(rg * 1000) / 1000, contacts: r.hbonds },
        charts: s.tick === FRAME_EVERY ? [
          { id: "temp", title: "droplet temperature (Berendsen thermostat)", x: "time",
            x_scale: 1e15, x_label: "time (fs)", y_label: "K", cursor: true,
            series: [{ key: "T", label: "kinetic T", color: "#ff8a5c" }],
            reference: [{ label: "target", color: "#9ad0ff", x: [0, TOTAL_TICKS * DT],
                          y: [TARGET_K, TARGET_K] }] },
          { id: "shape", title: "droplet stays together", x: "time", x_scale: 1e15,
            x_label: "time (fs)", y_label: "Å / count", cursor: true,
            series: [{ key: "rg", label: "radius of gyration (Å)", color: "#c9d3e6" },
                     { key: "contacts", label: "O–O contacts < 3.5 Å", color: "#59d8ff" }] }
        ] : []
      })); }
};
