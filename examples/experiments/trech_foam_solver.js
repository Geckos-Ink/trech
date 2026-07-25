// Shared bonded-parcel foam mechanics: a GROWING viscoelastic network under gravity.
//
// This module is deliberately physics-agnostic about chemistry. It owns only the
// mechanics that any expanding/curing/draining foam shares, and the scenario
// drives it with per-parcel fields its own inferred reaction produces:
//
//   growthRatePerS[i]  volumetric growth rate of parcel i (gas generation)
//   relaxRatePerS[i]   Maxwell stress-relaxation rate (viscous flow / creep)
//   strengthScale[i]   0..1 structural strength (network build-up)
//
// What the module does with them, every bounded step:
//   * bond rest lengths GROW with the local volumetric growth (linear = cube root)
//   * bond rest lengths CREEP toward the current length at the local relaxation
//     rate, so a low-viscosity material flows and slumps while a curing one locks
//   * bonds BREAK permanently once their tensile strain passes the failure strain
//     scaled by the local strength -- so cracks, detachment and fragmentation are
//     consequences of the stress state, never scheduled events
//   * gravity, cup-wall, ground and parcel contacts are solved as position-based
//     constraints (XPBD-style), which stays stable at the bounded step sizes a
//     minutes-long chemical process needs
//   * detached fragments are integrated with substeps so a sub-second ballistic
//     fall lands in the right place inside a much coarser network step
//
// Nothing here schedules a lean, a crack, a drop, or a landing site. Those come
// out of gravity acting on a network whose growth and strength are imperfect --
// the imperfection magnitude itself is a scenario input (inferred, not typed
// here), realised as a deterministic per-parcel field.
//
// Honest scope: this is hook-layer continuum mechanics ("physics for
// comparison"), not a Geant4 result. Geant4 supplies the material base its
// coefficients are inferred from, and the per-tick clock.
//
// Usage:
//   TRECH_INCLUDE("trech_foam_solver.js");
//   const foam = globalThis.TRECH_FOAM.create({ ... });
//   foam.step(dt);

globalThis.TRECH_FOAM = (function () {
  "use strict";

  const GRAVITY_MM_PER_S2 = 9806.65; // standard gravity, a physical constant

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, Number(v))); }
  function clamp01(v) { return clamp(v, 0.0, 1.0); }

  // Deterministic per-parcel noise (xorshift over the stable particle id).
  function noise01(id, stream) {
    let x = (((id + 1) * 1664525) + ((stream + 1) * 1013904223)) >>> 0;
    x ^= x << 13; x ^= x >>> 17; x ^= x << 5;
    return (x >>> 0) / 4294967296.0;
  }
  // Zero-mean unit-ish deviate from two noise draws (Irwin-Hall, deterministic).
  function deviate(id, stream) {
    return (noise01(id, stream) + noise01(id, stream + 977) +
            noise01(id, stream + 5501) - 1.5) * 1.1547;
  }

  // A smooth, spatially CORRELATED random field: a fixed sum of sinusoidal modes
  // whose wavelengths are comparable to the body itself. Real mixing and cell-size
  // imperfection comes in patches -- a badly mixed streak, a warmer side -- not as
  // independent noise per cell. That distinction matters twice over: patchy
  // heterogeneity is what actually tips a rising bun over, and unlike white noise
  // it does NOT average away when the discretisation is refined, so the macroscopic
  // consequence converges instead of vanishing into a finer mesh.
  const FIELD_MODES = 5;
  function makeSmoothField(correlationLengthMm, streamSeed) {
    const dirs = [], wavelengths = [], phases = [];
    for (let m = 0; m < FIELD_MODES; m += 1) {
      const theta = 2.0 * Math.PI * noise01(streamSeed + m, 101);
      const cosPhi = 2.0 * noise01(streamSeed + m, 211) - 1.0;
      const sinPhi = Math.sqrt(Math.max(0.0, 1.0 - cosPhi * cosPhi));
      dirs.push([sinPhi * Math.cos(theta), sinPhi * Math.sin(theta), cosPhi]);
      wavelengths.push(correlationLengthMm * (0.7 + 1.1 * noise01(streamSeed + m, 331)));
      phases.push(2.0 * Math.PI * noise01(streamSeed + m, 457));
    }
    const normalisation = Math.sqrt(FIELD_MODES / 2.0);
    return function field(x, y, z) {
      let sum = 0.0;
      for (let m = 0; m < FIELD_MODES; m += 1) {
        const d = dirs[m];
        const projection = d[0] * x + d[1] * y + d[2] * z;
        sum += Math.sin(2.0 * Math.PI * projection / wavelengths[m] + phases[m]);
      }
      return sum / normalisation;
    };
  }

  function create(options) {
    const opt = options || {};
    const n = Math.max(8, Math.floor(opt.parcelCount || 256));
    const fillRadiusMm = Number(opt.fillRadiusMm);
    const fillHeightMm = Number(opt.fillHeightMm);
    const fillBottomMm = Number(opt.fillBottomMm || 0.0);
    const cupInnerRadiusMm = Number(opt.cupInnerRadiusMm);
    const cupWallThicknessMm = Number(opt.cupWallThicknessMm || 2.5);
    const cupHeightMm = Number(opt.cupHeightMm);
    const groundZMm = Number(opt.groundZMm || 0.0);
    const groundRadiusMm = Number(opt.groundRadiusMm || (cupInnerRadiusMm * 6.0));
    const gravityScale = opt.gravityScale === undefined ? 1.0 : Number(opt.gravityScale);
    const constraintIterations = Math.max(1, Math.floor(opt.constraintIterations || 2));
    const fragmentSubsteps = Math.max(1, Math.floor(opt.fragmentSubsteps || 4));
    const maxBondsPerParcel = Math.max(4, Math.floor(opt.maxBondsPerParcel || 8));
    const imperfectionDispersion = Math.max(0.0, Number(opt.imperfectionDispersion || 0.0));
    if (!(fillRadiusMm > 0) || !(fillHeightMm > 0)) {
      throw new Error("foam solver requires a positive fill cylinder");
    }

    const fillVolumeMm3 = Math.PI * fillRadiusMm * fillRadiusMm * fillHeightMm;
    const parcelVolumeMm3 = fillVolumeMm3 / n;
    const initialSpacingMm = Math.cbrt(parcelVolumeMm3);

    const px = new Float64Array(n), py = new Float64Array(n), pz = new Float64Array(n);
    const vx = new Float64Array(n), vy = new Float64Array(n), vz = new Float64Array(n);
    const qx = new Float64Array(n), qy = new Float64Array(n), qz = new Float64Array(n);
    const dxAcc = new Float64Array(n), dyAcc = new Float64Array(n), dzAcc = new Float64Array(n);
    const corrCount = new Int32Array(n);
    // Scenario-driven per-parcel material fields (filled every step by the caller).
    const growthRatePerS = new Float64Array(n);
    const relaxRatePerS = new Float64Array(n);
    const relaxFactorPerStep = new Float64Array(n);
    const strengthScale = new Float64Array(n);
    // Per-parcel drag: the material's own resistance to creeping flow, which for a
    // curing resin climbs by orders of magnitude between pour and set. Zero means
    // "use the solver-wide coefficient".
    const dragPerS = new Float64Array(n);
    // Deterministic imperfection field: growth and strength multipliers. This is
    // the "no two cells are alike" reality of a hand-mixed foam. The magnitude is
    // the scenario's inferred dispersion; the pattern is reproducible.
    const growthImperfection = new Float64Array(n);
    const strengthImperfection = new Float64Array(n);
    const ids = new Array(n);
    const freeFlag = new Uint8Array(n);      // detached from the main body
    const landedFlag = new Uint8Array(n);    // detached and at rest on the ground
    const componentLabel = new Int32Array(n);
    const bondCount = new Int32Array(n);
    // Surface exposure 0..1: a parcel that lost neighbours is on the free surface
    // and exchanges heat with the room; a fully-bonded one is in the core. This is
    // what gives a curing bun a hot core and a cool skin without anyone saying so.
    const exposure = new Float64Array(n);

    for (let i = 0; i < n; i += 1) ids[i] = i;

    // ---- initial packing: a jittered lattice filling the liquid cylinder ----
    // The lattice is tightened until the poured cylinder really holds n distinct
    // sites, so no two parcels are ever seeded on top of each other (which the
    // contact solver would then blow apart).
    (function fill() {
      let spacing = initialSpacingMm;
      let candidates = [];
      for (let attempt = 0; attempt < 60 && candidates.length < n; attempt += 1) {
        candidates = [];
        const half = Math.ceil(fillRadiusMm / spacing) + 1;
        const layers = Math.max(1, Math.round(fillHeightMm / spacing));
        const layerHeight = fillHeightMm / layers;
        for (let iz = 0; iz < layers; iz += 1) {
          const z = fillBottomMm + (iz + 0.5) * layerHeight;
          const stagger = (iz % 2) * 0.5 * spacing;
          for (let iy = -half; iy <= half; iy += 1) {
            for (let ix = -half; ix <= half; ix += 1) {
              const x = ix * spacing + stagger;
              const y = iy * spacing * 0.866;
              const r2 = x * x + y * y;
              if (r2 > fillRadiusMm * fillRadiusMm) continue;
              candidates.push([x, y, z, r2]);
            }
          }
        }
        if (candidates.length < n) spacing *= 0.96;
      }
      if (candidates.length < n) {
        throw new Error("foam solver could not seed " + n + " parcels in the pour volume");
      }
      // Deterministic order (bottom-up, centre-out), then take exactly n.
      candidates.sort((a, b) => a[2] - b[2] || a[3] - b[3] || a[0] - b[0] || a[1] - b[1]);
      const jitter = 0.14 * spacing;
      for (let i = 0; i < n; i += 1) {
        const c = candidates[i];
        px[i] = c[0] + jitter * (noise01(i, 3) - 0.5);
        py[i] = c[1] + jitter * (noise01(i, 5) - 0.5);
        pz[i] = c[2] + jitter * (noise01(i, 7) - 0.5);
      }
    })();

    // The imperfection is a material property, sampled once from the smooth field
    // at each parcel's ORIGINAL position (so it travels with the material) plus a
    // small per-parcel cell-scale component.
    const correlationLengthMm = Number(opt.imperfectionCorrelationLengthMm ||
      (2.0 * fillRadiusMm));
    const growthField = makeSmoothField(correlationLengthMm, 7);
    const strengthField = makeSmoothField(correlationLengthMm, 23);
    const reactivityField = makeSmoothField(correlationLengthMm, 41);
    const reactivityImperfection = new Float64Array(n);
    for (let i = 0; i < n; i += 1) {
      const fx = px[i], fy = py[i], fz = pz[i];
      growthImperfection[i] = clamp(1.0 + imperfectionDispersion *
        (0.8 * growthField(fx, fy, fz) + 0.2 * deviate(i, 11)), 0.25, 2.5);
      strengthImperfection[i] = clamp(1.0 + imperfectionDispersion *
        (0.8 * strengthField(fx, fy, fz) + 0.2 * deviate(i, 23)), 0.25, 2.5);
      reactivityImperfection[i] = clamp(1.0 + imperfectionDispersion *
        (0.8 * reactivityField(fx, fy, fz) + 0.2 * deviate(i, 41)), 0.25, 2.5);
    }

    // ---- bond network: nearest neighbours at t=0, then persistent ----
    const bondCutoff = 1.45 * initialSpacingMm;
    const bondI = [], bondJ = [], bondRest = [];
    (function buildBonds() {
      const cell = bondCutoff;
      const grid = new Map();
      const key = (a, b, c) => a + "," + b + "," + c;
      for (let i = 0; i < n; i += 1) {
        const k = key(Math.floor(px[i] / cell), Math.floor(py[i] / cell),
                      Math.floor(pz[i] / cell));
        let bucket = grid.get(k);
        if (!bucket) { bucket = []; grid.set(k, bucket); }
        bucket.push(i);
      }
      const cutoff2 = bondCutoff * bondCutoff;
      for (let i = 0; i < n; i += 1) {
        const cx = Math.floor(px[i] / cell), cy = Math.floor(py[i] / cell),
              cz = Math.floor(pz[i] / cell);
        const found = [];
        for (let a = -1; a <= 1; a += 1) {
          for (let b = -1; b <= 1; b += 1) {
            for (let c = -1; c <= 1; c += 1) {
              const bucket = grid.get(key(cx + a, cy + b, cz + c));
              if (!bucket) continue;
              for (let q = 0; q < bucket.length; q += 1) {
                const j = bucket[q];
                if (j <= i) continue;
                const ddx = px[j] - px[i], ddy = py[j] - py[i], ddz = pz[j] - pz[i];
                const d2 = ddx * ddx + ddy * ddy + ddz * ddz;
                if (d2 <= cutoff2 && d2 > 1e-12) found.push([j, d2]);
              }
            }
          }
        }
        found.sort((a, b) => a[1] - b[1] || a[0] - b[0]);
        const keep = Math.min(found.length, maxBondsPerParcel);
        for (let q = 0; q < keep; q += 1) {
          bondI.push(i); bondJ.push(found[q][0]);
          bondRest.push(Math.sqrt(found[q][1]));
        }
      }
    })();
    const bondCountTotal = bondI.length;
    const bi = new Int32Array(bondI);
    const bj = new Int32Array(bondJ);
    const brest = new Float64Array(bondRest);
    const bbroken = new Uint8Array(bondCountTotal);
    // Local integrity: how much of each parcel's original link set survives. A
    // parcel that has lost half its links sits at a crack tip, and the links it has
    // left carry what the broken ones used to -- so they part sooner. Without this
    // load concentration damage stays diffuse and a cracked overhang never actually
    // separates.
    const initialBonds = new Int32Array(n);
    const liveBonds = new Int32Array(n);
    for (let b = 0; b < bondCountTotal; b += 1) {
      initialBonds[bi[b]] += 1; initialBonds[bj[b]] += 1;
      liveBonds[bi[b]] += 1; liveBonds[bj[b]] += 1;
    }

    const state = {
      n, ids, px, py, pz, vx, vy, vz,
      growthRatePerS, relaxRatePerS, strengthScale, dragPerS,
      growthImperfection, strengthImperfection, reactivityImperfection,
      imperfectionCorrelationLengthMm: correlationLengthMm,
      freeFlag, landedFlag, componentLabel, bondCount, exposure,
      parcelVolumeMm3, initialSpacingMm,
      bondCountTotal,
      // coefficients (set by the scenario from its inferred cascade values)
      coeff: {
        bondStiffnessPerS2: 900.0,
        bondFailureStrain: 0.30,
        // Material drag: sets the terminal creep velocity g/drag inside the foam.
        structuralDampingPerS: 2500.0,
        contactFriction: 0.55,
        contactRestitution: 0.05
      },
      // running metrics
      timeS: 0.0,
      steps: 0,
      bondsBroken: 0,
      maxSpeedMmS: 0.0,
      fragmentEvents: 0,
      largestComponentSize: n,
      componentCount: 1,
      detachedParcels: 0,
      landedParcels: 0,
      groundZMm, groundRadiusMm, cupInnerRadiusMm, cupHeightMm,
      gravityMmPerS2: GRAVITY_MM_PER_S2 * gravityScale,
      gravityScale
    };

    // The material's own linear scale: it grows with the mean volumetric growth
    // the scenario reports, independently of how many bonds have broken, so a
    // fragmenting foam keeps a well-defined parcel size.
    let materialLinearGrowth = 1.0;
    const CONTACT_FRACTION = 0.86; // parcels resist compaction below this spacing

    function currentSpacingMm() {
      return initialSpacingMm * materialLinearGrowth;
    }
    function contactRestMm() {
      return CONTACT_FRACTION * currentSpacingMm();
    }

    // ---- hash grid over all parcels (rebuilt once per step) ----------------
    let tableSize = 1;
    while (tableSize < 2 * n) tableSize <<= 1;
    const tableMask = tableSize - 1;
    const cellStart = new Int32Array(tableSize + 1);
    const cellCursor = new Int32Array(tableSize);
    const cellItems = new Int32Array(n);
    const cellIx = new Int32Array(n), cellIy = new Int32Array(n), cellIz = new Int32Array(n);
    let gridCellMm = 1.0;
    // Half-neighbourhood: the own cell plus the 13 cells "after" it. Every pair is
    // still visited exactly once (own cell uses j>i, forward cells take all j), for
    // half the scan work of the full 27.
    const FORWARD_CELLS = [
      1, 0, 0, -1, 1, 0, 0, 1, 0, 1, 1, 0,
      -1, -1, 1, 0, -1, 1, 1, -1, 1,
      -1, 0, 1, 0, 0, 1, 1, 0, 1,
      -1, 1, 1, 0, 1, 1, 1, 1, 1
    ];

    function hashCell(ix, iy, iz) {
      return (((ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791)) & tableMask) >>> 0;
    }
    function buildGrid(cellMm) {
      gridCellMm = Math.max(cellMm, 1e-6);
      const inv = 1.0 / gridCellMm;
      cellStart.fill(0);
      for (let i = 0; i < n; i += 1) {
        const ix = Math.floor(qx[i] * inv), iy = Math.floor(qy[i] * inv),
              iz = Math.floor(qz[i] * inv);
        cellIx[i] = ix; cellIy[i] = iy; cellIz[i] = iz;
        cellStart[hashCell(ix, iy, iz) + 1] += 1;
      }
      for (let c = 0; c < tableSize; c += 1) cellStart[c + 1] += cellStart[c];
      for (let c = 0; c < tableSize; c += 1) cellCursor[c] = cellStart[c];
      for (let i = 0; i < n; i += 1) {
        cellItems[cellCursor[hashCell(cellIx[i], cellIy[i], cellIz[i])]++] = i;
      }
    }

    // ---- constraint solving -------------------------------------------------
    // A correction vector points from i toward j scaled by the (signed) error, so
    // i moves along it and j against it: a stretched bond pulls its ends together,
    // an overlap pushes them apart.
    function accumulate(i, j, cx, cy, cz) {
      dxAcc[i] += cx; dyAcc[i] += cy; dzAcc[i] += cz;
      dxAcc[j] -= cx; dyAcc[j] -= cy; dzAcc[j] -= cz;
      corrCount[i] += 1; corrCount[j] += 1;
    }

    function solveBonds(dt) {
      const compliance = 1.0 / Math.max(state.coeff.bondStiffnessPerS2 * dt * dt, 1e-9);
      const stiffnessFactor = 1.0 / (1.0 + compliance);
      for (let b = 0; b < bondCountTotal; b += 1) {
        if (bbroken[b]) continue;
        const i = bi[b], j = bj[b];
        const ddx = qx[j] - qx[i], ddy = qy[j] - qy[i], ddz = qz[j] - qz[i];
        const d2 = ddx * ddx + ddy * ddy + ddz * ddz;
        if (d2 < 1e-12) continue;
        const d = Math.sqrt(d2);
        const rest = brest[b];
        const error = (d - rest) / d;
        const scale = 0.5 * stiffnessFactor * error;
        accumulate(i, j, ddx * scale, ddy * scale, ddz * scale);
      }
    }

    function applyAccumulated() {
      for (let i = 0; i < n; i += 1) {
        if (corrCount[i] === 0) continue;
        const inv = 1.0 / corrCount[i];
        qx[i] += dxAcc[i] * inv;
        qy[i] += dyAcc[i] * inv;
        qz[i] += dzAcc[i] * inv;
        dxAcc[i] = 0.0; dyAcc[i] = 0.0; dzAcc[i] = 0.0; corrCount[i] = 0;
      }
    }

    function solveBoundaries() {
      const contact = contactRestMm();
      for (let i = 0; i < n; i += 1) {
        // ground plane
        const floor = groundZMm + 0.45 * contact;
        if (qz[i] < floor) qz[i] = floor;
        // Cup wall, for material still inside the vessel column. Attached material
        // is held inside; only DETACHED pieces (integrateFragments) can leave.
        // Letting attached parcels resolve to the outside of the wall instead was
        // tried and rejected: it leaks material through the wall, relieving exactly
        // the stress that makes a rising bun crack. Spilling attached lather down
        // the OUTSIDE needs per-parcel wall sidedness -- deferred, see ROADMAP.md.
        if (qz[i] < cupHeightMm) {
          const r2 = qx[i] * qx[i] + qy[i] * qy[i];
          const limit = cupInnerRadiusMm - 0.35 * contact;
          if (r2 > limit * limit) {
            const r = Math.sqrt(r2);
            const s = limit / r;
            qx[i] *= s; qy[i] *= s;
          }
        }
        // table edge: nothing beyond it to rest on
        const rr2 = qx[i] * qx[i] + qy[i] * qy[i];
        if (rr2 > groundRadiusMm * groundRadiusMm) {
          const rr = Math.sqrt(rr2), s = groundRadiusMm / rr;
          qx[i] *= s; qy[i] *= s;
        }
      }
    }

    // Contact (non-penetration) constraints over every parcel pair inside the
    // material spacing. This is the foam's VOLUME: a liquid or a foam resists
    // being compacted, which is why a poured pool does not collapse flat under
    // its own weight and why the growing material pushes itself upward out of the
    // cup. It also lets fallen pieces pile on the table instead of interpenetrating.
    function solveContacts() {
      const rest = contactRestMm();
      const rest2 = rest * rest;
      for (let i = 0; i < n; i += 1) {
        const ix = cellIx[i], iy = cellIy[i], iz = cellIz[i];
        // own cell: only the parcels after i, so each pair is visited once
        let h = hashCell(ix, iy, iz);
        let stop = cellStart[h + 1];
        for (let q = cellStart[h]; q < stop; q += 1) {
          const j = cellItems[q];
          if (j <= i) continue;
          const ddx = qx[j] - qx[i], ddy = qy[j] - qy[i], ddz = qz[j] - qz[i];
          const d2 = ddx * ddx + ddy * ddy + ddz * ddz;
          if (d2 >= rest2 || d2 < 1e-12) continue;
          const d = Math.sqrt(d2);
          // Applied immediately (Gauss-Seidel) rather than averaged with every
          // other constraint: non-penetration converges in a couple of sweeps this
          // way, so the material's volume is set by the contact distance and not by
          // how many iterations were affordable. Fixed visit order keeps it
          // reproducible.
          const push = 0.5 * (d - rest) / d;
          const cx = ddx * push, cy = ddy * push, cz = ddz * push;
          qx[i] += cx; qy[i] += cy; qz[i] += cz;
          qx[j] -= cx; qy[j] -= cy; qz[j] -= cz;
        }
        // the 13 forward cells: every parcel in them
        for (let k = 0; k < 39; k += 3) {
          h = hashCell(ix + FORWARD_CELLS[k], iy + FORWARD_CELLS[k + 1],
                       iz + FORWARD_CELLS[k + 2]);
          stop = cellStart[h + 1];
          for (let q = cellStart[h]; q < stop; q += 1) {
            const j = cellItems[q];
            if (j === i) continue;
            const ddx = qx[j] - qx[i], ddy = qy[j] - qy[i], ddz = qz[j] - qz[i];
            const d2 = ddx * ddx + ddy * ddy + ddz * ddz;
            if (d2 >= rest2 || d2 < 1e-12) continue;
            const d = Math.sqrt(d2);
            const push = 0.5 * (d - rest) / d;
            const cx = ddx * push, cy = ddy * push, cz = ddz * push;
            qx[i] += cx; qy[i] += cy; qz[i] += cz;
            qx[j] -= cx; qy[j] -= cy; qz[j] -= cz;
          }
        }
      }
    }

    // ---- bond material update: growth, creep, failure ----------------------
    function updateBonds(dt) {
      const failureBase = state.coeff.bondFailureStrain;
      // The material's linear scale follows the mean volumetric growth (cube root).
      let meanGrowth = 0.0;
      for (let i = 0; i < n; i += 1) {
        meanGrowth += growthRatePerS[i];
        relaxFactorPerStep[i] = relaxRatePerS[i] > 0.0 ?
          1.0 - Math.exp(-relaxRatePerS[i] * dt) : 0.0;
      }
      meanGrowth /= n;
      materialLinearGrowth *= 1.0 + meanGrowth * dt / 3.0;
      for (let b = 0; b < bondCountTotal; b += 1) {
        if (bbroken[b]) continue;
        const i = bi[b], j = bj[b];
        const ddx = px[j] - px[i], ddy = py[j] - py[i], ddz = pz[j] - pz[i];
        const d = Math.sqrt(ddx * ddx + ddy * ddy + ddz * ddz);
        let rest = brest[b];
        // growth: local volumetric gas generation, linearised (cube root)
        const growth = 0.5 * (growthRatePerS[i] * growthImperfection[i] +
                              growthRatePerS[j] * growthImperfection[j]);
        rest *= 1.0 + growth * dt / 3.0;
        // creep: Maxwell relaxation of stress toward the current configuration
        // (per-parcel factors are precomputed once per step, not per bond)
        const relaxFactor = Math.min(relaxFactorPerStep[i], relaxFactorPerStep[j]);
        if (relaxFactor > 0.0) rest += (d - rest) * relaxFactor;
        brest[b] = rest;
        // failure: tensile strain beyond the locally-scaled failure strain
        // How far a link stretches before it parts depends on how solid it is: a
        // cured, cross-linked strut is brittle and cracks near the failure strain,
        // while a liquid filament necks a long way before it pinches off. So the
        // limit is the failure strain for fully-built structure and several times
        // that for a still-fluid link -- which is also why a settling liquid pool
        // flows instead of shattering.
        const strength = clamp01(0.5 * (strengthScale[i] * strengthImperfection[i] +
                                        strengthScale[j] * strengthImperfection[j]));
        const integrity = Math.min(liveBonds[i] / Math.max(1, initialBonds[i]),
                                   liveBonds[j] / Math.max(1, initialBonds[j]));
        const limit = failureBase * (1.0 + 1.5 * (1.0 - strength)) *
          (0.35 + 0.65 * integrity);
        if (rest > 1e-9 && (d - rest) / rest > limit) {
          bbroken[b] = 1;
          liveBonds[i] -= 1; liveBonds[j] -= 1;
          state.bondsBroken += 1;
        }
      }
    }

    // ---- connectivity: main body vs detached fragments ---------------------
    const parent = new Int32Array(n);
    function root(a) {
      let x = a;
      while (parent[x] !== x) { parent[x] = parent[parent[x]]; x = parent[x]; }
      return x;
    }
    function updateComponents() {
      for (let i = 0; i < n; i += 1) { parent[i] = i; bondCount[i] = 0; }
      for (let b = 0; b < bondCountTotal; b += 1) {
        if (bbroken[b]) continue;
        const i = bi[b], j = bj[b];
        bondCount[i] += 1; bondCount[j] += 1;
        const ra = root(i), rb = root(j);
        if (ra !== rb) parent[rb] = ra;
      }
      const sizes = new Map();
      for (let i = 0; i < n; i += 1) {
        const r = root(i);
        sizes.set(r, (sizes.get(r) || 0) + 1);
      }
      // The main body is the largest component that still touches the vessel.
      let mainRoot = -1, mainSize = -1;
      for (const [r, size] of sizes) {
        if (size > mainSize) { mainSize = size; mainRoot = r; }
      }
      const labelOf = new Map();
      let next = 0;
      let detached = 0, landed = 0;
      for (let i = 0; i < n; i += 1) {
        const r = root(i);
        if (!labelOf.has(r)) labelOf.set(r, next++);
        componentLabel[i] = labelOf.get(r);
        const isFree = r !== mainRoot;
        if (isFree && !freeFlag[i]) state.fragmentEvents += 1;
        freeFlag[i] = isFree ? 1 : 0;
        if (isFree) {
          detached += 1;
          const speed2 = vx[i] * vx[i] + vy[i] * vy[i] + vz[i] * vz[i];
          const resting = pz[i] < groundZMm + 2.5 * currentSpacingMm() && speed2 < 25.0;
          landedFlag[i] = resting ? 1 : 0;
          if (resting) landed += 1;
        } else {
          landedFlag[i] = 0;
        }
      }
      state.componentCount = next;
      state.largestComponentSize = mainSize;
      state.detachedParcels = detached;
      state.landedParcels = landed;
      let maxBonds = 1;
      for (let i = 0; i < n; i += 1) if (bondCount[i] > maxBonds) maxBonds = bondCount[i];
      for (let i = 0; i < n; i += 1) {
        exposure[i] = clamp01(1.0 - bondCount[i] / maxBonds);
      }
    }

    // Diffuse a per-parcel scalar along the intact bond network (symmetric, so
    // the field's total is conserved). Used for heat.
    function diffuseAlongBonds(values, ratePerS, dt) {
      if (!(ratePerS > 0.0)) return;
      const weight = 1.0 - Math.exp(-ratePerS * dt);
      for (let b = 0; b < bondCountTotal; b += 1) {
        if (bbroken[b]) continue;
        const i = bi[b], j = bj[b];
        const flux = (values[j] - values[i]) * weight * 0.25;
        values[i] += flux;
        values[j] -= flux;
      }
    }

    // ---- integration --------------------------------------------------------
    function integrate(dt) {
      const g = state.gravityMmPerS2;
      // The network is a dense viscous material, not a cloud of free particles:
      // a parcel inside it reaches its terminal creep velocity under the material's
      // own drag almost immediately. Integrating that exactly (v -> v_terminal with
      // an exponential approach) is what makes a poured pool sag at millimetres per
      // second instead of free-falling a whole parcel diameter every step. A piece
      // that has DETACHED is no longer inside the material -- it falls ballistically
      // through air in integrateFragments().
      const baseDrag = Math.max(state.coeff.structuralDampingPerS, 1e-6);
      for (let i = 0; i < n; i += 1) {
        if (freeFlag[i]) {
          qx[i] = px[i]; qy[i] = py[i]; qz[i] = pz[i];
          continue;
        }
        const drag = dragPerS[i] > 0.0 ? dragPerS[i] : baseDrag;
        const decay = Math.exp(-drag * dt);
        const terminalZ = -g / drag;
        vx[i] *= decay;
        vy[i] *= decay;
        vz[i] = terminalZ + (vz[i] - terminalZ) * decay;
        qx[i] = px[i] + vx[i] * dt;
        qy[i] = py[i] + vy[i] * dt;
        qz[i] = pz[i] + vz[i] * dt;
      }
      buildGrid(contactRestMm());
      for (let iter = 0; iter < constraintIterations; iter += 1) {
        solveBonds(dt);
        solveContacts();
        applyAccumulated();
        solveBoundaries();
      }
      const invDt = 1.0 / dt;
      const friction = clamp01(state.coeff.contactFriction);
      const restitution = clamp01(state.coeff.contactRestitution);
      const contact = contactRestMm();
      let maxSpeed = 0.0;
      for (let i = 0; i < n; i += 1) {
        if (freeFlag[i]) continue;
        vx[i] = (qx[i] - px[i]) * invDt;
        vy[i] = (qy[i] - py[i]) * invDt;
        vz[i] = (qz[i] - pz[i]) * invDt;
        px[i] = qx[i]; py[i] = qy[i]; pz[i] = qz[i];
        // ground friction / inelastic settling for parcels resting on the table
        if (pz[i] <= groundZMm + 0.5 * contact + 1e-9) {
          vx[i] *= (1.0 - friction);
          vy[i] *= (1.0 - friction);
          if (vz[i] < 0.0) vz[i] *= -restitution;
        }
        const speed = Math.sqrt(vx[i] * vx[i] + vy[i] * vy[i] + vz[i] * vz[i]);
        if (speed > maxSpeed) maxSpeed = speed;
      }
      if (maxSpeed > state.maxSpeedMmS) state.maxSpeedMmS = maxSpeed;
    }

    // Detached fragments are ballistic and much faster than the network; give
    // them substeps so a sub-second fall lands where gravity says it should.
    function integrateFragments(dt) {
      let any = false;
      for (let i = 0; i < n; i += 1) if (freeFlag[i] && !landedFlag[i]) { any = true; break; }
      if (!any) return;
      const g = state.gravityMmPerS2;
      const sub = dt / fragmentSubsteps;
      const friction = clamp01(state.coeff.contactFriction);
      const restitution = clamp01(state.coeff.contactRestitution);
      const contactRadius = contactRestMm();
      for (let s = 0; s < fragmentSubsteps; s += 1) {
        for (let i = 0; i < n; i += 1) {
          if (!freeFlag[i] || landedFlag[i]) continue;
          vz[i] -= g * sub;
          px[i] += vx[i] * sub;
          py[i] += vy[i] * sub;
          pz[i] += vz[i] * sub;
          const floor = groundZMm + 0.45 * contactRadius;
          if (pz[i] < floor) {
            pz[i] = floor;
            if (vz[i] < 0.0) vz[i] *= -restitution;
            vx[i] *= (1.0 - friction);
            vy[i] *= (1.0 - friction);
          }
          if (pz[i] < cupHeightMm) {
            const r2 = px[i] * px[i] + py[i] * py[i];
            const limit = cupInnerRadiusMm - 0.35 * contactRadius;
            const outside = cupInnerRadiusMm + cupWallThicknessMm;
            if (r2 > limit * limit && r2 < outside * outside && r2 > 1e-9) {
              // A piece that broke off over the rim clears the wall and falls to the
              // table; one still inside the vessel column stays in.
              const r = Math.sqrt(r2);
              const sc = limit / r;
              px[i] *= sc; py[i] *= sc;
              vx[i] *= 0.4; vy[i] *= 0.4;
            }
          }
          const rr2 = px[i] * px[i] + py[i] * py[i];
          if (rr2 > groundRadiusMm * groundRadiusMm) {
            const rr = Math.sqrt(rr2), sc = groundRadiusMm / rr;
            px[i] *= sc; py[i] *= sc; vx[i] *= 0.2; vy[i] *= 0.2;
          }
        }
      }
    }

    function step(dt) {
      integrate(dt);
      integrateFragments(dt);
      updateBonds(dt);
      state.timeS += dt;
      state.steps += 1;
    }

    // ---- observer metrics ---------------------------------------------------
    function metrics() {
      let cx = 0.0, cy = 0.0, cz = 0.0;
      let minZ = Infinity, maxZ = -Infinity, maxR = 0.0;
      // The BODY's own extent, excluding pieces in flight or lying on the table --
      // "how tall the bun is" must not be read off a fragment mid-fall.
      let bodyTopZ = -Infinity, bodyMaxR = 0.0;
      for (let i = 0; i < n; i += 1) {
        cx += px[i]; cy += py[i]; cz += pz[i];
        if (pz[i] < minZ) minZ = pz[i];
        if (pz[i] > maxZ) maxZ = pz[i];
        const r = Math.sqrt(px[i] * px[i] + py[i] * py[i]);
        if (r > maxR) maxR = r;
        if (!freeFlag[i]) {
          if (pz[i] > bodyTopZ) bodyTopZ = pz[i];
          if (r > bodyMaxR) bodyMaxR = r;
        }
      }
      if (bodyTopZ === -Infinity) bodyTopZ = maxZ;
      cx /= n; cy /= n; cz /= n;
      // Lean of the attached body: least-squares tilt of its axis, from the
      // regression of the horizontal position on height. Reported only for a body
      // tall enough to HAVE an axis -- a shallow puddle has no meaningful lean, and
      // a ratio of two small numbers must not be allowed to invent one.
      let sumZ = 0.0, sumZ2 = 0.0, sumX = 0.0, sumY = 0.0, sumZX = 0.0, sumZY = 0.0;
      let bodyN = 0, bodyMinZ = Infinity, bodyMaxZ = -Infinity;
      for (let i = 0; i < n; i += 1) {
        if (freeFlag[i]) continue;
        bodyN += 1;
        sumZ += pz[i]; sumZ2 += pz[i] * pz[i];
        sumX += px[i]; sumY += py[i];
        sumZX += pz[i] * px[i]; sumZY += pz[i] * py[i];
        if (pz[i] < bodyMinZ) bodyMinZ = pz[i];
        if (pz[i] > bodyMaxZ) bodyMaxZ = pz[i];
      }
      let leanDeg = 0.0, leanOffsetMm = 0.0;
      const bodyHeight = bodyN > 0 ? bodyMaxZ - bodyMinZ : 0.0;
      if (bodyN > 2 && bodyHeight > 3.0 * currentSpacingMm()) {
        const denom = bodyN * sumZ2 - sumZ * sumZ;
        if (Math.abs(denom) > 1e-9) {
          const slopeX = (bodyN * sumZX - sumZ * sumX) / denom;
          const slopeY = (bodyN * sumZY - sumZ * sumY) / denom;
          const slope = Math.sqrt(slopeX * slopeX + slopeY * slopeY);
          leanDeg = Math.atan(slope) * 180.0 / Math.PI;
          leanOffsetMm = slope * bodyHeight;
        }
      }
      // "Fell to the table" means a detached parcel is DOWN on the table and OUT of
      // the vessel footprint. A piece that comes loose near the bottom of the cup is
      // already low and already detached, but it has not fallen anywhere -- counting
      // it would let a zero-gravity control claim fallen debris.
      let groundParcels = 0, outsideCupParcels = 0;
      const restHeight = groundZMm + 2.5 * currentSpacingMm();
      const footprint = cupInnerRadiusMm + cupWallThicknessMm;
      for (let i = 0; i < n; i += 1) {
        if (!freeFlag[i]) continue;
        const radius = Math.sqrt(px[i] * px[i] + py[i] * py[i]);
        if (radius > footprint) {
          outsideCupParcels += 1;
          if (pz[i] <= restHeight) groundParcels += 1;
        }
      }
      // Compaction: how much smaller the body is than the material's own parcel
      // volume implies -- gravity squeezing the foam is a result, not a setting.
      const spacing = currentSpacingMm();
      const nominalVolume = n * spacing * spacing * spacing;
      const bodyVolume = Math.PI * maxR * maxR * Math.max(maxZ - minZ, 1e-6);
      return {
        centroid: [cx, cy, cz],
        minZMm: minZ, maxZMm: maxZ, maxRadiusMm: maxR,
        bodyTopZMm: bodyTopZ, bodyMaxRadiusMm: bodyMaxR,
        bodyHeightMm: bodyHeight,
        nominalVolumeMm3: nominalVolume,
        boundingVolumeMm3: bodyVolume,
        leanDeg, leanOffsetMm,
        groundParcels, outsideCupParcels,
        detachedParcels: state.detachedParcels,
        landedParcels: state.landedParcels,
        componentCount: state.componentCount,
        largestComponentSize: state.largestComponentSize,
        bondsBroken: state.bondsBroken,
        bondsTotal: bondCountTotal,
        spacingMm: currentSpacingMm()
      };
    }

    state.step = step;
    state.updateComponents = updateComponents;
    state.diffuseAlongBonds = diffuseAlongBonds;
    state.metrics = metrics;
    state.currentSpacingMm = currentSpacingMm;
    state.noise01 = noise01;
    state.gravityConstantMmPerS2 = GRAVITY_MM_PER_S2;
    return state;
  }

  return {
    create,
    GRAVITY_MM_PER_S2,
    noise01,
    deviate,
    honestScope: "hook-layer bonded-parcel continuum mechanics (physics for comparison); " +
      "standard gravity is a physical constant, all material coefficients are scenario-inferred"
  };
})();
