// Helper module for experiments; load with TRECH_INCLUDE or inline as needed.
globalThis.TRECH_HELPERS = (function() {
  function toArray(value) {
    if (value === undefined || value === null) {
      return [];
    }
    return Array.isArray(value) ? value : [value];
  }

  const units = {
    eV: (value) => value * 1e-6,
    keV: (value) => value * 1e-3,
    MeV: (value) => value,
    GeV: (value) => value * 1e3,
    mm: (value) => value,
    cm: (value) => value * 10.0,
    m: (value) => value * 1000.0,
    nm: (value) => value * 1e-6
  };

  const constants = {
    avogadro: 6.02214076e23,
    boltzmannEvK: 8.617333262e-5,
    carbonWallThicknessNm: 0.34
  };

  function clamp01(value) {
    if (value < 0.0) {
      return 0.0;
    }
    if (value > 1.0) {
      return 1.0;
    }
    return value;
  }

  function cloneMaterialPreset(preset, overrides) {
    const base = Object.assign({}, preset);
    if (preset.components) {
      base.components = preset.components.map((component) => Object.assign({}, component));
    }
    return Object.assign(base, overrides || {});
  }

  const materialPresets = {
    water: {
      name: "water",
      smiles: "O",
      densityGcm3: 1.0,
      components: [{ material: "G4_WATER", fraction: 1.0 }]
    },
    air: {
      name: "air",
      smiles: "[N]#[N].[O]=[O]",
      densityGcm3: 0.001225,
      components: [{ material: "G4_AIR", fraction: 1.0 }]
    },
    carbon: {
      name: "carbon",
      smiles: "C",
      densityGcm3: 2.2,
      components: [{ material: "G4_C", fraction: 1.0 }]
    },
    vacuum: {
      name: "vacuum",
      smiles: "",
      densityGcm3: 1e-25,
      components: [{ material: "G4_Galactic", fraction: 1.0 }]
    },
    brine: (salinityFraction) => {
      const salt = clamp01(typeof salinityFraction === "number" ? salinityFraction : 0.02);
      const water = clamp01(1.0 - salt);
      return {
        name: "brine",
        smiles: "O.[Na+].[Cl-]",
        densityGcm3: 1.02,
        components: [
          { material: "G4_WATER", fraction: water },
          { material: "G4_SODIUM_CHLORIDE", fraction: salt }
        ]
      };
    }
  };

  const materialAliases = {
    air: "G4_AIR",
    water: "G4_WATER",
    carbon: "G4_C",
    vacuum: "G4_Galactic"
  };

  const materialRegistry = {
    presets: materialPresets,
    fromPreset: (key, overrides) => {
      const preset = materialPresets[key];
      if (!preset) {
        throw new Error("Unknown material preset: " + key);
      }
      if (typeof preset === "function") {
        return cloneMaterialPreset(preset(), overrides);
      }
      return cloneMaterialPreset(preset, overrides);
    }
  };

  function normalizeVector(value, fallback) {
    if (Array.isArray(value) && value.length >= 3) {
      return [value[0], value[1], value[2]];
    }
    return fallback || [0, 0, 0];
  }

  function boxVolume(options) {
    if (!options || !options.name) {
      throw new Error("boxVolume requires name");
    }
    return {
      name: options.name,
      material: options.material || "",
      shape: { type: "box", sizeMm: normalizeVector(options.sizeMm, [1, 1, 1]) },
      placement: {
        parent: options.parent || "world",
        positionMm: normalizeVector(options.positionMm, [0, 0, 0]),
        rotationDeg: normalizeVector(options.rotationDeg, [0, 0, 0])
      },
      scoreEdep: !!options.scoreEdep,
      tags: toArray(options.tags)
    };
  }

  function tubeVolume(options) {
    if (!options || !options.name) {
      throw new Error("tubeVolume requires name");
    }
    return {
      name: options.name,
      material: options.material || "",
      shape: {
        type: "tube",
        innerRadiusMm: options.innerRadiusMm || 0.0,
        outerRadiusMm: options.outerRadiusMm || 0.0,
        lengthMm: options.lengthMm || 0.0
      },
      placement: {
        parent: options.parent || "world",
        positionMm: normalizeVector(options.positionMm, [0, 0, 0]),
        rotationDeg: normalizeVector(options.rotationDeg, [0, 0, 0])
      },
      scoreEdep: !!options.scoreEdep,
      tags: toArray(options.tags)
    };
  }

  function containerBox(options) {
    const volume = boxVolume(
      Object.assign({}, options, {
        material: options.material || materialAliases.vacuum,
        scoreEdep: false,
        tags: ["container"].concat(toArray(options.tags))
      })
    );
    return volume;
  }

  function composeBeams(base, variants) {
    return toArray(variants).map((variant) => {
      return Object.assign({}, base, variant);
    });
  }

  function pickBeam(beams, name) {
    const list = toArray(beams);
    if (name) {
      const match = list.find((beam) => beam && beam.name === name);
      if (match) {
        return match;
      }
    }
    const active = list.find((beam) => beam && beam.active);
    return active || list[0];
  }

  return {
    units,
    constants,
    toArray,
    composeBeams,
    pickBeam,
    materialPresets,
    materialRegistry,
    materialAliases,
    geometry: {
      boxVolume,
      tubeVolume,
      containerBox
    }
  };
})();
