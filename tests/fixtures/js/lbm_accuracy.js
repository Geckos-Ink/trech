// Lattice Boltzmann verification fixture; never particle training data or a physical validation.
// Exact/closed-form anchors are independent of the solver; the heated cavity is a published
// numerical benchmark (de Vahl Davis 1983), labelled as such.
TRECH_INCLUDE("../../../js/trech_lbm_reference.js");
const scope = "Lattice Boltzmann development-track verification; exact and benchmark anchors only, no Geant4-trained flow response";
globalThis.TRECH_CONFIG = {
  run: {nEvents: 1, seed: 424242, threads: 1}, determinism: {mode: "strict"},
  detector: {worldSizeMm: 100, worldMaterial: "G4_AIR"},
  beam: {particle: "gamma", energyMeV: .1, positionMm: [0, 0, -40], direction: [0, 0, 1]},
  hooks: {enable: true, maxEmitsPerCallback: 1, maxEmitPayloadBytes: 1048576,
    inputs: {reference_kind: "independent_exact_solution", scope,
      anchors: ["taylor_green_d2q9", "kolmogorov_d3q19", "poiseuille_d3q19", "couette_d3q19",
        "advection_diffusion_d3q7", "conduction_d3q7", "closed_box_conservation", "heated_cavity_d2q9_d2q5", "native_parity", "staggered_mode_guard", "applicability_evidence"],
      order_min: 1.8, order_max: 2.3, exact_tolerance: 1e-9}}
};

function verifyLbm() {
  const LBM = TRECH_LBM_REFERENCE;
  function check(ok, message) { if (!ok) throw new Error(message); }
  const orders = e => e.slice(1).map((v, i) => Math.log(e[i] / v) / Math.log(2));
  const inOrder = p => p.every(v => v > 1.8 && v < 2.3);
  const anchors = [];

  // 1. Taylor-Green vortex (D2Q9, periodic), diffusive scaling: second-order in space.
  function taylorGreen(N) {
    const tau = .8, steps = Math.round(100 * (N / 16) ** 2), u0 = .04 * 16 / N, k = 2 * Math.PI / N;
    const domain = LBM.createDomain({shape: [N, N, 1], periodic: [true, true, true]});
    const flow = LBM.createFlow({domain, lattice: "D2Q9", tau, initial: (x, y) => ({
      rho: 1 - .75 * u0 * u0 * (Math.cos(2 * k * x) + Math.cos(2 * k * y)),
      u: [-u0 * Math.cos(k * x) * Math.sin(k * y), u0 * Math.sin(k * x) * Math.cos(k * y), 0]})});
    for (let s = 0; s < steps; s++) flow.step(null);
    const m = flow.moments(), decay = Math.exp(-2 * flow.viscosity * k * k * steps);
    const actual = [], expected = [];
    for (let i = 0; i < domain.count; i++) {
      actual.push(m.ux[i] / u0);
      expected.push(-Math.cos(k * domain.x[i]) * Math.sin(k * domain.y[i]) * decay);
    }
    return LBM.errorNorms(actual, expected).l2;
  }
  const tg = [8, 16, 32].map(taylorGreen);
  check(inOrder(orders(tg)), "Taylor-Green order outside second-order band: " + orders(tg));
  anchors.push({kind: "taylor_green_d2q9", grids: [8, 16, 32], l2: tg, orders: orders(tg)});

  // 2. Kolmogorov flow (D3Q19, Guo forcing): steady u = F/(nu k^2) sin(k y).
  function kolmogorov(N) {
    const k = 2 * Math.PI / N, F0 = 1e-6;
    const domain = LBM.createDomain({shape: [1, N, 1], periodic: [true, true, true]});
    const flow = LBM.createFlow({domain, lattice: "D3Q19", tau: .8});
    const fx = new Float64Array(N), zero = new Float64Array(N);
    for (let i = 0; i < N; i++) fx[i] = F0 * Math.sin(k * domain.y[i]);
    for (let s = 0; s < Math.round(14 / (flow.viscosity * k * k)); s++) flow.step({x: fx, y: zero, z: zero});
    const v = flow.velocity(), amp = F0 / (flow.viscosity * k * k);
    let err = 0;
    for (let i = 0; i < N; i++) err = Math.max(err, Math.abs(v.ux[i] - amp * Math.sin(k * domain.y[i])));
    return err / amp;
  }
  const kf = [16, 32].map(kolmogorov);
  check(inOrder(orders(kf)), "Kolmogorov forcing order outside second-order band: " + orders(kf));
  anchors.push({kind: "kolmogorov_d3q19", grids: [16, 32], linf_relative: kf, orders: orders(kf)});

  // 3. Body-force Poiseuille between half-way bounce-back walls: TRT Lambda=3/16 is exact
  //    for every relaxation time (viscosity-independent wall location).
  function poiseuille(tau) {
    const H = 10, Fx = 1e-6;
    const domain = LBM.createDomain({shape: [1, 1, H + 2], periodic: [true, true, false],
      solid: (x, y, z) => z === 0 || z === H + 1});
    const flow = LBM.createFlow({domain, lattice: "D3Q19", tau});
    const nu = flow.viscosity;
    for (let s = 0; s < Math.round(4 * H * H / nu); s++) flow.step([Fx, 0, 0]);
    const v = flow.velocity();
    let err = 0, peak = 0;
    for (let i = 0; i < domain.count; i++) {
      const z = domain.z[i], exact = Fx / (2 * nu) * (z - .5) * (H + .5 - z);
      err = Math.max(err, Math.abs(v.ux[i] - exact)); peak = Math.max(peak, exact);
    }
    return err / peak;
  }
  const pz = [.6, .9, 1.7].map(poiseuille);
  check(pz.every(e => e < 1e-9), "Poiseuille not exact under TRT 3/16: " + pz);
  anchors.push({kind: "poiseuille_d3q19", taus: [.6, .9, 1.7], linf_relative: pz});

  // 4. Moving-wall Couette: exact linear profile.
  function couette(tau) {
    const H = 8, U = .01;
    const domain = LBM.createDomain({shape: [1, 1, H + 2], periodic: [true, true, false],
      solid: (x, y, z) => z === 0 || z === H + 1});
    const flow = LBM.createFlow({domain, lattice: "D3Q19", tau,
      wallVelocity: (x, y, z) => z === H + 1 ? [U, 0, 0] : [0, 0, 0]});
    for (let s = 0; s < Math.round(4 * H * H / flow.viscosity); s++) flow.step(null);
    const m = flow.moments();
    let err = 0;
    for (let i = 0; i < domain.count; i++) err = Math.max(err, Math.abs(m.ux[i] - U * (domain.z[i] - .5) / H));
    return err / U;
  }
  const cu = [.8, 1.4].map(couette);
  check(cu.every(e => e < 1e-9), "Couette not exact: " + cu);
  anchors.push({kind: "couette_d3q19", taus: [.8, 1.4], linf_relative: cu});

  // 5. Advected, diffusing sine (D3Q7, periodic), diffusive scaling: second order.
  function advectionDiffusion(N) {
    const D = .25 * .1, k = 2 * Math.PI / N, U = .05 * 16 / N, steps = Math.round(60 * (N / 16) ** 2);
    const domain = LBM.createDomain({shape: [N, 1, 1], periodic: [true, true, true]});
    const scalar = LBM.createScalar({domain, lattice: "D3Q7", diffusivity: D, initial: x => 1 + .5 * Math.sin(k * x)});
    const velocity = {ux: new Float64Array(N).fill(U), uy: new Float64Array(N), uz: new Float64Array(N)};
    for (let s = 0; s < steps; s++) scalar.step(velocity, null);
    const v = scalar.values(), expected = [];
    for (let i = 0; i < N; i++) expected.push(1 + .5 * Math.sin(k * (i - U * steps)) * Math.exp(-D * k * k * steps));
    return LBM.errorNorms(Array.from(v), expected).l2;
  }
  const ad = [16, 32, 64].map(advectionDiffusion);
  check(inOrder(orders(ad)), "Advection-diffusion order outside second-order band: " + orders(ad));
  anchors.push({kind: "advection_diffusion_d3q7", grids: [16, 32, 64], l2: ad, orders: orders(ad)});

  // 6. Steady conduction between anti-bounce-back Dirichlet walls: exact linear profile.
  const H = 8;
  const condDomain = LBM.createDomain({shape: [1, 1, H], periodic: [true, true, false]});
  const cond = LBM.createScalar({domain: condDomain, lattice: "D3Q7", diffusivity: .1,
    walls: (x, y, z) => ({value: z < 0 ? 1 : 0})});
  for (let s = 0; s < Math.round(4 * H * H / .1); s++) cond.step(null, null);
  const cv = cond.values();
  let condErr = 0;
  for (let i = 0; i < H; i++) condErr = Math.max(condErr, Math.abs(cv[i] - (1 - (condDomain.z[i] + .5) / H)));
  check(condErr < 1e-9, "Dirichlet conduction not exact: " + condErr);
  anchors.push({kind: "conduction_d3q7", linf: condErr});

  // 7. Closed box: bounce-back conserves mass, zero-flux walls conserve the scalar exactly,
  //    while buoyancy drives a real flow.
  const box = LBM.createDomain({shape: [6, 6, 6]});
  const thermal = LBM.createThermalFlow({domain: box, tau: .9, diffusivity: .05,
    initialTemperature: (x, y, z) => Math.sin(1 + x) * Math.cos(.5 * y + z),
    buoyancy: {axis: 2, coefficient: 1e-4, reference: 0}});
  const mass0 = thermal.flow.totals().mass, heat0 = thermal.scalar.total();
  for (let s = 0; s < 200; s++) thermal.step();
  const massDrift = Math.abs(thermal.flow.totals().mass - mass0) / mass0;
  const heatDrift = Math.abs(thermal.scalar.total() - heat0) / Math.max(1, Math.abs(heat0));
  const moved = thermal.status().max_mach;
  check(massDrift < 1e-12 && heatDrift < 1e-12 && moved > 0, "Closed-box conservation lost");
  anchors.push({kind: "closed_box_conservation", mass_drift: massDrift, scalar_drift: heatDrift, max_mach: moved});

  // 8. Differentially heated square cavity, Ra=1e3, Pr=0.71 (de Vahl Davis 1983: Nu=1.118).
  const N = 16, Ra = 1e3, Pr = .71, U = .05, gb = U * U / N;
  const nu = Math.sqrt(Pr / Ra) * U * N, kappa = nu / Pr;
  const cav = LBM.createDomain({shape: [N, N, 1]});
  const heated = LBM.createThermalFlow({domain: cav, flowLattice: "D2Q9", scalarLattice: "D2Q5",
    tau: .5 + 3 * nu, diffusivity: kappa, walls: x => x < 0 ? {value: .5} : x >= N ? {value: -.5} : null,
    buoyancy: {axis: 1, coefficient: gb, reference: 0}});
  let nusselt = 0, previous = 0, steps = 0;
  for (steps = 1; steps <= 20000; steps++) {
    heated.step();
    if (steps % 500) continue;
    const v = heated.flow.velocity(), T = heated.scalar.values();
    let flux = 0;
    for (let i = 0; i < cav.count; i++) flux += v.ux[i] * T[i];
    nusselt = 1 + flux / cav.count * N / kappa;
    if (Math.abs(nusselt - previous) < 1e-5 * nusselt) break;
    previous = nusselt;
  }
  const benchmark = 1.118;
  check(Math.abs(nusselt / benchmark - 1) < .01, "Heated cavity Nusselt off benchmark: " + nusselt);
  anchors.push({kind: "heated_cavity_d2q9_d2q5", grid: N, rayleigh: Ra, prandtl: Pr, steps,
    nusselt, benchmark_nusselt: benchmark, benchmark_source: "de Vahl Davis 1983 (numerical benchmark)",
    relative_error: nusselt / benchmark - 1, max_mach: heated.status().max_mach});

  // 9. Native kernel parity: TRECH_LATTICE_ADVANCE must reproduce the JS reference bit for bit
  //    (walls, Dirichlet links, buoyancy coupling and a relaxation source all exercised).
  function heatedBox(native) {
    const domain = LBM.createDomain({shape: [5, 4, 6], periodic: [true, false, false],
      solid: (x, y, z) => x === 2 && y === 1 && z === 3});
    const F = domain.count, rate = new Float64Array(F), target = new Float64Array(F), constant = new Float64Array(F);
    for (let i = 0; i < F; i++) {
      if (domain.z[i] === 0) { rate[i] = .02; target[i] = 1; }
      constant[i] = domain.z[i] === 5 ? -1e-4 : 0;
    }
    const box = LBM.createThermalFlow({domain, tau: .7, diffusivity: .03, native,
      initialTemperature: (x, y, z) => .1 * Math.cos(x + 2 * y) * (z + 1) / 6,
      walls: (x, y, z) => y < 0 ? {value: .25} : null, uniformForce: [1e-6, 0, 0],
      relaxation: {rate, target, constant}, buoyancy: {axis: 2, coefficient: 2e-4, reference: "mean"}});
    if (native === false) for (let s = 0; s < 120; s++) box.step();
    else box.advance(120);
    return {box, native: box.native};
  }
  const nativeAvailable = typeof globalThis.TRECH_LATTICE_ADVANCE === "function";
  const jsBox = heatedBox(false).box;
  let parity = null;
  if (nativeAvailable) {
    const nativeBox = heatedBox(undefined);
    check(nativeBox.native, "Native lattice advance not selected");
    const same = (a, b) => a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
    parity = same(jsBox.flow.view.f, nativeBox.box.flow.view.f) &&
      same(jsBox.scalar.view.g, nativeBox.box.scalar.view.g) &&
      jsBox.status().max_mach === nativeBox.box.status().max_mach &&
      nativeBox.box.status().steps === 120;
    check(parity, "Native lattice advance diverged from the JavaScript reference");
  }
  anchors.push({kind: "native_parity", native_available: nativeAvailable, bit_identical: parity,
    steps: 120, max_mach: jsBox.status().max_mach});

  // 10. Staggered-mode guard. A weakly diffusive scalar (tau- = 0.5072) heated from below in a
  //     closed box: with the default scalar tau+ = 1 the period-2 lattice modes stay negligible
  //     and the flow stays bounded; the Lambda = 1/4 counterexample must be caught by the
  //     diagnostic (it pumps the flow's staggered momentum invariant without bound).
  function staggeredBox(magic) {
    const domain = LBM.createDomain({shape: [6, 6, 16]}), F = domain.count;
    const rate = new Float64Array(F), target = new Float64Array(F);
    for (let i = 0; i < F; i++) {
      if (domain.z[i] === 0) { rate[i] = 4e-4; target[i] = 1; }
      if (domain.z[i] === 15) rate[i] = 4e-4;
    }
    const box = LBM.createThermalFlow({domain, tau: .58, diffusivity: .0018, scalarMagic: magic,
      relaxation: {rate, target}, initialTemperature: x => 1e-4 * (x - 2.5),
      buoyancy: {axis: 2, coefficient: 2e-4, reference: "mean"}});
    const rms = [];
    for (let k = 0; k < 5; k++) {
      box.advance(3000);
      const v = box.flow.velocity();
      let e = 0;
      for (let i = 0; i < F; i++) e += v.ux[i] ** 2 + v.uy[i] ** 2 + v.uz[i] ** 2;
      rms.push(Math.sqrt(e / F));
    }
    return {rms, staggered_fraction: LBM.staggeredFraction(domain, box.flow.velocity())};
  }
  const guarded = staggeredBox(undefined), unguarded = staggeredBox(.25);
  check(guarded.staggered_fraction < .01 && guarded.rms[4] < guarded.rms[0],
    "Default scalar relaxation lets a staggered lattice mode grow");
  check(unguarded.staggered_fraction > .5 && LBM.assess({staggered_fraction: unguarded.staggered_fraction}).applicable === false,
    "Staggered-mode diagnostic missed the Lambda=1/4 counterexample");
  anchors.push({kind: "staggered_mode_guard", default_scalar: guarded, lambda_quarter: unguarded});

  // 11. On-the-fly applicability evidence (the learner itself needs predictive mode): a twin
  //     identical to the main lattice reports exactly zero error, a coarser twin of the heated
  //     box reports a finite one, and wall distances follow the lattice.
  function heatedTwin(n) {
    const domain = LBM.createDomain({shape: [n, n, 2 * n]}), F = domain.count;
    const rate = new Float64Array(F), target = new Float64Array(F);
    for (let i = 0; i < F; i++) if (domain.z[i] === 0) { rate[i] = .01; target[i] = 1; }
    const box = LBM.createThermalFlow({domain, tau: .8, diffusivity: .05, relaxation: {rate, target},
      initialTemperature: x => 1e-3 * (x / n - .5), buoyancy: {axis: 2, coefficient: 1e-3, reference: "mean"}});
    box.advance(400 * (n / 4) * (n / 4) / 4);
    return box;
  }
  const fine = heatedTwin(8), same = heatedTwin(8), coarse = heatedTwin(4);
  const opts = {scalarScale: 1, velocityScale: 1, twinVelocityScale: 1, velocityFloor: 1e-9};
  const self = LBM.twinDiscrepancy(fine, same, Object.assign({ratio: 1}, opts));
  const twin = LBM.twinDiscrepancy(fine, coarse, Object.assign({ratio: 2}, opts));
  const maxOf = a => a.reduce((m, v) => Math.max(m, v), 0);
  const descriptors = LBM.localDescriptors(fine, 1);
  check(maxOf(self.temperature) === 0 && maxOf(self.velocity) === 0, "Identical twin reported a nonzero error");
  check(maxOf(twin.temperature) > 0 && twin.valid.every(v => v === 1), "Coarse twin evidence missing");
  check(Math.min(...descriptors.wall_distance) === 1 && Math.max(...descriptors.wall_distance) === 4,
    "Wall distances do not follow the lattice");
  anchors.push({kind: "applicability_evidence", identical_twin_max_error: 0,
    coarse_twin_max_temperature_error: maxOf(twin.temperature), coarse_twin_max_velocity_error: maxOf(twin.velocity),
    max_velocity_curvature: maxOf(descriptors.velocity_curvature)});

  return {schema: "trech_lbm_verification_v1", scope, anchors,
    physical_accuracy_verified: false, particle_training_data: false,
    limitations: "Exact periodic/channel/conduction anchors and one published thermal benchmark; no free surface, turbulence, curved-wall accuracy, experimental uncertainty or particle-derived response"};
}
globalThis.TRECH_HOOKS = {onEventEnd(ctx) { ctx.emit("lbm_accuracy", verifyLbm()); }};
