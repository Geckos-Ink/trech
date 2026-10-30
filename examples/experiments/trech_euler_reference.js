// Independent 2D ideal-gas Euler comparison: first-order conservative Rusanov
// flux, CFL steps, reflective stair-step walls and open reservoir boundaries.
// No viscosity, chemistry, heat transfer, structural failure or learned physics.
(function() {
  if (globalThis.TRECH_EULER_REFERENCE) return;
  function create(o) {
    const {nx, ny, dx, gamma, gasConstant, rho, pressure, mach} = o;
    if (!Number.isInteger(nx) || !Number.isInteger(ny) || nx < 4 || ny < 4 || nx * ny > 20000 ||
        ![dx, gamma - 1, gasConstant, rho, pressure].every(v => Number.isFinite(v) && v > 0) ||
        !Number.isFinite(mach) || mach < 0 || mach > 3)
      throw new Error("Invalid Euler comparison inputs");
    const speed = mach * Math.sqrt(gamma * pressure / rho);
    const inlet = [rho, rho * speed, 0, pressure / (gamma - 1) + 0.5 * rho * speed * speed];
    let state = Array.from({length: nx * ny}, () => inlet.slice());
    const solid = state.map((_, i) => o.body !== false &&
      Math.hypot(i % nx + 0.5 - nx * 0.42, Math.floor(i / nx) + 0.5 - ny * 0.5) < ny * 0.14);
    let time = 0, steps = 0;
    const exchange = [0, 0, 0, 0];
    function primitive(u) {
      const p = (gamma - 1) * (u[3] - 0.5 * (u[1] * u[1] + u[2] * u[2]) / u[0]);
      if (!u.every(Number.isFinite) || !(u[0] > 0) || !(p > 0))
        throw new Error("Nonphysical Euler comparison state; refine grid/timestep instead of clipping");
      return {rho: u[0], vx: u[1] / u[0], vy: u[2] / u[0], p,
        temperature: p / (u[0] * gasConstant), c: Math.sqrt(gamma * p / u[0])};
    }
    function flux(u, axis) {
      const a = primitive(u), v = axis === 0 ? a.vx : a.vy;
      return [u[0] * v, u[1] * v + (axis === 0 ? a.p : 0),
        u[2] * v + (axis === 1 ? a.p : 0), (u[3] + a.p) * v];
    }
    function rusanov(a, b, axis) {
      const pa = primitive(a), pb = primitive(b), fa = flux(a, axis), fb = flux(b, axis);
      const s = Math.max(Math.abs(axis === 0 ? pa.vx : pa.vy) + pa.c,
                         Math.abs(axis === 0 ? pb.vx : pb.vy) + pb.c);
      return fa.map((v, k) => 0.5 * (v + fb[k] - s * (b[k] - a[k])));
    }
    function totals() {
      const sum = [0, 0, 0, 0];
      state.forEach((u, i) => {if (!solid[i]) for (let k = 0; k < 4; ++k) sum[k] += u[k] * dx * dx;});
      return sum;
    }
    const initial = totals();
    function advance() {
      let frequency = 0;
      state.forEach((u, i) => {if (!solid[i]) {
        const p = primitive(u); frequency = Math.max(frequency, (Math.abs(p.vx) + Math.abs(p.vy) + 2 * p.c) / dx);
      }});
      const dt = 0.35 / frequency;
      const next = state.map(u => u.slice());
      function face(a, b, axis, exteriorA, exteriorB) {
        const fluidA = a >= 0 && !solid[a], fluidB = b >= 0 && !solid[b];
        if (!fluidA && !fluidB) return;
        let left = fluidA ? state[a] : exteriorA;
        let right = fluidB ? state[b] : exteriorB;
        if (a >= 0 && solid[a]) {left = right.slice(); left[axis + 1] *= -1;}
        if (b >= 0 && solid[b]) {right = left.slice(); right[axis + 1] *= -1;}
        const f = rusanov(left, right, axis);
        for (let k = 0; k < 4; ++k) {
          if (fluidA) next[a][k] -= dt / dx * f[k];
          if (fluidB) next[b][k] += dt / dx * f[k];
          // Includes wall momentum exchange; wall mass/energy flux are zero.
          if (fluidA !== fluidB) exchange[k] += (fluidB ? 1 : -1) * dt * dx * f[k];
        }
      }
      for (let y = 0; y < ny; ++y) for (let x = 0; x <= nx; ++x) {
        const a = x ? y * nx + x - 1 : -1, b = x < nx ? y * nx + x : -1;
        face(a, b, 0, inlet, a >= 0 ? state[a] : inlet);
      }
      for (let y = 0; y <= ny; ++y) for (let x = 0; x < nx; ++x)
        face(y ? (y - 1) * nx + x : -1, y < ny ? y * nx + x : -1, 1, inlet, inlet);
      next.forEach((u, i) => {if (!solid[i]) primitive(u);});
      state = next; time += dt; steps++;
      return dt;
    }
    function snapshot() {
      const cells = [];
      state.forEach((u, i) => {if (!solid[i]) cells.push({x: (i % nx + 0.5) * dx,
        y: (Math.floor(i / nx) + 0.5) * dx, ...primitive(u)});});
      const integral = totals();
      return {time_s: time, steps, cells, integral, boundary_exchange: exchange.slice(),
        solid_positions: solid.flatMap((s, i) => s ? [[(i % nx + 0.5) * dx,
          (Math.floor(i / nx) + 0.5) * dx]] : []),
        balance_residual: integral.map((v, k) => v - initial[k] - exchange[k])};
    }
    return {advance, snapshot};
  }
  globalThis.TRECH_EULER_REFERENCE = {create};
})();
