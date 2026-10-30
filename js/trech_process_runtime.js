// Generic process sequencing. State laws remain engine operators; no fallback kinetics.
(function() {
  if (globalThis.TRECH_PROCESS_RUNTIME) return;
  const copy = value => JSON.parse(JSON.stringify(value));
  function create({initial, stages, validate}) {
    let state = copy(initial), cursor = 0, elapsed = 0, calls = 0;
    validate(state);
    function snapshot() { return {state: copy(state), stage: cursor,
      active_process: stages[cursor] ? stages[cursor].id : null,
      completed: cursor === stages.length, elapsed_s: elapsed, calls}; }
    function step(ctx, dt) {
      if (!Number.isFinite(dt) || dt <= 0) throw new Error("Process dt must be positive seconds");
      if (!ctx.runtime || ctx.runtime.mode !== "predictive")
        return {...snapshot(), status: "strict_disabled", report: null};
      while (cursor < stages.length && stages[cursor].complete(state)) cursor++;
      if (cursor === stages.length) return {...snapshot(), status: "complete", report: null};
      const stage = stages[cursor], draft = copy(state);
      const report = stage.advance(ctx, draft, dt);
      calls++;
      if (!report || !report.ran) return {...snapshot(), status: "blocked", process: stage.id,
        reason: "Required operator unavailable, ambiguous or missing inputs; no fallback law", report};
      try { validate(draft); } catch (error) {
        return {...snapshot(), status: "rejected", process: stage.id, reason: error.message,
          report, note: "Inference/draws remain recorded; proposed state was not committed"};
      }
      state = draft; elapsed += dt;
      if (stage.complete(state)) cursor++;
      return {...snapshot(), status: cursor === stages.length ? "complete" : "advanced", process: stage.id, report};
    }
    return {step, snapshot};
  }
  globalThis.TRECH_PROCESS_RUNTIME = {create};
})();
