// Maintain domain identity between successive statistical subdivisions of a
// persistent population. Element rows must use the same identities and order.
globalThis.TRECH_TRACK_DOMAINS = function (report, previous = null) {
  const {groups, elementGroups} = report;
  if (previous && previous.elementIds.length !== elementGroups.length) {
    throw new Error("Domain lineage needs the same persistent population");
  }
  const previousGroups = new Map();
  if (previous) {
    for (const group of previous.groups) {
      if (group.id !== null) previousGroups.set(group.id, group);
    }
  }
  const contributions = groups.map(() => new Map());
  if (previous) {
    for (let i = 0; i < elementGroups.length; ++i) {
      const prior = previous.elementIds[i], current = elementGroups[i];
      if (prior === null || current === null || groups[current].path === "u") continue;
      const edges = contributions[current];
      edges.set(prior, (edges.get(prior) || 0) + 1);
    }
  }
  let nextId = previous ? previous.nextId : 0;
  const tracked = groups.map((group, index) => {
    const predecessors = Array.from(contributions[index], ([id, elements]) => ({id, elements}))
      .sort((a, b) => a.id - b.id);
    const continued = predecessors.find(({id, elements}) => {
      const prior = previousGroups.get(id);
      return prior.parent === group.parent && elements * 2 > Math.max(prior.elements, group.elements);
    });
    const id = group.path === "u" ? null : continued ? continued.id : nextId++;
    return {...group, id, predecessors};
  });
  // Engine trace channel (docs/engine/engine_trace.md), silent unless tracing is on. trech and the
  // Node model loader provide TRECH_TRACE, plain Node loads js/trech_trace.js, any other host
  // gets a no-op. Logging never changes a result.
  const trace = (globalThis.TRECH_TRACE || (typeof require === "function" ? require("./trech_trace.js") : null) ||
    {channel: () => ({info() {}, log() {}, debug() {}, trace() {}, count() {}, enabled: () => false,
      span: (name, fn) => fn()})}).channel("domain_tracking");
  if (trace.enabled("debug")) {
    trace.debug("domain lineage", {groups: tracked.length,
      continued: tracked.filter(g => g.predecessors && g.predecessors.length).length, next_id: nextId});
  }
  return {
    nextId, groups: tracked,
    elementIds: elementGroups.map(index => index === null ? null : tracked[index].id)
  };
};
