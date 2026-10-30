// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["glass_of_water_varied"] = {
"viz0": function() { return {
    enable: true,
    maxTrajectories: 2000,
    sampleEveryNth: 1,
    maxSegmentsPerTrajectory: 64,
    includeNonOptical: false,
    recordVertices: true
  }; },
"tags1": function() { return ["viz_emitter", "viz_forced_white"]; }
};
