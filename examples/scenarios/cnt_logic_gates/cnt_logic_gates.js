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
//   5. GATES -> MEMORY. Feedback turns gates into state. A cross-coupled NOR
//      SR latch, a master-slave D flip-flop (two NAND gated-D latches on
//      opposite clock phases) and a 2-bit synchronous counter (two flip-flops
//      with INV/XOR next-state logic) are solved as feedback netlists: every
//      node is relaxed (Gauss-Seidel) to the DC fixed point of the same
//      resistive-divider gates, starting from the previous phase's node
//      voltages -- that carried-over state IS the memory. A clock waveform with
//      data glitches while the clock is high/low checks edge triggering.
//
//   6. TUBES -> YIELD. Growth gives a chirality POPULATION, not one tube. Every
//      (n,m) of a diameter-selective distribution is graded with the same gate
//      panel; circuits are then built with an independently drawn tube in every
//      FET slot and evaluated by the same netlist (seeded Monte Carlo), over a
//      sorted-semiconducting-purity sweep. The unsorted ~1/3 metallic fraction
//      kills a 50-FET full adder; ~99.99% purity is needed for a 99% 2-bit adder.
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
//   trech run examples/scenarios/cnt_logic_gates/cnt_logic_gates.js \
//        --events 8 --output build/dev/out_cnt_logic_gates

TRECH_INCLUDE("../../../js/trech_helpers.js");
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
  // Read the ratio once per FET, on or off: a mixed-tube slot device (see the
  // chirality-yield panel) hands every FET its own tube in evaluation order.
  const ratio = dev.on_off_ratio;
  const high = vIn > 0.5;
  const on = (type === "n") ? high : !high;
  return on ? 1.0 : 1.0 / ratio;
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

const { round4 } = helpers.math;

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

// ---- sequential logic: feedback netlists relaxed to their DC fixed point ---
// A node is {name, fn(v, dev) -> voltage}. Nodes are updated in order using the
// newest values (Gauss-Seidel), so cross-coupled pairs settle instead of
// ringing as a synchronous update would. Hard-threshold FET switching makes the
// fixed point exact; a netlist that does not settle is reported, not hidden.
const SEQ_TOLERANCE = 1.0e-12;
const SEQ_MAX_SWEEPS = 64;

function solveNetlist(nodes, v, dev) {
  for (let sweep = 1; sweep <= SEQ_MAX_SWEEPS; sweep++) {
    let delta = 0.0;
    for (const node of nodes) {
      const next = node.fn(v, dev);
      const prev = v[node.name] === undefined ? 0.0 : v[node.name];
      delta = Math.max(delta, Math.abs(next - prev));
      v[node.name] = next;
    }
    if (delta < SEQ_TOLERANCE) return { converged: true, sweeps: sweep };
  }
  return { converged: false, sweeps: SEQ_MAX_SWEEPS };
}

function worstNodeRail(nodes, v) {
  let worst = 0.0;
  for (const node of nodes) worst = Math.max(worst, railCloseness(v[node.name]));
  return worst;
}

// Cross-coupled NOR SR latch: Q = NOR(R, Qb), Qb = NOR(S, Q).
const SR_LATCH_NODES = [
  { name: "q", fn: (v, d) => prim.NOR2(v.r, v.qb, d) },
  { name: "qb", fn: (v, d) => prim.NOR2(v.s, v.q, d) }
];

function evalSrLatch(dev) {
  const rows = [];
  let allOk = true, allConverged = true, worst = 0.0;
  const holdQ = {};
  // Every (stored state, S, R) combination except the forbidden S = R = 1.
  for (const stored of [0, 1]) {
    for (const [sIn, rIn] of [[0, 0], [1, 0], [0, 1]]) {
      const v = { s: sIn, r: rIn, q: stored, qb: 1 - stored };
      const solved = solveNetlist(SR_LATCH_NODES, v, dev);
      const ref = sIn ? 1 : (rIn ? 0 : stored);
      const q = level(v.q);
      const complementary = level(v.qb) === 1 - q;
      const ok = solved.converged && q === ref && complementary;
      if (!ok) allOk = false;
      if (!solved.converged) allConverged = false;
      worst = Math.max(worst, worstNodeRail(SR_LATCH_NODES, v));
      if (!sIn && !rIn) holdQ[stored] = v.q;
      rows.push({ stored, S: sIn, R: rIn, q, ref, q_voltage: round4(v.q),
                  qb_voltage: round4(v.qb), sweeps: solved.sweeps, ok });
    }
  }
  // Memory = two distinct stable states under identical inputs (S = R = 0).
  const separation = Math.abs(holdQ[1] - holdQ[0]);
  return { name: "sr_latch_nor", rows, all_ok: allOk, converged: allConverged,
           hold_state_separation: round4(separation), bistable: separation > 0.5,
           worst_rail_closeness: round4(worst) };
}

// NAND gated-D latch, transparent while `enable` is high.
function dLatchNodes(prefix, dName, enableName) {
  return [
    { name: prefix + "dn", fn: (v, d) => prim.INV(v[dName], d) },
    { name: prefix + "sb", fn: (v, d) => prim.NAND2(v[dName], v[enableName], d) },
    { name: prefix + "rb", fn: (v, d) => prim.NAND2(v[prefix + "dn"], v[enableName], d) },
    { name: prefix + "q", fn: (v, d) => prim.NAND2(v[prefix + "sb"], v[prefix + "qb"], d) },
    { name: prefix + "qb", fn: (v, d) => prim.NAND2(v[prefix + "rb"], v[prefix + "q"], d) }
  ];
}

// Positive-edge master-slave D flip-flop: the master follows D while the clock
// is low, the slave copies the master while it is high.
function dFlipFlopNodes(prefix, dName, clkName) {
  const clkN = prefix + "clkn";
  return [{ name: clkN, fn: (v, d) => prim.INV(v[clkName], d) }]
    .concat(dLatchNodes(prefix + "m_", dName, clkN))
    .concat(dLatchNodes(prefix + "s_", prefix + "m_q", clkName));
}

function resetFlipFlop(v, prefix) {
  for (const latch of ["m_", "s_"]) {
    v[prefix + latch + "q"] = 0.0;
    v[prefix + latch + "qb"] = 1.0;
    v[prefix + latch + "sb"] = 1.0;
    v[prefix + latch + "rb"] = 1.0;
  }
}

const DFF_DATA = [1, 0, 1, 1, 0, 0, 1, 0];

// Each clock cycle: D settles while CLK is low, CLK rises (capture), D glitches
// to its complement while CLK is high and again after CLK falls. Q must take
// D only at the rising edge and ignore both glitches.
function evalDFlipFlop(dev) {
  const nodes = dFlipFlopNodes("ff_", "d", "clk");
  const v = { d: 0, clk: 0 };
  resetFlipFlop(v, "ff_");
  const phases = [];
  let allOk = true, allConverged = true, worst = 0.0, expected = 0, glitchesRejected = 0;
  for (let k = 0; k < DFF_DATA.length; k++) {
    const bit = DFF_DATA[k];
    const steps = [
      { clk: 0, d: bit, phase: "setup", ref: expected },
      { clk: 1, d: bit, phase: "rising_edge", ref: bit },
      { clk: 1, d: 1 - bit, phase: "glitch_clock_high", ref: bit },
      { clk: 0, d: 1 - bit, phase: "glitch_clock_low", ref: bit }
    ];
    for (const step of steps) {
      v.clk = step.clk;
      v.d = step.d;
      const solved = solveNetlist(nodes, v, dev);
      const q = level(v.ff_s_q);
      const ok = solved.converged && q === step.ref;
      if (!ok) allOk = false;
      if (!solved.converged) allConverged = false;
      if (ok && step.phase.indexOf("glitch") === 0) glitchesRejected += 1;
      worst = Math.max(worst, worstNodeRail(nodes, v));
      phases.push({ cycle: k, phase: step.phase, clk: step.clk, d: step.d, q, ref: step.ref,
                    q_voltage: round4(v.ff_s_q), sweeps: solved.sweeps, ok });
    }
    expected = bit;
  }
  return { name: "d_flip_flop_master_slave", data: DFF_DATA, phases, all_ok: allOk,
           converged: allConverged, glitches_rejected: glitchesRejected,
           glitches_applied: 2 * DFF_DATA.length, worst_rail_closeness: round4(worst) };
}

// 2-bit synchronous counter: D0 = NOT Q0, D1 = Q1 XOR Q0, one shared clock.
const COUNTER_EDGES = 9;

function evalCounter2(dev) {
  const nodes = [
    { name: "d0", fn: (v, d) => prim.INV(v.b0_s_q, d) },
    { name: "d1", fn: (v, d) => logic.XOR(v.b1_s_q, v.b0_s_q, d) }
  ].concat(dFlipFlopNodes("b0_", "d0", "clk"))
   .concat(dFlipFlopNodes("b1_", "d1", "clk"));
  const v = { clk: 0, d0: 1, d1: 0 };
  resetFlipFlop(v, "b0_");
  resetFlipFlop(v, "b1_");
  const counts = [];
  let allOk = true, allConverged = true, worst = 0.0;
  for (let edge = 1; edge <= COUNTER_EDGES; edge++) {
    for (const clk of [0, 1]) {
      v.clk = clk;
      const solved = solveNetlist(nodes, v, dev);
      if (!solved.converged) allConverged = false;
      worst = Math.max(worst, worstNodeRail(nodes, v));
    }
    const value = level(v.b0_s_q) + 2 * level(v.b1_s_q);
    const ref = edge % 4;
    const ok = value === ref;
    if (!ok) allOk = false;
    counts.push({ edge, value, ref, ok });
  }
  return { name: "counter_2bit_synchronous", counts, all_ok: allOk && allConverged,
           converged: allConverged, worst_rail_closeness: round4(worst) };
}

function sequentialPanel(dev) {
  const srLatch = evalSrLatch(dev);
  const dFlipFlop = evalDFlipFlop(dev);
  const counter = evalCounter2(dev);
  return {
    device: dev.label,
    sr_latch: srLatch,
    d_flip_flop: dFlipFlop,
    counter_2bit: counter,
    all_correct: srLatch.all_ok && dFlipFlop.all_ok && counter.all_ok,
    worst_rail_closeness: round4(Math.max(srLatch.worst_rail_closeness,
      dFlipFlop.worst_rail_closeness, counter.worst_rail_closeness))
  };
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
// ---- chirality-distribution yield: a grown tube population -> working circuits ----
// Growth does not pick one chirality. A diameter-selective growth gives every
// (n,m) whose diameter falls in the distribution a weight (chiral tubes twice:
// left and right handed). Each tube is built into the SAME gate panel as the
// working device and is "usable" only if every gate is correct with clean rails.
// A circuit is then assembled with an independent tube drawn for every FET slot
// (the slot device below) and evaluated with the same divider netlist -- so the
// Monte-Carlo yield comes from the circuit model, while p_usable^N (all slots
// usable) is only a lower bound it must respect. Sorting is modelled as a purity
// knob: semiconducting tubes keep their relative weights and make up `purity`.
const YIELD_HEALTHY_RAIL = 0.05;       // same clean-rail limit as the gate checks
const YIELD_GROWTH = { label: "diameter_selective_cvd", mean_diameter_nm: 1.2, sigma_diameter_nm: 0.15 };
const YIELD_PURITIES = [0.9, 0.99, 0.999];
const YIELD_TRIALS = 400;
const YIELD_SEED = 20261111;
const YIELD_TARGET = 0.99;             // circuit yield the required purity aims for

function chiralityPopulation(growth) {
  const mean = growth.mean_diameter_nm, sigma = growth.sigma_diameter_nm;
  const dMin = Math.max(0.3, mean - 4 * sigma), dMax = mean + 4 * sigma;
  const tubes = [];
  let total = 0.0;
  for (let n = 1; DIAM_PREFACTOR * n <= dMax; n++) {
    for (let m = 0; m <= n; m++) {
      const d = DIAM_PREFACTOR * Math.sqrt(n * n + n * m + m * m);
      if (d < dMin || d > dMax) continue;
      const handedness = (m === 0 || m === n) ? 1 : 2;
      const weight = handedness * Math.exp(-0.5 * Math.pow((d - mean) / sigma, 2));
      const dev = makeDevice("tube_" + n + "_" + m, n, m);
      const panel = gatePanel(dev);
      tubes.push({
        n, m, diameter_nm: d, metallic: dev.metallic,
        quasi_metallic: dev.metallic && dev.band_gap_eV > 0,
        band_gap_eV: dev.band_gap_eV, on_off_ratio: dev.on_off_ratio,
        gates_correct: panel.all_gates_correct,
        worst_rail_closeness: panel.worst_rail_closeness,
        usable: panel.all_gates_correct && panel.worst_rail_closeness < YIELD_HEALTHY_RAIL,
        weight
      });
      total += weight;
    }
  }
  for (const t of tubes) t.weight /= total;
  return tubes;
}

// Re-weight the population to a sorted semiconducting purity.
function sortedWeights(tubes, purity) {
  let semi = 0.0;
  for (const t of tubes) if (!t.metallic) semi += t.weight;
  return tubes.map((t) => t.metallic ? t.weight * (1 - purity) / (1 - semi)
                                     : t.weight * purity / semi);
}

function fetCountOf(name) {
  let count = 0;
  for (const stage of visualTopology(name).stages) {
    for (const branch of stage.pull_up.concat(stage.pull_down)) count += branch.length;
  }
  return count;
}

// A device whose on/off ratio advances one slot per FET read, so every
// transistor of a circuit gets its own drawn tube; reset() before each row
// keeps slot k on the same physical FET across the truth table.
function slotDevice(ratios) {
  let k = 0;
  return {
    label: "mixed_tube_slots",
    reset() { k = 0; },
    reads() { return k; },
    get on_off_ratio() { const r = ratios[k % ratios.length]; k += 1; return r; }
  };
}

function drawIndex(cumulative, u) {
  let lo = 0, hi = cumulative.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (cumulative[mid] < u) lo = mid + 1; else hi = mid;
  }
  return lo;
}

// Full adder with one drawn tube per FET slot: works iff every row is correct
// with clean rails. Also returns how many FET reads one row made.
function fullAdderWithSlots(ratios) {
  const dev = slotDevice(ratios);
  let works = true, readsPerRow = -1, readsConsistent = true;
  for (let a = 0; a < 2; a++) {
    for (let b = 0; b < 2; b++) {
      for (let cin = 0; cin < 2; cin++) {
        dev.reset();
        const trace = [];
        const r = fullAdder(a, b, cin, dev, trace);
        const total = a + b + cin;
        if (r.sum !== (total & 1) || r.cout !== ((total >> 1) & 1)) works = false;
        for (const rc of trace) if (rc >= YIELD_HEALTHY_RAIL) works = false;
        if (readsPerRow < 0) readsPerRow = dev.reads();
        else if (dev.reads() !== readsPerRow) readsConsistent = false;
      }
    }
  }
  return { works, readsPerRow, readsConsistent };
}

function chiralityYieldPanel() {
  const tubes = chiralityPopulation(YIELD_GROWTH);
  let metallic = 0.0, quasi = 0.0, usable = 0.0, semi = 0.0, semiUsable = 0.0;
  let metallicUsableCount = 0;
  for (const t of tubes) {
    if (t.metallic) metallic += t.weight; else semi += t.weight;
    if (t.quasi_metallic) quasi += t.weight;
    if (t.usable) { usable += t.weight; if (!t.metallic) semiUsable += t.weight; }
    if (t.metallic && t.usable) metallicUsableCount += 1;
  }
  const usableAmongSemi = semiUsable / semi;
  const usableAmongMetal = metallic > 0 ? (usable - semiUsable) / metallic : 0.0;
  const pUsable = (purity) => purity * usableAmongSemi + (1 - purity) * usableAmongMetal;

  const gateFets = {};
  for (const g of GATE_DEFS) gateFets[g.name] = fetCountOf(g.name);
  const halfFets = gateFets.XOR + gateFets.AND;
  const fullFets = 2 * gateFets.XOR + 2 * gateFets.AND + gateFets.OR;
  const circuitFets = { half_adder: halfFets, full_adder: fullFets, ripple_carry_adder_2bit: 2 * fullFets };
  const boundsAt = (p) => {
    const out = {};
    for (const name of Object.keys(gateFets)) out[name] = Math.pow(p, gateFets[name]);
    for (const name of Object.keys(circuitFets)) out[name] = Math.pow(p, circuitFets[name]);
    return out;
  };

  const rng = helpers.random.mulberry32(YIELD_SEED);   // shared seeded sampler
  let fetCountConsistent = true, allUsableFailures = 0;
  const sweep = YIELD_PURITIES.map((purity) => {
    const weights = sortedWeights(tubes, purity);
    const cumulative = [];
    let acc = 0.0;
    for (const w of weights) { acc += w; cumulative.push(acc); }
    let works = 0, allUsableTrials = 0, toleratedBad = 0;
    for (let trial = 0; trial < YIELD_TRIALS; trial++) {
      const ratios = [];
      let allUsable = true;
      for (let s = 0; s < fullFets; s++) {
        const t = tubes[drawIndex(cumulative, rng() * acc)];
        ratios.push(t.on_off_ratio);
        if (!t.usable) allUsable = false;
      }
      const r = fullAdderWithSlots(ratios);
      if (!r.readsConsistent || r.readsPerRow !== fullFets) fetCountConsistent = false;
      if (allUsable) allUsableTrials += 1;
      if (r.works) works += 1;
      if (allUsable && !r.works) allUsableFailures += 1;
      if (!allUsable && r.works) toleratedBad += 1;
    }
    const p = pUsable(purity);
    const bound = Math.pow(p, fullFets);
    const mcYield = works / YIELD_TRIALS;
    const sigma = Math.max(Math.sqrt(bound * (1 - bound) / YIELD_TRIALS), 1 / YIELD_TRIALS);
    return {
      purity, p_usable: round4(p), full_adder_bound: round4(bound),
      full_adder_mc_yield: round4(mcYield), mc_sigma: round4(sigma),
      trials: YIELD_TRIALS, all_usable_trials: allUsableTrials,
      tolerated_bad_tube_trials: toleratedBad,
      mc_respects_bound: mcYield >= bound - 4 * sigma,
      circuit_bounds: boundsAt(p)
    };
  });

  const unsortedP = pUsable(semi);
  const unsortedBounds = boundsAt(unsortedP);
  const rippleFets = circuitFets.ripple_carry_adder_2bit;
  const pNeeded = Math.pow(YIELD_TARGET, 1 / rippleFets);
  const purityNeeded = usableAmongSemi > usableAmongMetal
    ? (pNeeded - usableAmongMetal) / (usableAmongSemi - usableAmongMetal) : null;

  let monotonic = true;
  for (let i = 1; i < sweep.length; i++) {
    if (!(sweep[i].full_adder_bound > sweep[i - 1].full_adder_bound)) monotonic = false;
    if (!(sweep[i].full_adder_mc_yield >= sweep[i - 1].full_adder_mc_yield)) monotonic = false;
  }
  const checks = {
    metallic_fraction_near_one_third: metallic > 0.30 && metallic < 0.37,
    no_metallic_tube_usable: metallicUsableCount === 0,
    usable_within_semiconducting: usable <= semi + 1e-12,
    fet_slot_count_consistent: fetCountConsistent,
    all_usable_draws_always_work: allUsableFailures === 0,
    mc_respects_independent_bound: sweep.every((s) => s.mc_respects_bound),
    yield_rises_with_purity: monotonic,
    unsorted_full_adder_fails: unsortedBounds.full_adder < 1.0e-3
  };
  const ok = Object.keys(checks).every((k) => checks[k]);
  return {
    model: "diameter-selective growth over every (n,m) in mean +/- 4 sigma, handedness-weighted; "
      + "each tube graded by the same static-CMOS gate panel; circuits built with one drawn tube "
      + "per FET slot and evaluated by the same divider netlist (hook-layer, not Geant4)",
    growth: YIELD_GROWTH,
    tube_count: tubes.length,
    metallic_fraction: round4(metallic),
    quasi_metallic_fraction: round4(quasi),
    semiconducting_fraction: round4(semi),
    usable_fraction: round4(usable),
    usable_fraction_among_semiconducting: round4(usableAmongSemi),
    gate_fet_counts: gateFets,
    circuit_fet_counts: circuitFets,
    unsorted_bounds: unsortedBounds,
    purity_sweep: sweep,
    target_yield: YIELD_TARGET,
    purity_needed_for_target_ripple_adder: purityNeeded === null ? null : Number(purityNeeded.toPrecision(8)),
    all_usable_failures: allUsableFailures,
    tubes: tubes.map((t) => ({ n: t.n, m: t.m, diameter_nm: round4(t.diameter_nm),
                               weight: Number(t.weight.toPrecision(6)), metallic: t.metallic,
                               quasi_metallic: t.quasi_metallic, usable: t.usable,
                               worst_rail_closeness: t.worst_rail_closeness })),
    checks,
    chirality_yield_ok: ok
  };
}

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
    ctx.emit("material_frame", TRECH_VIEWS["cnt_logic_gates"]["frame0"](CARBON_OFF, OBS, VDD, apparatus, bonds, charts, colors, hud, i, names, positions, radii, samples, tubes, vgs));
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
      ctx.emit("material_frame", TRECH_VIEWS["cnt_logic_gates"]["frame1"](CARBON_OFF, CARBON_ON, OBS, SEMI, VDD, apparatus, bonds, c, colors, combos, def, frame, ins, level, ok, positions, radii, topo, voltRgba, vout));
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

    // (2b) sequential logic (memory) on all three tubes.
    const semiSeq = sequentialPanel(SEMI);
    const metalSeq = sequentialPanel(METAL);
    const quasiSeq = sequentialPanel(QUASI);

    // (2c) manufacturing: a grown chirality population -> circuit yield.
    const chiralityYield = chiralityYieldPanel();
    const chiralityYieldOk = chiralityYield.chirality_yield_ok;

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

    // Memory: the working tube's latch is bistable, the flip-flop captures D
    // only on rising edges (rejecting every glitch) and the counter counts;
    // the metallic tube cannot hold a bit (no second stable state).
    const srLatchCorrect = semiSeq.sr_latch.all_ok && semiSeq.sr_latch.bistable;
    const dFlipFlopEdgeTriggered = semiSeq.d_flip_flop.all_ok &&
      semiSeq.d_flip_flop.glitches_rejected === semiSeq.d_flip_flop.glitches_applied;
    const counterCorrect = semiSeq.counter_2bit.all_ok;
    const sequentialNoiseHealthy = semiSeq.worst_rail_closeness < HEALTHY_RAIL;
    const metallicLosesMemory = !metalSeq.sr_latch.bistable && !metalSeq.all_correct;
    const sequentialLogicOk = srLatchCorrect && dFlipFlopEdgeTriggered && counterCorrect &&
      sequentialNoiseHealthy && metallicLosesMemory;

    const geant4DrivePresent =
      state.geant4.events === TOTAL_EVENTS &&
      state.geant4.totalStepCount > 0 &&
      state.geant4.totalTrackLengthMm > 0.0;

    const cntLogicGatesOk =
      allGatesCorrect && halfAdderCorrect && fullAdderCorrect && rippleAdderCorrect &&
      noiseMarginHealthy && metallicBreaksLogic && swingNear60 && onOffGapControlled &&
      fermiTrendOk && geant4DrivePresent && sequentialLogicOk && chiralityYieldOk;

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
      sequential: {
        model: "feedback netlists of the same static-CMOS divider gates, relaxed "
          + "(Gauss-Seidel) to the DC fixed point from the previous phase's node voltages",
        semiconducting: semiSeq,
        metallic: metalSeq,
        quasi_metallic: quasiSeq
      },
      chirality_yield: chiralityYield,
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
      validation: Object.assign(
        TRECH_CHECKS["cnt_logic_gates"]["checks0"](allGatesCorrect, cntLogicGatesOk, fermiTrendOk, fullAdderCorrect, geant4DrivePresent, halfAdderCorrect, metallicBreaksLogic, noiseMarginHealthy, onOffGapControlled, rippleAdderCorrect, round4, semiWorstRail, swingNear60),
        TRECH_CHECKS["cnt_logic_gates"]["checks1"](counterCorrect, dFlipFlopEdgeTriggered, metallicLosesMemory, round4, semiSeq, sequentialLogicOk, sequentialNoiseHealthy, srLatchCorrect),
        TRECH_CHECKS["cnt_logic_gates"]["checks2"](chiralityYield))
    });
  }
};

globalThis.TRECH_CONFIG = {
  environment: {
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
