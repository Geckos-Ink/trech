// Lattice Boltzmann comparison solver (development track). No learned or Geant4 flow response.
//
// A deterministic, physics-agnostic lattice-kinetic transport kernel used as a DUAL-RUN
// companion: a scenario keeps its normal-path evolution and also advances this lattice with
// the same geometry and the same (cascade-inferred) properties, then records a scored
// confrontation. Nothing computed here feeds back into a scenario's normal path while the
// track is in development (see AGENTS/engine/lattice/AGENTS.md for the stable contract).
//
// Flow:   D2Q9 / D3Q19, two-relaxation-time (TRT) collision, Guo body-force forcing,
//         link-wise half-way bounce-back walls (optionally moving), periodic axes.
// Scalar: D2Q5 / D3Q7 advection-diffusion, TRT, volumetric source, zero-flux (bounce-back)
//         or Dirichlet (anti-bounce-back) walls.
// All arithmetic is in lattice units (dx = dt = 1); `units` converts physical inputs.
(function() {
  if (globalThis.TRECH_LBM_REFERENCE) return;

  const LATTICES = {
    D2Q9: {d: 2, cs2: 1 / 3, c: [[0,0,0],[1,0,0],[0,1,0],[-1,0,0],[0,-1,0],
      [1,1,0],[-1,1,0],[-1,-1,0],[1,-1,0]],
      w: [4/9, 1/9, 1/9, 1/9, 1/9, 1/36, 1/36, 1/36, 1/36]},
    D3Q19: {d: 3, cs2: 1 / 3, c: [[0,0,0],
      [1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1],
      [1,1,0],[-1,-1,0],[1,-1,0],[-1,1,0],[1,0,1],[-1,0,-1],
      [1,0,-1],[-1,0,1],[0,1,1],[0,-1,-1],[0,1,-1],[0,-1,1]],
      w: [1/3, 1/18, 1/18, 1/18, 1/18, 1/18, 1/18,
        1/36, 1/36, 1/36, 1/36, 1/36, 1/36, 1/36, 1/36, 1/36, 1/36, 1/36, 1/36]},
    D2Q5: {d: 2, cs2: 1 / 3, c: [[0,0,0],[1,0,0],[0,1,0],[-1,0,0],[0,-1,0]],
      w: [1/3, 1/6, 1/6, 1/6, 1/6]},
    D3Q7: {d: 3, cs2: 1 / 4, c: [[0,0,0],[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]],
      w: [1/4, 1/8, 1/8, 1/8, 1/8, 1/8, 1/8]}
  };
  for (const name of Object.keys(LATTICES)) {
    const L = LATTICES[name];
    L.name = name;
    L.q = L.c.length;
    L.opp = L.c.map(a => L.c.findIndex(b => b[0] === -a[0] && b[1] === -a[1] && b[2] === -a[2]));
  }

  function lattice(name) {
    const L = LATTICES[name];
    if (!L) throw new Error("Unknown lattice " + name);
    return L;
  }

  function finitePositive(v) { return Number.isFinite(v) && v > 0; }

  // Fluid-cell compaction. `solid(x,y,z)` receives integer cell coordinates.
  function createDomain(o) {
    const shape = o.shape;
    if (!Array.isArray(shape) || shape.length !== 3 ||
        !shape.every(n => Number.isInteger(n) && n >= 1) || shape[0] * shape[1] * shape[2] > 400000)
      throw new Error("LBM domain shape must be three positive integers (<= 400000 cells)");
    const periodic = o.periodic || [false, false, false];
    const [nx, ny, nz] = shape, cells = nx * ny * nz;
    const index = new Int32Array(cells).fill(-1);
    const xs = [], ys = [], zs = [];
    for (let z = 0; z < nz; z++) for (let y = 0; y < ny; y++) for (let x = 0; x < nx; x++) {
      if (o.solid && o.solid(x, y, z)) continue;
      index[x + nx * (y + ny * z)] = xs.length;
      xs.push(x); ys.push(y); zs.push(z);
    }
    if (!xs.length) throw new Error("LBM domain has no fluid cells");
    return {shape: shape.slice(), periodic: periodic.slice(), index, count: xs.length,
      x: Int32Array.from(xs), y: Int32Array.from(ys), z: Int32Array.from(zs),
      // Fluid index of a lattice coordinate, honouring periodic wrap; -1 for wall/outside.
      at(x, y, z) {
        const p = [x, y, z];
        for (let a = 0; a < 3; a++) {
          if (p[a] < 0 || p[a] >= shape[a]) {
            if (!periodic[a]) return -1;
            p[a] = ((p[a] % shape[a]) + shape[a]) % shape[a];
          }
        }
        return index[p[0] + nx * (p[1] + ny * p[2])];
      }};
  }

  // Pull table: post-collision source slot for each (q, cell). A missing upstream
  // neighbour is a wall: the half-way bounce-back source is the opposite population of
  // the same cell. `wall[q*F+i]` marks those links (+1) so callers can add wall terms.
  function pullTable(domain, L) {
    const F = domain.count, Q = L.q;
    const src = new Int32Array(Q * F), wall = new Uint8Array(Q * F);
    for (let q = 0; q < Q; q++) {
      const c = L.c[q];
      for (let i = 0; i < F; i++) {
        const j = domain.at(domain.x[i] - c[0], domain.y[i] - c[1], domain.z[i] - c[2]);
        if (j >= 0) src[q * F + i] = q * F + j;
        else { src[q * F + i] = L.opp[q] * F + i; wall[q * F + i] = 1; }
      }
    }
    return {src, wall};
  }

  function checkDimension(domain, L) {
    if (L.d === 2 && domain.shape[2] !== 1) throw new Error(L.name + " needs nz = 1");
  }

  // Flow lattice. tau sets kinematic viscosity nu = cs2 (tau - 1/2); magic is the TRT
  // parameter Lambda = (tau+ - 1/2)(tau- - 1/2). Lambda = 3/16 places half-way walls exactly
  // for Poiseuille flow independent of viscosity; Lambda = (tau - 1/2)^2 recovers BGK.
  function createFlow(o) {
    const domain = o.domain, L = lattice(o.lattice || "D3Q19");
    if (L.name !== "D2Q9" && L.name !== "D3Q19") throw new Error("Flow lattice must be D2Q9 or D3Q19");
    checkDimension(domain, L);
    const tau = o.tau;
    if (!Number.isFinite(tau) || tau <= 0.5 || tau > 5) throw new Error("Flow tau must be in (0.5, 5]");
    const magic = o.magic === undefined ? 3 / 16 : o.magic;
    if (!finitePositive(magic)) throw new Error("TRT magic parameter must be positive");
    const tauMinus = 0.5 + magic / (tau - 0.5);
    const wp = 1 / tau, wm = 1 / tauMinus;
    const F = domain.count, Q = L.q, cs2 = L.cs2;
    const {src, wall} = pullTable(domain, L);
    let f = new Float64Array(Q * F), post = new Float64Array(Q * F);
    const rho = new Float64Array(F), ux = new Float64Array(F), uy = new Float64Array(F),
      uz = new Float64Array(F);
    const cx = L.c.map(c => c[0]), cy = L.c.map(c => c[1]), cz = L.c.map(c => c[2]);
    const w = L.w, opp = L.opp;
    // Moving-wall momentum per wall link: 2 w rho0 (c . u_wall) / cs2 (Ladd).
    const wallTerm = o.wallVelocity ? new Float64Array(Q * F) : null;
    if (wallTerm) {
      for (let q = 0; q < Q; q++) for (let i = 0; i < F; i++) {
        if (!wall[q * F + i]) continue;
        // Upstream wall cell lies at x - c_q; the link brings population q into i.
        const uw = o.wallVelocity(domain.x[i] - cx[q], domain.y[i] - cy[q], domain.z[i] - cz[q]);
        if (uw) wallTerm[q * F + i] = 2 * w[q] * (cx[q] * uw[0] + cy[q] * uw[1] + cz[q] * uw[2]) / cs2;
      }
    }
    function feq(q, r, vx, vy, vz) {
      const cu = (cx[q] * vx + cy[q] * vy + cz[q] * vz) / cs2;
      return w[q] * r * (1 + cu + 0.5 * cu * cu - 0.5 * (vx * vx + vy * vy + vz * vz) / cs2);
    }
    for (let i = 0; i < F; i++) {
      const s = o.initial ? o.initial(domain.x[i], domain.y[i], domain.z[i]) : null;
      const r = s && s.rho !== undefined ? s.rho : 1;
      const u = s && s.u ? s.u : [0, 0, 0];
      if (!finitePositive(r) || !u.every(Number.isFinite)) throw new Error("Invalid LBM initial state");
      rho[i] = r; ux[i] = u[0]; uy[i] = u[1]; uz[i] = u[2] || 0;
      for (let q = 0; q < Q; q++) f[q * F + i] = feq(q, r, ux[i], uy[i], uz[i]);
    }
    let steps = 0, maxMach = 0;
    const eq = new Float64Array(Q), fs = new Float64Array(Q);
    // force: null, a uniform [fx,fy,fz], or {x,y,z} Float64Arrays over fluid cells.
    function step(force) {
      const uniform = Array.isArray(force), field = force && !uniform;
      let peak = 0;
      for (let i = 0; i < F; i++) {
        let r = 0, mx = 0, my = 0, mz = 0;
        for (let q = 0; q < Q; q++) {
          const v = f[q * F + i];
          r += v; mx += cx[q] * v; my += cy[q] * v; mz += cz[q] * v;
        }
        const gx = uniform ? force[0] : field ? force.x[i] : 0;
        const gy = uniform ? force[1] : field ? force.y[i] : 0;
        const gz = uniform ? (force[2] || 0) : field ? (force.z ? force.z[i] : 0) : 0;
        if (!(r > 0) || !Number.isFinite(mx + my + mz))
          throw new Error("Nonphysical LBM state; refine lattice/timestep instead of clipping");
        const vx = (mx + 0.5 * gx) / r, vy = (my + 0.5 * gy) / r, vz = (mz + 0.5 * gz) / r;
        rho[i] = r; ux[i] = vx; uy[i] = vy; uz[i] = vz;
        const speed2 = vx * vx + vy * vy + vz * vz;
        if (speed2 > peak) peak = speed2;
        for (let q = 0; q < Q; q++) {
          eq[q] = feq(q, r, vx, vy, vz);
          // Guo source: w [ (c - u)/cs2 + (c.u) c / cs2^2 ] . F
          const cu = cx[q] * vx + cy[q] * vy + cz[q] * vz;
          fs[q] = w[q] * (((cx[q] - vx) * gx + (cy[q] - vy) * gy + (cz[q] - vz) * gz) / cs2 +
            cu * (cx[q] * gx + cy[q] * gy + cz[q] * gz) / (cs2 * cs2));
        }
        for (let q = 0; q < Q; q++) {
          const p = opp[q], a = q * F + i;
          const fp = 0.5 * (f[a] + f[p * F + i]), fm = 0.5 * (f[a] - f[p * F + i]);
          const ep = 0.5 * (eq[q] + eq[p]), em = 0.5 * (eq[q] - eq[p]);
          const sp = 0.5 * (fs[q] + fs[p]), sm = 0.5 * (fs[q] - fs[p]);
          post[a] = f[a] - wp * (fp - ep) - wm * (fm - em) + (1 - 0.5 * wp) * sp + (1 - 0.5 * wm) * sm;
        }
      }
      for (let k = 0; k < Q * F; k++) {
        f[k] = post[src[k]];
        if (wallTerm && wall[k]) f[k] += wallTerm[k] * rho[k % F];
      }
      steps++;
      const mach = Math.sqrt(peak / cs2);
      if (mach > maxMach) maxMach = mach;
      return mach;
    }
    function moments() {
      // Macroscopic fields of the current (post-streaming) populations; no force half-step.
      for (let i = 0; i < F; i++) {
        let r = 0, mx = 0, my = 0, mz = 0;
        for (let q = 0; q < Q; q++) {
          const v = f[q * F + i];
          r += v; mx += cx[q] * v; my += cy[q] * v; mz += cz[q] * v;
        }
        rho[i] = r; ux[i] = mx / r; uy[i] = my / r; uz[i] = mz / r;
      }
      return {rho, ux, uy, uz};
    }
    function totals() {
      let mass = 0, px = 0, py = 0, pz = 0;
      for (let q = 0; q < Q; q++) for (let i = 0; i < F; i++) {
        const v = f[q * F + i];
        mass += v; px += cx[q] * v; py += cy[q] * v; pz += cz[q] * v;
      }
      return {mass, momentum: [px, py, pz]};
    }
    // Arrays and rates for the native advance (TRECH_LATTICE_ADVANCE); same memory, same order.
    const view = {cx: Float64Array.from(cx), cy: Float64Array.from(cy), cz: Float64Array.from(cz),
      w: Float64Array.from(w), opp: Int32Array.from(opp), cs2, omega_plus: wp, omega_minus: wm,
      f, post, src, wall, wall_term: wallTerm, rho, ux, uy, uz};
    function record(n, mach) { steps += n; if (mach > maxMach) maxMach = mach; }
    return {lattice: L.name, domain, tau, tauMinus, magic, viscosity: cs2 * (tau - 0.5),
      step, moments, totals, view, record,
      // Velocity of the last collision (includes the half-force correction).
      velocity: () => ({rho, ux, uy, uz}),
      status: () => ({steps, max_mach: maxMach})};
  }

  // Scalar advection-diffusion lattice. diffusivity D = cs2 (tau- - 1/2) in lattice units.
  // The symmetric (even) modes relax at tau+ = 1 by default (magic = (tau- - 1/2)/2). The
  // tempting Lambda = 1/4 makes tau+ = 1/4 / (tau- - 1/2) huge when D is small, leaving the
  // scalar's period-2 staggered modes undamped; through buoyancy they pump the flow lattice's
  // staggered momentum invariant (which no viscosity damps) into a spurious, unbounded flow.
  // walls(xWall, yWall, zWall, xFluid, yFluid, zFluid) may return {value} for a Dirichlet
  // wall; otherwise the link is zero-flux. source: null or Float64Array of per-step deltas.
  function createScalar(o) {
    const domain = o.domain, L = lattice(o.lattice || "D3Q7");
    if (L.name !== "D2Q5" && L.name !== "D3Q7") throw new Error("Scalar lattice must be D2Q5 or D3Q7");
    checkDimension(domain, L);
    const D = o.diffusivity, cs2 = L.cs2;
    if (!finitePositive(D)) throw new Error("Scalar diffusivity must be positive");
    const tauMinus = 0.5 + D / cs2;
    const magic = o.magic === undefined ? 0.5 * (tauMinus - 0.5) : o.magic;
    if (!finitePositive(magic)) throw new Error("Scalar TRT magic parameter must be positive");
    const tauPlus = 0.5 + magic / (tauMinus - 0.5);
    const wp = 1 / tauPlus, wm = 1 / tauMinus;
    const F = domain.count, Q = L.q;
    const {src, wall} = pullTable(domain, L);
    // Dirichlet links: anti-bounce-back g_q = -g*_opp + 2 w_q T_wall.
    const dirichlet = new Float64Array(Q * F), anti = new Uint8Array(Q * F);
    const cx = L.c.map(c => c[0]), cy = L.c.map(c => c[1]), cz = L.c.map(c => c[2]);
    if (o.walls) {
      for (let q = 0; q < Q; q++) for (let i = 0; i < F; i++) {
        if (!wall[q * F + i]) continue;
        const b = o.walls(domain.x[i] - cx[q], domain.y[i] - cy[q], domain.z[i] - cz[q],
          domain.x[i], domain.y[i], domain.z[i]);
        if (b && Number.isFinite(b.value)) { anti[q * F + i] = 1; dirichlet[q * F + i] = 2 * L.w[q] * b.value; }
      }
    }
    const g = new Float64Array(Q * F), post = new Float64Array(Q * F), value = new Float64Array(F);
    const w = L.w, opp = L.opp;
    for (let i = 0; i < F; i++) {
      const v = o.initial ? o.initial(domain.x[i], domain.y[i], domain.z[i]) : 0;
      if (!Number.isFinite(v)) throw new Error("Invalid scalar initial value");
      value[i] = v;
      for (let q = 0; q < Q; q++) g[q * F + i] = w[q] * v;
    }
    let steps = 0;
    const eq = new Float64Array(Q);
    // velocity: null or {ux,uy,uz} over fluid cells (lattice units).
    function step(velocity, source) {
      for (let i = 0; i < F; i++) {
        let s = 0;
        for (let q = 0; q < Q; q++) s += g[q * F + i];
        value[i] = s;
        const vx = velocity ? velocity.ux[i] : 0, vy = velocity ? velocity.uy[i] : 0,
          vz = velocity ? velocity.uz[i] : 0;
        const add = source ? source[i] : 0;
        for (let q = 0; q < Q; q++)
          eq[q] = w[q] * s * (1 + (cx[q] * vx + cy[q] * vy + cz[q] * vz) / cs2);
        for (let q = 0; q < Q; q++) {
          const p = opp[q], a = q * F + i;
          const gp = 0.5 * (g[a] + g[p * F + i]), gm = 0.5 * (g[a] - g[p * F + i]);
          const ep = 0.5 * (eq[q] + eq[p]), em = 0.5 * (eq[q] - eq[p]);
          post[a] = g[a] - wp * (gp - ep) - wm * (gm - em) + w[q] * add;
        }
      }
      for (let k = 0; k < Q * F; k++) g[k] = anti[k] ? -post[src[k]] + dirichlet[k] : post[src[k]];
      steps++;
    }
    function values() {
      for (let i = 0; i < F; i++) {
        let s = 0;
        for (let q = 0; q < Q; q++) s += g[q * F + i];
        value[i] = s;
      }
      return value;
    }
    function total() { let s = 0; for (let k = 0; k < Q * F; k++) s += g[k]; return s; }
    const view = {cx: Float64Array.from(cx), cy: Float64Array.from(cy), cz: Float64Array.from(cz),
      w: Float64Array.from(w), opp: Int32Array.from(opp), cs2, omega_plus: wp, omega_minus: wm,
      g, post, src, anti, dirichlet, value};
    return {lattice: L.name, domain, diffusivity: D, tauMinus, tauPlus, magic, step, values, total,
      view, record: n => { steps += n; }, status: () => ({steps})};
  }

  // Boussinesq thermal flow: a flow lattice and a scalar (temperature) lattice on one domain.
  // Body force per cell = buoyancy.coefficient * (T - buoyancy.reference) along buoyancy.axis
  // (lattice units, coefficient = g beta dt^2/dx per kelvin), plus a uniform force.
  // reference "mean" uses the instantaneous fluid-mean temperature of every step, so a closed
  // vessel that warms uniformly carries no net body force (and no acoustic pulse).
  // relaxation (optional) declares the per-step temperature source of cell i as
  //   rate[i] * (target[i] - T[i]) + constant[i]
  // with caller-owned Float64Arrays that may be updated between advances.
  // advance(n) runs the native kernel (TRECH_LATTICE_ADVANCE) when the host provides it and
  // `native` is not false; it is bit-identical to n calls of step().
  function createThermalFlow(o) {
    const domain = o.domain;
    const flow = createFlow({domain, lattice: o.flowLattice || "D3Q19", tau: o.tau, magic: o.magic,
      initial: o.initialFlow, wallVelocity: o.wallVelocity});
    const scalar = createScalar({domain, lattice: o.scalarLattice || "D3Q7", diffusivity: o.diffusivity,
      walls: o.walls, initial: o.initialTemperature, magic: o.scalarMagic});
    const b = o.buoyancy || {axis: 2, coefficient: 0, reference: 0};
    const meanReference = b.reference === "mean";
    if (![0, 1, 2].includes(b.axis) || !Number.isFinite(b.coefficient) ||
        (!meanReference && !Number.isFinite(b.reference)))
      throw new Error("Invalid Boussinesq buoyancy declaration");
    let reference = meanReference ? 0 : b.reference;
    const F = domain.count;
    const relax = o.relaxation || null;
    if (relax) {
      for (const key of ["rate", "target", "constant"])
        if (relax[key] && !(relax[key] instanceof Float64Array && relax[key].length === F))
          throw new Error("Thermal relaxation " + key + " must be a Float64Array over fluid cells");
      if (!!relax.rate !== !!relax.target) throw new Error("Thermal relaxation rate needs a target");
    }
    const force = {x: new Float64Array(F), y: new Float64Array(F), z: new Float64Array(F)};
    const axisField = [force.x, force.y, force.z][b.axis];
    const base = (o.uniformForce || [0, 0, 0]).slice();
    if (base.length !== 3 || !base.every(Number.isFinite)) throw new Error("Invalid uniform force");
    const source = relax && (relax.rate || relax.constant) ? new Float64Array(F) : null;
    function step() {
      const T = scalar.values();
      if (meanReference) { let sum = 0; for (let i = 0; i < F; i++) sum += T[i]; reference = sum / F; }
      force.x.fill(base[0]); force.y.fill(base[1]); force.z.fill(base[2]);
      for (let i = 0; i < F; i++) axisField[i] += b.coefficient * (T[i] - reference);
      const mach = flow.step(force);
      if (source) {
        for (let i = 0; i < F; i++) {
          let add = 0;
          if (relax.rate) add = relax.rate[i] * (relax.target[i] - T[i]);
          if (relax.constant) add += relax.constant[i];
          source[i] = add;
        }
      }
      scalar.step(flow.velocity(), source);
      return mach;
    }
    const nativeAdvance = o.native === false ? null : globalThis.TRECH_LATTICE_ADVANCE;
    function advance(n) {
      if (!Number.isInteger(n) || n < 0) throw new Error("Lattice advance needs a non-negative step count");
      if (!nativeAdvance) { let peak = 0; for (let k = 0; k < n; k++) peak = Math.max(peak, step()); return peak; }
      const r = nativeAdvance({steps: n, flow: flow.view,
        scalar: Object.assign({}, scalar.view, relax ? {rate: relax.rate || null,
          target: relax.target || null, constant: relax.constant || null} : {}),
        coupling: {base, axis: b.axis, coefficient: b.coefficient, reference,
          mean_reference: meanReference}});
      flow.record(r.steps, r.max_mach); scalar.record(r.steps);
      if (r.nonphysical) throw new Error("Nonphysical LBM state; refine lattice/timestep instead of clipping");
      return r.max_mach;
    }
    return {flow, scalar, domain, step, advance, native: !!nativeAdvance,
      status: () => Object.assign(flow.status(), {scalar_steps: scalar.status().steps})};
  }

  // Physical -> lattice conversion with explicit stability/applicability flags. dt follows from
  // the chosen flow relaxation time; the scalar relaxation and Mach estimate follow from dt.
  function units(o) {
    const {dx_m, nu_m2_s, tau} = o;
    if (![dx_m, nu_m2_s].every(finitePositive) || !(tau > 0.5))
      throw new Error("LBM units need positive dx, viscosity and tau > 1/2");
    const nuLattice = (tau - 0.5) / 3;
    const dt_s = nuLattice * dx_m * dx_m / nu_m2_s;
    const out = {dx_m, dt_s, tau, nu_lattice: nuLattice, nu_m2_s,
      velocity_scale_m_s: dx_m / dt_s, acceleration_scale_m_s2: dx_m / (dt_s * dt_s)};
    if (o.kappa_m2_s !== undefined) {
      if (!finitePositive(o.kappa_m2_s)) throw new Error("LBM scalar diffusivity must be positive");
      out.kappa_m2_s = o.kappa_m2_s;
      out.kappa_lattice = o.kappa_m2_s * dt_s / (dx_m * dx_m);
      out.scalar_tau = 0.5 + out.kappa_lattice / (o.scalar_cs2 || 0.25);
    }
    if (o.velocity_estimate_m_s !== undefined)
      out.mach_estimate = o.velocity_estimate_m_s * dt_s / dx_m / Math.sqrt(1 / 3);
    return out;
  }

  // Applicability verdict for a run's own lattice parameters and observed Mach number.
  // The thresholds are the development track's declared stability envelope.
  const ENVELOPE = {mach_good: 0.1, mach_max: 0.3, tau_min: 0.505, scalar_tau_min: 0.5005,
    min_cells_across: 6, staggered_max: 0.05};
  function assess(o) {
    const reasons = [];
    if (o.tau !== undefined && o.tau < ENVELOPE.tau_min) reasons.push("flow tau below " + ENVELOPE.tau_min);
    if (o.scalar_tau !== undefined && o.scalar_tau < ENVELOPE.scalar_tau_min)
      reasons.push("scalar tau below " + ENVELOPE.scalar_tau_min);
    if (o.mach !== undefined && o.mach > ENVELOPE.mach_max)
      reasons.push("Mach " + o.mach.toFixed(3) + " exceeds weakly-compressible limit " + ENVELOPE.mach_max);
    if (o.cells_across !== undefined && o.cells_across < ENVELOPE.min_cells_across)
      reasons.push("only " + o.cells_across + " cells across the smallest feature");
    // Maximum principle: with sources that only relax toward values inside the bounds, an
    // advection-diffusion field leaving them signals a non-monotone (under-resolved) scalar.
    if (o.scalar_range && o.scalar_bounds) {
      const tol = o.scalar_tolerance === undefined ? 1e-6 : o.scalar_tolerance;
      if (o.scalar_range[0] < o.scalar_bounds[0] - tol || o.scalar_range[1] > o.scalar_bounds[1] + tol)
        reasons.push("scalar range [" + o.scalar_range.map(v => v.toFixed(3)).join(", ") +
          "] leaves its bounds [" + o.scalar_bounds.join(", ") + "] (non-monotone transport)");
    }
    if (o.staggered_fraction !== undefined && o.staggered_fraction > ENVELOPE.staggered_max)
      reasons.push("spurious staggered lattice mode carries " + (100 * o.staggered_fraction).toFixed(1) +
        "% of the kinetic energy");
    if (o.free_surface) reasons.push("free surface needs a mass-tracking LBM extension (not implemented)");
    if (o.compressible_mach !== undefined && o.compressible_mach > ENVELOPE.mach_max)
      reasons.push("flow Mach " + o.compressible_mach + " is outside the isothermal weakly-compressible model");
    const marginal = o.mach !== undefined && o.mach > ENVELOPE.mach_good && o.mach <= ENVELOPE.mach_max;
    return {applicable: reasons.length === 0, verdict: reasons.length ? "not_applicable" :
      marginal ? "marginal" : "applicable", reasons, envelope: ENVELOPE};
  }

  // Share of kinetic energy in the period-2 (Nyquist) mode along any lattice axis. A smooth flow
  // keeps it tiny; a large share is a spurious staggered lattice mode, not physics.
  function staggeredFraction(domain, v) {
    const F = domain.count, coords = [domain.x, domain.y, domain.z], comps = [v.ux, v.uy, v.uz];
    let total = 0;
    for (let i = 0; i < F; i++) total += v.ux[i] * v.ux[i] + v.uy[i] * v.uy[i] + v.uz[i] * v.uz[i];
    if (!(total > 0)) return 0;
    let worst = 0;
    for (let a = 0; a < 3; a++) {
      const b = (a + 1) % 3, c = (a + 2) % 3, lines = new Map();
      for (let i = 0; i < F; i++) {
        const key = coords[b][i] + "," + coords[c][i];
        let line = lines.get(key);
        if (!line) { line = [0, 0, 0, 0]; lines.set(key, line); }
        const sign = coords[a][i] & 1 ? -1 : 1;
        for (let k = 0; k < 3; k++) line[k] += sign * comps[k][i];
        line[3] += 1;
      }
      let energy = 0;
      for (const line of lines.values()) energy += (line[0] ** 2 + line[1] ** 2 + line[2] ** 2) / line[3];
      worst = Math.max(worst, energy / total);
    }
    return worst;
  }

  // Trilinear sample of a fluid-cell field at lattice coordinates (cell centres at integers).
  // Wall/missing corners are dropped and the weights renormalised; null if none remain.
  function sample(domain, field, x, y, z) {
    const x0 = Math.floor(x), y0 = Math.floor(y), z0 = Math.floor(z);
    let acc = 0, wsum = 0;
    for (let k = 0; k < 8; k++) {
      const ix = x0 + (k & 1), iy = y0 + ((k >> 1) & 1), iz = z0 + ((k >> 2) & 1);
      const j = domain.at(ix, iy, iz);
      if (j < 0) continue;
      const wt = (1 - Math.abs(x - ix)) * (1 - Math.abs(y - iy)) * (1 - Math.abs(z - iz));
      if (wt <= 0) continue;
      acc += wt * field[j]; wsum += wt;
    }
    return wsum > 0 ? acc / wsum : null;
  }

  // Plain error norms between paired samples (mean L1, RMS L2, Linf, signed bias).
  function errorNorms(actual, expected) {
    if (actual.length !== expected.length || !actual.length) throw new Error("Error norms need paired samples");
    let l1 = 0, l2 = 0, linf = 0, bias = 0;
    for (let i = 0; i < actual.length; i++) {
      const e = actual[i] - expected[i];
      l1 += Math.abs(e); l2 += e * e; bias += e; linf = Math.max(linf, Math.abs(e));
    }
    const n = actual.length;
    return {l1: l1 / n, l2: Math.sqrt(l2 / n), linf, bias: bias / n, n};
  }

  // Bounded agreement score in [0,1]: exp(-relative error). 1 means identical.
  function score(relativeError) {
    return Number.isFinite(relativeError) ? Math.exp(-Math.abs(relativeError)) : 0;
  }

  // ---- Dual-run confrontation helpers (schema trech_lbm_comparison_v1) --------------------
  // Same-bin profile comparison; `scale` (same unit) normalises the score.
  function compareProfiles(baseline, lbm, scale) {
    if (!finitePositive(scale)) throw new Error("Profile comparison needs a positive scale");
    const norms = errorNorms(lbm, baseline);
    return {norms, relative_rms: norms.l2 / scale, score: score(norms.l2 / scale)};
  }

  // Co-located vector samples ([[x,y,z],...]): magnitude ratio, mean direction cosine and the
  // relative L2 difference. Pairs where either vector vanishes are left out of the cosine.
  function compareVectors(baseline, lbm) {
    if (baseline.length !== lbm.length || !baseline.length) throw new Error("Vector comparison needs paired samples");
    let b2 = 0, l2 = 0, d2 = 0, cos = 0, used = 0;
    for (let i = 0; i < baseline.length; i++) {
      const a = baseline[i], b = lbm[i];
      const na = Math.hypot(a[0], a[1], a[2]), nb = Math.hypot(b[0], b[1], b[2]);
      b2 += na * na; l2 += nb * nb;
      d2 += (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2;
      if (na > 0 && nb > 0) { cos += (a[0] * b[0] + a[1] * b[1] + a[2] * b[2]) / (na * nb); used++; }
    }
    const n = baseline.length, rmsB = Math.sqrt(b2 / n), rmsL = Math.sqrt(l2 / n);
    const ratio = rmsB > 0 ? rmsL / rmsB : null;
    const meanCos = used ? cos / used : null;
    return {samples: n, rms_baseline: rmsB, rms_lbm: rmsL, speed_ratio: ratio,
      mean_direction_cosine: meanCos, relative_l2: rmsB > 0 ? Math.sqrt(d2 / n) / rmsB : null,
      speed_score: ratio && ratio > 0 ? score(Math.log(ratio)) : 0,
      direction_score: meanCos === null ? 0 : (1 + meanCos) / 2};
  }

  // Geometric-mean agreement over named [0,1] scores; any zero makes the card zero.
  function scoreCard(scores) {
    const names = Object.keys(scores);
    if (!names.length || !names.every(k => Number.isFinite(scores[k]) && scores[k] >= 0 && scores[k] <= 1))
      throw new Error("Score card needs scores in [0,1]");
    const overall = names.some(k => scores[k] === 0) ? 0 :
      Math.exp(names.reduce((s, k) => s + Math.log(scores[k]), 0) / names.length);
    return {scores, overall, agreement: overall >= 0.8 ? "agree" : overall >= 0.5 ? "partial" : "diverge"};
  }

  // ---- On-the-fly applicability (learned, not textbook) ---------------------------------
  // The engine decides where a lattice holds from evidence gathered during the run itself:
  //   evidence: a twin lattice at another resolution on the same clock; the local twin
  //             discrepancy is the observed error of each cell (no assumed convergence order);
  //   context:  lattice-intrinsic local descriptors of each cell;
  //   learning: ctx.learnDomains grows response domains error = f(context) online and predicts
  //             every cell's error BEFORE it sees that frame (prequential);
  //   verdict:  share of cells whose predicted error meets the caller's declared accuracy demand.
  // The textbook envelope (`assess`) stays a reference the learned verdict is compared with.

  // Axis neighbours of every fluid cell (-1 = wall/outside), cached on the domain.
  function neighbours(domain) {
    if (domain._neighbours) return domain._neighbours;
    const F = domain.count, nb = new Int32Array(6 * F);
    const steps = [[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]];
    for (let i = 0; i < F; i++) for (let k = 0; k < 6; k++)
      nb[6 * i + k] = domain.at(domain.x[i] + steps[k][0], domain.y[i] + steps[k][1], domain.z[i] + steps[k][2]);
    // Breadth-first distance (in cells) to the nearest wall link.
    const wallDistance = new Float64Array(F).fill(Infinity), queue = [];
    for (let i = 0; i < F; i++) for (let k = 0; k < 6; k++) if (nb[6 * i + k] < 0) { wallDistance[i] = 1; queue.push(i); break; }
    for (let head = 0; head < queue.length; head++) {
      const i = queue[head];
      for (let k = 0; k < 6; k++) {
        const j = nb[6 * i + k];
        if (j >= 0 && wallDistance[j] > wallDistance[i] + 1) { wallDistance[j] = wallDistance[i] + 1; queue.push(j); }
      }
    }
    for (let i = 0; i < F; i++) if (!Number.isFinite(wallDistance[i])) wallDistance[i] = Math.max(...domain.shape);
    domain._neighbours = {nb, wallDistance};
    return domain._neighbours;
  }

  // Lattice-intrinsic, dimensionless descriptors per fluid cell of a thermal flow. They name no
  // material: local Mach |u|/cs, cell Reynolds |u|/nu, cell Peclet |u|/D, scalar step per cell
  // (relative to `scalarScale`), velocity curvature |mean(neighbours) - u|/cs (walls at rest)
  // and wall distance in cells.
  function localDescriptors(thermal, scalarScale) {
    const domain = thermal.domain, F = domain.count, {nb, wallDistance} = neighbours(domain);
    const v = thermal.flow.velocity(), T = thermal.scalar.values();
    const cs = Math.sqrt(lattice(thermal.flow.lattice).cs2), nu = thermal.flow.viscosity, D = thermal.scalar.diffusivity;
    const out = {mach: new Float64Array(F), cell_reynolds: new Float64Array(F), cell_peclet: new Float64Array(F),
      scalar_step: new Float64Array(F), velocity_curvature: new Float64Array(F), wall_distance: Float64Array.from(wallDistance)};
    for (let i = 0; i < F; i++) {
      const speed = Math.hypot(v.ux[i], v.uy[i], v.uz[i]);
      out.mach[i] = speed / cs; out.cell_reynolds[i] = speed / nu; out.cell_peclet[i] = speed / D;
      let gx = 0, gy = 0, gz = 0, mx = 0, my = 0, mz = 0;
      for (let a = 0; a < 3; a++) {
        const p = nb[6 * i + 2 * a], m = nb[6 * i + 2 * a + 1];
        const g = p >= 0 && m >= 0 ? 0.5 * (T[p] - T[m]) : p >= 0 ? T[p] - T[i] : m >= 0 ? T[i] - T[m] : 0;
        if (a === 0) gx = g; else if (a === 1) gy = g; else gz = g;
      }
      for (let k = 0; k < 6; k++) {
        const j = nb[6 * i + k];
        if (j >= 0) { mx += v.ux[j]; my += v.uy[j]; mz += v.uz[j]; }
      }
      out.scalar_step[i] = Math.hypot(gx, gy, gz) / scalarScale;
      out.velocity_curvature[i] = Math.hypot(mx / 6 - v.ux[i], my / 6 - v.uy[i], mz / 6 - v.uz[i]) / cs;
    }
    return out;
  }

  // Observed local error from a twin lattice on the same physical domain and clock. Both lattices
  // share their lower corner; ratio = twin cell / main cell. Velocities are compared in physical
  // units (each lattice's own velocity scale). Errors: |dT| / scalarScale and
  // |du| / (rms speed of the main lattice + floor).
  function twinDiscrepancy(main, twin, o) {
    const d = main.domain, F = d.count;
    const v = main.flow.velocity(), T = main.scalar.values();
    const w = twin.flow.velocity(), Tw = twin.scalar.values();
    let rms = 0;
    for (let i = 0; i < F; i++) rms += v.ux[i] ** 2 + v.uy[i] ** 2 + v.uz[i] ** 2;
    rms = Math.sqrt(rms / F) * o.velocityScale;
    const temperature = new Float64Array(F), velocity = new Float64Array(F), valid = new Uint8Array(F);
    for (let i = 0; i < F; i++) {
      const x = (d.x[i] + 0.5) / o.ratio - 0.5, y = (d.y[i] + 0.5) / o.ratio - 0.5, z = (d.z[i] + 0.5) / o.ratio - 0.5;
      const tt = sample(twin.domain, Tw, x, y, z);
      if (tt === null) continue;
      const ux = sample(twin.domain, w.ux, x, y, z) * o.twinVelocityScale;
      const uy = sample(twin.domain, w.uy, x, y, z) * o.twinVelocityScale;
      const uz = sample(twin.domain, w.uz, x, y, z) * o.twinVelocityScale;
      temperature[i] = Math.abs(T[i] - tt) / o.scalarScale;
      velocity[i] = Math.hypot(v.ux[i] * o.velocityScale - ux, v.uy[i] * o.velocityScale - uy,
        v.uz[i] * o.velocityScale - uz) / (rms + o.velocityFloor);
      valid[i] = 1;
    }
    return {temperature, velocity, valid, rms_speed: rms};
  }

  // One learning step: features/errors over cells (valid mask), demand per error target.
  // Returns the learned (prequential) and observed shares meeting the demand, plus the learned
  // domains described in context space. acc accumulates the run.
  function learnApplicability(ctx, o) {
    const keep = [];
    for (let i = 0; i < o.valid.length; i++) if (o.valid[i]) keep.push(i);
    if (!keep.length) return null;
    const pick = a => Float64Array.from(keep, i => a[i]);
    const features = Object.fromEntries(Object.keys(o.features).sort().map(k => [k, pick(o.features[k])]));
    const targets = Object.fromEntries(Object.keys(o.errors).sort().map(k => [k, pick(o.errors[k])]));
    const report = ctx.learnDomains({name: o.name, time: o.time, features, targets,
      options: o.options || {min_elements: 64}, report: o.report || "summary"});
    if (!report) return null;
    const names = Object.keys(targets), n = keep.length;
    let predicted = 0, known = 0, observed = 0;
    const per = Object.fromEntries(names.map(k => [k, {predicted: 0, known: 0, observed: 0}]));
    for (let r = 0; r < n; r++) {
      let ok = true, okObserved = true, has = true;
      for (const k of names) {
        const p = report.predictions[k][r];
        if (p === null || !Number.isFinite(p)) has = false;
        else { per[k].known++; if (p <= o.demand[k]) per[k].predicted++; else ok = false; }
        if (targets[k][r] > o.demand[k]) okObserved = false; else per[k].observed++;
      }
      if (has) { known++; if (ok) predicted++; }
      if (okObserved) observed++;
    }
    const byTarget = Object.fromEntries(names.map(k => [k, {
      learned_share: per[k].known ? per[k].predicted / per[k].known : null, observed_share: per[k].observed / n}]));
    const featureNames = report.features;
    // Only domains holding cells this frame describe where the lattice currently stands.
    const domains = report.domains.filter(dm => dm.elements > 0).map(dm => {
      const value = Object.fromEntries(names.map((k, j) => [k, dm.value_at_mean ? dm.value_at_mean[j] : null]));
      return {id: dm.id, elements: dm.elements, model: dm.model,
        predicted_error_at_mean: value,
        meets_demand: names.every(k => value[k] !== null && value[k] <= o.demand[k]),
        context_envelope: Object.fromEntries(featureNames.map((f, j) =>
          [f, [dm.feature_min ? dm.feature_min[j] : null, dm.feature_max ? dm.feature_max[j] : null]])),
        error_rmse: Object.fromEntries(names.map((k, j) => [k, dm.error_rmse ? dm.error_rmse[j] : null]))};
    });
    const step = {call: report.call, rows: n, graded: report.scored,
      learned_share: known ? predicted / known : null, predicted_rows: known,
      observed_share: observed / n, by_target: byTarget, metrics: report.metrics, domains};
    if (o.accumulator) {
      const acc = o.accumulator;
      acc.calls++; acc.rows += n;
      if (known) {
        acc.learned.push(step.learned_share); acc.observed_when_learned.push(step.observed_share);
        acc.by_target = acc.by_target || {};
        for (const k of names) {
          const t = acc.by_target[k] = acc.by_target[k] || {learned: [], observed_when_learned: []};
          if (byTarget[k].learned_share !== null) {
            t.learned.push(byTarget[k].learned_share); t.observed_when_learned.push(byTarget[k].observed_share);
          }
        }
      }
    }
    return step;
  }

  // Run verdict from the accumulated learned shares: applicable when the learned share meets
  // the coverage demand on every graded call after the first `warmup` calls.
  function applicabilityVerdict(acc, coverage, warmup) {
    const out = verdictOf(acc, coverage, warmup);
    // Per target: the lattice may hold for one quantity (e.g. temperature) but not another.
    if (acc.by_target) out.by_target = Object.fromEntries(Object.entries(acc.by_target).map(([k, t]) =>
      [k, verdictOf(t, coverage, warmup)]));
    return out;
  }
  function verdictOf(acc, coverage, warmup) {
    const learned = acc.learned.slice(warmup), observed = acc.observed_when_learned.slice(warmup);
    if (!learned.length) return {verdict: "undetermined", reason: "no graded calls after warm-up"};
    const min = Math.min(...learned), mean = learned.reduce((a, b) => a + b, 0) / learned.length;
    const observedMean = observed.reduce((a, b) => a + b, 0) / observed.length;
    return {verdict: min >= coverage ? "applicable" : mean >= coverage ? "intermittent" : "not_applicable",
      coverage_demand: coverage, warmup_calls: warmup, graded_calls: learned.length,
      learned_share_min: min, learned_share_mean: mean, observed_share_mean: observedMean,
      learned_minus_observed: mean - observedMean};
  }

  globalThis.TRECH_LBM_REFERENCE = {lattice, createDomain, createFlow, createScalar, createThermalFlow,
    neighbours, localDescriptors, twinDiscrepancy, learnApplicability, applicabilityVerdict,
    units, assess, compareProfiles, compareVectors, scoreCard, staggeredFraction,
    sample, errorNorms, score, ENVELOPE, SCHEMA: "trech_lbm_comparison_v1",
    scope: "Lattice Boltzmann comparison solver (development dual-run companion); not a Geant4 result or learned prediction"};
})();
