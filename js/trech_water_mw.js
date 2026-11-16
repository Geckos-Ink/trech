// Shared coarse-grained mW water molecular-dynamics core (Molinero & Moore,
// J. Phys. Chem. B 113, 4008 (2009)): each water molecule is one site with a
// Stillinger-Weber two-body + three-body (tetrahedral) potential. Unlike the
// rigid-SPC/E core (`trech_water_md.js`, which melts near 215 K), mW melts at
// 274.6 K -- within 1.5 K of real water -- and has no partial charges, so it can
// actually FREEZE near 0 °C in reachable simulated time. It reproduces water's
// density maximum, liquid structure and ice Ih/Ic; it has no hydrogens, so
// hydrogen bonds are represented by the tetrahedral three-body term.
//
// Geometry: orthorhombic box, periodic in x, y and z. Optional FIXED sites
// (e.g. an ice-templating substrate) exert forces but never move. Neighbour
// search uses a cell list rebuilt every step. The cell layout is fixed by the
// box, so the traversal order -- and therefore the floating-point accumulation
// order -- is identical on every run: results are bit-reproducible.
//
// Units: Å, fs, amu; energies in amu·Å²/fs².
//
// Usage:
//   TRECH_INCLUDE("trech_water_mw.js");
//   const mw = globalThis.TRECH_WATER_MW;
//   const sim = mw.create({ box: [Lx, Ly, Lz], positions: [[x,y,z],...],
//                           fixed: [bool,...], dt: 10, seed, initialK });
//   sim.step()                  // one velocity-Verlet step (mobile sites only)
//   sim.temperature()           // kinetic T of the mobile sites
//   sim.thermostat(targetK, a)  // velocity rescale lambda = sqrt(1 + a (T0/T - 1))
//   sim.x / sim.y / sim.z       // unwrapped positions (Float64Array)
//   sim.neighbors(rmax)         // per-site [[j, dx, dy, dz, r], ...] by minimum image
//   mw.iceIhSites(a, nx, ny, nLayers, z0)  // ice Ih O sites, basal plane = xy
//   mw.chillPlus(sim, rmax)     // CHILL+ phase per site (Nguyen & Molinero 2015)

if (!globalThis.TRECH_RANDOM) TRECH_INCLUDE("trech_random.js");
globalThis.TRECH_WATER_MW = (function () {
  "use strict";

  // ---- mW parameters (Molinero & Moore 2009) ----
  const KCAL = 4.184e-4;              // kcal/mol -> amu Å²/fs²
  const KB = 8.314463e-7;             // amu Å²/(fs² K)
  const EPS = 6.189 * KCAL, SIG = 2.3925, A_CUT = 1.8;
  const LAMBDA = 23.15, GAMMA = 1.2, COS0 = -1 / 3;
  const AA = 7.049556277, BB = 0.6022245584;   // p = 4, q = 0
  const MASS = 18.015;
  const RC = A_CUT * SIG;                      // 4.3065 Å
  const MELTING_POINT_K = 274.6;               // mW ice Ih (Molinero & Moore 2009)

  const makeRng = globalThis.TRECH_RANDOM.mulberry32;
  const gauss = globalThis.TRECH_RANDOM.gaussian;

  function create(cfg) {
    const Lx = cfg.box[0], Ly = cfg.box[1], Lz = cfg.box[2];
    const n = cfg.positions.length, dt = cfg.dt;
    const x = new Float64Array(n), y = new Float64Array(n), z = new Float64Array(n);
    const vx = new Float64Array(n), vy = new Float64Array(n), vz = new Float64Array(n);
    const fx = new Float64Array(n), fy = new Float64Array(n), fz = new Float64Array(n);
    const fixed = new Uint8Array(n);
    let nMobile = 0;
    for (let i = 0; i < n; i++) {
      x[i] = cfg.positions[i][0]; y[i] = cfg.positions[i][1]; z[i] = cfg.positions[i][2];
      fixed[i] = cfg.fixed && cfg.fixed[i] ? 1 : 0;
      if (!fixed[i]) nMobile++;
    }
    const rng = makeRng(cfg.seed);
    const sv = Math.sqrt(KB * cfg.initialK / MASS);
    for (let i = 0; i < n; i++) {
      if (fixed[i]) continue;
      vx[i] = sv * gauss(rng); vy[i] = sv * gauss(rng); vz[i] = sv * gauss(rng);
    }

    // Cell list: cells at least RC wide (so the 27-cell stencil is complete);
    // both directions of every pair are stored, rebuilt every step.
    if (Math.min(Lx, Ly, Lz) < 3 * RC) throw new Error("mW box must be >= 3 cutoffs per side");
    const ncx = Math.floor(Lx / RC), ncy = Math.floor(Ly / RC), ncz = Math.floor(Lz / RC);
    const head = new Int32Array(ncx * ncy * ncz), next = new Int32Array(n);
    const MAXNB = 24;
    const nbCount = new Int32Array(n), nbIdx = new Int32Array(n * MAXNB);
    const nbDx = new Float64Array(n * MAXNB), nbDy = new Float64Array(n * MAXNB),
          nbDz = new Float64Array(n * MAXNB), nbR = new Float64Array(n * MAXNB);
    // Per-pair three-body radial factor g(r) = exp(gamma sig / (r - rc)) and g'(r),
    // evaluated once per pair instead of once per triplet.
    const nbG = new Float64Array(n * MAXNB), nbDG = new Float64Array(n * MAXNB);
    const GS = GAMMA * SIG;
    let overflow = 0;
    const wrapc = (v, L) => v - L * Math.floor(v / L);

    function buildNeighbors(rcut) {
      head.fill(-1); nbCount.fill(0);
      for (let i = n - 1; i >= 0; i--) {
        const cx = Math.min(ncx - 1, Math.floor(wrapc(x[i], Lx) / Lx * ncx));
        const cy = Math.min(ncy - 1, Math.floor(wrapc(y[i], Ly) / Ly * ncy));
        const cz = Math.min(ncz - 1, Math.floor(wrapc(z[i], Lz) / Lz * ncz));
        const c = (cx * ncy + cy) * ncz + cz;
        next[i] = head[c]; head[c] = i;
      }
      const rc2 = rcut * rcut;
      for (let i = 0; i < n; i++) {
        const cx = Math.min(ncx - 1, Math.floor(wrapc(x[i], Lx) / Lx * ncx));
        const cy = Math.min(ncy - 1, Math.floor(wrapc(y[i], Ly) / Ly * ncy));
        const cz = Math.min(ncz - 1, Math.floor(wrapc(z[i], Lz) / Lz * ncz));
        for (let ox = -1; ox <= 1; ox++) {
          const ax = (cx + ox + ncx) % ncx;
          for (let oy = -1; oy <= 1; oy++) {
            const ay = (cy + oy + ncy) % ncy;
            for (let oz = -1; oz <= 1; oz++) {
              const az = (cz + oz + ncz) % ncz;
              for (let j = head[(ax * ncy + ay) * ncz + az]; j >= 0; j = next[j]) {
                if (j <= i) continue;
                let dx = x[j] - x[i], dy = y[j] - y[i], dz = z[j] - z[i];
                dx -= Lx * Math.round(dx / Lx); dy -= Ly * Math.round(dy / Ly); dz -= Lz * Math.round(dz / Lz);
                const r2 = dx * dx + dy * dy + dz * dz;
                if (r2 >= rc2) continue;
                const r = Math.sqrt(r2);
                if (nbCount[i] < MAXNB && nbCount[j] < MAXNB) {
                  const dr = r - RC, g = r < RC ? Math.exp(GS / dr) : 0, dg = r < RC ? -g * GS / (dr * dr) : 0;
                  let k = i * MAXNB + nbCount[i]++;
                  nbIdx[k] = j; nbDx[k] = dx; nbDy[k] = dy; nbDz[k] = dz; nbR[k] = r; nbG[k] = g; nbDG[k] = dg;
                  k = j * MAXNB + nbCount[j]++;
                  nbIdx[k] = i; nbDx[k] = -dx; nbDy[k] = -dy; nbDz[k] = -dz; nbR[k] = r; nbG[k] = g; nbDG[k] = dg;
                } else {
                  overflow++;
                }
              }
            }
          }
        }
      }
    }

    let potential = 0;
    function computeForces() {
      buildNeighbors(RC);
      fx.fill(0); fy.fill(0); fz.fill(0);
      let pe = 0;
      const sig4 = SIG * SIG * SIG * SIG;
      // Two-body: phi2 = A eps (B (sig/r)^4 - 1) exp(sig / (r - rc)).
      for (let i = 0; i < n; i++) {
        const base = i * MAXNB, cnt = nbCount[i];
        for (let a = 0; a < cnt; a++) {
          const j = nbIdx[base + a];
          if (j <= i) continue;
          const r = nbR[base + a], dr = r - RC;
          const s4 = sig4 / (r * r * r * r), ex = Math.exp(SIG / dr);
          const e = AA * EPS * (BB * s4 - 1) * ex;
          const de = AA * EPS * ex * (-4 * BB * s4 / r - (BB * s4 - 1) * SIG / (dr * dr));
          pe += e;
          // F_i = +dE/dr * (r_j - r_i)/r
          const k = de / r;
          const ddx = nbDx[base + a] * k, ddy = nbDy[base + a] * k, ddz = nbDz[base + a] * k;
          fx[i] += ddx; fy[i] += ddy; fz[i] += ddz;
          fx[j] -= ddx; fy[j] -= ddy; fz[j] -= ddz;
        }
      }
      // Three-body around each centre i: lambda eps (cos - cos0)^2 g(r_ij) g(r_ik).
      const le = LAMBDA * EPS;
      for (let i = 0; i < n; i++) {
        const base = i * MAXNB, cnt = nbCount[i];
        for (let a = 0; a < cnt - 1; a++) {
          const j = nbIdx[base + a];
          const rij = nbR[base + a], uxj = nbDx[base + a] / rij, uyj = nbDy[base + a] / rij,
                uzj = nbDz[base + a] / rij;
          const gj = nbG[base + a], dgj = nbDG[base + a];
          for (let b = a + 1; b < cnt; b++) {
            const k = nbIdx[base + b];
            const rik = nbR[base + b], uxk = nbDx[base + b] / rik, uyk = nbDy[base + b] / rik,
                  uzk = nbDz[base + b] / rik;
            const gk = nbG[base + b], dgk = nbDG[base + b];
            const c = uxj * uxk + uyj * uyk + uzj * uzk, dc = c - COS0;
            pe += le * dc * dc * gj * gk;
            const t1 = 2 * le * dc * gj * gk;
            const t2j = le * dc * dc * dgj * gk, t2k = le * dc * dc * gj * dgk;
            // dE/dr_j and dE/dr_k
            const gjx = t1 * (uxk - c * uxj) / rij + t2j * uxj;
            const gjy = t1 * (uyk - c * uyj) / rij + t2j * uyj;
            const gjz = t1 * (uzk - c * uzj) / rij + t2j * uzj;
            const gkx = t1 * (uxj - c * uxk) / rik + t2k * uxk;
            const gky = t1 * (uyj - c * uyk) / rik + t2k * uyk;
            const gkz = t1 * (uzj - c * uzk) / rik + t2k * uzk;
            fx[j] -= gjx; fy[j] -= gjy; fz[j] -= gjz;
            fx[k] -= gkx; fy[k] -= gky; fz[k] -= gkz;
            fx[i] += gjx + gkx; fy[i] += gjy + gky; fz[i] += gjz + gkz;
          }
        }
      }
      potential = pe;
    }

    function temperature() {
      let ke = 0;
      for (let i = 0; i < n; i++) {
        if (fixed[i]) continue;
        ke += 0.5 * MASS * (vx[i] * vx[i] + vy[i] * vy[i] + vz[i] * vz[i]);
      }
      return nMobile ? 2 * ke / (3 * nMobile * KB) : 0;
    }

    const sim = {
      n, nMobile, box: [Lx, Ly, Lz], dt, x, y, z, vx, vy, vz, fixed,
      get potential() { return potential; },
      get neighborOverflow() { return overflow; },
      temperature,
      thermostat(targetK, a) {
        const T = temperature();
        if (T <= 0) return;
        const lam = Math.sqrt(Math.max(0, 1 + a * (targetK / T - 1)));
        for (let i = 0; i < n; i++) { vx[i] *= lam; vy[i] *= lam; vz[i] *= lam; }
      },
      step() {
        const h = 0.5 * dt / MASS;
        for (let i = 0; i < n; i++) {
          if (fixed[i]) continue;
          vx[i] += h * fx[i]; vy[i] += h * fy[i]; vz[i] += h * fz[i];
          x[i] += dt * vx[i]; y[i] += dt * vy[i]; z[i] += dt * vz[i];
        }
        computeForces();
        for (let i = 0; i < n; i++) {
          if (fixed[i]) continue;
          vx[i] += h * fx[i]; vy[i] += h * fy[i]; vz[i] += h * fz[i];
        }
      },
      // Minimum-image neighbours within rmax (<= RC uses the force list).
      neighbors(rmax) {
        if (rmax > RC) buildNeighbors(rmax);
        const out = [];
        for (let i = 0; i < n; i++) {
          const base = i * MAXNB, list = [];
          for (let a = 0; a < nbCount[i]; a++) {
            if (nbR[base + a] < rmax)
              list.push([nbIdx[base + a], nbDx[base + a], nbDy[base + a], nbDz[base + a], nbR[base + a]]);
          }
          out.push(list);
        }
        if (rmax > RC) buildNeighbors(RC);
        return out;
      },
      wrapped(i) { return [wrapc(x[i], Lx), wrapc(y[i], Ly), wrapc(z[i], Lz)]; }
    };
    computeForces();
    return sim;
  }

  // Ice Ih oxygen sites (wurtzite sublattice), basal plane = xy, c along z.
  // Orthorhombic cell a x sqrt(3) a x c with 8 sites; c = sqrt(8/3) a (ideal).
  function iceIhSites(a, nx, ny, nLayers, z0) {
    const c = Math.sqrt(8 / 3) * a, b = Math.sqrt(3) * a;
    const hex = [[1 / 3, 2 / 3, 0], [2 / 3, 1 / 3, 0.5], [1 / 3, 2 / 3, 0.375], [2 / 3, 1 / 3, 0.875]];
    const cell = [];
    for (const [f1, f2, f3] of hex) {
      const px = f1 * a - f2 * a / 2, py = f2 * b / 2;
      for (const [sx, sy] of [[0, 0], [a / 2, b / 2]]) {
        let cx = px + sx, cy = py + sy;
        cx -= a * Math.floor(cx / a); cy -= b * Math.floor(cy / b);
        cell.push([cx, cy, f3 * c]);
      }
    }
    const out = [];
    for (let l = 0; l < nLayers; l++)
      for (let ix = 0; ix < nx; ix++)
        for (let iy = 0; iy < ny; iy++)
          for (const s of cell) out.push([s[0] + ix * a, s[1] + iy * b, z0 + s[2] + l * c]);
    return { sites: out, cell: [a, b, c] };
  }

  // CHILL+ (Nguyen & Molinero, J. Phys. Chem. B 119, 9369 (2015)): per-site
  // l = 3 bond-orientational vectors over the 4 nearest neighbours; a bond is
  // "staggered" when c_ij <= -0.8 and "eclipsed" when -0.35 <= c_ij <= 0.25.
  // Hexagonal ice: 3 staggered + 1 eclipsed; cubic ice: 4 staggered;
  // interfacial ice: 2 or 3 staggered (with the rest unclassified/eclipsed).
  // Returns codes: 0 liquid, 1 hexagonal ice, 2 cubic ice, 3 interfacial ice.
  function chillPlus(sim, rmax) {
    const nbs = sim.neighbors(rmax || 3.5), n = sim.n;
    const S7 = Math.sqrt(7 / (16 * Math.PI)), S21 = Math.sqrt(21 / (64 * Math.PI)),
          S105 = Math.sqrt(105 / (32 * Math.PI)), S35 = Math.sqrt(35 / (64 * Math.PI));
    // q3m for m = 0..3 (real, imag); negative m follow by symmetry.
    const q = new Float64Array(n * 7), four = [];
    for (let i = 0; i < n; i++) {
      const list = nbs[i].slice().sort((u, v) => u[4] - v[4]).slice(0, 4);
      four.push(list.map((e) => e[0]));
      if (list.length < 4) continue;
      let q0 = 0, r1 = 0, i1 = 0, r2 = 0, i2 = 0, r3 = 0, i3 = 0;
      for (const e of list) {
        const ux = e[1] / e[4], uy = e[2] / e[4], uz = e[3] / e[4];
        q0 += S7 * (5 * uz * uz * uz - 3 * uz);
        const k1 = -S21 * (5 * uz * uz - 1);
        r1 += k1 * ux; i1 += k1 * uy;
        const k2 = S105 * uz;
        r2 += k2 * (ux * ux - uy * uy); i2 += k2 * 2 * ux * uy;
        const k3 = -S35;
        r3 += k3 * (ux * ux * ux - 3 * ux * uy * uy); i3 += k3 * (3 * ux * ux * uy - uy * uy * uy);
      }
      q.set([q0, r1, i1, r2, i2, r3, i3], i * 7);
    }
    const norm = (i) => {
      const o = i * 7;
      return Math.sqrt(q[o] * q[o] + 2 * (q[o + 1] * q[o + 1] + q[o + 2] * q[o + 2] +
             q[o + 3] * q[o + 3] + q[o + 4] * q[o + 4] + q[o + 5] * q[o + 5] + q[o + 6] * q[o + 6]));
    };
    const corr = (i, j) => {
      const a = i * 7, b = j * 7;
      const dot = q[a] * q[b] + 2 * (q[a + 1] * q[b + 1] + q[a + 2] * q[b + 2] +
                  q[a + 3] * q[b + 3] + q[a + 4] * q[b + 4] + q[a + 5] * q[b + 5] + q[a + 6] * q[b + 6]);
      const d = norm(i) * norm(j);
      return d > 0 ? dot / d : 0;
    };
    const phase = new Uint8Array(n);
    for (let i = 0; i < n; i++) {
      if (four[i].length < 4) continue;
      let st = 0, ec = 0;
      for (const j of four[i]) {
        if (four[j].length < 4) continue;
        const c = corr(i, j);
        if (c <= -0.8) st++;
        else if (c >= -0.35 && c <= 0.25) ec++;
      }
      if (st === 3 && ec === 1) phase[i] = 1;
      else if (st === 4) phase[i] = 2;
      else if (st === 3 || (st === 2 && ec >= 1)) phase[i] = 3;
    }
    return { phase, four };
  }

  return { create, iceIhSites, chillPlus, MELTING_POINT_K, RC, MASS, KB };
})();
