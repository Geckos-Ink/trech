// Water through a temperature program: 10 °C -> -1 °C (it FREEZES) -> 100 °C.
//
// A larger sibling of h2o_bulk_water.js built so the water can really freeze.
// Real water at -1 °C freezes heterogeneously: ice nucleates on a wall or an
// impurity and a crystal front grows into the liquid. This box reproduces that
// at molecular resolution:
//
//   * water model: coarse-grained mW (Molinero & Moore 2009), one site per
//     molecule with a tetrahedral three-body term. It melts at 274.6 K, within
//     1.5 K of real water, so -1 °C is below its melting point just as for real
//     water. (Rigid SPC/E, used by h2o_bulk_water, melts near 215 K and cannot
//     freeze at -1 °C at all.) Shared core: `js/trech_water_mw.js`.
//   * nucleation site: a FIXED ice Ih basal floor (two bilayers), an ideal
//     ice-templating substrate standing in for the container wall/impurity
//     where real water nucleates. It is never counted as frozen water.
//   * free surface: the water sits on the floor with vacuum above, so it can
//     expand as it freezes (ice is less dense); molecules that leave it
//     are counted as vapour.
//   * every molecule's phase is DETECTED each frame by CHILL+ (Nguyen &
//     Molinero 2015: hexagonal ice, cubic ice, interfacial ice, liquid) from
//     its neighbours' bond-orientational order -- nothing assigns a phase.
//
// The thermostat imposes the program (the experiment's boundary condition);
// freezing, the growth front, melting and any evaporation are the solver's own.
// Classical MD in the deterministic hook layer: Geant4 is the per-tick clock,
// not the source of the intermolecular forces ("physics for comparison").
//
// Time: the program spans ~2.8 ns of physical time (2.5 K below mW's melting
// point the ice front advances ~18 Å/ns at first and reaches ~75% of the
// water after ~1.5 ns, then stalls under the liquid-like free surface) while
// the GIF is seconds long. Each
// observer frame carries a declared PLAYBACK clock with a per-stage rate
// that compresses the slow growth and dilates the picosecond melt, so every
// transition state gets screen time; the physical clock is always shown
// alongside. Representation only.
//
// Run (slow, ~2 h: ~1 ns of mW per ~45 min of QuickJS):
//   trech run examples/scenarios/h2o_bulk_freeze_boil/h2o_bulk_freeze_boil.js \
//        --output build/dev/out_h2o_freeze_boil

TRECH_INCLUDE("../../../js/trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}
const units = helpers.units;
const geometry = helpers.geometry;

TRECH_INCLUDE("../../../js/trech_water_mw.js");
const mw = globalThis.TRECH_WATER_MW;
if (!mw) {
  throw new Error("TRECH_WATER_MW not available; include trech_water_mw.js");
}

// ---- system ----
const ICE_A = 4.424;               // Å, mW ice Ih basal lattice constant (rho_ice ~0.978 g/cm^3)
const NX = 6, NY = 4;              // orthorhombic ice cells across the floor (26.5 x 30.6 Å)
const FLOOR = mw.iceIhSites(ICE_A, NX, NY, 1, 1.0);   // 2 fixed bilayers (192 sites)
const LX = NX * ICE_A, LY = NY * FLOOR.cell[1];
const FLOOR_TOP = Math.max(...FLOOR.sites.map((s) => s[2]));
const N_LIQ = 600;                 // mobile water molecules (5.6x h2o_bulk_water's 108)
const LIQ_DENSITY = 0.0334;        // molecules / Å^3 for the initial placement
const LIQ_HEIGHT = N_LIQ / (LIQ_DENSITY * LX * LY);
const VACUUM = 30.0;               // Å of vacuum above the free surface
const LZ = FLOOR_TOP + 2.6 + LIQ_HEIGHT + VACUUM;
const ICE_SITES_PER_A3 = 8 / (FLOOR.cell[0] * FLOOR.cell[1] * FLOOR.cell[2]);
const ICE_A_PER_MOLECULE = 1 / (ICE_SITES_PER_A3 * LX * LY);   // ice thickness per frozen molecule
const DT = 10.0;                   // fs (standard mW step)
const SEED = 24601;
const C0 = 273.15;
const THERMO_EVERY = 2, THERMO_PHASE = 1;   // rescale on odd ticks; frames on even ticks
const THERMO_STRONG = 1.0, THERMO_GENTLE = 0.2;   // gentle = ~100 fs Berendsen coupling

// ---- temperature program (ticks of 10 fs) ----
const FRONT_WINDOW_NS = 0.5;         // ice-front velocity fit window at the start of a hold
const CONTACT_BILAYER_A = FLOOR.cell[2] / 2;   // one ice Ih bilayer (c/2 = 3.61 Å)
const PREP_TICKS = 1500, PREP_K = 300.0;   // melt the artificial start grid (not measured)
const STAGES = [
  { id: "hold_10C", kind: "hold", label: "10 °C", targetK: C0 + 10, equil: 2000, prod: 4000 },
  { id: "cool", kind: "ramp", label: "cooling 10 → -1 °C", fromK: C0 + 10, toK: C0 - 1, ticks: 2000 },
  { id: "hold_m1C", kind: "hold", label: "-1 °C", targetK: C0 - 1, equil: 0, prod: 250000 },
  { id: "heat", kind: "ramp", label: "heating -1 → 100 °C", fromK: C0 - 1, toK: C0 + 100, ticks: 8000 },
  { id: "hold_100C", kind: "hold", label: "100 °C", targetK: C0 + 100, equil: 0, prod: 12000 }
];
let cursor = PREP_TICKS;
for (const st of STAGES) {
  st.start = cursor;
  st.ticks = st.kind === "hold" ? st.equil + st.prod : st.ticks;
  cursor += st.ticks;
}
const TOTAL_TICKS = cursor;

// ---- measurement / observer cadence ----
const STRUCT_EVERY = 100;          // CHILL+ census every 1 ps
const ORIGIN_EVERY = 100, MAX_LAG = 1000;   // lateral multi-origin MSD (ticks)
// Observer frames: dense where the state changes fast, sparse in the long growth.
function frameStride(st) {
  if (!st) return 100;
  if (st.id === "hold_m1C") return 500;      // 5 ps
  if (st.id === "hold_100C" || st.id === "heat") return 40;   // 0.4 ps: melting
  return 100;
}

function stageAt(tick) {
  if (tick <= PREP_TICKS) return null;
  for (const st of STAGES) if (tick <= st.start + st.ticks) return st;
  return STAGES[STAGES.length - 1];
}
function targetAt(st, tick) {
  if (!st) return PREP_K;
  if (st.kind === "hold") return st.targetK;
  return st.fromK + (st.toK - st.fromK) * (tick - st.start) / st.ticks;
}

function buildSystem() {
  const positions = FLOOR.sites.slice(), fixed = FLOOR.sites.map(() => true);
  const sp = Math.cbrt(1 / LIQ_DENSITY);
  const nxl = Math.round(LX / sp), nyl = Math.round(LY / sp);
  let placed = 0;
  for (let iz = 0; placed < N_LIQ; iz++)
    for (let ix = 0; ix < nxl && placed < N_LIQ; ix++)
      for (let iy = 0; iy < nyl && placed < N_LIQ; iy++, placed++) {
        positions.push([(ix + 0.5) * LX / nxl, (iy + 0.5) * LY / nyl, FLOOR_TOP + 2.6 + iz * sp]);
        fixed.push(false);
      }
  return mw.create({ box: [LX, LY, LZ], positions, fixed, dt: DT, seed: SEED, initialK: PREP_K });
}

// Phase census of the mobile molecules (the floor is excluded): CHILL+ codes
// 0 liquid, 1 hexagonal ice, 2 cubic ice, 3 interfacial ice. Vapour = a mobile
// molecule with no neighbour inside 3.5 Å (it has left the liquid).
function census(sim) {
  const ch = mw.chillPlus(sim, 3.5);
  let hex = 0, cubic = 0, inter = 0, liquid = 0, vapour = 0, mobile = 0;
  for (let i = 0; i < sim.n; i++) {
    if (sim.fixed[i]) continue;
    mobile++;
    const p = ch.phase[i];
    if (ch.four[i].length === 0) { vapour++; continue; }
    if (p === 1) hex++; else if (p === 2) cubic++; else if (p === 3) inter++; else liquid++;
  }
  const crystal = hex + cubic;
  return {
    phase: ch.phase, four: ch.four, hex, cubic, inter, liquid, vapour, mobile,
    crystalFraction: crystal / mobile,
    iceThicknessA: crystal * ICE_A_PER_MOLECULE
  };
}

function resetHold(s) {
  s.msdOrigins = []; s.msdHead = 0;
  s.msdSum.fill(0); s.msdCnt.fill(0);
  s.sumT = 0; s.nT = 0; s.growth = [];
}

function lsq(points) {
  let sx = 0, sy = 0, sxx = 0, sxy = 0;
  for (const p of points) { sx += p.x; sy += p.y; sxx += p.x * p.x; sxy += p.x * p.y; }
  const d = points.length * sxx - sx * sx;
  return d !== 0 ? (points.length * sxy - sx * sy) / d : 0;
}

function lateralDiffusion(s) {
  const fit = [];
  for (let lag = Math.ceil(0.4 * MAX_LAG); lag <= MAX_LAG; lag++)
    if (s.msdCnt[lag] > 0) fit.push({ x: lag * DT, y: s.msdSum[lag] / s.msdCnt[lag] });
  if (fit.length < 8) return 0;
  return (lsq(fit) / 4) * 1e-5;   // 2D Einstein relation: Å^2/fs -> m^2/s
}

function ensureState(ctx) {
  if (!ctx.state || typeof ctx.state !== "object") throw new Error("ctx.state unavailable");
  if (!ctx.state.initialized) {
    ctx.state.sim = buildSystem();
    Object.assign(ctx.state, {
      tick: 0, initialized: true,
      msdOrigins: [], msdHead: 0,
      msdSum: new Float64Array(MAX_LAG + 1), msdCnt: new Float64Array(MAX_LAG + 1),
      sumT: 0, nT: 0, growth: [], results: [], last: null,
      play: { t: 0 }, chartsDeclared: false
    });
  }
  return ctx.state;
}

function measureHold(ctx, s, st, cen) {
  const meanT = s.nT ? s.sumT / s.nT : 0;
  // Ice-front growth velocity over the hold: least-squares slope of the
  // crystalline thickness vs time (Å per ns), from the per-ps census. The
  // whole-hold slope includes the plateau once the front reaches the free
  // surface, so the front velocity is also fitted over the first 0.5 ns.
  const growth = s.growth.length > 8 ? lsq(s.growth) : 0;
  const early = s.growth.length ? s.growth.filter((p) => p.x - s.growth[0].x <= FRONT_WINDOW_NS) : [];
  const front = early.length > 8 ? lsq(early) : 0;
  const result = {
    stage: st.id, label: st.label, target_K: st.targetK, target_C: st.targetK - C0,
    mean_temperature_K: meanT, mean_temperature_C: meanT - C0,
    duration_ps: st.ticks * DT / 1000,
    lateral_self_diffusion_m2_per_s: st.id === "hold_m1C" ? null : lateralDiffusion(s),
    crystal_fraction_end: cen.crystalFraction,
    ice_thickness_end_A: cen.iceThicknessA,
    hexagonal_ice: cen.hex, cubic_ice: cen.cubic, interfacial_ice: cen.inter,
    liquid: cen.liquid, vapour: cen.vapour,
    ice_growth_A_per_ns: growth,
    ice_front_velocity_A_per_ns: front,
    front_window_ns: FRONT_WINDOW_NS,
    // The fixed floor orders the water layer touching it into one ice
    // bilayer even above the melting point (epitaxial contact layer); ice
    // only counts as GROWN beyond that.
    contact_bilayer_A: CONTACT_BILAYER_A,
    model_melting_point_K: mw.MELTING_POINT_K,
    real_water_phase_1atm: TRECH_CHECKS["h2o_bulk_freeze_boil"].realPhase(st.targetK)
  };
  result.phase_verdict = TRECH_CHECKS["h2o_bulk_freeze_boil"].phaseVerdict(result);
  s.results.push(result);
  ctx.emit("phase_hold", result);
}

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    ctx.emit("scenario", {
      kind: "h2o_bulk_freeze_boil", mobile_molecules: N_LIQ, floor_sites: FLOOR.sites.length,
      box_A: [LX, LY, LZ], dt_fs: DT, ticks: TOTAL_TICKS, physical_time_ps: TOTAL_TICKS * DT / 1000,
      preparation: { ticks: PREP_TICKS, temperature_K: PREP_K },
      program: STAGES.map((st) => Object.assign({}, st)),
      model: "coarse-grained mW water (Molinero & Moore 2009; Tm 274.6 K) on a fixed ice Ih basal floor, free surface; classical MD in hook layer",
      phase_detection: "CHILL+ (Nguyen & Molinero 2015) per molecule per frame"
    });
  },
  onEventStart(ctx) {
    const s = ensureState(ctx);
    if (!ctx.event) return;
    const sim = s.sim;
    s.tick += 1;
    const st = stageAt(s.tick);
    const within = st ? s.tick - st.start - 1 : s.tick - 1;
    const targetK = targetAt(st, s.tick);
    const isHold = !!st && st.kind === "hold";
    const inProd = isHold && within >= st.equil;
    if (isHold && within === 0) resetHold(s);

    sim.step();
    if (s.tick % THERMO_EVERY === THERMO_PHASE)
      sim.thermostat(targetK, inProd ? THERMO_GENTLE : THERMO_STRONG);

    if (inProd) {
      s.sumT += sim.temperature(); s.nT += 1;
      if (st.id !== "hold_m1C") {
        const n = sim.n;
        if ((within - st.equil) % ORIGIN_EVERY === 0) {
          const ref = new Float64Array(n * 2);
          for (let i = 0; i < n; i++) { ref[2 * i] = sim.x[i]; ref[2 * i + 1] = sim.y[i]; }
          s.msdOrigins.push({ tick: s.tick, ref });
        }
        while (s.msdHead < s.msdOrigins.length &&
               s.tick - s.msdOrigins[s.msdHead].tick > MAX_LAG) s.msdHead++;
        for (let oi = s.msdHead; oi < s.msdOrigins.length; oi++) {
          const o = s.msdOrigins[oi], lag = s.tick - o.tick;
          if (lag < 1 || lag % 10 !== 0) continue;
          let sum = 0, cnt = 0;
          for (let i = 0; i < n; i++) {
            if (sim.fixed[i]) continue;
            const dx = sim.x[i] - o.ref[2 * i], dy = sim.y[i] - o.ref[2 * i + 1];
            sum += dx * dx + dy * dy; cnt++;
          }
          s.msdSum[lag] += sum; s.msdCnt[lag] += cnt;
        }
      }
    }

    const stride = frameStride(st);
    const frameTick = s.tick === 1 || s.tick % stride === 0;
    const lastOfStage = !!st && within === st.ticks - 1;
    let cen = null;
    if (frameTick || s.tick % STRUCT_EVERY === 0 || lastOfStage) {
      cen = census(sim);
      s.last = cen;
      if (inProd) s.growth.push({ x: s.tick * DT * 1e-6, y: cen.iceThicknessA });   // ns, Å
    }
    if (isHold && lastOfStage) measureHold(ctx, s, st, cen);
    if (frameTick) {
      TRECH_VIEWS["h2o_bulk_freeze_boil"].emitFrame(ctx, s, st, targetK, cen, {
        LX, LY, LZ, FLOOR_TOP, DT, C0, PREP_K, helpers, mw
      });
    }

    if (s.tick === TOTAL_TICKS) {
      ctx.emit("freeze_boil_summary", {
        mobile_molecules: N_LIQ, floor_sites: FLOOR.sites.length, box_A: [LX, LY, LZ],
        ticks: s.tick, physical_time_ps: s.tick * DT / 1000, holds: s.results,
        model_melting_point_K: mw.MELTING_POINT_K,
        model_reference: "mW, Molinero & Moore, J. Phys. Chem. B 113, 4008 (2009)",
        neighbor_overflow: sim.neighborOverflow,
        validation: TRECH_CHECKS["h2o_bulk_freeze_boil"].checks0(s.results, sim.neighborOverflow)
      });
    }
  }
};

globalThis.TRECH_CONFIG = {
  environment: { worldSizeMm: units.nm(10.0), worldMaterial: "G4_Galactic" },
  beam: { particle: "geantino", energyMeV: 0.0, direction: [0, 0, 1] },
  run: { nEvents: TOTAL_TICKS, seed: 13579, threads: 1 },
  determinism: { mode: "predictive" },
  system: { enable: true, mode: "steady_state", frame: "point_agnostic",
            ensemble: "h2o_bulk_freeze_boil" },
  geometry: {
    volumes: [
      geometry.boxVolume({
        name: "water_on_ice_floor", material: "G4_Galactic",
        sizeMm: [units.nm(3.0), units.nm(3.0), units.nm(8.0)],
        positionMm: [0, 0, 0], tags: ["fluid", "h2o", "md", "mW", "freezing", "phase_program"]
      })
    ]
  }
};
