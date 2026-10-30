// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["validation_glass_of_water"] = {
"viz0": function() { return {
    enable: true,
    // Big enough to give the inverse-Snell statistics decent
    // resolution while staying small enough to keep the JSONL
    // manageable. Cap-per-trajectory is generous because each photon
    // can refract up to four times in this geometry (air->glass,
    // glass->water, water->glass, glass->air) and we want headroom
    // for Fresnel reflections that bounce back.
    maxTrajectories: 4000,
    sampleEveryNth: 1,
    maxSegmentsPerTrajectory: 64,
    includeNonOptical: false,
    recordVertices: true
  }; },
"tags1": function() { return ["viz_emitter", "viz_forced_white"]; }
};
