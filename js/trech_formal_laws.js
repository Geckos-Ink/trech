// Classic JavaScript side of the optional Lean law pairs (docs/engine/formal_laws.md).
//
// Each law here is a closed-form REFERENCE for validation companions (`<name>.validation.js`)
// and analytic cross-checks: physics for comparison, fed from Geant4's own data, never a
// driver of scenario behaviour. Each carries the Lean declaration that states it
// (formal/Trech/...). Lean is optional: these classic functions are what runs, and the
// checks below return records that name the Lean pair without claiming its proof was checked.
//
// Pairs: formal/laws.json. Lean: formal/Trech/Laws/Compton.lean, formal/Trech/Laws/Attenuation.lean.
(function () {
  "use strict";
  if (globalThis.TRECH_FORMAL_LAWS) {
    if (typeof module === "object" && module.exports) module.exports = globalThis.TRECH_FORMAL_LAWS;
    return;
  }
  // Engine trace channel (docs/engine/engine_trace.md), silent unless tracing is on.
  const trace = (globalThis.TRECH_TRACE || (typeof require === "function" ? require("./trech_trace.js") : null) ||
    {channel: () => ({info() {}, log() {}, debug() {}, trace() {}, count() {}, enabled: () => false,
      span: (name, fn) => fn()})}).channel("formal_laws");
  // Values from this module come from an authored law (physics for comparison), not from the engine.
  const authored = (globalThis.TRECH_TRACE && globalThis.TRECH_TRACE.authored) || function () {};

  function number(value, label) {
    const x = Number(value);
    if (!Number.isFinite(x)) throw new Error("formal law input " + label + " is not finite");
    return x;
  }

  // Compton kinematics on a free electron at rest; eps = E / (m_e c^2), cosTheta = cos(theta).
  // Mirrors include/trech/sim/KleinNishina.hpp.
  const compton = {
    lean: {
      scatteredEnergyRatio: "Trech.Laws.Compton.scatteredEnergyRatio",
      transferFraction: "Trech.Laws.Compton.transferFraction",
      edgeFraction: "Trech.Laws.Compton.edgeFraction",
      transferBound: "Trech.Laws.Compton.transferFraction_le_edge",
    },
    scatteredEnergyRatio(eps, cosTheta) {
      authored("formal_laws.compton");
      const e = number(eps, "eps"), c = number(cosTheta, "cosTheta");
      return 1.0 / (1.0 + e * (1.0 - c));
    },
    transferFraction(eps, cosTheta) {
      return 1.0 - compton.scatteredEnergyRatio(eps, cosTheta);
    },
    edgeFraction(eps) {
      authored("formal_laws.compton");
      const e = number(eps, "eps");
      return e > 0 ? 2.0 * e / (1.0 + 2.0 * e) : 0.0;
    },
  };

  // Beer-Lambert survival exp(-mu x): probability of crossing a path x without interacting.
  // Mirrors the beer_lambert analytic cross-check in src/sim/AnalyticCrossCheck.cpp.
  const attenuation = {
    lean: {
      survival: "Trech.Laws.Attenuation.survival",
      memoryless: "Trech.Laws.Attenuation.survival_add",
    },
    survival(mu, x) {
      authored("formal_laws.attenuation");
      return Math.exp(-(number(mu, "mu") * number(x, "x")));
    },
  };

  function neumaier(values) {
    let sum = 0, carry = 0;
    for (const v of values) {
      const x = Number(v), t = sum + x;
      carry += Math.abs(sum) >= Math.abs(x) ? (sum - t) + x : (x - t) + sum;
      sum = t;
    }
    return sum + carry;
  }

  function record(law, lean, kind, tolerance) {
    return {law, lean_declaration: lean, lean_status: "not_checked_by_this_check", role: "validation",
            kind, samples: 0, violations: 0, max_abs_error: 0, tolerance, passed: false, detail: ""};
  }
  function violate(r, error, what) {
    r.violations += 1;
    if (!(error <= r.max_abs_error)) r.max_abs_error = error;
    if (!r.detail) r.detail = what;
  }
  function done(r) {
    r.passed = r.violations === 0 && Number.isFinite(r.max_abs_error);
    if (!r.passed) trace.info("law check failed", {law: r.law, detail: r.detail});
    return r;
  }

  // Invariant: lower[i] - tol <= values[i] <= upper[i] + tol (same contract as the C++
  // trech::formal::checkWithinBounds).
  function checkWithinBounds(law, lean, values, lower, upper, tolerance) {
    const r = record(law, lean, "invariant", tolerance);
    if (values.length !== lower.length || values.length !== upper.length) {
      violate(r, 0, "bound arrays do not match the sample count");
      return done(r);
    }
    r.samples = values.length;
    values.forEach((v, i) => {
      const error = Math.max(0, lower[i] - v, v - upper[i]);
      if (!Number.isFinite(v) || error > tolerance) violate(r, Number.isFinite(v) ? error : NaN,
        "sample " + i + " = " + v + " outside [" + lower[i] + ", " + upper[i] + "]");
      else if (error > r.max_abs_error) r.max_abs_error = error;
    });
    return done(r);
  }

  // Invariant: |sum(after) - sum(before)| <= tol * max(1, |sum(before)|).
  function checkConservedTotal(law, lean, before, after, relativeTolerance) {
    const r = record(law, lean, "invariant", relativeTolerance);
    r.samples = 1;
    const b = neumaier(before), a = neumaier(after);
    const error = Math.abs(a - b) / Math.max(1, Math.abs(b));
    if (!(error <= relativeTolerance)) violate(r, error, "total " + b + " became " + a);
    else r.max_abs_error = error;
    return done(r);
  }

  // Agreement between two classic implementations (or a classic one and a reference table).
  function checkAgreement(law, lean, a, b, absTolerance, relTolerance) {
    const r = record(law, lean, "agreement", absTolerance);
    if (relTolerance) r.relative_tolerance = relTolerance;  // as the C++ record: only when nonzero
    if (a.length !== b.length) {
      violate(r, 0, "implementations returned different sample counts");
      return done(r);
    }
    r.samples = a.length;
    a.forEach((x, i) => {
      const error = Math.abs(x - b[i]);
      if (!(error <= absTolerance + relTolerance * Math.max(Math.abs(x), Math.abs(b[i]))))
        violate(r, error, "sample " + i + ": " + x + " vs " + b[i]);
      else if (error > r.max_abs_error) r.max_abs_error = error;
    });
    return done(r);
  }

  // The Compton bound 0 <= T/E <= edge over an (eps, cosTheta) grid, plus equality at
  // back-scatter: the classic functions against Trech.Laws.Compton.transferFraction_le_edge and
  // transferFraction_backscatter.
  function checkComptonBounds(epsValues, cosValues, tolerance) {
    const values = [], lower = [], upper = [], back = [], edges = [];
    for (const eps of epsValues) {
      const edge = compton.edgeFraction(eps);
      for (const c of cosValues) {
        values.push(compton.transferFraction(eps, c));
        lower.push(0);
        upper.push(edge);
      }
      back.push(compton.transferFraction(eps, -1));
      edges.push(edge);
    }
    return [
      checkWithinBounds("compton.transfer_within_edge", compton.lean.transferBound, values, lower, upper, tolerance),
      checkAgreement("compton.edge_at_backscatter", "Trech.Laws.Compton.transferFraction_backscatter",
        back, edges, tolerance, tolerance),
    ];
  }

  // Memorylessness survival(x + y) = survival(x) survival(y): the classic exp against
  // Trech.Laws.Attenuation.survival_add.
  function checkAttenuationMemoryless(mu, pairs, tolerance) {
    const joint = pairs.map(([x, y]) => attenuation.survival(mu, x + y));
    const split = pairs.map(([x, y]) => attenuation.survival(mu, x) * attenuation.survival(mu, y));
    return checkAgreement("attenuation.memoryless", attenuation.lean.memoryless, joint, split, 0, tolerance);
  }

  // Invariant: every entry finite and >= -tol, and |sum - 1| <= tol (C++ checkProbabilityVector).
  function checkProbabilityVector(law, lean, probabilities, tolerance) {
    const r = record(law, lean, "invariant", tolerance);
    r.samples = probabilities.length;
    let sum = 0;
    probabilities.forEach((p, i) => {
      if (!Number.isFinite(p) || p < -tolerance) violate(r, Number.isFinite(p) ? -p : NaN, "entry " + i + " = " + p);
      sum += p;
    });
    const error = Math.abs(neumaier(probabilities) - 1);
    if (!(error <= tolerance)) violate(r, error, "sum " + sum + " is not 1");
    else if (error > r.max_abs_error) r.max_abs_error = error;
    return done(r);
  }

  // Records checks made by this module in the run's outputs: `law_checks` in the run_end scores
  // and the provenance `formal` object, with origin "validation". Call it only from a
  // `.validation.js` companion. Only records built by the check functions above are accepted.
  // Outside a TRECH host (Node, Studio) nothing is recorded and it returns 0; recording never
  // changes physics, RNG or emits.
  function recordChecks(checks) {
    const list = Array.isArray(checks) ? checks : [checks];
    const sink = globalThis.__TRECH_FORMAL_RECORD;
    let recorded = 0;
    for (const c of list) {
      if (!c || typeof c !== "object" || c.role !== "validation" || c.lean_status !== "not_checked_by_this_check" ||
          typeof c.law !== "string" || !c.law) {
        throw new TypeError("TRECH_FORMAL_LAWS.record accepts only records made by its check functions");
      }
      if (typeof sink === "function" && sink(JSON.stringify(c))) recorded += 1;
    }
    return recorded;
  }

  const api = {
    schema: "trech_formal_laws_js_v1",
    compton, attenuation,
    checkWithinBounds, checkConservedTotal, checkAgreement, checkProbabilityVector,
    checkComptonBounds, checkAttenuationMemoryless,
    record: recordChecks,
  };
  globalThis.TRECH_FORMAL_LAWS = api;
  if (typeof module === "object" && module.exports) module.exports = api;
})();
