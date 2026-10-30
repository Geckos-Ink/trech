// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["h2o_molecule_stability"] = {
"frame0": function(DEG, DT, FRAME_EVERY, R0, THETA0, TOTAL_TICKS, molecule, obs, observer, state) { return observer.frame(Object.assign(molecule, {
        physicalTimeS: state.tick * DT * 1e-15,
        phase: "NVE velocity-Verlet (flexible harmonic water)",
        lengthUnit: "angstrom",
        upAxis: "y",
        legend: observer.legend([["O", observer.elementRgba.O], ["H", observer.elementRgba.H]]),
        hud: [
          "O-H " + obs.bond1.toFixed(3) + " / " + obs.bond2.toFixed(3) + " A   (r0 " +
            R0.toFixed(4) + ")",
          "H-O-H " + (obs.angle / DEG).toFixed(2) + " deg  (theta0 " +
            (THETA0 / DEG).toFixed(2) + ")   E_tot " + obs.etot.toExponential(3)
        ],
        motionScope: "classical MD nuclei (hook layer); Geant4 is the per-tick clock",
        samples: { bond1: Math.round(obs.bond1 * 1e4) / 1e4, bond2: Math.round(obs.bond2 * 1e4) / 1e4,
                   angle: Math.round(obs.angle / DEG * 100) / 100 },
        charts: state.tick === FRAME_EVERY ? [
          { id: "bonds", title: "O–H bond lengths (the two bonds vibrate)", x: "time",
            x_scale: 1e15, x_label: "time (fs)", y_label: "Å", cursor: true,
            series: [{ key: "bond1", label: "O–H₁", color: "#ff6b5a" },
                     { key: "bond2", label: "O–H₂", color: "#e8ecf4" }],
            reference: [{ label: "r₀ (force-field rest length)", color: "#9ad0ff",
                          x: [0, TOTAL_TICKS * DT], y: [R0, R0] }] },
          { id: "angle", title: "H–O–H bending", x: "time", x_scale: 1e15, x_label: "time (fs)",
            y_label: "degrees", cursor: true,
            series: [{ key: "angle", label: "H–O–H angle", color: "#ffd24d" }],
            reference: [{ label: "θ₀", color: "#9ad0ff", x: [0, TOTAL_TICKS * DT],
                          y: [THETA0 / DEG, THETA0 / DEG] }] }
        ] : []
      })); }
};
