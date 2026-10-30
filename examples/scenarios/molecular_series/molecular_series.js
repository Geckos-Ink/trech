// First bounded electronic/torsional prediction group. See docs/molecular_series.md.
// Geant4 supplies live elemental identity + neutral-electron bookkeeping and
// actual particle transport. QM-trained surfaces supply charges/energies.
// Coordinates are imposed rigid scan samples, NOT predicted molecular dynamics.
TRECH_INCLUDE("../../../js/trech_helpers.js");
TRECH_INCLUDE("../../../data/molecular_series/series.js");
TRECH_INCLUDE("../../../js/trech_molecular_particle.js");
const observer = globalThis.TRECH_HELPERS.observer;
const molecule = TRECH_PARAMETER("molecule");
const mode = TRECH_PARAMETER("mode");
const spec = globalThis.TRECH_MOLECULAR_SERIES[molecule];
const particleModule = globalThis.TRECH_MOLECULAR_PARTICLE;
const particleEnabled = TRECH_PARAMETER("particle_response");
const masses = particleEnabled ? particleModule.data.atomic_masses : {H: 1.008, C: 12.011, N: 14.007, O: 15.999};
const totalMass = Object.keys(spec.counts).reduce((s, el) => s + masses[el] * spec.counts[el], 0);
globalThis.TRECH_CONFIG = {
  detector: {worldSizeMm: 20, worldMaterial: "molecular_probe"},
  beam: {particle: particleEnabled ? "gamma" : "e-", energyMeV: particleEnabled ? 0.003 : 0.1, direction: [0, 0, 1]},
  physics: particleEnabled ? {list: "QBBC_LIV"} : {},
  run: {nEvents: spec.scan.length * (particleEnabled ? 2 : 1), seed: 20261022, threads: 1},
  determinism: {mode},
  // Unit-density homogeneous transport proxy, NOT a bound atomistic molecule.
  materials: [{name: "molecular_probe", densityGcm3: 1,
    components: Object.keys(spec.counts).map(el => ({element: el,
      fraction: masses[el] * spec.counts[el] / totalMass}))}],
  materialProbe: {enable: true, materials: ["molecular_probe"]},
  models: [{name: "electronic_response", scale: "atomic", path: "data/molecular_series/" + molecule + ".json"}]
    .concat(particleEnabled ? particleModule.models() : []),
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

function emitView(ctx, sample, prediction, index, response, particleScan, referenceSigma) {
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
      if (response) {
        positions.push(p);
        colors.push([0.62, 0.36, 1, 0.18]);
        // Representation: halo volume proportional to inferred photoelectric
        // cross section, using one fixed display scale for every molecule/energy.
        radii.push(0.85 * Math.cbrt(response.atomic_state.phot_barn[i] / 10000));
      }
    }
  }
  const atomIndex = i => prediction ? i * (response ? 3 : 2) : i;
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
  const particleDomain = response ? "Particle domain: measured | OOD " +
    (response.atomic_trace.reduce((s, t) => s + t.elementsOutOfDomain, 0) + response.molecular_trace.stagesExtrapolating) +
    " | joint gaps " + (response.atomic_trace.reduce((s, t) => s + t.elementsJointStarved, 0) +
      response.molecular_trace.trace.filter(t => t.jointStarved).length) : "";
  const payload = observer.frame({
    positions, colors: TRECH_VIEWS["molecular_series"]["colors0"](colors), radii, bonds, labels,
    physicalTimeS: 0, playbackTimeS: (index % spec.scan.length) / (spec.scan.length - 1) * 8,
    lengthUnit: "angstrom", upAxis: "y",
    clockText: particleScan ? "photon energy " + responseEnergy(index).toFixed(0) + " eV | parameter scan" :
      "torsion " + sample.angle_deg.toFixed(1) + "° | parameter scan",
    phase: spec.group + " | " + molecule,
    motionScope: particleScan ? "fixed scaffold and photon-energy parameter scan; no physical time" :
      "imposed rigid torsion scan; no physical time or predicted nuclear trajectory",
    legend: TRECH_VIEWS["molecular_series"]["legend1"](observer, particleEnabled),
    hud: [prediction ? "QM reference fit | ΔE " + prediction.relative_energy_kcal_mol.toFixed(2) + " kcal/mol"
                                  : "STRICT: inference disabled; scaffold only",
      "Rigid scan barrier " + v.rigid_barrier_kcal_mol.toFixed(2) + " kcal/mol | not a free-energy barrier",
      response ? "Particle ML: molecular photo σ " + response.sigma_barn[0].toFixed(2) + " barn" :
        "Held-out energy RMSE " + v.energy_holdout_rmse_kcal_mol.toExponential(1) + " kcal/mol",
      "PubChem CID " + v.pubchem.cid + " | bond MAE " + v.pubchem.bond_length_mae_angstrom.toFixed(3) + " Å",
      response ? particleDomain : prediction ? "Measured domain: " + (prediction.__coverage.inDomain ? "in range" : "OUTSIDE") +
        " | joint gap: " + prediction.__coverage.jointStarved +
        " | empty bins: " + prediction.__coverage.starvedInputs.length : "No inferred charge bubbles"],
    samples: {angle: sample.angle_deg, energy: prediction ? prediction.relative_energy_kcal_mol : undefined,
      reference_energy: sample.reference_energy_kcal_mol, photon_energy: responseEnergy(index),
      photo: response ? response.sigma_barn[0] : undefined, photo_truth: referenceSigma ? referenceSigma[0] : undefined,
      compton: response ? response.sigma_barn[1] : undefined, compton_truth: referenceSigma ? referenceSigma[1] : undefined,
      rayleigh: response ? response.sigma_barn[2] : undefined, rayleigh_truth: referenceSigma ? referenceSigma[2] : undefined},
    charts: particleScan ? [{id: "particle", title: "Particle → atom → molecule ML", x: "photon_energy",
      x_label: "photon energy (eV)", y_label: "molecular cross section (barn)", log_x: true, log_y: true,
      note: "Solid: learned | dashed: held-out Geant4",
      series: [{key: "photo", label: "photoelectric", color: "#b58aff"},
        {key: "photo_truth", label: "Geant4 photo", color: "#b58aff", dashed: true},
        {key: "compton", label: "Compton", color: "#59cfff"},
        {key: "compton_truth", label: "Geant4 Compton", color: "#59cfff", dashed: true},
        {key: "rayleigh", label: "Rayleigh", color: "#ffc766"},
        {key: "rayleigh_truth", label: "Geant4 Rayleigh", color: "#ffc766", dashed: true}]}] :
      [{id: "torsion", title: "Rigid torsional capacity", x: "angle", x_label: "torsion (degrees)",
      x_range: [0, 360], y_label: "relative energy (kcal/mol)",
      note: "Held-out angles • no relaxation or thermal populations",
      series: [{key: "energy", label: "C++ learned response", color: "#59cfff"},
               {key: "reference_energy", label: "independent RHF reference", color: "#ffc766", dashed: true}]}]
  });
  if (particleEnabled) payload.stream = particleScan ? "particle_response" : "torsion";
  ctx.emit("material_frame", TRECH_VIEWS["molecular_series"]["frame0"](payload));
}

function responseEnergy(index) {
  return index < spec.scan.length ? 3000 : particleModule.data.heldout[molecule].energies_ev[index - spec.scan.length];
}

globalThis.TRECH_HOOKS = {
  onEventEnd(ctx) {
    const index = ctx.event.id;
    const total = spec.scan.length * (particleEnabled ? 2 : 1);
    if (index >= total) return;
    const particleScan = index >= spec.scan.length;
    const scanIndex = index % spec.scan.length;
    const sample = particleScan ? spec.scan.reduce((a, b) => a.reference_energy_kcal_mol < b.reference_energy_kcal_mol ? a : b) : spec.scan[index];
    const inputs = liveInputs(ctx, sample.angle_deg);
    const prediction = ctx.predict("electronic_response", inputs);
    const response = particleEnabled ? particleModule.infer(ctx, spec, responseEnergy(index)) : null;
    if (mode === "predictive" && !prediction) throw new Error("Electronic model unavailable; refusing fabricated bubbles");
    const charges = prediction ? spec.elements.map((_, i) => prediction["charge_" + i + "_e"]) : null;
    if (charges && (charges.some(q => !Number.isFinite(q)) || Math.abs(charges.reduce((s, q) => s + q, 0)) > 1e-7))
      throw new Error("Learned charge budget is invalid");
    const source = particleEnabled ? particleModule.data.heldout[molecule] : null;
    const referenceIndex = particleScan ? scanIndex : source ? source.energies_ev.indexOf(3000) : -1;
    const referenceSigma = source ? source.sigma_barn[referenceIndex] : null;
    ctx.emit("molecular_prediction", {molecule, group: spec.group, angle_deg: sample.angle_deg,
      inputs, charges_e: charges, relative_energy_kcal_mol: prediction ? prediction.relative_energy_kcal_mol : null,
      reference_energy_kcal_mol: sample.reference_energy_kcal_mol,
      reference_charges_e: sample.reference_charges_e, coverage: prediction ? prediction.__coverage : null,
      accuracy: prediction ? prediction.__accuracy : null, geant4_edep_mev: ctx.event.edepMeV,
      particle_response: response, particle_reference_sigma_barn: referenceSigma,
      queried_photon_energy_ev: particleEnabled ? responseEnergy(index) : null,
      stream: particleEnabled ? (particleScan ? "particle_response" : "torsion") : "",
      physics_scope: spec.notes, expected_model_sha256: spec.model_sha256,
      expected_particle_model_sha256: particleEnabled ? particleModule.data.model_sha256 : null});
    emitView(ctx, sample, prediction, index, response, particleScan, referenceSigma);
    if (index === total - 1) ctx.emit("molecular_summary", {
      molecule, mode, scan_samples: total, particle_enabled: particleEnabled,
      validation: spec.validation, physics_scope: spec.notes});
  }
};
