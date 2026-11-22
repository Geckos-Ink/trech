// Read recorded optics and comparison-only chemical identities. No inferred
// material properties, reaction laws, or substitution for missing Geant4 facts.
if (!globalThis.TRECH_MATH) TRECH_INCLUDE("trech_math.js");
globalThis.TRECH_MATERIAL_FACTS = (function () {
  "use strict";
  // Engine trace channel (docs/engine/engine_trace.md), silent unless tracing is on. trech and the
  // Node model loader provide TRECH_TRACE, plain Node loads js/trech_trace.js, any other host
  // gets a no-op. Logging never changes a result.
  const trace = (globalThis.TRECH_TRACE || (typeof require === "function" ? require("./trech_trace.js") : null) ||
    {channel: () => ({info() {}, log() {}, debug() {}, trace() {}, count() {}, enabled: () => false,
      span: (name, fn) => fn()})}).channel("material_facts");
  const { clamp01 } = globalThis.TRECH_MATH;
  function opticsRecord(ctx, name) {
    const item = ctx.optics && ctx.optics[name];
    if (!item || !Array.isArray(item.display_rgb)) {
      throw new Error("ctx.optics missing Geant4-derived colour for " + name);
    }
    if (trace.enabled("trace")) trace.trace("Geant4-derived optics read", {material: name, display_rgb: item.display_rgb});
    return item;
  }
  function opticsRgb(ctx, name) {
    return opticsRecord(ctx, name).display_rgb.slice(0, 3).map(clamp01);
  }
  function optics(ctx, name, includeNote) {
    const item = opticsRecord(ctx, name);
    const result = {
      rgb: item.display_rgb.slice(0, 3).map(clamp01),
      refractiveIndex: Number(item.mean_refractive_index),
      absorptionLengthMm: Number(item.mean_absorption_length_mm),
      scatterLengthMm: Number(item.mean_scatter_length_mm)
    };
    // Preserve the existing scenario payloads: some record the extractor note.
    if (includeNote) result.note = item.note;
    return result;
  }
  function pubchemStructure(name) {
    if (typeof globalThis.TRECH_PUBCHEM !== "function") {
      throw new Error("TRECH_PUBCHEM unavailable; fetch the build-local structure cache first");
    }
    const raw = globalThis.TRECH_PUBCHEM(name);
    if (!raw || !raw.cid || !raw.smiles) {
      throw new Error("PubChem structure cache for " + name + " must contain cid + smiles");
    }
    // An independent PubChem reference (not a Geant4 or learned result).
    trace.debug("PubChem structure read", {name: String(name), cid: Number(raw.cid)});
    return { cid: Number(raw.cid), smiles: String(raw.smiles),
             formula: String(raw.molecular_formula || "") };
  }
  // Lexical element inventory only, matching the existing identity check. This
  // is not a formula parser, valence check, or chemical-stability calculation.
  function formulaElements(formula) {
    const out = [];
    const re = /([A-Z][a-z]?)(\d*)/g;
    let match;
    while ((match = re.exec(formula)) !== null) {
      if (match[1] && out.indexOf(match[1]) < 0) out.push(match[1]);
    }
    return out;
  }
  function structureConsistent(structures, declaredElements) {
    return Object.keys(structures).every((key) =>
      formulaElements(structures[key].formula).every(
        (element) => declaredElements.indexOf(element) >= 0));
  }
  return { opticsRgb, optics, pubchemStructure, formulaElements, structureConsistent };
})();
