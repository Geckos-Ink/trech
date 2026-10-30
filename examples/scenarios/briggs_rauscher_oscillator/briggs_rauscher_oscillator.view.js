// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["briggs_rauscher_oscillator"] = {
"frame0": function(apparatus, charts, helpers, physicalTimeS, regime, rgb, s, samples) { return helpers.observer.frame({
    physicalTimeS: physicalTimeS,
    phase: "briggs_rauscher:" + regime,
    upAxis: "y",
    positions: [], colors: [],
    apparatus,
    samples, charts,
    legend: helpers.observer.legend([["solution colour: emergent", [rgb[0], rgb[1], rgb[2], 1]],
                                     ["stir bar rotation: representation", [0.97, 0.97, 0.98, 1]]]),
    hud: [
      "cycle " + s.cycles.length + "   " + regime.replace(/_/g, " "),
      "[I2] " + s.iodine2.toFixed(3) + "   [I-] " + s.iodide.toFixed(3) +
        "   reservoir " + s.reservoir.toFixed(3) + "  (dimensionless, emergent)"
    ],
    motionScope: "well-mixed oscillator: no spatial motion exists; colour is the emergent state; stir bar is representation"
  }); },
"viz1": function() { return { enable: true, maxTrajectories: 0, sampleEveryNth: 1,
         maxSegmentsPerTrajectory: 32, includeNonOptical: false, recordVertices: true }; },
"tags2": function() { return ["beaker", "glass", "viz_shell"]; },
"tags3": function() { return ["viz_hidden"]; },
"tags4": function() { return ["viz_hidden"]; },
"tags5": function() { return ["viz_hidden"]; }
};

Object.assign(TRECH_VIEWS["briggs_rauscher_oscillator"], {
"REPRESENTATION0": function() { return {
  policy: "amber/blue swatches are authored display; colourless base is Geant4-derived; colour TIMING is emergent",
  amberTint: [0.86, 0.52, 0.06],
  // Deep navy (the starch-triiodide complex reads blue-black); a saturating weight
  // 1 - exp(-k * intensity) makes the regime the colour classifier reports actually visible.
  blueBlackTint: [0.05, 0.08, 0.42],
  amberWeightK: 2.6,
  blueWeightK: 5.0,
  amberDisplayGain: 3.2,
  blueDisplayGain: 6.0
}; }
});

Object.assign(TRECH_VIEWS["briggs_rauscher_oscillator"], {
"REPRESENTATION_FILL_FRACTION0": function() {return 0.62;}
});
