// Data-only contracts for process libraries. No model selection or physical law
// lives here: engine operators still own inference, RNG and execution reports.
(function() {
  if (globalThis.TRECH_PROCESS_OPERATORS) return;
  const copy = value => JSON.parse(JSON.stringify(value));
  const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
  function requireText(value, label) {
    if (typeof value !== "string" || !value.trim()) throw new Error(label + " must be explicit");
  }
  function declarations(items, label, required) {
    if (!Array.isArray(items) || (required && !items.length)) throw new Error("Invalid " + label);
    const names = new Set();
    for (const item of items) {
      requireText(item.name, label + " name");
      requireText(item.unit, label + " unit");
      if (["__proto__", "constructor", "prototype"].includes(item.name) || names.has(item.name))
        throw new Error("Duplicate or reserved " + label + ": " + item.name);
      names.add(item.name);
      for (const bound of ["min", "max"])
        if (item[bound] !== undefined && !Number.isFinite(item[bound])) throw new Error("Invalid " + label + " bound");
      if (item.min !== undefined && item.max !== undefined && item.min > item.max)
        throw new Error("Reversed " + label + " bounds");
    }
  }
  function exactSum(sum, coefficient, value) {
    const product = coefficient * value;
    if (!Number.isSafeInteger(product) || !Number.isSafeInteger(sum + product))
      throw new Error("Conservation exceeds exact integer range");
    return sum + product;
  }
  function unitMaps(units) {
    if (!units || typeof units !== "object" || Array.isArray(units) || Object.keys(units).length !== 2)
      throw new Error("Model units require input/output maps");
    for (const side of ["inputs", "outputs"]) {
      const map = units[side];
      if (!map || typeof map !== "object" || Array.isArray(map) || !Object.keys(map).length)
        throw new Error("Model units require nonempty " + side);
      for (const [name, unit] of Object.entries(map)) {
        requireText(name, "Model feature name");
        requireText(unit, "Model feature unit");
        if (["__proto__", "constructor", "prototype"].includes(name) || unit.includes("\0"))
          throw new Error("Invalid model feature unit declaration");
      }
    }
  }
  function bind(definition) {
    const contract = copy(definition);
    if (!contract || !["evolve", "react"].includes(contract.operation))
      throw new Error("Process operation must be evolve or react");
    if (contract.schema !== undefined && contract.schema !== "trech_process_operator_v1")
      throw new Error("Unsupported process operator contract schema");
    for (const key of ["id", "operator_role"]) requireText(contract[key], key);
    const kinds = contract.element_kinds;
    if (kinds !== undefined) {
      if (contract.element_kind !== undefined || !kinds || typeof kinds !== "object" || Array.isArray(kinds))
        throw new Error("Declare scalar element_kind or per-element element_kinds");
      requireText(kinds.field, "Material kind field");
      if (kinds.field.includes("\0") || ["__proto__", "constructor", "prototype"].includes(kinds.field) ||
          !Array.isArray(kinds.allowed) || !kinds.allowed.length || new Set(kinds.allowed).size !== kinds.allowed.length)
        throw new Error("Invalid material kind declaration");
      for (const kind of kinds.allowed) {
        requireText(kind, "Allowed material kind");
        if (kind.includes("\0")) throw new Error("Material kind cannot contain NUL");
      }
    } else requireText(contract.element_kind, "element_kind");
    const declaredKinds = kinds ? kinds.allowed : [contract.element_kind];
    if (contract.model_artifacts !== undefined) {
      if (!Array.isArray(contract.model_artifacts) || !contract.model_artifacts.length)
        throw new Error("Model artifact pins must be a nonempty array");
      const names = new Set();
      for (const artifact of contract.model_artifacts) {
        if (!artifact || typeof artifact !== "object") throw new Error("Invalid model artifact pin");
        requireText(artifact.name, "Model artifact name");
        if (names.has(artifact.name) || typeof artifact.content_id !== "string" ||
            !/^fnv1a64:[0-9a-f]{16}$/.test(artifact.content_id)) throw new Error("Invalid model artifact pin");
        names.add(artifact.name);
      }
    }
    if (!contract.provenance) throw new Error("Process provenance must be explicit");
    requireText(contract.provenance.basis, "Process provenance basis");
    contract.schema = "trech_process_operator_v1";
    contract.aux = contract.aux || [];
    contract.context = contract.context || [];
    const writable = contract.operation === "evolve" ? contract.fields : contract.species;
    declarations(writable, "state", true);
    declarations(contract.aux, "aux", false);
    declarations(contract.context, "context", false);
    if (kinds && [...writable, ...contract.aux, ...contract.context].some(item => item.name === kinds.field))
      throw new Error("Material kind field must be separate from numeric declarations");
    if (contract.aux.some(a => writable.some(f => f.name === a.name)))
      throw new Error("Process state and aux names must be disjoint");
    if (contract.model_units !== undefined) {
      unitMaps(contract.model_units);
      const {inputs, outputs} = contract.model_units;
      for (const [name, unit] of Object.entries(inputs))
        if (own(outputs, name) && outputs[name] !== unit)
          throw new Error("Conflicting intermediate unit: " + name);
      for (const item of [...writable, ...contract.aux, ...contract.context, {name: "dt", unit: "s"}])
        for (const map of [inputs, outputs])
          if (own(map, item.name) && map[item.name] !== item.unit)
            throw new Error("Conflicting process feature unit: " + item.name);
    }
    if (contract.operation === "react" &&
        (!Array.isArray(contract.channels) || !contract.channels.length ||
         !Array.isArray(contract.conservation) || !contract.conservation.length))
      throw new Error("Discrete processes require channels and conservation");
    if (contract.operation === "react") {
      const names = new Set(writable.map(f => f.name));
      for (const [label, items, property] of [["channel", contract.channels, "delta"],
          ["conservation", contract.conservation, "coefficients"]]) {
        const seen = new Set();
        for (const item of items) {
          requireText(item.name, label + " name");
          const vector = item[property];
          if (seen.has(item.name) || !vector || typeof vector !== "object" || Array.isArray(vector) ||
              !Object.keys(vector).length || Object.entries(vector).some(([key, n]) => !names.has(key) || !Number.isSafeInteger(n)))
            throw new Error("Invalid process " + label + ": " + item.name);
          seen.add(item.name);
        }
      }
      for (const vector of contract.conservation)
        for (const channel of contract.channels) {
          const balance = writable.reduce((sum, f) => exactSum(sum,
            vector.coefficients[f.name] || 0, channel.delta[f.name] || 0), 0);
          if (balance !== 0) throw new Error("Channel violates conservation: " + channel.name);
        }
    }
    function totals(state, count) {
      return contract.conservation.map(vector => Array.from({length: count}, (_, i) =>
        writable.reduce((sum, field) => exactSum(sum,
          vector.coefficients[field.name] || 0, state[field.name][i]), 0)));
    }
    function arrays(state, items, count, discrete) {
      const result = {};
      for (const item of items) {
        const values = state[item.name];
        if (!Array.isArray(values) || !values.length || (count !== null && values.length !== count))
          throw new Error("Invalid process array: " + item.name);
        count = values.length;
        if (Array.from(values).some(v => !Number.isFinite(v) || (discrete && (!Number.isSafeInteger(v) || v < 0)) ||
            (item.min !== undefined && v < item.min) || (item.max !== undefined && v > item.max)))
          throw new Error("Invalid process values: " + item.name);
        result[item.name] = values.slice();
      }
      return result;
    }
    function advance(ctx, state, dt, values = {}) {
      if (!Number.isFinite(dt) || dt <= 0) throw new Error("Process dt must be positive seconds");
      let artifacts;
      const failure = (code, message, engine = null, ran = false) =>
        ({ran, accepted: false, contract_id: contract.id, error: {code, message}, engine,
          ...(artifacts ? {artifacts: copy(artifacts)} : {})});
      if (!ctx.runtime || ctx.runtime.mode !== "predictive")
        return failure("strict_disabled", "Process inference requires predictive mode");
      if (typeof ctx[contract.operation] !== "function")
        return failure("operator_unavailable", "Engine operation unavailable: " + contract.operation);
      if (!values || typeof values !== "object" || Array.isArray(values))
        return failure("invalid_context", "Process context must be an object");
      const context = {};
      for (const item of contract.context) {
        if (!own(values, item.name)) return failure("missing_context", "Missing process context: " + item.name);
        const value = values[item.name];
        if (!Number.isFinite(value) || (item.min !== undefined && value < item.min) ||
            (item.max !== undefined && value > item.max))
          return failure("invalid_context", "Invalid process context: " + item.name);
        context[item.name] = value;
      }
      let proposed, aux, balances, elementKinds;
      try {
        proposed = arrays(state, writable, null, contract.operation === "react");
        aux = arrays(state, contract.aux, proposed[writable[0].name].length, false);
        if (kinds) {
          elementKinds = state[kinds.field];
          if (!Array.isArray(elementKinds) || elementKinds.length !== proposed[writable[0].name].length ||
              Array.from(elementKinds).some(kind => !declaredKinds.includes(kind)))
            throw new Error("Invalid per-element material kinds: " + kinds.field);
          elementKinds = elementKinds.slice();
        }
        if (contract.operation === "react") balances = totals(proposed, proposed[writable[0].name].length);
      } catch (error) { return failure("invalid_binding", error.message); }
      if (contract.model_artifacts || contract.model_units) {
        if (typeof ctx.operatorCatalog !== "function")
          return failure("catalog_unavailable", "Process capability checks require an engine operator catalog");
        try {
          const catalog = ctx.operatorCatalog();
          if (!catalog || catalog.schema !== "trech_operator_catalog_v1" || !Array.isArray(catalog.operators))
            return failure("catalog_unavailable", "Invalid engine operator catalog");
          // Check the entire loaded role/kind group, including additions. Keep
          // contextual selection and required-input checks inside the engine.
          const group = catalog.operators.filter(m => m.loaded && m.operator_role === contract.operator_role &&
            declaredKinds.includes(m.element_kind));
          artifacts = group.map(m => ({name: m.name, content_id: m.content_id}));
          if (contract.model_artifacts && (artifacts.length !== contract.model_artifacts.length || contract.model_artifacts.some(pin =>
              !artifacts.some(m => m.name === pin.name && m.content_id === pin.content_id))))
            return failure("artifact_mismatch", "Loaded operator group differs from process model artifact pins");
          if (contract.model_units) {
            for (const kind of declaredKinds) {
              const materialGroup = group.filter(m => m.element_kind === kind);
              if (!materialGroup.length) return failure("unit_metadata_missing", "No loaded operator group for unit checks: " + kind);
              const seen = {inputs: new Set(), outputs: new Set()};
              for (const model of materialGroup) {
                try { unitMaps(model.feature_units); }
                catch (_) { return failure("unit_metadata_missing", "Missing complete model units: " + model.name); }
                for (const side of ["inputs", "outputs"]) {
                  const names = model[side], actual = model.feature_units[side], expected = contract.model_units[side];
                  if (!Array.isArray(names) || names.length !== Object.keys(actual).length ||
                      names.some(name => !own(actual, name)))
                    return failure("unit_metadata_missing", "Incomplete model units: " + model.name);
                  for (const name of names) {
                    if (!own(expected, name) || expected[name] !== actual[name])
                      return failure("unit_mismatch", "Model unit differs from process contract: " + model.name + "/" + side + "/" + name);
                    seen[side].add(name);
                  }
                }
              }
              for (const side of ["inputs", "outputs"])
                if (Object.keys(contract.model_units[side]).some(name => !seen[side].has(name)))
                  return failure("unit_mismatch", "Loaded operator group omits declared " + side);
            }
          }
        } catch (error) { return failure("catalog_unavailable", String((error && error.message) || error)); }
      }
      const spec = {dt, state: proposed, aux, context,
        operator_role: contract.operator_role, element_kind: kinds ? elementKinds : contract.element_kind,
        ...(kinds ? {require_complete_selection: true} : {})};
      if (contract.operation === "evolve")
        spec.fields = writable.map(({name, min, max}) => ({name, ...(min !== undefined ? {min} : {}), ...(max !== undefined ? {max} : {})}));
      else Object.assign(spec, {species: writable.map(f => f.name),
        channels: copy(contract.channels), conservation: copy(contract.conservation)});
      let engine;
      try { engine = ctx[contract.operation](spec); }
      catch (error) { return failure("operator_exception", String((error && error.message) || error)); }
      if (!engine || !engine.ran)
        return failure("operator_blocked", "Required operator unavailable, ambiguous or missing inputs; no fallback law", engine);
      try {
        const count = state[writable[0].name].length;
        arrays(proposed, writable, count, contract.operation === "react");
        if (contract.operation === "react") {
          const after = totals(proposed, count);
          for (let v = 0; v < balances.length; v++)
            if (balances[v].some((n, i) => n !== after[v][i]))
              throw new Error("Process violated conservation: " + contract.conservation[v].name);
        }
      } catch (error) { return failure("invalid_proposal", error.message, engine, true); }
      for (const field of writable) state[field.name] = proposed[field.name].slice();
      return {ran: true, accepted: true, contract_id: contract.id, error: null, engine,
        ...(artifacts ? {artifacts: copy(artifacts)} : {})};
    }
    return {contract: copy(contract), advance};
  }
  globalThis.TRECH_PROCESS_OPERATORS = {bind};
})();
