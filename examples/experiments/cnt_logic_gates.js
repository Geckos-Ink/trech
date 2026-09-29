// Vostok milestone (CNT parallel track): carbon-nanotube LOGIC GATES + CIRCUITS.
//
// cnt_band_structure.js answered "metallic or semiconducting, and what gap?"
// from the (n,m) chirality. This experiment takes the next step the ROADMAP and
// the user asked for: build the actual DEVICES -- carbon-nanotube field-effect
// transistors (CNTFETs) -- from that band structure, assemble them into the
// full family of logic gates, wire those gates into multi-stage circuits, and
// CONFIRM THE TRUTH TABLE the electrons produce at the output.
//
// The physics chain (each layer cross-checked against a textbook result):
//
//   1. BAND STRUCTURE -> DEVICE. A semiconducting CNT (here (16,0)) is the
//      transistor channel. Its gap E_g = 2 a_cc gamma0 / d (tight-binding
//      zone-folding, same as cnt_band_structure.js) sets how well it switches.
//
//   2. FERMI LEVEL -> SWITCHING. The gate voltage shifts the channel's Fermi
//      level E_F across the band edge; the carrier population it admits is
//      Fermi-Dirac, f(E) = 1/(1+exp((E-E_F)/kT)). Two measurable consequences:
//        * subthreshold swing SS = ln(10) * kT/q -> the famous ~60 mV/decade
//          room-temperature limit (here recovered from the simulated I_d(V_gs)).
//        * ON/OFF current ratio ~ exp(E_g / 2kT): a wide-gap (small-diameter)
//          tube switches cleanly; a METALLIC tube (E_g ~ 0) cannot be turned
//          off -- it is a permanent short. This is exactly the manufacturing
//          problem in docs/CNT/BackToTheCarbon.md: metallic tubes mixed into a
//          forest behave as invisible wires that destroy the logic.
//
//   3. DEVICE -> GATE. Each CNTFET is a switch with channel resistance R_on
//      (conducting) or R_off = R_on * onOffRatio (depleted). Static-CMOS gates
//      (pull-up p-FET network to Vdd, pull-down n-FET network to GND) set the
//      output node by a resistive divider, so the gate output is a real VOLTAGE
//      (not an assumed boolean). NOT/NAND/NOR are primitive stages; AND/OR/
//      BUFFER/XOR/XNOR are built by composing them -- a small gate netlist.
//
//   4. GATE -> CIRCUIT. Gates are chained into a half adder, a full adder, and
//      a 2-bit ripple-carry adder (carry propagating through two full adders --
//      "a series of gates with a circuit"). Output voltages propagate stage to
//      stage; the final levels are thresholded and compared to the canonical
//      arithmetic table.
//
// What is CONFIRMED: every gate reproduces its canonical truth table, the half/
// full/2-bit adders reproduce binary addition, the recovered subthreshold swing
// lands on ~60 mV/dec, and the SAME topology built from a metallic tube FAILS
// (its outputs collapse to ~Vdd/2 -- the logic is destroyed). Geant4 transports
// the electron beam through the representative CNT channel geometry each event.
//
// Honest scope (identical contract to the H2O MD ladder and cnt_band_structure):
// Geant4 transports electrons through the carbon geometry but does NOT compute
// band structure, the Fermi level, or CNTFET switching. Those are the hook-layer
// "physics for comparison" -- tight-binding zone-folding + Fermi-Dirac
// statistics + a static-CMOS resistive-divider device model. The on/off ratio
// is the genuine Fermi-statistics gate-quality knob; the C++ engine stays
// physics-agnostic.
//
// Run:
//   trech run examples/experiments/cnt_logic_gates.js \
//        --events 8 --output build/dev/out_cnt_logic_gates

TRECH_INCLUDE("trech_helpers.js");
const helpers = globalThis.TRECH_HELPERS;
if (!helpers) {
  throw new Error("TRECH_HELPERS not available; include trech_helpers.js");
}
const units = helpers.units;
const constants = helpers.constants;
const geometry = helpers.geometry;

// ---- tight-binding parameters (shared with cnt_band_structure.js) ----------
const A_CC = constants.carbonBondLengthNm;        // 0.142 nm
const GAMMA0 = 2.9;                                // eV, nn transfer integral
const DIAM_PREFACTOR = A_CC * Math.sqrt(3) / Math.PI;
const GAP_SCALING_EV_NM = 2 * A_CC * GAMMA0;       // E_g * d for semiconductors
const CURVATURE_GAP_COEFF_EV_NM2 = 0.050;          // metallic non-armchair gap

// ---- operating point -------------------------------------------------------
const TEMPERATURE_K = 300.0;                       // room temperature
const KT_EV = constants.boltzmannEvK * TEMPERATURE_K;   // kT in eV (= kT/q in V)
const VDD = 0.6;                                    // supply (V)
const V_TH = 0.15;                                  // n-FET threshold (V)
const IDEALITY = 1.0;                               // ideal subthreshold factor
// Real CNTFETs saturate the on/off ratio (~1e4-1e6) due to band-to-band and
// contact leakage; cap the divider's contrast there so the model stays
// realistic instead of producing absurd 1e30 ratios for very wide gaps.
const ON_OFF_CAP = 1.0e6;

// ---- band structure -> device --------------------------------------------
function tubeProps(n, m) {
  const root = Math.sqrt(n * n + n * m + m * m);
  const d = DIAM_PREFACTOR * root;                         // nm
  const thetaDeg = Math.atan2(Math.sqrt(3) * m, 2 * n + m) * 180 / Math.PI;
  const metallic = ((((n - m) % 3) + 3) % 3) === 0;
  const cos3theta = Math.cos(3 * thetaDeg * Math.PI / 180);
  const primaryGap = metallic ? 0.0 : GAP_SCALING_EV_NM / d;
  const curvatureGap = metallic
    ? CURVATURE_GAP_COEFF_EV_NM2 * Math.abs(cos3theta) / (d * d) : 0.0;
  return {
    n, m, diameter_nm: d, chiral_angle_deg: thetaDeg, metallic,
    band_gap_eV: primaryGap + curvatureGap,
    primary_gap_eV: primaryGap, curvature_secondary_gap_eV: curvatureGap
  };
}

// A CNTFET device: the band gap sets the Fermi-statistics on/off ratio, which
// becomes the R_off/R_on contrast of every transistor built from this tube.
function makeDevice(label, n, m) {
  const t = tubeProps(n, m);
  const idealOnOff = Math.exp(t.band_gap_eV / (2.0 * KT_EV));   // exp(E_g/2kT)
  const onOffRatio = Math.min(ON_OFF_CAP, idealOnOff);
  return {
    label,
    n: t.n, m: t.m,
    diameter_nm: t.diameter_nm,
    chiral_angle_deg: t.chiral_angle_deg,
    metallic: t.metallic,
    band_gap_eV: t.band_gap_eV,
    primary_gap_eV: t.primary_gap_eV,
    curvature_secondary_gap_eV: t.curvature_secondary_gap_eV,
    ideal_on_off_ratio: idealOnOff,
    on_off_ratio: onOffRatio,
    kT_eV: KT_EV
  };
}

// Working semiconducting channel, a textbook-metallic armchair counterexample,
// and a quasi-metallic zigzag (a tiny curvature gap -- still unusable for logic).
const SEMI = makeDevice("semiconducting_16_0", 16, 0);
const METAL = makeDevice("metallic_armchair_5_5", 5, 5);
const QUASI = makeDevice("quasi_metallic_zigzag_9_0", 9, 0);

// ---- static-CMOS resistive-divider gate model ------------------------------
// Logic values are carried as VOLTAGES normalised to Vdd in [0,1]. A FET's
// conductance is 1 (R_on) when on, 1/onOffRatio (R_off) when off. n-FET on when
// its gate is high, p-FET on when low. The output node sits between Vdd (through
// the pull-up conductance G_pu) and GND (through the pull-down G_pd):
//   Vout/Vdd = G_pu / (G_pu + G_pd).
function ser(g1, g2) { return 1.0 / (1.0 / g1 + 1.0 / g2); }   // series FETs
function par(g1, g2) { return g1 + g2; }                       // parallel FETs
function divide(gPu, gPd) { return gPu / (gPu + gPd); }
function railCloseness(v) { return Math.min(v, 1.0 - v); }     // 0 = clean rail
function fetG(type, vIn, dev) {
  const high = vIn > 0.5;
  const on = (type === "n") ? high : !high;
  return on ? 1.0 : 1.0 / dev.on_off_ratio;
}
// rec() records each stage's output rail-closeness into a trace so a circuit's
// worst-case noise margin (how far the weakest node sits from a clean rail) can
// be reported.
function rec(trace, v) { if (trace) trace.push(railCloseness(v)); return v; }

// Primitive single-stage CMOS gates (the only ones that are physically one
// stage). a,b are input voltages; returns the output voltage.
const prim = {
  INV: (a, dev, t) => rec(t, divide(fetG("p", a, dev), fetG("n", a, dev))),
  NAND2: (a, b, dev, t) => rec(t, divide(
    par(fetG("p", a, dev), fetG("p", b, dev)),    // PUN: p-FETs in parallel
    ser(fetG("n", a, dev), fetG("n", b, dev)))),  // PDN: n-FETs in series
  NOR2: (a, b, dev, t) => rec(t, divide(
    ser(fetG("p", a, dev), fetG("p", b, dev)),    // PUN: p-FETs in series
    par(fetG("n", a, dev), fetG("n", b, dev))))   // PDN: n-FETs in parallel
};

// Compound gates as netlists of primitive stages (real electrons crossing a
// SERIES of gates). AND = NAND then INV; OR = NOR then INV; XOR = AND(NAND,OR).
const logic = {
  NOT: (a, dev, t) => prim.INV(a, dev, t),
  BUFFER: (a, dev, t) => prim.INV(prim.INV(a, dev, t), dev, t),
  NAND: (a, b, dev, t) => prim.NAND2(a, b, dev, t),
  NOR: (a, b, dev, t) => prim.NOR2(a, b, dev, t),
  AND: (a, b, dev, t) => prim.INV(prim.NAND2(a, b, dev, t), dev, t),
  OR: (a, b, dev, t) => prim.INV(prim.NOR2(a, b, dev, t), dev, t),
  XOR: (a, b, dev, t) => {
    const nand = prim.NAND2(a, b, dev, t);
    const or = logic.OR(a, b, dev, t);
    return logic.AND(nand, or, dev, t);
  },
  XNOR: (a, b, dev, t) => prim.INV(logic.XOR(a, b, dev, t), dev, t)
};

function level(v) { return v > 0.5 ? 1 : 0; }

// ---- gate library: simulated truth table vs canonical reference ------------
const GATE_DEFS = [
  { name: "NOT", arity: 1, ref: (a) => (a ? 0 : 1), run: (i, d, t) => logic.NOT(i[0], d, t) },
  { name: "BUFFER", arity: 1, ref: (a) => a, run: (i, d, t) => logic.BUFFER(i[0], d, t) },
  { name: "AND", arity: 2, ref: (a, b) => a & b, run: (i, d, t) => logic.AND(i[0], i[1], d, t) },
  { name: "OR", arity: 2, ref: (a, b) => a | b, run: (i, d, t) => logic.OR(i[0], i[1], d, t) },
  { name: "NAND", arity: 2, ref: (a, b) => 1 - (a & b), run: (i, d, t) => logic.NAND(i[0], i[1], d, t) },
  { name: "NOR", arity: 2, ref: (a, b) => 1 - (a | b), run: (i, d, t) => logic.NOR(i[0], i[1], d, t) },
  { name: "XOR", arity: 2, ref: (a, b) => a ^ b, run: (i, d, t) => logic.XOR(i[0], i[1], d, t) },
  { name: "XNOR", arity: 2, ref: (a, b) => 1 - (a ^ b), run: (i, d, t) => logic.XNOR(i[0], i[1], d, t) }
];

function stageTopology(name, primitive, inputs, output) {
  const a = inputs[0];
  const b = inputs[1];
  if (primitive === "INV") {
    return {
      name, primitive, inputs, output,
      pull_up: [[{ type: "p", gate: a }]],
      pull_down: [[{ type: "n", gate: a }]]
    };
  }
  if (primitive === "NAND2") {
    return {
      name, primitive, inputs, output,
      pull_up: [[{ type: "p", gate: a }], [{ type: "p", gate: b }]],
      pull_down: [[{ type: "n", gate: a }, { type: "n", gate: b }]]
    };
  }
  if (primitive === "NOR2") {
    return {
      name, primitive, inputs, output,
      pull_up: [[{ type: "p", gate: a }, { type: "p", gate: b }]],
      pull_down: [[{ type: "n", gate: a }], [{ type: "n", gate: b }]]
    };
  }
  throw new Error("unknown primitive topology " + primitive);
}

function visualTopology(name) {
  if (name === "NOT") {
    return { name, inputs: ["A"], output: "Y", stages: [stageTopology("inv", "INV", ["A"], "Y")] };
  }
  if (name === "BUFFER") {
    return { name, inputs: ["A"], output: "Y", stages: [
      stageTopology("inv1", "INV", ["A"], "n1"),
      stageTopology("inv2", "INV", ["n1"], "Y")
    ] };
  }
  if (name === "NAND") {
    return { name, inputs: ["A", "B"], output: "Y", stages: [stageTopology("nand", "NAND2", ["A", "B"], "Y")] };
  }
  if (name === "NOR") {
    return { name, inputs: ["A", "B"], output: "Y", stages: [stageTopology("nor", "NOR2", ["A", "B"], "Y")] };
  }
  if (name === "AND") {
    return { name, inputs: ["A", "B"], output: "Y", stages: [
      stageTopology("nand", "NAND2", ["A", "B"], "n1"),
      stageTopology("inv", "INV", ["n1"], "Y")
    ] };
  }
  if (name === "OR") {
    return { name, inputs: ["A", "B"], output: "Y", stages: [
      stageTopology("nor", "NOR2", ["A", "B"], "n1"),
      stageTopology("inv", "INV", ["n1"], "Y")
    ] };
  }
  if (name === "XOR" || name === "XNOR") {
    const stages = [
      stageTopology("nand_ab", "NAND2", ["A", "B"], "n_nand"),
      stageTopology("nor_ab", "NOR2", ["A", "B"], "n_nor"),
      stageTopology("or_inv", "INV", ["n_nor"], "n_or"),
      stageTopology("and_nand", "NAND2", ["n_nand", "n_or"], "n_xor_bar"),
      stageTopology("xor_inv", "INV", ["n_xor_bar"], "n_xor")
    ];
    if (name === "XNOR") stages.push(stageTopology("xnor_inv", "INV", ["n_xor"], "Y"));
    else stages[stages.length - 1].output = "Y";
    return { name, inputs: ["A", "B"], output: "Y", stages };
  }
  throw new Error("unknown visual topology " + name);
}

function round4(x) { return Math.round(x * 1e4) / 1e4; }

function evalGate(def, dev) {
  const rows = [];
  let allOk = true;
  let worstRail = 0.0;
  const combos = 1 << def.arity;
  for (let c = 0; c < combos; c++) {
    const ins = [];
    for (let b = 0; b < def.arity; b++) ins.push((c >> b) & 1);
    const trace = [];
    const vout = def.run(ins, dev, trace);
    const out = level(vout);
    const ref = def.ref.apply(null, ins) & 1;
    const ok = out === ref;
    if (!ok) allOk = false;
    for (const rc of trace) if (rc > worstRail) worstRail = rc;
    rows.push({ in: ins, out, ref, out_voltage: round4(vout), ok });
  }
  return { name: def.name, arity: def.arity, rows, all_ok: allOk, worst_rail_closeness: round4(worstRail) };
}

function gatePanel(dev) {
  const gates = GATE_DEFS.map((g) => evalGate(g, dev));
  let worst = 0.0;
  let allOk = true;
  for (const g of gates) {
    if (!g.all_ok) allOk = false;
    if (g.worst_rail_closeness > worst) worst = g.worst_rail_closeness;
  }
  return { device: dev.label, gates, all_gates_correct: allOk, worst_rail_closeness: round4(worst) };
}

// ---- circuits: half adder, full adder, 2-bit ripple-carry adder ------------
function halfAdder(a, b, dev, trace) {
  return { sum: level(logic.XOR(a, b, dev, trace)), carry: level(logic.AND(a, b, dev, trace)) };
}
function fullAdder(a, b, cin, dev, trace) {
  const axb = logic.XOR(a, b, dev, trace);
  const sum = level(logic.XOR(axb, cin, dev, trace));
  const c1 = logic.AND(a, b, dev, trace);
  const c2 = logic.AND(axb, cin, dev, trace);
  const cout = level(logic.OR(c1, c2, dev, trace));
  return { sum, cout };
}

function evalHalfAdder(dev) {
  const rows = [];
  let allOk = true, worst = 0.0;
  for (let a = 0; a < 2; a++) {
    for (let b = 0; b < 2; b++) {
      const trace = [];
      const r = halfAdder(a, b, dev, trace);
      const refSum = a ^ b, refCarry = a & b;
      const ok = r.sum === refSum && r.carry === refCarry;
      if (!ok) allOk = false;
      for (const rc of trace) if (rc > worst) worst = rc;
      rows.push({ A: a, B: b, sum: r.sum, carry: r.carry, ref_sum: refSum, ref_carry: refCarry, ok });
    }
  }
  return { name: "half_adder", rows, all_ok: allOk, worst_rail_closeness: round4(worst) };
}

function evalFullAdder(dev) {
  const rows = [];
  let allOk = true, worst = 0.0;
  for (let a = 0; a < 2; a++) {
    for (let b = 0; b < 2; b++) {
      for (let cin = 0; cin < 2; cin++) {
        const trace = [];
        const r = fullAdder(a, b, cin, dev, trace);
        const total = a + b + cin;
        const refSum = total & 1, refCout = (total >> 1) & 1;
        const ok = r.sum === refSum && r.cout === refCout;
        if (!ok) allOk = false;
        for (const rc of trace) if (rc > worst) worst = rc;
        rows.push({ A: a, B: b, Cin: cin, sum: r.sum, cout: r.cout, ref_sum: refSum, ref_cout: refCout, ok });
      }
    }
  }
  return { name: "full_adder", rows, all_ok: allOk, worst_rail_closeness: round4(worst) };
}

// 2-bit ripple-carry adder: two full adders chained by the carry -- carry must
// propagate through a deep series of gates and still resolve to clean levels.
function evalRippleAdder2(dev) {
  const rows = [];
  let allOk = true, worst = 0.0;
  for (let a = 0; a < 4; a++) {
    for (let b = 0; b < 4; b++) {
      const a0 = a & 1, a1 = (a >> 1) & 1;
      const b0 = b & 1, b1 = (b >> 1) & 1;
      const trace = [];
      const fa0 = fullAdder(a0, b0, 0, dev, trace);
      const fa1 = fullAdder(a1, b1, fa0.cout, dev, trace);
      const result = fa0.sum + 2 * fa1.sum + 4 * fa1.cout;
      const ref = a + b;
      const ok = result === ref;
      if (!ok) allOk = false;
      for (const rc of trace) if (rc > worst) worst = rc;
      rows.push({ A: a, B: b, result, ref, ok });
    }
  }
  return { name: "ripple_carry_adder_2bit", rows, all_ok: allOk, worst_rail_closeness: round4(worst) };
}

// ---- Fermi-level transfer characteristic + subthreshold swing --------------
// I_d(V_gs) from Fermi-Dirac band-edge occupation: the smooth subthreshold ->
// above-threshold turn-on plus a band-gap-set leakage floor exp(-E_g/2kT).
function transferCurve(dev) {
  const vt = IDEALITY * dev.kT_eV;            // n*kT/q (V)
  const floor = Math.exp(-dev.band_gap_eV / (2.0 * dev.kT_eV));
  const points = [];
  const N = 40;
  for (let i = 0; i <= N; i++) {
    const vgs = VDD * i / N;
    const occ = Math.log(1.0 + Math.exp((vgs - V_TH) / vt));   // Fermi turn-on
    const id = occ + floor;
    points.push({ vgs: round4(vgs), id_rel: id, log10_id: Math.log10(id) });
  }
  // Subthreshold-swing fit: log10(I_d) vs V_gs in the subthreshold window
  // (V_gs well below V_th), where SS = dV_gs / dlog10(I_d) -> n*kT/q*ln10.
  const xs = [], ys = [];
  for (const p of points) {
    if (p.vgs <= V_TH - 2.0 * vt) { xs.push(p.vgs); ys.push(p.log10_id); }
  }
  let ssMvPerDec = 0.0;
  if (xs.length >= 3) {
    let sx = 0, sy = 0, sxx = 0, sxy = 0;
    const m = xs.length;
    for (let i = 0; i < m; i++) { sx += xs[i]; sy += ys[i]; sxx += xs[i] * xs[i]; sxy += xs[i] * ys[i]; }
    const slope = (m * sxy - sx * sy) / (m * sxx - sx * sx);   // dlog10(Id)/dVgs
    ssMvPerDec = slope > 0 ? 1000.0 / slope : 0.0;             // mV/decade
  }
  const idOff = points[0].id_rel;                              // V_gs = 0
  const idOn = points[points.length - 1].id_rel;              // V_gs = Vdd
  return {
    points: points.map((p) => ({ vgs: p.vgs, log10_id: round4(p.log10_id) })),
    subthreshold_swing_mV_per_dec: round4(ssMvPerDec),
    ideal_swing_mV_per_dec: round4(Math.LN10 * dev.kT_eV * 1000.0),
    transfer_on_off_ratio: round4(idOn / idOff),
    leakage_floor: floor
  };
}

// Temperature sweep: Fermi smearing makes the on/off ratio fall and the swing
// rise as kT grows -- the statistical signature of the Fermi level.
function temperatureSweep(n, m) {
  const out = [];
  for (const T of [250, 300, 350, 400]) {
    const kT = constants.boltzmannEvK * T;
    const t = tubeProps(n, m);
    out.push({
      temperature_K: T,
      kT_eV: round4(kT),
      on_off_ratio: Math.exp(t.band_gap_eV / (2.0 * kT)),
      swing_mV_per_dec: round4(Math.LN10 * kT * 1000.0)
    });
  }
  return out;
}

// ---- Geant4 geometry: representative semiconducting CNT channel -------------
const nm = units.nm(1.0);
const channelDiameterNm = SEMI.diameter_nm;                    // (16,0) ~1.25 nm
const outerRadiusMm = 0.5 * channelDiameterNm * nm;
const innerRadiusMm = Math.max(0.0, outerRadiusMm - constants.carbonWallThicknessNm * nm);
const cntMaterial = helpers.materialRegistry.fromPreset("carbon", {
  name: "cnt_carbon", densityGcm3: 2.2
});

const TOTAL_EVENTS = 8;

// ---- 3D observer frames (classic trech-viz / Studio) -------------------------
// Everything drawn is this scenario's own state: tube atoms are the (n,m) chirality geometry
// the band model reasons about, the glow is the model's computed drain current / FET
// conductance, and node colours are the evaluator's node voltages. Contacts, gate plates and
// the netlist layout are representation. Two streams: the transfer sweep and the CMOS gates.
const OBS = helpers.observer;
const CARBON_OFF = [0.33, 0.35, 0.4];
const CARBON_ON = [0.3, 0.95, 1.0];
const glowRgba = (s) => [CARBON_OFF[0] + (CARBON_ON[0] - CARBON_OFF[0]) * s,
                         CARBON_OFF[1] + (CARBON_ON[1] - CARBON_OFF[1]) * s,
                         CARBON_OFF[2] + (CARBON_ON[2] - CARBON_OFF[2]) * s, 1.0];
const voltRgba = (v) => [0.15 + 0.85 * v, 0.25 + 0.45 * v, 1.0 - 0.8 * v, 1.0];
function transferId(dev, vgs) {
  const vt = IDEALITY * dev.kT_eV;
  return Math.log(1.0 + Math.exp((vgs - V_TH) / vt)) + Math.exp(-dev.band_gap_eV / (2.0 * dev.kT_eV));
}

function emitTransferSweep(ctx) {
  const tubes = [SEMI, METAL, QUASI].map((dev, k) => ({
    dev, geo: helpers.cnt.roll(dev.n, dev.m, 4.0, {
      place: (q) => [q[0] + (k - 1) * 3.2, q[2] - 2.0, q[1]]   // axis along +y (up)
    })
  }));
  const idMin = Math.log10(transferId(SEMI, 0.0));
  const idMax = Math.log10(transferId(METAL, VDD));
  const N = 80;
  const names = tubes.map(({ dev }) => "(" + dev.n + "," + dev.m + ") " +
                          (dev.metallic ? "metallic" : "semiconducting"));
  const tubeColours = ["#66e0ff", "#ffb838", "#ff7ad9"];
  // Electrons along each tube: a representation of the model current (their count is
  // proportional to I_d, drift speed grows with it); each keeps its own helical lane.
  const LANES = 40;
  const idTop = transferId(METAL, VDD);
  for (let i = 0; i <= N; i += 1) {
    const vgs = VDD * i / N;
    const positions = [], colors = [], radii = [], bonds = [], apparatus = [], hud = [];
    const samples = { vgs: round4(vgs) };
    hud.push("n-FET gate sweep  V_gs = " + vgs.toFixed(3) + " V   (T = " + TEMPERATURE_K + " K)");
    for (let k = 0; k < tubes.length; k += 1) {
      const { dev, geo } = tubes[k];
      const id = transferId(dev, vgs);
      samples["id_" + k] = id;
      const glow = Math.max(0, Math.min(1, (Math.log10(id) - idMin) / (idMax - idMin)));
      const base = positions.length;
      for (const q of geo.atoms) { positions.push(q); colors.push(glowRgba(0.35 * glow)); radii.push(0.075); }
      for (const b of geo.bonds) bonds.push([base + b[0], base + b[1]]);
      const x = (k - 1) * 3.2, w = 2 * geo.radiusNm + 0.6;
      const lanes = Math.round(LANES * id / idTop);
      for (let e = 0; e < lanes; e += 1) {
        // R2 low-discrepancy lanes: evenly spread over the tube surface, no visible spiral.
        const phase0 = (0.5 + e * 0.5698402910) % 1.0;
        const along = (phase0 + i * (0.015 + 0.05 * id / idTop)) % 1.0;
        const ang = 2.0 * Math.PI * ((0.5 + e * 0.7548776662) % 1.0);
        const r = geo.radiusNm + 0.16;
        positions.push([x + r * Math.cos(ang), -2.0 + 4.0 * along, r * Math.sin(ang)]);
        colors.push([0.45, 0.85, 1.0, 1.0]);
        radii.push(0.13);
      }
      apparatus.push({ shape: "box", center: [x, -2.3, 0], size: [w, 0.6, w],
                       color_rgba: [0.95, 0.78, 0.35, 0.95], label: "source" });
      apparatus.push({ shape: "box", center: [x, 2.3, 0], size: [w, 0.6, w],
                       color_rgba: [0.95, 0.78, 0.35, 0.95], label: "drain" });
      hud.push(names[k] + "  Eg " + dev.band_gap_eV.toFixed(3) + " eV   I_d " + id.toExponential(2) + " (rel.)");
    }
    apparatus.push({ shape: "box", center: [0, 0, -2.2], size: [10.5, 3.6, 0.25],
                     color_rgba: [0.55, 0.6, 0.75, 0.35], label: "gate plate" });
    const charts = i === 0 ? [
      { id: "transfer", title: "transfer curve: drain current vs gate voltage", x: "vgs",
        x_label: "V_gs (V)", y_label: "I_d (relative, log)", log_y: true, cursor: false,
        x_range: [0, VDD],
        series: names.map((n, k) => ({ key: "id_" + k, label: n, color: tubeColours[k] })),
        note: "semiconducting: ~60 mV/decade until on; metallic: always on" },
      { id: "gap", title: "band gap from the (n,m) tight-binding model", x_label: "",
        y_label: "Eg (eV)", x_range: [-0.6, 2.6], y_range: [0, 0.8],
        categories: ["(16,0)", "(5,5)", "(9,0)"],
        reference: tubes.map(({ dev }, k) => ({ label: names[k], color: tubeColours[k],
                                               style: "bars", x: [k], y: [dev.band_gap_eV] })) }
    ] : [];
    ctx.emit("material_frame", Object.assign(OBS.frame({
      physicalTimeS: i, playbackTimeS: i,
      clockText: "V_gs " + vgs.toFixed(3) + " / " + VDD.toFixed(2) + " V",
      phase: "tight-binding gap -> Fermi-Dirac drain current (hook layer)",
      lengthUnit: "nm", upAxis: "y", digits: 4,
      positions, colors, radii, bonds, apparatus,
      samples, charts,
      labels: tubes.map(({ dev, geo }, k) => ({ position: [(k - 1) * 3.2, -2.95, 1.2],
                                                text: names[k], color_rgba: [0.85, 0.9, 1, 1] })),
      legend: OBS.legend([["carbon lattice (n,m)", CARBON_OFF.concat([1])],
                          ["electrons: count ∝ I_d (representation)", [0.45, 0.85, 1.0, 1]],
                          ["source/drain (repr.)", [0.95, 0.78, 0.35, 1]]]),
      hud,
      motionScope: "static geometry; electron count/drift = model drain current at this V_gs (representation)"
    }), { stream: "cnt_transfer_sweep" }));
  }
}

function nodeVoltages(name, inputs) {
  const topo = visualTopology(name);
  const nodes = {};
  topo.inputs.forEach((label, index) => { nodes[label] = inputs[index]; });
  for (const stage of topo.stages) {
    const a = nodes[stage.inputs[0]], b = nodes[stage.inputs[1]];
    nodes[stage.output] = stage.primitive === "INV" ? prim.INV(a, SEMI)
      : prim[stage.primitive](a, b, SEMI);
  }
  return { topo, nodes };
}

function emitCmosGates(ctx) {
  const fetGeo = helpers.cnt.roll(SEMI.n, SEMI.m, 1.3);
  const radius = fetGeo.radiusNm;
  let frame = 0;
  for (const def of GATE_DEFS) {
    const combos = 1 << def.arity;
    for (let c = 0; c < combos; c += 1) {
      const ins = [];
      for (let b = 0; b < def.arity; b += 1) ins.push((c >> b) & 1);
      const { topo, nodes } = nodeVoltages(def.name, ins);
      const positions = [], colors = [], radii = [], bonds = [], apparatus = [];
      const stageGap = 7.0, railY = 6.2;
      const width = (topo.stages.length - 1) * stageGap;
      const nodePos = {};
      topo.stages.forEach((stage, si) => { nodePos[stage.output] = [si * stageGap - width / 2, 0, 0]; });
      const addFet = (fet, at) => {
        const g = fetG(fet.type, nodes[fet.gate], SEMI);
        const glow = Math.max(0, Math.min(1, (Math.log10(g) + Math.log10(SEMI.on_off_ratio)) /
                                             Math.log10(SEMI.on_off_ratio)));
        const base = positions.length;
        for (const q of fetGeo.atoms) {
          positions.push([q[0] + at[0], q[2] + at[1] - fetGeo.lengthNm / 2, q[1] + at[2]]);
          colors.push(glowRgba(glow)); radii.push(0.07);
        }
        for (const bnd of fetGeo.bonds) bonds.push([base + bnd[0], base + bnd[1]]);
        apparatus.push({ shape: "box", center: [at[0] - radius - 0.35, at[1], at[2]],
                         size: [0.22, fetGeo.lengthNm * 0.8, 2 * radius],
                         color_rgba: fet.type === "p" ? [1.0, 0.5, 0.75, 0.8] : [0.5, 0.9, 0.5, 0.8],
                         label: fet.type + "-FET gate (" + fet.gate + ")" });
      };
      topo.stages.forEach((stage, si) => {
        const out = nodePos[stage.output];
        const network = (branches, sign) => {
          branches.forEach((branch, bi) => {
            const z = (bi - (branches.length - 1) / 2) * 2.6;
            let prev = [out[0], out[1], out[2]];
            const step = (railY - 1.0) / branch.length;
            branch.forEach((fet, fi) => {
              const centre = [out[0], sign * (1.0 + step * (fi + 0.5)), z];
              apparatus.push({ shape: "segment", from: prev,
                               to: [centre[0], centre[1] - sign * fetGeo.lengthNm / 2, z],
                               color_rgba: [0.75, 0.75, 0.8, 0.8] });
              addFet(fet, centre);
              prev = [centre[0], centre[1] + sign * fetGeo.lengthNm / 2, z];
            });
            apparatus.push({ shape: "segment", from: prev, to: [out[0], sign * railY, z],
                             color_rgba: [0.75, 0.75, 0.8, 0.8] });
          });
        };
        network(stage.pull_up, 1);
        network(stage.pull_down, -1);
        const v = nodes[stage.output];
        apparatus.push({ shape: "sphere", center: out, radius: 0.55, color_rgba: voltRgba(v),
                         label: stage.output });
      });
      apparatus.push({ shape: "box", center: [0, railY + 0.2, 0], size: [width + 5, 0.3, 7],
                       color_rgba: [1.0, 0.35, 0.3, 0.55], label: "Vdd rail" });
      apparatus.push({ shape: "box", center: [0, -railY - 0.2, 0], size: [width + 5, 0.3, 7],
                       color_rgba: [0.3, 0.45, 1.0, 0.55], label: "GND rail" });
      const vout = nodes[topo.output];
      const ok = level(vout) === (def.ref.apply(null, ins) & 1);
      ctx.emit("material_frame", Object.assign(OBS.frame({
        physicalTimeS: frame, playbackTimeS: frame,
        clockText: def.name + " gate, truth row " + (c + 1) + "/" + combos,
        phase: "static CMOS from (" + SEMI.n + "," + SEMI.m + ") CNTFETs (resistive-divider model)",
        lengthUnit: "nm", upAxis: "y", digits: 3,
        positions, colors, radii, bonds, apparatus,
        legend: OBS.legend([["FET off", CARBON_OFF.concat([1])], ["FET on", CARBON_ON.concat([1])],
                            ["node 0 V", voltRgba(0)], ["node Vdd", voltRgba(1)]]),
        hud: [
          topo.inputs.map((label, index) => label + "=" + ins[index]).join("  ") + "  ->  " +
            topo.output + " = " + level(vout) + "   (V_out = " + (vout * VDD).toFixed(3) + " V)",
          (ok ? "matches" : "DOES NOT match") + " the canonical " + def.name + " truth table   " +
            topo.stages.length + " stage(s), on/off " + SEMI.on_off_ratio.toExponential(1)
        ],
        motionScope: "static netlist; glow = FET conductance, node colour = evaluated voltage"
      }), { stream: "cnt_cmos_gates" }));
      frame += 1;
    }
  }
}

function ensureState(ctx) {
  if (!ctx.state || typeof ctx.state !== "object") return null;
  if (!ctx.state.initialized) {
    ctx.state.geant4 = {
      events: 0, totalEdepMeV: 0.0, totalTrackLengthMm: 0.0, totalStepCount: 0
    };
    ctx.state.initialized = true;
  }
  return ctx.state;
}

globalThis.TRECH_HOOKS = {
  onInit(ctx) {
    // Device-level physics (deterministic, Geant4-independent): the band
    // structure -> Fermi-statistics switching of the chosen channel.
    ctx.emit("cnt_device", {
      kind: "cnt_logic_device",
      model: "tight-binding zone-folding gap -> Fermi-Dirac CNTFET switching, hook-layer; "
        + "Geant4 transports electrons but does not compute band structure / Fermi level",
      temperature_K: TEMPERATURE_K,
      kT_eV: round4(KT_EV),
      vdd_V: VDD, v_th_V: V_TH, ideality: IDEALITY,
      devices: [SEMI, METAL, QUASI],
      visual_topologies: GATE_DEFS.map((g) => visualTopology(g.name)),
      visual_source: {
        topology: "serialized from the same primitive static-CMOS pull-up/pull-down networks used by the evaluator",
        tube_geometry: "working-device chirality and diameter; Geant4 channel is the representative (16,0) volume",
        pubchem: "not_applicable_for_cnt_chirality_track"
      },
      transfer: transferCurve(SEMI),
      temperature_sweep: temperatureSweep(SEMI.n, SEMI.m),
      references: {
        subthreshold_swing: "SS = ln(10) kT/q ~ 60 mV/decade at 300 K (Fermi-Dirac limit)",
        on_off_vs_gap: "on/off ~ exp(E_g/2kT); metallic (E_g~0) cannot switch off",
        manufacturing: "metallic tubes short the channel (docs/CNT/BackToTheCarbon.md)"
      }
    });
    return { override: { system: { ensemble: "cnt_logic_gates" } } };
  },

  onRunStart(ctx) {
    ensureState(ctx);
  },

  onEventEnd(ctx) {
    const state = ensureState(ctx);
    if (!state || !ctx.event) return;
    state.geant4.events += 1;
    state.geant4.totalEdepMeV += Math.max(0.0, ctx.event.edepMeV || 0.0);
    state.geant4.totalTrackLengthMm += Math.max(0.0, ctx.event.totalTrackLengthMm || 0.0);
    state.geant4.totalStepCount += Math.max(0.0, ctx.event.totalStepCount || 0.0);
  },

  onRunEnd(ctx) {
    const state = ctx.state;
    if (!state || !state.initialized) return;

    emitTransferSweep(ctx);
    emitCmosGates(ctx);

    // (1) gate truth tables for the working device and the metallic counterexample.
    const semiGates = gatePanel(SEMI);
    const metalGates = gatePanel(METAL);
    const quasiGates = gatePanel(QUASI);

    // (2) circuits on the working device, and the same circuits on the metallic
    // tube (to show the failure propagates through a real datapath).
    const semiHalf = evalHalfAdder(SEMI);
    const semiFull = evalFullAdder(SEMI);
    const semiRipple = evalRippleAdder2(SEMI);
    const metalFull = evalFullAdder(METAL);

    // (3) Fermi transfer / swing of the working device.
    const transfer = transferCurve(SEMI);
    const tSweep = temperatureSweep(SEMI.n, SEMI.m);

    // ---- validation -------------------------------------------------------
    const HEALTHY_RAIL = 0.05;     // clean rail: output within 5% of a supply
    const BROKEN_RAIL = 0.40;      // ambiguous: output stuck near Vdd/2

    const allGatesCorrect = semiGates.all_gates_correct;
    const semiWorstRail = Math.max(
      semiGates.worst_rail_closeness, semiHalf.worst_rail_closeness,
      semiFull.worst_rail_closeness, semiRipple.worst_rail_closeness);
    const halfAdderCorrect = semiHalf.all_ok;
    const fullAdderCorrect = semiFull.all_ok;
    const rippleAdderCorrect = semiRipple.all_ok;
    const noiseMarginHealthy = semiWorstRail < HEALTHY_RAIL;

    // The metallic tube must DESTROY the logic: outputs collapse toward Vdd/2
    // and at least one table is wrong.
    const metallicBreaksLogic =
      (!metalGates.all_gates_correct || !metalFull.all_ok) &&
      metalGates.worst_rail_closeness > BROKEN_RAIL;

    // Subthreshold swing on the ~60 mV/dec room-temperature Fermi limit.
    const ssIdeal = Math.LN10 * KT_EV * 1000.0;
    const swingNear60 = Math.abs(transfer.subthreshold_swing_mV_per_dec - ssIdeal) / ssIdeal < 0.03
      && transfer.subthreshold_swing_mV_per_dec > 55.0
      && transfer.subthreshold_swing_mV_per_dec < 65.0;

    // On/off ratio is gap-controlled: the semiconductor switches by >=1e3, and
    // it beats the metallic tube by >=1e3 (the Fermi-statistics gate-quality gap).
    const onOffGapControlled =
      SEMI.on_off_ratio >= 1.0e3 &&
      SEMI.on_off_ratio / METAL.on_off_ratio >= 1.0e3;

    // Fermi temperature trend: on/off falls and swing rises monotonically with T.
    let fermiTrendOk = true;
    for (let i = 1; i < tSweep.length; i++) {
      if (!(tSweep[i].on_off_ratio < tSweep[i - 1].on_off_ratio)) fermiTrendOk = false;
      if (!(tSweep[i].swing_mV_per_dec > tSweep[i - 1].swing_mV_per_dec)) fermiTrendOk = false;
    }

    const geant4DrivePresent =
      state.geant4.events === TOTAL_EVENTS &&
      state.geant4.totalStepCount > 0 &&
      state.geant4.totalTrackLengthMm > 0.0;

    const cntLogicGatesOk =
      allGatesCorrect && halfAdderCorrect && fullAdderCorrect && rippleAdderCorrect &&
      noiseMarginHealthy && metallicBreaksLogic && swingNear60 && onOffGapControlled &&
      fermiTrendOk && geant4DrivePresent;

    ctx.emit("cnt_gates_summary", {
      kind: "cnt_logic_gates",
      model: "static-CMOS CNTFET (tight-binding gap -> Fermi-Dirac on/off), hook-layer; "
        + "Geant4 transports electrons but does not compute the device physics",
      temperature_K: TEMPERATURE_K,
      kT_eV: round4(KT_EV),
      vdd_V: VDD, v_th_V: V_TH,
      working_device: SEMI,
      metallic_device: METAL,
      quasi_metallic_device: QUASI,
      gate_count: GATE_DEFS.length,
      visual_topologies: GATE_DEFS.map((g) => visualTopology(g.name)),
      visual_source: {
        topology: "serialized from the same primitive static-CMOS pull-up/pull-down networks used by the evaluator",
        tube_geometry: "working-device chirality and diameter; Geant4 channel is the representative (16,0) volume",
        geant4: "ctx.event transport metrics validate event drive; Geant4 does not synthesize CMOS topology",
        pubchem: "not_applicable_for_cnt_chirality_track"
      },
      semiconducting_gates: semiGates,
      metallic_gates: metalGates,
      quasi_metallic_gates: quasiGates,
      circuits: {
        half_adder: semiHalf,
        full_adder: semiFull,
        ripple_carry_adder_2bit: semiRipple,
        metallic_full_adder: metalFull
      },
      fermi: {
        transfer,
        temperature_sweep: tSweep,
        ideal_swing_mV_per_dec: round4(ssIdeal),
        semiconducting_on_off_ratio: SEMI.on_off_ratio,
        metallic_on_off_ratio: METAL.on_off_ratio,
        quasi_metallic_on_off_ratio: QUASI.on_off_ratio
      },
      geant4_event_drive: {
        events: state.geant4.events,
        total_edep_mev: state.geant4.totalEdepMeV,
        total_track_length_mm: state.geant4.totalTrackLengthMm,
        total_step_count: state.geant4.totalStepCount,
        channel_tube: SEMI.n + "," + SEMI.m,
        channel_diameter_nm: round4(channelDiameterNm)
      },
      references: {
        metallicity_rule: "(n-m) mod 3 == 0 => metallic (Saito/Dresselhaus 1998)",
        subthreshold_swing: "SS = ln(10) kT/q ~ 60 mV/decade at 300 K",
        manufacturing: "metallic tubes short the device (docs/CNT/BackToTheCarbon.md)"
      },
      validation: {
        all_gate_truth_tables_correct: allGatesCorrect,
        half_adder_correct: halfAdderCorrect,
        full_adder_correct: fullAdderCorrect,
        ripple_carry_adder_2bit_correct: rippleAdderCorrect,
        noise_margin_healthy: noiseMarginHealthy,
        metallic_tube_breaks_logic: metallicBreaksLogic,
        subthreshold_swing_near_60mV: swingNear60,
        on_off_ratio_gap_controlled: onOffGapControlled,
        fermi_temperature_trend: fermiTrendOk,
        geant4_event_drive_present: geant4DrivePresent,
        semiconducting_worst_rail_closeness: round4(semiWorstRail),
        cnt_logic_gates_ok: cntLogicGatesOk
      }
    });
  }
};

globalThis.TRECH_CONFIG = {
  detector: {
    worldSizeMm: units.mm(2.0),
    worldMaterial: helpers.materialAliases.air,
    temperatureK: TEMPERATURE_K, pressureAtm: 1.0
  },
  beam: { particle: "e-", energyMeV: 0.5, direction: [1, 0, 0] },
  run: { nEvents: TOTAL_EVENTS, seed: 424242, threads: 1 },
  determinism: { mode: "strict" },
  system: {
    enable: true, mode: "steady_state", frame: "point_agnostic",
    ensemble: "cnt_logic_gates"
  },
  materials: [cntMaterial],
  geometry: {
    volumes: [
      geometry.containerBox({
        name: "cnt_container",
        sizeMm: [units.mm(1.0), units.mm(1.0), units.mm(1.0)],
        tags: ["container", "cnt"]
      }),
      geometry.tubeVolume({
        name: "cnt_channel_16_0",
        material: "cnt_carbon",
        innerRadiusMm: innerRadiusMm, outerRadiusMm: outerRadiusMm,
        lengthMm: units.nm(50.0), parent: "cnt_container", scoreEdep: true,
        tags: ["carbon_nanotube", "semiconducting", "cntfet_channel"]
      })
    ]
  },
  hooks: {
    maxStepCallbacks: 0,
    maxEmitsPerCallback: 256,
    maxEmitPayloadBytes: 1048576
  }
};
