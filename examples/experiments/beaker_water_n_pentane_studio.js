// Studio reference wrapper for beaker_water_n_pentane.js.
//
// The underlying experiment still infers phase separation, layer order,
// colour, temperature-aware evaporation, and the staged pour/intermix/separate/
// moving-plume positions + clocks. These contrasting tints and mild vapour emphasis
// are representation-only labels so the two physically colourless phases are
// distinguishable in a compact GIF; layout remains `inferred` and therefore
// follows the cascade result.

globalThis.TRECH_BEAKER_VIZ_OVERRIDE = {
  waterTint: [0.58, 0.82, 1.0],
  pentaneTint: [1.0, 0.78, 0.38],
  waterAlpha: 0.24,
  pentaneAlpha: 0.30,
  vaporAlpha: 0.12,
  vaporExaggeration: 1.5,
  layout: "inferred"
};

TRECH_INCLUDE("beaker_water_n_pentane.js");
