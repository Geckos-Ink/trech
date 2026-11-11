// TRECH ML model definitions, structure searches and checkpoint resolution.
//
// Host-neutral: the same file loads through QuickJS `TRECH_INCLUDE` (scenarios resolve a
// registered checkpoint into a `models[]` entry) and through Node (the offline
// `tools/ml/bin/trech-ml.cjs` CLI evaluates definition files, trains, searches and manages the
// checkpoint store). It never touches files, the network, clocks or RNG of its own; Node-only
// work lives in tools/ml/lib/. Importing it draws no random values.
//
// Honesty contract: a definition declares WHAT a learned model is (named IO, dimension band,
// structure, training data). It never makes a prediction, and a checkpoint trained from it is a
// learned comparison model, not Geant4 output. Structure identity (`structure_id`) is a hash
// of the exported layer plan + named IO + output links, so two checkpoints that could not be
// loaded into the same definition can never share an identity or a store directory.
globalThis.TRECH_ML = (function () {
  "use strict";

  const DEFINITION_SCHEMA = "trech_ml_model_definition_v1";
  const SEARCH_SCHEMA = "trech_ml_structure_search_v1";
  const REGISTRY_SCHEMA = "trech_model_registry_v1";
  const SCALES = ["atomic", "nano", "micro", "meso", "macro"];
  const FAMILIES = ["linear", "mlp", "deepsets", "mpnn"];
  // Permutation-invariant set networks (generic_surrogate_v3): the flat inputs are `elements`
  // blocks of per-element features (element-major) followed by `context` global features.
  const SET_FAMILIES = ["deepsets", "mpnn"];
  const POOLS = ["sum", "mean", "max"];
  const AGGREGATES = ["sum", "mean"];
  // Hidden activations tools/torch/trech_torch/train_surrogate.py exports AND the C++
  // GenericSurrogate evaluates (src/ml/GenericSurrogate.cpp parseActivation).
  const ACTIVATIONS = ["silu", "tanh", "relu", "sigmoid"];
  const SHAPES = ["uniform", "taper"];
  const SELECTION_RULES = ["min_loss", "one_standard_error"];
  const LINKS = ["identity", "exp", "sigmoid"];
  const SOURCES = ["scores", "event_features", "hook_emits"];
  const FORMATS = ["generic_surrogate", "torchscript"];
  const ROLES = ["final", "best", "candidate", "intermediate"];
  const STRATEGIES = ["grid", "random", "evolvo", "custom"];
  const OBJECTIVES = ["r2_min", "r2_mean", "rmse_mean", "nrmse_mean"];
  const NAME_PATTERN = /^[A-Za-z][A-Za-z0-9_.-]{0,63}$/;
  const COLUMN_PATTERN = /^[A-Za-z_][A-Za-z0-9_.:/-]{0,127}$/;

  let declared = { definitions: [], searches: [] };

  function fail(where, message) {
    throw new Error("TRECH_ML " + where + ": " + message);
  }
  function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }
  function positiveInt(where, key, value, max) {
    if (!Number.isInteger(value) || value < 1 || (max && value > max))
      fail(where, key + " must be an integer in [1, " + (max || "∞") + "], got " + JSON.stringify(value));
    return value;
  }
  function finiteNumber(where, key, value, min, maxExclusive) {
    if (typeof value !== "number" || !Number.isFinite(value) || (min !== undefined && value < min) ||
        (maxExclusive !== undefined && value >= maxExclusive))
      fail(where, key + " must be a finite number" + (min !== undefined ? " >= " + min : "") +
           (maxExclusive !== undefined ? " and < " + maxExclusive : "") + ", got " + JSON.stringify(value));
    return value;
  }
  function oneOf(where, key, value, allowed) {
    if (allowed.indexOf(value) < 0)
      fail(where, key + " must be one of " + allowed.join("/") + ", got " + JSON.stringify(value));
    return value;
  }
  function onlyKeys(where, object, allowed) {
    for (const key of Object.keys(object))
      if (allowed.indexOf(key) < 0) fail(where, "unknown key '" + key + "' (allowed: " + allowed.join(", ") + ")");
  }
  function columns(where, key, value) {
    if (!Array.isArray(value) || value.length === 0) fail(where, key + " must be a non-empty array of column names");
    const seen = {};
    for (const column of value) {
      if (typeof column !== "string" || !COLUMN_PATTERN.test(column)) fail(where, key + " has an invalid column name " + JSON.stringify(column));
      if (seen[column]) fail(where, key + " repeats column '" + column + "'");
      seen[column] = true;
    }
    return value.slice();
  }
  function pathList(where, key, value) {
    if (value === undefined || value === null) return [];
    const list = typeof value === "string" ? [value] : value;
    if (!Array.isArray(list) || list.some(function (p) { return typeof p !== "string" || !p.length; }))
      fail(where, key + " must be a path string or an array of path strings");
    return list.slice();
  }

  // Stable JSON: object keys sorted recursively, so hashes never depend on authoring order.
  function canonical(value) {
    if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
    if (isObject(value)) {
      return "{" + Object.keys(value).sort().filter(function (k) { return value[k] !== undefined; })
        .map(function (k) { return JSON.stringify(k) + ":" + canonical(value[k]); }).join(",") + "}";
    }
    return JSON.stringify(value);
  }
  // FNV-1a 64 over UTF-16 code units folded to bytes (UTF-8 for ASCII names/values), the same
  // algorithm family the engine's `fnv1a64:` content IDs use. Identity only, not security.
  function fnv1a64(text) {
    let hash = 0xcbf29ce484222325n;
    const prime = 0x100000001b3n;
    const mask = 0xffffffffffffffffn;
    const bytes = utf8(text);
    for (let i = 0; i < bytes.length; ++i) {
      hash ^= BigInt(bytes[i]);
      hash = (hash * prime) & mask;
    }
    return hash.toString(16).padStart(16, "0");
  }
  function utf8(text) {
    const out = [];
    for (let i = 0; i < text.length; ++i) {
      let code = text.charCodeAt(i);
      if (code >= 0xd800 && code <= 0xdbff && i + 1 < text.length) {
        code = 0x10000 + ((code - 0xd800) << 10) + (text.charCodeAt(++i) - 0xdc00);
      }
      if (code < 0x80) out.push(code);
      else if (code < 0x800) out.push(0xc0 | (code >> 6), 0x80 | (code & 63));
      else if (code < 0x10000) out.push(0xe0 | (code >> 12), 0x80 | ((code >> 6) & 63), 0x80 | (code & 63));
      else out.push(0xf0 | (code >> 18), 0x80 | ((code >> 12) & 63), 0x80 | ((code >> 6) & 63), 0x80 | (code & 63));
    }
    return out;
  }

  // An MLP is either uniform ({width, depth, activation}) or per-layer ({widths, activations}).
  // The canonical form is the uniform one whenever every hidden layer has the same width and
  // activation, so a per-layer spelling of a uniform network keeps the same definition hash and
  // the same store directory as before per-layer plans existed.
  function canonicalMlp(widths, activations) {
    const uniform = widths.every(function (w) { return w === widths[0]; }) &&
      activations.every(function (a) { return a === activations[0]; });
    if (uniform) return { family: "mlp", width: widths[0], depth: widths.length, activation: activations[0] };
    return { family: "mlp", widths: widths.slice(), activations: activations.slice() };
  }
  function normalizeStructure(where, structure) {
    if (!isObject(structure)) fail(where, "structure must be an object such as {family: 'mlp', width: 32, depth: 2}");
    if (SET_FAMILIES.indexOf(structure.family) >= 0) return normalizeSetStructure(where, structure);
    onlyKeys(where + ".structure", structure, ["family", "width", "depth", "widths", "activation", "activations", "l2"]);
    const family = oneOf(where, "structure.family", structure.family, FAMILIES);
    if (family === "linear") {
      if (structure.width !== undefined || structure.depth !== undefined || structure.activation !== undefined ||
          structure.widths !== undefined || structure.activations !== undefined)
        fail(where, "a linear structure takes only l2 (width/depth/widths/activation describe an MLP)");
      return { family: "linear", l2: finiteNumber(where, "structure.l2", structure.l2 === undefined ? 1e-3 : structure.l2, 0) };
    }
    if (structure.l2 !== undefined) fail(where, "structure.l2 applies to linear structures only");
    let widths;
    if (structure.widths !== undefined) {
      if (structure.width !== undefined || structure.depth !== undefined)
        fail(where, "give either structure.widths (per layer) or structure.width/depth (uniform), not both");
      if (!Array.isArray(structure.widths) || !structure.widths.length || structure.widths.length > 64)
        fail(where, "structure.widths must be a non-empty array of at most 64 hidden widths");
      widths = structure.widths.map(function (w, i) { return positiveInt(where, "structure.widths[" + i + "]", w, 4096); });
    } else {
      const width = positiveInt(where, "structure.width", structure.width, 4096);
      const depth = positiveInt(where, "structure.depth", structure.depth === undefined ? 2 : structure.depth, 64);
      widths = [];
      for (let i = 0; i < depth; ++i) widths.push(width);
    }
    let activations;
    if (structure.activations !== undefined) {
      if (structure.activation !== undefined) fail(where, "give either structure.activation or structure.activations, not both");
      if (!Array.isArray(structure.activations) || structure.activations.length !== widths.length)
        fail(where, "structure.activations must name one activation per hidden layer (" + widths.length + ")");
      activations = structure.activations.map(function (a, i) { return oneOf(where, "structure.activations[" + i + "]", a, ACTIVATIONS); });
    } else {
      const activation = oneOf(where, "structure.activation", structure.activation === undefined ? "silu" : structure.activation, ACTIVATIONS);
      activations = widths.map(function () { return activation; });
    }
    return canonicalMlp(widths, activations);
  }
  function widthList(where, key, value, fallback, allowEmpty) {
    if (value === undefined) value = fallback;
    if (!Array.isArray(value) || (!allowEmpty && !value.length) || value.length > 64)
      fail(where, key + " must be " + (allowEmpty ? "an" : "a non-empty") + " array of at most 64 hidden widths");
    return value.map(function (w, i) { return positiveInt(where, key + "[" + i + "]", w, 4096); });
  }
  function indexList(where, key, value) {
    if (value === undefined || value === null) return [];
    if (!Array.isArray(value)) fail(where, key + " must be an array of element-feature indices");
    const out = value.map(function (v, i) {
      if (!Number.isInteger(v) || v < 0 || v > 4095) fail(where, key + "[" + i + "] must be a non-negative integer");
      return v;
    }).sort(function (a, b) { return a - b; });
    for (let i = 1; i < out.length; ++i) if (out[i] === out[i - 1]) fail(where, key + " repeats index " + out[i]);
    return out;
  }
  // DeepSets / message-passing structures. Every key is present in the canonical form, so the
  // definition hash never depends on which defaults an author spelled out.
  //   deepsets: rho([pool_i phi(x_i), context])
  //   mpnn:     h_i = phi(x_i); `rounds` times h_i = update([h_i, agg_{j != i} message([h_i, h_j, x_j[rel] - x_i[rel]])]);
  //             then rho([pool_i h_i, context]). Message/update weights are shared across rounds.
  // Every hidden layer uses `activation`; rho ends in a linear layer to the outputs.
  function normalizeSetStructure(where, structure) {
    const family = structure.family;
    const common = ["family", "elements", "context", "pool", "mask", "phi", "rho", "activation"];
    onlyKeys(where + ".structure", structure, family === "mpnn" ? common.concat(["message", "rounds", "relative", "aggregate"]) : common);
    const out = {
      family: family,
      elements: positiveInt(where, "structure.elements", structure.elements, 4096),
      context: structure.context === undefined ? 0 : (Number.isInteger(structure.context) && structure.context >= 0 ? structure.context
        : fail(where, "structure.context must be a non-negative integer (trailing global inputs)")),
      pool: oneOf(where, "structure.pool", structure.pool === undefined ? "sum" : structure.pool, POOLS),
      mask: structure.mask === undefined || structure.mask === null ? null
        : (Number.isInteger(structure.mask) && structure.mask >= 0 ? structure.mask
          : fail(where, "structure.mask must be an element-feature index (present when its raw value > 0.5) or null")),
      phi: widthList(where, "structure.phi", structure.phi, undefined, false),
      rho: widthList(where, "structure.rho", structure.rho, [], true),
      activation: oneOf(where, "structure.activation", structure.activation === undefined ? "silu" : structure.activation, ACTIVATIONS)
    };
    if (family === "mpnn") {
      out.message = widthList(where, "structure.message", structure.message, [], true);
      out.rounds = positiveInt(where, "structure.rounds", structure.rounds === undefined ? 1 : structure.rounds, 16);
      out.relative = indexList(where, "structure.relative", structure.relative);
      out.aggregate = oneOf(where, "structure.aggregate", structure.aggregate === undefined ? "mean" : structure.aggregate, AGGREGATES);
    }
    return out;
  }
  function hiddenLayers(structure) {
    if (structure.widths) return structure.widths.map(function (w, i) { return [w, structure.activations[i]]; });
    const out = [];
    for (let i = 0; i < structure.depth; ++i) out.push([structure.width, structure.activation]);
    return out;
  }

  // The exported layer plan: [inputs, outputs, activation] per dense layer, matching
  // generic_surrogate_v1/v2 `layers` (weights are [out][in]; the last layer is linear).
  function layerPlan(nInputs, nOutputs, structure) {
    if (SET_FAMILIES.indexOf(structure.family) >= 0) return setPlan(nInputs, nOutputs, structure);
    if (structure.family === "linear") return [[nInputs, nOutputs, "none"]];
    const plan = [];
    let previous = nInputs;
    for (const layer of hiddenLayers(structure)) {
      plan.push([previous, layer[0], layer[1]]);
      previous = layer[0];
    }
    plan.push([previous, nOutputs, "none"]);
    return plan;
  }
  // The exported plan of a set network: the generic_surrogate_v3 `network` block with each
  // dense-layer list reduced to [inputs, outputs, activation].
  function setPlan(nInputs, nOutputs, s) {
    const elementInputs = nInputs - s.context;
    if (elementInputs < s.elements || elementInputs % s.elements !== 0)
      fail("structure", s.family + ": " + nInputs + " inputs minus " + s.context + " context inputs do not split into " +
        s.elements + " equal element blocks");
    const features = elementInputs / s.elements;
    if (s.mask !== null && s.mask >= features) fail("structure", "mask index " + s.mask + " is not one of the " + features + " element features");
    const dense = function (first, widths, activation) {
      const out = [];
      let previous = first;
      for (const w of widths) { out.push([previous, w, activation]); previous = w; }
      return out;
    };
    const phi = dense(features, s.phi, s.activation);
    const hidden = s.phi[s.phi.length - 1];
    const rho = dense(hidden + s.context, s.rho, s.activation);
    rho.push([rho.length ? rho[rho.length - 1][1] : hidden + s.context, nOutputs, "none"]);
    const plan = { kind: s.family, elements: s.elements, element_features: features, context_features: s.context,
      pool: s.pool, mask_feature: s.mask, phi: phi, rho: rho };
    if (s.family === "mpnn") {
      if (s.relative.some(function (i) { return i >= features; }))
        fail("structure", "relative feature indices must be < " + features);
      const message = dense(2 * hidden + s.relative.length, s.message, s.activation);
      message.push([message.length ? message[message.length - 1][1] : 2 * hidden + s.relative.length, hidden, s.activation]);
      plan.message = message;
      plan.update = [[2 * hidden, hidden, s.activation]];
      plan.rounds = s.rounds;
      plan.relative_features = s.relative.slice();
      plan.aggregate = s.aggregate;
    }
    return plan;
  }
  function planParameterCount(plan) {
    const count = function (layers) { return layers.reduce(function (sum, l) { return sum + l[0] * l[1] + l[1]; }, 0); };
    if (Array.isArray(plan)) return count(plan);
    return count(plan.phi) + count(plan.rho) + (plan.message ? count(plan.message) + count(plan.update) : 0);
  }
  function parameterCount(nInputs, nOutputs, structure) {
    return planParameterCount(layerPlan(nInputs, nOutputs, structure));
  }
  function signatureFromPlan(inputs, outputs, links, plan) {
    const allIdentity = links.every(function (l) { return l === "identity"; });
    return {
      format: "generic_surrogate",
      model: !Array.isArray(plan) ? "generic_surrogate_v3" : allIdentity ? "generic_surrogate_v1" : "generic_surrogate_v2",
      inputs: inputs.slice(), outputs: outputs.slice(), links: links.slice(),
      layers: JSON.parse(JSON.stringify(plan))
    };
  }
  function structureIdOf(signature) {
    return "s" + fnv1a64(canonical(signature)).slice(0, 12);
  }
  function describeStructure(structure) {
    if (!structure) return "unknown";
    if (structure.family === "linear") return structure.l2 === undefined ? "linear" : "linear(l2=" + structure.l2 + ")";
    if (structure.family === "mlp" && structure.widths) {
      const sameAct = structure.activations.every(function (a) { return a === structure.activations[0]; });
      return "mlp(" + (sameAct ? structure.widths.join("→") + "," + structure.activations[0]
        : structure.widths.map(function (w, i) { return w + ":" + structure.activations[i]; }).join("→")) + ")";
    }
    if (structure.family === "mlp") return "mlp(width=" + structure.width + ",depth=" + structure.depth + "," + structure.activation + ")";
    if (structure.family === "layers") return Array.isArray(structure.plan)
      ? "layers(" + structure.plan.map(function (l) { return l[1]; }).join("→") + ")" : "layers(" + structure.plan.kind + ")";
    if (structure.family === "deepsets" || structure.family === "mpnn") {
      const parts = [structure.elements + " elements" + (structure.context ? " + " + structure.context + " context" : ""),
        "phi " + structure.phi.join("→")];
      if (structure.family === "mpnn") parts.push("message→" + structure.message.concat(["h"]).join("→") + " ×" + structure.rounds +
        " " + structure.aggregate + (structure.relative.length ? " rel[" + structure.relative.join(",") + "]" : ""));
      parts.push(structure.pool + " pool", "rho " + (structure.rho.length ? structure.rho.join("→") : "linear"), structure.activation);
      if (structure.mask !== null) parts.push("mask " + structure.mask);
      return structure.family + "(" + parts.join(", ") + ")";
    }
    return String(structure.family);
  }

  // Read the structure an exported generic_surrogate checkpoint actually carries. This is what
  // makes conflicting checkpoints impossible to register under the wrong definition: the store
  // compares this, not a file name or a trainer's claim.
  function densePlanOf(layers, label) {
    if (!Array.isArray(layers) || !layers.length) fail("checkpoint", label + " has no dense layers");
    const plan = layers.map(function (layer, index) {
      const w = layer.weights;
      if (!Array.isArray(w) || !w.length || !Array.isArray(w[0])) fail("checkpoint", label + " layer " + index + " has no weight matrix");
      return [w[0].length, w.length, layer.activation || "none"];
    });
    for (let i = 1; i < plan.length; ++i)
      if (plan[i][0] !== plan[i - 1][1]) fail("checkpoint", label + " layer " + i + " input width does not chain from layer " + (i - 1));
    return plan;
  }
  function setSignature(model, inputs, outputs) {
    const n = model.network;
    if (!isObject(n) || SET_FAMILIES.indexOf(n.kind) < 0) fail("checkpoint", "generic_surrogate_v3 needs network.kind deepsets/mpnn");
    const plan = { kind: n.kind, elements: n.elements, element_features: n.element_features, context_features: n.context_features || 0,
      pool: n.pool || "sum", mask_feature: n.mask_feature === undefined ? null : n.mask_feature,
      phi: densePlanOf(n.phi, "phi"), rho: densePlanOf(n.rho, "rho") };
    const hidden = plan.phi[plan.phi.length - 1][1];
    if (!Number.isInteger(plan.elements) || !Number.isInteger(plan.element_features) ||
        plan.elements * plan.element_features + plan.context_features !== inputs.length)
      fail("checkpoint", "set layout does not match its " + inputs.length + " named inputs");
    if (plan.phi[0][0] !== plan.element_features || plan.rho[0][0] !== hidden + plan.context_features ||
        plan.rho[plan.rho.length - 1][1] !== outputs.length)
      fail("checkpoint", "phi/rho widths do not chain to the element features and named outputs");
    if (n.kind === "mpnn") {
      plan.message = densePlanOf(n.message, "message");
      plan.update = densePlanOf(n.update, "update");
      plan.rounds = n.rounds;
      plan.relative_features = Array.isArray(n.relative_features) ? n.relative_features.slice() : [];
      plan.aggregate = n.aggregate || "mean";
      if (plan.message[0][0] !== 2 * hidden + plan.relative_features.length || plan.message[plan.message.length - 1][1] !== hidden ||
          plan.update.length !== 1 || plan.update[0][0] !== 2 * hidden || plan.update[0][1] !== hidden)
        fail("checkpoint", "message/update widths do not match the element state width " + hidden);
    }
    return plan;
  }
  function checkpointSignature(model) {
    if (!isObject(model)) fail("checkpoint", "is not a JSON object");
    const kind = model.model;
    if (kind !== "generic_surrogate_v1" && kind !== "generic_surrogate_v2" && kind !== "generic_surrogate_v3")
      fail("checkpoint", "unsupported model kind " + JSON.stringify(kind) + " (expected generic_surrogate_v1/v2/v3)");
    const inputs = model.input_features, outputs = model.output_features;
    if (!Array.isArray(inputs) || !Array.isArray(outputs)) fail("checkpoint", "missing input_features/output_features");
    if (kind === "generic_surrogate_v3") {
      const links = Array.isArray(model.output_transforms) ? model.output_transforms.slice() : outputs.map(function () { return "identity"; });
      return signatureFromPlan(inputs, outputs, links, setSignature(model, inputs, outputs));
    }
    const layers = kind === "generic_surrogate_v2" ? (model.network && model.network.layers) : model.layers;
    if (!Array.isArray(layers) || !layers.length) fail("checkpoint", "has no dense layers");
    const plan = layers.map(function (layer, index) {
      const w = layer.weights;
      if (!Array.isArray(w) || !w.length || !Array.isArray(w[0])) fail("checkpoint", "layer " + index + " has no weight matrix");
      return [w[0].length, w.length, layer.activation || "none"];
    });
    for (let i = 1; i < plan.length; ++i)
      if (plan[i][0] !== plan[i - 1][1]) fail("checkpoint", "layer " + i + " input width does not chain from layer " + (i - 1));
    if (plan[0][0] !== inputs.length || plan[plan.length - 1][1] !== outputs.length)
      fail("checkpoint", "layer plan does not match its named inputs/outputs");
    const links = kind === "generic_surrogate_v2" && Array.isArray(model.output_transforms)
      ? model.output_transforms.slice() : outputs.map(function () { return "identity"; });
    return signatureFromPlan(inputs, outputs, links, plan);
  }
  function structureFromPlan(plan) {
    if (!Array.isArray(plan)) {
      const hiddenActs = plan.phi.concat(plan.rho.slice(0, -1), plan.message || [], plan.update || []).map(function (l) { return l[2]; });
      if (plan.rho[plan.rho.length - 1][2] !== "none" || ACTIVATIONS.indexOf(hiddenActs[0]) < 0 ||
          hiddenActs.some(function (a) { return a !== hiddenActs[0]; }))
        return { family: "layers", plan: plan };
      const structure = { family: plan.kind, elements: plan.elements, context: plan.context_features, pool: plan.pool,
        mask: plan.mask_feature, phi: plan.phi.map(function (l) { return l[1]; }),
        rho: plan.rho.slice(0, -1).map(function (l) { return l[1]; }), activation: hiddenActs[0] };
      if (plan.kind === "mpnn") Object.assign(structure, { message: plan.message.slice(0, -1).map(function (l) { return l[1]; }),
        rounds: plan.rounds, relative: plan.relative_features.slice(), aggregate: plan.aggregate });
      return normalizeSetStructure("checkpoint", structure);
    }
    if (plan.length === 1 && plan[0][2] === "none") return { family: "linear" };
    const hidden = plan.slice(0, -1);
    const exportable = plan[plan.length - 1][2] === "none" &&
      hidden.every(function (l) { return ACTIVATIONS.indexOf(l[2]) >= 0; });
    if (!exportable) return { family: "layers", plan: plan };
    return canonicalMlp(hidden.map(function (l) { return l[1]; }), hidden.map(function (l) { return l[2]; }));
  }

  function normalizeTraining(where, training, requireSelection) {
    training = training || {};
    if (!isObject(training)) fail(where, "training must be an object");
    onlyKeys(where + ".training", training, ["source", "tag", "expand", "runs", "validationRuns", "testRuns",
      "calibrationRuns", "intervalCoverage", "epochs", "lr", "lrFinalFactor", "seed", "holdout", "teacher", "measured",
      "torchscript", "note"]);
    const out = {
      source: oneOf(where, "training.source", training.source === undefined ? "scores" : training.source, SOURCES),
      tag: training.tag === undefined ? null : String(training.tag),
      expand: training.expand === undefined ? null : String(training.expand),
      runs: pathList(where, "training.runs", training.runs),
      validationRuns: pathList(where, "training.validationRuns", training.validationRuns),
      testRuns: pathList(where, "training.testRuns", training.testRuns),
      // Runs that set the carried error bar (a split-conformal prediction interval), kept apart
      // from the test runs so the validator's error-bar check is an independent one.
      calibrationRuns: pathList(where, "training.calibrationRuns", training.calibrationRuns),
      intervalCoverage: finiteNumber(where, "training.intervalCoverage", training.intervalCoverage === undefined ? 0.9 : training.intervalCoverage, 0.5, 1),
      epochs: positiveInt(where, "training.epochs", training.epochs === undefined ? 400 : training.epochs, 1000000),
      lr: finiteNumber(where, "training.lr", training.lr === undefined ? 1e-2 : training.lr, 1e-12),
      lrFinalFactor: finiteNumber(where, "training.lrFinalFactor", training.lrFinalFactor === undefined ? 1 : training.lrFinalFactor, 1e-12),
      seed: training.seed === undefined ? 1234 : training.seed,
      holdout: finiteNumber(where, "training.holdout", training.holdout === undefined ? 0.25 : training.holdout, 0, 0.51),
      teacher: training.teacher === undefined ? null : String(training.teacher),
      measured: training.measured === undefined ? null : !!training.measured,
      torchscript: !!training.torchscript,
      note: training.note === undefined ? null : String(training.note)
    };
    if (!Number.isInteger(out.seed) || out.seed < 0) fail(where, "training.seed must be a non-negative integer");
    if (out.source === "hook_emits" && !out.tag) fail(where, "training.tag is required for source 'hook_emits'");
    if (out.expand && out.source !== "hook_emits") fail(where, "training.expand applies to source 'hook_emits' only");
    if (requireSelection === true && !out.validationRuns.length)
      fail(where, "a structure search needs training.validationRuns (selection runs, disjoint from training runs) or runFolds >= 2");
    const overlap = function (a, b) { return a.filter(function (p) { return b.indexOf(p) >= 0; }); };
    const clash = overlap(out.runs, out.validationRuns).concat(overlap(out.runs, out.testRuns), overlap(out.validationRuns, out.testRuns),
      overlap(out.calibrationRuns, out.runs), overlap(out.calibrationRuns, out.validationRuns), overlap(out.calibrationRuns, out.testRuns));
    if (clash.length) fail(where, "training/validation/test/calibration run lists must be disjoint; repeated: " + clash.join(", "));
    return out;
  }

  function normalizeLinks(where, outputs, links) {
    if (links === undefined) return outputs.map(function () { return "identity"; });
    if (!isObject(links)) fail(where, "links must map output names to identity/exp/sigmoid");
    for (const key of Object.keys(links)) {
      if (outputs.indexOf(key) < 0) fail(where, "links names unknown output '" + key + "'");
      oneOf(where, "links." + key, links[key], LINKS);
    }
    return outputs.map(function (o) { return links[o] || "identity"; });
  }

  function normalizeBase(where, spec, requireSelection) {
    if (typeof spec.name !== "string" || !NAME_PATTERN.test(spec.name))
      fail(where, "name must match " + NAME_PATTERN + " (it names the store directory and the scenario model)");
    const inputs = columns(where, "inputs", spec.inputs);
    const outputs = columns(where, "outputs", spec.outputs);
    for (const o of outputs) if (inputs.indexOf(o) >= 0) fail(where, "'" + o + "' is both an input and an output");
    return {
      name: spec.name,
      description: spec.description === undefined ? "" : String(spec.description),
      scale: spec.scale === undefined ? null : oneOf(where, "scale", spec.scale, SCALES),
      inputs: inputs,
      outputs: outputs,
      links: normalizeLinks(where, outputs, spec.links),
      training: normalizeTraining(where, spec.training, requireSelection),
      tags: Array.isArray(spec.tags) ? spec.tags.map(String) : []
    };
  }

  function finishDefinition(base, structure, extra) {
    const plan = layerPlan(base.inputs.length, base.outputs.length, structure);
    const signature = signatureFromPlan(base.inputs, base.outputs, base.links, plan);
    const definition = Object.assign({
      schema: DEFINITION_SCHEMA,
      name: base.name,
      description: base.description,
      scale: base.scale,
      inputs: base.inputs,
      outputs: base.outputs,
      links: base.links,
      structure: structure,
      structure_label: describeStructure(structure),
      structure_id: structureIdOf(signature),
      parameter_count: parameterCount(base.inputs.length, base.outputs.length, structure),
      signature: signature,
      training: base.training,
      tags: base.tags
    }, extra || {});
    definition.definition_hash = "fnv1a64:" + fnv1a64(canonical(definition));
    return definition;
  }

  function defineModel(spec) {
    const where = "defineModel(" + (spec && spec.name ? spec.name : "?") + ")";
    if (!isObject(spec)) fail("defineModel", "expects an object");
    onlyKeys(where, spec, ["name", "description", "scale", "inputs", "outputs", "links", "structure", "training", "tags"]);
    const base = normalizeBase(where, spec, false);
    const definition = finishDefinition(base, normalizeStructure(where, spec.structure));
    if (declared.definitions.some(function (d) { return d.name === definition.name; }))
      fail(where, "model '" + definition.name + "' is defined twice in the same evaluation");
    declared.definitions.push(definition);
    return definition;
  }

  function axis(where, key, value, fallback) {
    if (value === undefined) return fallback;
    if (Array.isArray(value)) {
      if (!value.length) fail(where, key + " must not be empty");
      value.forEach(function (v) { positiveInt(where, key + "[]", v, 4096); });
      return value.slice().sort(function (a, b) { return a - b; }).filter(function (v, i, a) { return i === 0 || a[i - 1] !== v; });
    }
    if (!isObject(value)) fail(where, key + " must be an array of integers or {min, max, step|factor}");
    const min = positiveInt(where, key + ".min", value.min, 4096);
    const max = positiveInt(where, key + ".max", value.max, 4096);
    if (max < min) fail(where, key + ".max must be >= min");
    const out = [];
    if (value.factor !== undefined) {
      const factor = finiteNumber(where, key + ".factor", value.factor, 1.000001);
      for (let v = min; v <= max; v = Math.max(v + 1, Math.round(v * factor))) out.push(v);
    } else {
      const step = positiveInt(where, key + ".step", value.step === undefined ? 1 : value.step, 4096);
      for (let v = min; v <= max; v += step) out.push(v);
    }
    if (out.length > 4096) fail(where, key + " expands to more than 4096 values");
    return out;
  }

  function defineSearch(spec) {
    const where = "defineSearch(" + (spec && spec.name ? spec.name : "?") + ")";
    if (!isObject(spec)) fail("defineSearch", "expects an object");
    onlyKeys(where, spec, ["name", "description", "scale", "inputs", "outputs", "links", "training", "tags",
      "strategy", "space", "budget", "seed", "objective", "complexityPenalty", "generate", "activate", "keepCandidates",
      "repeats", "selectionRule", "runFolds"]);
    const strategy = oneOf(where, "strategy", spec.strategy === undefined ? "grid" : spec.strategy, STRATEGIES);
    const folds = spec.runFolds === undefined || spec.runFolds === 0 || spec.runFolds === 1 ? 0 : positiveInt(where, "runFolds", spec.runFolds, 32);
    const base = normalizeBase(where, spec, folds ? "folds" : true);
    const space = spec.space || {};
    if (!isObject(space)) fail(where, "space must be an object");
    onlyKeys(where + ".space", space, ["families", "width", "depth", "l2", "activations", "shapes", "layouts", "set", "rounds"]);
    const families = space.families === undefined ? ["mlp"] : space.families;
    if (!Array.isArray(families) || !families.length) fail(where, "space.families must be a non-empty array");
    families.forEach(function (f) { oneOf(where, "space.families[]", f, FAMILIES); });
    const l2 = space.l2 === undefined ? [1e-3] : space.l2;
    if (!Array.isArray(l2) || !l2.length) fail(where, "space.l2 must be a non-empty array of numbers");
    l2.forEach(function (v) { finiteNumber(where, "space.l2[]", v, 0); });
    const activations = space.activations === undefined ? ["silu"] : space.activations;
    if (!Array.isArray(activations) || !activations.length) fail(where, "space.activations must be a non-empty array");
    activations.forEach(function (a) { oneOf(where, "space.activations[]", a, ACTIVATIONS); });
    const shapes = space.shapes === undefined ? ["uniform"] : space.shapes;
    if (!Array.isArray(shapes) || !shapes.length) fail(where, "space.shapes must be a non-empty array");
    shapes.forEach(function (sh) { oneOf(where, "space.shapes[]", sh, SHAPES); });
    const layouts = space.layouts === undefined ? [] : space.layouts;
    if (!Array.isArray(layouts)) fail(where, "space.layouts must be an array of per-layer width arrays");
    layouts.forEach(function (layout, i) {
      if (!Array.isArray(layout) || !layout.length || layout.length > 64) fail(where, "space.layouts[" + i + "] must be a non-empty array of hidden widths");
      layout.forEach(function (w) { positiveInt(where, "space.layouts[" + i + "][]", w, 4096); });
    });
    if (layouts.length && families.indexOf("mlp") < 0) fail(where, "space.layouts needs 'mlp' in space.families");
    const wantsSet = families.some(function (f) { return SET_FAMILIES.indexOf(f) >= 0; });
    let setSpace = null;
    if (wantsSet) {
      if (!isObject(space.set)) fail(where, "space.set ({elements, context, pool, mask, relative, aggregate}) is required for deepsets/mpnn families");
      onlyKeys(where + ".space.set", space.set, ["elements", "context", "pool", "mask", "relative", "aggregate"]);
      // Validate once through the structure normalizer with a placeholder phi.
      const probe = normalizeSetStructure(where + ".space.set", Object.assign({ family: "mpnn", phi: [1] }, space.set));
      setSpace = { elements: probe.elements, context: probe.context, pool: probe.pool, mask: probe.mask, relative: probe.relative,
        aggregate: probe.aggregate };
    } else if (space.set !== undefined || space.rounds !== undefined) {
      fail(where, "space.set/space.rounds apply to deepsets/mpnn families only");
    }
    const rounds = space.rounds === undefined ? [1] : space.rounds;
    if (!Array.isArray(rounds) || !rounds.length) fail(where, "space.rounds must be a non-empty array");
    rounds.forEach(function (r) { positiveInt(where, "space.rounds[]", r, 16); });
    const budget = spec.budget || {};
    if (!isObject(budget)) fail(where, "budget must be an object");
    onlyKeys(where + ".budget", budget, ["maxCandidates", "maxParameters", "seconds", "generations", "population"]);
    const search = {
      schema: SEARCH_SCHEMA,
      name: base.name,
      description: base.description,
      scale: base.scale,
      inputs: base.inputs,
      outputs: base.outputs,
      links: base.links,
      training: base.training,
      tags: base.tags,
      strategy: strategy,
      space: {
        families: families.slice(),
        width: axis(where, "space.width", space.width, [8, 16, 32, 64]),
        depth: axis(where, "space.depth", space.depth, [1, 2, 3]),
        l2: l2.slice(),
        activations: activations.slice(),
        shapes: shapes.slice(),
        layouts: layouts.map(function (l) { return l.slice(); }),
        set: setSpace,
        rounds: rounds.slice()
      },
      budget: {
        maxCandidates: positiveInt(where, "budget.maxCandidates", budget.maxCandidates === undefined ? 24 : budget.maxCandidates, 10000),
        maxParameters: positiveInt(where, "budget.maxParameters", budget.maxParameters === undefined ? 200000 : budget.maxParameters, 1e9),
        seconds: finiteNumber(where, "budget.seconds", budget.seconds === undefined ? 0 : budget.seconds, 0),
        generations: positiveInt(where, "budget.generations", budget.generations === undefined ? 8 : budget.generations, 10000),
        population: positiveInt(where, "budget.population", budget.population === undefined ? 12 : budget.population, 10000)
      },
      seed: spec.seed === undefined ? base.training.seed : spec.seed,
      objective: spec.objective === undefined ? "r2_min" : spec.objective,
      complexityPenalty: finiteNumber(where, "complexityPenalty", spec.complexityPenalty === undefined ? 0 : spec.complexityPenalty, 0),
      activate: !!spec.activate,
      keepCandidates: spec.keepCandidates === undefined ? 3 : positiveIntOrZero(where, "keepCandidates", spec.keepCandidates),
      // Train every candidate with this many seeds (training.seed, +1, ...) and rank on the mean
      // selection loss, so the report measures selection noise between close structures.
      repeats: spec.repeats === undefined ? 1 : positiveInt(where, "repeats", spec.repeats, 32),
      selectionRule: oneOf(where, "selectionRule", spec.selectionRule === undefined ? "min_loss" : spec.selectionRule, SELECTION_RULES),
      // Rotate which WHOLE runs select: the pooled runs + validationRuns are dealt into this many
      // folds; each candidate is trained on all but one fold and scored on the held-out fold, so
      // the reported spread includes run-to-run sampling noise, not only initialization noise.
      runFolds: folds,
      custom_objective: typeof spec.objective === "function",
      custom_generator: typeof spec.generate === "function"
    };
    if (!Number.isInteger(search.seed) || search.seed < 0) fail(where, "seed must be a non-negative integer");
    if (typeof search.objective !== "function") oneOf(where, "objective", search.objective, OBJECTIVES);
    if (strategy === "custom" && typeof spec.generate !== "function")
      fail(where, "strategy 'custom' needs generate(space, helpers) returning structures");
    if (strategy !== "custom" && spec.generate !== undefined) fail(where, "generate applies to strategy 'custom' only");
    if (search.selectionRule === "one_standard_error" && search.repeats < 2 && !folds)
      fail(where, "selectionRule 'one_standard_error' needs repeats >= 2 or runFolds >= 2 (the standard error is measured across seeds or folds)");
    if (strategy === "evolvo") {
      if (activations.length !== 1 || activations[0] !== "silu" || shapes.length !== 1 || shapes[0] !== "uniform" || layouts.length)
        fail(where, "the evolvo strategy searches uniform SiLU width/depth only (no activations/shapes/layouts)");
      if (search.repeats !== 1) fail(where, "the evolvo strategy does not repeat seeds; use grid/random for repeats");
      if (folds) fail(where, "the evolvo strategy does not rotate selection runs; use grid/random for runFolds");
      if (base.links.some(function (l) { return l !== "identity"; })) fail(where, "the evolvo strategy does not export output links; use grid/random");
      if (!base.training.testRuns.length) fail(where, "the evolvo strategy needs training.testRuns (untouched test runs)");
      if (families.indexOf("mlp") < 0 || families.length !== 1) fail(where, "the evolvo strategy searches MLP width/depth only (space.families = ['mlp'])");
      if (search.custom_objective) fail(where, "the evolvo strategy uses its own validation-MSE objective");
    }
    // Functions are kept off the serializable record but stay callable by the orchestrator.
    Object.defineProperty(search, "objectiveFunction", { value: typeof spec.objective === "function" ? spec.objective : null, enumerable: false });
    Object.defineProperty(search, "generateFunction", { value: typeof spec.generate === "function" ? spec.generate : null, enumerable: false });
    const serial = JSON.parse(JSON.stringify(search));
    delete serial.objective;
    search.search_hash = "fnv1a64:" + fnv1a64(canonical(Object.assign(serial, {
      objective_source: typeof spec.objective === "function" ? String(spec.objective) : spec.objective,
      generate_source: typeof spec.generate === "function" ? String(spec.generate) : null
    })));
    if (typeof search.objective === "function") search.objective = "custom";
    if (declared.searches.some(function (s) { return s.name === search.name; }))
      fail(where, "search '" + search.name + "' is defined twice in the same evaluation");
    declared.searches.push(search);
    return search;
  }
  function positiveIntOrZero(where, key, value) {
    if (!Number.isInteger(value) || value < 0) fail(where, key + " must be a non-negative integer");
    return value;
  }

  // Deterministic 32-bit generator (mulberry32, the same one js/trech_random.js exposes),
  // inlined so this file has no include-order dependency.
  function mulberry32(seed) {
    let state = seed >>> 0;
    return function () {
      state = (state + 0x6D2B79F5) | 0;
      let t = Math.imul(state ^ (state >>> 15), 1 | state);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // Hidden widths of a shape: "uniform" repeats the width; "taper" halves it each layer
  // (never below 2), the usual funnel toward a small output.
  function shapeWidths(shape, width, depth) {
    const out = [];
    for (let i = 0; i < depth; ++i) out.push(shape === "taper" ? Math.max(2, Math.round(width / Math.pow(2, i))) : width);
    return out;
  }
  // Grid order: family → depth → width → shape → activation, then explicit layouts × activation.
  // With the default space (silu, uniform, no layouts) this is the original family → depth → width.
  function gridStructures(space) {
    const out = [];
    const activations = space.activations || ["silu"], shapes = space.shapes || ["uniform"];
    for (const family of space.families) {
      if (family === "linear") { for (const l2 of space.l2) out.push({ family: "linear", l2: l2 }); continue; }
      if (SET_FAMILIES.indexOf(family) >= 0) {
        // phi takes the shape's widths, rho one hidden layer of the base width; mpnn crosses rounds.
        for (const depth of space.depth) for (const width of space.width) for (const shape of shapes) for (const activation of activations) {
          const s = { family: family, elements: space.set.elements, context: space.set.context, pool: space.set.pool, mask: space.set.mask,
            phi: shapeWidths(shape, width, depth), rho: [width], activation: activation };
          if (family === "deepsets") { out.push(s); continue; }
          for (const r of space.rounds || [1])
            out.push(Object.assign({}, s, { message: [], rounds: r, relative: space.set.relative, aggregate: space.set.aggregate }));
        }
        continue;
      }
      for (const depth of space.depth) for (const width of space.width) for (const shape of shapes) for (const activation of activations)
        out.push({ family: "mlp", widths: shapeWidths(shape, width, depth), activation: activation });
      for (const layout of space.layouts || []) for (const activation of activations)
        out.push({ family: "mlp", widths: layout.slice(), activation: activation });
    }
    return out;
  }

  // The candidate DEFINITIONS a search would train, in evaluation order. Every candidate keeps
  // the search's model name; distinct structures get distinct structure_ids and therefore
  // distinct store directories. Duplicates and over-budget structures are dropped, with a reason.
  function candidates(search) {
    if (!search || search.schema !== SEARCH_SCHEMA) fail("candidates", "expects a defineSearch() result");
    if (search.strategy === "evolvo") return { candidates: [], skipped: [], note: "evolvo proposes structures while it trains" };
    let structures;
    if (search.strategy === "custom") {
      const helpers = { random: mulberry32(search.seed), grid: function () { return gridStructures(search.space); }, parameterCount: function (s) {
        return parameterCount(search.inputs.length, search.outputs.length, normalizeStructure("generate", s));
      } };
      structures = search.generateFunction(JSON.parse(JSON.stringify(search.space)), helpers);
      if (!Array.isArray(structures)) fail("candidates(" + search.name + ")", "generate() must return an array of structures");
    } else {
      structures = gridStructures(search.space);
      if (search.strategy === "random") {
        const rng = mulberry32(search.seed);
        for (let i = structures.length - 1; i > 0; --i) {
          const j = Math.floor(rng() * (i + 1));
          const tmp = structures[i]; structures[i] = structures[j]; structures[j] = tmp;
        }
      }
    }
    const base = { name: search.name, description: search.description, scale: search.scale, inputs: search.inputs,
      outputs: search.outputs, links: search.links, training: search.training, tags: search.tags };
    const out = [], skipped = [], seen = {};
    for (const raw of structures) {
      const structure = normalizeStructure("candidates(" + search.name + ")", raw);
      const definition = finishDefinition(base, structure, { search: search.name, search_hash: search.search_hash });
      // Same exported structure, different training hyperparameter (linear l2) = distinct candidate.
      const key = definition.structure_id + " " + definition.structure_label;
      if (seen[key]) { skipped.push({ structure: describeStructure(structure), reason: "duplicate structure" }); continue; }
      seen[key] = true;
      if (definition.parameter_count > search.budget.maxParameters) {
        skipped.push({ structure: describeStructure(structure), reason: "parameter budget (" + definition.parameter_count + " > " + search.budget.maxParameters + ")" });
        continue;
      }
      if (out.length >= search.budget.maxCandidates) { skipped.push({ structure: describeStructure(structure), reason: "candidate budget" }); continue; }
      out.push(definition);
    }
    return { candidates: out, skipped: skipped };
  }

  // Selection loss (lower is better) from a trainer's per-output selection metrics
  // ({output: {r2, mae, rmse}}). Missing/non-finite metrics make the candidate unrankable.
  function score(search, metrics, definition) {
    if (!isObject(metrics)) return null;
    const rows = search.outputs.map(function (o) { return metrics[o]; });
    if (rows.some(function (r) { return !isObject(r); })) return null;
    let loss;
    if (search.objectiveFunction) {
      loss = search.objectiveFunction(JSON.parse(JSON.stringify(metrics)), { structure: definition.structure,
        parameter_count: definition.parameter_count, structure_id: definition.structure_id });
    } else if (search.objective === "r2_min") {
      loss = 1 - Math.min.apply(null, rows.map(function (r) { return r.r2; }));
    } else if (search.objective === "r2_mean") {
      loss = 1 - rows.reduce(function (s, r) { return s + r.r2; }, 0) / rows.length;
    } else if (search.objective === "rmse_mean") {
      loss = rows.reduce(function (s, r) { return s + r.rmse; }, 0) / rows.length;
    } else {
      // RMSE relative to the selection data spread (sqrt(1 - R²) when R² ≤ 1).
      loss = rows.reduce(function (s, r) { return s + Math.sqrt(Math.max(0, 1 - r.r2)); }, 0) / rows.length;
    }
    if (typeof loss !== "number" || !Number.isFinite(loss)) return null;
    return loss + search.complexityPenalty * definition.parameter_count;
  }

  // Deterministic ranking: loss, then fewer parameters, then structure_id.
  function rank(results) {
    return results.slice().sort(function (a, b) {
      const la = a.loss === null || a.loss === undefined ? Infinity : a.loss;
      const lb = b.loss === null || b.loss === undefined ? Infinity : b.loss;
      if (la !== lb) return la < lb ? -1 : 1;
      if (a.parameter_count !== b.parameter_count) return a.parameter_count - b.parameter_count;
      const ka = a.structure_id + " " + (a.structure_label || ""), kb = b.structure_id + " " + (b.structure_label || "");
      return ka < kb ? -1 : ka > kb ? 1 : 0;
    });
  }

  // Per-candidate loss statistics over repeated seeds: mean, sample standard deviation and
  // standard error. One seed gives a mean and an unmeasured (null) spread, never a fake 0.
  function lossStats(losses) {
    const values = (losses || []).filter(function (v) { return typeof v === "number" && Number.isFinite(v); });
    if (!values.length || values.length !== (losses || []).length) return { mean: null, std: null, stderr: null, n: values.length };
    const mean = values.reduce(function (s, v) { return s + v; }, 0) / values.length;
    if (values.length < 2) return { mean: mean, std: null, stderr: null, n: 1 };
    const variance = values.reduce(function (s, v) { return s + (v - mean) * (v - mean); }, 0) / (values.length - 1);
    const std = Math.sqrt(variance);
    return { mean: mean, std: std, stderr: std / Math.sqrt(values.length), n: values.length };
  }

  // Deal whole runs into `k` selection folds: sorted, shuffled with the search seed (mulberry32),
  // then round-robin, so the same runs + seed always give the same folds. Fold i selects on its
  // runs and trains on every other fold's runs. Runs are never split across folds.
  function runFolds(runs, k, seed) {
    if (!Number.isInteger(k) || k < 2) fail("runFolds", "needs k >= 2 folds");
    const pool = (runs || []).map(String).sort().filter(function (r, i, a) { return i === 0 || a[i - 1] !== r; });
    if (pool.length < k) fail("runFolds", "needs at least " + k + " distinct runs (one per fold), got " + pool.length);
    const rng = mulberry32(seed >>> 0);
    for (let i = pool.length - 1; i > 0; --i) {
      const j = Math.floor(rng() * (i + 1));
      const tmp = pool[i]; pool[i] = pool[j]; pool[j] = tmp;
    }
    const folds = [];
    for (let i = 0; i < k; ++i) folds.push([]);
    pool.forEach(function (run, i) { folds[i % k].push(run); });
    return folds.map(function (selection, i) {
      selection.sort();
      const training = [];
      folds.forEach(function (other, j) { if (j !== i) training.push.apply(training, other); });
      return { fold: i, selection: selection, training: training.sort() };
    });
  }

  // Loss statistics of a fold-rotated candidate: `foldLosses[f][s]` is the selection loss of
  // fold f under seed s. The candidate loss is the mean of the per-fold means; its standard error
  // is taken ACROSS folds (between-run sampling noise, which already contains seed noise); the
  // within-fold seed spread is reported separately.
  function foldStats(foldLosses) {
    const means = (foldLosses || []).map(function (seeds) { return lossStats(seeds).mean; });
    if (!means.length || means.some(function (m) { return m === null; })) return { mean: null, std: null, stderr: null, n: 0, fold_means: means, seed_std: null };
    const across = lossStats(means);
    let pooled = 0, dof = 0;
    for (const seeds of foldLosses) {
      const st = lossStats(seeds);
      if (st.std !== null) { pooled += st.std * st.std * (seeds.length - 1); dof += seeds.length - 1; }
    }
    return { mean: across.mean, std: across.std, stderr: across.stderr, n: means.length, fold_means: means,
      seed_std: dof ? Math.sqrt(pooled / dof) : null };
  }

  // Choose the winner of ranked results ({loss, loss_stderr, parameter_count, structure_id, ...},
  // already in rank() order) and report how trustworthy that choice is.
  // - `tied`: candidates whose mean loss is within two combined standard errors of the best
  //   (the best and they are not distinguishable at ~95% under repeated seeds);
  // - `distinguishable`: whether the runner-up is outside that band (null when the spread was
  //   not measured, i.e. one seed);
  // - rule "one_standard_error": the fewest-parameter candidate whose mean loss is within one
  //   standard error of the best mean (the classic parsimony rule); "min_loss" keeps rank 1.
  function select(search, ranked) {
    const rule = (search && search.selectionRule) || "min_loss";
    if (!ranked.length) return { rule: rule, winner: null, tied: [], distinguishable: null, measured: false };
    const best = ranked[0];
    const measured = ranked.every(function (r) { return typeof r.loss_stderr === "number"; });
    // Fold-rotated candidates are scored on the SAME folds, so the comparison is paired: the
    // band is two standard errors of the per-fold loss differences (the fold-to-fold difficulty
    // shared by both candidates cancels). Otherwise two combined independent standard errors.
    const paired = function (r) {
      const a = best.fold_means, b = r.fold_means;
      if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length || a.length < 2) return null;
      return lossStats(b.map(function (v, i) { return v - a[i]; }));
    };
    const band = function (r) {
      const d = paired(r);
      if (d && d.stderr !== null) return 2 * d.stderr;
      return 2 * Math.sqrt(Math.pow(best.loss_stderr || 0, 2) + Math.pow(r.loss_stderr || 0, 2));
    };
    const tied = measured ? ranked.slice(1).filter(function (r) { return r.loss - best.loss <= band(r); }) : [];
    const runnerUp = ranked[1] || null;
    let winner = best;
    if (rule === "one_standard_error" && measured) {
      const limit = best.loss + best.loss_stderr;
      const pool = ranked.filter(function (r) { return r.loss <= limit; });
      pool.sort(function (a, b) {
        if (a.parameter_count !== b.parameter_count) return a.parameter_count - b.parameter_count;
        if (a.loss !== b.loss) return a.loss < b.loss ? -1 : 1;
        const ka = a.structure_id + " " + (a.structure_label || ""), kb = b.structure_id + " " + (b.structure_label || "");
        return ka < kb ? -1 : ka > kb ? 1 : 0;
      });
      winner = pool[0];
    }
    return {
      rule: rule,
      measured: measured,
      paired: !!(runnerUp && paired(runnerUp)),
      winner: winner,
      best_mean: best,
      runner_up: runnerUp,
      gap_to_runner_up: runnerUp ? runnerUp.loss - best.loss : null,
      band_to_runner_up: runnerUp && measured ? band(runnerUp) : null,
      distinguishable: runnerUp ? (measured ? !(runnerUp.loss - best.loss <= band(runnerUp)) : null) : true,
      tied: tied
    };
  }

  // ---- Registry resolution (read-only; the Node store is the only writer) -------------------

  function eligible(entry, opts) {
    const roles = opts.roles || ["final", "best"];
    return entry.checkpoints.filter(function (c) {
      if (roles.indexOf(c.role) < 0) return false;
      if (opts.structure_id && c.structure_id !== opts.structure_id) return false;
      return true;
    });
  }

  // Pick one checkpoint of a registered model. Order: an explicit version; otherwise the model's
  // active checkpoint; otherwise the newest final/best version. With a definition, any
  // checkpoint whose structure_id differs is a conflict and is refused, never silently loaded.
  function resolve(index, name, opts) {
    opts = opts || {};
    if (!index || index.schema !== REGISTRY_SCHEMA) fail("resolve", "not a " + REGISTRY_SCHEMA + " index");
    const entry = index.models && index.models[name];
    if (!entry || !Array.isArray(entry.checkpoints) || !entry.checkpoints.length)
      fail("resolve", "no registered checkpoints for model '" + name + "'");
    const definition = opts.definition || null;
    const wanted = definition ? definition.structure_id : opts.structure_id;
    let chosen = null, how = "";
    if (opts.version !== undefined && opts.version !== null) {
      chosen = entry.checkpoints.find(function (c) { return c.version === opts.version; }) || null;
      if (!chosen) fail("resolve", "model '" + name + "' has no version " + opts.version);
      how = "version";
    } else if (entry.active && !opts.ignoreActive) {
      chosen = entry.checkpoints.find(function (c) { return c.id === entry.active; }) || null;
      how = "active";
      if (chosen && wanted && chosen.structure_id !== wanted) chosen = null; // fall through to newest compatible
    }
    if (!chosen) {
      const pool = eligible(entry, { roles: opts.roles, structure_id: wanted });
      pool.sort(function (a, b) { return b.version - a.version; });
      chosen = pool[0] || null;
      how = "newest";
      if (!chosen) fail("resolve", "model '" + name + "' has no " + (opts.roles || ["final", "best"]).join("/") +
        " checkpoint" + (wanted ? " with structure " + wanted : ""));
    }
    if (wanted && chosen.structure_id !== wanted)
      fail("resolve", "structure conflict: checkpoint " + chosen.id + " is " + chosen.structure_id + " (" +
        chosen.structure_label + ") but the definition is " + wanted + (definition ? " (" + definition.structure_label + ")" : ""));
    return Object.assign({ resolved_by: how }, chosen);
  }

  function joinPath(dir, rel) {
    if (/^([A-Za-z]:)?[\\/]/.test(rel)) return rel;
    if (!dir || dir === ".") return rel;
    return dir.replace(/[\\/]+$/, "") + "/" + rel;
  }
  function dirname(path) {
    const i = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
    return i < 0 ? "." : path.slice(0, i) || "/";
  }

  // A `models[]` entry for TRECH_CONFIG from the registry index. In QuickJS, `index` may be the
  // index path (read with TRECH_READ_JSON relative to the calling scenario); the checkpoint path
  // is returned relative to the same base, so the engine's normal model-path resolution applies.
  // `fallbackPath` (e.g. a committed data/ model) is used only when the index or checkpoint is
  // absent, and the entry says so in `registry.fallback`.
  function modelEntry(definitionOrName, opts) {
    opts = opts || {};
    const definition = isObject(definitionOrName) ? definitionOrName : null;
    const name = definition ? definition.name : String(definitionOrName);
    let index = opts.index, indexPath = opts.indexPath || null;
    if (typeof index === "string") {
      indexPath = index;
      try {
        index = typeof TRECH_READ_JSON === "function" ? TRECH_READ_JSON(indexPath) : null;
      } catch (error) {
        index = null;
        if (!opts.fallbackPath) fail("modelEntry(" + name + ")", "cannot read registry index " + indexPath + ": " + error.message);
      }
    }
    const scale = opts.scale !== undefined ? opts.scale : definition ? definition.scale : null;
    const entry = { name: opts.as || name, path: null };
    if (scale) entry.scale = scale;
    let checkpoint = null;
    if (index) {
      try {
        checkpoint = resolve(index, name, { version: opts.version, definition: definition, roles: opts.roles, structure_id: opts.structure_id });
      } catch (error) {
        if (!opts.fallbackPath || /structure conflict/.test(error.message)) throw error;
      }
    }
    if (checkpoint) {
      const file = checkpoint.files.find(function (f) { return f.format === (opts.format || "generic_surrogate"); });
      if (!file) fail("modelEntry(" + name + ")", "checkpoint " + checkpoint.id + " has no " + (opts.format || "generic_surrogate") + " file");
      entry.path = joinPath(indexPath ? dirname(indexPath) : opts.storeDir || ".", file.path);
      entry.registry = { checkpoint: checkpoint.id, version: checkpoint.version, structure_id: checkpoint.structure_id,
        sha256: file.sha256, resolved_by: checkpoint.resolved_by, fallback: false };
    } else if (opts.fallbackPath) {
      entry.path = opts.fallbackPath;
      entry.registry = { checkpoint: null, fallback: true };
    } else {
      fail("modelEntry(" + name + ")", "no registry index given (pass {index: 'path/to/index.json'} or {fallbackPath})");
    }
    if (opts.withRegistry === false) delete entry.registry;
    return entry;
  }

  function declarations() {
    return { definitions: declared.definitions.slice(), searches: declared.searches.slice() };
  }
  function reset() {
    declared = { definitions: [], searches: [] };
  }

  return {
    DEFINITION_SCHEMA: DEFINITION_SCHEMA, SEARCH_SCHEMA: SEARCH_SCHEMA, REGISTRY_SCHEMA: REGISTRY_SCHEMA,
    SCALES: SCALES, FAMILIES: FAMILIES, LINKS: LINKS, SOURCES: SOURCES, FORMATS: FORMATS, ROLES: ROLES,
    STRATEGIES: STRATEGIES, OBJECTIVES: OBJECTIVES, ACTIVATIONS: ACTIVATIONS, SHAPES: SHAPES, SELECTION_RULES: SELECTION_RULES,
    defineModel: defineModel, defineSearch: defineSearch, candidates: candidates, score: score, rank: rank,
    lossStats: lossStats, select: select, runFolds: runFolds, foldStats: foldStats,
    SET_FAMILIES: SET_FAMILIES, POOLS: POOLS, AGGREGATES: AGGREGATES,
    layerPlan: layerPlan, parameterCount: parameterCount, planParameterCount: planParameterCount, checkpointSignature: checkpointSignature,
    structureFromPlan: structureFromPlan, structureId: structureIdOf, describeStructure: describeStructure,
    resolve: resolve, modelEntry: modelEntry, declarations: declarations, reset: reset,
    canonical: canonical, fnv1a64: fnv1a64
  };
})();
if (typeof module !== "undefined" && module.exports) module.exports = globalThis.TRECH_ML;
