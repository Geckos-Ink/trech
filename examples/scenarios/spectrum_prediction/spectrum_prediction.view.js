// Representation of recorded state only; these functions never advance simulation state.
TRECH_VIEWS["spectrum_prediction"] = {
"viz0": function() { return {enable: true, maxTrajectories: 4}; },
// Display hints for the Studio Spectra dock: colors and axis labels are rendering choices.
"display1": function(record) {
  return {measured_color: [0.20, 0.55, 0.95, 1], predicted_color: [0.95, 0.45, 0.15, 1],
    x_label: "wavelength (" + record.grid.unit + ")",
    y_label: record.kind === "atom" ? "log-compressed g·A line strength (shape)" : "log10(1+ε)/5 absorption envelope",
    title: record.label + (record.split === "test" ? " · held-out" : record.split === "train" ? " · training member" : "")};
}
};
