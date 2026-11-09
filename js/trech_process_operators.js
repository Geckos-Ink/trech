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
  // ---- unit labels: dimensional analysis and multiplicative conversion ----
  // A label is a product of factors joined by "*", "." or " " and divided by "/"
  // (left to right: "mol/L/s" = mol L^-1 s^-1), each factor a symbol with an
  // optional integer power ("m^2", "s^-1", "m2"). "1" is dimensionless. Affine
  // temperature scales (degC/degF) are rejected: they need an offset, not a
  // factor. Parsing reads labels; it never certifies a model's physical units.
  const DIMENSIONS = ["m", "kg", "s", "A", "K", "mol", "cd"];
  const unitDef = (scale, m = 0, kg = 0, s = 0, A = 0, K = 0, mol = 0, cd = 0) =>
    ({scale, dims: [m, kg, s, A, K, mol, cd]});
  const UNIT_SYMBOLS = {
    "1": unitDef(1), "%": unitDef(0.01), rad: unitDef(1), sr: unitDef(1),
    m: unitDef(1, 1), g: unitDef(1e-3, 0, 1), s: unitDef(1, 0, 0, 1), A: unitDef(1, 0, 0, 0, 1),
    K: unitDef(1, 0, 0, 0, 0, 1), mol: unitDef(1, 0, 0, 0, 0, 0, 1), cd: unitDef(1, 0, 0, 0, 0, 0, 0, 1),
    min: unitDef(60, 0, 0, 1), h: unitDef(3600, 0, 0, 1), d: unitDef(86400, 0, 0, 1),
    Hz: unitDef(1, 0, 0, -1), N: unitDef(1, 1, 1, -2), Pa: unitDef(1, -1, 1, -2), J: unitDef(1, 2, 1, -2),
    W: unitDef(1, 2, 1, -3), C: unitDef(1, 0, 0, 1, 1), V: unitDef(1, 2, 1, -3, -1), Ohm: unitDef(1, 2, 1, -3, -2),
    S: unitDef(1, -2, -1, 3, 2), F: unitDef(1, -2, -1, 4, 2), T: unitDef(1, 0, 1, -2, -1), Wb: unitDef(1, 2, 1, -2, -1),
    H: unitDef(1, 2, 1, -2, -2), Gy: unitDef(1, 2, 0, -2), Sv: unitDef(1, 2, 0, -2),
    L: unitDef(1e-3, 3), M: unitDef(1e3, -3, 0, 0, 0, 0, 1), eV: unitDef(1.602176634e-19, 2, 1, -2),
    bar: unitDef(1e5, -1, 1, -2), atm: unitDef(101325, -1, 1, -2), u: unitDef(1.66053906660e-27, 0, 1),
    Da: unitDef(1.66053906660e-27, 0, 1), cal: unitDef(4.184, 2, 1, -2), b: unitDef(1e-28, 2)
  };
  UNIT_SYMBOLS["Ω"] = UNIT_SYMBOLS.Ohm;
  UNIT_SYMBOLS.deg = unitDef(Math.PI / 180);
  UNIT_SYMBOLS.angstrom = UNIT_SYMBOLS["\u00c5"] = unitDef(1e-10, 1);
  // Counted entities are dimensionless numbers (a parcel count, a photon count);
  // "mol/parcel" is therefore an amount per counted parcel.
  for (const noun of ["count", "parcel", "particle", "photon", "event", "cell", "molecule", "atom",
      "representative", "step", "substep", "tick", "iteration"])
    UNIT_SYMBOLS[noun] = UNIT_SYMBOLS[noun + "s"] = unitDef(1);
  // Symbols that take SI prefixes (cal, eV, L, M, g, ... but not min/h/d/%/1).
  const PREFIXABLE = new Set(["m", "g", "s", "A", "K", "mol", "cd", "Hz", "N", "Pa", "J", "W", "C", "V", "Ohm",
    "Ω", "S", "F", "T", "Wb", "H", "Gy", "Sv", "L", "M", "eV", "bar", "Da", "cal", "b"]);
  const PREFIXES = {Y: 1e24, Z: 1e21, E: 1e18, P: 1e15, T: 1e12, G: 1e9, M: 1e6, k: 1e3, h: 1e2, da: 1e1,
    d: 1e-1, c: 1e-2, m: 1e-3, u: 1e-6, "µ": 1e-6, n: 1e-9, p: 1e-12, f: 1e-15, a: 1e-18, z: 1e-21, y: 1e-24};
  const AFFINE = new Set(["degC", "°C", "degF", "°F", "C_deg"]);
  function unitSymbol(symbol, label) {
    if (AFFINE.has(symbol))
      throw new Error("Affine temperature unit needs an offset, not a factor: " + label);
    if (own(UNIT_SYMBOLS, symbol)) return UNIT_SYMBOLS[symbol];
    for (const prefix of Object.keys(PREFIXES).sort((a, b) => b.length - a.length)) {
      const rest = symbol.slice(prefix.length);
      if (symbol.startsWith(prefix) && rest && PREFIXABLE.has(rest))
        return {scale: PREFIXES[prefix] * UNIT_SYMBOLS[rest].scale, dims: UNIT_SYMBOLS[rest].dims};
    }
    throw new Error("Unknown unit symbol '" + symbol + "' in " + label);
  }
  function parseUnit(label) {
    requireText(label, "Unit label");
    const SUPERSCRIPTS = {"\u2070": "0", "\u00b9": "1", "\u00b2": "2", "\u00b3": "3", "\u2074": "4",
      "\u2075": "5", "\u2076": "6", "\u2077": "7", "\u2078": "8", "\u2079": "9", "\u207b": "-"};
    const normalized = label.replace(/[\u2070\u00b9\u00b2\u00b3\u2074-\u2079\u207b]+/g,
      run => "^" + Array.from(run).map(c => SUPERSCRIPTS[c]).join(""));
    const tokens = normalized.trim().split(/\s*(\/)\s*|\s*[*.· ]\s*/).filter(t => t !== undefined && t !== "");
    let scale = 1, sign = 1, expectFactor = true;
    const dims = DIMENSIONS.map(() => 0);
    for (const token of tokens) {
      if (token === "/") {
        if (expectFactor) throw new Error("Malformed unit label: " + label);
        sign = -1; expectFactor = true; continue;
      }
      const match = /^([^\^\d\-+]+|1)(?:\^?([+-]?\d+))?$/.exec(token);
      if (!match || (match[1] === "1" && match[2] !== undefined))
        throw new Error("Malformed unit factor '" + token + "' in " + label);
      const power = sign * (match[2] === undefined ? 1 : Number(match[2]));
      const unit = unitSymbol(match[1], label);
      scale *= Math.pow(unit.scale, power);
      unit.dims.forEach((d, i) => { dims[i] += d * power; });
      sign = 1; expectFactor = false;
    }
    if (expectFactor) throw new Error("Malformed unit label: " + label);
    return {label, scale, dims};
  }
  const sameDims = (a, b) => a.dims.every((d, i) => d === b.dims[i]);
  const sameScale = (a, b) => Math.abs(a.scale - b.scale) <= 1e-12 * Math.max(Math.abs(a.scale), Math.abs(b.scale));
  function describeDims(dims) {
    const text = DIMENSIONS.filter((_, i) => dims[i]).map(name => {
      const p = dims[DIMENSIONS.indexOf(name)];
      return p === 1 ? name : name + "^" + p;
    }).join(" ");
    return text || "1";
  }
  function conversionFactor(from, to) {
    const a = parseUnit(from), b = parseUnit(to);
    if (!sameDims(a, b))
      throw new Error("Incompatible units: " + from + " [" + describeDims(a.dims) + "] vs " + to + " [" + describeDims(b.dims) + "]");
    return a.scale / b.scale;
  }
  const units = Object.freeze({
    parse(label) { const u = parseUnit(label); return {label: u.label, scale: u.scale, dims: u.dims.slice(),
      dimension: describeDims(u.dims)}; },
    compatible(a, b) { return sameDims(parseUnit(a), parseUnit(b)); },
    factor: conversionFactor,
    convert(value, from, to) {
      if (!Number.isFinite(value)) throw new Error("Unit conversion requires a finite value");
      return value * conversionFactor(from, to);
    }
  });
  // Bind-time dimensional audit (opt-in `dimensional_check: true`): every declared
  // label must parse; `d_<f>_dt` outputs must equal unit(f)/s and `set_<f>` the
  // field unit (same dimension AND scale, since the engine integrates with dt in
  // seconds and converts nothing); `hazard_<channel>` must be exactly 1/s.
  function dimensionalAudit(contract, writable, coordinates) {
    const declared = {};
    for (const item of [...writable, ...contract.aux, ...contract.context, ...coordinates])
      declared[item.name] = parseUnit(item.unit);
    const checks = [];
    const second = parseUnit("s");
    const expectEqual = (feature, actual, expected, rule) => {
      const ok = sameDims(actual, expected) && sameScale(actual, expected);
      checks.push({feature, unit: actual.label, expected: describeDims(expected.dims), rule, ok});
      if (!ok) throw new Error("Dimensional mismatch for " + feature + ": " + actual.label + " [" +
        describeDims(actual.dims) + ", x" + actual.scale + "] but " + rule + " requires [" +
        describeDims(expected.dims) + ", x" + expected.scale + "]");
    };
    const outputs = contract.model_units ? contract.model_units.outputs : {};
    const inputs = contract.model_units ? contract.model_units.inputs : {};
    for (const label of Object.values(inputs)) parseUnit(label);
    const channelNames = new Set((contract.channels || []).map(c => c.name));
    for (const [name, label] of Object.entries(outputs)) {
      const actual = parseUnit(label);
      const rate = /^d_(.+)_dt$/.exec(name), assign = /^set_(.+)$/.exec(name), hazard = /^hazard_(.+)$/.exec(name);
      if (rate && own(declared, rate[1]) && writable.some(f => f.name === rate[1])) {
        const f = declared[rate[1]];
        expectEqual(name, actual, {scale: f.scale / second.scale, dims: f.dims.map((d, i) => d - second.dims[i])},
          "d_" + rate[1] + "_dt = unit(" + rate[1] + ")/s");
      } else if (assign && writable.some(f => f.name === assign[1])) {
        expectEqual(name, actual, declared[assign[1]], "set_" + assign[1] + " = unit(" + assign[1] + ")");
      } else if (hazard && contract.operation === "react") {
        if (!channelNames.has(hazard[1])) throw new Error("Hazard output names no declared channel: " + name);
        expectEqual(name, actual, parseUnit("1/s"), "hazard = 1/s");
      }
    }
    return {schema: "trech_process_dimensions_v1",
            declared: Object.fromEntries(Object.entries(declared).map(([k, u]) => [k, describeDims(u.dims)])),
            checks};
  }
  function bind(definition) {
    const contract = copy(definition);
    if (!contract || !["evolve", "react", "interact"].includes(contract.operation))
      throw new Error("Process operation must be evolve, react or interact");
    const spatial = contract.operation === "interact";
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
    let declaredKinds = kinds ? kinds.allowed : [contract.element_kind];
    if (spatial && kinds) {
      // Match C++ UTF-8 lexical ordering, including non-BMP material names.
      for (const kind of declaredKinds)
        if (kind.includes("|") || Array.from(kind).some(c => c.codePointAt(0) >= 0xd800 && c.codePointAt(0) <= 0xdfff))
          throw new Error("Pair member kinds cannot contain | or unpaired surrogates");
      const compare = (a, b) => {
        const aa = Array.from(a), bb = Array.from(b);
        for (let i = 0; i < Math.min(aa.length, bb.length); i++) {
          const difference = aa[i].codePointAt(0) - bb[i].codePointAt(0);
          if (difference) return difference;
        }
        return aa.length - bb.length;
      };
      const members = declaredKinds.slice().sort(compare);
      declaredKinds = members.flatMap((a, i) => members.slice(i).map(b => a + "|" + b));
    }
    if (contract.model_artifacts !== undefined) {
      if (!Array.isArray(contract.model_artifacts) || !contract.model_artifacts.length)
        throw new Error("Model artifact pins must be a nonempty array");
      const names = new Set();
      for (const artifact of contract.model_artifacts) {
        if (!artifact || typeof artifact !== "object") throw new Error("Invalid model artifact pin");
        requireText(artifact.name, "Model artifact name");
        if (names.has(artifact.name) || typeof artifact.content_id !== "string" ||
            !/^(fnv1a64:[0-9a-f]{16}|sha256:[0-9a-f]{64})$/.test(artifact.content_id)) throw new Error("Invalid model artifact pin");
        names.add(artifact.name);
      }
    }
    if (!contract.provenance) throw new Error("Process provenance must be explicit");
    requireText(contract.provenance.basis, "Process provenance basis");
    contract.schema = "trech_process_operator_v1";
    contract.aux = contract.aux || [];
    contract.context = contract.context || [];
    const writable = contract.operation !== "react" ? contract.fields : contract.species;
    declarations(writable, "state", true);
    declarations(contract.aux, "aux", false);
    declarations(contract.context, "context", false);
    if (kinds && [...writable, ...contract.aux, ...contract.context].some(item => item.name === kinds.field))
      throw new Error("Material kind field must be separate from numeric declarations");
    if (contract.aux.some(a => writable.some(f => f.name === a.name)))
      throw new Error("Process state and aux names must be disjoint");
    let coordinates = [];
    if (spatial) {
      const geometry = contract.spatial;
      if (!geometry || typeof geometry !== "object" || Array.isArray(geometry) ||
          !geometry.axes || Object.keys(geometry.axes).sort().join(",") !== "x,y,z" ||
          !Number.isFinite(geometry.cutoff) || geometry.cutoff <= 0 ||
          (geometry.max_pairs !== undefined && (!Number.isSafeInteger(geometry.max_pairs) || geometry.max_pairs <= 0)))
        throw new Error("Spatial binding requires x/y/z axes, positive cutoff and optional positive integer max_pairs");
      // What an empty neighbourhood means is domain knowledge, so it is declared:
      // "block" (default) keeps the step blocked; "complete" commits a recorded
      // no-op that advances the process clock with state unchanged.
      if (geometry.empty_neighbourhood !== undefined && !["block", "complete"].includes(geometry.empty_neighbourhood))
        throw new Error("Spatial empty_neighbourhood must be \"block\" or \"complete\"");
      requireText(geometry.unit, "Spatial coordinate unit");
      coordinates = ["x", "y", "z"].map(axis => ({name: geometry.axes[axis], unit: geometry.unit}));
      declarations(coordinates, "coordinate", true);
      if (coordinates.some(c => [...writable, ...contract.aux, ...contract.context].some(f => f.name === c.name) ||
          (kinds && c.name === kinds.field)))
        throw new Error("Spatial coordinates must be separate read-only state arrays");
      for (const field of writable)
        if (!["antisymmetric", "symmetric"].includes(field.symmetry))
          throw new Error("Pair fields require explicit symmetry");
      // Persistent topology has a distinct pair-state commit contract; do not silently ignore it.
      for (const name of ["links", "pair_fields", "pair_state"])
        if (contract[name] !== undefined) throw new Error("Spatial process binding does not support " + name);
    } else if (contract.spatial !== undefined) throw new Error("Spatial declaration requires interact");
    // Whether an EMPTY population (every state array has zero elements) means
    // "nothing to change" is domain knowledge, so it is declared: "block"
    // (default) keeps the empty step invalid; "complete" commits a recorded no-op
    // once the engine confirms complete operator selection with zero inference.
    // Per-element kinds have no kind to select over zero elements: not supported.
    if (contract.empty_population !== undefined) {
      if (!["block", "complete"].includes(contract.empty_population))
        throw new Error("empty_population must be \"block\" or \"complete\"");
      if (spatial || kinds)
        throw new Error("empty_population applies to scalar-kind evolve/react bindings only");
    }
    const emptyCompletes = contract.empty_population === "complete";
    if (contract.model_units !== undefined) {
      unitMaps(contract.model_units);
      const {inputs, outputs} = contract.model_units;
      for (const [name, unit] of Object.entries(inputs))
        if (own(outputs, name) && outputs[name] !== unit)
          throw new Error("Conflicting intermediate unit: " + name);
      const memberUnits = spatial ? [...writable, ...contract.aux].flatMap(f =>
        ["a_", "b_"].map(prefix => ({name: prefix + f.name, unit: f.unit}))) : [...writable, ...contract.aux];
      const geometryUnits = spatial ? ["r", "dx", "dy", "dz", "ux", "uy", "uz"].map(name =>
        ({name, unit: name.startsWith("u") ? "1" : contract.spatial.unit})) : [];
      for (const item of [...memberUnits, ...geometryUnits, ...contract.context, {name: "dt", unit: "s"}])
        for (const map of [inputs, outputs])
          if (own(map, item.name) && map[item.name] !== item.unit)
            throw new Error("Conflicting process feature unit: " + item.name);
    }
    let dimensions = null;
    if (contract.dimensional_check !== undefined) {
      if (typeof contract.dimensional_check !== "boolean") throw new Error("dimensional_check must be boolean");
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
    if (contract.dimensional_check === true) dimensions = dimensionalAudit(contract, writable, coordinates);
    function totals(state, count) {
      return contract.conservation.map(vector => Array.from({length: count}, (_, i) =>
        writable.reduce((sum, field) => exactSum(sum,
          vector.coefficients[field.name] || 0, state[field.name][i]), 0)));
    }
    function arrays(state, items, count, discrete, allowEmpty = false) {
      const result = {};
      for (const item of items) {
        const values = state[item.name];
        if (!Array.isArray(values) || (!values.length && !allowEmpty) || (count !== null && values.length !== count))
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
      let proposed, aux, balances, elementKinds, positions;
      try {
        proposed = arrays(state, writable, null, contract.operation === "react", emptyCompletes);
        aux = arrays(state, contract.aux, proposed[writable[0].name].length, false, emptyCompletes);
        if (spatial) {
          const values = arrays(state, coordinates, proposed[writable[0].name].length, false);
          positions = Object.fromEntries(["x", "y", "z"].map(axis => [axis, values[contract.spatial.axes[axis]]]));
        }
        if (kinds) {
          elementKinds = state[kinds.field];
          if (!Array.isArray(elementKinds) || elementKinds.length !== proposed[writable[0].name].length ||
              Array.from(elementKinds).some(kind => !kinds.allowed.includes(kind)))
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
          artifacts = group.map(m => ({name: m.name, content_id: m.content_id,
            ...(m.sha256 ? {sha256: m.sha256} : {})}));
          if (contract.model_artifacts && (artifacts.length !== contract.model_artifacts.length || contract.model_artifacts.some(pin =>
              !artifacts.some(m => m.name === pin.name &&
                (pin.content_id.startsWith("sha256:") ? "sha256:" + m.sha256 : m.content_id) === pin.content_id))))
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
      // Only a declared-complete binding reaches here with zero elements.
      const emptyStep = emptyCompletes && proposed[writable[0].name].length === 0;
      const spec = {dt, state: proposed, aux, context,
        operator_role: contract.operator_role, element_kind: kinds ? elementKinds : contract.element_kind,
        ...(kinds || spatial || emptyStep ? {require_complete_selection: true} : {}),
        ...(emptyStep ? {report_empty_population: true} : {})};
      if (contract.operation !== "react")
        spec.fields = writable.map(({name, min, max, symmetry}) => ({name,
          ...(spatial ? {symmetry} : {}), ...(min !== undefined ? {min} : {}), ...(max !== undefined ? {max} : {})}));
      else Object.assign(spec, {species: writable.map(f => f.name),
        channels: copy(contract.channels), conservation: copy(contract.conservation)});
      if (spatial) Object.assign(spec, {positions, cutoff: contract.spatial.cutoff,
        ...(contract.spatial.max_pairs !== undefined ? {max_pairs: contract.spatial.max_pairs} : {})});
      let engine;
      try { engine = ctx[contract.operation](spec); }
      catch (error) { return failure("operator_exception", String((error && error.message) || error)); }
      if (!engine || !engine.ran) {
        // Only the engine's explicit empty-pair verdict, after complete selection and an
        // untruncated search, may complete; every other non-run stays blocked.
        if (spatial && contract.spatial.empty_neighbourhood === "complete" && engine &&
            engine.blockedReason === "no_pairs" && engine.pairCount === 0 && engine.inferenceCount === 0 &&
            !engine.neighborPairsTruncated && engine.selection && engine.selection.status === "selected")
          return {ran: false, accepted: true, no_op: "empty_neighbourhood", contract_id: contract.id,
            error: null, engine, ...(artifacts ? {artifacts: copy(artifacts)} : {})};
        // Likewise only the explicit zero-element verdict, for a declared empty population.
        if (emptyStep && engine && engine.blockedReason === "no_elements" && engine.elementCount === 0 &&
            engine.inferenceCount === 0 && engine.drawCount === 0 &&
            engine.selection && engine.selection.status === "selected")
          return {ran: false, accepted: true, no_op: "empty_population", contract_id: contract.id,
            error: null, engine, ...(artifacts ? {artifacts: copy(artifacts)} : {})};
        return failure("operator_blocked", "Required operator unavailable, ambiguous or missing inputs; no fallback law", engine);
      }
      try {
        if (spatial && engine.neighborPairsTruncated)
          throw new Error("Spatial neighbour search truncated; incomplete proposal not committed");
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
    return dimensions ? {contract: copy(contract), advance, dimensions: copy(dimensions)} : {contract: copy(contract), advance};
  }
  globalThis.TRECH_PROCESS_OPERATORS = {bind, units};
})();
