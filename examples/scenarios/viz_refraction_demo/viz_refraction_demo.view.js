// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["viz_refraction_demo"] = {
"viz0": function() { return {
    enable: true,
    maxTrajectories: 192,
    sampleEveryNth: 1,
    maxSegmentsPerTrajectory: 256,
    includeNonOptical: false,
    recordVertices: true
  }; },
"tags1": function() { return ["viz_emitter", "viz_forced_white"]; }
};
