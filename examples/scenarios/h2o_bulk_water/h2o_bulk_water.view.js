// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["h2o_bulk_water"] = {
"frame0": function(BOXL, DT, RDF_RMAX, accumulate, curves, helpers, hud, s, temperatureK, view) { return helpers.observer.frame(Object.assign(view, {
        physicalTimeS: s.tick * DT * 1e-15,
        phase: accumulate ? "production (g(r) accumulating)" : "equilibration",
        lengthUnit: "angstrom", upAxis: "y", digits: 3,
        apparatus: [{ shape: "box", center: [BOXL / 2, BOXL / 2, BOXL / 2],
                      size: [BOXL, BOXL, BOXL], style: "wire",
                      color_rgba: [0.55, 0.7, 1.0, 0.7], label: "periodic cell" }],
        legend: helpers.observer.legend([["O", helpers.observer.elementRgba.O],
                                         ["H", helpers.observer.elementRgba.H]]),
        hud,
        samples: { temperature_K: Math.round(temperatureK * 10) / 10 },
        curves,
        // Side charts: the emergent O-O g(r) as it accumulates, and the thermostatted T.
        charts: s.tick === 1 ? [
          { id: "gr", title: "O–O radial distribution g(r)", x_label: "r (Å)",
            y_label: "g(r)", x_range: [2.0, RDF_RMAX], y_range: [0.0, 3.4],
            vlines: [{ x: 2.8, label: "measured first peak ~2.8 Å", color: "#9ad0ff" }] },
          { id: "temp", title: "temperature (equilibration, then production)", x: "time",
            x_scale: 1e12, x_label: "time (ps)", y_label: "K", cursor: true,
            series: [{ key: "temperature_K", label: "MD kinetic T", color: "#ff8a5c" }] }
        ] : [],
        motionScope: "wrapped rigid-SPC/E MD state (hook layer); Geant4 is the per-tick clock"
      })); }
};
