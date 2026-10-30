// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["chemistry_mode"] = {
"viz0": function() { return {enable: true, maxTrajectories: 16}; },
"frame1": function(frame) { return frame; }
};

Object.assign(TRECH_VIEWS["chemistry_mode"], {
"palette0": function() {return {H: [0.9, 0.94, 1, 1], C: [0.32, 0.39, 0.48, 1], N: [0.37, 0.48, 1, 1], O: [1, 0.34, 0.28, 1]};},
"colors1": function(molecule, palette) {return molecule.atoms.map(a => palette[a.element] || [0.65, 0.8, 0.6, 1]);}
});
