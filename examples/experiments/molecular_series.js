// First bounded electronic/torsional prediction group. See docs/molecular_series.md.
// Geant4 supplies live elemental identity + neutral-electron bookkeeping and
// actual particle transport. QM-trained surfaces supply charges/energies.
// Coordinates are imposed rigid scan samples, NOT predicted molecular dynamics.
TRECH_INCLUDE("trech_helpers.js");
TRECH_INCLUDE("../../data/molecular_series/series.js");
const observer = globalThis.TRECH_HELPERS.observer;
const molecule = TRECH_VALUE.choice("molecule", {
  label: "Molecule / comparison group", group: "Molecular series",
  default: globalThis.TRECH_MOLECULAR_PRESET || "ethanol",
  choices: ["ethane", "ethanol", "formamide"]
});
const mode = TRECH_VALUE.choice("mode", {
  label: "Inference mode", group: "Molecular series", default: "predictive",
  choices: ["predictive", "strict"]
});
const spec = globalThis.TRECH_MOLECULAR_SERIES[molecule];
const masses = {H: 1.008, C: 12.011, N: 14.007, O: 15.999};
const totalMass = Object.keys(spec.counts).reduce((s, el) => s + masses[el] * spec.counts[el], 0);
globalThis.TRECH_CONFIG = {
  detector: {worldSizeMm: 20, worldMaterial: "molecular_probe"},
  beam: {particle: "e-", energyMeV: 0.1, direction: [0, 0, 1]},
  run: {nEvents: spec.scan.length, seed: 20261022, threads: 1},
  determinism: {mode},
  // Unit-density homogeneous transport proxy, NOT a bound atomistic molecule.
  materials: [{name: "molecular_probe", densityGcm3: 1,
    components: Object.keys(spec.counts).map(el => ({element: el,
      fraction: masses[el] * spec.counts[el] / totalMass}))}],
  materialProbe: {enable: true, materials: ["molecular_probe"]},
  models: [{name: "electronic_response", scale: "atomic", path: "data/molecular_series/" + molecule + ".json"}],
  hooks: {maxEmitsPerCallback: 4, maxEmitPayloadBytes: 65536}
};

function liveInputs(ctx, angle) {
  const probe = ctx.materials && ctx.materials.molecular_probe;
  if (!probe || !probe.available || !Array.isArray(probe.elements))
    throw new Error("Molecular inference requires a real Geant4 elemental probe");
  let electrons = 0;
  for (const el of Object.keys(spec.counts)) {
    const atom = probe.elements.find(row => row.symbol === el);
    if (!atom || !Number.isFinite(atom.z)) throw new Error("Missing Geant4 element: " + el);
    electrons += atom.z * spec.counts[el];
  }
  if (electrons !== spec.neutral_electrons) throw new Error("Molecular electron budget differs from fitted neutral scaffold");
  const inputs = {neutral_electrons: electrons};
  const radians = angle * Math.PI / 180;
  for (let k = 1; k <= spec.fourier_order; ++k) {
    inputs["cos_" + k] = Math.cos(k * radians);
    inputs["sin_" + k] = Math.sin(k * radians);
  }
  return inputs;
}

function emitView(ctx, sample, prediction, index) {
  const count = spec.elements.length;
  const colors = [], radii = [], positions = [], labels = [];
  const cpk = {H: [0.88, 0.92, 1, 1], C: [0.32, 0.39, 0.48, 1],
               N: [0.37, 0.48, 1, 1], O: [1, 0.34, 0.28, 1]};
  const center = sample.positions_angstrom.reduce((s, p) => s.map((v, j) => v + p[j] / count), [0, 0, 0]);
  for (let i = 0; i < count; ++i) {
    const p = sample.positions_angstrom[i].map((v, j) => v - center[j]);
    positions.push(p);
    colors.push(cpk[spec.elements[i]]);
    radii.push(spec.elements[i] === "H" ? 0.16 : 0.25);
    if (prediction) {
      const q = prediction["charge_" + i + "_e"];
      // A charge glyph centered on each atom, volume proportional to |q|.
      // This is a display choice, not an orbital/ESP/electron-density isosurface.
      positions.push(p);
      colors.push(q < 0 ? [1, 0.22, 0.31, 0.27] : [0.2, 0.67, 1, 0.24]);
      radii.push(0.85 * Math.cbrt(Math.abs(q)));
      if (spec.elements[i] !== "H" || spec.torsion_atoms[0] === i || spec.torsion_atoms[3] === i)
        labels.push({position: [p[0], p[1] + 0.45, p[2]],
        text: spec.elements[i] + (q >= 0 ? " +" : " ") + q.toFixed(2) + " e",
        color_rgba: q < 0 ? [1, 0.6, 0.6, 1] : [0.55, 0.82, 1, 1]});
    }
  }
  const atomIndex = i => prediction ? i * 2 : i;
  const bonds = spec.bonds.map(b => b.map(atomIndex));
  const bond = spec.torsion_atoms.slice(1, 3).map(atomIndex);
  const a = positions[bond[0]], b = positions[bond[1]];
  const length = Math.hypot(...b.map((v, j) => v - a[j]));
  const axis = b.map((v, j) => (v - a[j]) / length);
  // Two marked endpoints extend the selected torsion axis, representation only.
  const base = positions.length;
  positions.push(a.map((v, j) => v - 0.8 * axis[j]), b.map((v, j) => v + 0.8 * axis[j]));
  colors.push([1, 0.81, 0.25, 1], [1, 0.81, 0.25, 1]);
  radii.push(0.07, 0.07); bonds.push([base, base + 1]);
  const v = spec.validation;
  ctx.emit("material_frame", observer.frame({
    positions, colors, radii, bonds, labels,
    physicalTimeS: 0, playbackTimeS: index / (spec.scan.length - 1) * 8,
    lengthUnit: "angstrom", upAxis: "y",
    clockText: "torsion " + sample.angle_deg.toFixed(1) + "° | parameter scan",
    phase: spec.group + " | " + molecule,
    motionScope: "imposed rigid torsion scan; no physical time or predicted nuclear trajectory",
    legend: observer.legend([["electron rich (q < 0)", [1, 0.22, 0.31, 1]],
      ["electron poor (q > 0)", [0.2, 0.67, 1, 1]], ["selected torsion axis", [1, 0.81, 0.25, 1]]]),
    hud: [prediction ? "Learned RHF/STO-3G | ΔE " + prediction.relative_energy_kcal_mol.toFixed(2) + " kcal/mol"
                                  : "STRICT: inference disabled; scaffold only",
      "Rigid scan barrier " + v.rigid_barrier_kcal_mol.toFixed(2) + " kcal/mol | not a free-energy barrier",
      "Held-out energy RMSE " + v.energy_holdout_rmse_kcal_mol.toExponential(1) + " kcal/mol",
      "PubChem CID " + v.pubchem.cid + " | bond MAE " + v.pubchem.bond_length_mae_angstrom.toFixed(3) + " Å",
      prediction ? "Measured domain: " + (prediction.__coverage.inDomain ? "in range" : "OUTSIDE") +
        " | joint gap: " + prediction.__coverage.jointStarved +
        " | empty bins: " + prediction.__coverage.starvedInputs.length : "No inferred charge bubbles"],
    samples: {angle: sample.angle_deg, energy: prediction ? prediction.relative_energy_kcal_mol : undefined,
      reference_energy: sample.reference_energy_kcal_mol},
    charts: [{id: "torsion", title: "Rigid torsional capacity", x: "angle", x_label: "torsion (degrees)",
      x_range: [0, 360], y_label: "relative energy (kcal/mol)",
      note: "Held-out angles • no relaxation or thermal populations",
      series: [{key: "energy", label: "C++ learned response", color: "#59cfff"},
               {key: "reference_energy", label: "independent RHF reference", color: "#ffc766", dashed: true}]}]
  }));
}

globalThis.TRECH_HOOKS = {
  onEventEnd(ctx) {
    const index = ctx.event.id;
    if (index >= spec.scan.length) return;
    const sample = spec.scan[index];
    const inputs = liveInputs(ctx, sample.angle_deg);
    const prediction = ctx.predict("electronic_response", inputs);
    if (mode === "predictive" && !prediction) throw new Error("Electronic model unavailable; refusing fabricated bubbles");
    const charges = prediction ? spec.elements.map((_, i) => prediction["charge_" + i + "_e"]) : null;
    if (charges && (charges.some(q => !Number.isFinite(q)) || Math.abs(charges.reduce((s, q) => s + q, 0)) > 1e-7))
      throw new Error("Learned charge budget is invalid");
    ctx.emit("molecular_prediction", {molecule, group: spec.group, angle_deg: sample.angle_deg,
      inputs, charges_e: charges, relative_energy_kcal_mol: prediction ? prediction.relative_energy_kcal_mol : null,
      reference_energy_kcal_mol: sample.reference_energy_kcal_mol,
      reference_charges_e: sample.reference_charges_e, coverage: prediction ? prediction.__coverage : null,
      accuracy: prediction ? prediction.__accuracy : null, geant4_edep_mev: ctx.event.edepMeV,
      physics_scope: spec.notes, expected_model_sha256: spec.model_sha256});
    emitView(ctx, sample, prediction, index);
    if (index === spec.scan.length - 1) ctx.emit("molecular_summary", {
      molecule, mode, scan_samples: spec.scan.length, validation: spec.validation, physics_scope: spec.notes});
  }
};
