// A recorded inference diagram, with authored layout and fractional glyph sizes.
// Diagram positions are not photon paths, particle positions or physical time.
TRECH_VIEWS.particle_observer_cascade = {
  frame: function(observer, prediction) {
    const p = prediction.predicted;
    const available = prediction.prediction_available;
    const percent = value => value === null ? "disabled" : (100 * value).toFixed(2) + "%";
    return observer.frame({
      physicalTimeS: 0, playbackTimeS: 0, lengthUnit: "diagram", upAxis: "y",
      positions: [[-3, 0, 0], [0, 0, 0], [3, 1, 0], [3, -1, 0]],
      colors: [[0.6, 0.4, 1, 1], [0.3, 0.7, 1, 1], [0.3, 0.9, 0.7, 1], [1, 0.65, 0.3, 1]],
      radii: [0.35, 0.45, available ? 0.6 * Math.cbrt(p.uncollided_fraction) : 0.12,
        available ? 0.6 * Math.cbrt(p.deposited_energy_fraction) : 0.12],
      bonds: [[0, 1], [1, 2], [1, 3]],
      labels: [
        {position: [-3, 0.8, 0], text: prediction.atom_count + (available ? " inferred atom responses" : " declared atoms")},
        {position: [0, 0.8, 0], text: available ? "nano composition" : "nano inference disabled"},
        {position: [3, 1.8, 0], text: "uncollided: " + percent(p.uncollided_fraction)},
        {position: [3, -1.8, 0], text: "deposited energy: " + percent(p.deposited_energy_fraction)}
      ],
      phase: prediction.material + " | " + prediction.energy_kev + " keV",
      clockText: "Prediction before Monte Carlo transport; no physical time",
      motionScope: "Static inference diagram. Layout, links and sphere volumes are display choices; not atomistic structure or photon trajectories.",
      hud: [available ? "Experimental Geant4-trained candidate | " + prediction.inference_count + " model evaluations"
                      : "STRICT: all learned stages disabled",
        "Unit-density proxy | centre-to-face path " + prediction.half_length_mm + " mm",
        "Atomic tables → nano composition → meso MC-trained observer",
        prediction.heldout_residual_rmse ? "Global held-out RMSE only; not a calibrated interval" : "Held-out residual unavailable",
        "Independent Monte Carlo tallies are written at run end; no experimental accuracy claim"],
      counts: {atomic_inferences: prediction.atomic_inference_count,
        cascade_inferences: prediction.cascade_inference_count}
    });
  }
};
