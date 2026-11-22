// Helpers for ctx.learnDomains reports: compact emits, agreement between the
// engine's unlabelled response domains and a scenario's own labels, run-level
// accumulation of prequential errors, and applying a frozen learner's rates.
// The engine owns every statistical decision; nothing here learns.
(function () {
  // Engine trace channel (docs/engine/engine_trace.md), silent unless tracing is on. trech and the
  // Node model loader provide TRECH_TRACE, plain Node loads js/trech_trace.js, any other host
  // gets a no-op. Logging never changes a result.
  const trace = (globalThis.TRECH_TRACE || (typeof require === "function" ? require("./trech_trace.js") : null) ||
    {channel: () => ({info() {}, log() {}, debug() {}, trace() {}, count() {}, enabled: () => false,
      span: (name, fn) => fn()})}).channel("domain_learning");
  function agreement(domains, labels) {
    const table = new Map();
    const rows = new Map(), columns = new Map();
    let n = 0;
    for (let i = 0; i < domains.length; ++i) {
      const d = domains[i], l = labels[i];
      if (d === null || d === undefined || d < 0 || l === null || l === undefined) continue;
      const key = d + "\u0000" + l;
      table.set(key, (table.get(key) || 0) + 1);
      rows.set(d, (rows.get(d) || 0) + 1);
      columns.set(l, (columns.get(l) || 0) + 1);
      n += 1;
    }
    const contingency = {};
    for (const [key, count] of table) {
      const [d, l] = key.split("\u0000");
      (contingency[d] = contingency[d] || {})[l] = count;
    }
    return { elements: n, contingency, ...scores(contingency) };
  }

  // Purity, inverse purity and adjusted Rand index of a contingency table.
  function scores(contingency) {
    const choose2 = (k) => k * (k - 1) / 2;
    let n = 0, sumCells = 0, purity = 0;
    const columns = {};
    for (const row of Object.values(contingency)) {
      let rowTotal = 0, best = 0;
      for (const [label, count] of Object.entries(row)) {
        rowTotal += count;
        best = Math.max(best, count);
        sumCells += choose2(count);
        columns[label] = (columns[label] || 0) + count;
      }
      n += rowTotal;
      purity += best;
    }
    if (!n) return { purity: null, inverse_purity: null, ari: null };
    let inverse = 0;
    for (const label of Object.keys(columns)) {
      let best = 0;
      for (const row of Object.values(contingency)) best = Math.max(best, row[label] || 0);
      inverse += best;
    }
    let sumRows = 0, sumColumns = 0;
    for (const row of Object.values(contingency)) {
      sumRows += choose2(Object.values(row).reduce((a, b) => a + b, 0));
    }
    for (const count of Object.values(columns)) sumColumns += choose2(count);
    const expected = sumRows * sumColumns / Math.max(choose2(n), 1);
    const maximum = 0.5 * (sumRows + sumColumns);
    const ari = maximum === expected ? 1.0 : (sumCells - expected) / (maximum - expected);
    return { purity: purity / n, inverse_purity: inverse / n, ari };
  }

  function merge(into, contingency) {
    for (const [d, row] of Object.entries(contingency)) {
      const target = (into[d] = into[d] || {});
      for (const [l, count] of Object.entries(row)) target[l] = (target[l] || 0) + count;
    }
    return into;
  }

  // Keep tendencies that carry information: significant trends, and the
  // population/error series every domain has.
  function compactTendencies(tendencies, all) {
    const out = {};
    for (const [name, t] of Object.entries(tendencies || {})) {
      if (all || t.significant || name === "elements" || name === "error") out[name] = t;
    }
    return out;
  }

  function summarize(report, extra, options) {
    const all = !!(options && options.allTendencies);
    const out = Object.assign({}, extra || {}, {
      learner: report.name, call: report.call, time: report.time, frozen: report.frozen,
      features: report.features, targets: report.targets,
      scored: report.scored, extrapolated: report.extrapolated, seconds: report.seconds,
      metrics: report.metrics, events: report.events,
      tendencies: compactTendencies(report.tendencies, true),
      capacity: report.capacity, budget: report.budget,
      domains: report.domains.map((d) => Object.assign({}, d, {
        tendencies: compactTendencies(d.tendencies, all)
      }))
    });
    if (options && options.labels) out.agreement = agreement(report.elementDomains, options.labels);
    // A few raw rows for offline parity replay (NumPy twin of the engine).
    if (options && options.samples) {
      const n = Math.min(options.samples.count, report.predictionDomains.length);
      const head = (values) => Array.from(values).slice(0, n);
      out.samples = {
        features: Object.fromEntries(Object.entries(options.samples.features).map(([k, v]) => [k, head(v)])),
        predictions: Object.fromEntries(Object.entries(report.predictions).map(([k, v]) => [k, head(v)])),
        domains: head(report.predictionDomains)
      };
    }
    if (report.state) out.state = report.state;
    return out;
  }

  // Run-level prequential accumulator (sums of squares over every graded row).
  function accumulator() {
    return { calls: 0, scored: 0, routed: {}, pooled: {}, covered: {}, events: {}, contingency: {}, seconds: 0,
             perCall: [] };
  }

  function accumulate(acc, report, contingency) {
    acc.calls += 1;
    acc.seconds += report.seconds;
    acc.scored += report.scored;
    const record = { scored: report.scored, routed: {}, pooled: {} };
    for (const name of report.targets) {
      const r = report.metrics.routed_rmse[name], p = report.metrics.pooled_rmse[name];
      if (report.scored && r !== null && p !== null) {
        acc.routed[name] = (acc.routed[name] || 0) + r * r * report.scored;
        acc.pooled[name] = (acc.pooled[name] || 0) + p * p * report.scored;
        record.routed[name] = r * r * report.scored;
        record.pooled[name] = p * p * report.scored;
        const c = (report.metrics.interval_coverage || {})[name];
        if (c !== null && c !== undefined) acc.covered[name] = (acc.covered[name] || 0) + c * report.scored;
      }
    }
    acc.perCall.push(record);
    for (const e of report.events) acc.events[e.type] = (acc.events[e.type] || 0) + 1;
    if (contingency) merge(acc.contingency, contingency);
    return acc;
  }

  function finish(acc) {
    const rmse = (sums) => Object.fromEntries(Object.entries(sums).map(([k, v]) =>
      [k, acc.scored ? Math.sqrt(v / acc.scored) : null]));
    const routed = rmse(acc.routed), pooled = rmse(acc.pooled);
    const gain = {};
    for (const k of Object.keys(routed)) {
      gain[k] = pooled[k] > 0 ? 1 - routed[k] / pooled[k] : null;
    }
    // Steady state: the calls after the first tenth (the start-up transient,
    // when every domain is young), graded the same prequential way.
    const skip = Math.ceil(acc.perCall.length / 10);
    const late = { scored: 0, routed: {}, pooled: {} };
    acc.perCall.slice(skip).forEach((c) => {
      late.scored += c.scored;
      for (const [k, v] of Object.entries(c.routed)) late.routed[k] = (late.routed[k] || 0) + v;
      for (const [k, v] of Object.entries(c.pooled)) late.pooled[k] = (late.pooled[k] || 0) + v;
    });
    const lateRmse = (sums) => Object.fromEntries(Object.entries(sums).map(([k, v]) =>
      [k, late.scored ? Math.sqrt(v / late.scored) : null]));
    const steady = { skipped_calls: skip, scored: late.scored, routed_rmse: lateRmse(late.routed),
                     pooled_rmse: lateRmse(late.pooled), gain: {} };
    for (const k of Object.keys(steady.routed_rmse)) {
      steady.gain[k] = steady.pooled_rmse[k] > 0 ? 1 - steady.routed_rmse[k] / steady.pooled_rmse[k] : null;
    }
    const coverage = Object.fromEntries(Object.entries(acc.covered).map(([k, v]) =>
      [k, acc.scored ? v / acc.scored : null]));
    return { calls: acc.calls, scored: acc.scored, routed_rmse: routed, pooled_rmse: pooled,
             gain, steady, interval_coverage_1_96: coverage, events: acc.events, seconds: acc.seconds,
             agreement: Object.keys(acc.contingency).length
               ? Object.assign({ contingency: acc.contingency }, scores(acc.contingency)) : null };
  }

  // Integrate a frozen learner's predicted rates in place (explicit Euler at
  // the caller's step, then the caller's bounds). Elements without a
  // prediction stay untouched and are counted.
  // A field may carry `mask` (per element, truthy = apply): a learned law that stands in for an
  // operator drives a field only where that operator rates it, so it never invents a rate the
  // operator does not have (a masked element keeps its value for that field).
  function applyRates(report, fields, dt) {
    let applied = 0, untouched = 0;
    const n = report.elementDomains.length;
    for (let i = 0; i < n; ++i) {
      let ok = true;
      for (const f of fields) {
        const v = report.predictions[f.rate][i];
        if (v === null || !Number.isFinite(v)) ok = false;
      }
      if (!ok) { untouched += 1; continue; }
      for (const f of fields) {
        if (f.mask && !f.mask[i]) continue;
        const next = f.values[i] + report.predictions[f.rate][i] * dt;
        f.values[i] = Math.min(f.max, Math.max(f.min, next));
      }
      applied += 1;
    }
    // Rates come from the engine's learned domains (ctx.learnDomains); untouched elements had
    // no finite prediction and keep their value.
    trace.count("rates_applied", applied);
    trace.count("rates_untouched", untouched);
    if (trace.enabled("debug")) trace.debug("learned rates applied", {applied, untouched, dt, fields: fields.map(f => f.rate)});
    return { applied, untouched };
  }

  globalThis.TRECH_DOMAIN_LEARNING = { agreement, scores, merge, summarize, accumulator,
                                       accumulate, finish, applyRates };
})();
