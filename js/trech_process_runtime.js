// Generic process sequencing. State laws remain engine operators; no fallback kinetics.
(function() {
  if (globalThis.TRECH_PROCESS_RUNTIME) return;
  // Engine trace channel (docs/engine/engine_trace.md), silent unless tracing is on. trech and the
  // Node model loader provide TRECH_TRACE, plain Node loads js/trech_trace.js, any other host
  // gets a no-op. Logging never changes a result.
  const trace = (globalThis.TRECH_TRACE || (typeof require === "function" ? require("./trech_trace.js") : null) ||
    {channel: () => ({info() {}, log() {}, debug() {}, trace() {}, count() {}, enabled: () => false,
      span: (name, fn) => fn()})}).channel("process_runtime");
  const copy = value => JSON.parse(JSON.stringify(value));
  function create({initial, stages, validate}) {
    let state = copy(initial), cursor = 0, elapsed = 0, calls = 0;
    validate(state);
    function snapshot() { return {state: copy(state), stage: cursor,
      active_process: stages[cursor] ? stages[cursor].id : null,
      completed: cursor === stages.length, elapsed_s: elapsed, calls}; }
    function step(ctx, dt) {
      const before = cursor;
      const result = stepOnce(ctx, dt);
      trace.count(result.status);
      if (cursor !== before)
        trace.info("process stage advanced", {from: stages[before] ? stages[before].id : null,
          to: stages[cursor] ? stages[cursor].id : null, completed: cursor === stages.length, elapsed_s: elapsed});
      if (result.status === "blocked" || result.status === "rejected")
        trace.info("process step " + result.status, {process: result.process, reason: result.reason});
      else if (trace.enabled("debug"))
        trace.debug("process step " + result.status, {process: result.process || null, stage: cursor, elapsed_s: elapsed});
      return result;
    }
    function stepOnce(ctx, dt) {
      if (!Number.isFinite(dt) || dt <= 0) throw new Error("Process dt must be positive seconds");
      if (!ctx.runtime || ctx.runtime.mode !== "predictive")
        return {...snapshot(), status: "strict_disabled", report: null};
      while (cursor < stages.length && stages[cursor].complete(state)) cursor++;
      if (cursor === stages.length) return {...snapshot(), status: "complete", report: null};
      const stage = stages[cursor], draft = copy(state);
      const report = stage.advance(ctx, draft, dt);
      calls++;
      // A declared no-op (the operator binding's contract, e.g. an empty spatial
      // neighbourhood) commits unchanged state and advances the clock.
      const noOp = report && !report.ran && report.accepted === true && typeof report.no_op === "string";
      if (!report || (!report.ran && !noOp) || report.accepted === false) {
        const rejected = report && report.accepted === false && (report.ran || !report.error ||
          !["strict_disabled", "operator_unavailable", "missing_context", "operator_blocked",
            "catalog_unavailable", "artifact_mismatch", "unit_metadata_missing", "unit_mismatch"].includes(report.error.code));
        return {...snapshot(), status: rejected ? "rejected" : "blocked", process: stage.id,
          reason: report && report.error ? report.error.message : "Required operator unavailable, ambiguous or missing inputs; no fallback law",
          report, ...(rejected ? {note: "Inference/draws remain recorded; proposed state was not committed"} : {})};
      }
      try { validate(draft); } catch (error) {
        return {...snapshot(), status: "rejected", process: stage.id, reason: error.message,
          report, note: "Inference/draws remain recorded; proposed state was not committed"};
      }
      state = draft; elapsed += dt;
      if (stage.complete(state)) cursor++;
      return {...snapshot(), status: cursor === stages.length ? "complete" : "advanced", process: stage.id, report,
        ...(noOp ? {no_op: report.no_op} : {})};
    }
    return {step, snapshot};
  }
  globalThis.TRECH_PROCESS_RUNTIME = {create};
})();
