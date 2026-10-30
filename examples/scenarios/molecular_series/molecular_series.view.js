// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["molecular_series"] = {
"frame0": function(payload) { return payload; }
};

Object.assign(TRECH_VIEWS["molecular_series"], {
"colors0": function(colors) {return colors;},
"legend1": function(observer, particleEnabled) {return observer.legend([[particleEnabled ? "QM electron rich (q < 0)" : "electron rich (q < 0)", [1, 0.22, 0.31, 1]],
      [particleEnabled ? "QM electron poor (q > 0)" : "electron poor (q > 0)", [0.2, 0.67, 1, 1]], ["selected torsion axis", [1, 0.81, 0.25, 1]]]
      .concat(particleEnabled ? [["ML photon response", [0.62, 0.36, 1, 1]]] : []));}
});
